"""credits/engine.py — the pluggable BillingEngine.

ONE interface, two implementations:
  • LocalCreditEngine  — the DEFAULT. Reads/writes the live wallet via a LAZY `import caller`
    (so there is no circular import at module load — exactly the ai_manager house pattern).
    Prefers the Postgres ACID wallet module when present; otherwise falls back to billing.json.
  • FlexpriceEngine     — a REST adapter (credits/flexprice_engine.py) selected with
    BILLING_ENGINE=flexprice once the FlexPrice stack is up. Falls back to Local for anything
    it cannot yet serve, so flipping it on can never regress the product.

Everything is best-effort + dormant-safe: a credits failure must NEVER break a call or a page.
Amounts cross the wire in BOTH ₹ (INR, the underlying wallet currency) and CREDITS (the
customer-facing unit, 1 credit = ₹CREDIT_INR_RATE).
"""
from __future__ import annotations

import os
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from . import pricing

# Engine-owned lock for the billing.json fallback path (the caller async _STORE_LOCK can't be
# taken from the worker threads our sync methods run in via asyncio.to_thread).
_LOCK = threading.RLock()

TOPUPS_FILE = "credits_topups.json"      # top-ups + grants + manual adjustments (one append-only log)
CREDITS_USAGE_FILE = "credits_usage.json"  # per-service metered usage rows (kb/crm/ads/creative/aim/sms…)


def _low_balance_threshold_inr() -> float:
    try:
        return float(os.getenv("CREDIT_LOW_BALANCE_INR", "100") or "100")
    except Exception:  # noqa: BLE001
        return 100.0


def _meter_charge_enabled() -> bool:
    """When truthy, record_usage() DEBITS the wallet (hard charge). Default OFF: metering only
    TRACKS usage (it shows in the Usage tab) without decrementing balances — safe to switch metering
    on platform-wide BEFORE tenants are funded / a top-up gateway exists. Flip CREDITS_METER_CHARGE=1
    to actually consume credits per usage event."""
    return (os.getenv("CREDITS_METER_CHARGE", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(s: str):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _month_start() -> datetime:
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class BillingEngine(ABC):
    """The contract every billing backend implements. All amounts in major units (₹) unless the
    field name says _credits. Implementations must be best-effort and never raise into a caller."""

    name = "base"

    @abstractmethod
    def wallet(self, tenant_id: str, is_admin: bool = False) -> dict: ...

    @abstractmethod
    def topup(self, tenant_id: str, amount_inr: float, *, idem_key: str = "",
              provider: str = "manual", payment_id: str = "", note: str = "",
              acting: str = "") -> dict: ...

    @abstractmethod
    def topups(self, tenant_id: str = "", limit: int = 100) -> list[dict]: ...

    @abstractmethod
    def ledger(self, tenant_id: str, limit: int = 100) -> list[dict]: ...

    @abstractmethod
    def usage(self, tenant_id: str, frm: str = "", to: str = "") -> dict: ...

    @abstractmethod
    def record_usage(self, tenant_id: str, service_key: str, qty: float, *,
                     meta: dict | None = None) -> dict: ...


class LocalCreditEngine(BillingEngine):
    """Default engine over the box's existing wallet / billing.json / cost_ledger primitives."""

    name = "local"

    # ---- caller bridge (lazy; never imported at module load) ----
    def _caller(self):
        import caller  # the live FastAPI app module (top-level on the box / under droplet_work in repo)
        return caller

    def _var(self):
        try:
            return self._caller().VAR
        except Exception:  # noqa: BLE001
            from pathlib import Path
            return Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))

    def _read(self, path, default):
        try:
            return self._caller()._read(path, default)
        except Exception:  # noqa: BLE001
            try:
                import json
                from pathlib import Path
                p = Path(path)
                return json.loads(p.read_text()) if p.exists() else default
            except Exception:  # noqa: BLE001
                return default

    def _write(self, path, data):
        try:
            self._caller()._write(path, data)
            return True
        except Exception:  # noqa: BLE001
            try:
                import json
                from pathlib import Path
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(data, indent=2))
                return True
            except Exception:  # noqa: BLE001
                return False

    def _topups_path(self):
        return self._var() / TOPUPS_FILE

    def _wallet_mod(self):
        try:
            wm = getattr(self._caller(), "_wallet_mod", None)
            return wm if (wm is not None and wm.available()) else None
        except Exception:  # noqa: BLE001
            return None

    # ---- balance ----
    def wallet(self, tenant_id: str, is_admin: bool = False) -> dict:
        rate = pricing.credit_rate()
        plan = "postpaid"
        balance_inr = 0.0
        held_inr = 0.0
        lifetime_topup_inr = 0.0
        lifetime_spend_inr = 0.0
        wallet_available = False
        try:
            c = self._caller()
            try:
                plan = (c._billing_for(tenant_id) or {}).get("plan", "postpaid")
            except Exception:  # noqa: BLE001
                plan = "postpaid"
            wm = self._wallet_mod()
            if wm is not None:
                bal = wm.balance(tenant_id, "INR", bool(is_admin))
                if bal:
                    balance_inr = round(bal["available_minor"] / 100.0, 2)
                    held_inr = round(bal["held_minor"] / 100.0, 2)
                    lifetime_topup_inr = round(bal["lifetime_topup_minor"] / 100.0, 2)
                    lifetime_spend_inr = round(bal["lifetime_spend_minor"] / 100.0, 2)
                    wallet_available = True
            if not wallet_available:
                # billing.json fallback (always present)
                b = c._billing_for(tenant_id) or {}
                balance_inr = round(float(b.get("balance", 0) or 0), 2)
                lifetime_topup_inr = round(sum(float(t.get("amount_inr", 0) or 0)
                                               for t in self.topups(tenant_id, limit=100000)
                                               if t.get("amount_inr", 0) and t.get("status") == "captured"), 2)
                lifetime_spend_inr = round(sum(float(e.get("cost", 0) or 0)
                                               for e in c._read_ledger(tenant_id)), 2)
        except Exception:  # noqa: BLE001
            pass
        mtd = self._mtd_spend_inr(tenant_id)
        low = (balance_inr <= _low_balance_threshold_inr()) or (plan == "prepaid" and balance_inr <= 0)
        return {
            "tenant_id": tenant_id,
            "currency": "INR",
            "credit_rate_inr": rate,
            "plan": plan,
            "balance_inr": balance_inr,
            "balance_credits": round(balance_inr / rate, 2),
            "held_inr": held_inr,
            "held_credits": round(held_inr / rate, 2),
            "lifetime_topup_inr": lifetime_topup_inr,
            "lifetime_topup_credits": round(lifetime_topup_inr / rate, 2),
            "lifetime_spend_inr": lifetime_spend_inr,
            "lifetime_spend_credits": round(lifetime_spend_inr / rate, 2),
            "mtd_spend_inr": mtd,
            "mtd_spend_credits": round(mtd / rate, 2),
            "low_balance": bool(low),
            "low_balance_threshold_inr": _low_balance_threshold_inr(),
            "wallet_available": wallet_available,
            "engine": self.name,
        }

    def _mtd_spend_inr(self, tenant_id: str) -> float:
        """Month-to-date spend from the per-call ledger (the billed truth)."""
        try:
            c = self._caller()
            start = _month_start()
            total = 0.0
            for e in c._read_ledger(tenant_id):
                ts = _parse_ts(e.get("at"))
                if ts is None or ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc) if ts else None
                if ts is None or ts >= start:
                    total += float(e.get("cost", 0) or 0)
            return round(total, 2)
        except Exception:  # noqa: BLE001
            return 0.0

    # ---- top-up / grant / adjust ----
    def topup(self, tenant_id: str, amount_inr: float, *, idem_key: str = "",
              provider: str = "manual", payment_id: str = "", note: str = "",
              acting: str = "") -> dict:
        rate = pricing.credit_rate()
        try:
            amt = round(float(amount_inr), 2)
        except Exception:  # noqa: BLE001
            return {"ok": False, "reason": "bad amount"}
        if amt == 0:
            return {"ok": False, "reason": "amount must be non-zero"}
        with _LOCK:
            rows = self._read(self._topups_path(), [])
            if not isinstance(rows, list):
                rows = []
            # idempotency — a webhook retry / double-submit must never double-credit
            if idem_key:
                for r in rows:
                    if r.get("idem_key") == idem_key and r.get("status") == "captured":
                        return {"ok": True, "deduped": True, "credited_inr": r.get("amount_inr", 0),
                                "credited_credits": r.get("credits", 0),
                                **{k: v for k, v in self.wallet(tenant_id, True).items()}}
            entry = {
                "id": uuid.uuid4().hex[:12],
                "tenant_id": tenant_id,
                "provider": provider,           # razorpay | stripe | grant | manual | adjust
                "payment_id": payment_id,
                "amount_inr": amt,
                "credits": round(amt / rate, 4),
                "status": "captured",
                "idem_key": idem_key or f"{provider}:{uuid.uuid4().hex}",
                "note": note,
                "acting": acting,
                "at": _now_iso(),
            }
            # credit the money balance — wallet module if present, else billing.json
            credited = False
            wm = self._wallet_mod()
            if wm is not None and amt > 0:
                try:
                    minor = int(round(amt * 100))
                    res = wm.topup(tenant_id, minor, acting or tenant_id, entry["idem_key"], "INR", True, note)
                    credited = bool(res.get("ok"))
                except Exception:  # noqa: BLE001
                    credited = False
            if not credited:
                try:
                    c = self._caller()
                    store = c._read_billing()
                    rec = store.get(tenant_id) or c._default_billing(c._tenant_by_id(tenant_id))
                    rec["balance"] = round(float(rec.get("balance", 0) or 0) + amt, 4)
                    store[tenant_id] = rec
                    c._write(c.BILLING_FILE, store)
                    credited = True
                except Exception:  # noqa: BLE001
                    credited = False
            entry["status"] = "captured" if credited else "failed"
            rows.insert(0, entry)
            del rows[10000:]
            self._write(self._topups_path(), rows)
        bal = self.wallet(tenant_id, True)
        return {"ok": credited, "credited_inr": amt, "credited_credits": entry["credits"],
                "id": entry["id"], **bal}

    def topups(self, tenant_id: str = "", limit: int = 100) -> list[dict]:
        rows = self._read(self._topups_path(), [])
        if not isinstance(rows, list):
            rows = []
        if tenant_id:
            rows = [r for r in rows if r.get("tenant_id") == tenant_id]
        return rows[: max(0, int(limit or 0)) or len(rows)]

    # ---- per-service metered usage rows (the metering seam writes here) ----
    def _usage_path(self):
        return self._var() / CREDITS_USAGE_FILE

    def _record_usage_row(self, tenant_id: str, service_key: str, qty: float,
                          cost_inr: float, idem: str, meta: dict) -> None:
        """Append one metered-usage row (idempotent on idem). Best-effort; never raises."""
        try:
            with _LOCK:
                rows = self._read(self._usage_path(), [])
                if not isinstance(rows, list):
                    rows = []
                if idem:
                    for r in rows:
                        if r.get("idem_key") == idem:
                            return  # already metered — idempotent
                rows.insert(0, {
                    "ts": _now_iso(), "tenant_id": tenant_id, "service_key": service_key,
                    "qty": round(float(qty or 0), 4), "cost_inr": round(float(cost_inr or 0), 4),
                    "idem_key": idem,
                    "meta": {k: v for k, v in (meta or {}).items() if k != "idem_key"},
                })
                del rows[20000:]
                self._write(self._usage_path(), rows)
        except Exception:  # noqa: BLE001
            pass

    # ---- unified ledger (top-ups + debits) ----
    def ledger(self, tenant_id: str, limit: int = 100) -> list[dict]:
        rate = pricing.credit_rate()
        out: list[dict] = []
        try:
            for t in self.topups(tenant_id, limit=limit):
                sign = 1 if float(t.get("amount_inr", 0) or 0) >= 0 else -1
                kind = "topup" if t.get("provider") not in ("adjust",) and sign > 0 else "adjust"
                if t.get("provider") == "grant":
                    kind = "grant"
                out.append({
                    "id": t.get("id"), "kind": kind, "service": t.get("provider", ""),
                    "description": t.get("note") or (f"Top-up via {t.get('provider')}" if kind == "topup"
                                                     else "Adjustment"),
                    "amount_inr": round(float(t.get("amount_inr", 0) or 0), 2),
                    "amount_credits": round(float(t.get("amount_inr", 0) or 0) / rate, 2),
                    "status": t.get("status", "captured"),
                    "ref": t.get("payment_id", ""), "at": t.get("at"),
                })
        except Exception:  # noqa: BLE001
            pass
        try:
            c = self._caller()
            for e in c._read_ledger(tenant_id)[:limit]:
                cost = float(e.get("cost", 0) or 0)
                out.append({
                    "id": e.get("id"), "kind": "debit", "service": "voice.call",
                    "description": f"Call {e.get('phone', '')} · {int(e.get('duration_s', 0) or 0)}s"
                                   + (f" · {e.get('outcome')}" if e.get("outcome") else ""),
                    "amount_inr": round(-cost, 2), "amount_credits": round(-cost / rate, 2),
                    "status": "settled", "ref": e.get("call_id", ""), "at": e.get("at"),
                })
        except Exception:  # noqa: BLE001
            pass
        out.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
        return out[:limit]

    # ---- per-service usage breakdown ----
    def usage(self, tenant_id: str, frm: str = "", to: str = "") -> dict:
        rate = pricing.credit_rate()
        c = None
        try:
            c = self._caller()
        except Exception:  # noqa: BLE001
            pass
        f_dt = _parse_ts(frm) if frm else _month_start()
        t_dt = _parse_ts(to) if to else None
        by_service: dict[str, dict] = {}
        daily: dict[str, float] = {}
        total_inr = 0.0
        rows = []
        try:
            rows = self._read(self._var() / "cost_ledger.json", [])
            if not isinstance(rows, list):
                rows = []
        except Exception:  # noqa: BLE001
            rows = []
        # map raw cost_ledger service_type -> a matrix service key for labelling
        svc_map = {"stt": "voice.call", "llm": "voice.call", "tts": "voice.call",
                   "telephony": "voice.telephony"}
        for r in rows:
            if tenant_id and r.get("tenant_id") and r.get("tenant_id") != tenant_id:
                continue
            ts = _parse_ts(r.get("ts"))
            if ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if f_dt and ts < (f_dt if f_dt.tzinfo else f_dt.replace(tzinfo=timezone.utc)):
                    continue
                if t_dt and ts > (t_dt if t_dt.tzinfo else t_dt.replace(tzinfo=timezone.utc)):
                    continue
            st = r.get("service_type", "")
            key = svc_map.get(st, f"voice.{st}" if st else "other")
            cost = float(r.get("cost", 0) or 0)
            b = by_service.setdefault(key, {"service": key, "qty": 0.0, "unit": r.get("unit", ""),
                                            "cost_inr": 0.0, "count": 0})
            b["qty"] += float(r.get("qty", 0) or 0)
            b["cost_inr"] += cost
            b["count"] += 1
            total_inr += cost
            if ts is not None:
                d = ts.date().isoformat()
                daily[d] = round(daily.get(d, 0.0) + cost, 4)
        # merge the metered-service usage (kb/crm/ads/creative/aim/sms via record_usage) so those
        # services appear in the per-service breakdown alongside voice (which comes from cost_ledger).
        try:
            urows = self._read(self._usage_path(), [])
            if isinstance(urows, list):
                for r in urows:
                    if tenant_id and r.get("tenant_id") and r.get("tenant_id") != tenant_id:
                        continue
                    ts = _parse_ts(r.get("ts"))
                    if ts is not None:
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if f_dt and ts < (f_dt if f_dt.tzinfo else f_dt.replace(tzinfo=timezone.utc)):
                            continue
                        if t_dt and ts > (t_dt if t_dt.tzinfo else t_dt.replace(tzinfo=timezone.utc)):
                            continue
                    key = r.get("service_key", "other") or "other"
                    cost = float(r.get("cost_inr", 0) or 0)
                    b = by_service.setdefault(key, {"service": key, "qty": 0.0, "unit": "",
                                                    "cost_inr": 0.0, "count": 0})
                    b["qty"] += float(r.get("qty", 0) or 0)
                    b["cost_inr"] += cost
                    b["count"] += 1
                    total_inr += cost
                    if ts is not None:
                        d = ts.date().isoformat()
                        daily[d] = round(daily.get(d, 0.0) + cost, 4)
        except Exception:  # noqa: BLE001
            pass

        # decorate with labels + credits
        pmatrix = {s["key"]: s for s in pricing.services(self._var())}
        services_out = []
        for key, b in by_service.items():
            meta = pmatrix.get(key, {})
            services_out.append({
                "service": key,
                "label": meta.get("label", key),
                "category": meta.get("category", "Other"),
                "unit": meta.get("unit", b.get("unit", "")),
                "qty": round(b["qty"], 2),
                "count": b["count"],
                "cost_inr": round(b["cost_inr"], 2),
                "cost_credits": round(b["cost_inr"] / rate, 2),
            })
        services_out.sort(key=lambda s: s["cost_inr"], reverse=True)
        series = [{"date": d, "cost_inr": daily[d], "cost_credits": round(daily[d] / rate, 2)}
                  for d in sorted(daily.keys())]
        return {
            "currency": "INR",
            "credit_rate_inr": rate,
            "from": (f_dt.isoformat() if f_dt else ""),
            "to": (t_dt.isoformat() if t_dt else ""),
            "total_inr": round(total_inr, 2),
            "total_credits": round(total_inr / rate, 2),
            "services": services_out,
            "series": series,
        }

    # ---- price + record (and optionally charge) one unit of usage — THE metering seam ----
    def record_usage(self, tenant_id: str, service_key: str, qty: float, *,
                     meta: dict | None = None) -> dict:
        """Price `qty` units of `service_key` via the costing matrix, RECORD it to the per-service
        usage store (so it shows in the Usage tab), and — only when CREDITS_METER_CHARGE is on —
        DEBIT the wallet. Voice + WhatsApp charge via their OWN paths (_charge_call / comm.metering)
        and must NOT be routed here (would double-charge). Best-effort + idempotent on
        meta['idem_key']; never raises into the calling service."""
        meta = meta or {}
        idem = str(meta.get("idem_key", "") or "")
        priced = pricing.price_for(self._var(), service_key, qty)
        inr = float(priced.get("total_inr", 0) or 0)
        # 1) ALWAYS track (Usage-tab visibility) — idempotent on idem
        self._record_usage_row(tenant_id, service_key, qty, inr, idem, meta)
        # 2) charge the wallet only when hard-charging is explicitly enabled (default OFF: safe to
        #    meter platform-wide before tenants are funded — see _meter_charge_enabled()).
        charged = False
        if inr > 0 and _meter_charge_enabled():
            try:
                self.topup(tenant_id, -inr, provider="adjust",
                           note=f"usage:{service_key} x{qty}",
                           idem_key=(f"meter:{idem}" if idem else ""))
                charged = True
            except Exception:  # noqa: BLE001
                pass
        priced["charged"] = charged
        return priced


def get_engine() -> BillingEngine:
    """Return the active engine. BILLING_ENGINE=flexprice selects the FlexPrice adapter (which
    falls back to Local for anything it cannot serve); anything else => LocalCreditEngine."""
    choice = (os.getenv("BILLING_ENGINE", "local") or "local").strip().lower()
    if choice in ("flexprice", "flex"):
        try:
            from .flexprice_engine import FlexpriceEngine
            return FlexpriceEngine()
        except Exception:  # noqa: BLE001 — never let a misconfigured FlexPrice break credits
            return LocalCreditEngine()
    return LocalCreditEngine()
