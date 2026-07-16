"""ads_engine.budget — ad-BUDGET FUNDING scaffold (Razorpay-first, India-appropriate; Stripe-ready).

BLINDSPOTS B13/B14 — the "+ budget" half of the vision: a tenant funds their ad budget through a
real payment gateway, the paise land in a tenant-scoped ledger, and that funded balance gates
campaign launch (an un-funded account can never silently publish into a dead ad set).

DESIGN (earner-safe, dormant-until-creds — mirrors droplet_work/payments dormancy):
  * The gateway CREDENTIALS are read ONLY through the vault seam (vault_adapter), NEVER os.environ:
    a vendor adds a Razorpay/Stripe key as a provider def with capability `payment_gateway` and
    named_provider `razorpay`/`stripe` (BLINDSPOTS B1 added the capability). With NO key stored,
    every call degrades to a calm `not_configured` shape — never an exception into the live spine.
  * Money is ALWAYS minor units (paise), suffix `*_minor`, matching `_lib.ts` + the paise ledger.
  * The balance is the CAS-guarded `budget_account` row; every credit/debit is also an immutable
    `budget_ledger` append (store.py). NO money is fronted by the platform — a balance only rises
    when a REAL gateway payment is cryptographically verified (Razorpay HMAC / Stripe webhook sig).
  * The actual order-creation HTTP call needs the founder's live keys + httpx; absent either, the
    intent is persisted `awaiting_gateway` with needs_setup=True (the founder completes external
    setup). The VERIFY+CREDIT path is pure crypto and fully offline-testable.

NEVER logs a key/secret/signature. NEVER raises into the caller spine (degrade -> not_configured).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid

from . import config, store, vault_adapter

_log = logging.getLogger("ads_engine.budget")

# Vault capability + named_provider used to resolve the stored gateway key (BLINDSPOTS B1).
CAP_PAYMENT = "payment_gateway"
PROVIDER_RAZORPAY = "razorpay"   # India default: UPI + cards + netbanking, paise-native.
PROVIDER_STRIPE = "stripe"
_SUPPORTED = (PROVIDER_RAZORPAY, PROVIDER_STRIPE)


def default_provider() -> str:
    """The platform's preferred gateway. India-appropriate => Razorpay (env may override to stripe)."""
    p = (config.cfg("ADS_BUDGET_PROVIDER", PROVIDER_RAZORPAY) or PROVIDER_RAZORPAY).strip().lower()
    return p if p in _SUPPORTED else PROVIDER_RAZORPAY


def _currency() -> str:
    return (config.caps().get("currency") or "INR").upper()


# ---------------------------------------------------------------------------
# Gateway credential resolution — vault ONLY (degrade-never-raise).
# ---------------------------------------------------------------------------
def _gateway_def_id(tenant_id: str, provider: str):
    try:
        return vault_adapter.resolve_provider_def_id(tenant_id, named_provider=provider)
    except Exception:  # noqa: BLE001
        return None


def _gateway_creds(tenant_id: str, provider: str):
    """The decrypted gateway credential blob (dict) or None. NEVER logs the blob."""
    pdid = _gateway_def_id(tenant_id, provider)
    if not pdid:
        return None
    try:
        return vault_adapter.get_secret_json(tenant_id, pdid)
    except Exception:  # noqa: BLE001
        return None


def configured_provider(tenant_id: str) -> str | None:
    """Which gateway this tenant has a key stored for (preferring the platform default). None when
    no gateway key exists — the dormant state the UI renders as 'gateway not connected'."""
    order = [default_provider()] + [p for p in _SUPPORTED if p != default_provider()]
    for p in order:
        if _gateway_def_id(tenant_id, p):
            return p
    return None


def gateway_status(tenant_id: str) -> dict:
    """Non-secret funding status for the Connections / Budget surface. ID/secret-free.

    { provider, configured, default_provider, currency } — never a key/secret/order id.
    """
    prov = configured_provider(tenant_id)
    return {
        "provider": prov or "",
        "configured": bool(prov),
        "default_provider": default_provider(),
        "currency": _currency(),
    }


# ---------------------------------------------------------------------------
# Balance + funding check (B14).
# ---------------------------------------------------------------------------
def get_balance(tenant_id: str) -> dict:
    """The tenant's funded ad-budget balance (paise) + gateway status. Default-safe (never raises)."""
    try:
        acct = store.get_budget_account(tenant_id)
    except Exception:  # noqa: BLE001
        acct = {"balance_minor": 0, "currency": _currency(),
                "funded_total_minor": 0, "spent_total_minor": 0}
    gw = gateway_status(tenant_id)
    return {
        "balance_minor": int(acct.get("balance_minor", 0) or 0),
        "currency": acct.get("currency", _currency()),
        "funded_total_minor": int(acct.get("funded_total_minor", 0) or 0),
        "spent_total_minor": int(acct.get("spent_total_minor", 0) or 0),
        "gateway": gw,
    }


def is_funded(tenant_id: str, required_minor: int) -> bool:
    """B14 funding pre-check: does the tenant hold >= `required_minor` paise of funded budget?

    Default-safe False (fail-CLOSED: a balance we can't read counts as un-funded, so a launch is
    blocked rather than silently publishing into a dead account)."""
    try:
        need = max(0, int(required_minor or 0))
        if need == 0:
            return True
        return int(store.get_budget_account(tenant_id).get("balance_minor", 0) or 0) >= need
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# FUNDING INTENT — create a gateway order (or a dormant scaffold intent).
# ---------------------------------------------------------------------------
def create_funding_intent(tenant_id: str, amount_minor: int, *, currency: str = "",
                          idem_key: str = "", description: str = "") -> dict:
    """Create (or resolve, idempotently) a funding intent for `amount_minor` paise.

    Idempotency: an `idem_key` that already has an intent returns that SAME intent (no double order).
    Live: with a stored gateway key + httpx, this creates a real Razorpay Order / Stripe PaymentIntent
    and returns the order id + the PUBLIC key the checkout needs. Dormant: with no key (or no httpx),
    the intent is persisted `awaiting_gateway` with needs_setup=True — the founder adds the key, then
    the SAME intent can be re-created live. NEVER raises; NEVER returns a secret.
    """
    amt = int(amount_minor or 0)
    cur = (currency or _currency()).upper()
    if amt <= 0:
        return {"ok": False, "status": "invalid_request", "reason": "amount_minor must be > 0"}

    # Idempotency: reuse an existing intent for this idem_key.
    if idem_key:
        try:
            existing = store.find_budget_intent_by_idem(tenant_id, idem_key)
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            return _intent_public(existing, exists=True)

    provider = configured_provider(tenant_id)
    intent_id = "bi_" + uuid.uuid4().hex[:20]
    now = int(time.time())
    base = {
        "intent_id": intent_id, "provider": provider or default_provider(),
        "amount_minor": amt, "currency": cur, "idem_key": str(idem_key or "")[:128],
        "description": str(description or "")[:200], "created_ts": now, "updated_ts": now,
    }

    if not provider:
        # Dormant: no gateway key stored — persist the intent so the founder can complete setup.
        base.update({"status": "not_configured", "needs_setup": True, "order_id": ""})
        _persist_intent(tenant_id, base)
        return _intent_public(base, reason="no gateway key stored (add a Razorpay/Stripe key)")

    creds = _gateway_creds(tenant_id, provider)
    order = _create_gateway_order(provider, creds, amt, cur, intent_id)
    if not order.get("ok"):
        base.update({"status": "awaiting_gateway", "needs_setup": True, "order_id": "",
                     "reason": order.get("reason", "")})
        _persist_intent(tenant_id, base)
        return _intent_public(base, reason=order.get("reason", "gateway order not created"))

    base.update({"status": "created", "order_id": order.get("order_id", ""),
                 "public_key": order.get("public_key", ""), "needs_setup": False})
    _persist_intent(tenant_id, base)
    return _intent_public(base)


def _persist_intent(tenant_id: str, intent: dict) -> None:
    try:
        store.put_budget_intent(tenant_id, intent["intent_id"], intent)
    except Exception:  # noqa: BLE001 — persistence failure must not crash the request
        _log.warning("ads_engine.budget: intent persist failed")


def _intent_public(intent: dict, *, exists: bool = False, reason: str = "") -> dict:
    """The non-secret intent view returned to the UI (order id + public key are checkout-safe)."""
    out = {
        "ok": intent.get("status") in ("created", "paid"),
        "status": intent.get("status", "not_configured"),
        "intent_id": intent.get("intent_id", ""),
        "provider": intent.get("provider", ""),
        "amount_minor": int(intent.get("amount_minor", 0) or 0),
        "currency": intent.get("currency", "INR"),
        "order_id": intent.get("order_id", ""),
        "public_key": intent.get("public_key", ""),
        "needs_setup": bool(intent.get("needs_setup", False)),
    }
    if exists:
        out["exists"] = True
    if reason or intent.get("reason"):
        out["reason"] = reason or intent.get("reason")
    return out


def _create_gateway_order(provider: str, creds, amount_minor: int, currency: str,
                          receipt: str) -> dict:
    """Create a real gateway order via httpx (live), else a degrade reason. NEVER raises.

    Razorpay: POST https://api.razorpay.com/v1/orders  (HTTP Basic key_id:key_secret), amount in
    paise. Stripe: POST https://api.stripe.com/v1/payment_intents, amount in the smallest unit.
    Returns {ok, order_id, public_key} or {ok:False, reason}. Requires the founder's live keys +
    httpx on the box; offline/keyless => ok:False with a setup reason (the dormant scaffold path).
    """
    if not isinstance(creds, dict):
        return {"ok": False, "reason": "no gateway credential"}
    try:
        import httpx  # type: ignore
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": "httpx unavailable on box"}
    try:
        if provider == PROVIDER_RAZORPAY:
            key_id = str(creds.get("key_id") or "")
            key_secret = str(creds.get("key_secret") or "")
            if not key_id or not key_secret:
                return {"ok": False, "reason": "razorpay key_id/key_secret missing"}
            resp = httpx.post(
                "https://api.razorpay.com/v1/orders",
                auth=(key_id, key_secret),
                json={"amount": int(amount_minor), "currency": currency,
                      "receipt": receipt, "payment_capture": 1},
                timeout=15.0,
            )
            if resp.status_code >= 300:
                return {"ok": False, "reason": f"razorpay {resp.status_code}"}
            data = resp.json()
            return {"ok": True, "order_id": str(data.get("id", "")), "public_key": key_id}
        if provider == PROVIDER_STRIPE:
            secret_key = str(creds.get("secret_key") or "")
            pub_key = str(creds.get("publishable_key") or "")
            if not secret_key:
                return {"ok": False, "reason": "stripe secret_key missing"}
            resp = httpx.post(
                "https://api.stripe.com/v1/payment_intents",
                headers={"Authorization": f"Bearer {secret_key}"},
                data={"amount": int(amount_minor), "currency": currency.lower(),
                      "metadata[receipt]": receipt},
                timeout=15.0,
            )
            if resp.status_code >= 300:
                return {"ok": False, "reason": f"stripe {resp.status_code}"}
            data = resp.json()
            return {"ok": True, "order_id": str(data.get("id", "")), "public_key": pub_key}
    except Exception as exc:  # noqa: BLE001 — network/JSON error => degrade (never raise)
        _log.warning("ads_engine.budget: gateway order failed: %r", type(exc).__name__)
        return {"ok": False, "reason": "gateway request failed"}
    return {"ok": False, "reason": f"unsupported provider {provider}"}


# ---------------------------------------------------------------------------
# VERIFY + CREDIT — the crypto-verified money-in path (fully offline-testable).
# ---------------------------------------------------------------------------
def _razorpay_signature(order_id: str, payment_id: str, key_secret: str) -> str:
    """Razorpay client checkout signature = HMAC-SHA256(key_secret, "order_id|payment_id")."""
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def confirm_funding(tenant_id: str, intent_id: str, *, payment_id: str = "",
                    signature: str = "") -> dict:
    """Verify a completed gateway payment for an intent and CREDIT the budget. Idempotent.

    Razorpay: verifies HMAC-SHA256(key_secret, order_id|payment_id) == signature, then credits the
    intent amount to the paise balance + appends a ledger row. A re-confirm of an already-paid intent
    (same payment_id) is a NO-OP success (no double credit). Fail-CLOSED: a bad/absent signature, no
    creds, or an unknown intent never credits. NEVER raises; NEVER logs the secret/signature.
    """
    intent = None
    try:
        intent = store.get_budget_intent(tenant_id, intent_id)
    except Exception:  # noqa: BLE001
        intent = None
    if not intent:
        return {"ok": False, "status": "not_found", "reason": "unknown funding intent"}

    # Idempotency: already paid by this payment_id => no double credit.
    if intent.get("status") == "paid":
        if not payment_id or str(intent.get("payment_id", "")) == str(payment_id):
            return {"ok": True, "status": "paid", "intent_id": intent_id, "already": True,
                    "balance_minor": int(get_balance(tenant_id)["balance_minor"])}

    provider = str(intent.get("provider") or default_provider())
    creds = _gateway_creds(tenant_id, provider)
    verified = _verify_payment(provider, creds, intent, payment_id, signature)
    if not verified:
        return {"ok": False, "status": "verification_failed",
                "reason": "payment signature did not verify (fail-closed; no credit)"}

    amt = int(intent.get("amount_minor", 0) or 0)
    cur = str(intent.get("currency") or _currency())
    try:
        new_acct = store.credit_budget(
            tenant_id, amt, currency=cur,
            ref={"intent_id": intent_id, "payment_id": payment_id,
                 "order_id": intent.get("order_id", ""), "provider": provider})
    except Exception:  # noqa: BLE001 — incl. CAS-retry exhaustion: do NOT mark paid (retryable).
        # Fail-CLOSED: the credit did not commit, so the intent stays unpaid and the caller can
        # re-confirm (idempotent — a later success credits exactly once). Never mark paid here.
        return {"ok": False, "status": "credit_failed",
                "reason": "balance write contended; retry confirm"}

    intent = dict(intent)
    intent.update({"status": "paid", "payment_id": str(payment_id or "")[:128],
                   "paid_ts": int(time.time()), "updated_ts": int(time.time())})
    _persist_intent(tenant_id, intent)
    return {"ok": True, "status": "paid", "intent_id": intent_id,
            "credited_minor": amt, "balance_minor": int(new_acct.get("balance_minor", 0) or 0)}


def _verify_payment(provider: str, creds, intent: dict, payment_id: str, signature: str) -> bool:
    """True iff the gateway signature verifies. Fail-CLOSED on any missing piece. constant-time cmp."""
    if not isinstance(creds, dict) or not signature:
        return False
    try:
        if provider == PROVIDER_RAZORPAY:
            key_secret = str(creds.get("key_secret") or "")
            order_id = str(intent.get("order_id") or "")
            if not key_secret or not order_id or not payment_id:
                return False
            expected = _razorpay_signature(order_id, payment_id, key_secret)
            return hmac.compare_digest(expected, str(signature))
        if provider == PROVIDER_STRIPE:
            # Stripe confirmation is normally a webhook (verify_webhook); for the synchronous confirm
            # path we accept a PaymentIntent client-secret-derived signature only when the webhook
            # secret matches the payment_id binding. Conservatively fail-closed here.
            return False
    except Exception:  # noqa: BLE001
        return False
    return False


def verify_webhook(tenant_id: str, raw_body: bytes, signature_header: str,
                   *, provider: str = "") -> dict:
    """Verify a gateway WEBHOOK (server->server money confirmation) and credit. Idempotent.

    Razorpay: signature = HMAC-SHA256(webhook_secret, raw_body) hex, compared to X-Razorpay-Signature.
    On a verified `payment.captured`/`order.paid` event we resolve the intent by order id and credit
    once (ledger-idempotent by payment_id). Fail-CLOSED on a bad signature / missing webhook_secret.
    """
    prov = provider or configured_provider(tenant_id) or default_provider()
    creds = _gateway_creds(tenant_id, prov)
    if not isinstance(creds, dict):
        return {"ok": False, "status": "not_configured"}
    secret = str(creds.get("webhook_secret") or "")
    if not secret or not signature_header:
        return {"ok": False, "status": "verification_failed", "reason": "no webhook secret/signature"}
    try:
        expected = hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature_header)):
            return {"ok": False, "status": "verification_failed"}
        payload = json.loads((raw_body or b"{}").decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {"ok": False, "status": "verification_failed"}

    # Resolve the intent from the event payload (Razorpay nests the entity under payload.*.entity).
    order_id, payment_id = _extract_razorpay_ids(payload)
    if not order_id:
        return {"ok": False, "status": "ignored", "reason": "no order id in event"}
    intent = None
    try:
        intent = store.find_budget_intent_by_order(tenant_id, order_id)
    except Exception:  # noqa: BLE001
        intent = None
    if not intent:
        return {"ok": False, "status": "not_found", "reason": "no intent for order"}
    # Mark verified-by-webhook then credit through the standard idempotent path.
    return confirm_funding(tenant_id, intent.get("intent_id", ""),
                           payment_id=payment_id, signature=_razorpay_signature(
                               order_id, payment_id, str(creds.get("key_secret") or "")))


def _extract_razorpay_ids(payload: dict) -> tuple[str, str]:
    """Pull (order_id, payment_id) out of a Razorpay webhook event payload. Default-safe ('','')."""
    try:
        pl = (payload or {}).get("payload", {}) or {}
        pay = (pl.get("payment", {}) or {}).get("entity", {}) or {}
        order = (pl.get("order", {}) or {}).get("entity", {}) or {}
        order_id = str(pay.get("order_id") or order.get("id") or "")
        payment_id = str(pay.get("id") or "")
        return order_id, payment_id
    except Exception:  # noqa: BLE001
        return "", ""


# ---------------------------------------------------------------------------
# READ surfaces for the UI.
# ---------------------------------------------------------------------------
def list_intents(tenant_id: str, limit: int = 50) -> list:
    """Funding intents (non-secret) newest-first, for the Budget surface."""
    try:
        rows = store.list_budget_intents(tenant_id)
    except Exception:  # noqa: BLE001
        rows = []
    rows = sorted(rows, key=lambda r: int(r.get("created_ts", 0) or 0), reverse=True)
    try:
        n = max(1, min(int(limit), 200))
    except Exception:  # noqa: BLE001
        n = 50
    return [_intent_public(r) for r in rows[:n]]


def ledger(tenant_id: str, limit: int = 50) -> list:
    """The immutable money-movement ledger (newest-first) for the Budget surface."""
    try:
        return store.get_budget_ledger(tenant_id, limit)
    except Exception:  # noqa: BLE001
        return []


def budget_health(tenant_id: str) -> dict:
    """The /ads/budget/health payload: balance + gateway status + dry_run flag. Default-safe."""
    bal = get_balance(tenant_id)
    return {
        "ok": True,
        "module": "ads_budget",
        "dry_run": config.dry_run(),
        **bal,
    }
