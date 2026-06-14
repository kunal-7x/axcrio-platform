"""Offline test for comm.webhook — the FAIL-CLOSED inbound Telegram webhook (S2 acceptance).

Acceptance (COMMUNICATION-MASTER-PLAN §4 S2 + WAVE 2 T-WEBHOOK):
  * dormant (COMM_ENABLED off)                       -> 403, NOT 200, NO DB touch
  * tenant has no configured bot (no provider_def)   -> 403 (bot-identity binding)
  * no signing secret available                      -> 403 (fail-closed, can't derive a secret)
  * missing secret header                            -> 403
  * WRONG secret header                              -> 403
  * ANOTHER tenant's valid secret on THIS path       -> 403 (secret bound to the PATH tenant)
  * CORRECT secret for THIS path tenant              -> 200, and ONLY THEN is a DB row touched
  * a Telegram retry (same update_id)                -> 200 dedup, no double-store
  * GUC-after-verify: the store fn (sessions.get_or_create) is called ONLY on the verified path
  * NEVER raises on any path; the handler returns a (status, body) tuple.

No network, no PG. vault_read.resolve_provider_def_id + sessions.* are monkeypatched.
Run: python -m comm.tests.test_webhook_offline
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from comm import webhook, vault_read, sessions, config  # noqa: F401

_SIGNING = "unit-test-signing-secret-AAAA"


def _run(coro):
    return asyncio.run(coro)


def _body(update_id=1, chat_id="555111", text="hi riya"):
    return json.dumps({
        "update_id": update_id,
        "message": {"chat": {"id": chat_id, "type": "private"}, "text": text},
    }).encode("utf-8")


def main() -> int:
    fails = []
    calls = {"get_or_create": 0, "append_turn": 0}

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # --- flags ON for the verified-path tests (dormant test toggles them OFF explicitly) ---
    os.environ["COMM_ENABLED"] = "1"
    os.environ["COMM_TELEGRAM_ENABLED"] = "1"
    os.environ["COMM_WEBHOOK_SIGNING_SECRET"] = _SIGNING

    # --- monkeypatch the registry + store so the test is fully offline ---
    orig_resolve = vault_read.resolve_provider_def_id
    orig_goc = sessions.get_or_create
    orig_append = sessions.append_turn

    # tenant 'admin' has a bot (pd_admin); tenant 'nobot' has none.
    def fake_resolve(tenant_id, *, named_provider="", slug=""):
        return {"admin": "pd_admin", "tenant_b": "pd_b"}.get(tenant_id, "")

    def fake_goc(tenant_id, **kw):
        calls["get_or_create"] += 1
        return "cse_fake"

    def fake_append(tenant_id, sid, **kw):
        calls["append_turn"] += 1
        return True

    vault_read.resolve_provider_def_id = fake_resolve  # type: ignore
    sessions.get_or_create = fake_goc                  # type: ignore
    sessions.append_turn = fake_append                 # type: ignore
    # reset the in-process update de-dup cache between runs
    webhook._SEEN_UPDATES.clear()

    try:
        # the correct secret for tenant 'admin' bound to its bot 'pd_admin'
        good_secret = webhook.derive_secret_token("admin", "pd_admin", signing_secret=_SIGNING)
        check("derive.nonempty", bool(good_secret) and len(good_secret) == 64)
        # a different tenant's secret (tenant_b) — must NOT validate on admin's path
        other_secret = webhook.derive_secret_token("tenant_b", "pd_b", signing_secret=_SIGNING)
        check("derive.distinct_per_tenant", good_secret != other_secret)

        # 1) dormant master flag -> 403, no store
        os.environ["COMM_ENABLED"] = "0"
        sc, body = _run(webhook.handle("admin", good_secret, _body()))
        check("dormant.403", sc == 403 and not body.get("ok"))
        os.environ["COMM_ENABLED"] = "1"

        # 2) no configured bot -> 403
        sc, body = _run(webhook.handle("nobot", good_secret, _body()))
        check("no_bot.403", sc == 403 and body.get("error") == "no_channel")

        # 3) missing secret header -> 403
        before = calls["get_or_create"]
        sc, body = _run(webhook.handle("admin", "", _body()))
        check("no_header.403", sc == 403 and body.get("error") == "bad_secret")
        check("no_header.no_store", calls["get_or_create"] == before)  # GUC-after-verify

        # 4) wrong secret -> 403
        sc, body = _run(webhook.handle("admin", "deadbeef" * 8, _body()))
        check("wrong_secret.403", sc == 403 and body.get("error") == "bad_secret")

        # 5) ANOTHER tenant's valid secret on admin's path -> 403 (bound to the PATH tenant)
        before = calls["get_or_create"]
        sc, body = _run(webhook.handle("admin", other_secret, _body()))
        check("cross_tenant_secret.403", sc == 403 and body.get("error") == "bad_secret")
        check("cross_tenant.no_store", calls["get_or_create"] == before)

        # 6) CORRECT secret -> 200, and ONLY NOW a DB row is touched (GUC-after-verify)
        before = calls["get_or_create"]
        sc, body = _run(webhook.handle("admin", good_secret, _body(update_id=10)))
        check("correct.200", sc == 200 and body.get("ok") and body.get("handled"))
        check("correct.stored", body.get("stored") is True)
        check("correct.touched_db_after_verify", calls["get_or_create"] == before + 1)
        check("correct.no_reply_w1", body.get("reply") is False)

        # 7) a retry with the SAME update_id -> dedup 200, no second store
        before = calls["get_or_create"]
        sc, body = _run(webhook.handle("admin", good_secret, _body(update_id=10)))
        check("retry.dedup_200", sc == 200 and body.get("dedup") is True)
        check("retry.no_double_store", calls["get_or_create"] == before)

        # 8) no signing secret available -> fail-closed even with a 'matching-shape' header
        os.environ.pop("COMM_WEBHOOK_SIGNING_SECRET", None)
        # force the file fallback to also miss by pointing it at a nonexistent path
        os.environ["FAMIT_SECRET_FILE"] = "/nonexistent/comm/secret/path"
        sc, body = _run(webhook.handle("admin", good_secret, _body(update_id=99)))
        check("no_signing_secret.403", sc == 403 and body.get("error") == "bad_secret")
        os.environ.pop("FAMIT_SECRET_FILE", None)
        os.environ["COMM_WEBHOOK_SIGNING_SECRET"] = _SIGNING

        # 9) never raises on a garbage body (correct secret, non-JSON) -> 200 ack, no crash
        sc, body = _run(webhook.handle("admin", good_secret, b"\xff\x00not json"))
        check("garbage_body.no_raise_200", sc == 200 and body.get("ok"))

    finally:
        vault_read.resolve_provider_def_id = orig_resolve  # type: ignore
        sessions.get_or_create = orig_goc                  # type: ignore
        sessions.append_turn = orig_append                 # type: ignore
        for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED",
                  "COMM_WEBHOOK_SIGNING_SECRET", "FAMIT_SECRET_FILE"):
            os.environ.pop(k, None)
        webhook._SEEN_UPDATES.clear()

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
