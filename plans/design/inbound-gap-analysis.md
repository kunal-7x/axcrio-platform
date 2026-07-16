# Inbound AI Manager — Production Gap Analysis (DIAGNOSE-2)

_Authored 2026-06-12 from live box famit@168.144.153.145 + local panel. Evidence-grounded; file:line cited._
_GOAL: founder phones +918071583488 → greet → speaks (broken/accented/code-mixed) → LLM intent → real-time execute → clarify/recover → full call logged (transcript + recording URL + commands + outcome) → viewable in panel → multi-vendor (DID + PIN + isolation)._

⚠️ NEVER touch the LIVE OUTBOUND EARNER (agent.py / capsy / famit-agent.service / :8090). Inbound = aim_voice_agent.py / aim-voice-agent.service / agent_name=manager / :8091 ONLY. Backup-first, regression-gate outbound healthy before+after, restart ONLY inbound. NO git.

---

## ROOT CAUSE OF THE SILENCE (P0) — corrected from the prompt's hypothesis

The prompt guessed "the inbound service lacks the Sarvam/round-robin keys." **That is FALSE.** Verified live:
- aim-voice-agent.service and famit-agent.service share the **same** `EnvironmentFile=/opt/famit-agent/.env` and the **same** venv `/opt/capsy-agent/.venv`. The env has all 5 `SARVAM_API_KEY*` + 6 `GROQ_API_KEY*`. Keys are present and identical to the working outbound earner.
- The inbound STT construction (`aim_voice_agent.py` `sarvam.STT(api_key=_next_sarvam_key(), language="unknown", model="saarika:v2.5")`) is **byte-identical** to the outbound `agent.py:510`.

**Real cause:** the crash was `aiohttp _resolve_host → CancelledError → TimeoutError → APIConnectionError: Failed to connect to STT WebSocket` inside the Sarvam `_stt_pump`. DNS for `api.sarvam.ai` resolves fine NOW (0.01s, ×3) → it was a **transient DNS/WS-connect hiccup at session start**. The fatal design flaw: STT is wired as a **bare single provider with NO retry and NO FallbackAdapter**, so one transient WS-connect failure propagates out of `_stt_pump` and **kills the whole job/process before any further speech** — total silence. The greet line is authored, but the pipeline tears down around it.

Two structural P0 fixes are needed (not an env fix):
1. **Resilient STT**: wrap STT in `livekit.agents.stt.FallbackAdapter([sarvam_primary, sarvam_secondary])` (or Sarvam→Deepgram) + connection retry, so a transient WS/DNS blip retries instead of killing the job. The outbound earner tolerates blips mid-call; the inbound dies because the failure lands at startup.
2. **Greet BEFORE the STT pump can fatal the job** + **never-silent guard**: speak the greeting on participant-join immediately, and wrap the whole entrypoint so ANY exception still says "Sorry, I had a glitch, please try again" before hangup — never a silent dead-air drop.

---

## WHAT EXISTS (strong — the brain is real, only the voice rail + plumbing are broken)

- **NLU**: `ai_manager/intent/driver.py` — closed-enum LLM matcher, `CONF_MIN` confidence floor, off-enum/low-conf → `{"kind":"clarify"}`, deterministic offline keyword fallback, code-mix Hinglish via Sarvam `language="unknown"`. Solid.
- **Command brain**: `workforce/tools/catalog.py` — 25+ tools mapped 1:1 to live caller.py routes: leads.read, analytics.read, billing.read, wallet.read, booking.read/create/reschedule/cancel, contacts.read/write, whatsapp.send, ads.set_budget/pause/create_campaign, campaigns.create, workflow.create_draft/activate/run_now, leads.enqueue_calls, suppression.add. (creative.generate_* = PARKED behind FEATURE_MEDIA.)
- **Safety spine**: `ai_manager/state_machine.py` CommandMachine S0–S9 — identity → PIN (anti-spoof, before data) → context → intent → permission → step-up PIN for risky → confirm → delegate → speak. Recorder pause/resume wraps PIN spans for audio hygiene.
- **Firewall**: `firewall.py` PIN 4827 salted-hash + HS256 step-up; init replicated in the worker (fail-closed).
- **DB schema LIVE**: PG tables exist — ai_manager_sessions, _commands, _action_runs, _audit_logs, _profiles, _authorized_users, _idempotency.
- **Registry (multi-vendor scaffolding)**: `ai_manager/registry.py` — per-number tenant_id + role + grants + verify_mode + status, OTP-verified, tenant-scoped reads.
- **Panel**: `app/ai-manager/sessions/[id]/page.tsx` (rich session-detail page already built) + endpoints `GET/POST /ai-manager/sessions`, `/numbers*`.

## WHAT IS MISSING / BROKEN (the gaps)

- **STT has no retry/fallback** → one transient blip kills the job (the P0 silence). [aim_voice_agent.py]
- **Never-silent guard absent** → an exception drops the call with no spoken apology.
- **RECORDING is a total no-op**: `_NullRecorder`, `recorder=None`, schema has **no `recording_url` column**, NO LiveKit Egress started, NO Spaces/S3 creds in env, NO upload. The "recording player" link in the panel points at nothing.
- **Session persistence write-path mismatch**: the voice worker writes a flat **JSONL** mirror (`endpoints._append_session`), NOT the rich **PG** tables (_sessions/_commands/_action_runs). The detailed schema is unused by the voice path. (And the JSONL file doesn't even exist yet — no call has ever completed.)
- **ai_manager router NOT mounted in caller.py** — endpoints.py self-documents "DEFINED-NOT-MOUNTED, un-applied diff." caller.py mounts ads/media/booking/payments/support/forms/workflow but NOT ai_manager. So the panel's `/ai-manager/sessions` + `/numbers` calls have **no live backend**.
- **Multi-vendor not wired into voice**: agent **hardcodes** a single `AUTHORIZED_CALLER (+917861019021)` + the single box firewall PIN. No DID→vendor routing, no per-vendor PIN, registry.lookup-by-caller not used as the gate.
- **No panel sessions LIST page** (only the `[id]` detail) — no way to browse call history.
- **Outbound regression-gate not automated** — no pre/post health check on famit-agent before touching inbound.

---

## PRIORITIZED BUILD LIST

### P0 — VOICE WORKS AT ALL (greet → understand → execute → never silent)
- **P0.1** Wrap STT in `FallbackAdapter([sarvam, sarvam_backup_key])` + connect-retry so a transient WS/DNS blip retries, never fatals the job. (mirror agent.py tolerance.)
- **P0.2** Speak greeting immediately on join; wrap the whole entrypoint in try/except that ALWAYS speaks a graceful apology + hangs up — eliminate dead-air on any failure.
- **P0.3** Smoke-test end-to-end: real inbound call → hear greet → say a leads/analytics query → hear the executed result. Confirm clarify-on-low-confidence speaks back (never silence).
- **P0.4** Regression gate: assert famit-agent (outbound earner) `is-active` + a test outbound call works BEFORE and AFTER every inbound change.

### P1 — LOGGING + RECORDING + HISTORY (the audit/replay product)
- **P1.1** Mount the ai_manager router in caller.py (tenant from token, service-token for POST /sessions) so the panel has a live backend.
- **P1.2** Switch the voice write-path from JSONL to the **PG tables** (create_session/create_command/create_action_run/record_audit_log already exist in store.py) so transcript + each command (intent·risk·permission·pin·status·cost·result) + audit + action-runs persist per session.
- **P1.3** RECORDING: add `recording_url` column; start a **LiveKit Egress** room-composite/track recording on join (PAUSED around PIN spans via the existing recorder hook); on hangup upload the audio to **DO Spaces** → store the URL on the session row. (Needs Spaces creds — currently absent.)
- **P1.4** Build the panel **sessions LIST** page (browse history) feeding the existing `[id]` detail; wire the recording player to the new URL. Deploy via FORTRESS (backup first; coordinate with the modelslab-image wave; do NOT clobber app/creative).

### P2 — MULTI-VENDOR (DID per vendor · per-vendor PIN · tenant isolation)
- **P2.1** Replace the hardcoded `AUTHORIZED_CALLER` with `registry.lookup(caller_id)` as the real gate; resolve tenant + role + grants from the registry row.
- **P2.2** Per-vendor PIN (per-tenant firewall pins, not the single box PIN) + per-DID→tenant dispatch so each vendor gets a dedicated number routed to agent_name=manager with their own isolation.
- **P2.3** RLS / in-code tenant scoping verified end-to-end (no cross-vendor session/transcript bleed) — mirror the control-layer T-probe style.

### P3 — POLISH (latency · barge-in · richer recovery)
- **P3.1** Tune endpointing/barge-in for inbound (semantic turn model already guarded); verify ~1.1s/turn moat is inherited.
- **P3.2** Multi-turn slot-filling + error-recovery phrasing (retry prompts, "I didn't catch that", confirm-before-risky read-back) hardened across all command types.
