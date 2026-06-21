# W12 — Telephony Sales-OS + India Compliance Engine (BUILD STATE)

Branch: fix/realtime-voice-kernel-v2. EARNER LAW: agent.py md5=98655dbf NEVER touched;
caller.py NEVER edited live (patch DOC only). All new code DISJOINT under
`voice_ops/telephony/` + `voice_ops/compliance/`. 0 droplet/agent imports (lazy).
Flags default OFF (COMPLIANCE_ENABLED, TELEPHONY_OPS_ENABLED).

## Plan / units (flip to DONE as each verifies)
- [DONE] explore: seam map (caller.py given), EventBus (voice_kernel/events/bus.py),
  trunk_registry (droplet_work, gitignored), callback store lead-lock pattern,
  W26 compliance design. Patterns: lazy importlib engine load, FORCE-RLS DDL,
  flag _flag(), InMemory store + Protocol, EventBus fire-and-forget emit.
- [DONE] voice_ops/telephony/__init__.py + config.py (TelephonyOpsConfig flags)
- [DONE] telephony/capacity_planner.py — CapacityPlanner.plan() warn-if-insufficient
- [DONE] telephony/number_pool.py — NumberPool + InMemory store + Protocol + PG DDL doc; FORCE-RLS table
- [DONE] telephony/health.py — SpamReputation scorer (rolling answer/reject/block -> score, auto-reduce/recover)
- [DONE] telephony/router.py — AdaptiveRouter.pick_next (capacity+cooldown+health, never overload)
- [DONE] telephony/lead_lock.py — LeadLock TTL mutex (no double-dial / two-number)
- [DONE] telephony/window.py — CallingWindowScheduler + legal hard floor (cannot widen)
- [DONE] compliance/__init__.py + config.py (ComplianceConfig: COMPLIANCE_ENABLED, floor, tiers)
- [DONE] compliance/dnd.py — DND/NCPR scrub-before-dial (cache + local suppression)
- [DONE] compliance/consent.py — consent ledger (FORCE-RLS) + retention TTL + freshness
- [DONE] compliance/cli_series.py — 140/1600 number-series check
- [DONE] compliance/disclosure.py — warm Tier-0 disclosure_ctx (purpose+recording, NOT 'AI assistant')
- [DONE] compliance/window_floor.py — legal window hard floor (intersect, cannot widen)
- [DONE] compliance/engine.py — compliance.preflight(tenant,lead,campaign)->Decision
- [DONE] db DDL doc: number_pool, consent_ledger, dlt_registry, dnd_cache, compliance_audit (FORCE-RLS)
- [DONE] tests under voice_ops/telephony/tests + voice_ops/compliance/tests
- [DONE] design/W12-TELEPHONY-COMPLIANCE-SEAM.md (caller.py patch DOCs, file:line, flags)
- [DONE] memory/wave_runs/W12-telephony-compliance.md append
- [DONE] pytest voice_ops/ + voice_kernel/ green

## Verification
pytest voice_ops/telephony voice_ops/compliance -> ALL PASS (see final report).
Full suite voice_ops/ + voice_kernel/ green (pre-existing unrelated collect noted).
