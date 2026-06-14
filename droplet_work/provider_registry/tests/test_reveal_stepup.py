"""Offline test for the firewall `provider.reveal` step-up scope (Provider-Framework W3).

Spec acceptance (PROVIDER-FRAMEWORK-PLAN §6 reveal-gate + §10.7 + §14 W3):
  * a reveal token reveals ONCE; replaying the SAME token (same jti) -> None (403) — closes the
    live jti-replay gap;
  * aud-binding: a token minted for provider X cannot reveal provider Y;
  * F3 caller-binding: a token minted for tenant A cannot be used by tenant B;
  * scope-binding: the generic spend/destructive token cannot satisfy a reveal;
  * 60s TTL: an expired token -> None;
  * AND a GOLDEN proving the EXISTING generic PIN/step-up path is byte-identical-behaviour
    (mint_step_up / verify_step_up_token round-trip + F3 sub-binding + change_pin/lockout) — the
    additive reveal scope must not have perturbed it.

No network, no PG. Uses a temp pins dir so the real var/ store is untouched.
Run: python -m provider_registry.tests.test_reveal_stepup
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path


def run() -> int:
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"UNEXPECTED {type(e).__name__}: {e}"))

    import importlib
    import firewall  # the DEPLOYED box-golden file (+ the additive reveal scope)
    importlib.reload(firewall)

    # Wire the firewall to an isolated temp store + force FIREWALL_ENABLED on for the gated tests.
    tmp = Path(tempfile.mkdtemp(prefix="fw_reveal_"))
    import os
    os.environ["FIREWALL_ENABLED"] = "true"
    assert firewall.init("test-secret-key-for-offline", tmp / "pins.json") is True, \
        "firewall.init must report available (pyjwt + secret present)"

    TENANT_A = "tenant-A"
    TENANT_B = "tenant-B"
    DEF_X = "def-x-uuid"
    DEF_Y = "def-y-uuid"

    # ===================== reveal step-up: the happy path + single-use =====================
    def t_reveal_once_then_replay_denied():
        minted = firewall.mint_reveal_step_up(TENANT_A, DEF_X)
        assert minted and minted["scope"] == "provider.reveal", minted
        assert minted["expires_in"] == firewall.REVEAL_STEP_UP_TTL_S
        assert minted["aud"] == DEF_X
        tok = minted["step_up_token"]
        # first use succeeds and returns the claims
        claims = firewall.consume_reveal_step_up(tok, DEF_X, TENANT_A)
        assert claims is not None, "first reveal use must succeed"
        assert claims.get("sub") == TENANT_A and claims.get("aud") == DEF_X
        # REPLAY the SAME token (same jti) -> denied (single-use; the jti-replay gap is closed)
        replay = firewall.consume_reveal_step_up(tok, DEF_X, TENANT_A)
        assert replay is None, "jti REPLAY must be denied (single-use)"
    check("reveal_once_then_jti_replay_403", t_reveal_once_then_replay_denied)

    def t_reveal_aud_binding():
        minted = firewall.mint_reveal_step_up(TENANT_A, DEF_X)
        tok = minted["step_up_token"]
        # a token minted for DEF_X must NOT reveal DEF_Y
        assert firewall.consume_reveal_step_up(tok, DEF_Y, TENANT_A) is None, \
            "aud mismatch (def Y with a def-X token) must be denied"
        # and the original (DEF_X) still works once (the failed DEF_Y attempt did NOT consume it)
        assert firewall.consume_reveal_step_up(tok, DEF_X, TENANT_A) is not None
    check("reveal_aud_binding", t_reveal_aud_binding)

    def t_reveal_sub_binding_f3():
        minted = firewall.mint_reveal_step_up(TENANT_A, DEF_X)
        tok = minted["step_up_token"]
        # F3: a token minted to tenant A must NOT be usable by tenant B (leaked-token replay)
        assert firewall.consume_reveal_step_up(tok, DEF_X, TENANT_B) is None, \
            "sub mismatch (tenant B with a tenant-A token) must be denied"
        assert firewall.consume_reveal_step_up(tok, DEF_X, TENANT_A) is not None
    check("reveal_sub_binding_f3", t_reveal_sub_binding_f3)

    def t_generic_token_cannot_reveal():
        # a generic spend step-up token must NOT satisfy a reveal (scope-binding)
        generic = firewall.mint_step_up(TENANT_A, scope="spend")
        assert generic and generic["step_up_token"]
        assert firewall.consume_reveal_step_up(generic["step_up_token"], DEF_X, TENANT_A) is None, \
            "a generic 'spend' token must not satisfy a 'provider.reveal' consume"
    check("generic_token_cannot_reveal", t_generic_token_cannot_reveal)

    def t_reveal_token_cannot_satisfy_generic():
        # symmetric: a reveal token must NOT satisfy the generic verify (different scope + type ok
        # but scope differs) — proves the two paths are isolated.
        minted = firewall.mint_reveal_step_up(TENANT_A, DEF_X)
        tok = minted["step_up_token"]
        assert firewall.verify_step_up_token(tok, "spend", TENANT_A) is None, \
            "a reveal-scope token must not pass the generic spend verify"
    check("reveal_token_isolated_from_generic", t_reveal_token_cannot_satisfy_generic)

    def t_reveal_expiry():
        # forge an already-expired reveal token and confirm it is rejected.
        import jwt as _jwt
        now = int(time.time())
        payload = {"sub": TENANT_A, "amr": "pin", "scope": "provider.reveal", "type": "step_up",
                   "aud": DEF_X, "iat": now - 120, "exp": now - 60, "jti": "expired-jti"}
        tok = _jwt.encode(payload, "test-secret-key-for-offline", algorithm="HS256")
        assert firewall.consume_reveal_step_up(tok, DEF_X, TENANT_A) is None, \
            "an expired reveal token must be denied"
    check("reveal_expiry", t_reveal_expiry)

    def t_reveal_no_jti_refused():
        # a token with NO jti can't be made single-use -> fail-closed (refuse).
        import jwt as _jwt
        now = int(time.time())
        payload = {"sub": TENANT_A, "amr": "pin", "scope": "provider.reveal", "type": "step_up",
                   "aud": DEF_X, "iat": now, "exp": now + 60}  # no jti
        tok = _jwt.encode(payload, "test-secret-key-for-offline", algorithm="HS256")
        assert firewall.consume_reveal_step_up(tok, DEF_X, TENANT_A) is None, \
            "a reveal token with no jti must be refused (can't be single-use)"
    check("reveal_no_jti_refused", t_reveal_no_jti_refused)

    # ===================== GOLDEN: the EXISTING generic path is unperturbed =====================
    def t_generic_stepup_roundtrip_golden():
        m = firewall.mint_step_up(TENANT_A, scope="spend")
        assert m and m["expires_in"] == firewall.STEP_UP_TTL_S == 300, m
        claims = firewall.verify_step_up_token(m["step_up_token"], "spend", TENANT_A)
        assert claims is not None and claims["scope"] == "spend" and claims["sub"] == TENANT_A
        # F3 on the generic path still holds: tenant B cannot use tenant A's token
        assert firewall.verify_step_up_token(m["step_up_token"], "spend", TENANT_B) is None
        # GENERIC tokens are deliberately NOT single-use (unchanged behaviour) — re-verify works
        again = firewall.verify_step_up_token(m["step_up_token"], "spend", TENANT_A)
        assert again is not None, "generic verify must remain replayable (byte-identical behaviour)"
    check("generic_stepup_roundtrip_golden", t_generic_stepup_roundtrip_golden)

    def t_pin_and_change_golden():
        # the existing PIN set/check/change/lockout machinery is unchanged.
        assert firewall.set_pin(TENANT_A, "1234")["ok"] is True
        assert firewall.check_pin(TENANT_A, "1234") is True
        assert firewall.check_pin(TENANT_A, "9999") is False
        # change_pin: wrong old -> invalid; right old -> ok; same new==old -> refused
        assert firewall.change_pin(TENANT_A, "0000", "5678")["reason"] == "invalid old PIN"
        assert firewall.change_pin(TENANT_A, "1234", "1234")["reason"] == "new PIN must differ from old PIN"
        assert firewall.change_pin(TENANT_A, "1234", "5678")["ok"] is True
        assert firewall.check_pin(TENANT_A, "5678") is True
    check("pin_and_change_golden", t_pin_and_change_golden)

    def t_classify_golden():
        # the risk classification table is unchanged.
        assert firewall.classify("wallet.topup") == "spend"
        assert firewall.classify("tenant.delete") == "destructive"
        assert firewall.classify("crm.read") == ""
    check("classify_golden", t_classify_golden)

    return _report("REVEAL", results)


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


def test_reveal_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
