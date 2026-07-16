"""Offline tests for ai_manager.store — InMemory backend round-trips, idempotency, audit
scrubbing/append-only, tenant isolation, dashboard zero-fill. No network, no PG, no creds. Run:
    cd droplet_work && python -m pytest ai_manager/tests/test_store.py -q
"""
from __future__ import annotations

import uuid

from ai_manager import store


def _tid(prefix: str = "t") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Sessions: create -> add_turn -> end_session -> get_session round-trip
# ---------------------------------------------------------------------------
def test_session_roundtrip_with_turns_and_commands():
    tid = _tid()
    sid = "sess_" + uuid.uuid4().hex[:8]
    assert store.create_session(tid, sid, channel="phone", caller_phone="+91***10") == sid
    store.add_turn(tid, sid, "agent", "Hi, you're verified.", seq=0)
    store.add_turn(tid, sid, "user", "set ads budget to 5000", seq=1)
    # a command on this session shows up in the detail view
    cmd_id = store.create_command(tid, session_id=sid, action_type="ads.set_budget",
                                  raw_text="set ads budget to 5000", risk_level=3)
    store.end_session(tid, sid, status="completed", transcript_text="Agent: Hi\nUser: ...",
                      outcome="ok", n_actions=1)

    detail = store.get_session(tid, sid)
    assert detail is not None
    assert detail["id"] == sid
    assert detail["status"] == "completed"
    assert detail["caller_phone"] == "+91***10"
    # turns present + ordered by seq
    texts = [t["text"] for t in detail["turns"]]
    assert "Hi, you're verified." in texts
    assert "set ads budget to 5000" in texts
    assert [t["seq"] for t in detail["turns"]] == sorted(t["seq"] for t in detail["turns"])
    # commands present
    assert any(c["id"] == cmd_id for c in detail["commands"])
    # recording fields zero-filled on a non-recorded session
    assert detail["has_recording"] is False
    assert detail["recording_status"] in ("", "none")
    assert detail["recording_duration_s"] == 0


def test_get_session_unknown_returns_none():
    tid = _tid()
    assert store.get_session(tid, "does_not_exist") is None


def test_list_sessions_newest_first():
    tid = _tid()
    for i in range(3):
        store.create_session(tid, f"s_{i}", channel="phone")
    rows = store.list_sessions(tid, limit=50)
    assert len(rows) == 3
    starts = [r["started_at"] for r in rows]
    assert starts == sorted(starts, reverse=True)


# ---------------------------------------------------------------------------
# Commands: create -> update -> list -> get
# ---------------------------------------------------------------------------
def test_command_create_update_list_get():
    tid = _tid()
    sid = "sess_cmd"
    store.create_session(tid, sid)
    cmd_id = store.create_command(tid, session_id=sid, action_type="ads.set_budget",
                                  detected_intent="ads.set_budget", risk_level=3,
                                  status="pending")
    assert cmd_id.startswith("cmd_")
    store.update_command(tid, cmd_id, status="succeeded", pin_verified=True,
                         execution_result={"status": "done"})
    got = store.get_command(tid, cmd_id)
    assert got is not None
    assert got["status"] == "succeeded"
    assert got["pin_verified"] is True
    assert got["execution_result"] == {"status": "done"}
    listed = store.list_commands(tid, session_id=sid)
    assert any(c["id"] == cmd_id and c["status"] == "succeeded" for c in listed)


def test_update_command_unknown_is_noop():
    tid = _tid()
    # no row -> no crash, no creation
    store.update_command(tid, "cmd_nope", status="succeeded")
    assert store.get_command(tid, "cmd_nope") is None


def test_create_command_idempotent_same_key_one_row():
    tid = _tid()
    sid = "sess_idem"
    args = {"budget_minor": 500000}
    key = store.make_idempotency_key(tid, sid, "ads.set_budget", args)
    # the key is stable for identical inputs
    assert key == store.make_idempotency_key(tid, sid, "ads.set_budget", args)
    c1 = store.create_command(tid, session_id=sid, action_type="ads.set_budget",
                              action_payload=args, idempotency_key=key)
    c2 = store.create_command(tid, session_id=sid, action_type="ads.set_budget",
                              action_payload=args, idempotency_key=key)
    assert c1 == c2  # same idem key -> same id
    rows = store.list_commands(tid, session_id=sid)
    assert len([r for r in rows if r["idempotency_key"] == key]) == 1  # exactly ONE row


# ---------------------------------------------------------------------------
# Audit: secret scrubbing + append-only
# ---------------------------------------------------------------------------
def test_record_audit_log_scrubs_secret_metadata():
    tid = _tid()
    aid = store.record_audit_log(
        tid, event_type="execute", severity="info",
        metadata={"pin": "4242", "otp": "999111", "secret": "s", "code": "c",
                  "token": "tok", "step_up_token": "su", "action": "ads.set_budget"})
    assert aid.startswith("aud_")
    rows = store.list_audit(tid)
    assert rows
    meta = rows[0]["metadata"]
    for secret_key in ("pin", "otp", "secret", "code", "token", "step_up_token"):
        assert meta[secret_key] == "***", (secret_key, meta.get(secret_key))
    # a non-secret field passes through untouched
    assert meta["action"] == "ads.set_budget"


def test_audit_is_append_only():
    tid = _tid()
    store.record_audit_log(tid, event_type="call_start")
    store.record_audit_log(tid, event_type="execute")
    store.record_audit_log(tid, event_type="call_end")
    rows = store.list_audit(tid)
    assert len(rows) == 3
    events = {r["event_type"] for r in rows}
    assert events == {"call_start", "execute", "call_end"}
    # no public mutate/delete API exists; a 2nd record only ADDS, never replaces.
    store.record_audit_log(tid, event_type="extra")
    assert len(store.list_audit(tid)) == 4


# ---------------------------------------------------------------------------
# Action runs
# ---------------------------------------------------------------------------
def test_action_run_lifecycle():
    tid = _tid()
    cmd_id = store.create_command(tid, action_type="ads.set_budget")
    run_id = store.create_action_run(tid, command_id=cmd_id, action_type="ads.set_budget",
                                     target_module="ads", status="running",
                                     input={"budget_minor": 500000})
    assert run_id.startswith("run_")
    store.finish_action_run(tid, run_id, status="succeeded", output={"status": "done"})
    runs = store.list_action_runs(tid, command_id=cmd_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["output"] == {"status": "done"}
    assert runs[0]["completed_at"]


# ---------------------------------------------------------------------------
# Dashboard summary — zero-filled (every enum bucket present)
# ---------------------------------------------------------------------------
def test_dashboard_summary_zero_filled_empty_tenant():
    tid = _tid()
    s = store.dashboard_summary(tid)
    assert s["commands"]["total"] == 0
    assert s["sessions"]["total"] == 0
    assert s["action_runs"]["total"] == 0
    assert s["audit"]["total"] == 0
    # every command status bucket present
    for st in ("pending", "needs_confirmation", "needs_pin", "executing",
               "succeeded", "failed", "denied", "cancelled"):
        assert s["commands"]["by_status"][st] == 0
    # every risk-level bucket present
    for lvl in ("0", "1", "2", "3", "4"):
        assert s["commands"]["by_risk_level"][lvl] == 0
    # session/run/audit enum buckets present
    for st in ("active", "completed", "failed", "blocked"):
        assert s["sessions"]["by_status"][st] == 0
    for ch in ("phone", "whatsapp", "dashboard"):
        assert s["sessions"]["by_channel"][ch] == 0
    for st in ("queued", "running", "succeeded", "failed", "retried", "cancelled"):
        assert s["action_runs"]["by_status"][st] == 0
    for sev in ("info", "warn", "error", "critical", "debug"):
        assert s["audit"]["by_severity"][sev] == 0


def test_dashboard_summary_counts_real_rows():
    tid = _tid()
    sid = "sess_dash"
    store.create_session(tid, sid, channel="phone")
    store.end_session(tid, sid, status="completed", n_actions=2)
    cmd = store.create_command(tid, session_id=sid, action_type="ads.set_budget", risk_level=3)
    store.update_command(tid, cmd, status="succeeded", pin_required=True)
    store.record_audit_log(tid, event_type="execute", severity="info")
    s = store.dashboard_summary(tid)
    assert s["commands"]["total"] == 1
    assert s["commands"]["by_status"]["succeeded"] == 1
    assert s["commands"]["by_risk_level"]["3"] == 1
    assert s["commands"]["pin_required"] == 1
    assert s["sessions"]["total"] == 1
    assert s["sessions"]["by_status"]["completed"] == 1
    assert s["sessions"]["total_actions"] == 2
    assert s["audit"]["total"] == 1


# ---------------------------------------------------------------------------
# TENANT ISOLATION — tenant B cannot read tenant A's rows
# ---------------------------------------------------------------------------
def test_tenant_isolation_session():
    a, b = _tid("a"), _tid("b")
    sid = "shared_sid"
    store.create_session(a, sid, channel="phone", caller_phone="+91secretA")
    # tenant B asking for the same session id sees nothing
    assert store.get_session(b, sid) is None
    assert store.list_sessions(b) == []
    # tenant A still sees its own
    assert store.get_session(a, sid) is not None


def test_tenant_isolation_command():
    a, b = _tid("a"), _tid("b")
    cmd = store.create_command(a, action_type="ads.set_budget")
    assert store.get_command(b, cmd) is None
    assert store.list_commands(b) == []
    assert store.get_command(a, cmd) is not None


def test_tenant_isolation_audit_and_runs():
    a, b = _tid("a"), _tid("b")
    store.record_audit_log(a, event_type="execute", message="A only")
    store.create_action_run(a, command_id="c", action_type="ads.set_budget", target_module="ads")
    assert store.list_audit(b) == []
    assert store.list_action_runs(b) == []
    assert store.list_audit(a)
    assert store.list_action_runs(a)


# ---------------------------------------------------------------------------
# Blank-tenant fail-closed
# ---------------------------------------------------------------------------
def test_blank_tenant_fail_closed():
    assert store.create_command("", action_type="ads.set_budget") == ""
    assert store.record_audit_log("", event_type="execute") == ""
    assert store.create_action_run("", command_id="c", action_type="x", target_module="x") == ""
    assert store.list_commands("") == []
    assert store.list_sessions("") == []
    assert store.list_audit("") == []
    assert store.list_action_runs("") == []
    assert store.get_session("", "s") is None
    assert store.get_command("", "c") is None
    # dashboard still returns the zero-filled shape (calm), never a crash
    z = store.dashboard_summary("")
    assert z["commands"]["total"] == 0


# ---------------------------------------------------------------------------
# Profiles + authorized users — no pin_hash ever leaked
# ---------------------------------------------------------------------------
def test_profile_defaults_and_upsert():
    tid = _tid()
    prof = store.get_profile(tid)
    assert prof["vendor_id"] == tid
    assert prof["enabled"] is False
    updated = store.upsert_profile(tid, {"enabled": True, "language_preference": "hi"})
    assert updated["enabled"] is True
    assert updated["language_preference"] == "hi"
    assert store.get_profile(tid)["enabled"] is True


def test_users_never_leak_pin_hash():
    tid = _tid()
    u = store.create_user(tid, {"name": "Ravi", "phone_number": "+919876543210", "role": "manager"})
    assert "pin_hash" not in u
    assert u["has_pin"] is False
    listed = store.list_users(tid)
    assert all("pin_hash" not in row for row in listed)
    got = store.get_user(tid, u["id"])
    assert got is not None and "pin_hash" not in got
    deactivated = store.set_user_active(tid, u["id"], False)
    assert deactivated["is_active"] is False
    # tenant isolation on users too
    other = _tid("b")
    assert store.get_user(other, u["id"]) is None
    assert store.list_users(other) == []
