"""Offline test for comm.post_call + comm.founder_alert + comm.consent (Wave 1, W1-P3).

Acceptance (COMMUNICATION-MASTER-PLAN §2.3 / §1.1 / §5.3 / WAVE 1):
  * snapshot() is PURE-SYNCHRONOUS and holds NO reference to the live rec/tr/camp_fields
    (mutating the live dict AFTER snapshot does not change the snapshot) — the earner law;
  * is_hot_lead() matches caller.py's existing definition (>=70, non-opt_out);
  * run() is DORMANT (no I/O, returns skip/skip) when the flags are off — resting byte-identical;
  * run() with master ON but feature flags OFF still sends NOTHING;
  * run() NEVER raises and is fully bounded (the engine owns the per-channel wait_for cap);
  * the founder alert envelope is PII-MINIMIZED by default (no name/phone/summary inline) and
    carries an "Open in panel" URL button; full-PII opt-in inlines the detail (§5.7);
  * consent.derive_basis() derives the basis from lead_source (NEVER a constant, §5.2);
  * a hot lead with the alert flag ON dispatches EXACTLY ONE founder send (engine monkeypatched);
  * a non-hot lead dispatches NO founder send.

No network, no PG. comm.engine.send + derive_founder_chat_id are monkeypatched.
Run: python -m comm.tests.test_post_call_offline
"""
from __future__ import annotations

import asyncio
import os
import sys

from comm import post_call, founder_alert, consent
from comm.channels.base import SendResult


def _clear_flags():
    for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED",
              "FEATURE_TELEGRAM_FOUNDER_ALERT", "FEATURE_TELEGRAM_FOLLOWUP",
              "COMM_FOUNDER_ALERT_FULL_PII"):
        os.environ.pop(k, None)


def _snap(**over):
    base = dict(
        name="Riya", phone="+919812345678", id="c1", outcome="interested",
        interest=82, duration_s=90, campaign_name="Godrej", room="r1",
    )
    base.update(over.get("rec", {}))
    tr = dict(summary="Wants a 2BHK site visit", next_action="Book Saturday visit", interest=82)
    tr.update(over.get("tr", {}))
    cf = dict(company_name="Godrej", product_name="Godrej Hills",
              agent_name="Riya", lead_source="inbound_form")
    cf.update(over.get("cf", {}))
    return post_call.snapshot(base, tr, cf, tenant_id="admin", call_id="c1")


def main() -> int:
    passed = 0
    fail = []

    def ok(name, cond):
        nonlocal passed
        if cond:
            passed += 1
        else:
            fail.append(name)

    _clear_flags()

    # 1) snapshot is faithful + a hot lead
    s = _snap()
    ok("snapshot.fields", s["phone"] == "+919812345678" and s["interest"] == 82
       and s["summary"].startswith("Wants") and s["agent_name"] == "Riya")
    ok("snapshot.hotlead", post_call.is_hot_lead(s) is True)

    # 2) snapshot holds NO live ref (the earner law)
    live = {"name": "X", "phone": "P", "id": "c2", "interest": 90, "outcome": "interested"}
    s2 = post_call.snapshot(live, {}, {}, tenant_id="t", call_id="c2")
    live["name"] = "MUTATED"
    ok("snapshot.no_alias", s2["name"] == "X")

    # 3) hot-lead gate edges
    ok("hot.cold", post_call.is_hot_lead(dict(s, interest=40)) is False)
    ok("hot.optout", post_call.is_hot_lead(dict(s, outcome="opt_out")) is False)
    ok("hot.boundary", post_call.is_hot_lead(dict(s, interest=70)) is True)

    # 4) consent basis derivation (never a constant)
    ok("consent.inbound", consent.derive_basis("inbound_form") == "inbound_form")
    ok("consent.purchased", consent.derive_basis("purchased_list") == "purchased_optin")
    ok("consent.call", consent.derive_basis("phone_call") == "prior_transaction")
    ok("consent.empty", consent.derive_basis("") == "prior_transaction")

    # 5) alert envelope — minimized by default, full-pii opt-in
    env_min = founder_alert.build_alert_envelope(dict(s, founder_chat_id="999"), full_pii=False)
    ok("alert.min.dest", env_min.to_ref == "999" and env_min.kind == "alert")
    ok("alert.min.button", bool(env_min.buttons) and env_min.buttons[0].url.startswith("http"))
    ok("alert.min.no_pii", "+919812345678" not in env_min.text and "Riya" not in env_min.text
       and "Wants a 2BHK" not in env_min.text)
    env_full = founder_alert.build_alert_envelope(dict(s, founder_chat_id="999"), full_pii=True)
    ok("alert.full.pii", "+919812345678" in env_full.text and "Wants a 2BHK" in env_full.text)

    # 6) run() DORMANT when flags off (no I/O, skip/skip)
    _clear_flags()
    r0 = asyncio.run(post_call.run(s))
    ok("run.dormant", r0 == {"alert": "skip", "summary": "skip"})

    # 7) master+channel ON but feature flags OFF -> still nothing
    os.environ["COMM_ENABLED"] = "1"
    os.environ["COMM_TELEGRAM_ENABLED"] = "1"
    r1 = asyncio.run(post_call.run(s))
    ok("run.features_off", r1["alert"] == "skip" and r1["summary"] == "skip")

    # 8) hot lead + alert flag ON -> EXACTLY one founder send (engine monkeypatched)
    sent = []

    async def _fake_send(tenant_id, env, **kw):
        sent.append((tenant_id, env.kind, env.to_ref, env.idempotency_key))
        return SendResult.success("telegram", external_id="m1", provider="telegram")

    async def _fake_chat(tenant_id, **kw):
        return "777"

    from comm import engine as _engine
    orig_send, orig_chat = _engine.send, _engine.derive_founder_chat_id
    _engine.send, _engine.derive_founder_chat_id = _fake_send, _fake_chat
    try:
        os.environ["FEATURE_TELEGRAM_FOUNDER_ALERT"] = "1"
        sent.clear()
        rA = asyncio.run(post_call.run(s))
        ok("run.alert.one_send", len(sent) == 1 and sent[0][1] == "alert"
           and sent[0][2] == "777" and sent[0][3] == "comms:c1:alert")
        ok("run.alert.status", rA["alert"] in ("sent", "ok"))

        # 9) non-hot lead -> NO founder send
        sent.clear()
        rC = asyncio.run(post_call.run(dict(s, interest=30)))
        ok("run.cold.no_send", len(sent) == 0 and rC["alert"] == "skip")

        # 10) followup ON but no contact chat_id -> clean no_destination (not an error)
        os.environ["FEATURE_TELEGRAM_FOLLOWUP"] = "1"
        sent.clear()
        rF = asyncio.run(post_call.run(dict(s, interest=30)))  # cold so only followup path
        ok("run.followup.no_dest", rF["summary"] == "no_destination" and len(sent) == 0)

        # 11) followup ON + contact chat_id present -> one summary send
        sent.clear()
        rS = asyncio.run(post_call.run(dict(s, interest=30, contact_chat_id="555")))
        ok("run.followup.send", len(sent) == 1 and sent[0][1] == "summary"
           and sent[0][2] == "555" and sent[0][3] == "comms:c1:summary")
    finally:
        _engine.send, _engine.derive_founder_chat_id = orig_send, orig_chat

    # 12) run NEVER raises even with a garbage snapshot
    try:
        asyncio.run(post_call.run({}))
        asyncio.run(post_call.run({"tenant_id": "x", "outcome": None, "interest": "NaN"}))
        ok("run.never_raises", True)
    except Exception:  # noqa: BLE001
        ok("run.never_raises", False)

    _clear_flags()
    print(f"test_post_call_offline: {passed} PASS, {len(fail)} FAIL")
    if fail:
        print("  FAILED:", ", ".join(fail))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
