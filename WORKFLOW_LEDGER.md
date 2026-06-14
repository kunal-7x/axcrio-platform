# 🧾 WORKFLOW LEDGER — durable record of every ultracode workflow + its OUTPUT

> **Why:** workflows run in the main context; when compaction hits, the next session loses what each
> workflow produced. This file (+ `memory/wave_runs/<wave>.md` for full output) makes every run's result
> PERMANENT. **After any compaction, read this FIRST** to know every wave's outcome, then drill into the
> per-wave file for detail. Costs ~1 append per phase — the work is unchanged.

## 📏 THE CONVENTION (every workflow I author bakes this in)
- Each workflow defines a log file `memory/wave_runs/<wave-name>.md`.
- **Every phase agent APPENDS its tight conclusion there** under `## <phase> — <label>` as it finishes
  (crash-safe: a wave that dies mid-run still leaves its completed phases' outputs on disk).
- The **final phase appends ONE line to THIS ledger** (newest on top): `<date> · <wave> · [runId] · STATUS · <one-line outcome> · → <detail file>`.
- This is in addition to (not instead of) the build_log / *-STATE.md / master-plan a wave already writes.

## 📇 INDEX (newest on top)
- 2026-06-14 · rag-w1-retrieval-harden · [W1-build] · ✅ DONE (build+offline-verify) · core.py retrieve() gains `dense=False`(reply-path default→ZERO embed/network; C-3) + `include_global=True`; `_global` UNION via explicit `OR tenant_id='_global'` bound selftid under is_admin=False (no `%`, no admin); kb_chunks/sources/documents RLS USING read-shares `_global` / WITH CHECK write-locks it; NEW kb_query_log FORCE-RLS (strict per-tenant) + log_query/purge_query_log TTL(90d). 3 grounding sites funnel one `_kb_retrieve` chokepoint → passes dense=False explicitly (FTS-only forever). Offline 5/5 PASS; DDL rollback-validated on live box DB RC=0; py_compile OK; gitleaks 0. Commit 266f2c1 on fe/unify-run-wavec. Box NOT mutated (DDL deploys next aim-voice-agent restart via ensure_schema). FLAG TRUTH: CTX_CACHE + INBOUND_PROV_LOCK both DORMANT (absent from .env, code-default off) — NOT flipped. Earner UNTOUCHED (9150fabe/PID1477083/caller-200/0-5xx/NO ring). → memory/wave_runs/rag-w1-retrieval-harden.md
- 2026-06-14 · rag-w0-retrogate · [W0-build] · ✅ DONE (build+verify) · Built RAG_INJECT_ENABLED kill-switch (default 1) + wrapped all 3 live grounding sites (lookup/pick_campaign/connect-prefetch) + the _kb_retrieve chokepoint → flag-OFF does NO kb retrieval & passes grounding="" → byte-identical no-RAG inbound render. Golden 5/5; flag CI exit 0 (flag-off==no-RAG render, 18938 chars; non-empty block appends exactly). prompt.py untouched. Commit 8bc8780 on fe/unify-run-wavec, gitleaks 0. Earner UNTOUCHED (9150fabe/PID1477083/caller-200/0-5xx/NO ring). NOT yet deployed to box (still 018c20a7) — box deploy + .env RAG_INJECT_ENABLED=1 = next box-mutating step. → memory/wave_runs/rag-w0-retrogate.md
- 2026-06-14 · repo-recovery-audit (P3 final) · [wf_2b177b10] · ✅ DONE · RECOVERY-STATE.md written (authoritative source map + live flags + 4 follow-ups); PLAYBOOK rules 16+17 banked; AGENT_LEARNINGS + ORCHESTRATOR updated. Local↔box CONSISTENT. Open: W0 RAG kill-switch; CTX_CACHE/INBOUND_PROV_LOCK .env verify; branch merge. Earner UNTOUCHED (9150fabe/PID1477083/health200/0-5xx). → memory/wave_runs/repo-recovery-audit.md + design/RECOVERY-STATE.md
- 2026-06-14 · repo-recovery-audit (P2 reconcile) · [wf_2b177b10] · ✅ DONE · Local mirrors RECONCILED to live box truth (SCP-pull, no box write): aim_voice_agent a9eefa8c→018c20a7, prompt ec5fa971→fb87ea56, both .LIVEBOX goldens refreshed, agent.py on-disk→9150fabe (gitignored), _inbound_ref DEPLOYED ref 3152539f→018c20a7 + README.CANONICAL.md canonical map. kb/ already matched. Commit 70969dd, gitleaks 0. Earner UNTOUCHED (9150fabe/PID1477083/health200/0-5xx). NO safe gap deployed; RAG_INJECT_ENABLED W0 retro-gate = separate box-mutating wave (noted). → memory/wave_runs/repo-recovery-audit.md
- 2026-06-14 · repo-recovery-audit (P1 drift-map) · [wf_2b177b10] · ✅ DONE · Full drift map: earner HEALTHY; 3 critical stale local files; RAG LIVE+UNGATED (W0 must build RAG_INJECT_ENABLED); missing .env flags (CTX_CACHE, INBOUND_PROV_LOCK); 7-branch sprawl mapped. → memory/wave_runs/repo-recovery-audit.md
- 2026-06-14 · panel-unify-redeploy · [wf_0eff1d2b] · ✅ DONE · Run-page regression FIXED — all UI unified (4-step + Wave C cost-meter/provider-lock/exclude-toggle + W4 CRM + AIM + #8). Branch fe/unify-run-wavec, BUILD_ID TU16Mn1DcJVmxnxr2GVyL live.
- 2026-06-14 · three-products-megaplan · [wf_666fe925] · ✅ DONE · 3 master plans (RAG/Video/Vault). 🚨 KEY: RAG grounding LIVE+UNGATED on box (3 sites, 63 chunks) + box↔local earner-file drift → RAG W0 = retro-gate first. → design/{RAG,VIDEO-STUDIO,VAULT}-MASTER-PLAN.md
- 2026-06-14 · workflow-funnel-execution (#8) · [wf_6dfd8def] · ✅ DONE · funnel/workflow now RUNS (empty run_token was the bug → 401 at dialer); human labels + Run button; verified queued-only, NO ring. → droplet_work/funnels/RUN_EXEC_STATE.md
- 2026-06-14 · aim-access-and-pin (#6) · [wf_e7cb7c7d] · ✅ DONE · PIN change (old→new + lockout) + numbers CRUD; firewall byte-identical. BUILD_ID sTCWP4Jj.
- 2026-06-14 · voice-w4-memory-read · [wf_f70d5945] · ✅ DONE · memory read side LIVE (retrieval into inbound + CRM Memory tab + API); LEAD_MEMORY_PG=1; 10/10 verify. → design/W4-MEMORY-READ-STATE.md
- 2026-06-14 · voice-w3-multichannel-memory · [wf_45ee5836] · ✅ DONE · lead_memory/episodes RLS tables + durable PG-outbox extraction (survive-restart); flag-gated. → design/W3b-EXTRACTION-STATE.md
- 2026-06-14 · run-wave-c-ui-costmeter · [wf_88dc2a51] · ✅ DONE (then reverted by branch-sprawl → being re-fixed) · real cost meter + provider-lock banner + exclude-toggle. On branch fe/wave-c-run-cost-meter.
- 2026-06-14 · run-wave-a-billing-providerlock · [wf_59b68b62] · ✅ DONE · resolve_providers leaf (golden 5/5) + USD_INR 95.2 (Groq 95× fix) + funnels secure. → RUN-PLATFORM-MASTER-PLAN.md
- 2026-06-14 · run-wave-b-preview-fix · [wf_7a9bfd23] · ✅ DONE · preview silent cause = text/plain; backend full-buffer + force audio/mpeg. Live: 200 audio/mpeg ID3.
- 2026-06-14 · voice-w2-context-cache · [wf_b26d1b52] · ✅ DONE · full-context cache (warm 0.16ms) + version-stamp invalidation; flag CTX_CACHE=1 inbound. → design/W2-DEPLOY-STATE.md
- 2026-06-14 · voice-p0-leak · [wf_ed3b9042] · ✅ DONE · cross-tenant memory leak CLOSED (inbound+WA, tenant-checked fallback); no earner restart. → design/P0-LEAK-STATE.md
- 2026-06-14 · voice-w1-script-fullcontext · [wf_17dcce28] · ✅ DONE · dynamic vendor-script→persona + lossless raw_script store + Script Studio; golden 5/5. → design/W1-DEPLOY-STATE.md
- 2026-06-14 · master-dna-plan · [wf_4f117706] · ✅ DONE · the full-DNA brain. → MASTER_DNA_PLAN.md
- 2026-06-14 · run-platform-megaplan · [wf_eefea3fb] · ✅ DONE · real pricing + preview cause + provider-lock + feature table. → design/RUN-PLATFORM-MASTER-PLAN.md
- 2026-06-14 · voice-brain-megaplan · [wf_8988e0cb] · ✅ DONE · the adaptive-voice-brain architecture (45 agents). → design/VOICE-BRAIN-MASTER-PLAN.md

## ⏭️ QUEUED (launch when a wave slot frees — avoid rate-limiting the urgent fix + priority research)
- **repo-recovery-audit** — diagnose + recover ALL latent mistakes like the branch-sprawl (other deployed-then-reverted UI, un-deployed committed work, local↔box drift, half-merged branches, dormant flags). Launch after panel-unify-redeploy lands.
- **RAG (heart) → Video Studio → Vault** — build each (BE Opus / FE Sonnet+frontend-design) once three-products-megaplan lands its master plans.
- Then the gold-mine backlog (NEXT-BIG-BUILDS items).
- 2026-06-14 RAG W0 DEPLOY ✅ — `RAG_INJECT_ENABLED` kill-switch deployed to box (`8335d4ba`); flag=1 (grounding ON); golden 5/5 PASS; flag-gate A/B/C PASS; earner UNTOUCHED. Kill: set `RAG_INJECT_ENABLED=0` + restart aim-voice-agent.
- 2026-06-14 RAG W1 DEPLOY ✅ — retrieval hardening live: dense=False default (zero embed on reply path), _global UNION predicate (RLS USING + explicit SQL, no %wildcard), kb_query_log FORCE-RLS + TTL. Box: kb/core.py(7010a77e) + schema.sql(42c14591) + __init__.py(aa2b7c13) + aim_voice_agent.py(5c3936fa). DDL applied (all 4 kb_ tables FORCE-RLS=t live; kb_query_log NEW). aim-voice-agent restarted PID 2669239. 8/8 offline probes PASS. Earner UNTOUCHED (agent.py 9150fabe, famit-agent PID 1477083, /health 200). CTX_CACHE+INBOUND_PROV_LOCK = DORMANT (absent from .env, not flipped). NEXT: W2 seed _global corpus.
