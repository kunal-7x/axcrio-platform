# Famit — P0 + Top-P1 Production Implementation Plan (Code-Level, Build-Ready)

Author: Senior architect (read-only design pass)
Date: 2026-06-04
Targets the EXACT live stack. No rewrites. All changes are additive and tenant-scoped.

## Ground truth (verified against live source)
- Backend: `droplet_work/caller.py` (FastAPI, uvicorn `caller:app` :8209). Form-encoded endpoints, JSON file stores under `VAR=/opt/famit-agent/var/`. Auth via `resolve_tenant(request)` -> tenant dict (admin sees all; vendors scoped by `tenant_id`). Helpers `_read(path,default)` / `_write(path,data)`. Dial loop = `run_job(job_id)` driving `JOBS[job_id]`. Calls recorded via `record_call(rec)` into module-global `CALLS` + `calls.json`.
- Agent: `droplet_work/agent.py` (livekit-agents). Loads campaign by `meta["campaign_id"]`, greets by `lead_name`, opener via `_llm_opener(...)`, transcript+summary via `_summarize(turns)` written to `var/transcripts/<room>.json` on shutdown (`_persist_memory`). `turns` collected in `conversation_item_added`.
- Prompt: `droplet_work/prompt.py` `build_system_prompt(fields)` + `SHARED_RULES` (currently contains the line "कभी मत कहो कि तुम AI/bot हो" — MUST change for P0.3).
- Frontend: `famit-panel`, Next.js `"use client"` pages using `@/components/Layout`, `@/components/Card`, `@/components/Button`. All API calls go through `lib/api.ts` (sends `X-Auth` from `localStorage['famit_token']`, `handle401`). Nav in `contstants/navigation.tsx`. Tables use the shared Tailwind table class pattern.

## Global conventions every change MUST follow
1. New stores are JSON files under `VAR`, read/written ONLY via `_read`/`_write`. Add a `Path` constant near line 49 (next to `TENANTS_FILE`).
2. Every new endpoint starts with `t = resolve_tenant(request); if not t: return need_auth()` and filters/writes with `t["tenant_id"]` (admin bypass: `t.get("is_admin")`), mirroring `_leads_for`/`calls_for`.
3. Every new record carries `tenant_id`. Reuse `uuid.uuid4().hex[:N]` for ids, `datetime.now().isoformat(timespec="seconds")` for timestamps.
4. Endpoints are `Form(...)` based (matches existing). Responses are `JSONResponse`.
5. Frontend: add a typed wrapper in `lib/api.ts`, then a page under `app/<x>/page.tsx` wrapped in `<Layout>` + `<Card>`; register in `contstants/navigation.tsx` if it is a top-level nav item.
6. IST helper (used by P0.1 + P0.5): add once near the top of caller.py:
   `IST = timezone(timedelta(hours=5, minutes=30))` and `def now_ist(): return datetime.now(IST)` (import `timezone, timedelta`).

---

# P0.1 — Calling-window + timezone gate on /run

### Data model
- Per-campaign override stored INSIDE the campaign `fields` (no new store): add keys to `_coerce_fields` defaults:
  - `call_window_start` (str "HH:MM", default "09:00")
  - `call_window_end` (str "HH:MM", default "21:00")
  - `call_window_tz` (str, default "Asia/Kolkata" — informational; gate computes in IST)
  Add these to the string-defaults loop in `_coerce_fields` (caller.py ~line 513).

### Backend logic
- New helper in caller.py:
  ```
  def _in_window(fields: dict) -> tuple[bool, str]:
      s = fields.get("call_window_start") or "09:00"; e = fields.get("call_window_end") or "21:00"
      now = now_ist().strftime("%H:%M")
      ok = s <= now <= e
      return ok, f"{s}-{e} IST"
  ```
- Enforce in TWO places:
  1. `run_job` dial inner-loop (caller.py ~line 409, the `while idx < len ...` that creates SIP participants): before dialing each lead, re-check `_in_window(campaign_fields)`. If out of window, do NOT dial; set `it["status"]="queued"` (leave pending) and break the inner while so the job idles. Add `job["paused_reason"]="out_of_window"`. Load `campaign_fields` once at top of `run_job` via `get_campaign(cid)`.
  2. The outer `while` (~line 391): when out of window AND no active calls, `await asyncio.sleep(60)` and continue (queue/idle) instead of busy-spinning. The job stays `running` and auto-resumes when the window opens. This satisfies "reject OR queue".
- `/run` endpoint (~line 673): add `force: str = Form("")`. After resolving the campaign, if `not _in_window(camp["fields"])` and not `force`, return `JSONResponse({"queued_out_of_window": True, "window": win, "job_id": <created>, "count": n})` with HTTP 202 — the job is still created and will start dialing automatically when the window opens. This makes the gate non-destructive.

### Agent change
None.

### Frontend
- `app/run/page.tsx`: when `/run` returns `queued_out_of_window`, show an amber toast "Outside calling window (09:00–21:00 IST) — leads queued, dialing will start automatically." Add an optional "Start anyway" button that re-POSTs with `force=1` (admin-only convenience).
- Campaign create/edit form (`app/campaigns/page.tsx`): two `<input type="time">` fields bound to `call_window_start`/`call_window_end`, included in `fields_json`.
- `lib/api.ts`: extend `RunPayload` with `force?: boolean`; append `force=1` when set. `run()` return type gains optional `queued_out_of_window?: boolean; window?: string`.

### Effort: Quick-win (0.5 day backend, 0.5 day frontend)

---

# P0.2 — DND / suppression list

### Data model
- New store `SUPPRESSION_FILE = VAR / "suppression.json"` (constant near line 49).
- Shape: list of `{tenant_id, phone (normalized via norm()), reason, source, added_at}`.
  - `reason` in `["upload","opt_out_call","manual","api"]`.
- Helper:
  ```
  def _suppressed_set(tenant_id: str) -> set[str]:
      return {x["phone"] for x in _read(SUPPRESSION_FILE, []) if x.get("tenant_id")==tenant_id}
  def _add_suppression(tenant_id, phone, reason, source=""):
      store=_read(SUPPRESSION_FILE,[]); phone=norm(phone)
      if phone and not any(x["phone"]==phone and x["tenant_id"]==tenant_id for x in store):
          store.append({"tenant_id":tenant_id,"phone":phone,"reason":reason,"source":source,
                        "added_at":datetime.now().isoformat(timespec="seconds")}); _write(SUPPRESSION_FILE,store)
  ```

### Backend endpoints
- `GET /suppression` -> `{numbers:[{phone,reason,source,added_at}], total}` (tenant-scoped).
- `POST /suppression` form `numbers` (text, one per line "Name,Phone" or bare phone) + optional file `csv` -> reuse `parse_leads()` to extract numbers; call `_add_suppression(t["tenant_id"], num, "upload")` per number -> `{added, total}`.
- `DELETE /suppression/{phone}` -> removes that tenant's entry (normalize first) -> `{deleted}`.
- `POST /optout` form `phone`, optional `campaign_id`, `source` ("call"|"manual"|"api") -> `_add_suppression(...,"opt_out_call" or "manual")`; ALSO flip matching lead `status="opted_out"` in leads.json -> `{ok:true}`. This is the public-ish opt-out writer used by the agent post-call hook (P0.3) and by a manual UI action.

### Dial-time skip (the enforcement)
- In `run_job`, load `supp = _suppressed_set(tenant_id)` ONCE at job start. In the dial inner-loop, before dialing: `if num in supp: it["status"]="suppressed"; record a call rec with status="suppressed", outcome="suppressed", duration_s=0; continue`. This makes suppressed skips visible in Call Logs and counted nowhere as conversations.
- Also pre-filter in `/run` to return `{suppressed_count}` alongside `{count}` so the UI can show "X excluded (DND)".

### Agent change
None for upload; opt-out auto-add handled in P0.3.

### Frontend
- New page `app/suppression/page.tsx` ("Do-Not-Call") + nav entry `{title:"Do-Not-Call", icon:"profile", href:"/suppression"}`. Upload textarea + CSV (mirror `app/leads/page.tsx`), table of suppressed numbers, per-row delete.
- `app/run/page.tsx`: surface `suppressed_count` from `/run` response in the start toast.
- `lib/api.ts`: `getSuppression()`, `addSuppression(text,file)`, `deleteSuppression(phone)`, `optOut(phone, source)`.

### Effort: Quick-win (1 day backend, 1 day frontend)

---

# P0.3 — AI self-disclosure + in-call opt-out + auto-suppress

### Prompt change (prompt.py)
- In `SHARED_RULES`, REMOVE the guard "कभी मत कहो कि तुम AI/bot हो" and REPLACE with a disclosure + opt-out rule:
  - Opener must include a brief AI disclosure, e.g. add to the OPENER section of `build_system_prompt`: "...मैं {agent}, {company} की AI assistant बोल रही हूँ..." (one short clause; do not over-explain).
  - New SHARED_RULES block: "अगर caller कहे 'दोबारा call मत करना' / 'remove me' / 'do not call' / 'opt out' / 'mat karo call' → तुरंत: 'जी ज़रूर, माफ़ कीजिए, अब आपको call नहीं आएगा।' और politely end. इसे साफ़ acknowledge करो।"
- `_llm_opener` in agent.py: add the AI-assistant clause to BOTH the `sysmsg` instruction and the `fallback` line so the disclosure survives the fast say() path.

### Summary schema change (agent.py `_summarize`)
- Extend the system instruction JSON to also return `"opt_out": true|false` (true if the caller asked not to be called / remove / DND). Update the returned dict: `"opt_out": bool(d.get("opt_out", False))`. Keep existing `outcome` enum but add `"opt_out"` as a possible outcome value too.
- Persist `opt_out` into `var/transcripts/<room>.json` (it already spreads `**summ`).

### Auto-suppress wiring (the loop closes server-side, no agent->backend coupling)
- In caller.py `run_job`, when a call finalizes (the `else` branch ~line 398 that sets `rec["status"]="done"`), read the transcript `tr = _read(TRANSCRIPT_DIR / f"{room}.json", {})`. If `tr.get("opt_out")` or `tr.get("outcome")=="opt_out"`: call `_add_suppression(tenant_id, rec["phone"], "opt_out_call", source=room)` and set `rec["outcome"]="opt_out"`. Also flip the lead status to `opted_out`.
- Safety net (covers calls whose room finalized after job ended): in `GET /calls/{call_id}` and in a lightweight periodic sweep, if a loaded transcript has `opt_out` and the number is not yet suppressed, suppress it. Implement the sweep as part of P0.5 scheduler tick (single shared background loop) to avoid a second timer.

### Frontend
- `app/calls/page.tsx` detail modal: render an "Opted out / DND" red badge when `transcript.opt_out` is true. Add `opt_out` to `CallDetail.transcript` type in `lib/api.ts`.

### Effort: Quick-win (0.5 day prompt+agent, 0.5 day backend wiring, 0.25 day frontend)

---

# P0.4 — Answering-machine / no-answer handling

### Signals available
- `_phone_present(lk, room)` already polls SIP participant presence; `MIN_CALL_FLOOR=22s`.
- `turns` count in transcript (`var/transcripts/<room>.json`). `_summarize` already returns `outcome="no_answer"` when there is NO conversation text.
- Per-call `duration_s` computed in `run_job`.

### Classification rule (backend, in run_job finalize branch + as fallback in /calls)
Add `def _classify_outcome(rec, tr) -> str`:
```
turns = tr.get("turns") or []
user_turns = [x for x in turns if x.get("role")=="user" and (x.get("content") or "").strip()]
dur = rec.get("duration_s", 0)
if not turns and dur < 8:        return "no_answer"      # never connected / ring-out
if len(user_turns) == 0 and dur < 25: return "voicemail" # agent spoke, human never did -> machine/VM
if len(user_turns) == 0:         return "no_human"        # connected, no human turns (likely VM/IVR)
return tr.get("outcome") or "answered"
```
- In `run_job` finalize: set `rec["outcome"]=_classify_outcome(rec, tr)` and `rec["answered"] = rec["outcome"] in ("answered","interested","not_interested","callback")` (a real conversation flag).
- These outcomes (`no_answer`,`voicemail`,`no_human`) are NEVER counted as conversations.

### Agent change (optional accuracy boost, low risk)
- In `entrypoint`, track first user turn time. If after `session.start` + opener no `user` turn arrives within ~12s AND VAD never fired, write a hint `tr["amd_hint"]="no_user_audio"` into the transcript. Implement by recording a `first_user_at` timestamp inside the existing `_on_item` handler and including it in `_persist_memory`'s written JSON. Backend `_classify_outcome` can prefer this hint when present. Keep it additive; never block the call.

### Stats change
- `GET /stats` (~line 750): change `answered` to count `c.get("answered") is True` (fallback to the old `duration_s>=8` only when `answered` key absent, for legacy rows). Add `voicemail`, `no_answer` counts to the response. This corrects conversation metrics.

### Frontend
- `app/calls/page.tsx`: extend `statusBadge`/`outcomeBadge` maps with `voicemail` (orange) and `no_human` (grey). The breakdown grid already buckets by status — it will pick these up automatically.

### Effort: Medium-light (1 day backend, 0.5 day agent hint, 0.25 day frontend)

---

# P0.5 — Smart retry + callback scheduling + scheduler tick

### Data model
- New store `RETRY_FILE = VAR / "retry_queue.json"`: list of
  `{id, tenant_id, campaign_id, name, phone, attempts, max_attempts, next_attempt_at (ISO), reason ("no_answer"|"busy"|"voicemail"|"callback"), created_at}`.
- Per-campaign retry policy in `fields` (defaults added in `_coerce_fields`):
  - `retry_max_attempts` (int, default 3)
  - `retry_backoff_mins` (list[int], default [120, 360, 1440]) — +2h, +6h, +next day.
- Callback capture reuses transcript: extend `_summarize` (agent.py) JSON to return `"callback_at"` (ISO datetime or "" — the LLM parses "5 baje", "kal subah" into an absolute IST datetime; instruct it to resolve relative to "now" passed in the prompt) and `"callback_raw"` (the spoken phrase). Persist both into the transcript.

### Enqueue logic (run_job finalize branch)
After `_classify_outcome`:
```
camp_fields = (get_campaign(cid) or {}).get("fields", {})
maxa = int(camp_fields.get("retry_max_attempts", 3))
backoff = camp_fields.get("retry_backoff_mins") or [120,360,1440]
outcome = rec["outcome"]
if tr.get("callback_at"):
    _enqueue_retry(..., reason="callback", next_at=tr["callback_at"], max_attempts=maxa)
elif outcome in ("no_answer","voicemail","busy") and attempts < maxa:
    delay = backoff[min(attempts, len(backoff)-1)]
    next_at = now_ist()+timedelta(minutes=delay)
    next_at = _clamp_to_window(next_at, camp_fields)   # never schedule outside 09-21 IST
    _enqueue_retry(..., reason=outcome, next_at=next_at.isoformat(), attempts=attempts+1)
```
- `_clamp_to_window(dt, fields)`: if `dt` time-of-day < start -> set to start same day; if > end -> roll to start NEXT day. Reuses P0.1 window fields.
- `_enqueue_retry` writes/updates `retry_queue.json` (dedupe by phone+campaign; bump `attempts`).

### Scheduler tick (single shared background loop — also drives P0.3 sweep)
- Add ONE app-startup task (FastAPI `@app.on_event("startup")` or `asyncio.create_task` at import like existing jobs):
  ```
  async def scheduler_loop():
      while True:
          await asyncio.sleep(60)
          due = [r for r in _read(RETRY_FILE,[]) if r["next_attempt_at"] <= now_ist().isoformat()]
          for r in due:
              camp_fields = (get_campaign(r["campaign_id"]) or {}).get("fields",{})
              if not _in_window(camp_fields): continue        # respect window
              if norm(r["phone"]) in _suppressed_set(r["tenant_id"]): _remove_retry(r); continue
              # spin up a 1-lead job reusing run_job machinery
              jid = _spawn_retry_job(r)                        # creates JOBS entry, asyncio.create_task(run_job(jid))
              _remove_retry(r)
          # P0.3 opt-out safety sweep folded in here
  ```
- `_spawn_retry_job(r)` builds a `JOBS[jid]` identical in shape to `/run`'s (single lead, concurrency 1, caps from campaign) and `asyncio.create_task(run_job(jid))`. No new dial code path.

### Backend endpoints (visibility/control)
- `GET /callbacks` -> `{items:[...]}` tenant-scoped from `retry_queue.json` where `reason=="callback"` (and optionally all retries with `?all=1`).
- `DELETE /callbacks/{id}` -> cancel a scheduled retry/callback.
- `POST /callbacks` form `phone,campaign_id,when` -> manual callback enqueue.

### Frontend
- New page `app/callbacks/page.tsx` + nav `{title:"Callbacks", icon:"send", href:"/callbacks"}`: table (Name, Phone, Campaign, When, Reason, attempts) with cancel button. Show reason badge (callback=blue, no_answer/voicemail=amber).
- `lib/api.ts`: `getCallbacks()`, `cancelCallback(id)`, `addCallback(...)`.
- Campaign form: inputs for `retry_max_attempts` (number) and backoff (comma list parsed to int[]).

### Effort: Medium (2–3 days backend, 1 day frontend)

---

# P0.6 — Lead scoring + hot-leads view

### Data model
- `interest` (0–100) ALREADY produced by `_summarize` and stored in the transcript. No new store needed; surface it onto leads + calls.
- On call finalize (run_job), copy `tr.get("interest")` and `tr.get("outcome")` onto the lead record in leads.json:
  - add `score` (int), `last_outcome` (str), `last_call_at` (ISO), `hot` (bool: `score>=70`).
  - Match the lead by `tenant_id`+`phone`==rec phone. Helper `_update_lead_after_call(tenant_id, phone, score, outcome)`.
- Also copy `interest` onto the call rec (`rec["interest"]=tr.get("interest")`) so Call Logs can show it without a second read.

### Backend endpoints
- `GET /leads` (existing): now returns `score,last_outcome,last_call_at,hot` because they live on the lead record. Add `?hot=1` filter and `?sort=score`.
- `GET /leads/hot` -> convenience: `{leads:[... score>=70 ...]}` sorted desc. (Or just rely on `/leads?hot=1`.)

### Agent change
None beyond P0.5's `_summarize` (interest already returned).

### Frontend
- `app/leads/page.tsx`: add a `Score` column with a color-coded badge (>=70 green "hot", 40–69 amber, <40 grey) and an `last outcome` column; add a "Hot only" toggle (calls `/leads?hot=1`).
- New dashboard widget on `app/page.tsx`: "Hot Leads" count + top-5 list (links to leads filtered).
- `lib/api.ts`: extend `Lead` type with `score?, last_outcome?, last_call_at?, hot?`; `getLeads(opts?)` supports `{hot?,sort?}` query.

### Effort: Quick-win (0.5 day backend, 1 day frontend)

---

# P0.7 — Usage metering + concurrency caps per tenant

### Data model
- Per-tenant plan limits live on the tenant record (tenants.json). Extend `create_tenant` + admin edit to set:
  - `max_concurrency` (int, default 3), `daily_call_cap` (int, default 500), `monthly_minutes_cap` (int, default 5000). Backfill admin/existing tenants with generous defaults via a one-time migrate (mirror `_migrate_to_admin`).
- Usage is DERIVED from `calls.json` (no new event store needed for v1; calls already have `tenant_id`, `started_at`, `duration_s`). A rollup helper:
  ```
  def _tenant_usage(tenant_id, since_iso) -> dict:
      rows=[c for c in CALLS if c.get("tenant_id")==tenant_id and c.get("started_at","")>=since_iso]
      return {"calls":len(rows), "minutes":round(sum(c.get("duration_s",0) for c in rows)/60,1)}
  ```
  - today = `now_ist().date().isoformat()`, month = `now_ist().strftime("%Y-%m")`.
- Live concurrency: count active across that tenant's JOBS, or simpler/global-safe — an in-memory `ACTIVE_CALLS: dict[tenant_id,int]` incremented when a SIP participant is created in `run_job` and decremented in the finalize branch. Single source of truth, no Redis (matches "JSON file + in-proc" architecture).

### Enforcement
- In `run_job` dial inner-loop, before creating a SIP participant:
  - `tenant = _tenant_by_id(tenant_id)`; `cap = tenant.get("max_concurrency",3)`.
  - if `ACTIVE_CALLS.get(tenant_id,0) >= cap`: skip dialing this tick (leave lead queued), continue. This stacks UNDER the existing per-job `concurrency`.
  - Daily cap: `if _tenant_usage(tenant_id, today_iso)["calls"] >= tenant.get("daily_call_cap",500): pause job with reason "daily_cap_reached"`.
  - Monthly minutes: checked at `/run` admission (reject new run with 429 `{error:"monthly minutes cap reached"}`) AND each tick.
- `/run` (admission): also clamp `concurrency` to `min(requested, tenant.max_concurrency)`.

### Backend endpoints
- `GET /usage` -> `{today:{calls,minutes}, month:{calls,minutes}, limits:{max_concurrency,daily_call_cap,monthly_minutes_cap}, active_now}` tenant-scoped.
- `GET /usage/all` (admin) -> per-tenant rollup table.
- `POST /tenants/{id}/limits` (admin) form `max_concurrency,daily_call_cap,monthly_minutes_cap` -> updates tenant record.

### Frontend
- Dashboard widget on `app/page.tsx`: "Usage this month" (calls, minutes, % of cap, concurrency in use / cap) via `GET /usage`.
- `app/vendors/page.tsx` (admin): add editable limit columns + per-vendor usage from `GET /usage/all`.
- `lib/api.ts`: `getUsage()`, `getUsageAll()`, `setTenantLimits(id, limits)`.

### Effort: Medium (1.5 days backend, 1 day frontend)

---

# TOP P1 (designed briefly)

## P1.A — WhatsApp follow-up after a call (BSP: Gupshup/Interakt/360Dialog)
- Store `WA_TEMPLATES` per campaign in `fields`: `wa_enabled (bool)`, `wa_template_qualified`, `wa_template_noanswer` (template names), `wa_bsp` config in `.env` (`WA_API_URL`, `WA_API_KEY`).
- Trigger: in `run_job` finalize branch, after outcome classification, call `_send_whatsapp(tenant_id, rec, outcome, camp_fields)` which POSTs to the BSP. Map `outcome=="interested"/score>=70` -> qualified template; `no_answer/voicemail` -> brochure/re-engage template. Fire-and-forget with try/except (never block the loop); log result to a new `wa_log.json` (`{tenant_id,phone,template,status,at}`).
- Endpoint `GET /whatsapp/log` for visibility. Frontend: per-campaign WA toggle + template name inputs; a "WA sent" indicator in Call Logs detail.
- Effort: Medium.

## P1.B — Richer analytics: conversion funnel
- New `GET /analytics?campaign_id=&from=&to=` -> buckets computed from `calls.json` + transcripts: `{dialed, connected, answered, interested, callback, qualified(score>=70), opted_out, voicemail, no_answer}` and a funnel array `[{stage,count}]`. Reuse `calls_for(t)` + `_classify_outcome`. No new store.
- Frontend: `app/analytics/page.tsx` with a funnel (Recharts; template already ships Recharts per existing dashboard series chart) + per-campaign dropdown, 30s poll. Nav entry.
- Effort: Medium.

## P1.C — CRM webhook out
- Per-tenant `webhooks.json`: `{tenant_id, url, secret, events:[...], active}`. Admin/vendor endpoint `GET/POST/DELETE /webhooks`.
- Delivery: `_emit_webhook(tenant_id, event, payload)` called from run_job finalize (`call.completed` with summary/score/outcome/transcript-url) and from `/optout` (`lead.opted_out`). HMAC-SHA256 sign body with the tenant secret (reuse the `hmac` import already present). Retry with exponential backoff (3 tries) inside a background task; log to `webhook_log.json`.
- Frontend: `app/settings/page.tsx` section to register a webhook URL + view recent deliveries.
- Effort: Medium.

---

# BUILD ORDER (waves)

## Wave 1 — Backend agent (caller.py + agent.py + prompt.py), in this order
1. Shared scaffolding: `IST`/`now_ist`, `_in_window`, `_clamp_to_window`, new `Path` constants (`SUPPRESSION_FILE`, `RETRY_FILE`), and extend `_coerce_fields` defaults (window + retry fields). (Unblocks everything.)
2. P0.3 prompt.py + agent.py `_llm_opener` + `_summarize` extension (`opt_out`, `callback_at`, `interest` already present). Deploy + verify a real call discloses AI + summary JSON has new keys.
3. P0.4 `_classify_outcome` + stats `answered` correction (pure backend, no deps).
4. P0.2 suppression store + endpoints + dial-time skip.
5. P0.1 window gate in `run_job` + `/run` (uses #1).
6. P0.7 tenant limits + `ACTIVE_CALLS` + `_tenant_usage` + `/usage` (touches run_job dial loop — do after window gate so both gates compose cleanly).
7. P0.5 retry/callback store + `scheduler_loop` (folds in P0.3 opt-out sweep) + `_spawn_retry_job` + `/callbacks`. (Last because it reuses window+suppression+classify.)
8. P0.6 `_update_lead_after_call` + `/leads` score fields/filters (small, after classify+summary land).
9. P1.A/B/C hooks (WhatsApp send, analytics endpoint, webhook emit) — all hang off the SAME run_job finalize branch built in steps 3–8.
- Single touch-point discipline: steps 3,5,6,7,8,9 all modify the `run_job` finalize/dial inner-loop. Implement that block ONCE with clearly ordered sub-steps: suppression-skip -> window-check -> concurrency/cap-check -> dial; and on finalize: classify -> update lead -> enqueue retry/callback -> opt-out suppress -> whatsapp -> webhook.

## Wave 2 — Frontend agent (famit-panel), after each backend endpoint is live
1. `lib/api.ts`: add all wrappers (suppression, optOut, callbacks, usage, analytics, webhooks, extended Lead/RunPayload/CallDetail types). Single PR.
2. `contstants/navigation.tsx`: add Do-Not-Call, Callbacks, Analytics nav items.
3. New pages (clone `app/leads/page.tsx` / `app/calls/page.tsx` patterns, `<Layout>`+`<Card>`): `app/suppression/page.tsx`, `app/callbacks/page.tsx`, `app/analytics/page.tsx`.
4. Edits to existing pages: `app/run/page.tsx` (out-of-window + suppressed toasts, force button), `app/campaigns/page.tsx` (window/retry/WA fields in create+edit form), `app/leads/page.tsx` (score column + hot toggle), `app/calls/page.tsx` (voicemail/no_human/opt_out badges), `app/page.tsx` (hot-leads + usage widgets), `app/vendors/page.tsx` (limits + usage), `app/settings/page.tsx` (webhook registration).
5. Build with `npm install --legacy-peer-deps && npm run build` until exit 0; deploy per HANDOFF recipe.

## Deploy + verify per feature (per HANDOFF)
- Backend: scp caller.py/agent.py/prompt.py -> `famit@168.144.153.145:/opt/famit-agent/`, `sudo systemctl restart famit-caller famit-agent`, curl-verify each new endpoint with `-H "X-Auth: FamitCall2026"`.
- One real test call to 6375548830 to verify: AI disclosure spoken (P0.3), opt-out phrase auto-adds to /suppression and lead->opted_out, a no-pickup -> outcome no_answer + retry enqueued (P0.4/P0.5), window gate queues an out-of-hours run (P0.1), /usage reflects the call + concurrency cap holds (P0.7), lead score appears (P0.6).

# Risk notes
- run_job is the single hot path; all gates funnel through it — keep each check cheap (sets/dicts in memory, JSON reads cached per job, not per tick). Load campaign fields, suppression set, tenant limits ONCE per job; only `_tenant_usage`/`ACTIVE_CALLS` are per-tick.
- JSON stores are read-modify-write without locks today; the scheduler_loop + run_job both write retry_queue.json/leads.json. Serialize writes via a module-level `asyncio.Lock` around `_write` for the shared stores (suppression, retry_queue, leads, calls) to avoid lost updates. Low effort, prevents data loss.
- Never break legacy admin login (`FamitCall2026`) or the voice path (trunk/iptables/Groq model) — all changes are additive.
