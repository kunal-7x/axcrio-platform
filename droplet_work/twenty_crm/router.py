"""
twenty_crm.router — Haptica's server-side surface over a tenant's Twenty CRM.

Built with the house ``build_router(resolve_tenant, can, need_auth, forbidden)``
pattern (same shape as forms-surveys / workflow-studio). The browser only ever
talks to ``/twenty/*`` on the Haptica API — never to Twenty directly — so:
  * the workspace API key stays server-side (never shipped to the client),
  * there is no cross-origin / iframe coupling,
  * the panel renders native Haptica UI over a normalized contract.

Tenant isolation: the connection (URL + key) is resolved per tenant from
``resolve_tenant(request)["tenant_id"]`` via the injected store — never a
body/query field. Writes require ``can(t, "write")``. Reads are dormant-safe:
with no connection they return ``{connected: false}`` + empty collections (200),
so the panel shows a calm "Connect your Twenty CRM" state, never an error wall.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# SSRF guard for the TENANT-supplied workspace URL. /twenty/connect lets an authed
# user hand us an arbitrary base_url the server then fetches (carrying their key) —
# the same BYO-endpoint vector trunk_registry/provider_registry already gate. Reuse
# the house guard; if it's somehow absent, fall back to a stdlib resolve+denylist
# (see _check_base_url). Import-guarded so a missing module can't break startup.
try:
    from provider_registry.ssrf_guard import validate_endpoint as _ssrf_validate
except Exception:  # noqa: BLE001
    _ssrf_validate = None

from .client import TwentyClient, TwentyError, gather_limited, DEFAULT_STAGES
from .normalize import (
    company_in, company_out, note_out, opportunity_in, opportunity_out,
    person_in, person_out, task_out,
)
from .store import TwentyStore
from .provision import provision_workspace, purge_seed_data, ProvisionError

# noteTarget / taskTarget FK field for each record type we can attach activity to.
_TARGET_FK = {"company": "companyId", "person": "personId", "opportunity": "opportunityId"}

# Haptica lead lifecycle/status keyword -> a Twenty stage *rank* preference. We map
# against whatever stage VALUES the live workspace exposes (first match wins), so a
# renamed/custom pipeline still gets a sensible default.
_STAGE_HINTS = [
    (("won", "customer", "closed_won", "converted"), ("CUSTOMER", "WON", "CLOSED")),
    (("booked", "proposal", "negotiation"), ("PROPOSAL", "NEGOTIATION")),
    (("qualified", "meeting", "demo"), ("MEETING", "QUALIFIED")),
    (("contacted", "engaged", "screening"), ("SCREENING", "CONTACTED")),
    (("new", "lead"), ("NEW", "LEAD")),
]


def build_router(resolve_tenant, can, need_auth, forbidden, *,
                 var_dir, env_url: str = "", env_key: str = "",
                 self_host: bool = False, internal_url: str = "",
                 provision_domain: str = "crm.haptica.local", provision_secret: str = ""):
    store = TwentyStore(var_dir, env_url=env_url, env_key=env_key)
    router = APIRouter()
    # one provisioning lock per tenant (prevents a double-provision race when two
    # tabs/users open Sales CRM at once and both trigger auto-setup).
    _provision_locks: dict[str, "asyncio.Lock"] = {}

    # ── small helpers (closures over injected deps) ───────────────────────────
    def _tenant(request: Request):
        return resolve_tenant(request)

    def _client_for(t) -> TwentyClient | None:
        conn = store.resolve(t["tenant_id"])
        if not conn:
            return None
        return TwentyClient(conn["base_url"], conn["api_key"])

    def _err(e: TwentyError) -> JSONResponse:
        # Pass client-meaningful codes through; collapse transport/5xx to 502.
        code = e.status if e.status in (400, 401, 403, 404, 409, 429) else 502
        return JSONResponse({"error": e.message, "twenty_status": e.status}, status_code=code)

    async def _json_body(request: Request) -> dict | JSONResponse:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        return body

    async def _safe_list(client: TwentyClient, plural: str, **kw):
        """List with a graceful retry: if a server-side filter is rejected (400),
        retry unfiltered so search degrades to 'show all' instead of erroring."""
        try:
            return await client.list(plural, **kw)
        except TwentyError as e:
            if e.status == 400 and kw.get("filter"):
                kw.pop("filter", None)
                return await client.list(plural, **kw)
            raise

    def _esc(q: str) -> str:
        # Keep a search term from altering the colon-form filter expression: drop the
        # structural metacharacters Twenty's parser uses ( , ( ) [ ] : ). The query
        # only ever hits the tenant's OWN workspace with their OWN key, so this is
        # defense-in-depth (a clean query), not a cross-tenant boundary.
        out = q or ""
        for ch in (",", "(", ")", "[", "]", ":"):
            out = out.replace(ch, " ")
        return out.strip()

    # ── connection lifecycle ──────────────────────────────────────────────────
    @router.get("/twenty/status")
    async def status(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        # self_host=True tells the panel to auto-provision (no API-key form). It is
        # only "true" when both the flag and the internal URL are configured.
        return JSONResponse({
            **store.status(t["tenant_id"]),
            "can_write": bool(can(t, "write")),
            "self_host": bool(self_host and internal_url),
        })

    @router.post("/twenty/provision")
    async def provision(request: Request):
        """Zero-touch: create (or return) this tenant's OWN isolated self-hosted
        Twenty workspace + mint its API key. Idempotent + per-tenant locked."""
        t = _tenant(request)
        if not t:
            return need_auth()
        if not (self_host and internal_url):
            return JSONResponse({"error": "self-hosted CRM is not enabled"}, status_code=400)
        tid = t["tenant_id"]
        # already provisioned/connected -> just report status (idempotent, no gate)
        if store.resolve(tid):
            return JSONResponse({"ok": True, **store.status(tid), "self_host": True})
        if not can(t, "write"):
            return forbidden("CRM setup needs an admin or manager")
        lock = _provision_locks.setdefault(tid, asyncio.Lock())
        async with lock:
            if store.resolve(tid):  # re-check after acquiring the lock
                return JSONResponse({"ok": True, **store.status(tid), "self_host": True})
            display = str(t.get("name") or t.get("tenant_name") or "Sales CRM")
            try:
                res = await provision_workspace(
                    internal_url, tenant_id=tid, secret=provision_secret,
                    domain=provision_domain, display_name=display)
            except ProvisionError as e:
                code = 507 if e.capacity else 502
                return JSONResponse({"error": e.message, "capacity": e.capacity}, status_code=code)
            # start the client on an EMPTY CRM (drop Twenty's demo seed records)
            try:
                await purge_seed_data(internal_url, res["api_key"])
            except Exception:  # noqa: BLE001
                pass
            store.set(tid, internal_url, res["api_key"],
                      when=datetime.now(timezone.utc).isoformat(), source="self_host",
                      workspace_id=res.get("workspace_id"), email=res.get("email"))
            return JSONResponse({"ok": True, **store.status(tid), "self_host": True})

    @router.post("/twenty/connect")
    async def connect(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        base_url = str(body.get("base_url") or "").strip()
        api_key = str(body.get("api_key") or "").strip()
        if not base_url or not api_key:
            return JSONResponse({"error": "base_url and api_key are required"}, status_code=400)
        # SSRF GATE (before any outbound fetch / persist): the URL is attacker-
        # controllable, so reject non-http(s) schemes and any host that resolves to a
        # private / loopback / link-local / metadata address. DNS is blocking → thread.
        ok_url, why = await asyncio.to_thread(_check_base_url, base_url)
        if not ok_url:
            return JSONResponse({"error": why}, status_code=400)
        # Verify the credentials before persisting, so a bad URL/key fails loud.
        probe = await TwentyClient(base_url, api_key).ping()
        if not probe.get("ok"):
            return JSONResponse(
                {"error": probe.get("error") or "Could not connect to Twenty with those details",
                 "twenty_status": probe.get("status")},
                status_code=400,
            )
        store.set(t["tenant_id"], base_url, api_key,
                  when=datetime.now(timezone.utc).isoformat())
        return JSONResponse({"ok": True, **store.status(t["tenant_id"])})

    @router.post("/twenty/disconnect")
    async def disconnect(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        store.delete(t["tenant_id"])
        return JSONResponse({"ok": True, **store.status(t["tenant_id"])})

    @router.get("/twenty/meta/stages")
    async def meta_stages(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"connected": False, "stages": list(DEFAULT_STAGES)})
        stages = await client.opportunity_stages()
        return JSONResponse({"connected": True, "stages": stages})

    # ── companies ─────────────────────────────────────────────────────────────
    @router.get("/twenty/companies")
    async def companies_list(request: Request, q: str = "", limit: int = 40, cursor: str = ""):
        t = _tenant(request)
        if not t:
            return need_auth()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"connected": False, "companies": [], "total": 0})
        filt = f"name[ilike]:%{_esc(q)}%" if q.strip() else None
        try:
            recs, page = await _safe_list(client, "companies", filter=filt,
                                          order_by="createdAt[DescNullsLast]",
                                          limit=limit, depth=1, starting_after=cursor or None)
        except TwentyError as e:
            return _err(e)
        return JSONResponse({
            "connected": True,
            "companies": [company_out(r) for r in recs],
            "total": page.get("totalCount"),
            "next_cursor": (page.get("pageInfo") or {}).get("endCursor")
            if (page.get("pageInfo") or {}).get("hasNextPage") else None,
        })

    @router.post("/twenty/companies")
    async def companies_create(request: Request):
        return await _create_record(request, "companies", company_in, company_out)

    @router.get("/twenty/companies/{rec_id}")
    async def companies_get(request: Request, rec_id: str):
        return await _record_detail(request, "companies", company_out, rec_id, with_relations=True)

    @router.patch("/twenty/companies/{rec_id}")
    async def companies_update(request: Request, rec_id: str):
        return await _update_record(request, "companies", company_in, company_out, rec_id)

    @router.delete("/twenty/companies/{rec_id}")
    async def companies_delete(request: Request, rec_id: str):
        return await _delete_record(request, "companies", rec_id)

    # ── people ────────────────────────────────────────────────────────────────
    @router.get("/twenty/people")
    async def people_list(request: Request, q: str = "", limit: int = 40, cursor: str = ""):
        t = _tenant(request)
        if not t:
            return need_auth()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"connected": False, "people": [], "total": 0})
        qq = _esc(q)
        filt = (f"or(name.firstName[ilike]:%{qq}%,name.lastName[ilike]:%{qq}%,"
                f"emails.primaryEmail[ilike]:%{qq}%,phones.primaryPhoneNumber[ilike]:%{qq}%)"
                ) if qq else None
        try:
            recs, page = await _safe_list(client, "people", filter=filt,
                                          order_by="createdAt[DescNullsLast]",
                                          limit=limit, depth=1, starting_after=cursor or None)
        except TwentyError as e:
            return _err(e)
        return JSONResponse({
            "connected": True,
            "people": [person_out(r) for r in recs],
            "total": page.get("totalCount"),
            "next_cursor": (page.get("pageInfo") or {}).get("endCursor")
            if (page.get("pageInfo") or {}).get("hasNextPage") else None,
        })

    @router.post("/twenty/people")
    async def people_create(request: Request):
        return await _create_record(request, "people", person_in, person_out)

    @router.get("/twenty/people/{rec_id}")
    async def people_get(request: Request, rec_id: str):
        return await _record_detail(request, "people", person_out, rec_id, with_relations=True)

    @router.patch("/twenty/people/{rec_id}")
    async def people_update(request: Request, rec_id: str):
        return await _update_record(request, "people", person_in, person_out, rec_id)

    @router.delete("/twenty/people/{rec_id}")
    async def people_delete(request: Request, rec_id: str):
        return await _delete_record(request, "people", rec_id)

    # ── opportunities (+ kanban grouping) ─────────────────────────────────────
    @router.get("/twenty/opportunities")
    async def opportunities_list(request: Request, q: str = "", group: str = "",
                                 limit: int = 50, cursor: str = ""):
        t = _tenant(request)
        if not t:
            return need_auth()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"connected": False, "opportunities": [], "stages": list(DEFAULT_STAGES)})

        # Kanban view: one balanced column per live stage (parallel, capped).
        if group == "stage":
            stages = await client.opportunity_stages()

            async def _col(stage_value):
                recs, _ = await client.list("opportunities",
                                            filter=f"stage[eq]:{stage_value}",
                                            order_by="position[AscNullsLast]",
                                            limit=50, depth=1)
                return stage_value, [opportunity_out(r) for r in recs]

            results = await gather_limited([_col(s["value"]) for s in stages], concurrency=4)
            columns: dict[str, list] = {}
            for r in results:
                if isinstance(r, tuple):
                    columns[r[0]] = r[1]
            return JSONResponse({"connected": True, "stages": stages, "columns": columns})

        # Flat list view.
        filt = f"name[ilike]:%{_esc(q)}%" if q.strip() else None
        try:
            recs, page = await _safe_list(client, "opportunities", filter=filt,
                                          order_by="createdAt[DescNullsLast]",
                                          limit=limit, depth=1, starting_after=cursor or None)
        except TwentyError as e:
            return _err(e)
        return JSONResponse({
            "connected": True,
            "opportunities": [opportunity_out(r) for r in recs],
            "total": page.get("totalCount"),
            "next_cursor": (page.get("pageInfo") or {}).get("endCursor")
            if (page.get("pageInfo") or {}).get("hasNextPage") else None,
        })

    @router.post("/twenty/opportunities")
    async def opportunities_create(request: Request):
        return await _create_record(request, "opportunities", opportunity_in, opportunity_out)

    @router.get("/twenty/opportunities/{rec_id}")
    async def opportunities_get(request: Request, rec_id: str):
        return await _record_detail(request, "opportunities", opportunity_out, rec_id, with_relations=False)

    @router.patch("/twenty/opportunities/{rec_id}")
    async def opportunities_update(request: Request, rec_id: str):
        return await _update_record(request, "opportunities", opportunity_in, opportunity_out, rec_id)

    @router.delete("/twenty/opportunities/{rec_id}")
    async def opportunities_delete(request: Request, rec_id: str):
        return await _delete_record(request, "opportunities", rec_id)

    # ── notes / tasks (activity attached to a record) ─────────────────────────
    @router.post("/twenty/notes")
    async def note_create(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"error": "Twenty CRM is not connected"}, status_code=400)
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        title = str(body.get("title") or "").strip() or "Note"
        text = str(body.get("body") or "").strip()
        target_type = str(body.get("target_type") or "").strip()
        target_id = str(body.get("target_id") or "").strip()
        try:
            note = await _create_note_like(client, "notes", title, text)
            if target_type in _TARGET_FK and target_id:
                await client.create("noteTargets", {"noteId": note.get("id"),
                                                     _TARGET_FK[target_type]: target_id})
        except TwentyError as e:
            return _err(e)
        return JSONResponse({"ok": True, "note": note_out(note)})

    @router.post("/twenty/tasks")
    async def task_create(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"error": "Twenty CRM is not connected"}, status_code=400)
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        title = str(body.get("title") or "").strip() or "Task"
        text = str(body.get("body") or "").strip()
        target_type = str(body.get("target_type") or "").strip()
        target_id = str(body.get("target_id") or "").strip()
        extra = {}
        if body.get("due_at"):
            extra["dueAt"] = body["due_at"]
        try:
            task = await _create_note_like(client, "tasks", title, text, extra=extra)
            if target_type in _TARGET_FK and target_id:
                await client.create("taskTargets", {"taskId": task.get("id"),
                                                     _TARGET_FK[target_type]: target_id})
        except TwentyError as e:
            return _err(e)
        return JSONResponse({"ok": True, "task": task_out(task)})

    # ── value bridge: Haptica voice leads -> Twenty pipeline ──────────────────
    @router.post("/twenty/sync/leads")
    async def sync_leads(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"error": "Twenty CRM is not connected"}, status_code=400)
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        leads = body.get("leads")
        if not isinstance(leads, list) or not leads:
            return JSONResponse({"error": "leads (non-empty array) is required"}, status_code=400)
        leads = leads[:50]  # Twenty rate-limits; cap a single import
        create_opp = bool(body.get("create_opportunity", True))
        stages = await client.opportunity_stages()
        stage_values = [s["value"] for s in stages] or ["NEW"]

        async def _one(lead: dict) -> dict:
            name = str(lead.get("name") or "").strip()
            phone = str(lead.get("phone") or "").strip()
            email = str(lead.get("email") or "").strip()
            company_name = str(lead.get("company") or "").strip()
            try:
                company_id = None
                if company_name:
                    company_id = await _upsert_company(client, company_name)
                person, created = await _upsert_person(client, name, phone, email, company_id)
                if created:
                    # CREDITS metering — one "crm.enrich" unit per NEW contact synced (updates are
                    # free). Dormant-safe: never breaks the sync. Idempotent on the Twenty person id.
                    try:
                        import credits
                        credits.get_engine().record_usage(
                            t["tenant_id"], "crm.enrich", 1,
                            meta={"idem_key": f"twenty:{person.get('id')}", "name": name})
                    except Exception:  # noqa: BLE001
                        pass
                opp = None
                if create_opp:
                    stage = _map_stage(lead.get("status") or lead.get("stage"), stage_values)
                    opp_body = opportunity_in({
                        "name": name or company_name or "Opportunity",
                        "stage": stage,
                        "amount": lead.get("amount"),
                        "pointOfContactId": person.get("id"),
                        "companyId": company_id,
                    })
                    opp = await client.create("opportunities", opp_body)
                return {"ok": True, "name": name or phone, "created": created,
                        "person_id": person.get("id"),
                        "opportunity_id": opp.get("id") if opp else None}
            except TwentyError as e:
                return {"ok": False, "name": name or phone, "error": e.message}

        results = await gather_limited([_one(l) for l in leads if isinstance(l, dict)], concurrency=3)
        out = [r if isinstance(r, dict) else {"ok": False, "error": str(r)} for r in results]
        ok = sum(1 for r in out if r.get("ok"))
        return JSONResponse({"ok": True, "imported": ok, "total": len(out), "results": out})

    # ── generic record helpers (shared by the typed routes above) ─────────────
    async def _create_record(request, plural, to_twenty, to_flat):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"error": "Twenty CRM is not connected"}, status_code=400)
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            rec = await client.create(plural, to_twenty(body))
        except TwentyError as e:
            return _err(e)
        return JSONResponse({"ok": True, "record": to_flat(rec)})

    async def _update_record(request, plural, to_twenty, to_flat, rec_id):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"error": "Twenty CRM is not connected"}, status_code=400)
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        try:
            rec = await client.update(plural, rec_id, to_twenty(body))
        except TwentyError as e:
            return _err(e)
        return JSONResponse({"ok": True, "record": to_flat(rec)})

    async def _delete_record(request, plural, rec_id):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"error": "Twenty CRM is not connected"}, status_code=400)
        try:
            await client.delete(plural, rec_id)
        except TwentyError as e:
            return _err(e)
        return JSONResponse({"ok": True})

    async def _record_detail(request, plural, to_flat, rec_id, *, with_relations):
        t = _tenant(request)
        if not t:
            return need_auth()
        client = _client_for(t)
        if client is None:
            return JSONResponse({"connected": False, "record": None})
        try:
            rec = await client.get(plural, rec_id, depth=1)
        except TwentyError as e:
            return _err(e)
        if not rec:
            return JSONResponse({"error": "not found"}, status_code=404)
        out: dict = {"connected": True, "record": to_flat(rec)}
        # Relations embedded by depth=1 (people / opportunities on a company).
        if with_relations:
            if plural == "companies":
                out["people"] = [person_out(p) for p in _rel_list(rec.get("people"))]
                out["opportunities"] = [opportunity_out(o) for o in _rel_list(rec.get("opportunities"))]
            elif plural == "people":
                out["opportunities"] = [opportunity_out(o)
                                        for o in _rel_list(rec.get("pointOfContactForOpportunities"))]
        # Notes + tasks attached to this record (best-effort).
        target_type = {"companies": "company", "people": "person",
                       "opportunities": "opportunity"}.get(plural)
        if target_type:
            out["notes"], out["tasks"] = await _activity_for(client, target_type, rec_id)
        return JSONResponse(out)

    async def _activity_for(client: TwentyClient, target_type: str, target_id: str):
        """Notes + tasks linked to a record via the *Targets join objects. Best
        effort: any failure (version drift, perms) yields empty lists, never a 500."""
        fk = _TARGET_FK.get(target_type)
        notes, tasks = [], []
        if not fk:
            return notes, tasks
        try:
            recs, _ = await client.list("noteTargets", filter=f"{fk}[eq]:{target_id}",
                                        limit=30, depth=1)
            for nt in recs:
                n = nt.get("note") if isinstance(nt.get("note"), dict) else None
                if n:
                    notes.append(note_out(n))
        except TwentyError:
            pass
        try:
            recs, _ = await client.list("taskTargets", filter=f"{fk}[eq]:{target_id}",
                                        limit=30, depth=1)
            for tt in recs:
                tk = tt.get("task") if isinstance(tt.get("task"), dict) else None
                if tk:
                    tasks.append(task_out(tk))
        except TwentyError:
            pass
        return notes, tasks

    async def _create_note_like(client: TwentyClient, plural: str, title: str,
                                text: str, *, extra: dict | None = None):
        """Create a note/task tolerant of the body-field rename across Twenty
        versions (bodyV2 {markdown} on current, body string on older)."""
        base = {"title": title}
        if extra:
            base.update(extra)
        attempts = [
            {**base, "bodyV2": {"markdown": text}} if text else {**base},
            {**base, "body": text} if text else {**base},
            {**base},
        ]
        last: TwentyError | None = None
        for payload in attempts:
            try:
                return await client.create(plural, payload)
            except TwentyError as e:
                last = e
                if e.status not in (400, 422):
                    raise
        raise last or TwentyError(400, f"could not create {plural}")

    async def _upsert_company(client: TwentyClient, name: str) -> str | None:
        # _esc() strips the filter metacharacters ( , ( ) [ ] : ) — without it a
        # company like "Smith, Jones (LLC)" makes a malformed filter Twenty 400s on,
        # the lookup is swallowed, and we'd CREATE A DUPLICATE every import.
        nq = _esc(name)
        if nq:
            try:
                recs, _ = await client.list("companies", filter=f"name[eq]:{nq}", limit=1, depth=0)
                if recs:
                    return recs[0].get("id")
            except TwentyError:
                pass
        rec = await client.create("companies", company_in({"name": name}))
        return rec.get("id")

    async def _upsert_person(client: TwentyClient, name: str, phone: str,
                             email: str, company_id: str | None):
        existing = None
        pq = _esc(phone)
        if pq:
            try:
                recs, _ = await client.list(
                    "people", filter=f"phones.primaryPhoneNumber[eq]:{pq}", limit=1, depth=0)
                existing = recs[0] if recs else None
            except TwentyError:
                existing = None
        eq = _esc(email)
        if not existing and eq:
            try:
                recs, _ = await client.list(
                    "people", filter=f"emails.primaryEmail[eq]:{eq}", limit=1, depth=0)
                existing = recs[0] if recs else None
            except TwentyError:
                existing = None
        flat = {"name": name, "phone": phone, "email": email}
        if company_id:
            flat["companyId"] = company_id
        if existing:
            # only fill the company link if newly known; don't clobber the name
            patch = {}
            if company_id and not existing.get("companyId"):
                patch["companyId"] = company_id
            if patch:
                rec = await client.update("people", existing["id"], patch)
                return (rec or existing), False
            return existing, False
        rec = await client.create("people", person_in(flat))
        return rec, True

    return router


# ── SSRF validation for the tenant-supplied workspace URL ────────────────────
def _check_base_url(base_url: str) -> tuple[bool, str]:
    """(ok, reason) for an UNTRUSTED workspace URL. Prefers the house ssrf_guard;
    falls back to a stdlib resolve+denylist if it's unavailable. Fail-closed: any
    parse/resolution problem or private target → not ok. NEVER raises."""
    raw = (base_url or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        u = urlparse(raw)
    except Exception:  # noqa: BLE001
        return False, "That doesn't look like a valid URL"
    scheme = (u.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://"
    host = (u.hostname or "").strip()
    if not host:
        return False, "URL is missing a host"
    try:
        port = u.port or (443 if scheme == "https" else 80)
    except ValueError:
        return False, "URL has an invalid port"

    blocked_msg = "That address isn't allowed — it points to a private or internal network"
    if _ssrf_validate is not None:
        try:
            d = _ssrf_validate(host, port, scheme)
            return (bool(d), "ok" if d else blocked_msg)
        except Exception:  # noqa: BLE001 — guard says it never raises, but fail-closed anyway
            return False, blocked_msg
    return _fallback_ssrf_check(host, port, blocked_msg)


def _fallback_ssrf_check(host: str, port: int, blocked_msg: str) -> tuple[bool, str]:
    """Self-contained guard used only if provider_registry.ssrf_guard is absent:
    reject IP literals / DNS targets in private / loopback / link-local / reserved /
    multicast ranges. Conservative (fail-closed on resolution failure)."""
    import ipaddress
    import socket

    def _is_blocked(ip_str: str) -> bool:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)

    # IP literal → check directly (no DNS to rebind).
    try:
        ipaddress.ip_address(host)
        return (not _is_blocked(host), blocked_msg)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        ips = [i[4][0] for i in infos]
    except Exception:  # noqa: BLE001
        return False, "Could not resolve that host"
    if not ips or any(_is_blocked(ip) for ip in ips):
        return False, blocked_msg
    return True, "ok"


# ── module-level pure helpers ────────────────────────────────────────────────
def _rel_list(rel) -> list[dict]:
    if isinstance(rel, list):
        return [r for r in rel if isinstance(r, dict)]
    if isinstance(rel, dict):
        edges = rel.get("edges")
        if isinstance(edges, list):
            return [e.get("node", {}) for e in edges if isinstance(e, dict)]
        recs = rel.get("records")
        if isinstance(recs, list):
            return [r for r in recs if isinstance(r, dict)]
    return []


def _map_stage(status, stage_values: list[str]) -> str:
    """Map a Haptica lead status keyword to the closest live Twenty stage value."""
    s = (str(status or "")).lower().strip()
    upper = [v.upper() for v in stage_values]
    if s:
        for keywords, prefs in _STAGE_HINTS:
            if any(k in s for k in keywords):
                for p in prefs:
                    for v in upper:
                        if v == p or v.startswith(p):
                            return stage_values[upper.index(v)]
    # default to the first ("NEW"-ish) column
    return stage_values[0] if stage_values else "NEW"
