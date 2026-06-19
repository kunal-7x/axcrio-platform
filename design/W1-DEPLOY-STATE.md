# W1 DEPLOY+VERIFY — STATE (crash-safe)

**Wave:** W1 backend deploy (caller.py + prompt.py + aim_voice_agent.py) + FORTRESS panel deploy + verify.
**Branch:** backend/handoff-name-clean-line. FE commit aae7e0a, BE commits f87f101/db9ddbf/8d6df34 — ALL committed, NOT deployed.

## EARNER GATE (must hold before+after every box step)
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED
- famit-agent PID `1477083` NOT restarted (ActiveEnter 2026-06-10 19:58:18)
- famit-caller /health 200, 0 real 5xx, NO ring
- prompt.py golden byte-diff (flag OFF) == IDENTICAL (run oracle ON BOX)
- Restart ONLY famit-caller + aim-voice-agent. NEVER famit-agent.

## SOURCE OF TRUTH (repo-naming trap — honor it)
- BOX prompt.py  <= droplet_work/prompt.LIVEBOX.py  (md5 de2fd2a7c4b162fd995ccd60668066fc was the baseline pre-edit; now has v2)
- BOX aim_voice_agent.py <= droplet_work/aim_voice_agent.LIVEBOX.py
- BOX caller.py  <= droplet_work/caller.py  (plain name IS box-truth)
- Box: famit@168.144.153.145  key C:\Users\kunal\.ssh\do-blr-test\id_ed25519  src /opt/famit-agent/

## STEPS
- [ ] S0  box reachable + capture pre-deploy md5/PID/health baseline
- [ ] S1  py_compile all 3 locally + gitleaks 0
- [ ] S2  capture golden render of legacy campaigns on box (flag OFF) BEFORE deploy
- [ ] S3  backup-first box copies of all 3 + scp + md5-gate + py_compile on box
- [ ] S4  run golden oracle ON BOX flag OFF == identical (EARNER GATE prompt.py)
- [ ] S5  restart famit-caller + aim-voice-agent ONLY; /health 200
- [ ] S6  VERIFY item1: >3k vendor script byte-equal on campaign_fields(cid) + _load_campaign fields
- [ ] S7  VERIFY item2: dry-run shows vendor greeting adopted
- [ ] S8  VERIFY item3: injection canary NOT echoed/obeyed + </vendor_script> escaped
- [ ] S9  VERIFY item4: legacy campaigns render BYTE-IDENTICAL to baseline goldens (flag off)
- [ ] S10 VERIFY item5: set VENDOR_SCRIPT_INJECT=1 INBOUND worker only + re-verify dry-run uses script
- [ ] S11 EARNER GATE after: md5/PID/health/5xx
- [ ] S12 FORTRESS panel deploy (recipe §6)
- [ ] S13 update ledgers + founder recipe

## PROGRESS LOG
- S0 PASS — box reachable; agent.py 9150fabe UNCHANGED, famit-agent PID 1477083, 3 svc active, box prompt de2fd2a7
- S1 PASS — all 3 py_compile OK locally; clean in git
- S2 PASS — golden oracle on box vs CURRENT prompt.py = 5/5 byte-identical (oracle valid box-truth)
- safety: my new caller.py is a clean SUPERSET of box-live caller.py (only 7 box-only lines = the OLD code my W1 edit intentionally changed; PERF UNIT-1 pagination preserved 13/13)
- S3 PASS — backup *.W1DEPLOYbak.20260614-045719; atomic swap all 3; box md5==local; py_compile OK on box; agent.py/PID unchanged
- S4 PASS (EARNER GATE prompt.py) — golden oracle vs NEW v2 prompt.py = 5/5 byte-identical (flag OFF); v2==v1 for 5/5 legacy
- S5 PASS — restarted famit-caller + aim-voice-agent ONLY; famit-agent PID 1477083 unchanged; /health 200
- S6 PASS (item1) — 9866-char vendor script byte-equal http==disk (sha 97839b63); both REAL read paths
- S7 PASS (item2) — dry-run adopts vendor greeting (Anjali/Skyline/Lakeview); English line -> English persona reply
- S8 PASS (item3) — </vendor_script> defanged to fullwidth; canary stored as DATA, NOT echoed/obeyed in reply; legit fence count=1
- S9 PASS (item4) — legacy campaigns render byte-identical to baseline goldens (proven at S4)
- S10 PASS (item5) — VENDOR_SCRIPT_INJECT=1 via systemd drop-in for aim-voice-agent ONLY; inbound env has it, EARNER env ABSENT; env flag drives v2 splice; golden 5/5 still identical under flag ON
- S11 PASS (FINAL EARNER GATE) — agent.py 9150fabe unchanged, PID 1477083 never restarted, /health 200, 0 real 5xx, 0 Traceback, NO ring
- cleanup — test campaign c444b5185a deleted; box temp artifacts removed
- S12 PASS — FORTRESS panel deployed (BUILD_ID Ykm_1fVt267VDkPib8uVg); 200 loopback + panel.famit.in edge; famit-panel restarted only; backups *.W1bak.20260614-051000
- S13 PASS — ledgers updated (ORCHESTRATOR/NEXT-BIG-BUILDS/VOICE-BRAIN-MASTER-PLAN+STATE/AGENT_LEARNINGS); founder recipe FOUNDER-SCRIPT-STUDIO.md; commit 1ffe7cd

## ✅ WAVE COMPLETE 2026-06-14
All 5 verify items PASS + FULL EARNER GATE PASS + panel LIVE. Final snapshot:
agent.py 9150fabe unchanged · famit-agent PID 1477083 · 3 svc active · /health 200 · inbound flag ON (earner clean) · panel BUILD_ID Ykm_1fVt267VDkPib8uVg.
RESIDUAL: only a real inbound DID call proves the live mic/voice adoption; outbound earner stays flag-OFF pending founder sign-off + ring.
