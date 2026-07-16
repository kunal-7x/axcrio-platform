"""Offline smoke test for the fastapi-independent core of twenty_crm.

Run: python3 -m twenty_crm._smoke   (needs only httpx, no fastapi/PG)
Exercises: normalizers round-trip, client envelope unwrapping, the per-tenant
store (set/resolve/status/delete + masking + env fallback), and the async
TwentyClient against a mocked Twenty server (httpx.MockTransport)."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx

from . import client as C
from . import normalize as N
from .store import TwentyStore

_fail = 0


def ok(cond, label):
    global _fail
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        _fail += 1


# ── normalizers ──────────────────────────────────────────────────────────────
def test_normalize():
    person = {
        "id": "p1",
        "name": {"firstName": "Ada", "lastName": "Lovelace"},
        "emails": {"primaryEmail": "ada@acme.com"},
        "phones": {"primaryPhoneNumber": "+15551234"},
        "jobTitle": "CTO", "city": "London",
        "company": {"id": "c1", "name": "Acme"},
        "companyId": "c1",
    }
    flat = N.person_out(person)
    ok(flat["name"] == "Ada Lovelace", "person_out joins name")
    ok(flat["email"] == "ada@acme.com" and flat["phone"] == "+15551234", "person_out email/phone")
    ok(flat["companyName"] == "Acme", "person_out company relation")

    body = N.person_in({"name": "Grace Hopper", "email": "g@navy.mil", "phone": "123", "companyId": "c1"})
    ok(body["name"] == {"firstName": "Grace", "lastName": "Hopper"}, "person_in splits name")
    ok(body["emails"] == {"primaryEmail": "g@navy.mil"}, "person_in emails composite")
    ok(body["phones"] == {"primaryPhoneNumber": "123"}, "person_in phones composite")

    comp = {"id": "c1", "name": "Acme", "domainName": {"primaryLinkUrl": "acme.com"},
            "address": {"addressCity": "NY"}, "people": [1, 2, 3]}
    cf = N.company_out(comp)
    ok(cf["domain"] == "acme.com" and cf["city"] == "NY", "company_out links/address")
    ok(cf["peopleCount"] == 3, "company_out relation count")
    ok(N.company_in({"name": "X", "domain": "x.io"})["domainName"] == {"primaryLinkUrl": "x.io"},
       "company_in domain composite")

    opp = {"id": "o1", "name": "Big deal", "stage": "PROPOSAL",
           "amount": {"amountMicros": 5000000000000, "currencyCode": "USD"},
           "company": {"id": "c1", "name": "Acme"},
           "pointOfContact": {"id": "p1", "name": {"firstName": "Ada", "lastName": "L"}}}
    of = N.opportunity_out(opp)
    ok(of["amount"] == 5_000_000.0, "opportunity_out micros->major")
    ok(of["stage"] == "PROPOSAL" and of["companyName"] == "Acme", "opportunity_out stage/company")
    ok(of["pointOfContactName"] == "Ada L", "opportunity_out poc name")
    ob = N.opportunity_in({"name": "D", "stage": "NEW", "amount": 2500, "currencyCode": "INR"})
    ok(ob["amount"] == {"amountMicros": 2_500_000_000, "currencyCode": "INR"}, "opportunity_in major->micros")

    note = {"id": "n1", "title": "Hi", "bodyV2": {"markdown": "**bold**"}}
    ok(N.note_out(note)["body"] == "**bold**", "note_out bodyV2 markdown")
    ok(N.note_out({"id": "n2", "title": "X", "body": "plain"})["body"] == "plain", "note_out legacy body")


# ── envelope unwrapping ──────────────────────────────────────────────────────
def test_envelope():
    a = {"data": {"people": [{"id": "1"}]}, "totalCount": 1, "pageInfo": {"hasNextPage": False}}
    recs, page = C.TwentyClient._unwrap_list(a, "people")
    ok(recs == [{"id": "1"}] and page["totalCount"] == 1, "unwrap_list data.plural")
    recs, _ = C.TwentyClient._unwrap_list({"people": [{"id": "2"}]}, "people")
    ok(recs == [{"id": "2"}], "unwrap_list bare plural")
    recs, _ = C.TwentyClient._unwrap_list([{"id": "3"}], "people")
    ok(recs == [{"id": "3"}], "unwrap_list bare array")
    one = C.TwentyClient._unwrap_one({"data": {"person": {"id": "9"}}}, "people")
    ok(one == {"id": "9"}, "unwrap_one data.singular")
    one = C.TwentyClient._unwrap_one({"data": {"id": "10"}}, "people")
    ok(one == {"id": "10"}, "unwrap_one bare record")


# ── store ────────────────────────────────────────────────────────────────────
def test_store():
    with tempfile.TemporaryDirectory() as d:
        s = TwentyStore(Path(d))
        ok(s.status("t1")["connected"] is False, "store empty -> disconnected")
        ok(s.resolve("t1") is None, "store empty -> resolve None")
        s.set("t1", "https://acme.twenty.com/", "secretkey1234", when="2026-06-23")
        st = s.status("t1")
        ok(st["connected"] and st["key_masked"] == "••••1234", "store status masks key")
        ok("secretkey" not in json.dumps(st), "store status never leaks key")
        ok(s.resolve("t1")["api_key"] == "secretkey1234", "store resolve returns real key")
        ok(s.resolve("t2") is None, "store per-tenant isolation")
        s.delete("t1")
        ok(s.status("t1")["connected"] is False, "store delete works")
        # env fallback
        s2 = TwentyStore(Path(d), env_url="https://env.twenty.com", env_key="envkeyABCD")
        ok(s2.resolve("anyone")["source"] == "env", "store env fallback resolves")
        ok(s2.status("anyone")["source"] == "env", "store env fallback status")


# ── client against a mocked Twenty ───────────────────────────────────────────
def _mock_twenty(request: httpx.Request) -> httpx.Response:
    auth = request.headers.get("Authorization", "")
    if auth != "Bearer good-key":
        return httpx.Response(401, json={"messages": ["Invalid token"]})
    path = request.url.path
    if path == "/rest/companies" and request.method == "GET":
        return httpx.Response(200, json={"data": {"companies": [
            {"id": "c1", "name": "Acme", "domainName": {"primaryLinkUrl": "acme.com"}}]},
            "totalCount": 1, "pageInfo": {"hasNextPage": False}})
    if path == "/rest/people" and request.method == "POST":
        body = json.loads(request.content)
        return httpx.Response(201, json={"data": {"person": {"id": "p9", **body}}})
    if path == "/rest/opportunities/o1" and request.method == "PATCH":
        body = json.loads(request.content)
        return httpx.Response(200, json={"data": {"opportunity": {"id": "o1", **body}}})
    if path == "/rest/opportunities" and request.method == "POST":
        body = json.loads(request.content)
        return httpx.Response(201, json={"data": {"opportunity": {"id": "o-new", **body}}})
    if path == "/rest/people" and request.method == "GET":
        return httpx.Response(200, json={"data": {"people": []}})  # no dup -> create path
    if path == "/rest/metadata/objects":
        return httpx.Response(200, json={"data": {"objects": [
            {"nameSingular": "opportunity", "fields": [
                {"name": "stage", "options": [
                    {"value": "NEW", "label": "New"}, {"value": "WON", "label": "Won"}]}]}]}})
    return httpx.Response(404, json={"messages": ["nope"]})


def test_client():
    # Inject the mock transport by wrapping httpx.AsyncClient construction.
    orig = httpx.AsyncClient
    transport = httpx.MockTransport(_mock_twenty)

    def patched(*a, **k):
        k["transport"] = transport
        return orig(*a, **k)

    C.httpx.AsyncClient = patched  # type: ignore
    try:
        async def run():
            cl = C.TwentyClient("https://acme.twenty.com/rest", "good-key")
            recs, page = await cl.list("companies")
            ok(recs and recs[0]["name"] == "Acme", "client.list parses records")
            person = await cl.create("people", {"name": {"firstName": "A", "lastName": "B"}})
            ok(person["id"] == "p9", "client.create returns record")
            opp = await cl.update("opportunities", "o1", {"stage": "WON"})
            ok(opp["stage"] == "WON", "client.update (stage move) works")
            stages = await cl.opportunity_stages()
            ok([s["value"] for s in stages] == ["NEW", "WON"], "client reads live stages from metadata")
            ping = await cl.ping()
            ok(ping["ok"] is True, "client.ping ok with good key")
            bad = await C.TwentyClient("https://x/rest", "bad").ping()
            ok(bad["ok"] is False and bad["status"] == 401, "client.ping flags bad key (401)")
        asyncio.run(run())
    finally:
        C.httpx.AsyncClient = orig  # type: ignore


def test_stage_map():
    try:
        from .router import _map_stage  # imports fastapi; skip cleanly if absent
    except ImportError:
        print("SKIP stage map (fastapi not installed in this shell)")
        return
    vals = ["NEW", "SCREENING", "MEETING", "PROPOSAL", "CUSTOMER"]
    ok(_map_stage("won", vals) == "CUSTOMER", "stage map won->CUSTOMER")
    ok(_map_stage("qualified", vals) == "MEETING", "stage map qualified->MEETING")
    ok(_map_stage("", vals) == "NEW", "stage map default->first")


def test_ssrf():
    try:
        from .router import _check_base_url  # imports fastapi; skip if absent
    except ImportError:
        print("SKIP ssrf (fastapi not installed in this shell)")
        return
    ok(_check_base_url("http://169.254.169.254/latest/meta-data/")[0] is False, "ssrf blocks cloud metadata IP")
    ok(_check_base_url("http://127.0.0.1:3000")[0] is False, "ssrf blocks loopback")
    ok(_check_base_url("http://10.0.0.5")[0] is False, "ssrf blocks RFC1918")
    ok(_check_base_url("ftp://twenty.com")[0] is False, "ssrf blocks non-http scheme")
    ok(_check_base_url("")[0] is False, "ssrf blocks empty")
    ok(_check_base_url("https://twenty.com")[0] is True, "ssrf allows a public host")


def test_router():
    """Build the router with stub auth deps and drive it through FastAPI's
    TestClient against the mocked Twenty — validates dormant, connect, write-gating
    and a CRUD path end to end."""
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        print("SKIP router (fastapi not installed in this shell)")
        return
    from . import build_router

    # Stub injected auth deps. X-Test: 'admin' (write) | 'agent' (read) | absent (anon)
    def resolve_tenant(request):
        role = request.headers.get("X-Test", "")
        if role == "admin":
            return {"tenant_id": "t-admin", "role": "admin"}
        if role == "agent":
            return {"tenant_id": "t-admin", "role": "agent"}
        return None

    def can(t, action):
        return t.get("role") in ("admin", "manager") if action == "write" else True

    from fastapi.responses import Response, JSONResponse as JR

    def need_auth():
        return Response(status_code=401)

    def forbidden(msg="forbidden"):
        return JR({"error": msg}, status_code=403)

    orig = httpx.AsyncClient
    transport = httpx.MockTransport(_mock_twenty)

    def patched(*a, **k):
        k["transport"] = transport
        return orig(*a, **k)

    C.httpx.AsyncClient = patched  # type: ignore
    try:
        with tempfile.TemporaryDirectory() as d:
            app = FastAPI()
            app.include_router(build_router(resolve_tenant, can, need_auth, forbidden, var_dir=Path(d)))
            cl = TestClient(app)

            ok(cl.get("/twenty/status").status_code == 401, "router: anon status -> 401")
            r = cl.get("/twenty/status", headers={"X-Test": "admin"})
            ok(r.status_code == 200 and r.json()["connected"] is False, "router: dormant status 200")
            r = cl.get("/twenty/companies", headers={"X-Test": "admin"})
            ok(r.json() == {"connected": False, "companies": [], "total": 0}, "router: dormant companies safe")

            # read-only tenant cannot connect
            ok(cl.post("/twenty/connect", headers={"X-Test": "agent"},
                       json={"base_url": "x", "api_key": "y"}).status_code == 403,
               "router: write-gating on connect (403)")

            # connect with good key (ping hits mocked /rest/companies)
            r = cl.post("/twenty/connect", headers={"X-Test": "admin"},
                        json={"base_url": "https://acme.twenty.com", "api_key": "good-key"})
            ok(r.status_code == 200 and r.json()["connected"] is True, "router: connect succeeds + masks")
            ok("good-key" not in r.text, "router: connect never echoes key")

            # bad key rejected at connect
            ok(cl.post("/twenty/connect", headers={"X-Test": "admin"},
                       json={"base_url": "https://x", "api_key": "bad"}).status_code == 400,
               "router: bad key rejected at connect")

            # SSRF: a private/internal base_url is refused BEFORE any probe/persist,
            # and must NOT overwrite the already-good connection.
            r = cl.post("/twenty/connect", headers={"X-Test": "admin"},
                        json={"base_url": "http://169.254.169.254", "api_key": "good-key"})
            ok(r.status_code == 400 and "private" in r.text.lower(), "router: SSRF blocks internal base_url")
            ok("169.254" not in cl.get("/twenty/status", headers={"X-Test": "admin"}).json()["base_url"],
               "router: SSRF-blocked URL was never persisted")

            # now connected -> real data flows
            r = cl.get("/twenty/companies", headers={"X-Test": "admin"})
            ok(r.json()["connected"] and r.json()["companies"][0]["name"] == "Acme",
               "router: companies list flows after connect")
            r = cl.post("/twenty/people", headers={"X-Test": "admin"},
                        json={"name": "Ada Lovelace", "email": "ada@acme.com"})
            ok(r.json()["ok"] and r.json()["record"]["id"] == "p9", "router: create person")
            r = cl.patch("/twenty/opportunities/o1", headers={"X-Test": "admin"},
                         json={"stage": "WON"})
            ok(r.json()["record"]["stage"] == "WON", "router: stage move (kanban drag)")
            r = cl.get("/twenty/meta/stages", headers={"X-Test": "admin"})
            ok([s["value"] for s in r.json()["stages"]] == ["NEW", "WON"], "router: live stages")

            # value bridge: import a lead whose company name has filter metacharacters
            # (the dedup filter must be sanitized, not 400 -> duplicate)
            r = cl.post("/twenty/sync/leads", headers={"X-Test": "admin"},
                        json={"leads": [{"name": "Ada Lovelace", "phone": "+91 (98) 765",
                                         "company": "Smith, Jones (LLC)", "status": "won"}],
                              "create_opportunity": True})
            jr = r.json()
            ok(jr.get("ok") and jr.get("imported") == 1, "router: sync/leads imports (sanitized filter, no 400)")

            # disconnect
            ok(cl.post("/twenty/disconnect", headers={"X-Test": "admin"}).json()["connected"] is False,
               "router: disconnect")
    finally:
        C.httpx.AsyncClient = orig  # type: ignore


if __name__ == "__main__":
    test_normalize()
    test_envelope()
    test_store()
    test_client()
    test_stage_map()
    test_ssrf()
    test_router()
    print("\n" + ("ALL PASSED" if _fail == 0 else f"{_fail} FAILED"))
    raise SystemExit(1 if _fail else 0)
