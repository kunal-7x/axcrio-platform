# W12 — Telephony Sales-OS + India Compliance Engine — wave run log

Spec: `design/W12-TELEPHONY-COMPLIANCE-SEAM.md` (the caller.py patch DOC) +
`design/W26-COMPLIANCE-CONSENT-ENGINE.md` (the legal spine). Branch
`fix/realtime-voice-kernel-v2`. Earner-safe: agent.py md5 `98655dbf` NEVER imported/edited;
caller.py NEVER edited live (patch DOC only). All new code DISJOINT + tracked under
`voice_ops/telephony/` + `voice_ops/compliance/`. Flags `TELEPHONY_OPS_ENABLED` +
`COMPLIANCE_ENABLED` both default OFF (resting build byte-identical).

---

## W12 — self-managing outbound Sales-OS + compliance gate — DONE (build/test green, NOT deployed) 2026-06-18

### What shipped (tracked, droplet-free, lazy imports, 0 droplet/agent imports verified)

**voice_ops/telephony/** (the Sales-OS layer — fail-OPEN on internal error, the call still goes):
- `config.py` — `TelephonyOpsConfig` (master `TELEPHONY_OPS_ENABLED` OFF; per-number cap/concurrency/cooldown, answer-rate/avg-call planning knobs, health thresholds, lead-lock TTL).
- `capacity_planner.py` — `CapacityPlanner.plan(leads,numbers,window,conc) -> CapacityPlan`: per-number throughput (answer-weighted talk + overhead / concurrency, capped by daily cap), fleet capacity, `safe_daily_target=min(leads,fleet)`, **warn-if-insufficient** + suggested_numbers + days_to_clear. Advisory; never blocks.
- `number_pool.py` — `NumberPool` + `NumberPoolStore` Protocol + `InMemoryNumberPoolStore`: add/remove/pause/resume numbers from UI, atomic `lease()` (cap+concurrency under one lock = no-overload fence), cooldown gate, day-roll reset, `available_numbers(avoid=[])` least-loaded-first. FORCE-RLS `phone_number_pool` table is the later Pg swap.
- `health.py` — `SpamReputation`: per-DID rolling-window score (answered=+1, no_answer=+0.25, rejected=-0.6, blocked/spam_flag=-1; neutral 0.5 prior) -> HEALTHY/DEGRADED/QUARANTINED with hysteresis (recover bar > degrade bar, quarantine needs >= min_samples). Auto-reduce (`traffic_factor`) + auto-recover; `unhealthy_numbers([...])` = the `avoid=` list feeding the existing `trunk_registry.rotation.pick_did(avoid=...)`.
- `router.py` — `AdaptiveRouter.pick_next(tenant) -> RouteChoice|None`: capacity (pool) + health (exclude QUARANTINED, HEALTHY-before-DEGRADED) + **atomic lease before return** (no two routes pick the same number past concurrency). `record_outcome` releases the lease + feeds health. None -> queue the lead (never force a dial).
- `lead_lock.py` — `LeadLock` per-(tenant,phone) TTL mutex: a lead is NEVER double-dialed / dialed by 2 numbers; lease self-heals after TTL (crashed worker). Same proven semantics as `callback.store.try_lock`, extracted standalone.
- `window.py` — `CallingWindowScheduler.decide(...) -> WindowDecision`: recipient-tz window open/closed + next_open; `apply_legal_floor=True` lazily clamps to the compliance legal floor (a tenant CANNOT widen).

**voice_ops/compliance/** (the W26 dial-time GATE — fail-CLOSED on Tier A):
- `config.py` — `ComplianceConfig` (master `COMPLIANCE_ENABLED` OFF; legal window 10:00-19:00 / BFSI 08:00, disclosure tier, explicit-consent 7d, DND refresh 30d, retention TTLs, number-hash salt).
- `window_floor.py` — `clamp_to_legal_floor(tenant_win) = INTERSECT(tenant, legal_floor[vertical])`; max/min math makes WIDENING structurally impossible (the live ILLEGAL 09:00-21:00 default is clamped to 10:00-19:00). `legal_floor("bfsi")` opens 08:00. `widens_floor()` = always False (auditable assertion).
- `cli_series.py` — `check(number, purpose) -> SeriesVerdict`: 140=promotional(campaign), 160/1600/1601=transactional, **10-digit mobile = ineligible (the violation)**, unknown=fail-closed; TEST/MANUAL single rings ungated (mirrors trunk_registry Purpose).
- `dnd.py` — `DndScrubber.scrub(tenant,number)`: layer-1 NCPR cache (<=30d fresh; **cache-miss = fail-closed block + needs_rescrub**) + layer-2 local per-tenant suppression. PII-min: salted SHA-256 hash only. `record_optout` / `cache_ncpr`.
- `consent.py` — `ConsentLedger`: append-only `consent_ledger`; freshness AT DIAL TIME (explicit auto-expires +7d; inferred-without-contract-expiry = weak; revocation = newest row wins); `expired_principal_refs(ttl)` = retention-TTL purge input.
- `disclosure.py` — `build_disclosure_ctx(brand,product,tier,record_cue) -> DisclosureCtx`: warm Tier-0/1/2 openers in EN+Hinglish+Hindi (brand+purpose+record cue), **NEVER the banned "AI assistant"** (BANNED_PHRASES + `assert_no_banned_phrase` = the W2 generation-filter source-of-truth; smuggled banned brand is scrubbed).
- `engine.py` — `ComplianceEngine.preflight(tenant,lead,campaign) -> Decision{allow|block|soft, reasons, gate, disclosure_ctx, needs_rescrub}`. Order A1 registration -> A2 number-series -> A4 window-floor (recipient-local) -> A5 consent -> A3 DND -> B disclosure. Fail-closed Tier A; flag-OFF -> allow + `compliance_unenforced` (disclosure still built). `RegistrationStore` Protocol + InMemory (Pg over `dlt_registry`). Emits W8 events fire-and-forget (emit never affects a decision). Module-level `preflight()` + singleton.

**voice_ops/db/ddl_telephony_compliance.sql** — FORCE-RLS DDL (P1 admin-GUC policy verbatim): `phone_number_pool`, `consent_ledger` (append-only), `dlt_registry`, `dnd_cache` (national, no tenant_id -> no RLS), `dnd_suppression` (tenant-scoped), `compliance_audit` (append-only, >=6mo). No raw PII (salted hashes). famit_app NOSUPERUSER/NOBYPASSRLS.

### EARNER GATE
| Check | Value |
|---|---|
| agent.py imported/edited | NO — zero imports of agent/droplet_work/livekit/redis/psycopg2 at module load (verified by import probe) |
| caller.py edited on box | NO — patch DOC only (`design/W12-TELEPHONY-COMPLIANCE-SEAM.md`) |
| Flags default | `TELEPHONY_OPS_ENABLED=0`, `COMPLIANCE_ENABLED=0` (resting byte-identical) |

### TESTS — `python -m pytest voice_ops/ voice_kernel/` => **471 passed** (35 new)
New: `voice_ops/tests/test_telephony_sales_os.py` (16) + `voice_ops/tests/test_compliance_engine.py` (19).
Proven: capacity warns when insufficient + never targets > leads; router never exceeds concurrency,
respects cooldown, distributes least-loaded-first; lead never double-dialed + self-heals + tenant-isolated;
unhealthy number quarantined + router skips it + recovers; window opens/closes + **legal floor cannot be
widened** (property over 6 tenant windows incl. the illegal 09-21 default); preflight blocks DND-listed +
DND cache-miss(fail-closed) + out-of-window + unregistered-tenant + mobile-CLI + no/expired/revoked/weak-
inferred consent; disclosure warm + **never banned across all 3 tiers + 3 langs** + scrubs smuggled brand;
flag-off allows + unenforced marker + still builds disclosure; blank tenant fails closed.

### NEXT (seam wave — founder-signed, one box mutation at a time)
1. Apply `ddl_telephony_compliance.sql` (additive, no live-path change on its own).
2. Build the Pg*Store swaps (NumberPool/Consent/Dnd/Registration) over the FORCE-RLS tables.
3. Apply the caller.py patch (§1-§7 of the seam doc) behind the flags; flip `TELEPHONY_OPS_ENABLED=1`
   ALONE first (real call rings, pool distributes, lock holds); only after DLT+140-series registered
   flip `COMPLIANCE_ENABLED=1`. Integrated real outbound-call smoke before+after each; revert = flag to 0.
4. W2 brain: emit `disclosure_ctx` FIRST as control-flow + the BANNED_PHRASES generation filter.
5. Frontend (founder rule): number-pool CRUD + capacity-plan banner + compliance dashboard
   (blocked-dials, consent coverage, DND freshness, health gauges, DLT-registry CRUD screen).

### FOUNDER / COUNSEL ACTIONS (gate high-volume — keep COMPLIANCE_ENABLED=0 until done)
- DLT **Principal-Entity registration** (per-tenant PE recommended; Famit = RTM/aggregator) — PAN/GST/
  incorporation + biometric (mandatory since Feb-2025), 3-7 business days.
- Registered **header** + >=1 approved **content template** (variable-slot envelope so the adaptive brain
  stays inside a registered structure — not a content-template violation).
- **140-series CLI** (promotional) / 1600 (transactional) provisioning — NOT a 10-digit mobile (the live
  trunk identity is a known audit item, W26 §8).
- **Auto-dialer pre-notification** to the originating access provider.
- **Counsel sign-off** on the suspension/disconnection clause + abandoned-call cap; default disclosure
  Tier 0 (Tier 1 for BFSI/insurance).

## Phase: VERIFY + RED-TEAM FOLD (2026-06-18)
RED-TEAM verdict = **SHIP with 2 fixes** (no hard blockers). Both folded BEFORE commit;
neither lets an illegal call through on the default path, neither can block the live
(flag-OFF) earner.

**FINDING 1 (MEDIUM) — legal floor was env-overridable with no absolute cap.**
`window_floor.legal_floor()` read `COMPLIANCE_WINDOW_START/END` verbatim when a cfg was
supplied; `COMPLIANCE_WINDOW_END=23:30` made the engine authorize dialing to 23:30 (a
TCCCPR/TRAI violation). FIX (`voice_ops/compliance/window_floor.py`): added ABSOLUTE
statutory ceilings `ABS_COMMERCIAL=((10,0),(19,0))` / `ABS_BFSI=((8,0),(19,0))` and
clamped the env floor INTO them — `eff_open=max(env_open,abs_open)`,
`eff_close=min(env_close,abs_close)`, degenerate→absolute ceiling. The env knob can now
only ever NARROW; a misconfigured/hostile env can never authorize a dial outside
10:00–19:00 (08:00–19:00 BFSI). Tests: `test_env_floor_cannot_widen_past_absolute_ceiling`,
`test_env_floor_can_still_narrow`, `test_engine_blocks_dial_when_env_tries_to_widen_window`
(end-to-end: now=20:00 IST + env claims 23:30 → BLOCK at window gate).

**FINDING 2 (MEDIUM) — consent scope-collapse on empty campaign id.**
`InMemoryConsentStore.rows_for` matched `scope == "" or r.scope == scope or r.scope == ""`;
a campaign with no id passes `scope=""` (engine.py:183) which then matched a consent
granted only for a *different specific* campaign → a lead who consented to campaign A
could be dialed by a no-id campaign on A's consent. FIX (`voice_ops/compliance/consent.py`):
replaced the inline predicate with `_scope_matches(query_scope, row_scope)` — a GLOBAL
grant (`row_scope==""`) satisfies any query (true blanket consent); a SPECIFIC grant is
satisfied ONLY by an exact-scope query; an EMPTY query rides ONLY a global grant, never
collapses onto another campaign's specific consent. Tests:
`test_consent_scope_does_not_collapse_to_other_campaign`,
`test_consent_global_grant_satisfies_any_scope`,
`test_engine_blocks_when_consent_only_for_other_campaign` (end-to-end: consent for campA +
no-id campaign → BLOCK at consent gate).

**Red-team safety invariants confirmed (no change needed):** DND stale-clear→blocked+
rescrub (fail-closed); opt-out = absolute block; local suppression tenant-isolated (t2
does not inherit t1's opt-out, independently fail-closes on its own cache miss); NCPR
cache intentionally shared across tenants (national register — correct); `needs_rescrub`
requeue is the seam's bound (scrub-refresh job populates the cache), not a code defect.
No double-dial / two-number-dial (`LeadLock` (tenant,phone) TTL mutex, tenant-isolated,
blank-tenant fail-closed, guards both campaign loop §3b and retry §5); no number-burn
(`number_pool.lease` atomic per-number daily-cap+concurrency under one lock; `_cooldown_ok`
min-gap; `health.SpamReputation` quarantine + router exclusion).

**VERIFICATION:** `pytest voice_ops/tests/test_telephony_sales_os.py
voice_ops/tests/test_compliance_engine.py` = **41 passed** (35 original + 6 new
regression). Full `pytest voice_ops/ voice_kernel/` = **476 passed / 2 failed** — the 2
failures are `voice_kernel/integrations/tests/test_inbound_integration.py` and are caused
by UNCOMMITTED in-flight edits to `voice_kernel/integrations/inbound.py`/`outbound.py`
from ANOTHER wave (confirmed: `git stash` → those 28 inbound tests pass; my W12 changes
touch only `voice_ops/compliance/` + `voice_ops/tests/`). Not staged, not my scope.

**EARNER LAW HELD, ZERO DRIFT:** live OUTBOUND `droplet_work/agent.py` md5
`98655dbfc71d5c3da36bcfe3f848082c` UNCHANGED (recomputed exact match); NOT edited/
imported/restarted; `caller.py` NOT edited (seam stays patch-DOC only in
`design/W12-TELEPHONY-COMPLIANCE-SEAM.md`). Resting build flag-OFF byte-identical
(`COMPLIANCE_ENABLED`/`TELEPHONY_OPS_ENABLED` default OFF → preflight ALLOW +
`compliance_unenforced`). gitleaks `protect --staged` = **0** (~181 KB, no leaks).
Staged ONLY `voice_ops/telephony/` + `voice_ops/compliance/` +
`voice_ops/db/ddl_telephony_compliance.sql` + the 2 W12 test files +
`design/W12-TELEPHONY-COMPLIANCE-SEAM.md` + this wave-log (never `git add -A`; left the
dirty inbound/outbound + every other untracked file for their own waves).
NO box deploy — wiring is the LATER founder-gated seam.

**FOUNDER ACTIONS (DLT / TRAI — required BEFORE `COMPLIANCE_ENABLED=1`, else 100% of dials
block):** (1) register the Principal Entity (PE) on a DLT platform (Jio/Airtel/Vi/BSNL/
Tanla/Karix) and get PE status ACTIVE; (2) register at least one Header/Sender-ID +
≥1 content TEMPLATE and get it APPROVED; (3) provision a 140-series (promotional) / 1600
(transactional) CLI number — NOT a 10-digit mobile; (4) send the auto-dialer
pre-notification to the originating access provider; (5) counsel sign-off on the
suspension/disconnection + abandoned-call-cap clauses and the default disclosure tier
(Tier 0 commercial, Tier 1 BFSI/insurance). Until these land, keep `COMPLIANCE_ENABLED=0`.
