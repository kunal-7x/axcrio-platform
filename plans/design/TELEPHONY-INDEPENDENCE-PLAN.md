# TELEPHONY-INDEPENDENCE-PLAN — own/flexible trunk registry on LiveKit-SIP

> **Status:** DESIGN-COMPLETE + RED-TEAMED (4 adversarial passes folded). Decision-ready.
> **Date:** 2026-06-14 · **Mode of this doc:** synthesis of the READ-ONLY design wave
> (`memory/wave_runs/telephony-independence-megaplan.md`, 1212 lines). No box / `caller.py` /
> `agent.py` mutation by this wave. The live Vobiz/SIP trunk config is LEFT AS-IS — we build
> OUR OWN ALONGSIDE (additive). `agent.py` (`9150fabe…`) is NEVER imported.
> **Twin:** this is a column-for-column clone of the LIVE `provider_registry` (W1–W5) — same
> FORCE-RLS, AAD AES-256-GCM creds, circuit breaker, SSRF guard, strangler cut-over, super-admin+BYO UI.

---

## 0. THE HONEST REALITY (founder mandate — surface the truth, do not blindly agree)

The founder's goal — **independence, his own numbers, flexible, multi-number, multi-concurrency,
add-a-trunk-entirely-from-the-UI, spam-protected** — is RIGHT and buildable. But four facts are
physics/law, not opinion, and the design states them plainly instead of pretending otherwise:

1. **A consumer SIM/phone number CANNOT be a SIP trunk directly.** It needs either (a) a **GSM
   gateway** (GoIP/Yeastar/SIM-bank hardware that bridges a physical SIM to SIP), or (b) a
   **BYO-number SIP/CPaaS provider** (software-only). There is no third path — Android-as-gateway
   is architecturally blocked (locked RIL, no in-call audio API); eSIM/VoLTE are credential/IMS
   mechanisms, not internet-SIP interfaces.
2. **1 SIM = 1 concurrent call. Always.** Cellular physics. Multi-concurrency = summing channels
   across **multiple** trunks/SIMs (GoIP-8 = 8 SIMs = 8 calls; a CPaaS elastic trunk = N channels).
   You never get concurrency from one SIM.
3. **Auto-dialing from ANY 10-digit number risks the SAME carrier spam-flag.** This is **carrier
   behaviour, not a Vobiz bug.** Indian carrier graph-ML scores the calling *pattern* (high velocity,
   near-zero answer rate, failed-call bursts), flags the *number*, and increasingly the *entity/route*.
   **A fresh DID does NOT escape the block — it just resets a clock** (re-flagged in 24–72h if the
   same pattern repeats). This is exactly why `+918071583488` is carrier-blocked today.
4. **A personal SIM is strictly WORSE, and illegal at volume.** Mass-calling from a personal SIM
   violates carrier ToS + TRAI/DND/DLT → **permanent SIM ban** (not a recoverable block), flags every
   SIM on the same gateway, and a consumer SIM **cannot present a 140-series CLI** so it is
   non-compliant by construction.

**The one-line truth:** the registry gives **technical** independence TODAY (own creds, add any
trunk from the UI, multi-number, multi-concurrency, rotation, failover, spam-rest). **Legal**
independence at India scale is gated by **regulation, not code** — promotional calls legally MUST
originate from a **140-series DID** on a **DLT-registered Principal-Entity + Telemarketer** route,
NCPR-scrubbed, 9am–9pm. The registry is built to **enforce** that compliance (140/DLT are
required-to-enable fields, gated in the resolution choke-point — see §3.B), **not to bypass it.**
**Build the machine; buy the legal fuel** (§7 founder-buy list). Rotation/auto-rest/throttle are the
**seatbelt** — they keep you alive and buy time UNDERNEATH a compliant route; they are not a way
around the rules.

---

## 1. EXEC SUMMARY (~25 lines)

- **What:** a `trunk_registry` — a PG FORCE-RLS table + Python package + a `/telephony` UI — that
  resolves *which* `ST_<id>` (LiveKit-SIP trunk) and *which* DID `caller.py` passes per outbound
  dial, instead of the hardcoded `TRUNK` at `caller.py:184`.
- **Why it's low-risk:** it is a **column-for-column clone of the already-LIVE `provider_registry`**.
  LiveKit-SIP already runs two outbound trunks on the box with zero conflict — multi-trunk is native.
- **Chosen architecture:** 3 FORCE-RLS tables (`sip_trunks` / `sip_trunk_credentials` /
  `sip_trunk_health_log`) + package `droplet_work/trunk_registry/` (clones provider_registry; REUSES
  credentials/ssrf_guard/health; genuinely NEW: `livekit_sync.py`, `rotation.py`, in-process
  `concurrency`) + a strangler cut at `caller.py:184` behind `TRUNK_REGISTRY_ENABLED` (default OFF →
  resting byte-identical) + a Core_2-ported `app/telephony/page.tsx`.
- **Independence delivered in code:** own SIP creds (AAD-encrypted), add-any-trunk-via-UI, multi-number
  DID pool, per-trunk concurrency cap, DID rotation, failover, spam-rest/quarantine, a founder-placed
  single test call (the ONLY non-campaign originate — never auto-dial).
- **The Vobiz trunk stays a trunk:** `ST_fmtVmNJmpzKa` is imported as ONE `_global` row, so flipping
  the flag ON dials *exactly the same trunk* as today. Vobiz config files are untouched.
- **The honest gate:** legal India campaigns need a **140-series DID + DLT registration** (a purchase
  + ~1–2 week paperwork). The code can't mint that; it can and does *enforce* it.
- **FASTEST PATH TO INDEPENDENCE (recommendation):** a **BYO-number SIP/CPaaS provider is faster than
  a GSM gateway** — software-only, instant, no hardware, multi-concurrency. Recommended: **Plivo** as
  a 2nd trunk (₹250/DID/mo, ₹0.60/min, unlimited concurrency, official LiveKit support; needs India
  COI+GST which Famit likely has). The GSM gateway (his physical SIM) is **niche, manual-only, never
  in a campaign** — buy only for a single personal-number recall, if ever. **For real campaign legality
  the 140-series + DLT route is the non-negotiable purchase** (Airtel Business / Tata Tele / C-Zentrix).
- **4 red-teams folded:** every claim re-checked vs live code. The blockers below (B1, A1/A2, B/C/D,
  the retry-bug gate + velocity throttle) MUST land before `TRUNK_REGISTRY_ENABLED=1` in prod.

---

## 2. THE TRUNK-REGISTRY ARCHITECTURE (the chosen design)

### 2.1 Layers (mirrors provider_registry exactly)

```
 FE: app/telephony/page.tsx (Core_2 port) ── lib/api.ts (Bearer JWT)
   │
 caller.py guarded mount (additive, flag-gated):  /trunk-registry/* (super-admin) · /trunks/byo/* (vendor)
   │
 trunk_registry/  ── store.py / admin_store.py / schema.py / registry.py(get_trunk THE choke-point)
   │               ── credentials.py [REUSE] · ssrf_guard.py [REUSE] · health.py [clone]
   │               ── livekit_sync.py [NEW] · rotation.py [NEW] · concurrency [NEW, in-process]
   │
 PG: 3 FORCE-RLS tables   ·   LiveKit-SIP (Docker, box) — we only ADD/REMOVE trunk+dispatch OBJECTS via API
   │
 caller.py dial loop ── resolves ST_<id> + DID via get_trunk() ──► CreateSIPParticipantRequest
```

**Key decision — REUSE, don't re-build.** `credentials.py`, `ssrf_guard.py`, the circuit-breaker
primitive, the `get_secret()`/Fernet seam, `require_super_admin`, and the `build_router(...)` guarded
mount are imported/copied verbatim from `provider_registry`. Genuinely NEW: the 3 trunk tables,
`livekit_sync.py` (LiveKit Server API glue), `rotation.py` (DID rotation + spam-rest), and the
in-process concurrency counter.

### 2.2 Schema — `db/ddl_trunk_registry.sql` (3 tables, FORCE-RLS, INTEGER paise, no floats)

Same posture as `ddl_provider_registry.sql`: standalone psql apply, idempotent, `famit_app`
NOBYPASSRLS so FORCE-RLS binds the owner, money in INTEGER paise, `_global` read-share + write-lock.

- **`sip_trunks`** (analog of `provider_definitions`): `trunk_type` (`sip_provider`|`gsm_gateway`|
  `direct_sip`), `provider_vendor`, `direction`, `sip_host`/`sip_port`/`transport`/`encryption`,
  `auth_username`, `allowed_addresses[]` (inbound IP allowlist), `did_pool[]` (rotated caller-IDs),
  `max_concurrency` (channel cap; GSM = #SIMs, HARD 1/SIM), `cost_per_minute_paise` (INTEGER),
  **compliance gates** `is_140_series` / `dlt_entity_id` / `dlt_status` / `per_did_daily_cap`,
  `priority` / `rotation_strategy`, `is_enabled` / `is_test_verified` / `quarantined_until`,
  `livekit_trunk_id` (the `ST_<id>`). **+ the red-team-mandated `is_campaign_eligible` GENERATED
  column / DB CHECK (see §3.B).**
- **`sip_trunk_credentials`** (analog of `provider_credentials`): AAD AES-256-GCM SIP digest password,
  AAD = `tenant_id||trunk_id||key_version` (cross-tenant ciphertext copy → `InvalidTag`),
  `scope` = `integration` (revealable under PIN) | `platform` (masked-only). Strictly own-tenant RLS.
- **`sip_trunk_health_log`** (analog of `provider_health_log`): append-only
  (`REVOKE UPDATE,DELETE FROM famit_app`), per-DID `did` column for reputation tracking, `event` /
  `sip_code` / `latency_ms`.

### 2.3 LiveKit-SIP wiring (drives the SAME LiveKit the agent dials, NO container restart)

- **Add a trunk:** UI → SSRF-guard `sip_host` → encrypt password → insert row →
  `livekit_sync.create_outbound_trunk(...)` returns `ST_<id>` → store in `livekit_trunk_id`. Inbound
  also creates an inbound trunk + a dispatch rule with `metadata:{tenant_id}` (multi-tenant DID→agent
  routing). **Pure API — no restart.**
- **Outbound selection (the ONE hot-path change — strangler):** at `caller.py:2913`, flag ON →
  `tc = registry.get_trunk(tenant, 'outbound')` (never raises) → `sip_trunk_id = tc.livekit_trunk_id`,
  `sip_number = tc.did` (native LiveKit per-call caller-ID selector = DID rotation with zero LK config
  change). Any miss / flag OFF → legacy `TRUNK` env (byte-identical).
- **Import Vobiz zero-disruption:** `ST_fmtVmNJmpzKa` seeded as ONE `_global` row → flag-on dials the
  same trunk. **`_global` row is UN-DELETABLE (see §3.D).**

### 2.4 Per-trunk concurrency — **IN-PROCESS, not Redis** (red-team C correction)

The box runs uvicorn `--workers 1` (`ratelimit.py:13`), so the in-proc `ACTIVE_CALLS` dict
(`caller.py:535`) is already authoritative and correct. **Extend `ACTIVE_CALLS` per-trunk** for the
counter. Do NOT use the rate-limiter's `:6380` Redis — it is **FAIL-OPEN**, so a hard channel cap on
it would silently vanish on a Redis hiccup → 486 storm. Redis is introduced **only if/when the box goes
multi-worker, and then fail-CLOSED for the cap.** An in-proc counter under one worker has neither the
A1 leak nor the A2 TOCTOU race. `acquire`/`release` paired with the existing `ACTIVE_CALLS` finalize
touch-point (`caller.py:2844`) in a `try/finally` so a channel can never leak.

### 2.5 Number rotation + spam-reputation guard (corrected to a signal that EXISTS — red-team B)

The dial uses `wait_until_answered=False` (`caller.py:2916`) and returns immediately; outcome is
inferred from **duration + transcript** in `_classify_outcome` (`caller.py:1551`) — **there is NO
486/480/603 SIP code anywhere in caller.py.** So the original "quarantine on 486 burst" guard could
NEVER fire. Corrected design:

- **Quarantine on a burst of zero-duration ring-outs per DID** (a signal that already exists), OR add
  NEW LiveKit SIP-webhook / `participant-disconnected` plumbing to capture the real SIP code (the
  cleaner long-term fix; specified as an explicit BUILD sub-task, not assumed present).
- **NEW velocity throttle (was MISSING):** per-DID inter-call spacing + a calls/hour ceiling — because
  `per_did_daily_cap` limits *volume* but not *velocity*, and **velocity is the stronger flag signal**
  (75 calls in 10 min still looks like a dialer). Both ship.
- **Reputation-aware rotation:** never feed a fresh DID into a campaign already throwing failures
  (low answer rate is itself a flag input → death spiral).
- **Escalation, not silent pool-burn (red-team B3):** ≥K quarantines on one trunk →
  **DISABLE the trunk + loud compliance alert**, do NOT keep rotating to the next 10-digit DID (that
  just burns the whole pool one number at a time while hiding the root cause — exactly what blocked
  `+918071583488`, now automated across N numbers).

---

## 3. RED-TEAM FIXES — the non-negotiables that gate `TRUNK_REGISTRY_ENABLED=1`

Four adversarial passes (`spam-reality`, `sim-concurrency-legal`, `earner-safety-reliability`, folded).
Every fix lives in `concurrency`/`rotation.py`/`registry.py`/the DDL — **none touch `agent.py` or the
Vobiz config.** The honest finding across all four: **"the registry enforces compliance" was true in
prose, false in code** — the gates were in default-permissive columns + UI, not in the choke-point.
These make it unbypassable by construction.

| ID | Severity | Defect | Fix (where it lands) |
|----|----------|--------|----------------------|
| **B1** | 🟥 BLOCKER | `dlt_status DEFAULT 'unregistered'` + `is_enabled DEFAULT true` → an unregistered 10-digit trunk can be returned for a campaign via direct `POST /trunks/byo` (UI block is prose-only) → the exact 2-lakh-fine / 2-year-blacklist violation the design exists to prevent | Gate in `registry.get_trunk(purpose='campaign')` + an `is_campaign_eligible` **GENERATED column / DB CHECK** (`is_140_series AND dlt_status='registered'`). Unbypassable by construction. |
| **A1** | 🟥 CRITICAL | (only if Redis were used) `active_calls` INCR/DECR leaks on crash/raise → trunk stuck "full" → dialer silently STOPS | **Resolved by §2.4** — keep the counter IN-PROCESS under `--workers 1` with `try/finally`; no leak possible. If ever multi-worker: self-healing sorted-set + TTL eviction. |
| **A2** | 🟧 HIGH | (only if Redis) check-then-acquire TOCTOU oversells the cap under burst → 486 storm | **Resolved by §2.4** in-proc; if ever Redis: atomic INCR-and-compare (Lua). |
| **B (rel)** | 🟥 BLOCKER | spam-rest guard fires on a SIP code caller.py never captures (`wait_until_answered=False`) → guard never fires as written | **§2.5** — quarantine on zero-duration ring-out bursts (signal exists) OR add NEW SIP-webhook plumbing. Do NOT ship the guard as the original text described. |
| **C (rel)** | 🟥 BLOCKER | Redis concurrency contradicts the live `--workers 1` posture + the `:6380` Redis is FAIL-OPEN → a hard cap silently vanishes | **§2.4** — in-process counter. |
| **D (rel)** | 🟧 HIGH | `livekit_sync.delete` removes an `ST_` from the SAME LiveKit the earner dials; wrong-id/misclick/`_global` DELETE kills the live trunk with no restart | Refuse DELETE of env `LIVEKIT_SIP_TRUNK_ID` + any `_global`/AIM-inbound trunk; default to **soft-disable**; hard-delete = **PIN-gated + audited**. |
| **B3** | 🟧 HIGH | rotation auto-rotates through the whole DID pool on a non-compliant trunk, hiding root cause | **§2.5** — ≥K quarantines → DISABLE trunk + loud alert, stop rotating. |
| **Retry-gate** | 🟥 HARD GATE | the live `scheduler_loop` retry bug re-fires dead/486 numbers → turning on rotation with it present multiplies the failed-call signature across the WHOLE pool in one campaign | **Rotation stays OFF until the scheduler retry bug is fixed AND verified.** This is T0 of the roadmap. |
| **Velocity** | 🟧 HIGH | `per_did_daily_cap` limits volume not velocity (the stronger signal) | **§2.5** — NEW per-DID inter-call spacing + calls/hour ceiling. |
| **A4** | 🟨 MED | `max_concurrency` can exceed the box RTP ceiling (~100) until the recreate wave | Box-global cap (~90) in every acquire. |
| **B2** | 🟨 MED | NCPR-scrub / 9–9 window / AI-disclosure named but un-enforced, orphaned between registry↔campaign | Name the 3 choke-points: campaign-launch / `scheduler_loop` / agent prompt. |
| **E** | gap | no real-time per-DID kill switch independent of the master flag | Add `POST /quarantine-did`. |
| **F** | gap | `/test-call` un-rate-limited → 20 debug-hammers reputation-damage the DID | Rate-limit ≤3/hr/trunk, founder-owned destination, counted vs the daily cap. |
| **A3** | 🟦 LOW | a GSM trunk can ask one SIM for 2 calls via DID-rotation collision | `did_pool len == max_concurrency == #SIMs` + per-DID in-flight==0 guard (only bites `gsm_gateway`). |
| **B4** | 🟦 LOW | "live AI is unregulated" is a moving grey area (TRAI amendment pending mid-2026) | Treat as the floor, not a moat; AI self-disclosure mandatory NOW. |

**Earner-safety VERIFIED (not assumed):** flag-OFF is byte-identical (`caller.py:184 TRUNK`, dial
`:2913`); `agent.py` (`9150fabe…`) is never imported; the Vobiz `_global` row is reused not replaced.
The honest compliance section must NOT be softened.

---

## 4. THE FRONTEND — Settings › Telephony / Numbers (Core_2 kit, never from scratch)

`famit-panel/app/telephony/page.tsx` + `components/telephony/*`, ported from the Core_2 Capsy kit,
talks via `lib/api.ts`. Every backend capability has its FE control here (founder's standing rule).

- **Trunk cards grid:** one card per trunk — friendly name, vendor badge, **live health dot**,
  **concurrency gauge** (`3 / 20`), **DID pool chips** with a per-DID daily-budget bar (`52 / 75`),
  a **compliance badge** (140-series + DLT-registered = campaign-eligible / unregistered = blocked from
  campaigns), a **quarantine banner** if rested; actions Test · Edit · Reveal · Disable (Disable, not
  Delete, by default).
- **Add-trunk wizard (3 steps):** Step 1 pick type (SIP provider · GSM gateway · Direct SIP) with
  honest inline notes ("GSM: 1 SIM = 1 call; manual-trigger only; NOT TRAI-compliant for campaigns").
  Step 2 the form (host:port, transport, auth, DID pool, max-concurrency, **140-series + DLT fields
  REQUIRED to enable for campaigns**, with a "What's DLT?" helper). Step 3 **Test trunk** — the founder
  types a destination → ONE live test call with a ringing animation + SIP trace → "Connected" flips
  `is_test_verified` and unlocks "Save & enable". **This is the ONLY non-campaign call this system ever
  originates — never an auto-dial.**
- **Inbound-routing panel:** DID → agent → tenant dispatch rules (add/edit/delete).
- **Spam-reputation panel:** per-DID failure-history sparkline + quarantine status + a manual
  "rest this number" / "release" toggle (the §3.E kill switch).

---

## 5. PHASED EARNER-SAFE BUILD ROADMAP

Each wave: scope · files · flag · acceptance · rollback. **ADDITIVE — Vobiz stays a trunk; never
touch `agent.py` without founder sign-off; a controlled FOUNDER test-call gates each step, never an
auto-dial.** One box-mutating wave at a time. `caller.py` is serialized vs RAG/Vault/Registry/Video —
only ONE edits `caller.py` at a time.

| Wave | Scope | Files | Flag | Acceptance | Rollback |
|------|-------|-------|------|------------|----------|
| **T0** (prereq) | Fix the queued `scheduler_loop` retry bug that re-fires dead/486 numbers (the HARD GATE — rotation must not amplify it) | `caller.py` scheduler_loop | n/a | retry no longer re-fires terminal-outcome numbers; verified on a dry-run; earner gate green | revert the scheduler patch |
| **T1** ✅ DONE (2026-06-15) | Apply `db/ddl_trunk_registry.sql` (3 FORCE-RLS tables + `is_campaign_eligible` CHECK); seed the `_global` Vobiz row + cred (UN-DELETABLE) | `db/ddl_trunk_registry.sql` | none | **LIVE on box `168.144.153.145`**: 3 tables `relforcerowsecurity=t`; 3 triggers present (append-only + 2 undeletable locks); `is_campaign_eligible` STORED `attgenerated='s'`; Vobiz `_global` row `9896cddf…` un-deletable (DELETE=0 blocked); B1 gate: non-140 row → `is_campaign_eligible=f`; AAD cred encrypted + roundtrip verified. Earner gate PASS. Commit `f0efa6c`. | `DROP` the 3 additive tables (drop-safe) |
| **T2** ✅ DONE (2026-06-15) | Ship `trunk_registry/*` (clone provider_registry; REUSE credentials/ssrf/health; NEW livekit_sync/rotation/in-proc concurrency w/ ring-out-burst guard + velocity throttle) | `droplet_work/trunk_registry/` | `TRUNK_REGISTRY_ENABLED` OFF | **31/31 offline PASS** (9/9 registry + 8/8 concurrency + 14/14 rotation/livekit); provider_registry suites still green (5/5); B1 gate rejects non-140 for campaign; AAD cross-tenant → `InvalidTag`; in-proc counter try/finally no-oversell; ring-out-burst quarantine + disable; red-team-D delete refusal. Resting byte-identical. Earner gate PASS. Commit `46301d2`. | flag absent → dormant |
| **T3** ✅ DONE (2026-06-15) | Additive `/trunk-registry/*` + `/trunks/byo/*` guarded mount; `/test-call` rate-limited (≤3/hr); DELETE soft-disables + refuses `_global`/env trunk; `POST /quarantine-did` kill switch | `caller.py` (additive mount only) | OFF | **LIVE on box `168.144.153.145`**: flag-OFF → all `/trunk-registry/*` return 404 (dormant, byte-identical); flag-ON → all 16 routes return 401 (auth-gated, not 500); legacy `/campaigns` = 401 intact; 0 5xx; caller /health 200; earner gate PASS (agent.py `9150fabe` UNCHANGED, famit-agent PID 1477083 NRestarts=0). caller.py md5 `44b867ea`. Commit `db7b489` on `fe/unify-run-wavec`. | unmount / flag off |
| **T4** (FE) | Settings › Telephony page (Core_2 port) + founder test-call flow + reputation panel + kill switch | `app/telephony/page.tsx`, `components/telephony/*`, `lib/api.ts` | OFF | FORTRESS build green; page renders; test-call flow works against the `_global` Vobiz trunk; founder can add a trunk | redeploy prior FE BUILD_ID |
| **T5** (strangler, flag ON staging→prod) | The `caller.py:2913` dial-loop cut behind `TRUNK_REGISTRY_ENABLED` | `caller.py` (additive strangler) | ON | **Integrated smoke: a real founder outbound call RINGS via the registry-resolved Vobiz row BEFORE and AFTER** = zero regression. Then enable DID rotation; cross-trunk rotation only AFTER the founder buys a 140/Plivo trunk | `TRUNK_REGISTRY_ENABLED=0` (instant, byte-identical) |

**The acceptance truth (founder mandate):** a green per-component report is NOT success. T5 is proven
only when the founder places a REAL outbound call that rings via the registry-resolved trunk, both
before and after the flag flip. I never test-call a campaign DID (it spam-flags it) — the founder's
real ring is the final proof.

---

## 6. RISKS + MITIGATIONS (baked in)

| Risk | Mitigation |
|------|-----------|
| Touching the live earner | Flag OFF = byte-identical; `agent.py` never imported; Vobiz imported as a row; one box-mutating wave; instant env-flag revert |
| Retry bug + rotation amplifying the carrier flag | T0 fixes it FIRST; rotation OFF until verified (HARD GATE) |
| Non-compliant DID dialing a campaign | `is_campaign_eligible` GENERATED column + `get_trunk(purpose='campaign')` gate (B1) — unbypassable |
| Deleting the live trunk by misclick | DELETE refuses `_global`/env/AIM trunks; default soft-disable; hard-delete PIN-gated + audited (D) |
| Channel leak / oversell | In-process counter + try/finally + box-global ~90 cap (C/A1/A2/A4) |
| Spam-rest never firing | Ring-out-burst signal + velocity throttle + SIP-webhook plumbing (B-rel/velocity) |
| Pool-burn hiding root cause | ≥K quarantines → disable trunk + alert, stop rotating (B3) |
| SSRF via user `sip_host` | REUSE `ssrf_guard.py` verbatim; gsm/direct super-admin-only |
| Cross-tenant credential theft | AAD AES-256-GCM; FORCE-RLS; PIN reveal; platform scope masked-only |
| Auto-dialing a personal SIM | `gsm_gateway` HARD-flagged manual-only + excluded from the campaign pool in code |
| Test call auto-firing | The only non-campaign originate is the explicit founder-typed `/test-call`, rate-limited ≤3/hr (F) |

---

## 7. FOUNDER ACTIONS (dead-simple — what code cannot give you)

### 7.1 THE FASTEST PATH TO INDEPENDENCE — recommendation

**A BYO-number SIP/CPaaS provider is FASTER than a GSM gateway.** Side-by-side:

| | **BYO-number SIP provider** (software) | **GSM gateway** (your physical SIM) |
|--|----------------------------------------|--------------------------------------|
| Speed | **Instant** — paste creds in the UI, one form, live in minutes | Slow — buy + ship + rack + LAN-wire hardware |
| Hardware | None | GoIP/Yeastar box (~₹18k+), on your network |
| Concurrency | **Multi** (elastic / many channels) | 1 call per SIM (need N SIMs for N calls) |
| Legality for campaigns | Compliant **with** a 140/DLT route | **Illegal at volume** — consumer SIM, no 140 CLI, WILL be banned |
| Verdict | **RECOMMENDED** | Niche, manual-only, not for campaigns |

**So: go software-only.** The GSM gateway is only worth it for a single personal-number manual recall
to a high-trust lead — never a campaign.

### 7.2 The buy list (in order)

1. **140-series DID + DLT registration — THE non-negotiable for legal India campaigns.** Register
   Famit/Axcrio as a **Principal Entity + Telemarketer** on a DLT portal, register call headers +
   templates, provision a **140-series SIP trunk** from a licensed VNO (**Airtel Business / Tata Tele /
   C-Zentrix / Knowlarity** — all are standard SIP trunks LiveKit connects to identically). ~1–2 weeks;
   registration cheap, trunk per-channel + per-minute. **Until this exists, every campaign from any
   10-digit DID (incl. the current Vobiz number) is non-compliant + spam-flag-prone — which is why
   `+918071583488` is blocked today.**
2. **A 2nd BYO SIP trunk for independence + failover — Plivo** (₹250/DID/mo, ₹0.60/min, unlimited
   concurrency, official LiveKit support; needs India COI+GST — Famit likely has these). One UI form →
   one registry row → instant second trunk. **Exotel** is the only BYO-port path for an existing Indian
   number but its LiveKit vSIP is Alpha/wait-GA. **Telnyx/Twilio = no India DID, skip.**
3. **(Optional, niche) Yeastar TG200 GSM gateway** (~₹18k, 2-SIM) ONLY for a single personal-number
   manual recall — `gsm_gateway` is HARD-flagged manual-only, never in the campaign pool. **Skip unless
   that exact use-case is needed.**
4. **NCPR/DND scrub access** (bundled with the DLT/VNO trunk) — mandatory pre-campaign scrub.
5. **Raise the LiveKit RTP port range** (a future container-recreate, not a buy) when scaling past
   ~100 concurrent.

---

## 8. FILES THIS PLAN NAMES (created in the BUILD waves)

- `droplet_work/db/ddl_trunk_registry.sql` (NEW — 3 tables + `is_campaign_eligible` CHECK)
- `droplet_work/trunk_registry/` (NEW package: config/schema/store/admin_store/credentials[reuse]/
  ssrf_guard[reuse]/health/livekit_sync[NEW]/rotation[NEW]/concurrency[NEW,in-proc]/registry/endpoints)
- `caller.py` (additive: guarded mount + the §2.3 strangler dial-loop cut, flag-gated + the T0
  scheduler retry-bug fix)
- `famit-panel/app/telephony/page.tsx` + `famit-panel/components/telephony/*` (NEW — Core_2 port)
- `famit-panel/lib/api.ts` (additive trunk-registry client methods)

**Flags:** `TRUNK_REGISTRY_ENABLED` (master, default OFF → resting byte-identical); reuses
`FIREWALL_ENABLED` for the PIN step-up reveal + hard-delete.

**Full design + 4 red-teams:** `memory/wave_runs/telephony-independence-megaplan.md` (1212 lines).
