# W12 — Telephony Sales-OS + Compliance Engine: caller.py SEAM (PATCH DOC)

> **Status:** DOC-ONLY patch spec. `agent.py` md5=98655dbf NEVER touched. `caller.py` is
> NEVER edited on the live box by this wave — this document is the exact, file:line patch
> a later founder-signed **seam wave** applies, ONE box-mutating change at a time, with an
> integrated real outbound-call smoke (a real number rings before AND after) + a revert path.
> All new code is DISJOINT + tracked under `voice_ops/telephony/` + `voice_ops/compliance/`
> (this repo), imports ZERO `droplet_work`/`agent.py`, and is FLAG-GATED default OFF.
> 2026-06-18.

Seam line numbers are from the EXPLORE seam map handed to this wave (caller.py on the live
box). Re-confirm each anchor with a `grep` at patch time — caller.py drifts.

---

## 0. Flags (both DEFAULT OFF — resting build byte-identical to today)

| Flag | Module | Effect when OFF (default) |
|---|---|---|
| `TELEPHONY_OPS_ENABLED` | `voice_ops.telephony.config.TelephonyOpsConfig` | the dial loop never calls the pool/router/lock/window seams; legacy single-`TRUNK` dial unchanged. |
| `COMPLIANCE_ENABLED` | `voice_ops.compliance.config.ComplianceConfig` | `preflight()` returns `allow` + `compliance_unenforced=true`; no gate, no block; disclosure_ctx still built (so W2 can test). |

Both are read once at process start (the agent.py:451 `os.getenv(...) in ("1","true",...)`
pattern). Turning `COMPLIANCE_ENABLED` ON **before** DLT + number-series registration would
block 100% of dials — keep it OFF until §9 founder actions are done.

---

## 1. One-time process wiring (top of caller.py module init, near the other singletons)

```python
# --- W12 telephony Sales-OS + compliance gate (flag-gated, default OFF) ---
_TEL_CFG = None; _NUMBER_POOL = None; _ROUTER = None; _LEAD_LOCK = None; _WINDOW = None
_COMPLIANCE = None
try:
    from voice_ops.telephony.config import TelephonyOpsConfig
    _TEL_CFG = TelephonyOpsConfig.from_env()
    if _TEL_CFG.enabled:
        from voice_ops.telephony.number_pool import NumberPool
        from voice_ops.telephony.health import SpamReputation
        from voice_ops.telephony.router import AdaptiveRouter
        from voice_ops.telephony.lead_lock import LeadLock
        from voice_ops.telephony.window import CallingWindowScheduler
        _NUMBER_POOL = NumberPool(_TEL_CFG)           # later: PgNumberPoolStore (FORCE-RLS)
        _ROUTER = AdaptiveRouter(_TEL_CFG, pool=_NUMBER_POOL, health=SpamReputation(_TEL_CFG))
        _LEAD_LOCK = LeadLock(ttl_s=_TEL_CFG.lead_lock_ttl_seconds)
        _WINDOW = CallingWindowScheduler(_TEL_CFG)
except Exception as _e:                                # never break boot on a seam import
    logging.getLogger("caller").info("telephony seam import skipped: %r", _e)
try:
    from voice_ops.compliance import ComplianceEngine, ComplianceConfig
    _CC = ComplianceConfig.from_env()
    _COMPLIANCE = ComplianceEngine(_CC, event_bus=EVENT_BUS)   # EVENT_BUS = the W8 bus or None
except Exception as _e:
    logging.getLogger("caller").info("compliance seam import skipped: %r", _e)

COMPLIANCE_ENABLED = bool(_COMPLIANCE and _COMPLIANCE.cfg.enabled)
TELEPHONY_OPS_ENABLED = bool(_TEL_CFG and _TEL_CFG.enabled)
```

`PgNumberPoolStore` / `PgConsentStore` / `PgDndStore` / `PgRegistrationStore` are the
later FORCE-RLS swaps (§ DDL doc); until they exist the InMemory stores run (single dial
worker = authoritative, same assumption `trunk_registry.rotation` already makes).

---

## 2. Capacity Planner — advisory, at `/run` (caller.py:5121)

**Anchor:** `caller.py:5121` — after `conc = max(1, min(int(concurrency), 20, int(tenant_rec.get("max_concurrency", 3))))`, before `asyncio.create_task(run_job(jid))`.

```python
if TELEPHONY_OPS_ENABLED and _TEL_CFG:
    try:
        from voice_ops.telephony.capacity_planner import CapacityPlanner
        _win_min = _window_minutes(camp_fields)   # derive from call_window_start/end
        _plan = CapacityPlanner(_TEL_CFG).plan(
            leads=len(leads), numbers=len(_NUMBER_POOL.list_numbers(tenant_id)),
            window_minutes=_win_min, per_number_concurrency=conc)
        JOBS[jid]["plan_warning"] = _plan.warning
        JOBS[jid]["safe_daily_target"] = _plan.safe_daily_target
        if _plan.insufficient:
            log.warning("CAPACITY[%s]: %s", jid, _plan.warning)
    except Exception as e:
        log.info("capacity plan skipped: %r", e)
```

Advisory ONLY — never blocks a dial. The panel reads `plan_warning` / `safe_daily_target`
from the job dict (founder-facing "you need more numbers" banner). Optionally compare
`safe_daily_target` to `daily_cap_tenant` at **caller.py:2865-2866** to cap the job size.

---

## 3. Lead-lock + Number-pool pick + Compliance preflight — inner dispatch loop

The inner `while` loop in `run_job` (**caller.py:2903-2954**) advances `idx`, picks a lead
(`num = it["num"]` at **caller.py:2909**), checks suppression (**caller.py:2911**), the
concurrency gate (**caller.py:2922**), assembles metadata (**caller.py:2931-2941**), and
dials at **caller.py:2951-2954** (`sip_trunk_id=TRUNK, sip_call_to=num, ...`).

### 3a. Window legal-floor wrap — after `_in_window` at caller.py:2889

```python
in_win, win = _in_window(camp_fields)                 # caller.py:2889 (unchanged)
if job.get("force_window"): in_win = True             # caller.py:2890 (unchanged)
elif COMPLIANCE_ENABLED and _WINDOW:                  # NEW: legal hard floor cannot widen
    _wd = _WINDOW.decide(start=camp_fields.get("call_window_start","10:00"),
                         end=camp_fields.get("call_window_end","19:00"),
                         tz_name=camp_fields.get("tz","Asia/Kolkata"),
                         vertical=camp_fields.get("vertical",""),
                         apply_legal_floor=True)
    in_win = in_win and _wd.in_window                 # tenant window AND legal floor
```

### 3b. Lead-lock guard — after `num = it["num"]` (caller.py:2909), before the concurrency check (caller.py:2922)

```python
if TELEPHONY_OPS_ENABLED and _LEAD_LOCK:
    if not _LEAD_LOCK.acquire(tenant_id, norm(num), ttl_s=_TEL_CFG.lead_lock_ttl_seconds):
        it["status"] = "skipped_locked"; idx += 1; continue   # already being dialed
```

### 3c. Compliance preflight — after suppression skip (caller.py:2911), before wallet-hold/dial

```python
if COMPLIANCE_ENABLED and _COMPLIANCE:
    _dec = await _COMPLIANCE.preflight(
        tenant_id,
        {"phone": norm(num), "lead_id": it.get("lead_id",""), "tz": camp_fields.get("tz","")},
        {"id": camp_fields.get("campaign_id",""), "vertical": camp_fields.get("vertical",""),
         "purpose": "campaign", "cli": camp_fields.get("cli",""),
         "brand": camp_fields.get("brand",""), "product": camp_fields.get("product",""),
         "window_start": camp_fields.get("call_window_start","10:00"),
         "window_end": camp_fields.get("call_window_end","19:00"),
         "recording": True})
    if _dec.verdict == "block":
        it["status"] = "compliance_blocked"
        record_call({..., "outcome": "compliance_blocked", "reason": ",".join(_dec.reasons)})
        if TELEPHONY_OPS_ENABLED and _LEAD_LOCK: _LEAD_LOCK.release(tenant_id, norm(num))
        idx += 1; continue
    # ALLOW/SOFT -> stash the disclosure_ctx for the metadata injection (3e).
    it["_disclosure"] = _dec.disclosure_ctx
```

### 3d. Number-pool pick (T5 dial substitution) — replace hard-wired TRUNK at caller.py:2951-2954

```python
_chosen_trunk = TRUNK; _chosen_did = None
if TELEPHONY_OPS_ENABLED and _ROUTER:
    _rc = _ROUTER.pick_next(tenant_id)
    if _rc is None:
        it["status"] = "queued_no_healthy_number"          # same path as ACTIVE_CALLS>=max_conc
        if _LEAD_LOCK: _LEAD_LOCK.release(tenant_id, norm(num))
        await asyncio.sleep(1); continue
    _chosen_trunk, _chosen_did = _rc.trunk_id, _rc.number
    it["_route"] = _rc
# ... at the dial (caller.py:2952):
sip_trunk_id=_chosen_trunk, sip_call_to=num,
# (set the CLI / from-number to _chosen_did via the existing participant attrs / trunk config)
```

### 3e. Disclosure injection — before `json.dumps(md_obj)` at caller.py:2941

```python
if COMPLIANCE_ENABLED and it.get("_disclosure") is not None:
    md_obj["disclosure"] = it["_disclosure"].as_metadata()   # {tier,brand,purpose,record_cue,say_*}
    # W2's brain emits this FIRST as control-flow (never a hardcoded agent.py string).
```

---

## 4. Finalize — outcome feedback + lock release (caller.py:2715, end of `_finalize_call`)

**Anchor:** end of `_finalize_call` (**caller.py:2715**), after the existing opt-out block
(**caller.py:2743**), where `rec["answered"]` / `rec["duration_s"]` are known.

```python
# number-pool outcome + health (auto-reduce/recover) + release the leased slot.
if TELEPHONY_OPS_ENABLED and _ROUTER and rec.get("_route") is not None:
    _ROUTER.record_outcome(tenant_id, rec["_route"],
                           answered=bool(rec.get("answered")),
                           duration_s=float(rec.get("duration_s") or 0),
                           outcome=rec.get("outcome",""))
# release the per-lead dial lock (idempotent; safe even if it expired).
if TELEPHONY_OPS_ENABLED and _LEAD_LOCK:
    _LEAD_LOCK.release(tenant_id, norm(rec.get("num","")))
# consent + recording rows on an opt-out / a recorded call.
if COMPLIANCE_ENABLED and _COMPLIANCE:
    if rec.get("opted_out"):
        _COMPLIANCE.dnd.record_optout(tenant_id, norm(rec.get("num","")))
        _COMPLIANCE.consent.revoke(tenant_id, rec.get("lead_id","") or "<hash>",
                                   "tcccpr_place_call")
```

> **Spam-health note:** this SHADOWS the live `trunk_registry.rotation.note_call_outcome`
> (per-trunk quarantine) with finer per-DID rolling-window scoring. The two co-exist:
> `SpamReputation.unhealthy_numbers([...])` produces the same `avoid=[bad_dids]` list the
> existing `trunk_registry.rotation.pick_did(avoid=...)` already accepts (rotation.py:70) —
> so the seam can feed our health verdict straight into the proven DID picker.

---

## 5. Retry / callback path (caller.py:7203-7250)

The retry scheduler (`scheduler_loop` at **caller.py:7241-7250**, `_spawn_retry_job` at
**caller.py:7203-7214**) gets the SAME guards before re-dialing a lead:

- **Window floor:** the existing `_in_window(camp_fields)[0]` check at **caller.py:7245** is
  wrapped with `_WINDOW.decide(..., apply_legal_floor=True).in_window` (same as §3a).
- **Lead-lock:** before `asyncio.create_task(run_job(jid))` at **caller.py:7214**, call
  `_LEAD_LOCK.acquire(...)` (same as §3b) — a retry can never collide with a live campaign dial.
- **Compliance preflight:** before `_spawn_retry_job(r)` at **caller.py:7249**, run the same
  `_COMPLIANCE.preflight(...)` (§3c); a `block` drops the retry (terminate the callback entry
  with the reason), never re-dials a now-DND / out-of-window lead.

---

## 6. Calling-window defaults (the ILLEGAL live default — caller.py:865-866, 875-876, 4251)

The literals `"09:00"`/`"21:00"` at `_in_window()` (**caller.py:865-866**),
`_clamp_to_window()` (**caller.py:875-876**), and `_coerce_fields()` (**caller.py:4251**)
are **NOT edited** — the legal floor is enforced in `voice_ops.compliance.window_floor`
(§3a wraps the result). Reason: keep caller.py byte-identical; the floor is a runtime clamp,
not a literal change, so flag-OFF leaves the live default untouched and flag-ON cannot widen
past 10:00–19:00 regardless of these literals. (A later cosmetic wave may also change the
schema defaults to 10:00/19:00 for UI honesty.)

---

## 7. Bulk DND scrub at campaign start (caller.py:5121 area)

Before `JOBS[jid]["leads"] = leads`, pre-filter when armed:

```python
if COMPLIANCE_ENABLED and _COMPLIANCE:
    kept = []
    for ld in leads:
        sr = _COMPLIANCE.dnd.scrub(tenant_id, norm(ld["num"]))
        if sr.block and not sr.needs_rescrub:        # hard DND/suppression hit -> drop now
            record_call({..., "outcome": "compliance_blocked", "reason": sr.reason})
        else:
            kept.append(ld)                          # cache-miss leads stay; per-lead gate re-scrubs
    leads = kept
```

The per-lead preflight (§3c) is still the authoritative gate (handles cache-miss requeue).

---

## 8. Earner-safety checklist for the seam wave (each box mutation)
1. `COMPLIANCE_ENABLED=0` + `TELEPHONY_OPS_ENABLED=0` -> resting build byte-identical; prove
   `md5 agent.py == 98655dbf`, a real outbound call still rings.
2. Flip `TELEPHONY_OPS_ENABLED=1` ALONE first (pool/router/lock/window, no compliance block) —
   real call rings, pool distributes, lock holds. Revert path = flag back to 0.
3. Only AFTER DLT + 140-series are registered (§9), flip `COMPLIANCE_ENABLED=1`; seed a fresh
   consent + a clear DND cache for the test lead; real call rings + a DND-listed test number
   is blocked. Revert = flag to 0.
4. One flag per box mutation, integrated real-flow smoke before AND after, immediate revert.

---

## 9. Founder / counsel actions (gating high-volume; recorded, see W26 §9)
- **DLT Principal-Entity registration** (per-tenant PE recommended; Famit as RTM/aggregator) —
  PAN/GST/incorporation + biometric (mandatory since Feb-2025); 3–7 business days.
- **Registered header + >=1 approved content template** (variable-slot envelope so the adaptive
  brain operates inside a registered structure).
- **140-series CLI** provisioning (promotional) / 1600 (transactional) — NOT a 10-digit mobile.
- **Auto-dialer pre-notification** to the originating access provider (a registration flag).
- **Counsel sign-off** on suspension/disconnection clause + the abandoned-call cap before
  high-volume; default disclosure **Tier 0** (Tier 1 for BFSI/insurance).
Until all done: keep `COMPLIANCE_ENABLED=0` (don't block dials) and do NOT run high-volume.
