"""comm.metering — per-message metering through the REAL wallet ledger (Wave 3, guard #1).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §6 — "Per-message metering through the real
reserve->settle/release ledger (idem_key=comms:{message_id}). A provider 5xx -> release, never
bills. The pseudocode's wallet.debit() does not exist — strike it everywhere."

THE LAW (why reserve->settle/release, not a single debit):
  * BEFORE the send we wallet.reserve(estimated_cost) -> a HOLD (no double-spend; atomic
    conditional UPDATE in wallet.py). A reserve idem_key=comms:{message_id} makes a retried
    create_task safe (the same key reserves once).
  * AFTER a SUCCESSFUL send we wallet.settle(hold, actual_cost) -> charges actual (<= reserved),
    refunds the remainder. Idempotent on settle:comms:{message_id}.
  * AFTER a FAILED send (provider 5xx / timeout / blocked) we wallet.release(hold) -> the hold
    returns to available. NEVER BILLS A FAILED SEND.
  * There is NO wallet.debit() — the plan's pseudocode was wrong. We use the LIVE ACID core.

EARNER LAW / DEGRADE:
  * wallet unavailable (no PG) OR cost==0 (Telegram is free) -> metering is a NO-OP that returns a
    permissive ticket: the send still proceeds. A guard must NEVER block a free send or crash the
    detached post-call task.
  * NEVER raises. Every entrypoint returns a small dataclass; failures degrade to a no-op ticket.
  * Zero I/O at import; wallet is imported lazily (a local build box without wallet.py still works).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger("comm.metering")


@dataclass
class MeterTicket:
    """The handle returned by reserve_for_send(); passed to finalize(). `hold_id` None means
    'no hold was taken' (free send / wallet down / disabled) -> finalize is a no-op."""
    hold_id: Optional[int] = None
    message_id: str = ""
    reserved_minor: int = 0
    tenant_id: str = ""
    ok: bool = True            # False ONLY on a hard 'insufficient funds' reserve (a real block)
    reason: str = ""           # 'free' | 'wallet_unavailable' | 'metering_off' | 'reserved' | 'insufficient_funds'


def _wallet():
    """Lazy import of the live wallet ACID core (degrade to None off-box)."""
    try:
        import wallet  # type: ignore
        return wallet
    except Exception:  # noqa: BLE001
        return None


def reserve_for_send(tenant_id: str, message_id: str, estimated_cost_minor: int) -> MeterTicket:
    """Reserve `estimated_cost_minor` paise BEFORE a send. Returns a MeterTicket.

      * estimated_cost <= 0 (Telegram is free) -> a no-op permissive ticket (no hold).
      * metering flag off OR wallet unavailable -> a no-op permissive ticket (send proceeds).
      * insufficient funds -> ticket.ok = False (the caller blocks the send with 'blocked_funds').
      * success -> ticket.hold_id set; finalize() must be called with the actual cost.

    Idempotent on reserve:comms:{message_id} (a retried create_task reserves exactly once).
    NEVER raises."""
    from . import config
    mid = (message_id or "").strip()
    est = int(estimated_cost_minor or 0)
    if est <= 0:
        return MeterTicket(hold_id=None, message_id=mid, reserved_minor=0,
                           tenant_id=tenant_id, ok=True, reason="free")
    if not config.metering_enabled():
        return MeterTicket(hold_id=None, message_id=mid, reserved_minor=est,
                           tenant_id=tenant_id, ok=True, reason="metering_off")
    w = _wallet()
    try:
        if not (w and w.available()):
            return MeterTicket(hold_id=None, message_id=mid, reserved_minor=est,
                               tenant_id=tenant_id, ok=True, reason="wallet_unavailable")
        hold_id = w.reserve(
            tenant_id, est,
            resource_type="comm_send", resource_id=mid,
            idem_key=f"reserve:comms:{mid}", actor="comm",
        )
        if hold_id is None:
            # insufficient funds is the ONE hard block metering imposes.
            return MeterTicket(hold_id=None, message_id=mid, reserved_minor=est,
                               tenant_id=tenant_id, ok=False, reason="insufficient_funds")
        return MeterTicket(hold_id=int(hold_id), message_id=mid, reserved_minor=est,
                           tenant_id=tenant_id, ok=True, reason="reserved")
    except Exception as exc:  # noqa: BLE001 — a metering fault must never block/crash the send
        _log.warning("comm.metering.reserve_for_send degraded: %r", type(exc).__name__)
        return MeterTicket(hold_id=None, message_id=mid, reserved_minor=est,
                           tenant_id=tenant_id, ok=True, reason="wallet_unavailable")


def finalize(ticket: MeterTicket, *, sent_ok: bool, actual_cost_minor: int = -1) -> dict:
    """Settle (on a successful send) or release (on a failed send) the reservation.

      * no hold (free / disabled / wallet-down) -> no-op {ok:True, charged_minor:0}.
      * sent_ok=True  -> settle(hold, actual) — charges min(actual, reserved), refunds remainder.
                         actual_cost_minor<0 means 'charge the full reservation' (Telegram never
                         hits this — it's the paid-channel path where actual==estimated).
      * sent_ok=False -> release(hold) — the provider failed (5xx/timeout/blocked): NEVER BILL.

    Idempotent on settle:comms:{mid} / release:comms:{mid}. NEVER raises."""
    if ticket is None or ticket.hold_id is None:
        return {"ok": True, "charged_minor": 0, "note": "no_hold"}
    w = _wallet()
    if not (w and getattr(w, "available", lambda: False)()):
        return {"ok": False, "reason": "wallet_unavailable", "charged_minor": 0}
    mid = ticket.message_id
    try:
        if sent_ok:
            actual = int(actual_cost_minor)
            if actual < 0:
                actual = int(ticket.reserved_minor)
            res = w.settle(int(ticket.hold_id), actual, idem_key=f"settle:comms:{mid}", actor="comm")
            return {"ok": bool(res.get("ok")), "charged_minor": int(res.get("charged_minor") or 0),
                    "refunded_minor": int(res.get("refunded_minor") or 0)}
        # failed send -> release the whole hold (no charge).
        res = w.release(int(ticket.hold_id), idem_key=f"release:comms:{mid}",
                        reason="send_failed", actor="comm")
        return {"ok": bool(res.get("ok")), "charged_minor": 0,
                "released_minor": int(res.get("released_minor") or 0)}
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.metering.finalize degraded: %r", type(exc).__name__)
        return {"ok": False, "reason": "error", "charged_minor": 0}
