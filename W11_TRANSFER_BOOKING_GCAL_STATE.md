# W11 — Warm-Transfer + Booking + Google-Calendar SEAM — BUILD STATE

Branch: `fix/realtime-voice-kernel-v2`  ·  EARNER LAW: agent.py md5 `98655dbf` NEVER touched.
aim_voice_agent.py edits = PATCH DOC only (never live-edited here).

## Goal (3 founder bugs)
1. WARM TRANSFER over-talks + doesn't reliably ring/play music -> ONE short line + hold music +
   same-room dial + AI-exit + state logging (requested/started/completed/failed).
2. BOOKING page is UI-only -> AI `book_site_visit` must create a REAL appointment (persist +
   dashboard + link lead/campaign) with full lifecycle; manual + AI status.
3. Google Calendar OAuth -> vendor connects calendar; AI/manual bookings create cal events;
   reschedule/cancel update; sync ASYNC (never blocks the call).

## Architecture (DISJOINT, tracked, droplet-free, 0 heavy imports at load)
- `voice_ops/booking/` — tracked layer that WRAPS the gitignored droplet_work/booking schema
  (lazy `importlib` load of core.py at call-time; dormant-safe when absent). Adds the AI
  `book_site_visit` tool impl + lifecycle + W8 `site_visit_booked` event emit + tenant isolation.
- `voice_ops/gcal/` — Google Calendar OAuth (server-side flow), self-contained tracked AES-256-GCM
  refresh-token vault (does NOT depend on gitignored provider_registry; FORCE-RLS table DDL), async
  create/update/cancel on booking changes, reconnect-on-expiry.
- transfer hardening = helper in `voice_ops/booking/transfer.py` (pure planner: one-line ack +
  dial/exit sequence + state log) + PATCH DOC for aim_voice_agent.

## Units (IN PROGRESS / DONE)
- [DONE] explore + reconcile (read core.py/models.py/calendar_sync.py/events/credentials.py)
- [DONE] voice_ops/booking/config.py
- [DONE] voice_ops/booking/store.py  (lazy wrapper over droplet_work/booking/core.py)
- [DONE] voice_ops/booking/service.py (book_site_visit + lifecycle + event emit)
- [DONE] voice_ops/booking/transfer.py (transfer plan helper + state log)
- [DONE] voice_ops/gcal/config.py
- [DONE] voice_ops/gcal/vault.py (self-contained AES-GCM + RLS DDL)
- [DONE] voice_ops/gcal/oauth.py (auth url + code exchange + refresh)
- [DONE] voice_ops/gcal/sync.py (async create/update/cancel; reconnect-on-expiry)
- [DONE] voice_ops/booking/__init__.py + voice_ops/gcal/__init__.py
- [DONE] tests: voice_ops/booking/tests + voice_ops/gcal/tests
- [DONE] run pytest voice_ops/ + voice_kernel/ green  (170 passed)
- [DONE] design/W11-TRANSFER-BOOKING-GCAL-SEAM.md
- [DONE] memory/wave_runs/W11-transfer-booking-gcal.md append

## STATUS: COMPLETE. Founder action = Google OAuth client id/secret (see SEAM doc §Founder).
