# Outbound Carrier-Block Diagnosis
**Run date:** 2026-06-14 ~14:35 UTC  
**Scope:** READ-ONLY evidence. Zero calls placed. Zero restarts. agent.py untouched.

---

## CHECK 1 — EARNER HEALTH

| Item | Evidence |
|---|---|
| famit-agent service | `active (running)` since 2026-06-10 19:58:18 UTC (3 days, unchanged) |
| MainPID | 1477083 — CONFIRMED, no restart |
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` — CONFIRMED, byte-identical |
| famit-caller /health (port 8209) | `{"status":"ok","checks":{"db":{"ok":true},"redis":{"ok":true},"livekit":{"ok":true}}}` |
| Recent agent errors (last 2h) | ZERO errors/tracebacks in journalctl |
| Latest agent log line | 2026-06-14T11:34:07Z — normal "transcript saved" exit after an inbound call |

**VERDICT: Earner infra is fully healthy. PID/md5/health all confirm no change.**

---

## CHECK 2 — SIP TRUNK STATUS

```
docker ps output (livekit-sip container):
  livekit-sip     Up 2 days
  livekit-server  Up 11 days
  livekit-redis   Up 11 days (healthy)
  livekit-egress  Up 2 days
```

No trunk registration errors in the last 24h logs. The SIP container is healthy and processing both inbound and outbound INVITE attempts on trunk `ST_fmtVmNJmpzKa`.

**VERDICT: SIP trunk container healthy, no registration failures.**

---

## CHECK 3 — VOBIZ BALANCE

API endpoint: `GET https://api.vobiz.ai/api/v1/Account/MA_0UX9IR0K/balance/INR`

```json
{
  "balance": 477.55,
  "available_balance": 477.55,
  "reserved_funds": 0,
  "status": "active",
  "is_postpaid": false,
  "low_balance_threshold": 50,
  "updated_at": "2026-06-14T14:29:27Z"
}
```

**VERDICT: Balance ₹477.55 INR — well above zero, no billing block possible.**

---

## CHECK 4 — SIP EVIDENCE (the key one)

### All outbound signaling timestamps on trunk ST_fmtVmNJmpzKa in the last 48h:

Every single call shows the same fingerprint:

```
result: "client_error"
reason: "busy"
inviteToTryingMs: 14–48ms   ← carrier ACKs the INVITE (so SIP is routing)
inviteToRingingMs: NOT PRESENT (field absent)  ← never got 180/183
status: 9 (= SIP 486 Busy Here)
```

**Full call log (chronological, all calls, last 48h):**

| Time (UTC) | CallID | To | inviteToTryingMs | inviteToRingingMs | Result |
|---|---|---|---|---|---|
| 2026-06-13 17:51:36 | SCL_qABVjZhTtMh5 | +917861019021 | 14ms | — | 486 busy |
| 2026-06-13 17:51:36 | SCL_n7WfzPtLo6eH | +916376980812 | 16ms | — | 486 busy |
| 2026-06-13 18:03:38 | SCL_gr3QxaDVYEun | +917987388671 | 15ms | — | 486 busy |
| 2026-06-13 18:10:38 | SCL_EHBtmR4aheK5 | +916375548830 | 21ms | — | 486 busy |
| 2026-06-13 20:00:13 | SCL_DgJmu2WTGsUi | +918949906361 | 39ms | — | 486 busy |
| 2026-06-13 21:51:33 | SCL_HKsfNHSBeHYT | +918839352959 | 39ms | — | 486 busy |
| 2026-06-13 21:53:33 | SCL_NSdrcg2mKaVe | +916376980812 | 20ms | — | 486 busy |
| 2026-06-13 22:41:02 | SCL_Dof5eXN6dEr9 | +916375548830 | 19ms | — | 486 busy |
| 2026-06-13 22:58:45 | SCL_wiFBeJjTxmJg | +917861019021 | 21ms | — | 486 busy |
| 2026-06-14 00:42:23 | SCL_R8eTmn8dKagf | +916375548830 | 39ms | — | 486 busy |
| 2026-06-14 03:30:47 | SCL_sPDxCmpWzWQT | +917861019021 | 19ms | — | 486 busy |
| 2026-06-14 03:30:47 | SCL_NHtwjThrRGpE | +917861019021 | 46ms | — | 486 busy |
| 2026-06-14 03:30:47 | SCL_rqFADcZPwkcm | +916376980812 | 46ms | — | 486 busy |
| 2026-06-14 03:30:56 | SCL_iwsHYAjmfe9v | +916375548830 | 20ms | — | 486 busy |
| 2026-06-14 06:43:38 | SCL_arYFPpTymsEA | +916375548830 | 48ms | — | 486 busy |
| 2026-06-14 08:02:03 | SCL_kw9WUKCJ8VTw | +916375548830 | 39ms | — | 486 busy |
| 2026-06-14 09:31:25 | SCL_ucVB7crT8qmN | +917861019021 | 39ms | — | 486 busy |
| 2026-06-14 09:32:25 | SCL_TBqVfXovVSt8 | +917861019021 | 21ms | — | 486 busy |
| 2026-06-14 10:02:32 | SCL_Vdj2TTs5bsdj | +916375548830 | 19ms | — | 486 busy |
| 2026-06-14 11:33:47 | SCL_JP837QSAbRjm | +917861019021 | 41ms | — | 486 busy |

**19+ attempts across multiple different destination numbers. EVERY ONE returns 486 Busy Here with no inviteToRingingMs. Zero calls rang anywhere.**

The most recent attempt (SCL_Vdj2TTs5bsdj at 10:02 UTC today) also logged explicitly:
```
sip/outbound.go:665  SIP invite failed  "error": "INVITE failed: sip status: 486: Busy Here"
```

**VERDICT: CARRIER BLOCK IS STILL ACTIVE. Not cleared. The 24h rest did not lift it.**

---

## CHECK 5 — CALL WINDOW / CONFIG FLAGS

- `CALL_WINDOW` env var: **not set** (code defaults to 09:00–21:00 IST — calls in the last 48h were within this window)
- `FORCE_WINDOW`: not set
- `SUPPRESSION_FILE`: config reference present but not blocking (separate per-number suppression, not the issue here)
- No other gate in `.env` that would independently block dialing

**VERDICT: No config-level gate is the cause. The block is at the carrier (Vobiz), not in the Famit code.**

---

## FINAL VERDICT

| | Status |
|---|---|
| **(a) Infra READY?** | YES — earner/PID/md5 CONFIRMED, trunk container healthy, Vobiz balance ₹477.55, no config gates |
| **(b) Carrier-block EVIDENCE** | **STILL BLOCKED** — 19+ calls across multiple destination numbers, all 486 Busy Here, inviteToRingingMs absent on every single attempt, most recent at 11:33 UTC today (well after 24h rest period) |
| **(c) Recommendation** | **Contact Vobiz support.** The 24h rest did NOT clear the carrier spam-flag on DID +918071583488. Next steps: (1) Open a Vobiz support ticket citing the DID and the automated-call spam pattern that flagged it. (2) Request caller-ID rotation to a new DID — this is the fastest unblock path. (3) Do NOT place any more test calls until Vobiz clears/rotates the DID, as each attempt re-triggers the same 486 and may extend the block TTL. Once Vobiz confirms the DID is cleared/rotated, the founder should place exactly ONE test call (not Claude) as the ring-gate. If it rings (inviteToRingingMs > 0 in the SIP logs), outbound build can proceed. |

**IMPORTANT NOTE on the 486 pattern:** The `inviteToTryingMs` is 14–48ms (non-zero), which means the SIP INVITE is reaching the Vobiz gateway and Vobiz is responding — this is NOT a SIP trunk misconfiguration or a Famit code error. The carrier is actively rejecting at the DID/A-number level. Vobiz controls the block; only they can clear it.

---

## WAVE 2 — AUTO-DIALER SOURCE FOUND + PAUSED (2026-06-14 ~15:00 UTC)

### Root Cause: `scheduler_loop` + `retry_queue.json`

The outbound INVITEs were fired by the **retry scheduler** inside `famit-caller.service` (`caller.py`), not by any manual campaign run or cron job.

**How it works:**
1. `caller.py` has a `scheduler_loop()` that runs every 60 seconds on startup (via `@app.on_event("startup")`).
2. On each tick it reads `/opt/famit-agent/var/retry_queue.json` and spawns `_spawn_retry_job()` for every entry whose `next_attempt_at <= now`.
3. `_spawn_retry_job()` creates a LiveKit room + SIP participant via `bridge.py` (POST `/v1/calls` to `127.0.0.1:8208`), which then fires the Vobiz INVITE via trunk `ST_fmtVmNJmpzKa`.
4. **Critical bug:** `scheduler_loop` does NOT check `attempts >= max_attempts` before spawning — only `next_attempt_at`, call window, and suppression list are checked. So entries at attempts=3/max_attempts=3 still fire.

### What was in the queue (11 entries across 3 campaigns):
| Lead | Phone | Campaign | Attempts | Next Due (IST) | Reason |
|---|---|---|---|---|---|
| colin | +917987388671 | c17e55e9f3 | 3/3 | Jun 14 23:33 | voicemail |
| Inbound caller | +918949906361 | c17e55e9f3 | 3/3 | Jun 15 01:30 | voicemail |
| nikhil | +918839352959 | c17e55e9f3 | 3/3 | Jun 15 03:21 | voicemail |
| कुणाल कुमार | +916376980812 | c17e55e9f3 | 3/3 | Jun 15 03:23 | voicemail |
| (unnamed) | +917861019021 | c17e55e9f3 | 3/3 | Jun 15 04:29 | voicemail |
| Founder Test | +917861019021 | 985c7e46c0 | 3/3 | Jun 15 09:01 | voicemail |
| कुणाल कुमार | +916376980812 | 985c7e46c0 | 3/3 | Jun 15 09:01 | voicemail |
| kunal kumar | +916375548830 | 985c7e46c0 | 3/3 | Jun 15 09:01 | voicemail |
| Founder | +917861019021 | (no campaign) | 3/3 | Jun 15 15:01 | voicemail |
| kunal kumar | +916375548830 | c17e55e9f3 | 2/3 | **Jun 14 21:32** ← IMMINENT | voicemail |
| Founder | +917861019021 | 42777c2c64 | 2/3 | Jun 15 09:00 | voicemail |

The entry for `+916375548830` was **75 minutes away from firing** at time of action.

### Action Taken (PAUSE — zero service restarts)
- Backed up: `/opt/famit-agent/var/retry_queue.json.PAUSED_20260614-201754.bak`
- Cleared: `/opt/famit-agent/var/retry_queue.json` → `[]`
- No famit-caller restart needed; scheduler reads the file live on each tick.
- No famit-agent touched whatsoever.

### Earner Gate (POST-PAUSE)
| Check | Result |
|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` — UNCHANGED |
| famit-agent MainPID | `1477083` — NOT restarted |
| /health (port 8209) | `{"status":"ok","checks":{"db":{"ok":true},"redis":{"ok":true},"livekit":{"ok":true}}}` |
| famit-caller PID | `2685432` — NOT restarted |
| New bridge POST /v1/calls after clear | **ZERO** |
| retry_queue.json after clear | `[]` |

### Bug to fix (non-urgent, DO NOT fix while DID is carrier-blocked)
`scheduler_loop` (caller.py line ~7131) must add a guard:
```python
if int(r.get("attempts", 0)) >= int(r.get("max_attempts", 3)):
    await _remove_retry(r["id"]); continue   # exhausted
```
This prevents exhausted retries from ever sitting in the queue and accidentally re-firing.

### Next Steps for Founder
1. **Contact Vobiz support** to clear/rotate DID `+918071583488` — the carrier spam-flag is still active; each attempt extends the block.
2. **Do not run any campaign or manually trigger a call** until Vobiz confirms the DID is cleared/rotated.
3. When ready to resume: restore the queue from the `.bak` file only for entries you actually want re-dialed (or start fresh campaigns). Do NOT restore the full queue blindly — it contains exhausted 3/3 entries.
4. The bug fix above should be applied before resuming retry-based campaigns.
