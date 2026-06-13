# Wave build — REC-C: Unified Recordings API (tenant-scoped)

Wave: `handoff-name-and-recordings` / unit **REC-C**. Date 2026-06-13.
Box famit@168.144.153.145 `/opt/famit-agent`, caller port 8209, venv `/opt/capsy-agent/.venv`,
X-Auth `FamitCall2026`. DO Spaces `capsy-recordings` (sgp1).

## What shipped
Two ADDITIVE read routes on `caller.py` (famit-caller only; INBOUND+OUTBOUND unified):

- `GET /calls/{call_id}/recording` — the recording for ONE outbound call (REC-B). BOLA-guarded
  via `require_object` (cross-tenant id -> 404, existence not revealed). Returns the unified ITEM.
- `GET /contacts/{phone}/recordings` — ALL recordings for one lead, UNIFIED across both directions
  (newest-first): outbound calls (REC-B JSON `CALLS` store, filtered by tenant via `calls_for`) +
  inbound AI-Manager sessions (REC-A `ai_manager_sessions` PG, RLS-scoped via `store.list_sessions`/
  `get_session`), joined on the canonicalized phone.

### Unified shape (ITEM)
```
{call_id, direction("inbound"|"outbound"), phone, name, campaign_id,
 started_at, duration_s, status, recording_status, has_recording(bool),
 recording_presigned_url(str; "" when no object / boto3 absent)}
```
`/calls/{id}/recording` -> `{recording: ITEM}`.
`/contacts/{phone}/recordings` -> `{phone, recordings:[ITEM...], total, with_recording}`.

## How it works (the wiring)
- New helpers in `caller.py` (right after `call_detail`, before `/stats`):
  - `_rec_presign(bucket,key,expires_s=3600)` — lazy-imports `ai_manager.recorder.presign` (the PROVEN
    sigv4 + path-style minter that already powers the AIM player; serves 200 + 206) and returns "" on
    any error. Reuse, NOT a re-impl.
  - `_outbound_rec_item(rec)` — shapes one REC-B `CALLS` row; `recording_key` is the authoritative
    handle (auto-egress returns no id at room-create). Hardcodes `direction:"outbound"` (the row's own
    `direction` field is None on outbound).
  - `_inbound_rec_items(tid,phone_n)` — RLS-scoped `store.list_sessions(tid,channel="voice")` filtered
    on `caller_phone==phone_n`, then `store.get_session(tid,sid)` for bucket/key/egress_id. Carries the
    REC-A finalize-on-read self-heal: if a row has an egress_id but isn't terminal, `recorder.finalize()`
    reconciles the true terminal status + duration from LiveKit `ListEgress` and persists via
    `set_recording` before presigning. NEVER raises -> [].
- Tenant is pinned from the TOKEN (`resolve_tenant`) exactly like `/contacts` — never a body/param.
  Outbound isolation = `calls_for(t)` tenant filter + `require_object` BOLA guard; inbound isolation =
  `store._query` runs `engine.session(tenant_id=vendor_id)` (FORCE-RLS).
- Every helper degrades to `has_recording`/empty url, never a 500.

## Deploy
backup `caller.py.RECbak.20260613-194141` (md5 `e82ccbff…`) -> edit live copy -> scp `/tmp/caller.recc.py`
(md5 match) -> box-venv `py_compile` OK + AST check (5 fns + 2 routes present) -> `cp` in place ->
`sudo systemctl restart famit-caller` ONLY -> `is-active` + `/health`=200, 0 traceback.
caller.py md5 `e82ccbff…` -> **`f05fdd2e35c3227e4a0aa7284c292f92`** (box + tracked mirror `droplet_work/caller.py`).

## EARNER GATE (before + after) — PASS
agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent MainPID `1477083` /
ActiveEnter `2026-06-10 19:58:18` NEVER restarted; all 3 services active; only famit-caller restarted.

## SMOKE — proven over real HTTP
- `GET /calls/61a6bfeada/recording` (admin) -> ITEM with a 360-char presigned URL.
  full GET -> **200** `audio/ogg` **56916 bytes**; `Range: bytes=0-1023` -> **206** `audio/ogg` **1024 bytes**.
  (Spaces `head_object` confirmed the object: 56916 B audio/ogg.)
- `GET /contacts/+918949906361/recordings` (admin) -> 8 calls newest-first, `with_recording:1`
  (the REC-B-armed one presigns; older pre-REC-B rows `has_recording:false`, url "").
- TENANT ISOLATION (token minted via `_make_token` on box SECRET): tenant B (`21d0a13603da`)
  GET tenant-A call `/calls/61a6bfeada/recording` -> **404**; tenant B token valid (`/calls`->200);
  tenant B GET `/contacts/+918949906361/recordings` (A-owned phone) -> **total:0** (no leak).

## Notes / next
- `/contacts/{phone}/recordings` runs the inbound branch off the event loop (`asyncio.to_thread`) since
  `store`/`recorder.finalize` are sync (finalize opens its own loop).
- pre-REC-B outbound rows have no `recording_key` -> `has_recording:false` (correct; they dialed unrecorded).
- UNBUILT (same wave): CRM (`app/crm/[id]`) + AIM player UI to consume these routes; handoff-name e2e.

## REC-UI FRONTEND — DEPLOYED LIVE (2026-06-13)
The CRM/AIM/handoff UI was already COMMITTED (`68bbc63`) from the network-dropped `wimqqngha` wave but
NEVER deployed (box at old LPR `BUILD_ID WwBfbgcnCuH-Rzi9--YvE`; box `_handoff.tsx`/`crm/client.ts`
lacked `name`/`getContactRecordings`; no `*.RECUIbak.*`). Re-run = the DEPLOY only.
- Files (all in `68bbc63`): `app/ai-manager/_handoff.tsx` (required Name field + name-led rows),
  `lib/api.ts` (HandoffMember.name wired through add/save), `app/crm/client.ts`
  (`getContactRecordings` dormant-safe), `app/crm/[id]/page.tsx` (Recordings card + seekable player +
  per-row Download mirroring the AIM player). AIM session player needed no change.
- VERIFY: local `tsc --noEmit` EXIT 0 + `npm run build` EXIT 0.
- DEPLOY (build-locally, ship artifacts to avoid on-box OOM, box ~1.4GB free): backup
  `*.RECUIbak.20260613-195539` (.next/app/lib); md5-gated 56M tarball SCP (1st attempt truncated → re-sent
  foreground, md5 local==box); extract→stage→verify→atomic mv-swap→`chown deployuser`; restart famit-panel
  ONLY → PID 239673, new `BUILD_ID 4aXNPr1rvAfpK4ku5dNa7`. 200 + new BUILD_ID on loopback:3001 AND
  panel.famit.in edge for `/ /login /crm /crm/[id] /ai-manager /ai-manager/sessions/[id]`. EARNER N/A
  (FORTRESS box `143.110.247.249`, no agent dir; earner box `168.144.153.145` never touched).
- ROLLBACK: restore the 3 RECUIbak dirs + restart. State: `famit-panel/REC_UI_STATE.md`.
