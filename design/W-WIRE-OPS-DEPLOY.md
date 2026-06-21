# W-WIRE-OPS — DEPLOY runbook: wire the real-time ops backbone (flag-gated)

The BUILT-but-unwired ops modules are now spliced into the live FastAPI app
`caller.py` (service `famit-caller`, :8209). This is the **exact deploy + gated
flip order + per-flag smoke + rollback**. The founder problem it closes:
"nothing is live — recordings / hot-leads / dashboard / CRM never update."

> EARNER LAW — NEVER touch `agent.py` / `famit-agent`. Restart ONLY `famit-caller`.
> Every feature is behind its own flag, **default OFF**. With all flags OFF the
> wired build is byte-identical to today (no singleton engages). Edit from the BOX
> GOLDEN caller.py. `/health` 200 before+after. Rollback = restore the caller.py
> backup + restart `famit-caller`.

---

## 0. What was wired (the seam patches, all in `caller.py`)

| Wave | Founder outcome | Seam | REAL env flag (the module config reads) |
|------|-----------------|------|-----------------------------------------|
| **W8** event backbone | every call/lead/recording/booking event is emitted live | `_ev()` + emit-sites in `_finalize_call` + `call_started` in `run_job` | `EVENTBUS_ENABLED` (+ `EVENTBUS_REDIS_URL`) |
| **W9** recording finalize | recording appears in **seconds**, not 20-60 min | detached `StagedPipeline.run` in `_finalize_call` + read self-heal in `_outbound_rec_item` | `RECORDING_FINALIZE_ENABLED` (+ R2/B2 creds) |
| **W14** reporting + AIM live | dashboard date-range + hot-leads update live; AI-Manager reads the SAME live numbers | 9 `GET /report*` routes + `POST /ai-manager/report` | `REPORTING_ENABLED` |
| **W7** lead lifecycle + AI summary | CRM lead flips hot/warm/cold/dead + gets an AI summary after each call | `_w7_lifecycle_after_call` in `_finalize_call` | `LEAD_LIFECYCLE_ENABLED` |
| **W10** smart callback cadence | re-enable callbacks **safely** (anti-runaway) | `enqueue_smart` in finalize + recon sweep; `fire_due` in `scheduler_loop` | `CALLBACK_CADENCE_ENABLED` (+ existing `RETRY_SCHEDULER_ENABLED`) |

> Flag-name note: the founder's labels (EVENTS_ENABLED / RECORDING_FINALIZE_POLL /
> REPORTING_ENABLED / LEAD_LIFECYCLE_ENABLED / CALLBACK_CADENCE_ENABLED) map to the
> REAL env vars the module `from_env()` configs actually read (above). Use the REAL
> names in the systemd drop-in — they are load-bearing.

The legacy flat-file callback path is **gated, not deleted** — when
`CALLBACK_CADENCE_ENABLED` is OFF, the old `_enqueue_retry` path runs exactly as
today; when ON, the cadence engine owns the enqueue/dial. Reversible by the flag.

---

## 1. PRE-FLIGHT (ground truth)

- Box: `famit@168.144.153.145`, key `~/.ssh/do-blr-test/id_ed25519`
- Box golden `caller.py` md5 = `6d9f9e7d0631454c7603bda9b4c02643` (8177 lines).
  If the live md5 differs, RE-PULL the golden and re-apply (do not deploy a stale local).
- `agent.py` / `famit-agent` md5 — record it, must be UNCHANGED at the end.
- `voice_kernel/` IS already on the box. **`voice_ops/` is NOT** — it must be shipped
  (W9/W14/W10/AIM all import from `voice_ops`). With it absent, the W9/W14/W10 imports
  fail closed (try/except → singletons None) so the flags are inert — but the features
  never activate. Shipping `voice_ops/` is REQUIRED for the flips to do anything.

---

## 2. DEPLOY STEP A — ship `voice_ops/` to the box (additive, no restart needed)

```bash
KEY=~/.ssh/do-blr-test/id_ed25519
H=famit@168.144.153.145
# rsync the tracked package tree (exclude pycache/tests are fine to include)
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=no" \
  --exclude '__pycache__' \
  voice_ops/ "$H:/opt/famit-agent/voice_ops/"
# verify it imports on the box PYTHONPATH
ssh -i $KEY $H 'cd /opt/famit-agent && python3 -c "import sys; sys.path.insert(0,\".\"); \
  import voice_ops.recording, voice_ops.reporting, voice_ops.callback, voice_ops.ai_manager_live; \
  print(\"voice_ops OK\")"'
```
Expected: `voice_ops OK`. (`voice_kernel/` is already present; re-rsync it only if
its md5 drifted from the repo.) Shipping the package alone changes NOTHING live —
nothing imports it until the wired caller.py is deployed AND a flag is ON.

## 3. DEPLOY STEP B — deploy the wired caller.py (root-owned)

```bash
# 1. backup the live golden ON the box (timestamped)
ssh -i $KEY $H 'sudo cp /opt/famit-agent/caller.py \
   /opt/famit-agent/caller.py.WIREOPSbak.$(date +%Y%m%d-%H%M%S)'
# 2. scp the WIRED file to a staging path, then sudo cp into place
scp -i $KEY .wireops_work/caller.py.WIRED $H:/tmp/caller.py.WIRED
ssh -i $KEY $H 'cd /opt/famit-agent && python3 -m py_compile /tmp/caller.py.WIRED && \
   sudo cp /tmp/caller.py.WIRED /opt/famit-agent/caller.py && rm -f /tmp/caller.py.WIRED'
# 3. restart ONLY famit-caller (NEVER famit-agent)
ssh -i $KEY $H 'sudo systemctl restart famit-caller'
# 4. /health 200 + agent.py md5 unchanged
ssh -i $KEY $H 'curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8209/health; \
   md5sum /opt/famit-agent/agent.py'
```
At this point ALL flags are still OFF → the service runs byte-identical behavior
(every singleton built `None`/disabled). This proves the additive code is inert.

### EARNER REGRESSION GATE (do this before ANY flag flip)
Place ONE real outbound call from the panel and confirm it RINGS + connects + the
agent talks normally. The wired-but-flags-OFF build MUST behave exactly as before.
If anything regresses → ROLLBACK (§7) immediately.

---

## 4. THE GATED FLIP ORDER (one flag at a time; smoke each before the next)

All flags go in the **systemd drop-in** for `famit-caller`, NEVER the shared `.env`
(a shared-.env flag leaks across the inbound agent + the outbound earner on restart):

```bash
ssh -i $KEY $H 'sudo systemctl edit famit-caller'   # adds /etc/systemd/system/famit-caller.service.d/override.conf
# then: sudo systemctl daemon-reload && sudo systemctl restart famit-caller
```

Flip in THIS order (least-blast-radius first; each is independently revertible):

### FLIP 1 — `EVENTBUS_ENABLED=1` (+ `EVENTBUS_REDIS_URL=redis://127.0.0.1:6379/0`)
W8 is the substrate W9+W14 ride on. After restart:
- SMOKE: place one outbound call. On the box: `redis-cli XLEN vk:events:<tenant_id>`
  is > 0 and grows per event; `redis-cli XRANGE vk:events:<tenant_id> - + COUNT 10`
  shows `call_started/call_ended/summary_ready/...`. `/proc/<famit-caller pid>/environ`
  shows `EVENTBUS_ENABLED` (and `famit-agent`'s does NOT).
- GATE: a real call still rings; `/health` 200; no 5xx in the caller log.
- REVERT: drop the drop-in line + restart → `_EVBUS` is None → zero emits.

### FLIP 2 — `RECORDING_FINALIZE_ENABLED=1` (+ R2/B2 creds per `RecordingConfig`)
Needs FLIP 1 (emits `recording_ready` on the same bus). After restart:
- SMOKE: place a recorded outbound call. `recording_status` flips `recording →
  completed` within SECONDS (panel recordings tab plays it almost immediately, not
  20-60 min). The tenant stream shows `recording_ready → transcript_ready →
  summary_ready` in order. A row stuck at "recording" self-heals on the next panel read.
- GATE: a real call still rings; the existing recon sweep (`scheduler_loop`) is
  untouched as the second net.
- REVERT: drop the line + restart → no finalize task scheduled; reads fall back to
  the existing sync HEAD-check.

### FLIP 3 — `REPORTING_ENABLED=1`
Mounts the live `/report*` + `/ai-manager/report` routes. NOTE: the read-model is
filled by a SEPARATE consumer worker tailing the W8 stream (deploy
`voice_ops_reporting_worker.py` as its own systemd unit — see W14 seam §4). Until
that worker runs, the routes return zeros (never an error).
- SMOKE: `GET /report?preset=today` (with a tenant token) → 200 with
  `range:{preset:today,...}` + `totals`. After the consumer is up + a live call,
  `totals.calls` increments; `GET /report/hot-leads` lists the hot lead;
  `POST /ai-manager/report {"message":"how many calls today"}` returns the SAME number.
  A second tenant's token sees none of tenant-1's data (isolation).
- GATE: with the flag OFF the routes return 503 (not mounted-live); a real call rings.
- REVERT: drop the line + restart → routes 503; panel falls back to legacy
  `/analytics`/`/stats`.

### FLIP 4 — `LEAD_LIFECYCLE_ENABLED=1`
After each completed call the lead row gains `lifecycle` (hot/warm/cold/dead) +
`ai_summary` + `next_action` + `conversion_prob`.
- SMOKE: place a call that engages → the CRM lead flips to warm/hot with a summary;
  an opt-out call → dead (sticky). Existing `score`/`last_outcome` are NOT regressed
  (additive write only).
- GATE: a real call rings; `_w7_lifecycle_after_call` never raises into finalize.
- REVERT: drop the line + restart → no lifecycle write; legacy lead fields unchanged.

### FLIP 5 — `CALLBACK_CADENCE_ENABLED=1` (the careful one — anti-runaway)
Two-step, per the W10 seam:
1. Flip `CALLBACK_CADENCE_ENABLED=1` while `RETRY_SCHEDULER_ENABLED=0` stays.
   The cadence engine SCHEDULES (queue fills with correct cadence times, no
   answered-call entries, attempts monotonic) but NOTHING dials.
   - SMOKE: a no-answer enqueues the next dial at **D1** (not +2h); a pickup leaves
     the lead `CALLED` with ZERO further entries; attempts never reset across recon ticks.
2. ONLY THEN flip `RETRY_SCHEDULER_ENABLED=1` so `fire_due` dials.
   - SMOKE: the first cadence dial fires at the RIGHT time; a pickup is never
     redialed; the lead `EXPIRES` after `max_retries` (queue does not refill); no
     min-gap violation. (Proven anti-runaway in tests: 60-day time-advance + re-enqueue
     on every no-answer → exactly 1 dial then EXPIRED, never the old 10-11×/night.)
- GATE: a real call rings throughout.
- REVERT: both flags → `0` + restart → engine never engages → legacy flat-file path
  (or fully off) → byte-identical to today.

---

## 5. PER-FLAG SMOKE — quick command cheat-sheet (on the box)

```bash
# event stream growing
redis-cli XLEN vk:events:<tenant_id>
# recording flipped
curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:8209/calls/<id>/recording | jq .recording.recording_status
# reporting live
curl -s -H "Authorization: Bearer <token>" "http://127.0.0.1:8209/report?preset=today" | jq '.range,.totals.calls'
# AI-Manager live = same number
curl -s -X POST -H "Authorization: Bearer <token>" -d '{"message":"how many calls today"}' http://127.0.0.1:8209/ai-manager/report | jq .reply
# which flags are on THIS process (must NOT be on famit-agent)
sudo tr '\0' '\n' < /proc/$(pgrep -f 'caller.py')/environ | grep -E 'ENABLED'
# earner untouched
md5sum /opt/famit-agent/agent.py
```

---

## 6. FRONTEND (W15 — auto-upgrades)

The panel (W15) already auto-detects the live `/report*` routes and swaps from the
legacy poll to real data the moment they mount. No frontend deploy is required for
the data to go live; the SSE push (instant invalidate) is a follow-on (W14 seam §5):
deploy the consumer/SSE bridge unit + `lib/events.ts` to replace the 30s poll with a
push. Until then the panel's React-Query refetch on the report routes is already live.

---

## 7. ROLLBACK (any time, fast)

- **Per-feature:** remove that flag's drop-in line → `daemon-reload` → restart
  `famit-caller`. That feature goes inert; everything else stays.
- **Full:** restore the caller.py backup + restart:
  ```bash
  ssh -i $KEY $H 'sudo cp /opt/famit-agent/caller.py.WIREOPSbak.<ts> /opt/famit-agent/caller.py && \
     sudo systemctl restart famit-caller && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8209/health'
  ```
- `voice_ops/` can stay on the box (additive, imported only when a flag is ON). To
  fully remove: `rm -rf /opt/famit-agent/voice_ops` after caller.py is rolled back.
- `agent.py` / `famit-agent` are NEVER part of this — they are untouched throughout.

---

## 8. DEFINITION OF DONE
1. `voice_ops/` imports on the box (`voice_ops OK`).
2. Wired caller.py deployed; `/health` 200; a real outbound call RINGS (flags OFF).
3. `agent.py` md5 unchanged; only `famit-caller` was restarted.
4. Each flag flipped in order, each with its smoke green, before the next.
5. The founder sees recordings appear in seconds, hot-leads + dashboard date-range
   update live, the CRM lead updates after each call, and callbacks fire on the warm
   cadence with NO runaway.
