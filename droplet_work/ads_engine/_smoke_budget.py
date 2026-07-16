"""Offline smoke for ads_engine.budget — NO app boot, NO .env, NO network, NO caller.

Wires the store onto a tempdir and monkeypatches the vault seam (resolve_provider_def_id +
get_secret_json) to return a Razorpay credential blob, so the verify+credit path runs with real
crypto and zero network. Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_budget as s; s.main()"

Asserts (BLINDSPOTS B13/B14):
  * dormant-until-creds: no gateway key -> gateway_status not configured; fund intent needs_setup
  * a created intent + a VALID Razorpay HMAC signature credits the paise balance (real crypto)
  * a BAD signature is fail-CLOSED (no credit)
  * confirm is idempotent (re-confirm same payment_id -> no double credit)
  * is_funded reflects the balance; debit draws down and is floored at zero (never negative)
  * the ledger is append-only (one row per movement) + balance reconstructs
  * funding-intent idempotency by idem_key (same key -> same intent, no second order)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
from pathlib import Path


def _wire_store(tmp: Path):
    import ads_engine as pkg

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _awj(p, d),
             _atomic_write_json=_awj, var_dir=tmp)


_KEY_SECRET = "rzp_test_secret_abc123"
_ORDER_ID = "order_TESTORDER001"
_DEF_ID = "def_razorpay_1"


def _install_fake_vault(has_key: bool):
    """Monkeypatch vault_adapter so budget resolves a Razorpay key (or not)."""
    from ads_engine import vault_adapter

    def _resolve(tenant_id, *, named_provider="", slug=""):
        if has_key and named_provider == "razorpay":
            return _DEF_ID
        return None

    def _get_secret_json(tenant_id, provider_def_id, *a):
        if has_key and provider_def_id == _DEF_ID:
            return {"key_id": "rzp_test_key", "key_secret": _KEY_SECRET,
                    "webhook_secret": "whk_secret_1"}
        return None

    vault_adapter.resolve_provider_def_id = _resolve  # type: ignore
    vault_adapter.get_secret_json = _get_secret_json  # type: ignore


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def main() -> None:
    if "droplet_work" not in ",".join(sys.path):
        sys.path.insert(0, "droplet_work")
    tmp = Path(tempfile.mkdtemp(prefix="ads_budget_"))
    _wire_store(tmp)

    from ads_engine import budget, store

    T = "tenant_smoke_1"

    # 1) DORMANT — no gateway key stored.
    _install_fake_vault(has_key=False)
    gs = budget.gateway_status(T)
    _assert(gs["configured"] is False, "dormant: gateway_status configured=False with no key")
    intent = budget.create_funding_intent(T, 500000, idem_key="ik_dormant")
    _assert(intent["needs_setup"] is True and intent["status"] in ("not_configured", "awaiting_gateway"),
            "dormant: fund intent needs_setup with no gateway key")
    bal0 = budget.get_balance(T)
    _assert(bal0["balance_minor"] == 0, "dormant: balance starts at 0")

    # 2) GATEWAY CONFIGURED — but stub the live order so no network is touched.
    _install_fake_vault(has_key=True)
    gs = budget.gateway_status(T)
    _assert(gs["configured"] is True and gs["provider"] == "razorpay",
            "configured: gateway_status reflects the stored razorpay key")

    budget._create_gateway_order = lambda provider, creds, amount_minor, currency, receipt: {
        "ok": True, "order_id": _ORDER_ID, "public_key": "rzp_test_key"}  # type: ignore

    created = budget.create_funding_intent(T, 500000, idem_key="ik_1", description="Top up")
    _assert(created["status"] == "created" and created["order_id"] == _ORDER_ID,
            "configured: fund creates an intent with a gateway order id")
    intent_id = created["intent_id"]

    # 2b) idem_key idempotency — same key returns the SAME intent (no second order).
    again = budget.create_funding_intent(T, 500000, idem_key="ik_1")
    _assert(again.get("intent_id") == intent_id and again.get("exists") is True,
            "idempotency: same idem_key resolves the same intent")

    # 3) BAD signature -> fail-CLOSED (no credit).
    bad = budget.confirm_funding(T, intent_id, payment_id="pay_1", signature="deadbeef")
    _assert(bad["ok"] is False and bad["status"] == "verification_failed",
            "fail-closed: a bad signature does not credit")
    _assert(budget.get_balance(T)["balance_minor"] == 0, "fail-closed: balance still 0 after bad sig")

    # 4) VALID Razorpay signature -> credits the balance (real crypto).
    good_sig = hmac.new(_KEY_SECRET.encode(), f"{_ORDER_ID}|pay_1".encode(),
                        hashlib.sha256).hexdigest()
    ok = budget.confirm_funding(T, intent_id, payment_id="pay_1", signature=good_sig)
    _assert(ok["ok"] is True and ok["status"] == "paid" and ok["credited_minor"] == 500000,
            "credit: a valid signature credits the intent amount")
    _assert(budget.get_balance(T)["balance_minor"] == 500000, "credit: balance == 500000 paise")

    # 5) Idempotent re-confirm -> NO double credit.
    again2 = budget.confirm_funding(T, intent_id, payment_id="pay_1", signature=good_sig)
    _assert(again2["ok"] is True and again2.get("already") is True,
            "idempotency: re-confirm is a no-op success")
    _assert(budget.get_balance(T)["balance_minor"] == 500000, "idempotency: no double credit")

    # 6) is_funded reflects the balance.
    _assert(budget.is_funded(T, 500000) is True, "is_funded: covers an equal monthly budget")
    _assert(budget.is_funded(T, 500001) is False, "is_funded: shortfall fails (fail-closed)")

    # 7) debit draws down + is floored at zero (never negative).
    store.debit_budget(T, 300000, ref={"campaign_id": "cmp_x"})
    _assert(budget.get_balance(T)["balance_minor"] == 200000, "debit: balance drawn down to 200000")
    store.debit_budget(T, 999999, ref={"campaign_id": "cmp_x"})
    _assert(budget.get_balance(T)["balance_minor"] == 0, "debit: floored at zero (never negative)")

    # 8) Ledger is append-only: credit + 2 debits = 3 rows; balance reconstructs.
    led = store.get_budget_ledger(T, 50)
    _assert(len(led) == 3, f"ledger: 3 append-only movements recorded (got {len(led)})")
    kinds = [r["kind"] for r in led]
    _assert(kinds.count("credit") == 1 and kinds.count("debit") == 2,
            "ledger: 1 credit + 2 debits")

    # 9) Tenant isolation — a second tenant sees a zero balance + cannot read tenant1's intent.
    T2 = "tenant_smoke_2"
    _assert(budget.get_balance(T2)["balance_minor"] == 0, "isolation: tenant2 balance is 0")
    _assert(store.get_budget_intent(T2, intent_id) is None,
            "isolation: tenant2 cannot read tenant1's intent")

    print("\nALL ads_engine.budget smoke assertions passed.")


if __name__ == "__main__":
    main()
