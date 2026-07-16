"""Offline tests for ai_manager.state_machine.run_command_offline — the full S0..S_END safety
spine, driven by a ScriptedTransport + StubFirewall + a registered number. ZERO keys / network /
telephony / PG. Run:
    cd droplet_work && python -m pytest ai_manager/tests/test_lifecycle.py -q
"""
from __future__ import annotations

import uuid

from ai_manager import registry, state_machine, store, config


GOOD_PIN = "4242"
BAD_PIN = "0000"


# ---------------------------------------------------------------------------
# Test doubles — a scripted transport + a stub firewall (a KNOWN PIN verifies)
# ---------------------------------------------------------------------------
class StubFirewall:
    """A deterministic firewall the state machine can inject (fw=). check_pin is True only for
    the right PIN; mint_step_up always returns a scoped token. No real firewall init needed."""

    def __init__(self, good_pin: str = GOOD_PIN):
        self.good_pin = good_pin

    def check_pin(self, tenant_id, pin):
        return pin == self.good_pin

    def mint_step_up(self, tenant_id, scope):
        return {"step_up_token": "su_" + (scope or "x"), "scope": scope, "expires_in": 300}


class ScriptedTransport:
    """speak() is a sink; listen() pops the next scripted utterance ("" => hangup);
    collect_secret() pops the next scripted PIN."""

    def __init__(self, utterances, pins):
        self.utt = list(utterances)
        self.pins = list(pins)
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)

    def listen(self):
        return self.utt.pop(0) if self.utt else ""

    def collect_secret(self, n=4, mode="voice_pin"):
        return self.pins.pop(0) if self.pins else ""


_PHONE_SEQ = [70000000]


def _unique_phone() -> str:
    """A fresh, valid +91 10-digit number per call (no collisions across tests)."""
    _PHONE_SEQ[0] += 1
    return "+919" + str(_PHONE_SEQ[0]).zfill(9)


def _register(role="manager", grants=None):
    tenant = "tenant_" + uuid.uuid4().hex[:8]
    phone = _unique_phone()
    r = registry.register(tenant_id=tenant, phone=phone, role=role,
                          grants=grants if grants is not None else ["ads", "analytics"])
    assert r["ok"], r
    return tenant, phone


def _all_text(res) -> str:
    return " | ".join(t["text"] for t in res.turns)


# ---------------------------------------------------------------------------
# S1: an unregistered caller reveals nothing
# ---------------------------------------------------------------------------
def test_unregistered_caller_reveals_nothing():
    tp = ScriptedTransport(utterances=[""], pins=[])
    res = state_machine.run_command_offline("+910000000001", transport=tp,
                                            firewall=StubFirewall())
    assert res.outcome == "reject:unregistered"
    assert res.authed is False
    assert res.tenant_id == ""
    # no business data, no PIN prompt — just the generic rejection.
    joined = _all_text(res).lower()
    assert "isn't registered" in joined or "not registered" in joined
    assert "pin" not in joined  # we never even asked for a PIN


# ---------------------------------------------------------------------------
# S2: correct login PIN authenticates; a SAFE read needs no step-up
# ---------------------------------------------------------------------------
def test_login_pin_authenticates_and_safe_read_no_stepup():
    tenant, phone = _register()
    tp = ScriptedTransport(utterances=["how many leads today", ""], pins=[GOOD_PIN])
    res = state_machine.run_command_offline(phone, transport=tp, firewall=StubFirewall())
    assert res.authed is True
    assert res.outcome == "ok"
    # a read answers with NO further PIN collection (only the login PIN was consumed).
    assert tp.pins == []          # exactly one PIN consumed (login)
    assert res.actions == []      # a read is not an "action" execution
    # only ONE "Say your PIN" prompt total (login), none for the read.
    pin_prompts = [s for s in tp.spoken if "PIN" in s]
    assert len(pin_prompts) == 1


# ---------------------------------------------------------------------------
# S6+S7+S8: a RISKY command triggers step-up PIN -> confirm -> execute -> done
# and the PIN string NEVER appears in turns/transcript.
# ---------------------------------------------------------------------------
def test_risky_command_full_stepup_confirm_execute():
    tenant, phone = _register(grants=["ads", "analytics"])
    # login PIN, then the risky command, then the step-up PIN, then "yes" to confirm, then hangup.
    tp = ScriptedTransport(utterances=["set ads budget to 5000", "yes", ""],
                           pins=[GOOD_PIN, GOOD_PIN])
    res = state_machine.run_command_offline(phone, transport=tp, firewall=StubFirewall())
    assert res.authed is True
    assert res.outcome == "ok"
    assert res.n_actions == 1
    act = res.actions[0]
    assert act["intent"] == "ads.set_budget"
    assert act["risk"] == "money"
    assert act["stepup"] is True
    assert act["executed"] is True
    assert act["result_status"] == "done"
    # TWO PINs consumed: login + step-up.
    assert tp.pins == []

    # the PIN string NEVER appears in any turn text or the flattened transcript.
    for turn in res.turns:
        assert GOOD_PIN not in turn["text"]
    transcript = state_machine._flatten_transcript(res.turns)
    assert GOOD_PIN not in transcript
    # nor in the persisted session detail (transcript snapshot + turns)
    detail = store.get_session(tenant, res.session_id)
    assert detail is not None
    assert GOOD_PIN not in detail.get("transcript_text", "")
    for t in detail["turns"]:
        assert GOOD_PIN not in t["text"]
    # the command row landed succeeded.
    cmds = store.list_commands(tenant, session_id=res.session_id)
    assert any(c["action_type"] == "ads.set_budget" and c["status"] == "succeeded" for c in cmds)


# ---------------------------------------------------------------------------
# S2: wrong-PIN lockout after N attempts
# ---------------------------------------------------------------------------
def test_wrong_pin_lockout_after_n_attempts():
    tenant, phone = _register()
    n = config.max_pin_attempts()
    assert n >= 1
    # supply N wrong PINs; the machine locks the number and ends the call.
    tp = ScriptedTransport(utterances=[], pins=[BAD_PIN] * n)
    res = state_machine.run_command_offline(phone, transport=tp, firewall=StubFirewall())
    assert res.authed is False
    assert res.outcome == "reject:lockout"
    # the number is now locked (no longer resolves on caller-ID).
    assert registry.lookup(phone) is None


# ---------------------------------------------------------------------------
# Idempotency: the same command twice in ONE session -> exactly ONE command row.
# ---------------------------------------------------------------------------
def test_idempotent_same_command_one_row():
    tenant, phone = _register(grants=["ads"])
    sid = "vs_idem_" + uuid.uuid4().hex[:6]
    # login, command, confirm, then the IDENTICAL command again, confirm, hangup.
    tp = ScriptedTransport(
        utterances=["set ads budget to 5000", "yes", "set ads budget to 5000", "yes", ""],
        pins=[GOOD_PIN, GOOD_PIN, GOOD_PIN])
    machine = state_machine.CommandMachine(tp, firewall=StubFirewall())
    res = machine.run(phone, session_id=sid)
    assert res.authed is True
    # the durable command row is deduplicated on the idempotency key: exactly ONE row, not two.
    cmds = store.list_commands(tenant, session_id=sid)
    budget_cmds = [c for c in cmds if c["action_type"] == "ads.set_budget"]
    assert len(budget_cmds) == 1, budget_cmds
    assert budget_cmds[0]["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Permission: a tool outside the caller's grants is denied (not executed).
# ---------------------------------------------------------------------------
def test_permission_denied_for_ungranted_tool():
    # an operator granted ONLY analytics tries an ads spend -> denied (default-deny).
    tenant, phone = _register(role="operator", grants=["analytics"])
    tp = ScriptedTransport(utterances=["set ads budget to 5000", ""], pins=[GOOD_PIN])
    res = state_machine.run_command_offline(phone, transport=tp, firewall=StubFirewall())
    assert res.authed is True
    # nothing executed; the step-up PIN was never even collected (only the login PIN).
    assert res.n_actions == 0
    assert tp.pins == []
    joined = _all_text(res).lower()
    assert "not permitted" in joined
    cmds = store.list_commands(tenant, session_id=res.session_id)
    assert any(c["action_type"] == "ads.set_budget" and c["status"] == "denied" for c in cmds)
