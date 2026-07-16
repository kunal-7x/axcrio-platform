# W11 — Warm-Transfer + Booking + Google-Calendar SEAM

**Branch:** `fix/realtime-voice-kernel-v2`
**EARNER LAW honored:** live OUTBOUND `agent.py` md5 `98655dbf` — never edited, never imported, never restarted.
The LIVE inbound agent (`aim_voice_agent.DEPLOYED.py`) is **NOT live-edited** — its changes are this **PATCH DOC**.
All NEW code is **tracked + disjoint** under `voice_ops/booking/` and `voice_ops/gcal/` and imports **zero**
droplet/livekit/google/redis/sqlalchemy at module load (every such import is lazy).

This doc is the seam: it specifies (1) the exact `aim_voice_agent` transfer + `book_site_visit` patch, (2) the
`caller.py` booking API mount, (3) the Google OAuth founder-setup steps. Apply patches one at a time, each with an
integrated real-call smoke + revert path.

---

## 0. What shipped (tracked, tested, default-OFF)

| File | Purpose |
|---|---|
| `voice_ops/booking/config.py` | `BookingOpsConfig` (flags; `BOOKING_OPS_ENABLED` default OFF) |
| `voice_ops/booking/store.py` | **Lazy wrapper** over the gitignored `droplet_work/booking/core.py` — loads the engine file at call-time via importlib; dormant-safe (returns `not_configured`) when absent. No double-book / RLS / immutable audit are inherited unchanged from the engine. |
| `voice_ops/booking/datetime_resolve.py` | PURE clock-injected resolver: "kal subah 10 baje" / "tomorrow 3pm" / ISO -> concrete UTC slot (IST-aware). |
| `voice_ops/booking/service.py` | `BookingService.book_site_visit(...)` (AI tool impl) + lifecycle (`confirm/complete/cancel/mark_no_show/reschedule`) + W8 `site_visit_booked` emit + async calendar fan-out. |
| `voice_ops/booking/transfer.py` | `plan_transfer(...)` pure planner (ONE ack line + dial/exit step order), `detect_transfer_intent`, `TransferLog` lifecycle (requested/started/connecting/completed/failed -> W8 `handoff_requested`/`handoff_done`). |
| `voice_ops/gcal/config.py` | `GCalConfig` (OAuth client + endpoints; `BOOKING_CALENDAR_SYNC` default OFF). |
| `voice_ops/gcal/vault.py` | **Self-contained** AAD-bound AES-256-GCM refresh-token vault (does NOT depend on the gitignored `provider_registry`) + FORCE-RLS `gcal_credentials` table DDL. |
| `voice_ops/gcal/oauth.py` | server-side flow: `authorization_url` -> `exchange_code` (store encrypted refresh token) -> `refresh` (mint access token; flip `revoked` on `invalid_grant` = reconnect-on-expiry). |
| `voice_ops/gcal/sync.py` | `CalendarSync.on_booked/on_rescheduled/on_cancelled` — ASYNC Calendar v3 REST (never blocks the call). |

Tests: `voice_ops/booking/tests/`, `voice_ops/gcal/tests/` — **39 new, all green; full `pytest voice_ops/ voice_kernel/` = 447 passed.**

---

## 1. Founder bug 1 — WARM TRANSFER (PATCH `aim_voice_agent.DEPLOYED.py`, inbound-only)

### Root cause (from the explore + confirmed on disk)
`_OUTBOUND_TRUNK` is captured at **import time** (line 172, default `ST_fmtVmNJmpzKa`). When the box `.env` trunk
changed to `ST_bpGqmc9TL9Ph`, `aim-voice-agent` was **never restarted**, so it keeps dialing the old spam-blocked
trunk -> every dial returns `486/408/500` -> hold music starts then the `finally` stops it -> the LLM reads the
verbose `no_human_answered: I couldn't reach a team member live…` paragraph aloud = the "unnecessary things".

### IMMEDIATE FIX (no code): `sudo systemctl restart aim-voice-agent` — picks up the correct trunk.

### Code patches (each calls into the tested `voice_ops.booking.transfer` brain)

**Patch A — per-call trunk (line 172).** Replace the module-level capture with a function read **per call**, so a
future trunk swap never needs a code restart:
```python
def _get_outbound_trunk() -> str:
    return (os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_bpGqmc9TL9Ph") or "ST_bpGqmc9TL9Ph").strip()
```
At the `CreateSIPParticipantRequest` (line ~890) use `sip_trunk_id=_get_outbound_trunk()` instead of `_OUTBOUND_TRUNK`.

**Patch B — ONE-line ack via the planner (`_do_warm_transfer`, line 757).** At entry, build the deterministic plan:
```python
from voice_ops.booking.transfer import plan_transfer, TransferLog
team = await asyncio.to_thread(_vt.handoff_list, tenant_id) or []   # existing fetch (line 776)
plan = plan_transfer(handoff_numbers=team, dial_who="team")
tlog = TransferLog(call_id=call_id, tenant_id=tenant_id, reason=reason,
                   event_bus=_event_bus_or_none())   # W8 emit (fire-and-forget)
await tlog.requested()
# speak EXACTLY plan.ack_line — nothing else (no numbers, no paragraph):
await session.say(plan.ack_line)           # the ONLY spoken line before the dial
```
Then run `plan.steps` in order: `start_hold_music` -> `tlog.started(num)` -> the **existing** `create_sip_participant`
bridge into the caller's room (`_get_outbound_trunk()`), sequential over `plan.dial_numbers` -> on answer
`tlog.connecting()`/`tlog.completed(agent=num)`, stop music, then the **existing** `session.aclose()` AI-exit
(room stays alive). On all-dials-fail: `await session.say(plan.fallback_line)` (the ONE short line) then `tlog.failed(...)`.

**Patch C — delete the verbose fallback return strings (lines 816/849/958).** Replace each
`return "no_human_answered: I couldn't reach a team member live, …"` with returning `plan.fallback_line` only, OR
returning a tight instruction `"Say only: '<plan.fallback_line>'. Then close."` so the LLM speaks exactly one sentence.

**Patch D — prompt hard-block (the `transfer_to_human` tool docstrings, lines ~1302/1798 + the system prompt).**
Change "do NOT say…" to: *"When you call `transfer_to_human`, your ENTIRE response for that turn is ONLY the tool
call — zero spoken words before or after. The tool speaks the one connect line itself."* This stops the LLM emitting
a spoken "ठीक है सर" prefix in addition to the tool's ack line.

**Net behaviour:** detect intent (the prompt + `detect_transfer_intent` backstop) -> AI says ONE short line
`"Theek hai sar, main aapko team se connect kar raha hoon."` -> hold music -> dial handoff number into the SAME SIP
room -> connect -> AI exits -> states logged (requested/started/connecting/completed/failed) and emitted on W8.

### Revert: the patches are additive; `git checkout` the agent file + `systemctl restart aim-voice-agent`.

---

## 2. Founder bug 2 — BOOKING from the call (PATCH `aim_voice_agent` tool + `caller.py` API)

### AI tool (add a `@function_tool` to BOTH the CustomerSales + Manager agent classes)
```python
@function_tool
async def book_site_visit(self, context: RunContext, when: str, name: str = "", notes: str = "") -> str:
    """Book a real site visit when the prospect agrees. `when` = the time they said
    (e.g. 'kal subah 10 baje'). Returns ONE short line to say."""
    from voice_ops.booking import BookingService, BookingOpsConfig
    from voice_ops.gcal import CalendarSync
    svc = BookingService(BookingOpsConfig.from_env(),
                         event_bus=_event_bus_or_none(),
                         calendar_sync=CalendarSync())   # async, never blocks
    res = await svc.book_site_visit(
        org_id=self._tenant_id, call_id=context.room.name if context else "",
        phone=self._caller_phone, when=when, name=name, notes=notes,
        campaign_id=self._campaign_id)
    return res["say"]      # the LLM speaks exactly this one confirmation line
```
- Persists a REAL appointment (atomic claim, no double-book — inherited from the engine), links lead+campaign,
  source=`voice`. Emits W8 `site_visit_booked` -> the dashboard/CRM update instantly.
- Conflict -> `say` re-asks for another time; unresolved time -> `say` asks for a clear day/time; dormant/disabled ->
  graceful "we'll confirm the time" (the call is never broken).

### `caller.py` booking API (mount the booking router; replaces the panel's UI-only page with real data)
Add near the other route registrations:
```python
from voice_ops.booking.service import BookingService
from voice_ops.booking.config import BookingOpsConfig
_booking = BookingService(BookingOpsConfig.from_env(), event_bus=_event_bus)

@app.get("/booking")
async def booking_list(request: Request):
    t = resolve_tenant(request)
    return JSONResponse(_booking.list(org_id=t["tenant_id"], status=request.query_params.get("status","")))

@app.post("/booking/{booking_id}/complete")
async def booking_complete(booking_id: str, request: Request):
    t = resolve_tenant(request)
    return JSONResponse(await _booking.complete(org_id=t["tenant_id"], booking_id=booking_id))
# + /booking/{id}/cancel, /reschedule, /confirm, /no_show, /{id}/events  (manual lifecycle from the panel)
```
The (gitignored) `droplet_work/booking/router.py` already defines the full CRUD router — either mount it directly
(`app.include_router(build_router(resolve_tenant, can))`) or use the thin `BookingService` wrappers above. The
schema mount (Alembic `0003_booking` + `booking/rls.sql`) is the one-time DB step.

### Lifecycle states (founder words -> engine status)
Scheduled=`booked` · Confirmed=`booked`+confirmed flag · Rescheduled=`rescheduled` · Completed=`completed` ·
NoShow=`no_show` (scheduler tick or manual) · Cancelled=`cancelled`. Manual (panel) and AI both drive them.

---

## 3. Founder bug 3 — Google Calendar (ASYNC, reconnect-on-expiry)

### Flow (all in `voice_ops/gcal/`)
1. Vendor clicks **Connect Google Calendar** in the panel -> backend calls `GoogleOAuth(cfg).authorization_url(tenant)`
   -> redirect the vendor to the returned `url` (access_type=offline + prompt=consent => a refresh token; signed
   `state` binds the result to the tenant).
2. Google redirects back to `GET /api/gcal/callback?code=...&state=...` -> backend calls
   `GoogleOAuth(cfg).exchange_code(code, state)` -> the **refresh token is encrypted (AES-256-GCM, AAD-bound) and
   stored** in the FORCE-RLS `gcal_credentials` table. **Tenant comes from the verified state, never the body.**
3. On every booking change the `BookingService` fires `CalendarSync.on_booked/on_rescheduled/on_cancelled`
   **as a background task** (never blocks the call). Each mints a fresh access token via `oauth.refresh` (run in a
   thread) and calls Calendar v3 `events.insert/patch/delete`. The event body carries lead name/phone/campaign/
   notes/status.
4. **Reconnect-on-expiry:** if Google returns `invalid_grant` (revoked/expired), `refresh` flips the row to
   `revoked` and the sync no-ops; the panel shows "reconnect" and re-runs step 1.

### `caller.py` OAuth endpoints to mount
```python
from voice_ops.gcal import GoogleOAuth, GCalConfig
_gcal = GoogleOAuth(GCalConfig.from_env())

@app.get("/gcal/connect")          # returns {url} for the panel to redirect to
async def gcal_connect(request: Request):
    t = resolve_tenant(request); return JSONResponse(_gcal.authorization_url(t["tenant_id"]))

@app.get("/api/gcal/callback")     # Google redirect target (redirect_uri)
async def gcal_callback(code: str = "", state: str = ""):
    return JSONResponse(_gcal.exchange_code(code, state))   # org_id is from the signed state

@app.get("/gcal/status")
async def gcal_status(request: Request):
    t = resolve_tenant(request); return JSONResponse(CalendarSync().status(t["tenant_id"]))
```

### DB: apply `voice_ops/gcal/vault.RLS_DDL` (the `gcal_credentials` FORCE-RLS table) at mount.

---

## 4. Env flags (all default OFF — nothing changes until flipped)
```
BOOKING_OPS_ENABLED=1            # arm the AI book_site_visit tool
BOOKING_DEFAULT_RESOURCE=site_visit
BOOKING_DEFAULT_TZ=Asia/Kolkata
LIVEKIT_SIP_TRUNK_ID=ST_bpGqmc9TL9Ph     # the CORRECT current trunk (transfer fix)

BOOKING_CALENDAR_SYNC=1          # arm Google Calendar sync
GOOGLE_CALENDAR_CLIENT_ID=...            # FOUNDER ACTION (see §5)
GOOGLE_CALENDAR_CLIENT_SECRET=...        # FOUNDER ACTION
GOOGLE_CALENDAR_REDIRECT_URI=https://panel.famit.in/api/gcal/callback
# vault key rides the existing FAMIT_KEYSTORE_SECRET / PROVIDER_KEYSTORE_SECRET — no new secret needed
```

---

## 5. FOUNDER ACTION — Google OAuth client (needed to go live on calendar; ~10 min, one-time)
1. Go to **https://console.cloud.google.com** -> create/select a project (e.g. "Famit").
2. **APIs & Services -> Library -> Google Calendar API -> Enable.**
3. **APIs & Services -> OAuth consent screen** -> External -> fill app name/email -> add scope
   `.../auth/calendar` -> add your vendor Google accounts as test users (or publish).
4. **APIs & Services -> Credentials -> Create Credentials -> OAuth client ID -> Web application.**
   - Authorized redirect URI: `https://panel.famit.in/api/gcal/callback`
5. Copy the **Client ID** and **Client secret** and send them (out-of-band, not in git) so they go into the box
   `.env` as `GOOGLE_CALENDAR_CLIENT_ID` / `GOOGLE_CALENDAR_CLIENT_SECRET`, then set `BOOKING_CALENDAR_SYNC=1`.

Until these arrive, calendar sync stays dormant and bookings still persist in Postgres + show on the dashboard
(calendar is an enrichment, never a dependency).

---

## 6. Earner-safety summary
- `agent.py` md5 `98655dbf` untouched; `aim_voice_agent` edits are this doc only (apply one at a time + real-call smoke).
- All new code default-OFF, droplet-free, lazy-import, fail-closed on empty tenant, never raises into the call path.
- W8 emits + calendar sync are fire-and-forget — a dead Redis / revoked Google token can never break a booking or call.
