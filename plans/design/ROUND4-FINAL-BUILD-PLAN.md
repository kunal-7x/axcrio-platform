# ROUND4 — FINAL BUILD PLAN (production ship)

Synthesized from 3 audits (orphans/wire-up · frontend · github/readiness/research), 2026-06-19.
This file is what the build workflow executes. Order is by dependency; parallel-safe lanes are flagged.

## THE ONE LAW (non-negotiable, every wave)
- `caller.py` = **famit-caller service ONLY**. NEVER touch `famit-agent`.
- Voice path **byte-identical**: `agent.py` TTS region (lines 540-640, live md5 `f20e1348`) unchanged; `.env` asserts `EL_STABILITY=0.55` + `EL_SPEED=1.08` (grep `.env` every deploy — code default 0.65 is the broken value, md5 alone won't catch drift).
- One box-mutating change at a time, each backed up + one-command rollback (golden `*.PERFECTgolden.20260618-210445`).
- Panel: ship pre-built `.next` — NEVER `npm run build` on the box (OOM-kills it). `images.unoptimized:true` makes the local `.next` Linux-safe.
- A green per-component report ≠ production. The gate is the FOUNDER's real integrated flow.

Ground truth on box: `caller.py` md5 `6a7acd06` (past P2), `agent.py` `b529c22c`. Flags ON: `KERNEL_OUTBOUND=1 W5_SPEECH=0` (agent); `EVENTBUS/RECORDING_FINALIZE/REPORTING/LEAD_LIFECYCLE=1`, `RAG_INJECT_ENABLED=1`, `AIM_ENABLED=1`, `FEATURE_BOOKING=1` (caller).

---

## (A) BACKEND WIRE-UP — famit-caller / voice_kernel / panel only, flag-gated, earner-safe

Lanes A1–A6 touch **different files** → parallel-safe except where noted. Each: fix → verify → restart **famit-caller** (A3 = famit-agent kernel-only restart).

### A1. RAG retrieval into outbound calls — `voice_kernel/integrations/outbound.py` [HIGHEST VALUE, voice-safe]
- **Bug:** line 253 `build_rag_runtime()` called with NO `corpus=` arg → falls back to Null/InMemory backend (line 249) despite `kb_chunks` having 188 rows. Uploaded PDFs never reach the live brain.
- **Fix:** `impls["rag"] = build_rag_runtime(corpus=KbCorpusBackend(tenant_id=...))` (production backend in `voice_kernel/rag/backends.py`, wraps `kb/core.py`). Confirm the kernel actually consumes `RAG_INJECT_ENABLED=1` (in `.env`, no agent.py ref yet — verify the kernel reads it).
- **Deploy:** famit-agent restart (kernel-only change; voice byte-identical, no TTS touched). Verify via `/kb/test-retrieve` then a real call where the lead asks a KB-answerable question.

### A2. Callbacks / retry firing — `caller.py` drop-in + `voice_ops/callback.py` [GATED ON T0 BUG]
- **State:** enqueue works (`_enqueue_retry` caller.py:1863 → `var/retry_queue.json`, W10 `enqueue_smart` at :3021). Firing disabled: `scheduler_loop` (:7808) only dials when `RETRY_SCHEDULER_ENABLED` truthy (:7835), defaults `0` (spam kill-switch :447-455).
- **GATE (do FIRST):** verify the T0 retry-bug is fixed in `voice_ops/callback.py fire_due` — this is the reason the kill-switch exists. Do NOT flip until confirmed.
- **Compliance clamp (from research — REQUIRED):** "call me at 5am" must clamp into India legal window **9 AM–9 PM, lead-local TZ**; scrub DND/NCPR before dialing; ≤2-3 attempts/day, vary time-of-day across attempts, rotate caller-ID. Add the window-clamp in `_enqueue_retry`/`fire_due` before enabling.
- **Fix:** add to `/etc/systemd/system/famit-caller.service.d/*.conf`: `Environment=CALLBACK_CADENCE_ENABLED=1`, `Environment=RETRY_SCHEDULER_ENABLED=1`. Anti-spam guards (`max_attempts`, `_add_suppression`, backoff) already present.
- **Deploy:** restart famit-caller. Fired callback → `_finalize_call` → EVENTBUS → `/report` → Call-Logs.

### A3. Booking voice-tool + Google Calendar — `voice_kernel/integrations/outbound.py` + `booking/calendar_sync.py`
- **Gap 1 (booking not called from voice):** outbound agent never calls `POST /booking/book`; a verbally-agreed visit is only captured as `tr.booked` text. **Fix:** add a booking tool to the kernel tool-surface (`outbound.py`) that calls `POST /booking/book` when a slot is agreed. (Inbound: `aim_voice_agent.py`.) Voice-safe.
- **Gap 2 (GCal stub):** `booking/calendar_sync.py:_client()` returns `None`. **Fix:** set Google OAuth client + refresh-token env + `BOOKING_CALENDAR_SYNC=1`; finish `_client()` (build `Credentials` + `googleapiclient.discovery.build`); call `push_event` from `booking/core.py` on book/reschedule/cancel.
- **Deploy:** famit-caller + new creds. NOTE: shares `outbound.py` with A1 → **sequence A1 then A3** (same file, no parallel).

### A4. Creative Studio super-admin entitlements — `var/control/registry.json` + panel matrix
- **Gap:** `feature_registry` has 91 keys but ZERO `creative*/studio*/brand_kit*/render_brain*/script*` keys → Creative Studio is NOT governable by HIDE/LOCK/ON. **Fix:** add the missing keys to `registry.json`; the C3 middleware (HIDDEN→404, LOCKED→402) and panel matrix (`super-admin/vendors/[id]/page.tsx`) auto-render them. Parallel-safe (own file).

### A5. Brand-kit persistence — `caller.py` (famit-caller) + panel `app/assets`
- **Gap:** caller `:8209` has `/extract` (URL→brand) but NO `/brand-kits` GET/POST persistence and NO `/creative/*` image routes (only `/creative/video/*`). Panel brand page binds `/api/assets/brand-kits` → no backend → save NOT wired.
- **Fix:** add `GET/POST /brand-kits` (RLS-scoped, `ai_asset_*` schema) to famit-caller; wire the panel brand page to it. Parallel-safe.

### A6. Groq key exhaustion-awareness — `agent.py` (brain/logic only) [LOWER PRIORITY, voice-safe]
- **Gap:** `_next_groq_key` (agent.py:77-120) is pure round-robin — no 429 detection; exhausted key stays in cycle. **Fix:** wrap the per-call Groq client so a 429/quota error marks that key cooling (timestamp); `_next_groq_key` skips cooling keys (port the cooling logic from the provider-key pool). No TTS touched. Lowest priority.

**Already WORKING (no code) — founder-test only:** AI-Manager add-number+PIN+inbound-routing (A.5 audit), support tickets/workflows/webhooks (A.6 audit), super-admin 91-key matrix (A.7).

---

## (B) FRONTEND PREMIUM — panel-only, reuse Core_2 ONLY, ship pre-built `.next`

Most of the round-4 "broken" list is ALREADY built (call-history pagination/sort/recording/karaoke; CRM sort/delete/temp/lifecycle; CRM-profile recordings+transcript slide-over; run wizard; super-admin transparent tabs; AI-Manager 4-tab). Do NOT rebuild. Lanes B1–B4 are **different pages** → parallel-safe.

### B1. Dashboard — `app/page.tsx` [chart variety]
- Lead-temp pie (:454) → Core_2 `CardChartPie` donut w/ center total. Outcome `BarChart` (:410) → RadialBarChart. Top-campaigns "over-big" `col-span-2` (:496) → single column, top-3, `Sparkline` per campaign. Replace local `Kpi` (:925) with Core_2 `KpiCard` (spark/meter/tone). Fill right column: mini calls-by-hour heatmap + Bookings/Callbacks radial. Hot-leads/temp data path is correct (`report.by_status`/`hot_leads`); empty display = upstream live-data (A2/reporting), UI fine.
- Reuse: `Card`, `CardChartPie`, `KpiCard`, `Sparkline`, `Percentage`, recharts `RadialBarChart` (only new import).

### B2. Reports — `app/analytics/page.tsx` [DAY-FILTER BUG]
- **Bug:** `:66` calls `getAnalytics({campaign_id})` — never passes `range.from/to`, so day-filters do nothing. Also `lib/api.ts:1873` path typo `` `${BASE}\analytics` `` (backslash) breaks on Linux → `/analytics`.
- **Fix:** read shared range via `useGlobalFilters()` (already imported :49) and call `getReport(range, {campaign})` from `lib/report.ts` (forwards from/to at report.ts:327).
- Funnel (:146 `FunnelChart` h-80) shows ratio + stretched → port dashboard's compact h-funnel rows (page.tsx:657-685, shows `{count}` + `step_conv%`), capped height.
- Add area-Trends + temp donut (`CardChartPie`). Add CSV/Excel **Download** button (client-side blob, `URL.createObjectURL`, no backend route).

### B3. Run Campaign — `app/run/_voice-providers.tsx` [card-split]
- The one-big jargon card (`:393`, 7 sections) → split into 3: **Quality & Voice** (tier slider :425 + voice dropdown :629); **Cost estimate** (avg-call + `CostBreakdown` + `TierCompare` + CPL :518-604); **Providers** (health :606 + ProviderLock + Advanced :722). Bump labels `text-sub-title-1`, helper `text-body-2`. Wizard/retention/CSV+XLSX/manual-pick already present.

### B4. Call Logs warm-lead + polish — `app/calls/page.tsx`
- Add 4th `CALL_TABS` tab (:701) "Warm leads" — tier 40–69 contacts + AI-summary + "schedule follow-up". (Only genuine new build here.) Karaoke t0/t1 falls back gracefully until backend emits timing — no UI work.

### B5. Polish (cross-page, cheap)
- CRM `handleDelete` (:132) deletes immediately → add `confirm()` to match "delete with confirmation EVERYWHERE". AI-Manager `_home.tsx` AimStat strip (:197) → Core_2 `KpiCard`. Audit remaining raw `<select>` in `app/whatsapp`/`app/funnels` → Core_2 `Select`.

---

## (C) VOICE DEEPEN — earner-safe, voice byte-identical
- A1 (RAG corpus) and A6 (Groq cooling) are the voice-adjacent items — both brain/logic only, no TTS region touched. No additional voice-path changes in this round.
- Every voice/agent deploy: grep `.env` for `EL_STABILITY=0.55`/`EL_SPEED=1.08`, md5 the TTS region, off-hours restart (drops active calls — H12), golden rollback armed.

---

## (D) GITHUB PUSH (secure) + DEPLOY + VERIFY

### D1. Secure push (gitleaks 0 — tracked tree is CLEAN today)
- History (292 commits) + tracked tree: `gitleaks detect` = **0 leaks**. Working-tree `--no-git` = 247, ALL in ignored/untracked files.
- **NEVER `git add -A`/`git add .`** — that stages Risk-A secret files. **Stage selectively** → `gitleaks protect --staged --no-banner` must print **0** → commit.
- **Harden `.gitignore` FIRST** (closes Risk A): append `.boxsrc/`, `_inbound_ref/`, `autonmous/`, `research/agents/`, `request2.md`, `MAX_AUTONOMY_PROMPT.md` (root + `autonmous/`).
- **Risk B (optional, before any new droplet_work add):** `git rm -r --cached droplet_work/` in a dedicated commit (118 tracked files; clean today but violates "not in git" intent).
- Push branch `fix/realtime-voice-kernel-v2`; open PR into `feat/premium-ui`. Never push to a shared default.

### D2. Deploy order
1. famit-caller drop-in flags (A2 — only after T0 gate) + A4/A5 routes → restart **famit-caller**.
2. famit-agent kernel (A1 then A3 booking-tool; A6 if done) → off-hours restart, golden armed.
3. Panel: build `.next` LOCALLY, scp to box, swap, public 200. Current `.next` id `LcX_6UESoY4uHwPqjey7l`.

### D3. Production-readiness gate (must be TRUE to call it shipped)
- Founder real-call test PASSED on current stack (`KERNEL_OUTBOUND=1`/`W5_SPEECH=0`) — only the live call is truth.
- After a real call: dashboard/CRM show REAL data within seconds; date/campaign/status filters change results; TZ-correct timestamps; recording finalizes + plays on Call-Logs detail AND CRM profile.
- `/report` returns 200 with real numbers; `voice-ops-reporting.service` active; W7 DDL applied.
- In-memory reporting store → PG before "real" dashboard (C3 — restart wipes history).
- H10: legacy default-password token (`LEGACY_TOKEN_ENABLED`/`CALLER_PASS`) DISABLED before a 2nd tenant (bypasses RLS).
- gitleaks 0 on pushed tree; secrets only in out-of-band `.env`.

---

## EXECUTION SEQUENCE (dependency-ordered)
1. **D1 .gitignore hardening** (instant, unblocks safe commits) — solo.
2. **Parallel lane 1 (backend):** A1(RAG) → then A3(booking, same file). **Parallel lane 2:** A4(registry), A5(brand-kit), A6(Groq) — independent files.
3. **A2(callbacks) GATED** on T0-bug verification + compliance clamp — do not flip until both done.
4. **Parallel (frontend):** B1, B2, B3, B4 — independent pages; B5 polish last.
5. **D2 deploy** (caller → agent off-hours → panel pre-built).
6. **D3 founder real-call gate** = the only success signal.
