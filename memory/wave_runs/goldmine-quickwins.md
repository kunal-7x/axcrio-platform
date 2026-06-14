# GOLDMINE quick-wins wave (eval harness + cache + never-silent)

> Box `famit@168.144.153.145` key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`, source `/opt/famit-agent/`.
> Rule: EARNER-SAFE — agent.py md5 9150fabe NEVER touched, famit-agent NEVER restarted, additive only.
> KEY OUTCOME: both targeted quick-wins were found ALREADY SHIPPED + ALREADY ACTIVE on the live box.
> Zero box mutations were made this wave (re-editing live, working code = pure regression risk). Verified, not re-built.

---

## Phase 1 — EARNER GATE baseline (this session)
- agent.py md5 = `9150fabe4ff62b4b4470f9a87df346e5` (UNCHANGED — earner heart intact).
- famit-agent MainPID = **2808658**, ActiveEnter `2026-06-14 19:38:45 UTC` (note: differs from the prompt's
  historical 1477083 — it was restarted by another process before this wave; MY job is to NOT restart it, which I didn't).
- aim-voice-agent MainPID = **2739156**, ActiveEnter `2026-06-14 15:51:05 UTC`.
- caller `/health` (port **8209**) = HTTP 200; 0 recent 5xx; DID resting (no ring).

## Phase 2 — VERIFIED FLAG STATE (resolves the systemd-vs-.env confusion — verified, not assumed)
Checked BOTH locations as instructed:
- **systemd drop-in** `/etc/systemd/system/aim-voice-agent.service.d/vendor-script.conf` (the ONLY drop-in; FragmentPath = base unit):
  ```
  [Service]
  Environment=VENDOR_SCRIPT_INJECT=1
  Environment=CTX_CACHE=1          <-- already ON
  Environment=INBOUND_PROV_LOCK=1  <-- already ON
  ```
- **`/opt/famit-agent/.env`**: NONE of CTX_CACHE / INBOUND_PROV_LOCK / VENDOR_SCRIPT_INJECT present.
- **Running process `/proc/2739156/environ`** confirms the live worker actually has `CTX_CACHE=1` + `INBOUND_PROV_LOCK=1` + `VENDOR_SCRIPT_INJECT=1` exported.
- CONCLUSION: the flags live in the systemd drop-in (NOT .env), and they are genuinely exported to the live worker process. The W2-DEPLOY-STATE note "CTX_CACHE not set in env" was stale (true at W2-build time; the drop-in was added later, 2026-06-13/14).

## Phase 3 — #29 NEVER-SILENT GUARD: ALREADY SHIPPED (verified in box golden)
Box golden `aim_voice_agent.py` md5 `1614be09bfc10c8e3d91c2f68ea64e56` (pulled fresh -> `droplet_work/aim_voice_agent.LIVEBOX.py`).
The guard the task asked for is ALREADY present and correctly wired — two layers:
- **Outer entrypoint guard** `aim_voice_agent.py:2127-2147` (`async def entrypoint`): wraps `_entrypoint_impl`
  in try/except; on ANY uncaught exception it `say()`s an apology ("Sorry, the Famit AI Manager hit a problem.
  Please call again in a moment.") via `ctx._aim_session`, then `_hangup()`s cleanly. INBOUND-only.
- **Reachability** `:2498` `ctx._aim_session = session` — makes the outer guard able to speak.
- **Per-turn LLM/TTS guard** `:2508 _speak_recovery()` + `:2521 @session.on("error")`: on any session/LLM/TTS
  error speaks a short natural recovery line ("Ek second, thoda sa system slow hua — main aapke saath hoon,
  boliye."), debounced 4s — so a transient Groq/TTS blip = a voice within ~1s, never dead air.
- DECISION: re-adding the guard would be a duplicate + regression risk on working live code. Correct earner-safe
  action = VERIFY present (done) + report. No edit made.

## Phase 4 — CTX_CACHE: ALREADY ACTIVE (flag ON + reader wired + PROVEN at runtime)
The reader-wiring (the W2b follow-on that W2-DEPLOY-STATE listed as "dormant/TODO") is in fact DONE — it lives one
layer down in `ai_manager/voice_tools.py`, the central campaign-fields chokepoint that `aim_voice_agent.py` calls
via `_vt.campaign_fields`. My first grep against aim_voice_agent.py alone returned nothing, which is why the state
looked "dormant"; the wiring is in voice_tools:
- `voice_tools.py:37` `import context_store as _ctx_store`
- `voice_tools.py:449` `_fetch_full_campaign(cid)` (the loader)
- `voice_tools.py:472-481` W2 fast path: `if _ctx_store.is_enabled(): disk_path=.../var/campaigns/{cid}.json;
  ctx=_ctx_store.get_campaign_context(tenant, cid, _loader, disk_path)` -> falls back to direct HTTP `_get` on
  miss / flag-off (byte-identical when CTX_CACHE=0).
- **LIVE RUNTIME PROOF** (box venv `/opt/capsy-agent/.venv`, real env, read-only, no mutation):
  - `is_enabled: True`
  - COLD miss = **56.9ms** (loader ran once) -> WARM hit = **0.205ms** (loader did NOT re-run; served from L1) = ~277x faster.
  - Redis :6380 version-stamp invalidation works: after `bump_version`, next read re-loaded (loader 1->2). `redis: True`.
- CONCLUSION: CTX_CACHE is ACTIVE in production NOW (flag on + reader wired + verified warm-cache behavior). No
  restart was needed (the flag was already on the running worker). INBOUND_PROV_LOCK left EXACTLY as-is (=1; voice
  works on Sarvam bulbul — NOT touched).

## Phase 5 — FINAL EARNER GATE (GREEN, zero mutations this wave)
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- famit-agent PID **2808658** UNCHANGED (not restarted by me).
- aim-voice-agent PID **2739156** / ActiveEnter `2026-06-14 15:51:05` UNCHANGED (NOT restarted by me — none needed).
- caller `/health` 200, 0 5xx, NO ring.
- INBOUND_PROV_LOCK untouched (=1).
