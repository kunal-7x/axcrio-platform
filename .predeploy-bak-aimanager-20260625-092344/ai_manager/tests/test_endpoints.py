"""Offline tests for ai_manager.endpoints — drive the FastAPI route functions DIRECTLY (no ASGI,
no caller.py, no network). We fetch each route's .endpoint closure off the router and call it with a
fake Request + a monkeypatched endpoints._resolve_tenant. Calling route fns directly bypasses FastAPI
injection, so EVERY Query() default arrives as a FieldInfo — we therefore pass real string/int values
for every Query param. Run:
    cd droplet_work && python -m pytest ai_manager/tests/test_endpoints.py -q
"""
from __future__ import annotations

import os
import uuid

import pytest

from ai_manager import endpoints, store

# FastAPI must be present for the router to exist (it is in this env).
pytestmark = pytest.mark.skipif(endpoints.router is None, reason="FastAPI absent")


# ---------------------------------------------------------------------------
# harness — fetch a route closure by function name, a fake Request, a tenant pin
# ---------------------------------------------------------------------------
def _ep(name: str):
    for r in endpoints.router.routes:
        if r.endpoint.__name__ == name:
            return r.endpoint
    raise KeyError(name)


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def _pin_tenant(monkeypatch, tenant_id: str, role: str = "manager", is_admin: bool = False):
    """Monkeypatch _resolve_tenant to return a fixed authenticated tenant dict."""
    tenant = {"tenant_id": tenant_id, "role": role}
    if is_admin:
        tenant["is_admin"] = True
    monkeypatch.setattr(endpoints, "_resolve_tenant", lambda req: tenant)
    return tenant


def _tid(prefix: str = "t") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _no_pin_hash_anywhere(obj) -> bool:
    """Recursively assert no 'pin_hash' key appears in a response payload."""
    if isinstance(obj, dict):
        if "pin_hash" in obj:
            return False
        return all(_no_pin_hash_anywhere(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_pin_hash_anywhere(v) for v in obj)
    return True


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------
def test_status(monkeypatch):
    _pin_tenant(monkeypatch, _tid())
    out = _ep("status")(FakeRequest())
    assert out["module"] == "ai_manager"
    # snapshot is booleans-only, no secrets
    assert out["feature"] is False
    assert "has_service_token" in out


# ---------------------------------------------------------------------------
# /commands (history)
# ---------------------------------------------------------------------------
def test_list_commands_history(monkeypatch):
    tid = _tid()
    _pin_tenant(monkeypatch, tid)
    sid = "sess_ep"
    store.create_session(tid, sid)
    cid = store.create_command(tid, session_id=sid, action_type="ads.set_budget",
                               raw_text="set ads budget to 5000", detected_intent="ads.set_budget",
                               risk_level=3, status="succeeded")
    out = _ep("list_commands")(FakeRequest(), status="", channel="", risk="", action_type="",
                               session_id="", user="", module="", q="")
    assert out["total"] >= 1
    assert any(c.get("command_id") == cid or c.get("id") == cid for c in out["commands"])
    # filter by a non-matching status -> empty
    out2 = _ep("list_commands")(FakeRequest(), status="denied", channel="", risk="",
                                action_type="", session_id="", user="", module="", q="")
    assert all(c.get("status") != "succeeded" for c in out2["commands"])


# ---------------------------------------------------------------------------
# /dashboard/summary
# ---------------------------------------------------------------------------
def test_dashboard_summary(monkeypatch):
    tid = _tid()
    _pin_tenant(monkeypatch, tid)
    store.create_command(tid, action_type="ads.set_budget", risk_level=3, status="succeeded")
    out = _ep("dashboard_summary")(FakeRequest())
    assert out["commands_today"] >= 1
    assert out["commands_succeeded"] >= 1
    assert "recent_sessions" in out and isinstance(out["recent_sessions"], list)
    assert "recent_risky" in out and isinstance(out["recent_risky"], list)


# ---------------------------------------------------------------------------
# /audit-logs
# ---------------------------------------------------------------------------
def test_audit_logs(monkeypatch):
    tid = _tid()
    _pin_tenant(monkeypatch, tid)
    store.record_audit_log(tid, event_type="execute", message="did a thing",
                           metadata={"pin": "4242", "action": "ads.set_budget"})
    out = _ep("audit_logs")(FakeRequest(), session_id="", command_id="", limit=200)
    assert len(out["logs"]) >= 1
    # secret-shaped metadata was scrubbed at the store layer.
    log = out["logs"][0]
    assert log["metadata"].get("pin") == "***"
    assert log["metadata"].get("action") == "ads.set_budget"


# ---------------------------------------------------------------------------
# /action-runs
# ---------------------------------------------------------------------------
def test_action_runs(monkeypatch):
    tid = _tid()
    _pin_tenant(monkeypatch, tid)
    cid = store.create_command(tid, action_type="ads.set_budget")
    run = store.create_action_run(tid, command_id=cid, action_type="ads.set_budget",
                                  target_module="ads", status="running")
    store.finish_action_run(tid, run, status="succeeded", output={"status": "done"})
    out = _ep("action_runs")(FakeRequest(), command_id="", session_id="", limit=200)
    assert len(out["runs"]) >= 1
    assert any(r["status"] == "succeeded" for r in out["runs"])


# ---------------------------------------------------------------------------
# /profile  (get + put)
# ---------------------------------------------------------------------------
def test_profile_get_and_put(monkeypatch):
    tid = _tid()
    _pin_tenant(monkeypatch, tid)
    got = _ep("get_profile")(FakeRequest())
    assert got["vendor_id"] == tid
    assert got["enabled"] is False
    put = _ep("put_profile")(FakeRequest(), body={"enabled": True, "language_preference": "hi"})
    assert put["ok"] is True
    assert put["enabled"] is True
    # the change persisted
    again = _ep("get_profile")(FakeRequest())
    assert again["enabled"] is True
    assert again["language_preference"] == "hi"


# ---------------------------------------------------------------------------
# /authorized-users CRUD — NO pin_hash in any response
# ---------------------------------------------------------------------------
def test_authorized_users_crud_no_pin_hash(monkeypatch):
    tid = _tid()
    _pin_tenant(monkeypatch, tid, role="admin", is_admin=True)
    created = _ep("create_user")(FakeRequest(),
                                 body={"name": "Ravi", "phone_number": "+919876543210",
                                       "role": "manager"})
    assert created["ok"] is True
    assert _no_pin_hash_anywhere(created)
    assert created["has_pin"] is False
    uid = created["id"]
    # list is dormant-safe (store.available() False offline -> calm empty list, NO crash, no leak)
    listed = _ep("list_users")(FakeRequest())
    assert "users" in listed and isinstance(listed["users"], list)
    assert _no_pin_hash_anywhere(listed)
    # patch
    patched = _ep("patch_user")(FakeRequest(), user_id=uid, body={"name": "Ravi K"})
    assert patched["name"] == "Ravi K"
    assert _no_pin_hash_anywhere(patched)
    # delete (soft) -> ok
    deleted = _ep("delete_user")(FakeRequest(), user_id=uid)
    assert deleted["ok"] is True


# ---------------------------------------------------------------------------
# CROSS-TENANT ISOLATION — tenant B sees 0 of tenant A's rows
# ---------------------------------------------------------------------------
def test_cross_tenant_isolation(monkeypatch):
    a = _tid("a")
    b = _tid("b")
    # seed tenant A with a command, audit row, action run.
    sid = "sess_iso"
    store.create_session(a, sid)
    cid = store.create_command(a, session_id=sid, action_type="ads.set_budget", status="succeeded")
    store.record_audit_log(a, event_type="execute", command_id=cid)
    store.create_action_run(a, command_id=cid, action_type="ads.set_budget", target_module="ads")

    # tenant A sees them.
    _pin_tenant(monkeypatch, a)
    assert _ep("list_commands")(FakeRequest(), status="", channel="", risk="", action_type="",
                                session_id="", user="", module="", q="")["total"] >= 1
    assert len(_ep("audit_logs")(FakeRequest(), session_id="", command_id="", limit=200)["logs"]) >= 1
    assert len(_ep("action_runs")(FakeRequest(), command_id="", session_id="",
                                  limit=200)["runs"]) >= 1

    # tenant B sees NONE of tenant A's rows.
    _pin_tenant(monkeypatch, b)
    assert _ep("list_commands")(FakeRequest(), status="", channel="", risk="", action_type="",
                                session_id="", user="", module="", q="")["total"] == 0
    assert _ep("audit_logs")(FakeRequest(), session_id="", command_id="", limit=200)["logs"] == []
    assert _ep("action_runs")(FakeRequest(), command_id="", session_id="", limit=200)["runs"] == []
    # B's command-by-id read of A's command 404s (raises HTTPException) — RLS at the get path.
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _ep("get_command")(FakeRequest(), command_id=cid)
    assert ei.value.status_code == 404


# ---------------------------------------------------------------------------
# SERVICE-TOKEN endpoint — /numbers/lookup 401 when AIM_SERVICE_TOKEN unset
# ---------------------------------------------------------------------------
def test_lookup_number_401_without_service_token(monkeypatch):
    # ensure the service token is UNSET -> the service-token gate is dormant -> 401.
    monkeypatch.delenv("AIM_SERVICE_TOKEN", raising=False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _ep("lookup_number")(FakeRequest(headers={}), phone="+919876543210")
    assert ei.value.status_code == 401


def test_ship_session_401_without_service_token(monkeypatch):
    monkeypatch.delenv("AIM_SERVICE_TOKEN", raising=False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _ep("ship_session")(FakeRequest(headers={}), body={"session_id": "x"})
    assert ei.value.status_code == 401


def test_lookup_number_accepts_valid_service_token(monkeypatch):
    # with the token set + presented, the gate passes; an unknown phone still 404s (reveals nothing).
    tok = "svc_" + uuid.uuid4().hex
    monkeypatch.setenv("AIM_SERVICE_TOKEN", tok)
    req = FakeRequest(headers={"authorization": "Bearer " + tok})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _ep("lookup_number")(req, phone="+910000009999")  # not registered
    assert ei.value.status_code == 404  # past the auth gate, into not_registered
