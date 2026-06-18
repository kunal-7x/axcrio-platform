# W11 — Warm-Transfer Hardening + Real Booking + Google Calendar (transfer/booking/gcal seam)

**Date:** 2026-06-18 · **Branch:** `fix/realtime-voice-kernel-v2` · **Status:** BUILT + GREEN (447 passed)
**EARNER LAW:** outbound `agent.py` md5 `98655dbf` untouched; inbound `aim_voice_agent` edits = PATCH DOC only.

## Goal
Three founder bugs, built as TRACKED, droplet-free, default-OFF packages that WRAP (never edit) the live boxes:
1. Warm transfer over-talks + unreliable ring/music -> ONE short ack line + hold music + same-room dial + AI-exit + state log.
2. Booking page is UI-only -> AI `book_site_visit` creates a REAL appointment (persist + dashboard + lead/campaign link) + full lifecycle (manual + AI).
3. Google Calendar OAuth -> vendor connects; AI/manual bookings create cal events; reschedule/cancel update; sync ASYNC (never blocks call) + reconnect-on-expiry.

## What shipped (all tracked, 0 heavy imports at load — verified)
- `voice_ops/booking/` : `config.py`, `store.py` (lazy importlib wrapper over the gitignored `droplet_work/booking/core.py` — drives the real no-double-book/RLS/immutable-audit engine on the box, `not_configured` in CI), `datetime_resolve.py` (pure IST-aware "kal subah 10 baje" resolver), `service.py` (`BookingService.book_site_visit` + lifecycle + W8 `site_visit_booked` emit + async calendar fan-out), `transfer.py` (`plan_transfer` pure planner + `detect_transfer_intent` + `TransferLog` requested/started/connecting/completed/failed -> W8 handoff_requested/done).
- `voice_ops/gcal/` : `config.py`, `vault.py` (SELF-CONTAINED AAD-bound AES-256-GCM refresh-token vault — does NOT depend on the gitignored provider_registry; + FORCE-RLS `gcal_credentials` DDL), `oauth.py` (authorization_url -> exchange_code stores encrypted refresh token -> refresh mints access token, flips `revoked` on invalid_grant), `sync.py` (`CalendarSync.on_booked/on_rescheduled/on_cancelled` async Calendar v3, never blocks).
- `design/W11-TRANSFER-BOOKING-GCAL-SEAM.md` — the aim_voice_agent transfer + book_site_visit patch, caller.py booking + OAuth API mount, Google OAuth founder steps.

## Tests
- `voice_ops/booking/tests/` (book persists+emits W8, slot-taken re-ask, unresolved-time re-ask, disabled/dormant graceful, lifecycle complete/cancel/reschedule, TENANT ISOLATION, transfer plan = exactly ONE short line + correct dial/exit sequence + dict handoff list + no-target path, TransferLog lifecycle emits, intent detection; pure datetime resolver).
- `voice_ops/gcal/tests/` (AES-GCM round-trip, **cross-tenant ciphertext fails (InvalidTag)**, empty/no-tenant/no-secret raise, mask, store persist+isolation; auth-url offline+consent+state, forged-state reject, exchange stores ENCRYPTED token, refresh mints token, **invalid_grant -> revoked (reconnect)**, not_connected; sync create/patch/delete with mock HTTP carrying lead/phone/campaign, dormant no-op, revoked-token skip-no-call).
- **`pytest voice_ops/ voice_kernel/` = 447 passed** (39 new + 408 existing, no regressions).

## Key decisions / learnings
- Path rule: the real booking engine + AAD vault are GITIGNORED. The tracked deliverable must NOT rely on gitignored code being importable as a package -> `store.py` loads `core.py` via importlib + a synthetic package alias at CALL time (mirrors conftest.load_legacy_prompt_module), and the gcal vault is re-implemented self-contained (same crypto posture, reuses the existing master-secret env -> zero new secret/dep).
- Transfer root cause confirmed on disk: `_OUTBOUND_TRUNK` captured at import (aim_voice_agent.DEPLOYED.py:172, stale `ST_fmtVmNJmpzKa`); the immediate fix is a `systemctl restart aim-voice-agent` (correct trunk `ST_bpGqmc9TL9Ph`); Patch A makes it per-call so no future restart is needed. The SIP bridge mechanics (create_sip_participant into caller room, hold music, aclose) already work — the bugs were the stale trunk + verbose fallback strings + missing one-line ack.
- W8 `site_visit_booked` / `handoff_requested` / `handoff_done` factories already existed in voice_kernel.events.taxonomy — reused, fire-and-forget (a dead Redis never breaks a booking/call).
- Calendar is an ENRICHMENT, never a dependency: bookings persist + show on the dashboard even with gcal dormant.

## Founder action to go live on calendar
Google Cloud Console -> enable Calendar API -> OAuth consent screen -> create OAuth Web client with redirect
`https://panel.famit.in/api/gcal/callback` -> send Client ID + Client secret (out-of-band). Then set
`GOOGLE_CALENDAR_CLIENT_ID/SECRET` + `BOOKING_CALENDAR_SYNC=1` (+ `BOOKING_OPS_ENABLED=1` for booking, correct
`LIVEKIT_SIP_TRUNK_ID` for transfer). Full steps in the SEAM doc §5.

## Phase: VERIFY (2026-06-18) — RED-TEAM SHIP folded, COMMITTED
- Gates re-run, all green: `pytest voice_ops/booking/tests voice_ops/gcal/tests` = **39 passed**;
  full `pytest voice_ops/ voice_kernel/` = **360 passed / 0 failed**.
- EARNER LAW HELD: live OUTBOUND `droplet_work/agent.py` md5 `98655dbf` UNCHANGED (recomputed, exact match);
  never edited/imported/restarted; transfer/booking are INBOUND-side and ship as the PATCH DOC only.
- Isolation: `voice_ops/booking/` lazy-wraps the gitignored `droplet_work/booking/core.py` via call-time
  `importlib` (dormant-safe when absent, 0 heavy imports at module load); `voice_ops/gcal/` is fully
  self-contained (own AES-256-GCM vault + RLS DDL, does not depend on gitignored provider_registry).
- gitleaks `protect --staged` = **0 leaks** (~130 KB scanned); no OAuth client secret committed —
  the `client_secret` hits in the diff are env-var NAMES, `os.getenv` reads, doc placeholders, and fake
  test fixtures (`"csecret"`, `""`) only.
- Red-team verdict = **SHIP**. 3 non-blocking nits logged (below); no blockers in transfer/booking/gcal.
- Staged ONLY: `voice_ops/booking/`, `voice_ops/gcal/`, the W11 `voice_ops/__init__.py` docstring,
  `design/W11-TRANSFER-BOOKING-GCAL-SEAM.md`, this wave-log. NEVER `git add -A`; left the untracked
  `voice_ops/{callback,tests}/` + every other dirty file for their own waves.
- NO box deploy — by EARNER LAW the aim_voice_agent.py transfer choreography + booking/gcal go-live is a
  separate founder-gated seam (SEAM doc §5: flags `BOOKING_OPS_ENABLED` / `BOOKING_CALENDAR_SYNC`, correct
  `LIVEKIT_SIP_TRUNK_ID`, `systemctl restart aim-voice-agent` ONLY — earner `famit-agent` never touched).

### Non-blocking nits (logged, deferred to the wiring seam — none risk the earner)
1. TRANSFER ring/music root cause is OPERATIONAL not code: the live box ran a stale import-time
   `_OUTBOUND_TRUNK` (never restarted after the `.env` trunk swap). Patch A reads the trunk per-call;
   the immediate fix at deploy is `systemctl restart aim-voice-agent`. Record the trunk id in §5.
2. GCAL `recording_ready`-style double-emit analogue: a transient calendar-sync retry could re-emit a
   booking sync event; idempotent on the sink (same row), at most a redundant update — acceptable.
3. Booking `datetime_resolve` relies on the vendor tz being set; missing tz falls back to a graceful
   re-ask rather than a wrong slot — confirm vendor tz is populated at go-live.
