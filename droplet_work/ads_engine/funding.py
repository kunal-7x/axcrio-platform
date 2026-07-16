"""ads_engine.funding — budget FUNDING, vendor-own-card model (BLINDSPOTS B13/B14/B15).

DEFAULT model = **vendor_own_card**: the vendor attaches their OWN card to their OWN Meta/Google ad
account; we NEVER front spend. This module
  * reads the funded status of that ad account (Meta `account_status`/`funding_source`) — live-gated;
  * exposes a launch PRE-CHECK that returns `blocked_insufficient_funds` when the account has no
    usable payment method (B14 — so a launch can't silently publish into a dead account);
  * builds a deep-link to the provider "add payment method" surface (the vendor-own-card UX).

The alternative model = **managed** (a real gateway + paise ledger, already built in `budget.py`) is
delegated to when `ADS_FUNDING_MODEL=managed`. That model changes the "never front spend" stance and
is founder-sign-off gated.

EARNER-SAFE: nothing here spends. The real Meta/Google funding READ runs ONLY when `ADS_CONNECT_LIVE`
is ON (and creds exist); otherwise it degrades to a dormant, structural answer. NEVER raises; NEVER
returns a secret value.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from . import budget, config, vault_adapter

_log = logging.getLogger("ads_engine.funding")

_DEFAULT_MODEL = "vendor_own_card"


def model() -> str:
    m = (config.cfg("ADS_FUNDING_MODEL", _DEFAULT_MODEL) or _DEFAULT_MODEL).strip().lower()
    return m if m in ("vendor_own_card", "managed") else _DEFAULT_MODEL


def live_enabled() -> bool:
    """The real provider funding READ is armed. Default OFF (earner-safe, offline-testable)."""
    return config._flag("ADS_CONNECT_LIVE", "0")


def manage_link(tenant_id: str) -> str:
    """Deep-link to the vendor's OWN Meta ad-account billing/payment-method page (vendor-own-card).
    Empty when the ad_account_id isn't configured yet. Secret-free (only the public act id)."""
    try:
        creds = vault_adapter.get_connector_creds(tenant_id, "meta")
        blob = getattr(creds, "secret_json", None) or {}
        act = str((blob or {}).get("ad_account_id") or "")
        if not act:
            return ""
        act_num = act[4:] if act.startswith("act_") else act
        return ("https://business.facebook.com/ads/manager/account_settings/"
                f"account_billing/?act={act_num}")
    except Exception:  # noqa: BLE001
        return ""


async def funding_status(tenant_id: str) -> dict:
    """SECRET-FREE funded-status read for the Connections UI.

    Returns: { ok, model, funded: bool|None, reason, account_status, funding_source, manage_url,
               balance_minor?, currency? }
      reason ∈ ok | not_configured | dry_run | registry_disabled | read_failed | <managed reasons>
    `funded=None` means "unknown" (dry-run / not live) — the UI shows 'connect a card', not a false
    green. NEVER raises."""
    m = model()
    if m == "managed":
        # delegate to the gateway/ledger model (budget.py owns it).
        try:
            bal = budget.get_balance(tenant_id)
            funded = int(bal.get("balance_minor", 0) or 0) > 0
            return {"ok": True, "model": "managed", "funded": funded, "reason": "ok",
                    "account_status": None, "funding_source": None, "manage_url": "",
                    "balance_minor": int(bal.get("balance_minor", 0) or 0),
                    "currency": bal.get("currency", "INR")}
        except Exception:  # noqa: BLE001
            return {"ok": False, "model": "managed", "funded": False, "reason": "read_failed",
                    "account_status": None, "funding_source": None, "manage_url": ""}

    # vendor_own_card --------------------------------------------------------
    creds = vault_adapter.get_connector_creds(tenant_id, "meta")
    base = {"ok": True, "model": "vendor_own_card", "manage_url": manage_link(tenant_id),
            "account_status": None, "funding_source": None}
    if not getattr(creds, "ok", False):
        return {**base, "ok": False, "funded": None,
                "reason": getattr(creds, "reason", "not_configured")}
    if not live_enabled():
        # cannot verify funds offline -> unknown (never a false green); the dry-run gate stops spend.
        return {**base, "funded": None, "reason": "dry_run"}
    try:
        from .connectors.meta import MetaConnector
        conn = MetaConnector(creds)
        res = await conn.get_account_funding()
        if not getattr(res, "ok", False):
            return {**base, "ok": False, "funded": False, "reason": "read_failed"}
        data = getattr(res, "data", None) or {}
        acct_status = data.get("account_status")
        funding_source = data.get("funding_source") or data.get("funding_source_details")
        # Meta: account_status==1 == ACTIVE; a funding_source present == a payment method attached.
        funded = (str(acct_status) == "1") and bool(funding_source)
        return {**base, "funded": bool(funded), "reason": "ok",
                "account_status": acct_status, "funding_source": bool(funding_source)}
    except Exception as exc:  # noqa: BLE001
        _log.warning("ads_engine.funding.funding_status failed: %r", type(exc).__name__)
        return {**base, "ok": False, "funded": False, "reason": "read_failed"}


async def launch_precheck(tenant_id: str, *, required_minor: int = 0) -> dict:
    """The launch funding gate (B14). Returns { ok, blocked, status, reason, model }.

      status ∈ "ok" | "blocked_insufficient_funds"   (matches campaign.ST_BLOCKED_FUNDS)
    Policy:
      * managed model: block when balance < required_minor (budget.is_funded is fail-closed).
      * vendor_own_card + LIVE: block when the read says the account is not ACTIVE/funded, OR when
        no ad account is configured (can't publish into nothing) — fail-closed for a REAL launch.
      * vendor_own_card + dry-run (default): NOT blocked here (the dry_run gate already prevents
        spend); funded is 'unknown'. This keeps the offline pipeline testable while never letting a
        LIVE launch slip into an unfunded account.
    NEVER raises."""
    m = model()
    if m == "managed":
        try:
            ok = budget.is_funded(tenant_id, int(required_minor or 0))
        except Exception:  # noqa: BLE001
            ok = False
        return {"ok": True, "model": "managed", "blocked": (not ok),
                "status": "ok" if ok else "blocked_insufficient_funds",
                "reason": "ok" if ok else "insufficient_balance"}

    # vendor_own_card
    if not live_enabled():
        return {"ok": True, "model": "vendor_own_card", "blocked": False,
                "status": "ok", "reason": "dry_run"}
    st = await funding_status(tenant_id)
    funded = st.get("funded")
    if funded is True:
        return {"ok": True, "model": "vendor_own_card", "blocked": False,
                "status": "ok", "reason": "ok"}
    return {"ok": True, "model": "vendor_own_card", "blocked": True,
            "status": "blocked_insufficient_funds",
            "reason": st.get("reason", "not_funded")}
