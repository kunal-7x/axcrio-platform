"""wallet.py — Credit/Wallet ACID ledger transactional core (BUILD-don't-compose money custody).

Spec: design/credit-ledger-firewall.md §4 (RED-TEAM fixes folded). Tables: db/ddl_wallet.sql.

WHY this rides db.engine (sync psycopg2) instead of a raw asyncpg pool (spec §4):
  * Reuses the P1 `db.engine.session(tenant_id, is_admin)` FORCE-RLS GUC (SET LOCAL app.tenant_id /
    app.is_admin IN-txn) + admin escape hatch — no 3rd connection pool to the same DB (spec residual-risk 1),
    no duplicated GUC plumbing. caller.py handlers already run the _read/_write seam sync inside async
    routes, so a sync wallet core is consistent and avoids an event-loop-blocking pool.
  * The correctness primitives are driver-independent:
      - NO-OVERSELL  = ONE atomic conditional UPDATE  (... WHERE available_minor >= :amt RETURNING ...).
        Under READ COMMITTED a 2nd concurrent UPDATE on the same row BLOCKS, then re-evaluates the WHERE
        against the just-committed row -> 0 rows -> insufficient funds. NEVER read-check-write.
      - NO-DOUBLE-CHARGE = INSERT INTO wallet_idempotency ... ON CONFLICT DO NOTHING. The loser of a
        concurrent settle BLOCKS on the unique-key lock until the winner COMMITs, then reads the result
        the winner stored IN THE SAME TXN. (A SELECT-then-INSERT check would reopen the race.)

HARD INVARIANT: every public op = EXACTLY ONE `with engine.session() as s:` block. The idempotency
INSERT + the balance UPDATE + the hold mutation + the result-store all share ONE txn / ONE COMMIT. Split
any of them across two session() calls and the no-double-charge guarantee silently dies.

IMPORT-SAFE DEGRADE: if PG is down / db.engine unavailable, available() -> False and every entrypoint
returns a clean "unavailable" signal (reserve->None, settle/release/topup->{ok:False}, balance->None).
caller.py then forces the legacy/postpaid path. The live site never breaks because Postgres is down.

Money is INTEGER MINOR UNITS (paise) end to end. NO float touches money. Display layer divides by 100.
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Hold TTL: a crashed/lost call's hold is released by the sweep this long after reserve.
HOLD_TTL_S = int(os.getenv("WALLET_HOLD_TTL_S", "900") or 900)
DEFAULT_CURRENCY = "INR"

# Test/negative-control hook: when True, reserve() drops the `available_minor >= :amt` guard so the
# concurrency proof can demonstrate it OVERSELLS without the guard (proving the test has teeth). NEVER
# set in production; defaults False; the proof harness flips it on a throwaway tenant only.
_UNSAFE_NO_OVERSELL_GUARD = False


# ============================================================================
# availability (mirrors kb.core / store.py degrade contract)
# ============================================================================
def _engine():
    try:
        from db import engine  # type: ignore
        return engine
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    """True iff Postgres is usable (the authoritative balance lives there)."""
    eng = _engine()
    try:
        return bool(eng and eng.available())
    except Exception:  # noqa: BLE001
        return False


def status() -> dict:
    return {"pg_available": available(), "hold_ttl_s": HOLD_TTL_S}


def _text(sql: str):
    from sqlalchemy import text
    return text(sql)


# ============================================================================
# read: balance (cheap single-row SELECT; no hold scan) — F5
# ============================================================================
def balance(tenant_id: str, currency: str = DEFAULT_CURRENCY,
            is_admin: bool = False) -> Optional[dict]:
    """Return {available_minor, held_minor, lifetime_topup_minor, lifetime_spend_minor, currency}
    or None when PG is unavailable OR no account row exists. Cheap; the /run admission pre-check uses
    it and MUST degrade to None (skip the wallet pre-check) on any PG blip, never 402 a postpaid tenant."""
    if not available():
        return None
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            row = s.execute(_text(
                "SELECT available_minor, held_minor, lifetime_topup_minor, lifetime_spend_minor "
                "FROM wallet_accounts WHERE tenant_id=:t AND currency=:c"
            ), {"t": tenant_id, "c": currency}).fetchone()
            if row is None:
                return None
            return {
                "currency": currency,
                "available_minor": int(row[0]),
                "held_minor": int(row[1]),
                "lifetime_topup_minor": int(row[2]),
                "lifetime_spend_minor": int(row[3]),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.balance failed: %r", exc)
        return None


def _ensure_account(s, tenant_id: str, currency: str) -> None:
    """Create the (tenant,currency) account row at 0 balance if absent. Same txn as the caller.
    ON CONFLICT DO NOTHING makes it race-safe (two concurrent first-ops can't both insert)."""
    s.execute(_text(
        "INSERT INTO wallet_accounts (tenant_id, currency) VALUES (:t, :c) "
        "ON CONFLICT (tenant_id, currency) DO NOTHING"
    ), {"t": tenant_id, "c": currency})


def _idem_get(s, idem_key: str) -> Optional[dict]:
    """Claim the idempotency key in THIS txn. Returns None if we are the FIRST (claimed it ->
    proceed to apply the money move), or the previously-stored result dict if it already ran.

    The INSERT ... ON CONFLICT DO NOTHING is the concurrency gate: the loser of a race BLOCKS on the
    PK lock until the winner COMMITs, then this SELECT reads the result the winner stored in-txn."""
    if not idem_key:
        return None
    ins = s.execute(_text(
        "INSERT INTO wallet_idempotency (idem_key, tenant_id, op, result) "
        "VALUES (:k, '', '', '{}'::jsonb) ON CONFLICT (idem_key) DO NOTHING RETURNING idem_key"
    ), {"k": idem_key}).fetchone()
    if ins is not None:
        return None  # we are first; placeholder row claimed
    # conflict: another txn already created/committed it -> read its stored result
    row = s.execute(_text(
        "SELECT result FROM wallet_idempotency WHERE idem_key=:k"
    ), {"k": idem_key}).fetchone()
    if row is None:
        return None
    res = row[0]
    return res if isinstance(res, dict) else json.loads(res)


def _idem_store(s, idem_key: str, tenant_id: str, op: str, result: dict) -> None:
    """Persist the op's result onto the idempotency row IN THIS TXN (before COMMIT), so a concurrent
    loser that blocked on the PK lock reads a populated result, not an empty placeholder."""
    if not idem_key:
        return
    s.execute(_text(
        "UPDATE wallet_idempotency SET tenant_id=:t, op=:op, result=CAST(:r AS jsonb) WHERE idem_key=:k"
    ), {"t": tenant_id, "op": op, "r": json.dumps(result), "k": idem_key})


def _append_tx(s, tenant_id: str, currency: str, kind: str, amount_minor: int,
               held_delta_minor: int, balance_after_minor: int, resource_type: str = "",
               resource_id: str = "", hold_id: Optional[int] = None, idem_key: Optional[str] = None,
               actor: str = "", meta: Optional[dict] = None) -> int:
    """Append one immutable wallet_transactions row in the current txn. Returns its id."""
    row = s.execute(_text(
        "INSERT INTO wallet_transactions "
        "(tenant_id, currency, kind, amount_minor, held_delta_minor, resource_type, resource_id, "
        " hold_id, idempotency_key, balance_after_minor, actor, meta) "
        "VALUES (:t,:c,:k,:amt,:hd,:rt,:rid,:hid,:ik,:bal,:actor,CAST(:meta AS jsonb)) RETURNING id"
    ), {
        "t": tenant_id, "c": currency, "k": kind, "amt": amount_minor, "hd": held_delta_minor,
        "rt": resource_type, "rid": resource_id, "hid": hold_id, "ik": idem_key,
        "bal": balance_after_minor, "actor": actor, "meta": json.dumps(meta or {}),
    }).fetchone()
    return int(row[0])


# ============================================================================
# topup(tenant, amount_minor, ...) — admin/payment credit. Idempotent on payment_ref. §4
# ============================================================================
def topup(tenant_id: str, amount_minor: int, actor: str = "", idem_key: str = "",
          currency: str = DEFAULT_CURRENCY, is_admin: bool = True,
          meta: Optional[dict] = None) -> dict:
    """Credit available_minor by amount_minor. is_admin defaults True (admin/payment op). Idempotent
    on idem_key (e.g. 'topup:<payment_ref>') so a webhook retry can't double-credit."""
    if not available():
        return {"ok": False, "reason": "wallet_unavailable"}
    amount_minor = int(amount_minor)
    if amount_minor <= 0:
        return {"ok": False, "reason": "amount_must_be_positive"}
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            prior = _idem_get(s, idem_key)
            if prior is not None:
                return prior
            _ensure_account(s, tenant_id, currency)
            row = s.execute(_text(
                "UPDATE wallet_accounts "
                "SET available_minor = available_minor + :amt, "
                "    lifetime_topup_minor = lifetime_topup_minor + :amt, "
                "    version = version + 1, updated_at = now() "
                "WHERE tenant_id=:t AND currency=:c "
                "RETURNING available_minor, held_minor"
            ), {"amt": amount_minor, "t": tenant_id, "c": currency}).fetchone()
            avail_after = int(row[0])
            _append_tx(s, tenant_id, currency, "topup", amount_minor, 0, avail_after,
                       resource_type="manual", resource_id=idem_key.split(":")[-1] if idem_key else "",
                       idem_key=idem_key, actor=actor, meta=meta)
            result = {"ok": True, "available_minor": avail_after, "held_minor": int(row[1]),
                      "credited_minor": amount_minor}
            _idem_store(s, idem_key, tenant_id, "topup", result)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.topup failed: %r", exc)
        return {"ok": False, "reason": "error", "detail": repr(exc)[:160]}


# ============================================================================
# reserve(tenant, amount_minor, ...) — INVARIANT 1: no oversell via ONE atomic UPDATE. §4
# Returns the hold_id (int) on success, or None on insufficient funds / unavailable.
# ============================================================================
def reserve(tenant_id: str, amount_minor: int, resource_type: str = "", resource_id: str = "",
            idem_key: str = "", currency: str = DEFAULT_CURRENCY, is_admin: bool = False,
            ttl_s: Optional[int] = None, actor: str = "") -> Optional[int]:
    """Atomically move `amount_minor` from available -> held and open a hold. ONE txn:
      idempotency claim -> atomic conditional UPDATE (WHERE available>=amt) -> insert hold + tx -> store.
    0 rows from the UPDATE == insufficient funds -> rollback, return None (no race window)."""
    if not available():
        return None
    amount_minor = int(amount_minor)
    if amount_minor <= 0:
        return None
    eng = _engine()
    ttl = int(ttl_s if ttl_s is not None else HOLD_TTL_S)
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            if idem_key:
                prior = _idem_get(s, idem_key)
                if prior is not None:
                    return prior.get("hold_id")
            _ensure_account(s, tenant_id, currency)
            # INVARIANT 1: atomic check+decrement in a single statement. NEVER read-check-write.
            if _UNSAFE_NO_OVERSELL_GUARD:
                # NEGATIVE CONTROL ONLY (proof harness): same UPDATE WITHOUT the funds guard -> oversells.
                row = s.execute(_text(
                    "UPDATE wallet_accounts SET available_minor = available_minor - :amt, "
                    "held_minor = held_minor + :amt, version = version + 1, updated_at = now() "
                    "WHERE tenant_id=:t AND currency=:c RETURNING available_minor"
                ), {"amt": amount_minor, "t": tenant_id, "c": currency}).fetchone()
            else:
                row = s.execute(_text(
                    "UPDATE wallet_accounts SET available_minor = available_minor - :amt, "
                    "held_minor = held_minor + :amt, version = version + 1, updated_at = now() "
                    "WHERE tenant_id=:t AND currency=:c AND available_minor >= :amt "
                    "RETURNING available_minor"
                ), {"amt": amount_minor, "t": tenant_id, "c": currency}).fetchone()
            if row is None:
                # insufficient funds. Store a negative idem result so a retry is consistent.
                if idem_key:
                    _idem_store(s, idem_key, tenant_id, "reserve", {"ok": False, "hold_id": None,
                                                                    "reason": "insufficient_funds"})
                return None
            avail_after = int(row[0])
            hold_row = s.execute(_text(
                "INSERT INTO wallet_holds (tenant_id, currency, amount_minor, state, resource_type, "
                " resource_id, expires_at) "
                "VALUES (:t,:c,:amt,'open',:rt,:rid, now() + (:ttl || ' seconds')::interval) RETURNING id"
            ), {"t": tenant_id, "c": currency, "amt": amount_minor, "rt": resource_type,
                "rid": resource_id, "ttl": ttl}).fetchone()
            hold_id = int(hold_row[0])
            _append_tx(s, tenant_id, currency, "hold", 0, amount_minor, avail_after,
                       resource_type=resource_type, resource_id=resource_id, hold_id=hold_id,
                       idem_key=idem_key, actor=actor)
            if idem_key:
                _idem_store(s, idem_key, tenant_id, "reserve", {"ok": True, "hold_id": hold_id})
            return hold_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.reserve failed: %r", exc)
        return None


# ============================================================================
# settle(hold_id, actual_minor, idem_key) — INVARIANT 2: idempotent capture keyed by call_id. §4
# ============================================================================
def settle(hold_id: int, actual_minor: int, idem_key: str = "", is_admin: bool = False,
           actor: str = "", meta: Optional[dict] = None) -> dict:
    """Capture a hold: charge actual=min(actual_minor, hold.amount), refund the remainder, close the
    hold. Idempotent on idem_key='settle:call:<call_id>' — a second (even CONCURRENT) settle returns
    the stored result and applies NOTHING (double-charge guard). ONE txn."""
    if not available():
        return {"ok": False, "reason": "wallet_unavailable"}
    actual_minor = max(0, int(actual_minor))
    eng = _engine()
    try:
        # we need the hold's tenant for the GUC; an admin session can read any tenant's hold safely.
        with eng.session(tenant_id="", is_admin=True) as s:
            if idem_key:
                prior = _idem_get(s, idem_key)
                if prior is not None:
                    return prior
            hold = s.execute(_text(
                "SELECT tenant_id, currency, amount_minor, state FROM wallet_holds "
                "WHERE id=:h FOR UPDATE"
            ), {"h": int(hold_id)}).fetchone()
            if hold is None:
                result = {"ok": False, "reason": "hold_not_found", "hold_id": hold_id}
                _idem_store(s, idem_key, "", "settle", result)
                return result
            tenant_id, currency, reserved, state = hold[0], hold[1], int(hold[2]), hold[3]
            if state != "open":
                # already settled/released/expired -> return a stable outcome, apply nothing.
                result = {"ok": True, "hold_id": hold_id, "state": state, "charged_minor": None,
                          "note": "hold_not_open"}
                _idem_store(s, idem_key, tenant_id, "settle", result)
                return result
            charged = min(actual_minor, reserved)   # never charge more than reserved
            refund = reserved - charged
            row = s.execute(_text(
                "UPDATE wallet_accounts SET "
                "  held_minor = held_minor - :reserved, "        # release the whole reservation
                "  available_minor = available_minor + :refund, "  # return unspent remainder
                "  lifetime_spend_minor = lifetime_spend_minor + :charged, "
                "  version = version + 1, updated_at = now() "
                "WHERE tenant_id=:t AND currency=:c "
                "RETURNING available_minor, held_minor"
            ), {"reserved": reserved, "refund": refund, "charged": charged,
                "t": tenant_id, "c": currency}).fetchone()
            avail_after = int(row[0])
            s.execute(_text(
                "UPDATE wallet_holds SET state='settled', settled_minor=:c, closed_at=now() WHERE id=:h"
            ), {"c": charged, "h": int(hold_id)})
            # audit rows: hold_settle (release the reservation) + charge (the real spend).
            _append_tx(s, tenant_id, currency, "hold_settle", 0, -reserved, avail_after,
                       resource_type="", resource_id="", hold_id=int(hold_id), idem_key=idem_key,
                       actor=actor, meta=meta)
            _append_tx(s, tenant_id, currency, "charge", -charged, 0, avail_after,
                       resource_type="", resource_id="", hold_id=int(hold_id), idem_key=idem_key,
                       actor=actor, meta=meta)
            result = {"ok": True, "hold_id": hold_id, "charged_minor": charged,
                      "refunded_minor": refund, "available_minor": avail_after,
                      "held_minor": int(row[1])}
            _idem_store(s, idem_key, tenant_id, "settle", result)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.settle failed: %r", exc)
        return {"ok": False, "reason": "error", "detail": repr(exc)[:160]}


# ============================================================================
# release(hold_id) — void an unused/leftover/expired reservation. Idempotent. §4
# ============================================================================
def release(hold_id: int, idem_key: str = "", reason: str = "released",
            actor: str = "") -> dict:
    """Return a still-open hold's reserved amount to available (dial failed -> nothing spent).
    `reason` records why ('released' | 'expired'). Idempotent via idem_key. ONE txn."""
    if not available():
        return {"ok": False, "reason": "wallet_unavailable"}
    eng = _engine()
    try:
        with eng.session(tenant_id="", is_admin=True) as s:
            if idem_key:
                prior = _idem_get(s, idem_key)
                if prior is not None:
                    return prior
            hold = s.execute(_text(
                "SELECT tenant_id, currency, amount_minor, state FROM wallet_holds "
                "WHERE id=:h FOR UPDATE"
            ), {"h": int(hold_id)}).fetchone()
            if hold is None:
                result = {"ok": False, "reason": "hold_not_found", "hold_id": hold_id}
                _idem_store(s, idem_key, "", "release", result)
                return result
            tenant_id, currency, reserved, state = hold[0], hold[1], int(hold[2]), hold[3]
            if state != "open":
                result = {"ok": True, "hold_id": hold_id, "state": state, "note": "hold_not_open"}
                _idem_store(s, idem_key, tenant_id, "release", result)
                return result
            row = s.execute(_text(
                "UPDATE wallet_accounts SET held_minor = held_minor - :amt, "
                "available_minor = available_minor + :amt, version = version + 1, updated_at = now() "
                "WHERE tenant_id=:t AND currency=:c RETURNING available_minor, held_minor"
            ), {"amt": reserved, "t": tenant_id, "c": currency}).fetchone()
            avail_after = int(row[0])
            new_state = "expired" if reason == "expired" else "released"
            s.execute(_text(
                "UPDATE wallet_holds SET state=:st, closed_at=now() WHERE id=:h"
            ), {"st": new_state, "h": int(hold_id)})
            _append_tx(s, tenant_id, currency, "hold_release", 0, -reserved, avail_after,
                       resource_type="", resource_id="", hold_id=int(hold_id), idem_key=idem_key,
                       actor=actor, meta={"reason": reason})
            result = {"ok": True, "hold_id": hold_id, "released_minor": reserved,
                      "state": new_state, "available_minor": avail_after, "held_minor": int(row[1])}
            _idem_store(s, idem_key, tenant_id, "release", result)
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.release failed: %r", exc)
        return {"ok": False, "reason": "error", "detail": repr(exc)[:160]}


# ============================================================================
# sweep_expired_holds() — crash-safety: release open holds past their TTL. §4
# ============================================================================
def sweep_expired_holds(limit: int = 200) -> dict:
    """Release every open hold whose expires_at < now() (a crashed/lost call leaked it). Idempotent
    per-hold via release()'s idem key. Returns {swept, released_minor}. Safe to call every scheduler tick."""
    if not available():
        return {"ok": False, "reason": "wallet_unavailable", "swept": 0}
    eng = _engine()
    swept = 0
    released_total = 0
    try:
        with eng.session(tenant_id="", is_admin=True) as s:
            rows = s.execute(_text(
                "SELECT id, resource_type, resource_id FROM wallet_holds "
                "WHERE state='open' AND expires_at < now() ORDER BY id LIMIT :lim"
            ), {"lim": int(limit)}).fetchall()
        for r in rows:
            hid = int(r[0])
            rt = r[1] or "hold"
            rid = r[2] or str(hid)
            res = release(hid, idem_key=f"release:expired:{rt}:{rid}:{hid}", reason="expired")
            if res.get("ok") and res.get("released_minor"):
                swept += 1
                released_total += int(res.get("released_minor") or 0)
        return {"ok": True, "swept": swept, "released_minor": released_total}
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.sweep_expired_holds failed: %r", exc)
        return {"ok": False, "reason": "error", "swept": swept}


# ============================================================================
# read helpers for the additive endpoints (transactions / holds)
# ============================================================================
def transactions(tenant_id: str, limit: int = 100, is_admin: bool = False) -> list[dict]:
    if not available():
        return []
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            rows = s.execute(_text(
                "SELECT id, kind, amount_minor, held_delta_minor, resource_type, resource_id, "
                "       balance_after_minor, hold_id, created_at "
                "FROM wallet_transactions WHERE tenant_id=:t ORDER BY id DESC LIMIT :lim"
            ), {"t": tenant_id, "lim": max(1, min(int(limit), 1000))}).fetchall()
            return [{
                "id": int(r[0]), "kind": r[1], "amount_minor": int(r[2]),
                "held_delta_minor": int(r[3]), "resource_type": r[4], "resource_id": r[5],
                "balance_after_minor": int(r[6]), "hold_id": (int(r[7]) if r[7] is not None else None),
                "at": r[8].isoformat() if r[8] else "",
            } for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.transactions failed: %r", exc)
        return []


def holds(tenant_id: str, state: str = "", is_admin: bool = False) -> list[dict]:
    if not available():
        return []
    eng = _engine()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            if state:
                rows = s.execute(_text(
                    "SELECT id, amount_minor, state, resource_type, resource_id, settled_minor, "
                    "       expires_at, created_at FROM wallet_holds "
                    "WHERE tenant_id=:t AND state=:st ORDER BY id DESC LIMIT 500"
                ), {"t": tenant_id, "st": state}).fetchall()
            else:
                rows = s.execute(_text(
                    "SELECT id, amount_minor, state, resource_type, resource_id, settled_minor, "
                    "       expires_at, created_at FROM wallet_holds "
                    "WHERE tenant_id=:t ORDER BY id DESC LIMIT 500"
                ), {"t": tenant_id}).fetchall()
            return [{
                "id": int(r[0]), "amount_minor": int(r[1]), "state": r[2],
                "resource_type": r[3], "resource_id": r[4],
                "settled_minor": (int(r[5]) if r[5] is not None else None),
                "expires_at": r[6].isoformat() if r[6] else "",
                "at": r[7].isoformat() if r[7] else "",
            } for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet.holds failed: %r", exc)
        return []
