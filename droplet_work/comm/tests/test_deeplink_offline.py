"""Offline test for comm.deeplink — the SIGNED, SINGLE-USE Telegram /start consent deep-link (S5).

Acceptance (COMMUNICATION-MASTER-PLAN §4 S5 + WAVE 2 T-DEEPLINK):
  * a minted payload is Telegram-safe: <= 64 chars of [A-Za-z0-9_-] (the /start budget).
  * a correctly-minted link VERIFIES on its OWN tenant -> (ok, phone).
  * REPLAY (verify the same payload twice) -> refused 'replayed' (single-use nonce).
  * FORGED (tamper the mac / the phone) -> refused 'bad_mac'.
  * TENANT-MISMATCH (a link minted for tenant B presented on tenant A) -> refused.
  * EXPIRED (past the TTL) -> refused 'expired'.
  * NO SECRET -> mint returns '' / verify fails-closed.
  * NEVER raises on any path.

No network, no PG. The single-use store is pointed at a temp file. The signing secret is set
via COMM_WEBHOOK_SIGNING_SECRET. Run: python -m comm.tests.test_deeplink_offline
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    os.environ["COMM_WEBHOOK_SIGNING_SECRET"] = "unit-test-deeplink-secret-BBBB"
    os.environ["COMM_DEEPLINK_STORE"] = os.path.join(tempfile.mkdtemp(), "used.json")
    os.environ.pop("COMM_DEEPLINK_TTL_S", None)

    # import AFTER the env is set so module-level reads (if any) see it; reload to be safe.
    import importlib
    from comm import deeplink as dl
    importlib.reload(dl)

    try:
        # --- mint + budget ---
        payload = dl.mint("admin", "+91 98765 43210")
        check("mint.nonempty", bool(payload))
        check("mint.within_64", len(payload) <= 64)
        check("mint.telegram_alphabet", bool(re.fullmatch(r"[A-Za-z0-9_-]+", payload)))

        # --- verify (own tenant) ---
        ok, phone, err = dl.verify("admin", payload)
        check("verify.ok", ok is True and err == "")
        check("verify.phone_digits", phone == "919876543210")

        # --- replay (single-use) ---
        ok2, _, err2 = dl.verify("admin", payload)
        check("replay.refused", ok2 is False and err2 == "replayed")

        # --- a no-consume verify does NOT burn the nonce (e.g. a dry validation) ---
        p_dry = dl.mint("admin", "9000000000")
        okd1, _, _ = dl.verify("admin", p_dry, consume=False)
        okd2, _, _ = dl.verify("admin", p_dry, consume=True)
        check("noconsume.then_consume_ok", okd1 is True and okd2 is True)

        # --- forged mac ---
        p3 = dl.mint("admin", "9123456789")
        parts = p3.split("_")
        parts[-1] = ("0" * len(parts[-1])) if parts[-1] != "0" * len(parts[-1]) else ("1" * len(parts[-1]))
        ok3, _, err3 = dl.verify("admin", "_".join(parts))
        check("forged_mac.refused", ok3 is False and err3 == "bad_mac")

        # --- tampered phone (mac no longer matches) ---
        p4 = dl.mint("admin", "9123456789")
        parts4 = p4.split("_"); parts4[1] = "9999999999"
        ok4, _, err4 = dl.verify("admin", "_".join(parts4))
        check("tamper_phone.refused", ok4 is False and err4 == "bad_mac")

        # --- tenant mismatch (minted for 'admin', presented on 'tenant_b') ---
        p5 = dl.mint("admin", "9123456789")
        ok5, _, err5 = dl.verify("tenant_b", p5)
        check("tenant_mismatch.refused", ok5 is False and err5 == "tenant_mismatch")

        # --- long / unsafe tenant id is hashed but still binds correctly ---
        long_t = "org_with_underscores_AND_long_slug"
        p6 = dl.mint(long_t, "9123456789")
        check("long_tenant.within_64", len(p6) <= 64)
        ok6, ph6, _ = dl.verify(long_t, p6)
        check("long_tenant.verify_ok", ok6 is True and ph6 == "9123456789")
        ok6b, _, err6b = dl.verify("some_other_tenant", dl.mint(long_t, "9"))
        check("long_tenant.mismatch", ok6b is False and err6b == "tenant_mismatch")

        # --- expired ---
        os.environ["COMM_DEEPLINK_TTL_S"] = "0"
        p7 = dl.mint("admin", "9123456789")
        time.sleep(1.1)
        ok7, _, err7 = dl.verify("admin", p7)
        check("expired.refused", ok7 is False and err7 == "expired")
        os.environ.pop("COMM_DEEPLINK_TTL_S", None)

        # --- malformed payloads never raise ---
        for bad in ("", "garbage", "a_b_c", "a_b_c_d_e_f_g", "_" * 70):
            try:
                okx, _, _ = dl.verify("admin", bad)
                check(f"malformed.no_raise[{bad[:6]!r}]", okx is False)
            except Exception:  # noqa: BLE001
                check(f"malformed.no_raise[{bad[:6]!r}]", False)

        # --- no signing secret -> fail-closed ---
        os.environ.pop("COMM_WEBHOOK_SIGNING_SECRET", None)
        importlib.reload(dl)
        check("no_secret.mint_empty", dl.mint("admin", "9") == "")
        oks, _, errs = dl.verify("admin", payload)
        check("no_secret.verify_failclosed", oks is False and errs == "no_secret")

    finally:
        for k in ("COMM_WEBHOOK_SIGNING_SECRET", "COMM_DEEPLINK_STORE", "COMM_DEEPLINK_TTL_S"):
            os.environ.pop(k, None)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
