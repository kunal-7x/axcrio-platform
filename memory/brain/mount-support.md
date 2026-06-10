# BRAIN — MOUNT: support router into caller.py (2026-06-10)

Durable facts + hard-won learnings. Append, never delete. Full log: build_log/wave-build-mount-support.md.

## STATE: MOUNTED, flag-gated DEFAULT-OFF, gate GREEN
- support router IS NOW MOUNTED behind `FEATURE_SUPPORT` (default OFF) at the END of caller.py (after the
  payments block). Pattern = **wire-then-include** (checklist row #6), the payments twin — NOT build_router.
- Box+local caller.py md5 = `babf0494480e9a1395e578f9e721ed21` (box 4204 LOC / local 3746 by CRLF count).
- Rollback target (post-payments-mount, clean) = `e4cbcad565d5e94f131a268ed910d191`, box backup
  `caller.py.MNTbak.1781094726`. Rollback: `cp` that backup over caller.py + `systemctl restart famit-caller`.
- Mount order in caller.py tail now: ads-engine → media-gen → booking → payments → support.

## LOAD-BEARING GOTCHAS (do not relearn)
- `wire()` is **KEYWORD-ONLY**: `wire(resolve_tenant=, can=, need_auth=, forbidden=, firewall=)`. Positional
  TypeErrors. (Same as payments; booking/media-gen's build_router took positional — support does NOT.)
- Router has **NO internal prefix** — `/support` is applied at `include_router(..., prefix="/support")`.
  Health path = `/support/health` (NOT /status). 10 route objects / 10 unique paths (no GET+POST collapse).
- `support.init()` is **NOT in startup ON PURPOSE**: it calls `ensure_schema()` (touches PG/DDL) → would run
  with the flag OFF → breaks byte-identical-when-OFF. ensure_schema() is LAZY/`_schema_ready`-guarded/never
  raises; routes self-degrade (PG down→unavailable; empty KB / no LLM→extractive draft, grounded-or-escalate).
  So init() is NOT a route prerequisite. When activating: gate init() INSIDE the flag-on block, never top-level.
- `models.py` declares its OWN `Base(DeclarativeBase)` (booking-style) — but it is NOT in the router import
  path (`__init__`→core→agent→sentiment; core imports only stdlib+sentiment at top). So no import-time risk.
- ⚠ **STALE /tmp/caller.py SHADOWS THE IMPORT** — the burn of this wave. A leftover `/tmp/caller.py` (old
  pre-mount version) made `import caller` resolve to it (Python puts the script's dir, `/tmp`, on sys.path[0])
  → spine smoke falsely showed 0 routes + all FEATURE_* attrs MISSING. ALWAYS run the spine smoke FROM
  `/opt/famit-agent` (or check `caller.__file__`), and `rm /tmp/caller.py` first if present. False-negative trap.
- scp can `Connection reset` mid-transfer and leave the box file UNCHANGED — **md5-verify after EVERY scp**
  (caught it: box stayed `e4cbcad5` until the retry).
- caller.py is UTF-8 with em-dash/⚠ bytes that render as mojibake (`â€”`) in tool output — anchor Edits on
  ASCII-clean lines (the final `_lg_payments...warning(...)` line), keep new blocks pure ASCII, deploy via scp
  (byte-preserving). Never round-trip caller.py through Out-File/Set-Content.

## VERIFICATION (this wave, HONEST)
- Box py3.12.3 UNGUARDED import smoke: `from support.router import router,wire` clean → 10 routes; status() no-raise.
- Spine smoke both flag states (correct file): OFF→0 /support paths (79 total, byte-identical), ON→10
  /support/* paths (89 total). Done WITHOUT restarting the live service.
- Post-restart regression gate GREEN: legacy /me,/campaigns,/leads,/contacts,/billing/overview=200;
  /support/health,/support/tickets=404 (flag-off); /run dispatches job_id `b257df30b0` count=1 with the only
  lead suppressed (suppressed_count=1) → NO paid call; zero 5xx/traceback; both services active; md5 box==local.
- ⚠ NOT proven (box-only, deferred to flag-ON+creds): real PG DDL apply, RLS isolation, live ingest→draft→
  escalate. The smokes prove IMPORT/MOUNT/DEGRADE/byte-identical-OFF only.

## TO GO LIVE LATER (founder/orchestrator)
`FEATURE_SUPPORT=1` in /opt/famit-agent/.env + restart → 10 /support routes (authed, token-derived, org_id=
resolved tenant; /resolve firewall-step-up-gated). Tables materialize lazily on first authed call. Then:
KB content (F2) for grounded replies, LLM key (GROQ/ANTHROPIC via AIWF_LLM_PROVIDER) for generative drafts,
channel creds (Meta WhatsApp BSP/email) to SEND + verify webhooks (DRAFT-only today). Deferred: support.init()
in startup (inside flag-on), runner tool-catalog + /tickets loopback, channel adapters, crm 'support' timeline.
