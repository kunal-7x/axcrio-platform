"""credits/flexprice_engine.py — the FlexPrice REST adapter.

Selected with BILLING_ENGINE=flexprice once a FlexPrice instance is reachable
(FLEXPRICE_API_URL + FLEXPRICE_API_KEY). It pushes usage EVENTS + wallet TOP-UPS to FlexPrice and
reads balances back; for anything FlexPrice cannot (yet) serve — or any transport error — it
DELEGATES to LocalCreditEngine. So turning it on is always safe: worst case you keep the local
behaviour you have today, best case FlexPrice becomes the system of record with zero product churn.

FlexPrice maps to our concepts 1:1:
  Haptica tenant      -> FlexPrice customer (external_id = tenant_id)
  Haptica credit       -> FlexPrice wallet credit balance (prepaid)
  Haptica service usage -> FlexPrice event (event_name = service_key, properties carry qty)
  Haptica pricing matrix-> FlexPrice meters + prices (mirrored from credits/pricing.py)

Self-host: see selfhost/flexprice/docker-compose.yml (postgres + clickhouse + kafka + temporal +
flexprice api). Stdlib HTTP only.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .engine import LocalCreditEngine


def _env(k: str, d: str = "") -> str:
    return (os.getenv(k, d) or "").strip()


class FlexpriceEngine(LocalCreditEngine):
    """REST adapter; everything not overridden here transparently uses the local wallet."""

    name = "flexprice"

    def __init__(self) -> None:
        self.base = _env("FLEXPRICE_API_URL").rstrip("/")
        self.key = _env("FLEXPRICE_API_KEY")

    # ---- transport ----
    def _live(self) -> bool:
        return bool(self.base and self.key)

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 15.0):
        if not self._live():
            return None
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", "x-api-key": self.key,
                     "Authorization": f"Bearer {self.key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw else {}
        except Exception:  # noqa: BLE001 — any failure => caller falls back to local
            return None

    # ---- wallet: read from FlexPrice, fall back to local on any miss ----
    def wallet(self, tenant_id: str, is_admin: bool = False) -> dict:
        base = super().wallet(tenant_id, is_admin)  # always have a valid local shape
        res = self._call("GET", f"/v1/customers/{tenant_id}/wallets")
        try:
            if res:
                wallets = res if isinstance(res, list) else res.get("wallets") or res.get("data") or []
                if wallets:
                    bal = wallets[0]
                    avail = float(bal.get("balance", bal.get("credit_balance", base["balance_credits"])))
                    rate = base["credit_rate_inr"]
                    base.update({
                        "balance_credits": round(avail, 2),
                        "balance_inr": round(avail * rate, 2),
                        "engine": self.name,
                        "wallet_available": True,
                    })
        except Exception:  # noqa: BLE001
            pass
        base["engine"] = self.name
        return base

    # ---- top-up: credit FlexPrice wallet AND keep the local mirror in lockstep ----
    def topup(self, tenant_id: str, amount_inr: float, *, idem_key: str = "",
              provider: str = "manual", payment_id: str = "", note: str = "",
              acting: str = "") -> dict:
        local = super().topup(tenant_id, amount_inr, idem_key=idem_key, provider=provider,
                              payment_id=payment_id, note=note, acting=acting)
        try:
            from . import pricing
            credits = round(float(amount_inr) / pricing.credit_rate(), 4)
            self._call("POST", f"/v1/customers/{tenant_id}/wallets/top-up",
                       {"credits": credits, "idempotency_key": idem_key or payment_id,
                        "description": note or f"top-up via {provider}"})
        except Exception:  # noqa: BLE001
            pass
        local["engine"] = self.name
        return local

    # ---- usage: emit a FlexPrice event (metering) + price/charge locally ----
    def record_usage(self, tenant_id: str, service_key: str, qty: float, *,
                     meta: dict | None = None) -> dict:
        try:
            self._call("POST", "/v1/events", {
                "event_name": service_key,
                "external_customer_id": tenant_id,
                "properties": {"qty": qty, **(meta or {})},
            })
        except Exception:  # noqa: BLE001
            pass
        return super().record_usage(tenant_id, service_key, qty, meta=meta)
