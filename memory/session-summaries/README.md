> 🧭 **READ `MASTER-INDEX.md` FIRST** (caps repo root) — the single read-first orchestration index. STEP 0 of any compaction-resume is still: save the harness summary verbatim here (see protocol below), then read MASTER-INDEX.md → the detailed plans.

# 🗂️ SESSION-SUMMARIES ARCHIVE — never lose a compaction summary

When the harness compacts, it injects a big summary at the top of the NEXT context window — but that summary only lives in THAT window; the session after it loses it. This folder makes every compaction summary **permanent**, so the history compounds and nothing is ever lost across chained compactions.

## 🟥 COMPACTION PROTOCOL — do this STEP 0 of any session that resumes from a compaction (before anything else)
1. The harness gave you a summary at the top of this new context. **Immediately `Write` it VERBATIM** to `memory/session-summaries/<YYYY-MM-DD-HHMM>-<short-tag>.md`, with a header `# SESSION SUMMARY — <date> — <tag>` and a one-line "what was happening".
2. Append a one-line entry to the INDEX below (`- <date> <tag> → <file> — <hook>`).
3. THEN read, in order: `MASTER_PLAN.md` → `PLAYBOOK.md` → `ORCHESTRATOR.md` → `NEXT-BIG-BUILDS.md` → `AGENT_LEARNINGS.md`. Then continue the autonomous build.
This costs ~1 Write and guarantees the summary survives the NEXT compaction too.

## ♻️ FOREVER LEARNING/MISTAKE LOOP (compounds across all sessions)
- Every SESSION and every WORKFLOW/SUBAGENT appends its mistakes + learnings (one tight dated line: context — lesson) to **`AGENT_LEARNINGS.md`**; a NEW class of mistake also gets a numbered rule in **`PLAYBOOK.md §1`**.
- Every wave's agents READ `PLAYBOOK.md` + `AGENT_LEARNINGS.md` BEFORE starting. This is how each session is sharper than the last, and the session after sharper still — no mistake is ever made twice. **The future-of-the-future ultra-agent is built by never repeating a mistake.**

## 📇 INDEX (newest on top)
- 2026-06-15 did-swap-transfer-leads-restore → `2026-06-15-did-swap-transfer-leads-restore.md` — founder tested the live product; OUTBOUND RESTORED via Vobiz DID swap (new trunk `ST_bpGqmc9TL9Ph`, ring 3.46s), WARM-TRANSFER restored (aim-voice-agent restart to reload new trunk — inbound-only), LEADS-MGMT LIVE (`/leads` delete+sort, BUILD_ID `xF8YUvBmTwYj_yP4w7WY4`, Comm tab + Video Studio now visible), Telegram ecosystem diagnosed (post-call hook is outbound-only → no inbound follow-up; #1 fix = seed comm_sessions). LEARNING: an env change reaches only the processes you restart (caller restart ≠ voice-agent reload). Earner `9150fabe` UNCHANGED.
- 2026-06-14 autonomous-night-build → (live state, not yet compacted) — full picture in `MASTER_PLAN.md` + `ORCHESTRATOR.md`; queue in `NEXT-BIG-BUILDS.md`; lessons in `AGENT_LEARNINGS.md` + `PLAYBOOK.md`. Built tonight: switcher, perf-overhaul (app fast: 90% smaller payloads, virtualized, cached), recordings+transcript fixes, gold-mine sweep (27 net-new items), this archive system. RUNNING: multilingual-voice [wanazr7so]. Next: AIM-access → workflow → video-studio → vault → … (see NEXT-BIG-BUILDS).
