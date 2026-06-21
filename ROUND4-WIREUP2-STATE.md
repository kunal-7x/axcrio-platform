# ROUND4 — WIRE-UP 2 STATE (2026-06-19)

**Honest verdict: every IN-SCOPE (famit-caller / caller.py / its modules) deferred item
was ALREADY shipped + live by the prior wave (box backups `*.R4bak.20260619-153138/154956`).
I verified each on the box, made ZERO box mutations, and did not touch the earner.**

## EARNER GATE — OK (verified start + end)
`famit-agent`=active, `agent.py` md5 `48bc2b5a` (== R4 golden, voice byte-identical).
`famit-caller`=active, `/health`=200, 0 caller errors since start. Nothing restarted.

## PER-FEATURE STATUS (verified on box 168.144.153.145)
1. **Super-admin vendor permissions (lock/hide/on ALL incl Creative Studio + script + render-brain)** — ✅ DONE/LIVE. `var/control/registry.json`=100 keys; creative keys present (studio/library/video/brand_kit/script/render_brain/generate/brand_kit.save). Enforce-mw HIDDEN=404/LOCKED=402 live.
2. **AI-Manager add-number(PIN)+inbound-routing** — ⚠️ PARTIAL. Add-number router mounted (`/ai-manager/numbers`→401 gated); `registry.lookup/register/mark_verified` present; PIN step-up wired. DEFERRED (out of scope): inbound-routing wiring lives in `aim_voice_agent.py` (separate aim-voice-agent VOICE service) + `inbound_agent.py` stub — touching it = a voice-service restart, forbidden by the gate.
3. **Booking + Google-Calendar real-time** — ✅ BACKEND DONE/LIVE. Booking router mounted; `/booking/book` + reschedule/cancel defined; `calendar_sync.py` GCal client un-stubbed (real Credentials+discovery). Dormant on founder creds. Voice booking-tool gap is in `outbound.py` (agent.py/earner path) = out of scope.
4. **Brand-kit persistence** — ✅ DONE/LIVE. `/brand-kits` GET/POST/DELETE (`caller.py:4426+`, `var/brand_kits/<tenant>.json`), `/brand-kits`→401 gated.
5. **Creative-Studio entitlement keys** — ✅ DONE (same as #1).
6. **Customer-support / Workflow / Webhook** — ✅ DONE/LIVE. Routers mounted (`/support`, workflow, webhooks); all →401 gated, no 500s.
7. **T0 callback retry-bug fix + India 9-9/DND clamp** — ✅ BUILT, correctly OFF. `voice_ops/callback/` (single authoritative attempts++ site, `>=cap` guard) + `voice_ops/compliance/` + `cadence.py:_apply_dnd` (TRAI 21:00→09:00 IST clamp). `RETRY_SCHEDULER_ENABLED` defaults 0; NOT flipped.

## VERIFICATION
Routes 401/404 (gated, not crashing); registry=100 keys; callback/compliance packages present; agent.py md5 unchanged; famit-agent+famit-caller active; /health 200; 0 errors.

## ROLLBACK
Nothing to roll back — I mutated nothing. Prior-wave armed backups on box: `caller.py.R4bak.20260619-154956`, `registry.json.R4bak.20260619-154956`, `agent.py.R4bak.20260619-153138`. Voice golden: `*.PERFECTgolden.20260618-210445`.

## GIT
No new code authored → nothing committed/pushed this round. `droplet_work/{agent,caller}.py` show as local working-tree drift (synced from box by the prior wave; box `caller.py` md5 `8f6bb1d0` == local) but `droplet_work/` is deliberately NOT tracked-for-changes per policy (secret-risk) — left uncommitted.

## STILL NEEDS THE FOUNDER
1. **GCal go-live** — set `BOOKING_CALENDAR_SYNC=1` + `GOOGLE_CALENDAR_CLIENT_ID/SECRET/REFRESH_TOKEN` (creds, no code).
2. **AIM OTP backend** — `ai_manager/otp/sender` send+verify dormant (number can't verify live).
3. **Callbacks/DND flip** — code complete; flip `RETRY_SCHEDULER_ENABLED=1`+`CALLBACK_CADENCE_ENABLED=1` ONLY after a founder-signed live test (spam-gated).
4. **Voice-path gaps (need a separate earner-gated wave, NOT this task):** booking voice-tool in `outbound.py` (agent.py/earner) + inbound-routing in `aim_voice_agent.py`/`inbound_agent.py` (aim-voice service). Both require a voice-service restart → out of the caller-only gate.
5. **Real proof = founder's live call + dashboard check.** Per-component green ≠ shipped.
