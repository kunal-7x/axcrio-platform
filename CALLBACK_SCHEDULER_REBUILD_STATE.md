# CALLBACK/RETRY/SCHEDULER REBUILD — ORCHESTRATOR / STATE (crash-safe)

**Goal:** the auto-retry/callback scheduler redialed leads ~every 2h non-stop (even after pickup).
STOP it (done), then REBUILD correct: ≤2 retries, next-day cadence, no-callback-on-pickup,
busy→short reschedule, "call me at X"→that time, dedup, compliance, + frontend control. Founder
mandate: fill ALL blind spots, full ownership, may override his instructions.

**Branch:** `fix/callback-retry-scheduling` (off `fix/voice-brain-language-natural`).

## STATUS
- [x] Root-caused the spam in `caller.py` scheduler_loop (infinite re-enqueue, callback-on-answered).
- [x] **KILL-SWITCH DEPLOYED — spam STOPPED** (commit `6aa1f32`). `RETRY_SCHEDULER_ENABLED` default OFF
      gates the dial point; box caller.py md5 `6d9f9e7d`; `retry_queue.json` cleared (7 spam entries;
      evidence in `var/retry_queue.evidence.*`). Box backup `caller.py.bak.20260616-041519`.
      ⚠️ Local caller.py was STALE (`ef9ae696` != box `32e6062f`) → pulled live first;
      `caller.LIVE-BASELINE.py` pristine, `caller.LOCAL-PRESESSION.py` = prior session's undeployed local.
- [~] **IN PROGRESS:** Workflow 1 = REBUILD DIAGNOSIS+DESIGN (read-only): Haiku explore → Sonnet research
      → Sonnet diagnose → Opus/Sonnet RED-TEAM (biggest) → Opus synth → writes
      `droplet_work/_scheduler_rebuild/DESIGN_SPEC.md`. Brief: `_scheduler_rebuild/REQUIREMENTS.md`.
- [ ] Review spec → Workflow 2 = EXECUTE (Opus build the rebuilt engine on branch + red-team + offline test).
- [ ] Deploy gated (sudo cp — caller.py is ROOT-owned, scp to /tmp then sudo cp; restart famit-caller) +
      founder verifies on real flow → re-enable `RETRY_SCHEDULER_ENABLED=1` → merge.

## #1 BLIND SPOT — RESOLVED (verified 2026-06-16): the Go scheduler is NOT a second dialer.
## famit-bridge :8208 had ZERO call POSTs in 6h (last activity Jun 14, only health checks);
## 0 retry dials + 0 calls in 30 min after the kill-switch. caller.py scheduler_loop was the SOLE
## spam source (2h = backoff[0]=120min). Spam definitively stopped.

## DEPLOY caller.py (root-owned): scp to /tmp/x.py → `sudo cp /tmp/x.py /opt/famit-agent/caller.py`
## → `sudo systemctl restart famit-caller`. SSH: famit@168.144.153.145 key do-blr-test/id_ed25519.
## REVERT: `sudo cp /opt/famit-agent/caller.py.bak.20260616-041519 /opt/famit-agent/caller.py` + restart.

---

# W10 — SMART CADENCE ENGINE (branch fix/realtime-voice-kernel-v2, 2026-06-18)

The disjoint TRACKED rebuild lives under `voice_ops/callback/` (NOT droplet_work).
0 droplet/agent imports (lazy). caller.py NOT edited — patch DOC only in
`design/W10-CALLBACK-SEAM.md`. Reuses voice_kernel.events (W8 emit) +
voice_kernel.events.timeutil (UTC/IST) + voice_kernel.memory continuity (W7).

## Units (flip DONE as each verifies)
1. config.py — CallbackConfig (flags, cadence Day0/1/3/7/14/30, max<=2, DND, busy) — DONE
2. store.py — CallbackStore Protocol + InMemoryCallbackStore (lead-lock, idempotent upsert) — DONE
3. intent.py — "call me at 5pm/tomorrow/Sunday" -> ISO scheduled_at — DONE
4. cadence.py — enqueue_smart (outcome guard, attempts, dedup, context carry, emit) — DONE
5. scheduler.py — fire_due (due-check, max-attempts guard, DND window, lock) — DONE
6. __init__.py — public surface — DONE
7. tests/ — pytest (advance, max cap, no-redial-after-answer, "5pm", busy, dedup, OLD-runaway regression) — DONE
8. design/W10-CALLBACK-SEAM.md — caller.py patch DOC + re-enable flag — DONE
9. memory/wave_runs/W10-callback.md append — DONE

## Bugs closed (EXPLORE map): A=2756 no outcome guard; B=2755/1637 attempts=0 reset->infinite;
## C=7285 recon same; D=7294 recon attempts=1/tick; E=7241 no max guard; F=2754/7284 [120,360,1440] no cadence.

## Decisions
- Cadence offsets (mins from lead arrival): [0, 1440(D1), 4320(D3), 10080(D7), 20160(D14), 43200(D30)];
  MAX_RETRIES default 2 caps it (3 cadence touches total: T0 + up to 2 retries).
- Connected/answered => NEVER schedule cadence retry (no-redial-after-answer). Exception:
  explicit "call me at X" => exact-time callback, highest priority, honored even after answer.
- Busy -> BUSY_RETRY_MINS (default 25), max 1 busy retry/day, NOT counted as a cadence attempt.
- Dedup/lock key = (tenant_id, phone). Terminal status (CALLED/EXPIRED/OPT_OUT) never re-enqueued.
- attempts ONLY ++ via record_attempt; re-enqueue NEVER resets (kills bug B/D).
- DND 09:00-21:00 IST; fire time outside -> advance to next 09:00 IST.
- Context carry: last_summary stored on entry; fire_due returns it for continuity (W7).
- Idempotent + flag-gated (CALLBACK_CADENCE_ENABLED default OFF) + tenant-tunable.
