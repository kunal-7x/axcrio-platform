# wave-build-run-redesign.md — Run-Page 4-Step Redesign + Voice-Preview Fix

**Branch:** `backend/handoff-name-clean-line`
**Date:** 2026-06-14
**Status:** COMPLETE — Phase 0 (BE) + Phase 1 (FE) + Phase 2 (Deploy) + Phase 3 (Verify) ALL PASS

---

## What was built

### Phase 0 — Voice-Preview Backend Fix (BE only)
**Root cause:** `GET /voice-preview` gate used `authed(request)` → `resolve_tenant` → `_extract_cred` which reads the JWT ONLY from the `Authorization` or `X-Auth` HEADER. An `<audio src=...>` tag CANNOT send headers. The FE (`lib/api.ts voicePreviewUrl`, `_voice-providers.tsx:227`) already passed the token as `?t=<jwt>`, but the backend IGNORED the query param → 401 → swallowed by `.catch` → "no voice preview".

**Fix applied (`droplet_work/caller.py` lines ~3392-3406):**
- Before `authed(request)`, read `_t_param = request.query_params.get("t", "")`
- If header auth passes → proceed normally (unchanged)
- If header auth fails AND `t=` absent → 401 (unchanged)
- If header auth fails AND `t=` present → validate via `resolve_tenant(_FakeReq(_t_param))` (lightweight adapter presenting the token as a Bearer header, the SAME `_extract_cred` path) → 401 if invalid, proceed if valid
- Scope: THIS route only (returns a public sample mp3/wav — no spend, no PII)

**Verify (read-only, no calls):**
- `GET /voice-preview?provider=elevenlabs&id=test` (no auth, no t=) → **401** PASS
- `GET /voice-preview?provider=elevenlabs&id=test&t=invalid` → **401** PASS
- `GET /voice-preview?provider=elevenlabs&id=bogus_id&t=<valid_hmac>` → **404** (auth PASSED, ElevenLabs not-found) PASS
- No FE change needed — FE already sends `?t=`

**Commit:** `e275ebc` on `backend/handoff-name-clean-line`
**Box backup:** `/opt/famit-agent/caller.py.RUNbak.20260614-025131`

---

### Phase 1 — Run-Page 4-Step Redesign (FE only)

**Problem:** `app/run/page.tsx` (~949 lines) was ONE 26rem left rail stacking SEVEN cards in a max-h scroll. All functionality fine; the IA was the problem.

**Architecture (pure presentational re-housing — NO state migration, NO API changes):**
- Single `const [step, setStep] = useState(0)` added to the existing RunPage component
- All handlers, `buildRunPayload`, queue/force logic, `getStatus` poll + liveLeads table PRESERVED verbatim

**4 Steps:**
1. **Campaign & Audience** — campaign Select + audience builder where the 4 source modes (All stored / By temperature / By upload / Pick manually) become a Tabs row; only the active mode renders (progressive disclosure). Live audience-count chip in step header.
2. **Voice & Providers** — reuses `app/run/_voice-providers.tsx` verbatim, given a full step to breathe. Cost-meter/projected ₹ feeds the summary rail.
3. **Pacing & Handoff** — Pacing field grid (concurrency/hourly/daily) + HandoffTeam compact.
4. **Review & Launch** — read-only summary grid + off-window queue notice + big Launch button (`isBlack icon="send"`) + "Start anyway" affordance (all `handleStart`/`buildRunPayload`/queue logic verbatim). Live Status (getStatus poll + liveLeads table) renders below step 4 once a jobId exists; launching auto-advances to step 4.

**New file: `app/run/_stepper.tsx`** (~80 lines)
- Horizontal, clickable on completed steps, locks ahead until step 0 (campaign) is valid
- Composed from `Button` + `Icon` + Core_2 tokens (`text-button`, `bg-b-surface2`, `shadow-depth`, `border-s-subtle`, `primary-01/02`)
- Mirrors the proven 3-stop segmented pattern in `_voice-providers.tsx:362-401`
- `role=tablist`, each stop `aria-current="step"` when active
- Mobile (max-lg): stepper → compact "Step N of 4" pill + dots, NO horizontal scroll; summary rail → sticky bottom bar (step number + Launch)

**Sticky right-hand Launch-summary rail (always visible):**
- Campaign name, audience count + hot badges, tier + ₹/min, projected ₹, pacing, handoff count, big Launch button
- Composed from `.card`/`.surface` + `.kpi`/`.kpi-label`/`.kpi-value` + `Badge` — pure Core_2

**CSS addition:** `.step-reveal` staggered reveal in `globals.css` (CSS-only, no JS animation lib)

**Commit:** `6923b45` + learnings `ba1f63a`

---

### Phase 2 — FORTRESS Deploy

**Local build:** `npm run build` EXIT 0, /run = 16.8 kB, zero TS errors
**Tarball md5:** `638736b0cc2b6461361489e2bd79924c` — matched on box
**Box backup:** `/opt/famit-panel.bak-<timestamp>`
**BUILD_ID before:** `p6hSTJX9R46-NQdLf8Daw`
**BUILD_ID after:** `jcDEy4iclWbxS_zvVpvk0`
- Atomic `.next` swap
- `chown deployuser` applied
- `systemctl restart famit-panel` — service active
- Loopback `http://127.0.0.1:3001/` → 200
- `/run` route loopback → 200
- Edge `https://panel.famit.in/` → 200
- Recent 5xx count → 0

---

### Phase 3 — Honest Integrated Verify (read-only, NO calls)

| Check | Result |
|---|---|
| `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` | UNCHANGED |
| `famit-agent` active, MainPID 1477083 never restarted | PASS |
| `famit-caller /health` (:8209) | 200 |
| `famit-panel` active on FORTRESS | PASS |
| BUILD_ID on FORTRESS | `jcDEy4iclWbxS_zvVpvk0` (new, deployed) |
| Loopback `/` | 200 |
| Loopback `/run` | 200 |
| Loopback `/login` | 200 |
| Edge `https://panel.famit.in/` | 200 |
| 0 real 5xx (304 Not Modified = false positive, excluded) | PASS |
| Voice-preview: no auth + no t= → 401 | PASS |
| Voice-preview: invalid t= → 401 | PASS |
| NO outbound call placed (DID resting) | PASS |

**What only the founder's real click can prove:**
- The stepper renders with 4 steps (no giant scroll)
- Step 2 voice preview: click ▶ on a voice → audio plays (307→GCS mp3 / Sarvam wav)
- Launch + "Start anyway" still build the correct payload and queue a job
- Live Status still polls once jobId exists

---

## Residuals

- `lib/api.ts:801-803` comment still references a Next.js rewrite that doesn't exist (nginx on FORTRESS proxies `/api`; the note is cosmetic only — code is correct)
- OB-PROV (outbound provider honor in `agent.py`) is still Phase-2 gated (separate wave, founder sign-off, DID un-rested)

---

## Earner gate summary (all green)

```
agent.py md5  = 9150fabe4ff62b4b4470f9a87df346e5  UNCHANGED
famit-agent   = active, PID 1477083, never restarted
famit-caller  /health (:8209) = 200
famit-panel   = active on FORTRESS
0 real 5xx    = confirmed
NO call placed (DID RESTING per hard rule)
```
