"""Offline test for comm.channels.telegram — the Telegram adapter (Wave 1).

Acceptance (COMMUNICATION-MASTER-PLAN §2.1 / WAVE 1):
  * dormant when no token: status()='not_configured', send() returns a non-ok 'not_configured'
    SendResult, NEVER raises, NEVER calls out;
  * sendMessage: routes a text envelope to sendMessage, returns the provider message_id;
  * inline URL buttons: a button -> reply_markup.inline_keyboard with a url row;
  * media: a photo/document/video envelope routes to sendPhoto/Document/Video and caches the
    returned file_id (the §1.2 #6 zero-cost re-send);
  * verify(): getMe -> (True, username); a token-less adapter -> (False, '');
  * derive_founder_chat_id(): picks the most-recent PRIVATE-chat sender from getUpdates, ignores
    a group update, caches in-process;
  * the token NEVER appears in a redacted URL (no token leak in logs).

No network: comm.channels.telegram._api_call is replaced by an in-memory fake Bot API.
Run: python -m comm.tests.test_telegram_offline
"""
from __future__ import annotations

import asyncio
import sys

from comm.channels import telegram as tg
from comm.channels.base import Button, MediaItem, SendEnvelope


# ---------------------------------------------------------------------------
# A fake Bot API: records the last call, returns canned ok/result by method.
# ---------------------------------------------------------------------------
class FakeAPI:
    def __init__(self):
        self.calls = []           # (method, payload)
        self.updates = []         # getUpdates result list
        self.me = {"username": "mr_kunal_bot", "id": 7777}
        self.fail = False

    async def __call__(self, token, method, payload, *, timeout):
        self.calls.append((method, payload))
        if self.fail:
            return False, None, "net_FakeError"
        if method == "getMe":
            return True, dict(self.me), ""
        if method == "getUpdates":
            return True, list(self.updates), ""
        if method == "sendMessage":
            return True, {"message_id": 1001}, ""
        if method == "sendPhoto":
            return True, {"message_id": 1002, "photo": [{"file_id": "SMALL"}, {"file_id": "BIG_PHOTO_ID"}]}, ""
        if method == "sendVideo":
            return True, {"message_id": 1003, "video": {"file_id": "VIDEO_ID"}}, ""
        if method == "sendDocument":
            return True, {"message_id": 1004, "document": {"file_id": "DOC_ID"}}, ""
        return False, None, "unknown_method"


def _run(coro):
    return asyncio.run(coro)


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # --- 1) dormant when token-less ---
    dormant = tg.TelegramAdapter("")
    check("dormant.status==not_configured", dormant.status() == "not_configured")
    r = _run(dormant.send(SendEnvelope(to_ref="123", text="hi")))
    check("dormant.send not ok", (not r.ok) and r.status == "not_configured")
    ok, user = _run(dormant.verify())
    check("dormant.verify False", ok is False and user == "")

    # --- install the fake API for the configured-adapter tests ---
    fake = FakeAPI()
    orig = tg._api_call
    tg._api_call = fake  # type: ignore

    try:
        a = tg.TelegramAdapter("123456:FAKE_TOKEN_ABC", provider_def_id="pd1")
        check("configured.status==configured", a.status() == "configured")
        check("estimate_cost==0", a.estimate_cost_minor(SendEnvelope()) == 0)

        # --- 2) text -> sendMessage, returns message_id ---
        r = _run(a.send(SendEnvelope(to_ref="42", text="Hello from Riya")))
        check("text.ok", r.ok and r.status == "sent")
        check("text.external_id==1001", r.external_id == "1001")
        last_method, last_payload = fake.calls[-1]
        check("text.method==sendMessage", last_method == "sendMessage")
        check("text.no_markup_when_no_buttons", "reply_markup" not in last_payload)

        # --- 3) inline URL buttons ---
        env = SendEnvelope(to_ref="42", text="Hot lead", buttons=[Button(text="Call Now", url="https://panel.famit.in/x")])
        r = _run(a.send(env))
        _m, p = fake.calls[-1]
        kb = p.get("reply_markup", {}).get("inline_keyboard", [])
        check("button.url_row_present", bool(kb) and kb[0][0]["url"] == "https://panel.famit.in/x")
        check("button.text", kb[0][0]["text"] == "Call Now")

        # --- 4) media: photo caches the largest file_id ---
        env = SendEnvelope(to_ref="42", text="Brochure", kind="photo",
                           media=[MediaItem(kind="photo", url="https://cdn/x.png")])
        r = _run(a.send(env))
        m, p = fake.calls[-1]
        check("photo.method==sendPhoto", m == "sendPhoto")
        check("photo.caption", p.get("caption") == "Brochure")
        check("photo.file_id_cached==BIG", r.file_id_cached == "BIG_PHOTO_ID")

        # --- video + document ---
        r = _run(a.send(SendEnvelope(to_ref="42", kind="video",
                                     media=[MediaItem(kind="video", url="https://cdn/v.mp4")])))
        check("video.file_id_cached==VIDEO_ID", r.file_id_cached == "VIDEO_ID")
        r = _run(a.send(SendEnvelope(to_ref="42", kind="document",
                                     media=[MediaItem(kind="document", url="https://cdn/d.pdf")])))
        check("document.file_id_cached==DOC_ID", r.file_id_cached == "DOC_ID")

        # --- media with no source -> clean failure ---
        r = _run(a.send(SendEnvelope(to_ref="42", kind="photo", media=[MediaItem(kind="photo")])))
        check("media.no_source_fails", (not r.ok) and r.error_code == "no_media_source")

        # --- 5) verify -> getMe ---
        ok, user = _run(a.verify())
        check("verify.ok", ok and user == "mr_kunal_bot")

        # --- 6) derive_founder_chat_id: private chat wins, group ignored, cached ---
        fake.updates = [
            {"update_id": 1, "message": {"chat": {"id": -100200, "type": "group"}}},
            {"update_id": 2, "message": {"chat": {"id": 555111, "type": "private"}}},
        ]
        cid = _run(a.derive_founder_chat_id(force=True))
        check("chatid.private_wins", cid == "555111")
        # cached: a second call with the cache present returns without a new getUpdates
        n_before = len([c for c in fake.calls if c[0] == "getUpdates"])
        cid2 = _run(a.derive_founder_chat_id())
        n_after = len([c for c in fake.calls if c[0] == "getUpdates"])
        check("chatid.cached", cid2 == "555111" and n_after == n_before)

        # --- destination guard ---
        r = _run(a.send(SendEnvelope(to_ref="", text="x")))
        check("no_destination_fails", (not r.ok) and r.error_code == "no_destination")

    finally:
        tg._api_call = orig  # type: ignore

    # --- 7) token redaction (no leak) ---
    red = tg._redact_url("https://api.telegram.org/bot123456:SECRET/sendMessage")
    check("url_redacts_token", "SECRET" not in red and "<redacted>" in red)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
