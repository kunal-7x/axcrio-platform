# 🧭 00 — READ THIS FIRST (post-compaction restore point)

> The founder compacts often and starts fresh. THIS folder is how a new session
> wakes up fully restored — what's done, what's pending, what we TRIED that failed,
> and every mistake to never repeat. Read this file, then 01→04, then drill into the
> plans. Nothing is lost. Treasure everything.

---

## ⚡ CURRENT LIVE TRUTH (2026-06-15 — reconciled, overrides any older "blocked" notes)

- ✅ **Outbound calling RESTORED.** Old DID was carrier-spam-blocked (SIP 486, no ring) from repeated test calls. Founder bought a NEW Vobiz DID → swapped via a NEW LiveKit outbound trunk `ST_bpGqmc9TL9Ph` (env `LIVEKIT_SIP_TRUNK_ID`). `agent.py` UNTOUCHED (md5 `9150fabe`). Real test call RANG (3.46s) + connected + conversed. Campaigns work again. (`design/W-DID-SWAP-STATE.md`)
  - 🙋 Founder action: ask Vobiz to KYC-confirm the new number for outbound so it doesn't get re-flagged.
- ✅ **Warm-transfer (human handoff) RESTORED.** It was broken because the running `aim-voice-agent` process still held the OLD trunk in memory (env captured at import). Fixed by `systemctl restart aim-voice-agent` (loaded the new trunk). Transfer is **INBOUND-only** (`aim_voice_agent.py:779 _do_warm_transfer`, `:1854 transfer_to_human`); handoff list populated. (`design/WARM-TRANSFER-DIAGNOSIS.md`)
- ✅ **Leads management LIVE** on panel.famit.in: `/leads` sort + delete-all (type-DELETE) + multi-select/per-row delete; `/run` manual-pick sort. caller golden `32e6062f`, panel BUILD_ID `xF8YUvBmTwYj_yP4w7WY4`. (`memory/wave_runs/leads-mgmt-feature.md`)
- ✅ **Communication tab + Video Studio now VISIBLE** on the panel (deployed with the leads wave).
- ✅ **Telegram comm system BUILT + LIVE** (DB, vault token, adapter, engine, poll worker `comm-poll.service`, brain, founder alert). Founder chat_id persisted; two-way chat works. ⚠️ **BUT the conversation HALLUCINATES** — `comm_sessions` is never seeded with the real call facts post-call → the #1 pending fix. Telegram also **cannot cold-message a lead's phone** (opt-in only). (`design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md` — 6-unit fix plan)
- 🌿 Current git branch: `fix/callback-retry-scheduling` (callback/retry scheduler rebuild in-flight; kill-switch hotfix `6aa1f32` already stopped the spam). FE work on `fe/unify-run-wavec`.
- 🔒 Earner law holds: `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` unchanged all session.

---

## 📚 THE RESTORE SET (read in order)

1. **`01-LEARNINGS-MASTER.md`** — ~75 deduped, categorized mistakes (EARNER-SAFETY · BOX/DEPLOY · VOICE/TELEPHONY · TELEGRAM/COMMS · ORCHESTRATION · UI · COMPACTION · FOUNDER-STYLE), `[HOT]` = most-painful at top. **READ THIS BEFORE ANY WORK** — it's how we stop repeating mistakes. (Append-only source: `AGENT_LEARNINGS.md`; rules: `PLAYBOOK.md`.)
2. **`02-DONE-LIVE.md`** — 49 verified-live items + 7 built-not-deployed gaps. **Don't rebuild what exists.**
3. **`03-PENDING-AND-TRIED.md`** — the full build queue (30+ items, ordered) + 13 dead-ends (why they failed) + 13 founder-action gates.
4. **`04-SESSION-HISTORY.md`** — the chronological journey (2026-06-03→06-18) + 17 founder preferences/working-style.

## 🗺️ THEN drill into (only what the next task needs)
`MASTER-INDEX.md` (the bird's-eye, points everywhere) → `MASTER_DNA_PLAN.md` (the why) → the per-domain `design/*-MASTER-PLAN.md` + `design/*-DIAGNOSIS.md` / `*-STATE.md`. Box is source of truth — pull + md5 before editing any deployed file.

## ♻️ COMPACTION PROTOCOL (do this every time)
On resume from a compaction: save the harness summary verbatim to `memory/session-summaries/<date>-<tag>.md` + index it; read this file; reconcile with `git status` + the latest `memory/wave_runs/*`. Every wave appends its output to `memory/wave_runs/<wave>.md` + a line to `WORKFLOW_LEDGER.md`. Every new mistake → a dated line in `AGENT_LEARNINGS.md`. **Future sessions: do this same thing. Never lose a line.**
