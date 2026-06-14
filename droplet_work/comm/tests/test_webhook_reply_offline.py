"""Offline test for the W2 inbound->brain->reply loop wired into comm.webhook.

Acceptance (COMMUNICATION-MASTER-PLAN WAVE 2):
  * COMM_BRAIN_ENABLED OFF -> the webhook keeps W1 behaviour (store + ack, NO reply, NO Groq).
  * COMM_BRAIN_ENABLED ON  -> a normal inbound message is replied to: ONE Groq call (grounded in
    the session seeds), the reply is SENT via the engine, and the assistant turn is appended.
  * an OPT-OUT word short-circuits BEFORE any Groq call (free) and sends the canned ack.
  * a /start deep-link is verified + binds (no brain reply for a bare /start command).
  * INBOUND MEDIA (a photo-only message, no text) does NOT crash -> 200 ack, no reply, no Groq.
  * the per-tenant daily Groq cap blocks the LLM call once exceeded (still 200, no reply).
  * the body-size cap drops an oversized body (200 ack, no store/parse).
  * NEVER raises; the handler always returns a (status, body) tuple.

No network, no PG. vault_read / sessions / brain._groq_chat / engine.send are monkeypatched.
Run: python -m comm.tests.test_webhook_reply_offline
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

from comm import webhook, vault_read, sessions, config, brain, engine, deeplink  # noqa: F401
from comm.channels.base import SendResult

_SIGNING = "unit-test-signing-secret-CCCC"


def _run(coro):
    return asyncio.run(coro)


def _body(update_id=1, chat_id="555111", text="hi riya", media=False):
    msg = {"chat": {"id": chat_id, "type": "private"}}
    if media:
        msg["photo"] = [{"file_id": "AgACphoto", "file_unique_id": "u"}]
    else:
        msg["text"] = text
    return json.dumps({"update_id": update_id, "message": msg}).encode("utf-8")


def main() -> int:
    fails = []
    calls = {"groq": 0, "send": 0, "append": 0, "goc": 0}

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    os.environ["COMM_ENABLED"] = "1"
    os.environ["COMM_TELEGRAM_ENABLED"] = "1"
    os.environ["COMM_WEBHOOK_SIGNING_SECRET"] = _SIGNING
    os.environ["COMM_DEEPLINK_STORE"] = os.path.join(tempfile.mkdtemp(), "u.json")
    os.environ.pop("COMM_GROQ_DAILY_CAP", None)
    os.environ.pop("COMM_INBOUND_RATE_PER_MIN", None)

    # --- monkeypatch the offline seams ---
    orig = {
        "resolve": vault_read.resolve_provider_def_id,
        "goc": sessions.get_or_create, "append": sessions.append_turn,
        "get_session": sessions.get_session, "groq": brain._groq_chat, "send": engine.send,
        "consent": __import__("comm.consent", fromlist=["record_consent"]).record_consent,
    }

    def fake_resolve(tenant_id, *, named_provider="", slug=""):
        return {"admin": "pd_admin"}.get(tenant_id, "")

    def fake_goc(tenant_id, **kw):
        calls["goc"] += 1
        return "cse_fake"

    def fake_append(tenant_id, sid, *, role="user", text_body="", is_admin=False):
        if role == "assistant":
            calls["append"] += 1
        return True

    def fake_get_session(tenant_id, session_id, *, is_admin=False):
        # the post-call seeds the brain grounds on
        return {
            "agent_persona": "Riya", "name": "Rahul", "contact_phone": "919876500000",
            "call_summary": "Rahul asked for a 2BHK site visit this weekend",
            "next_action": "share brochure + confirm Saturday", "outcome": "interested",
            "interest": "hot", "company_name": "Acme Homes", "product_name": "2BHK flats",
            "turns": [{"role": "user", "text": "hi"}],
        }

    def fake_groq(messages, **kw):
        calls["groq"] += 1
        # assert the grounding made it into the system message
        sysm = messages[0]["content"] if messages else ""
        fake_groq.last_sys = sysm  # type: ignore
        return "Bilkul Rahul, Saturday ka site visit fix karte hain!"

    async def fake_send(tenant_id, env, **kw):
        calls["send"] += 1
        fake_send.last_text = env.text  # type: ignore
        return SendResult.success("telegram", external_id="999")

    import comm.consent as _consent_mod

    def fake_consent(tenant_id, **kw):
        return True

    vault_read.resolve_provider_def_id = fake_resolve  # type: ignore
    sessions.get_or_create = fake_goc                  # type: ignore
    sessions.append_turn = fake_append                 # type: ignore
    sessions.get_session = fake_get_session            # type: ignore
    brain._groq_chat = fake_groq                       # type: ignore
    engine.send = fake_send                            # type: ignore
    _consent_mod.record_consent = fake_consent         # type: ignore
    webhook._SEEN_UPDATES.clear()

    good = webhook.derive_secret_token("admin", "pd_admin", signing_secret=_SIGNING)

    try:
        # --- (1) BRAIN OFF -> store + ack, NO reply, NO Groq (W1 behaviour preserved) ---
        os.environ.pop("COMM_BRAIN_ENABLED", None)
        calls["groq"] = calls["send"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=1)))
        check("brain_off.200_no_reply", sc == 200 and body.get("reply") is False)
        check("brain_off.no_groq", calls["groq"] == 0 and calls["send"] == 0)
        check("brain_off.stored", body.get("stored") is True)

        # --- (2) BRAIN ON -> one Groq call, reply sent, assistant turn appended, grounded ---
        os.environ["COMM_BRAIN_ENABLED"] = "1"
        calls["groq"] = calls["send"] = calls["append"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=2, text="weekend visit ho sakta hai?")))
        check("brain_on.200", sc == 200 and body.get("ok"))
        check("brain_on.one_groq", calls["groq"] == 1)
        check("brain_on.replied", body.get("reply") is True and calls["send"] == 1)
        check("brain_on.assistant_turn_appended", calls["append"] == 1)
        check("brain_on.grounded", "site visit this weekend" in getattr(fake_groq, "last_sys", ""))
        check("brain_on.reply_text_sent", "site visit" in getattr(fake_send, "last_text", ""))

        # --- (3) OPT-OUT short-circuits BEFORE Groq (free), sends a canned ack ---
        calls["groq"] = calls["send"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=3, text="please STOP")))
        check("optout.200", sc == 200)
        check("optout.no_groq", calls["groq"] == 0)
        check("optout.action_opted_out", body.get("action") == "opted_out")
        check("optout.canned_ack_sent", calls["send"] == 1)

        # --- (4) HANDOFF short-circuits BEFORE Groq ---
        calls["groq"] = calls["send"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=4, text="I want to talk to human")))
        check("handoff.no_groq", calls["groq"] == 0 and body.get("action") == "needs_human")

        # --- (5) INBOUND MEDIA (photo, no text) does NOT crash, no reply, no Groq ---
        calls["groq"] = calls["send"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=5, media=True)))
        check("media.no_crash_200", sc == 200 and body.get("ok"))
        check("media.no_reply_no_groq", body.get("reply") is False and calls["groq"] == 0)

        # --- (6) /start deep-link verifies + binds, no brain reply for a bare /start ---
        payload = deeplink.mint("admin", "919876500000")
        calls["groq"] = calls["send"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=6, text=f"/start {payload}")))
        check("start.200", sc == 200)
        check("start.bound", body.get("start", {}).get("bound") is True)
        check("start.no_brain_reply", body.get("reply") is False and calls["groq"] == 0)

        # --- (7) per-tenant daily Groq cap blocks the LLM once exceeded ---
        os.environ["COMM_GROQ_DAILY_CAP"] = "1"
        import comm.ratelimit as rl
        rl._GROQ_DAY.clear()
        calls["groq"] = calls["send"] = 0
        sc1, b1 = _run(webhook.handle("admin", good, _body(update_id=7, text="hello one")))
        sc2, b2 = _run(webhook.handle("admin", good, _body(update_id=8, text="hello two")))
        check("groqcap.first_replies", calls["groq"] == 1 and b1.get("reply") is True)
        check("groqcap.second_blocked", b2.get("action") == "groq_cap" and calls["groq"] == 1)
        os.environ.pop("COMM_GROQ_DAILY_CAP", None)
        rl._GROQ_DAY.clear()

        # --- (8) body-size cap drops an oversized body (no store, no parse) ---
        os.environ["COMM_INBOUND_BODY_MAX_BYTES"] = "10"
        before = calls["goc"]
        sc, body = _run(webhook.handle("admin", good, _body(update_id=9, text="x" * 200)))
        check("bodycap.200_dropped", sc == 200 and body.get("error") == "body_too_large")
        check("bodycap.no_store", calls["goc"] == before)
        os.environ.pop("COMM_INBOUND_BODY_MAX_BYTES", None)

        # --- (9) a Groq failure on the reply path -> 200, no reply, never raises ---
        def fail_groq(messages, **kw):
            return ""
        brain._groq_chat = fail_groq  # type: ignore
        calls["send"] = 0
        sc, body = _run(webhook.handle("admin", good, _body(update_id=11, text="anything")))
        check("groqfail.200_no_reply", sc == 200 and body.get("reply") is False and calls["send"] == 0)

    finally:
        vault_read.resolve_provider_def_id = orig["resolve"]   # type: ignore
        sessions.get_or_create = orig["goc"]                   # type: ignore
        sessions.append_turn = orig["append"]                  # type: ignore
        sessions.get_session = orig["get_session"]             # type: ignore
        brain._groq_chat = orig["groq"]                        # type: ignore
        engine.send = orig["send"]                             # type: ignore
        _consent_mod.record_consent = orig["consent"]          # type: ignore
        for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED", "COMM_BRAIN_ENABLED",
                  "COMM_WEBHOOK_SIGNING_SECRET", "COMM_DEEPLINK_STORE", "COMM_GROQ_DAILY_CAP",
                  "COMM_INBOUND_RATE_PER_MIN", "COMM_INBOUND_BODY_MAX_BYTES"):
            os.environ.pop(k, None)
        webhook._SEEN_UPDATES.clear()

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
