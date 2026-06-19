# W18 — Blind-spot & Grand Red-Team (wave run log)

Wave G cross-cutting "99% hunt". DOC-ONLY (no code, no box, agent.py untouched).
Deliverable: `design/W18-BLINDSPOT-AND-REDTEAM.md`.
Inputs: security/isolation gaps note + architecture red-team + rollout/earner-safety red-team + external web verification (LiveKit fleet scaling, TRAI/DPDP India 2026).

## Phase: SYNTHESIS (done 2026-06-18)
- Read the 18-wave plan, founder requests (request1/2), RECOVERY-STATE + VOICE_BRAIN_FIX_STATE for ground truth.
- Confirmed the rollout red-team's central B1: earner live md5 disagreement — `98655dbf` (VOICE_BRAIN_FIX_STATE:36) vs `9150fabe` (RECOVERY-STATE:15 + plan L58). Verified, CRITICAL (C5).
- Web-verified two NET-NEW whole dimensions the security/architecture passes could not see:
  - M1/C1 concurrency: single LiveKit 4c/8GB worker = 10-25 concurrent jobs; box is single-worker; "replace 500 telecallers" is an un-modeled concurrency claim.
  - M4/C7 India 2026 law: mandatory AI-disclosure-at-call-start + synthetic-voice consent + DLT + DND-scrub; ₹10 lakh + 15-day telecom suspension; COLLIDES with W2 "never say I am an AI".
- Produced: 4 meta-blind-spots, ranked master gap list (7 CRITICAL / 13 HIGH / 8 MEDIUM / 3 LOW), top-10 production-killers, grand red-team required plan changes (A-E, 18 items), net-new waves W19-W26.

## Phase: TICKETS (residual findings → owning waves, fed back per the plan's W18 mandate)

Each ticket = {ID, owning wave, severity, one-line action}. Building waves pick these up from `design/W18-BLINDSPOT-AND-REDTEAM.md`.

### CRITICAL — block deploy gate / block owning-wave "done"
- T-C1 → NEW-W24 (+W1/W12/W17): build per-call admission control + 50/100/200-concurrent load harness as a HARD deploy gate. The 500-team claim is unprovable without it.
- T-C2 → W1: `tenant_id`+`call_id` mandatory SIGNED `KernelSession` fields, stamped server-side, required ctor arg on every service, fail-closed.
- T-C3 → W1+W3+W4+W7: ONE trust boundary — typed fences for brief/RAG/PDF/memory/summary/mic; safety-above-by-prompt-POSITION.
- T-C4 → W1+W3: `_load_campaign` tenant-scoped; assert `campaign.tenant_id == dispatch.tenant_id`.
- T-C5 → W0+W17+deploy-gate: **DO FIRST** — pull live agent.py md5 off box, reconcile `98655dbf` vs `9150fabe`, re-anchor earner-gate invariant. The current gate protects a ghost hash.
- T-C6 → NEW-W25: second LiveKit worker + graceful DRAIN (not systemctl restart) + atomic swap + flock + drift check.
- T-C7 → NEW-W26 (W2/W9/W7/W14): DLT + DND-scrub + AI-disclosure + synthetic-voice consent + recording consent + retention/erasure/at-rest-encryption. Resolve W2 "never say I am an AI" vs legal disclosure as one compliant human-sounding open. ₹10 lakh + telecom-suspension exposure.

### HIGH
- T-H1 → W1+W6: soft any-stage policy (constraint vs drive decoupled), re-derive stage from transcript.
- T-H2 → W1+W4: contract-level warm-path sync; hot path never blocks on network RAG/embed; not-ready ≠ empty.
- T-H3 → W7+W9+W14: COLD writes untrusted-until-validated; not "always async" for next-call-gating writes.
- T-H4 → W9+W4+W8+W14: drop is_admin=True on content workers; tenant-scoped + RLS.
- T-H5 → NEW-W19 (W8/W13): wire validate_outbound_url() at registration AND fetch; pin DO egress.
- T-H6 → W11+W10+W16: tool wrappers enforce entitlement+budget+rate-limit; caller can't dictate destination.
- T-H7 → NEW-W22 (W17): per-route resolve_tenant+RLS+forge-tenant-B+BOLA+OAuth-state CI gate.
- T-H8 → NEW-W21 (W14): firewall-as-control-flow; HARD-REFUSE without F3 step-up; PIN lockout.
- T-H9 → W4+W17: per-tenant vector namespace + RLS + dense-embed gate; poisoning eval. Watch KERNEL_OUTBOUND + stale RAG_INJECT_ENABLED=1 on _global = earner cross-tenant leak.
- T-H10 → W7+W9+W14: no key/internal-URL spoken; summary can't manufacture facts.
- T-H11 → W2: per-vertical leakage eval gates W2 "done"; add use_case to ProviderRouter key NOW.
- T-H12 → W1+W6: structural safety + phonetic/STT-mangled injection set.
- T-H13 → W1+W3: fix stale premises — Groq cache DOES support llama-4-scout (quota-headroom lever); campaign-stable prefix; retrieval-over-truncation (kill 600c/usps≤5 clamp).

### MEDIUM
- T-MD1 → NEW-W20 (GATES W8-W16): retire legacy FamitCall2026.
- T-MD2 → W10+W12+W16+W4: per-tenant spend-budget/rate-limit (subsumed by W24).
- T-MD3 → NEW-W23 (W8/W13/W5): split signing keys; short-lived inter-service tokens; vault OAuth/WABA.
- T-MD4 → W9+W12+W7/W14: retention TTL + cascading erasure + at-rest encryption.
- T-MD5 → W0+W1: lazy in-call import + test_off_does_not_import + dark-import box-canary (separate box-change from flag enable).
- T-MD6 → W0: live FLAG_MANIFEST.md reconciled from box .env, unsafe-combos listed.
- T-MD7 → deploy-gate+W14+W17: inbound green ≠ outbound proven; keep outbound gate at full rigor.
- T-MD8 → W0+deploy-gate+W1: prompt.py deploy = dual earner (inbound+outbound) change, both gated.

### LOW
- T-L1 → deploy-gate+W17: post-deploy auto-rollback signal (rollout B8 truncated in input — complete it).
- T-L2 → follow-up isolation survey: cross-tenant Redis-packet bleed, per-store vector namespace, RLS per new table.
- T-L3 → W9+W17: LiveKit Cloud obs US-stored/30d-deleted — keep own archive (DPDP residency).

### NET-NEW WAVES TO ADD TO THE FLEET
W19 egress-guard · W20 legacy-token retirement (gates W8-16) · W21 firewall-as-control-flow · W22 per-route CI gate · W23 key-mgmt · **W24 concurrency/capacity/admission (the #1 missing wave)** · **W25 deploy-safety/earner-cutover engine** · **W26 India regulatory & consent engine**.

_Last updated 2026-06-18 — W18 doc-only synthesis complete._
