"""credits/gateways.py — real-money top-up rails: Razorpay + Stripe.

DORMANT-UNTIL-KEYS: with no gateway keys set, every entry point returns
{"status": "not_configured"} so the UI shows "ask your admin to enable a gateway" and the
super-admin can still grant credits manually. Add keys (env) and it goes live with NO code change.

Stdlib only (urllib + hmac/hashlib) — zero new dependencies. Both gateways operate in INR minor
units (paise). Webhooks are HMAC-signature verified before a single credit is granted; the wallet
top-up itself is idempotent on the gateway payment id (see engine.topup), so a webhook retry can
never double-credit.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or "").strip()


def razorpay_configured() -> bool:
    return bool(_env("RAZORPAY_KEY_ID") and _env("RAZORPAY_KEY_SECRET"))


def stripe_configured() -> bool:
    return bool(_env("STRIPE_SECRET_KEY"))


def configured_providers() -> dict:
    return {
        "razorpay": {"configured": razorpay_configured(), "currency": "INR",
                     "display_name": "Razorpay"},
        "stripe": {"configured": stripe_configured(), "currency": "INR",
                   "display_name": "Stripe"},
    }


def default_provider() -> str:
    pref = _env("CREDITS_DEFAULT_GATEWAY").lower()
    if pref in ("razorpay", "stripe"):
        return pref
    if razorpay_configured():
        return "razorpay"
    if stripe_configured():
        return "stripe"
    return ""


def _success_url() -> str:
    return _env("CREDITS_SUCCESS_URL") or _env("PANEL_BASE_URL", "https://haptica.famit.in") + "/credits?topup=success"


def _cancel_url() -> str:
    return _env("CREDITS_CANCEL_URL") or _env("PANEL_BASE_URL", "https://haptica.famit.in") + "/credits?topup=cancel&tab=buy"


def _http(url: str, *, method: str = "POST", headers: dict | None = None,
          data: bytes | None = None, timeout: float = 20.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body)
            except Exception:  # noqa: BLE001
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as e:  # noqa: PERF203
        try:
            body = e.read().decode("utf-8", "replace")
            return e.code, json.loads(body)
        except Exception:  # noqa: BLE001
            return e.code, {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


# ── Razorpay ───────────────────────────────────────────────────────────────────────────────
def _razorpay_order(tenant_id: str, amount_inr: float, credits: float, note: str) -> dict:
    key_id, secret = _env("RAZORPAY_KEY_ID"), _env("RAZORPAY_KEY_SECRET")
    minor = int(round(float(amount_inr) * 100))
    auth = base64.b64encode(f"{key_id}:{secret}".encode()).decode()
    payload = json.dumps({
        "amount": minor, "currency": "INR",
        "receipt": f"credits_{tenant_id}_{int(time.time())}",
        "notes": {"tenant_id": tenant_id, "credits": str(credits), "kind": "credit_topup"},
    }).encode()
    status, body = _http("https://api.razorpay.com/v1/orders", method="POST",
                         headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                         data=payload)
    if status in (200, 201) and body.get("id"):
        return {
            "status": "created", "provider": "razorpay", "order_id": body["id"],
            "key_id": key_id, "amount_inr": round(amount_inr, 2), "amount_minor": minor,
            "credits": credits, "currency": "INR",
        }
    return {"status": "error", "provider": "razorpay", "message": body.get("error", body)}


# ── Stripe ─────────────────────────────────────────────────────────────────────────────────
def _stripe_session(tenant_id: str, amount_inr: float, credits: float, note: str,
                    email: str = "") -> dict:
    sk = _env("STRIPE_SECRET_KEY")
    minor = int(round(float(amount_inr) * 100))
    form = [
        ("mode", "payment"),
        ("success_url", _success_url()),
        ("cancel_url", _cancel_url()),
        ("client_reference_id", tenant_id),
        ("metadata[tenant_id]", tenant_id),
        ("metadata[credits]", str(credits)),
        ("metadata[kind]", "credit_topup"),
        ("line_items[0][quantity]", "1"),
        ("line_items[0][price_data][currency]", "inr"),
        ("line_items[0][price_data][unit_amount]", str(minor)),
        ("line_items[0][price_data][product_data][name]", f"{credits:g} Haptica credits"),
    ]
    if email:
        form.append(("customer_email", email))
    data = urllib.parse.urlencode(form).encode()
    status, body = _http("https://api.stripe.com/v1/checkout/sessions", method="POST",
                         headers={"Authorization": f"Bearer {sk}",
                                  "Content-Type": "application/x-www-form-urlencoded"},
                         data=data)
    if status in (200, 201) and body.get("url"):
        return {
            "status": "created", "provider": "stripe", "session_id": body.get("id"),
            "checkout_url": body["url"], "amount_inr": round(amount_inr, 2),
            "amount_minor": minor, "credits": credits, "currency": "INR",
        }
    return {"status": "error", "provider": "stripe", "message": body.get("error", body)}


def create_checkout(provider: str, tenant_id: str, amount_inr: float, credits: float,
                    note: str = "", email: str = "") -> dict:
    """Create a gateway order/session for buying credits. Returns a dict the panel hands to the
    Razorpay widget (order_id+key_id) or redirects to (Stripe checkout_url)."""
    provider = (provider or default_provider() or "").lower()
    if amount_inr is None or float(amount_inr) <= 0:
        return {"status": "error", "message": "amount must be positive"}
    if provider == "razorpay":
        if not razorpay_configured():
            return {"status": "not_configured", "provider": "razorpay"}
        return _razorpay_order(tenant_id, amount_inr, credits, note)
    if provider == "stripe":
        if not stripe_configured():
            return {"status": "not_configured", "provider": "stripe"}
        return _stripe_session(tenant_id, amount_inr, credits, note, email)
    return {"status": "not_configured", "provider": provider or "none"}


# ── webhook verification + extraction ────────────────────────────────────────────────────────
def _verify_razorpay(raw_body: bytes, signature: str) -> bool:
    secret = _env("RAZORPAY_WEBHOOK_SECRET")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_stripe(raw_body: bytes, sig_header: str) -> bool:
    secret = _env("STRIPE_WEBHOOK_SECRET")
    if not secret or not sig_header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        ts, v1 = parts.get("t"), parts.get("v1")
        if not ts or not v1:
            return False
        signed = f"{ts}.".encode() + raw_body
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v1)
    except Exception:  # noqa: BLE001
        return False


def verify_and_extract(provider: str, raw_body: bytes, headers: dict) -> dict:
    """Verify a webhook signature and pull out the credit instruction.

    Returns {ok, captured, tenant_id, amount_inr, payment_id, event} — ok=False on a bad
    signature (the route 400s) so an unsigned/forged request can never grant credits."""
    provider = (provider or "").lower()
    h = {k.lower(): v for k, v in (headers or {}).items()}
    try:
        if provider == "razorpay":
            if not _verify_razorpay(raw_body, h.get("x-razorpay-signature", "")):
                return {"ok": False, "reason": "bad signature"}
            ev = json.loads(raw_body.decode("utf-8", "replace"))
            event = ev.get("event", "")
            ent = (((ev.get("payload") or {}).get("payment") or {}).get("entity")) or {}
            captured = event in ("payment.captured", "order.paid")
            notes = ent.get("notes") or {}
            return {"ok": True, "captured": captured, "event": event,
                    "tenant_id": notes.get("tenant_id", ""),
                    "amount_inr": round(int(ent.get("amount", 0)) / 100.0, 2),
                    "payment_id": ent.get("id", "")}
        if provider == "stripe":
            if not _verify_stripe(raw_body, h.get("stripe-signature", "")):
                return {"ok": False, "reason": "bad signature"}
            ev = json.loads(raw_body.decode("utf-8", "replace"))
            event = ev.get("type", "")
            obj = ((ev.get("data") or {}).get("object")) or {}
            captured = event == "checkout.session.completed" and obj.get("payment_status") == "paid"
            md = obj.get("metadata") or {}
            return {"ok": True, "captured": captured, "event": event,
                    "tenant_id": md.get("tenant_id", "") or obj.get("client_reference_id", ""),
                    "amount_inr": round(int(obj.get("amount_total", 0) or 0) / 100.0, 2),
                    "payment_id": obj.get("payment_intent", "") or obj.get("id", "")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"parse error: {e}"}
    return {"ok": False, "reason": "unknown provider"}
