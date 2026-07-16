# 🛑 HOLD-STATE — READ THIS FIRST (founder directive, 2026-06-15)

> A compaction wipes the live context window — only a short summary survives, not
> the detail. THIS FILE + `MASTER-INDEX.md` + `memory/wave_runs/` + the ledgers are
> the durable truth. After any compaction: read this file, then `MASTER-INDEX.md`.

## ⛔ STANDING ORDER — DO NOT LAUNCH ANY NEW WAVE
The founder explicitly said (repeatedly): **do not start anything new** until **the
founder personally tests Telegram and confirms it works.** Until he says "go" / "it
works", every other build is **QUEUED / PENDING only** — record it in
`MASTER-INDEX.md`, do **NOT** run it. No new Workflow launches. No box mutations.

## ✅ BOTH WAVES LANDED (2026-06-15) — now WAITING ON THE FOUNDER
- **master-index-compaction-proof** — DONE. `MASTER-INDEX.md` written (HOLD banner at
  §0). 
- **communication-telegram-build** — DONE + LIVE. Full system built (DB+RLS, vault
  token, adapter/engine, fail-closed HMAC webhook 6/6, hot-lead alert, post-call
  auto-summary, conversation brain, cost guards, FE tab built+committed). Flags ON for
  the founder tenant. Earner untouched (`9150fabe`). 26/27 verify PASS.

## ✅ TELEGRAM = PROVEN LIVE END-TO-END (2026-06-15, W1-P4, commit `8ad6bee`)
The founder tapped `@mr_kunal_bot`; chat_id `1862240811` derived + auto-persisted.
- **Real message landed** (message_id 4) — outbound send works.
- **Two-way conversation LIVE** — webhook port is private-only, so a standalone
  `comm/poll_worker.py` (`comm-poll.service`, systemd, Restart=always, running) long-polls
  getUpdates → brain → Riya replies. Real round-trips proven in logs; founder actively
  chatting. Same fail-closed HMAC verify (`derive_secret_token`).
- **Inbound-call alert armed** — `FEATURE_TELEGRAM_FOUNDER_ALERT=1`+`FEATURE_TELEGRAM_FOLLOWUP=1`;
  `_finalize_call` (caller golden `ccf9715b`) fires `comm.post_call.run` detached when a call
  ends interest≥70 → hot-lead alert to `1862240811`. No restart needed.
- Earner untouched (`9150fabe`, PID 2808658 NRestarts=0, /health 200, 0 5xx, no ring).
- **NOW: founder testing in real life.** Still HOLD on new waves until he confirms fully happy.

## 🟥 PANEL DEPLOY — STILL DEFERRED (not done; needs founder OK)
The Communication tab FE + Video Studio FE are built+committed on `fe/unify-run-wavec`
but the panel is NOT deployed yet (coordinated deploy held per the founder). The
Communication tab will not be VISIBLE on `panel.famit.in` until this deploy. The Video
Studio IS visible (its FE shipped in W9; only the BE mount was needed). Deploy only on
the founder's go.

## ✅ DONE + LIVE THIS SESSION (already shipped — do NOT rebuild)
- **Video Studio = REAL + LIVE.** Real composite MP4 rendered end-to-end (h264
  1080×1920 + AAC audio, 12s, playable); 2 videos in the Creative library; the real
  studio renders at `panel.famit.in/creative/video` (no placeholder). Built the
  missing `compose_worker.py`. Earner untouched. Log:
  `memory/wave_runs/video-studio-activate-real.md`.
- **Gold-mine quick-wins** — #29 never-silent guard verified live; CTX_CACHE active
  (0.2ms warm vs 57ms cold). Commit `e818f81`. Log:
  `memory/wave_runs/goldmine-quickwins.md`.

## 📋 PENDING QUEUE (recorded — run ONLY after founder green-lights, one wave at a time)
1. **Communication W2** — the multi-step LLM brain (after W1 tested + confirmed).
2. **Communication W3 — Email** (needs founder: Resend/SES API key).
3. **Communication W5 — SMS** (needs founder: MSG91 + DLT registration).
4. **Panel deploy** — Communication UI + Video Studio UI ship TOGETHER from
   `fe/unify-run-wavec` (deferred; deploy + verify on edge in one pass).
5. **Video render at scale** — deploy `compose_worker.py` on famit-hatchet
   `68.183.94.38` (current auto-spawn render works on-box; hatchet = the scale path).
6. **Telephony** — T0 scheduler-guard (caller.py hard-gate before campaign resume),
   T4 control UI, T5 cut-over (needs founder: BYO Plivo number + ONE ring-test).
7. **Gold-mine (after-caller.py-free queue)** — #33 DPDP consent, #35 mid-call
   lead_is_hot, #37 post-call workflow event, #30 inbound recording, #31 metering,
   #34 analytics, #47 warm-cache. (See `GOLDMINE-QUEUE.md` / `NEXT-BIG-BUILDS.md`.)

## 🙋 FOUNDER ACTIONS (only he can do — gates the above)
- **Vobiz**: unblock the spam-flagged DID or rotate to a new caller-ID (outbound is
  486-blocked; see `FOUNDER-VOBIZ-UNBLOCK.md`). DO NOT place test calls until cleared.
- **Telephony independence**: buy a BYO Plivo number → enables T5 cut-over.
- **Comms**: Resend/SES key (Email), MSG91 + DLT (SMS).
- **RAG dense**: OpenAI key (optional; FTS works without it).
- **agent.py outbound work**: sign-off + a real ring-test (gated on Vobiz fix).

## 🔐 NON-NEGOTIABLE RULES (every wave)
- **EARNER-SAFE**: NEVER edit/restart `agent.py` (md5 `9150fabe…`). Re-baseline md5
  fresh from the box each box step; caller `/health` 200; 0 5xx; NO ring.
- **Edit from the BOX golden**, not the stale repo. ONE box-mutating wave at a time.
- Panel deploys build from `fe/unify-run-wavec` (has ALL the UI).
- Every wave: flag-gated default-OFF + rollback + earner-gate + `gitleaks` 0 +
  append output to `memory/wave_runs/<wave>.md` + one line to `WORKFLOW_LEDGER.md`.
