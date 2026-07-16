"""Offline smoke test for auto_lead (needs fastapi, no PG/leads store).
Run: python3 -m auto_lead._smoke"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .pipeline import extract_candidate, validate
from .store import AutoLeadStore

_fail = 0


def ok(cond, label):
    global _fail
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        _fail += 1


def norm(n: str) -> str:  # mirror caller.py:norm
    d = re.sub(r"\D", "", n or "")
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return "+" + d if len(d) >= 11 else ""


def test_pipeline():
    # flat payload
    c = extract_candidate({"full_name": "Ada Lovelace", "phone": "9876543210", "email": "ada@x.com"})
    ok(c["name"] == "Ada Lovelace" and c["phone"] == "9876543210" and c["email"] == "ada@x.com", "extract flat")
    # first+last
    c = extract_candidate({"first_name": "Grace", "last_name": "Hopper", "mobile": "08123456789"})
    ok(c["name"] == "Grace Hopper" and c["phone"] == "08123456789", "extract first+last + mobile key")
    # explicit mapping (dot path)
    c = extract_candidate({"lead": {"contact": {"cell": "9000000000"}}, "who": "Neo"},
                          {"phone": "lead.contact.cell", "name": "who"})
    ok(c["phone"] == "9000000000" and c["name"] == "Neo", "extract mapping dot-path")
    # Meta Lead Ads field_data
    meta = {"entry": [{"changes": [{"value": {"field_data": [
        {"name": "full_name", "values": ["Trinity"]},
        {"name": "phone_number", "values": ["+91 98765 11111"]},
        {"name": "email", "values": ["t@matrix.io"]}]}}]}]}
    c = extract_candidate(meta)
    ok(c["name"] == "Trinity" and "98765" in c["phone"] and c["email"] == "t@matrix.io", "extract Meta field_data")
    # Google user_column_data
    g = {"user_column_data": [{"column_name": "Full Name", "string_value": "Morpheus"},
                              {"column_name": "Phone Number", "string_value": "9333333333"}]}
    c = extract_candidate(g)
    ok(c["name"] == "Morpheus" and c["phone"] == "9333333333", "extract Google user_column_data")

    ok(validate({"name": "X", "phone": "9876543210"}, {}, norm)[0] is True, "validate ok")
    ok(validate({"name": "X", "phone": "123"}, {"valid_phone_only": True}, norm)[1] == "invalid phone number", "validate bad phone")
    ok(validate({"name": "X"}, {"require_phone": True}, norm)[1] == "missing phone", "validate missing phone")
    ok(validate({"email": "a@b.com"}, {"require_phone": False}, norm)[0] is True, "validate phone-optional")


def test_store():
    with tempfile.TemporaryDirectory() as d:
        s = AutoLeadStore(Path(d))
        rec = s.add_source("t1", {"type": "custom", "name": "Site"})
        ok(rec["token"].startswith("alt_") and rec["id"].startswith("als_"), "store add_source token/id")
        ok(s.find_by_token(rec["token"])[0] == "t1", "store find_by_token")
        ok(s.find_by_token("nope") is None, "store unknown token -> None")
        s.bump_stats("t1", rec["id"], accepted=True, status="accepted")
        ok(s.get_source("t1", rec["id"])["stats"]["accepted"] == 1, "store bump_stats")
        s.add_event("t1", {"source_id": rec["id"], "accepted": True, "name": "A"})
        s.add_event("t1", {"source_id": rec["id"], "accepted": False, "name": "B"})
        ok(len(s.list_events("t1")) == 2, "store events")
        ok(len(s.list_events("t1", status="rejected")) == 1, "store events filter")
        ok(s.update_source("t1", rec["id"], {"enabled": False})["enabled"] is False, "store update")
        ok(s.delete_source("t1", rec["id"]) is True, "store delete")
        ok(s.add_source("t2", {"type": "custom"})["id"] != rec["id"], "store tenant isolation")


def test_router():
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        print("SKIP router (fastapi not installed)")
        return
    from . import build_router

    LEADS: dict = {}

    async def add_lead(tid, lead):
        p = norm(lead.get("phone", ""))
        if not p:
            return {"added": False, "reason": "invalid_phone"}
        book = LEADS.setdefault(tid, {})
        if p in book:
            return {"added": False, "reason": "duplicate", "lead_id": book[p]["id"]}
        lid = f"L{len(book)}"
        book[p] = {"id": lid, **lead, "phone": p}
        return {"added": True, "lead_id": lid}

    def resolve_tenant(request):
        r = request.headers.get("X-Test", "")
        if r == "admin":
            return {"tenant_id": "t-admin", "role": "admin"}
        if r == "agent":
            return {"tenant_id": "t-admin", "role": "agent"}
        return None

    def can(t, a):
        return t.get("role") in ("admin", "manager") if a == "write" else True

    from fastapi.responses import Response, JSONResponse as JR

    def need_auth():
        return Response(status_code=401)

    def forbidden(m="forbidden"):
        return JR({"error": m}, status_code=403)

    with tempfile.TemporaryDirectory() as d:
        app = FastAPI()
        app.include_router(build_router(resolve_tenant, can, need_auth, forbidden,
                                        var_dir=Path(d), add_lead=add_lead, norm=norm))
        cl = TestClient(app)

        ok(cl.get("/auto-lead/sources").status_code == 401, "router: anon -> 401")
        ok(len(cl.get("/auto-lead/types", headers={"X-Test": "admin"}).json()["types"]) >= 6, "router: types catalog")
        ok(cl.post("/auto-lead/sources", headers={"X-Test": "agent"}, json={"type": "custom"}).status_code == 403,
           "router: write-gated create")

        r = cl.post("/auto-lead/sources", headers={"X-Test": "admin"},
                    json={"type": "website", "name": "My Site",
                          "validation": {"require_phone": True, "valid_phone_only": True}})
        src = r.json()["source"]
        token = src["token"]
        ok(r.status_code == 200 and token, "router: create source")
        ok(src["config"] == {} and src["mode"] == "push", "router: source public view")

        # public ingest (no auth) -> creates a lead
        r = cl.post(f"/auto-lead/ingest/{token}", json={"name": "Neo", "phone": "9876543210", "email": "neo@m.io"})
        ok(r.json()["accepted"] is True and r.json()["lead_id"], "router: ingest accepts + routes to leads")
        ok(LEADS["t-admin"]["+919876543210"]["name"] == "Neo", "router: lead landed in leads store")
        # duplicate
        ok(cl.post(f"/auto-lead/ingest/{token}", json={"phone": "9876543210"}).json()["accepted"] is False,
           "router: dedup rejects duplicate")
        # invalid (no phone)
        ok(cl.post(f"/auto-lead/ingest/{token}", json={"name": "NoPhone"}).json()["reason"] == "missing phone",
           "router: validation rejects no-phone")
        # Meta field_data ingest
        meta = {"field_data": [{"name": "full_name", "values": ["Trinity"]},
                               {"name": "phone_number", "values": ["9000000022"]}]}
        ok(cl.post(f"/auto-lead/ingest/{token}", json=meta).json()["accepted"] is True, "router: ingest Meta shape")
        # unknown token
        ok(cl.post("/auto-lead/ingest/bogus", json={"phone": "9"}).status_code == 404, "router: unknown token 404")
        # honeypot
        cl.patch(f"/auto-lead/sources/{src['id']}", headers={"X-Test": "admin"}, json={"honeypot": "website_url"})
        before = len(LEADS.get("t-admin", {}))
        cl.post(f"/auto-lead/ingest/{token}", json={"phone": "9111111111", "website_url": "http://spam"})
        ok(len(LEADS.get("t-admin", {})) == before, "router: honeypot silently drops bot")
        # form-urlencoded ingest
        r = cl.post(f"/auto-lead/ingest/{token}", content="name=Cypher&phone=9222222222",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
        ok(r.json()["accepted"] is True, "router: ingest form-urlencoded")
        # test (dry-run) -> no lead
        cnt = len(LEADS.get("t-admin", {}))
        r = cl.post(f"/auto-lead/sources/{src['id']}/test", headers={"X-Test": "admin"}, json={})
        ok(r.json()["would_accept"] is True and len(LEADS.get("t-admin", {})) == cnt, "router: test is dry-run")
        # feed + overview
        ok(len(cl.get("/auto-lead/feed", headers={"X-Test": "admin"}).json()["events"]) >= 4, "router: feed")
        ov = cl.get("/auto-lead/overview", headers={"X-Test": "admin"}).json()
        ok(ov["total_accepted"] >= 3 and ov["active_sources"] == 1, "router: overview stats")
        # toggle off -> ingest ignored
        cl.patch(f"/auto-lead/sources/{src['id']}", headers={"X-Test": "admin"}, json={"enabled": False})
        ok(cl.post(f"/auto-lead/ingest/{token}", json={"phone": "9444444444"}).json().get("ignored"),
           "router: disabled source ignores ingest")


if __name__ == "__main__":
    test_pipeline()
    test_store()
    test_router()
    print("\n" + ("ALL PASSED" if _fail == 0 else f"{_fail} FAILED"))
    raise SystemExit(1 if _fail else 0)
