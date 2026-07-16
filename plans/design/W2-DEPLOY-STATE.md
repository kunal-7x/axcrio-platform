# W2 — full-context cache + pooled HTTP (inbound, earner-safe, flag CTX_CACHE)

> Read order: `design/VOICE-BRAIN-MASTER-PLAN.md` (W2 row) → this → `AGENT_LEARNINGS.md`.
> Box `famit@168.144.153.145` key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`, source `/opt/famit-agent/`.
> Local mirror `C:\Users\kunal\Desktop\caps\droplet_work`.

## Earner gate (run before+after) — PASS @ start
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED
- famit-agent MainPID `1477083` NOT restarted (active since 2026-06-10 19:58:18)
- caller `/health` 200 (port **8209**, NOT 8000), 0 5xx, NO ring (DID resting)
- Redis :6380 PONG, redis lib 8.0.0, CTX_CACHE not set in env

## Scope (3 units)
1. **U1 — pooled httpx merge** — ✅ ALREADY DONE. The box's `/opt/famit-agent/ai_manager/voice_tools.py`
   (md5 `63c3f89b…`) AND the local mirror `droplet_work/ai_manager/voice_tools.py` ALREADY carry the
   `_POOL` keep-alive pooled client (lines 41-70, FIX(E)) identical to `.boxwork/handoff/voice_tools.py`.
   The "built-not-merged" handoff was merged in the W1 deploy. Nothing to do; verify only.
2. **U2 — context_store.py** — NEW module. LRU TTL 300s keyed `(tenant_id, cid)` holding full campaign
   context; Redis :6380 version-stamp invalidation bus (bump on save, NOT just TTL); PG/disk fallback on
   miss; loaded ONCE at connect → per-turn ~0. ALL behind `CTX_CACHE` (default 0 → today's direct path).
3. **U3 — caller.py save-path version bump** — on create (`save_campaign` :1423) AND edit
   (`update_campaign` :4028) publish a cache-invalidate (version bump) on the bus. Flag-gated, swallows.

## How invalidation works (version stamp, NOT just TTL)
- Redis key `ctxver:{tenant_id}:{cid}` holds a monotonically-bumped integer.
- On load, the store reads the disk file's `_ctx_version` (mtime_ns based) + the Redis version; the cache
  entry stores the version it was built with. A `get()` compares the LIVE version stamp to the cached
  one; if they differ → cache miss → reload. So a compliance-line edit invalidates IMMEDIATELY (next
  load), not after the 300s TTL. Redis-down → falls back to the disk-mtime stamp (self-corrects on next
  file change), so correctness never depends on Redis.

## How flag-off preserves today's path
- `CTX_CACHE` default `0`. When off: `context_store` is never consulted by any caller; the save-path
  publish is a no-op (guarded `if _ctx_cache_on()`). voice_tools reads stay the exact HTTP `_get` path.
  → byte-identical to today. The module is import-safe (no side effects at import; lazy Redis).

## Files
- `droplet_work/context_store.py` (NEW)
- `droplet_work/caller.py` save-path publish (`save_campaign`, `update_campaign`)

## Status — ✅ DONE + DEPLOYED + VERIFIED 2026-06-14
- [x] U1 pooled httpx — already merged+deployed (box voice_tools md5 `63c3f89b…` has `_POOL`); verify-only.
- [x] U2 context_store.py written + py_compile + 7/7 local unit tests PASS (flag-off None+no-loader;
      miss-loads-once; L1-hit-no-reload; tenant-isolation; disk-mtime invalidate; invalidate() reload;
      loader-None fallback; bump redis-down no-raise).
- [x] U3 caller.py publish wired (`save_campaign` :1466 + `update_campaign` :4095, helper :174) + py_compile.
- [x] deploy box: backup `caller.py.W2bak.20260614-055231`; scp md5-gated (context `245d864f`, caller
      `19a7ac1f` box==local); box py_compile + import-test OK (redis:True on :6380); atomic mv;
      restarted **famit-caller + aim-voice-agent ONLY** (famit-agent untouched).
- [x] EARNER GATE after PASS: agent.py `9150fabe…` UNCHANGED, famit-agent PID `1477083`/ActiveEnter
      `2026-06-10 19:58:18` NOT restarted, caller `/health` 200, 0 5xx, NO ring.
- [x] LIVE version-bus probe PASS (real Redis :6380): bump INCR 0→1; miss→hit loader=1; invalidate→loader=2.
- [x] flag-off no-op PROVEN: CTX_CACHE NOT in .env (default OFF) → `_publish_ctx_invalidate` creates 0 redis
      keys → byte-identical to today.
- [x] commit per unit

## Box deploy facts
- context_store.py md5 `245d864fcd90e77edaad4f7ee0f42d3c` (box == local mirror)
- caller.py md5 `19a7ac1f29b51b81cd0d38346f1649b8` (box == local mirror; was `992c08ff…`)
- backup `caller.py.W2bak.20260614-055231`

## Residual / activation
- The cache is DORMANT until `CTX_CACHE=1` is set in `/opt/famit-agent/.env` AND the inbound
  reader (aim_voice_agent.py connect) is wired to call `context_store.get_campaign_context(...)` with a
  loader. That READER wiring is a follow-on (W2b) — this wave shipped the module + the save-path bus +
  the pooled client, all flag-gated OFF. Outbound earner unaffected (flag-off + agent.py untouched).
