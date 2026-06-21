# W-FRONTEND-RECONCILE — Additive Restore (nav) + Keep New Dashboard + Wire Filters

**Status:** DESIGN READY · 2026-06-19 · branch context `fix/realtime-voice-kernel-v2` (feature pages live on disk) / `fix/callback-retry-scheduling` (current)
**Author:** architect (subagent)
**Earner safety:** FE-only. Touches `famit-panel/` nav + report binder ONLY. Zero box/voice/caller.py mutation.

---

## 0. The decision (one sentence)

The W15 "consolidation" **hid** ~15 feature routes (the whole Creative Studio suite, the AI-Manager sub-pages, Callbacks, Communication, Leads, Do-Not-Call, Vendors) behind a minimal rail and shipped a good new dashboard whose GlobalFilters don't actually filter. The live panel is **already rolled back** to the full pre-W15 product (interim relief — founder sees everything again). This plan makes that reconciliation **permanent and additive**: END STATE = the **full feature nav** (nothing removed) **+** the **new W15 dashboard kept at `/`** **+** the dashboard **GlobalFilters wired to real endpoints**. We restore the NAV; we do **not** rebuild pages (they exist on disk).

**Why additive, not "revert W15":** the W15 dashboard (`app/page.tsx`, GlobalFilters, LeadBadge, report binder) is genuinely better and the founder likes it. The damage was purely the *nav IA* dropping links + the filters being inert. So: keep the new home, un-hide every route, fix the fetch. Remove nothing.

---

## 1. NAV RESTORE — exact file + edits

**Single file to edit:** `famit-panel/contstants/navigation.tsx`
(Render path unchanged: `components/Sidebar/index.tsx` → `Dropdown` renders any group `list[]`; `resolveNav` already honours `feature_key`/`roles`. No component change needed — collapsible groups already work, the Billing group proves it.)

The current file ships the W15-collapsed rail (6 task groups). We **add back** the dropped children as real grouped sub-entries, keeping the new task-group names the founder likes. Every restored entry keeps its **verbatim `feature_key`** (MAP 1/MAP 3 list) so entitlement gating is unchanged.

### 1a. Restore the Creative Studio sub-suite (MAP 2 — the loudest loss)

In the **GROW** group, replace the single flat `Creative Studio` link (line 107) with a **collapsible group** exposing all four real routes:

```ts
// REMOVE: { title: "Creative Studio", href: "/creative" },
// ADD (collapsible group — sub-routes are REAL pages on disk):
{
    title: "Creative Studio",
    icon: "image",
    list: [
        { title: "Image Studio", href: "/creative" },
        { title: "Video Studio", href: "/creative/video" },   // FEATURE_VIDEO_STUDIO-gated page, real
        { title: "Asset Library", href: "/creative/library" },
        { title: "Brand Kit", href: "/creative/brand" },
    ],
},
```
This single change un-orphans `/creative/video`, `/creative/library`, `/creative/brand` (MAP 2: today only reachable by typing the URL or an in-page button). No tab scaffold needs building — the four pages already render standalone.

### 1b. Restore the AI-Manager sub-pages

In **WORK**, replace the single `AI Manager` link (line 88) with a collapsible group that keeps the single-link gate (`mod.ai_manager`) on the group and lists the 9 real sub-routes (all pages exist, MAP 1):

```ts
{
    title: "AI Manager", icon: "ai", roles: "manager", feature_key: "mod.ai_manager",
    list: [
        { title: "Overview",         href: "/ai-manager/overview",       feature_key: "ai_manager.overview" },
        { title: "Live Calls",       href: "/ai-manager/live" },
        { title: "Command Center",   href: "/ai-manager/command-center" },
        { title: "Handoff Team",     href: "/ai-manager/handoff" },
        { title: "Try it",          href: "/ai-manager/test",            feature_key: "ai_manager.test" },
        { title: "Command History",  href: "/ai-manager/commands",        feature_key: "ai_manager.commands" },
        { title: "Pending Approvals",href: "/ai-manager/approvals",       feature_key: "ai_manager.approvals" },
        { title: "Capabilities",     href: "/ai-manager/capabilities",    feature_key: "ai_manager.capabilities" },
        { title: "Setup",           href: "/ai-manager/setup",           feature_key: "ai_manager.setup" },
        { title: "Team",            href: "/ai-manager/users",           feature_key: "ai_manager.users" },
    ],
},
```
> Note: the W15 in-page tabs were never built (MAP 2 confirms the same pattern for Creative — "intent, not reality"). Restoring sidebar children is the safe path because every child page already renders standalone. If in-page tabs later ship, they coexist (children just deep-link to the same routes).

### 1c. Restore the folded standalone links

- **Callbacks** — add to WORK after Call Logs: `{ title: "Callbacks", href: "/callbacks", feature_key: "engage.callbacks" }`. (`/callbacks` page was gutted to a redirect shell to `/calls?tab=callbacks` in 617febd — the link still works; if the founder wants the *old* full callbacks page, it lives on `fix/realtime-voice-kernel-v2` — restore that page file too. Default: keep the tab redirect, the link just lands on the calls callbacks tab.)
- **Communication** — add to MESSAGE: `{ title: "Communication", href: "/communication", feature_key: "engage.communication" }`. Real page exists (MAP 1); W15 dropped it with no replacement entry.
- **Leads (standalone)** — add to WORK after Leads & CRM: `{ title: "Leads", href: "/leads", feature_key: "sell.leads" }`. Real page exists; W15 folded it into a CRM tab but the standalone page is on disk.

### 1d. Super Admin — close the genuine gap

Add the **one missing real page** (MAP 1 key finding) to the Super Admin `list[]` (after line 194):
```ts
{ title: "API Keys", href: "/super-admin/api-keys", roles: "admin" },
```

### 1e. Footer (navigationUser) — already correct

`Settings` / `Do-Not-Call` (`/suppression`) / `Vendors` (`/vendors`, admin) are already in `navigationUser` (lines 207–211). Keep as-is — those routes are reachable via the avatar dropdown. (Optional polish: also surface Do-Not-Call + Vendors in the main rail if the founder wants them visible without the avatar menu — but footer is non-orphaning, so this is cosmetic, not a fix.)

**Net nav result:** every route in MAP 1's "EXISTS ON DISK BUT MISSING FROM NAV" table is now reachable from the sidebar (except dynamic `[id]` detail pages and `/login`, which are correctly never in nav). Nothing W15 added is removed — group names (Work/Grow/Message/Intelligence/Money/Build) stay.

---

## 2. KEEP THE NEW DASHBOARD AT `/`

**No change needed.** `navigation.tsx:76` already points `Dashboard → "/"`, and `app/page.tsx` is the new W15 cockpit (DashboardInner + GlobalFilters + LeadBadge). The reconciliation does **not** touch `app/page.tsx`'s layout — it only fixes the data the filters fetch (§3). The new dashboard stays the home page exactly as W15 shipped it.

---

## 3. WIRE GlobalFilters → REAL DATA (per MAP 4)

**Root cause (MAP 4):** filters correctly update URL state and re-trigger `getReport()`, but the live fallback `composeReport()` (the `/report` seam is NOT mounted on the box → always 404 → always falls here) calls `getStats()`/`getAnalytics()`/`getLeads()` **without forwarding** `range`, `campaign`, or `status`. So every filter change re-fetches identical all-time data.

**Verified ground truth (already on disk):**
- `getAnalytics(opts?: { campaign_id?, from?, to? })` — `lib/api.ts:1779` — ALREADY accepts `from`/`to`. Just not passed.
- `getLeads(opts?: { hot?, sort?, batch?, limit?, offset? })` — `lib/api.ts:559` — does NOT yet accept date/campaign/status. Must extend.
- `getStats()` — `lib/api.ts:1606` — no params; `/stats` is not range-parameterised on the box. Leave all-time + label honestly.
- `ReportFilters` (`lib/report.ts:188`) already has `campaign`, `lead_status`. No type change needed for filters.

### Fix 1 — forward `range` to `getAnalytics` (`lib/report.ts:268-270`)

```ts
getAnalytics({
    ...(filters?.campaign ? { campaign_id: filters.campaign } : {}),
    ...(range.from ? { from: range.from } : {}),
    ...(range.to ? { to: range.to } : {}),
}).catch(() => null),
```
Immediately makes the funnel + connected/interested/booked counts date-range-aware (endpoint already supports it).

### Fix 2 — extend `getLeads` to accept date/campaign/status (`lib/api.ts:559-571`)

Add optional params and forward as query string:
```ts
export async function getLeads(opts?: {
    hot?: boolean; sort?: string; batch?: string; limit?: number; offset?: number;
    from?: string; to?: string; campaign_id?: string; status?: string;
}): Promise<LeadsPage> {
    const params = new URLSearchParams();
    if (opts?.hot) params.set("hot", "1");
    if (opts?.sort) params.set("sort", opts.sort);
    if (opts?.batch) params.set("batch", opts.batch);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.offset != null && opts.offset > 0) params.set("offset", String(opts.offset));
    if (opts?.from) params.set("from", opts.from);
    if (opts?.to) params.set("to", opts.to);
    if (opts?.campaign_id) params.set("campaign_id", opts.campaign_id);
    if (opts?.status) params.set("status", opts.status);
    // ...rest unchanged
```
> The live `/leads` endpoint may ignore params it doesn't support — that's safe (no error). Client-side classification (report.ts:284-310) still works; where the backend filters, the result narrows correctly. If `/leads` ignores `status`/`from` server-side, do a **client-side post-filter** in `composeReport` as a guaranteed fallback (see Fix 2b).

### Fix 2b — pass the filters into `getLeads` in `composeReport` (`lib/report.ts:271`)

```ts
getLeads({
    limit: 500,
    ...(range.from ? { from: range.from } : {}),
    ...(range.to ? { to: range.to } : {}),
    ...(filters?.campaign ? { campaign_id: filters.campaign } : {}),
    ...(filters?.lead_status ? { status: filters.lead_status } : {}),
}).catch(() => ({ leads: [] as Lead[] })),
```
**Guaranteed client-side fallback** (so the filter visibly works even if the box ignores the params): after fetching, before the classification loop, filter `leads` by `range` (on `last_call_at ?? added_at`) and by `lead_status` (map the status dropdown value onto the same tier logic at lines 285-309). This makes the dropdown *always* narrow the KPIs/hot-leads even on the un-upgraded box.

### Fix 3 — `getStats()` stays all-time; label it honestly

`/stats` has no date param. Leave the "Total calls" KPI all-time and surface the existing `live_seam: false` flag in the UI as an "all-time" chip on that one tile (the report already returns `live_seam:false`; `app/page.tsx` should show the chip — small UI note, not a data fix).

### Fix 4 — "All campaigns" clear in CampaignSelect (`components/CampaignSelect/index.tsx` + `components/GlobalFilters/index.tsx`)

CampaignSelect has no "All campaigns" option, so once a campaign is picked the URL param sticks (MAP 4 Gap 4). Add a synthetic first option `{ id: 0, name: "All campaigns" }`; in `handleChange`, when `id===0` emit `null`. In `GlobalFilters/index.tsx:136`, change the handler to `patch({ campaign: c ? c.id : null })` so selecting "All" clears the URL param.

**Acceptance for §3:** switch range Today→30d and watch funnel + connected/booked counts change; pick a campaign and watch KPIs + hot-leads narrow (not just the funnel); pick a status and watch tiers narrow; pick "All campaigns" and watch it reset. URL params persist + are shareable.

---

## 4. BUILD / DEPLOY SEQUENCE (next phase, serialized, FE-only)

1. **On branch `fix/realtime-voice-kernel-v2`** (where the feature pages live on disk) — make ALL §1 nav edits + §3 filter edits in one FE branch. One file for nav, two for filters (`lib/report.ts`, `lib/api.ts`), two for the campaign clear (`CampaignSelect`, `GlobalFilters`).
2. `npm run build` green (the only gate — pages already exist, so no missing-route 404s).
3. Smoke locally: open every restored nav link → 200, not 404. Exercise the 4 filter cases in §3.
4. Deploy to FORTRESS panel (`143.110.247.249`) per the standard panel deploy recipe; verify `BUILD_ID` bumps + every restored route resolves on the live edge.
5. **Founder real-flow check** (the only truth): he sees the full nav (Creative suite + AI-Manager subs + all routes), the dashboard at `/` unchanged, and the filters actually move the numbers.

**Revert path:** pure FE; `git revert` the nav/filter commit + redeploy. No box/voice touch, earner untouched throughout.

---

## 5. CONSOLIDATED PLAN / STATUS (per MAP 5 + MAP 6)

### (a) DONE + LIVE (flags ON, founder-verified)
- **Inbound voice** (`aim_voice_agent.py`, `KERNEL_INBOUND=1`): RealtimeVoiceKernel v2 LIVE (357 tests, founder "PERFECT"); MLV multilingual adaptive (per-turn STT auto-detect); Sarvam bulbul:v3; ctx-cache; PG lead_memory/episodes; never-silent guard; `INBOUND_PROV_LOCK=1`; P0 cross-tenant leak CLOSED.
- **Outbound earner** (`agent.py` md5 `76a93f0a`, `KERNEL_OUTBOUND=0`): A2 surgical AI-self-label fix LIVE, voice byte-identical; rollback golden `98655dbf`.
- **Backend caller.py** (`44b867ea`): Run Platform A+B+C; Provider Registry W1-W5 (`PROVIDER_REGISTRY_ENABLED=1`); RAG W0-W3+W7 (`RAG_INJECT_ENABLED=1`); Video Studio (`FEATURE_VIDEO_STUDIO=1`); Foundation Control Layer (18/18 T1-T18, `CONTROL_ENABLED=1`); ACID Wallet+Firewall; WhatsApp B1/B2/C2; recordings; LLM pool; handoff.
- **Panel/FE** (FORTRESS): Integrations + Video Studio FE; perf overhaul; asset-presign + CRM transcript fixes; AIM sessions page. **NOW: rolled back to FULL pre-W15 product (full nav + all features visible to founder again — interim relief).**
- **W-WIRE-OPS:** live-data backbone wired into caller.py + deployed DORMANT (flags OFF, earner untouched).
- **Infra:** 3-box FORTRESS egress-locked; Cloudflare Full Strict; gitleaks CI; Hatchet-lite + Logto deployed (not in request path).

### (b) BUILT but NOT DEPLOYED / dormant-flagged
- **Voice-heart outbound brain fix** — fully built + committed (`fix/callback-retry-scheduling`, 931 pytest green, 16 gates, 5/5 golden replays). U1 brain_packs, U2 R11-R15 gates, U3 bad-transcript replay, U4 deployable agent.py hunks A/B/C/H/I/J/D + static OFF-identity proof. `KERNEL_OUTBOUND=0` default → box byte-identical to `98655dbf`. **GATED on founder test call.**
- Voice kernel outbound (W-INT-OUTBOUND, 318 tests, `KERNEL_OUTBOUND=0`); W8-W14/W20/W24/W25 voice_ops modules built, flag-OFF, NOT wired (the WIRING PHASE).
- **W15 UI-consolidation + W16 WhatsApp-media** — npm green, NOT deployed (and W15 nav is what this plan supersedes additively).
- **THIS PLAN's FE reconcile** — designed, not built.
- Telephony T1+T2+T3 (deployed, `TRUNK_REGISTRY_ENABLED` OFF); T4 FE not built; ADS engine flip-ready; cost-meter re-tune pending; Growth OS Phase-0 local only.

### (c) PENDING / not started
- **T0 scheduler retry-bug** (`caller.py:scheduler_loop`, ~5 lines) — exhausted-retry re-fire auto-dialed 6 numbers + deepened carrier block. Queue PAUSED. **HARD GATE before any campaign resume / telephony T5.**
- W12 compliance engine (NOW-BUG: default window `09:00-21:00` is out of legal 10:00-19:00 IST bounds); W24 concurrency harness (hard deploy gate); DPDP erase; mid-call `lead_is_hot` tool; post-call workflow event; inbound recording egress/spend metering; Run audience-builder UX; Communication W1-W3; Vault V0-V8; LiveKit semantic turn-detector; AIM dedicated service; Logto/Hatchet caller.py wiring; LoRA.

### (d) VOICE-HEART PRIORITY — what remains before a founder test call (MAP 6)
The **build wave is COMPLETE**. No code remains — only the **7-step founder-gated deploy** (box ops, instant revert always armed):
1. Pre-flight: confirm box `agent.py` md5 `98655dbf`, `KERNEL_OUTBOUND` unset, no drop-in; back up `agent.py` + `.env` timestamped.
2. Apply hunks A/B/C/H/I/J to box `agent.py` (re-locate per `design/W-VOICE-HEART-DEPLOYABLE-PATCH.md`); deploy tracked `voice_kernel/` package.
3. **OFF-identity ring:** restart, one real outbound call, confirm zero behavioral change (hunks inert) — proves gating.
4. Install systemd drop-in with ONLY `EL_STABILITY=0.45` + `EL_SPEED=1.08` (no `KERNEL_OUTBOUND` yet); verify env didn't leak to inbound; ring → OLD brain in constant inbound voice.
5. Flip: uncomment `KERNEL_OUTBOUND=1`, `daemon-reload && restart`.
6. **Founder test call (only acceptance truth):** single greeting, name once at normal volume, all LLM-generated (no "ok perfect"/hardcoded bye), natural Hinglish, constant pace. Watch journal for double-greet / `session.generate_reply()` crash.
7. Revert: comment `KERNEL_OUTBOUND=1` + restart = old brain + good voice; delete drop-in = byte-identical `98655dbf`.

**One real-ring unknown:** whether `session.generate_reply()` (Hunk H greeting kickoff) is supported on the box's pinned `livekit-agents` — the `try/except` fails open to natural turn-1, never crashes.

**Priority order:** Voice-heart deploy (founder-gated, no code) and this FE reconcile (FE-only, no box) are **independent and parallel-safe** — neither touches the other's surface. T0 scheduler fix remains the hard gate for any *dialing/campaign* work but does NOT block either of these two.
