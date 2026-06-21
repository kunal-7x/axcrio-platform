#!/usr/bin/env python3
"""Smoke test for entitlements.py resolution engine (CL-B1 GATE).
Runs WITHOUT Postgres (degrade path) by monkeypatching the tenant-scoped reads, so it proves the pure
resolution algorithm: precedence (status>override>plan>global), parent rolldown, unknown→hidden,
is_core floor, status gate, longest-prefix path→key. Exit 0 = PASS.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entitlements as E

FAILS = []
def check(name, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}")
    if not ok:
        FAILS.append(name)

# ── scenario injectors: override the tenant-scoped reads (no PG needed) ──
SCEN = {"status": "active", "plan_id": "plan_a", "ent_version": 1, "overrides": {}, "plan_ent": {}}
E.load_status = lambda tid: {"status": SCEN["status"], "plan_id": SCEN["plan_id"], "ent_version": SCEN["ent_version"]}
E.load_overrides = lambda tid: dict(SCEN["overrides"])
_real_plan_ent = E.load_plan_entitlements
E.load_plan_entitlements = lambda pid: dict(SCEN["plan_ent"])

def reset():
    SCEN.update({"status":"active","plan_id":"plan_a","ent_version":1,"overrides":{},"plan_ent":{}})
    E.invalidate()

reg = E.load_registry()
print(f"registry loaded: {len(reg)} keys")
assert len(reg) >= 80, "registry too small — seed not loaded"

print("\n=== RESOLUTION SMOKE TABLE ===\n")

# 1) RESTING STATE: everything ON (T17 byte-identical proof)
reset()
m = E.resolve_modes("t1")
nonon = {k:v for k,v in m.items() if v != "on"}
check("resting: ALL keys 'on'", nonon, {})

# 2) GLOBAL DEFAULT honored
reset()
check("global default: sell.leads", E.mode_for("t1","sell.leads"), "on")

# 3) PLAN entitlement layer (plan locks a feature)
reset(); SCEN["plan_ent"] = {"grow.ads": "locked"}; E.invalidate()
check("plan locks grow.ads → locked", E.mode_for("t1","grow.ads"), "locked")
check("plan-lock does NOT leak to sibling grow.funnels", E.mode_for("t1","grow.funnels"), "on")

# 4) PER-VENDOR OVERRIDE beats plan (most-specific-wins)
reset(); SCEN["plan_ent"]={"grow.ads":"locked"}; SCEN["overrides"]={"grow.ads":"on"}; E.invalidate()
check("override 'on' beats plan 'locked'", E.mode_for("t1","grow.ads"), "on")
reset(); SCEN["overrides"]={"sell.crm":"hidden"}; E.invalidate()
check("override hides sell.crm", E.mode_for("t1","sell.crm"), "hidden")

# 5) PARENT ROLLDOWN — hide a module → whole subtree hidden
reset(); SCEN["overrides"]={"mod.grow":"hidden"}; E.invalidate()
check("hide mod.grow → child grow.campaigns hidden", E.mode_for("t1","grow.campaigns"), "hidden")
check("hide mod.grow → grandchild grow.campaigns.create hidden", E.mode_for("t1","grow.campaigns.create"), "hidden")
check("hide mod.grow → sibling module mod.sell untouched", E.mode_for("t1","sell.leads"), "on")

# 6) PARENT ROLLDOWN — lock a module → subtree locked (not hidden)
reset(); SCEN["overrides"]={"mod.engage":"locked"}; E.invalidate()
check("lock mod.engage → child engage.calls locked", E.mode_for("t1","engage.calls"), "locked")

# 7) ROLLDOWN strictness — child 'on' under hidden parent still hidden (strictest wins)
reset(); SCEN["overrides"]={"mod.automate":"hidden","automate.webhooks":"on"}; E.invalidate()
check("child 'on' under hidden parent → hidden (strictest)", E.mode_for("t1","automate.webhooks"), "hidden")

# 8) is_core FLOOR — cannot be hidden by override
reset(); SCEN["overrides"]={"core.settings":"hidden"}; E.invalidate()
check("core.settings override hidden → demoted to on", E.mode_for("t1","core.settings"), "on")
# core CAN be locked (billing visible-but-locked allowed)
reset(); SCEN["overrides"]={"core.settings":"locked"}; E.invalidate()
check("core.settings can be locked", E.mode_for("t1","core.settings"), "locked")

# 9) STATUS GATE — suspended hides everything except core
reset(); SCEN["status"]="suspended"; E.invalidate()
check("suspended: non-core sell.leads hidden", E.mode_for("t1","sell.leads"), "hidden")
check("suspended: core.auth stays on", E.mode_for("t1","core.auth"), "on")
check("suspended: core.wallet_pay stays on (pay to reactivate)", E.mode_for("t1","core.wallet_pay"), "on")
check("suspended: core money.billing_overview stays on", E.mode_for("t1","money.billing_overview"), "on")
reset(); SCEN["status"]="disabled"; E.invalidate()
check("disabled: non-core hidden", E.mode_for("t1","engage.run"), "hidden")
reset(); SCEN["status"]="expired"; E.invalidate()
check("expired: non-core hidden", E.mode_for("t1","grow.campaigns"), "hidden")

# 10) UNKNOWN key → fail-closed hidden
reset()
check("unknown key → hidden", E.mode_for("t1","does.not.exist"), "hidden")

# 11) GARBAGE override value → fail-closed hidden
reset(); SCEN["overrides"]={"sell.leads":"banana"}; E.invalidate()
check("garbage override mode → hidden", E.mode_for("t1","sell.leads"), "hidden")

# 12) assert_access codes
reset()
import_ok = True
def code_of(tid, key):
    try:
        E.assert_access(tid, key); return 200
    except Exception as e:
        return getattr(e, "status_code", None)
check("assert_access on → 200", code_of("t1","sell.leads"), 200)
reset(); SCEN["overrides"]={"sell.leads":"hidden"}; E.invalidate()
check("assert_access hidden → 404", code_of("t1","sell.leads"), 404)
reset(); SCEN["overrides"]={"sell.leads":"locked"}; E.invalidate()
check("assert_access locked → 402", code_of("t1","sell.leads"), 402)
reset()
check("assert_access unknown key → 404", code_of("t1","ghost.feature"), 404)

# 13) PATH → feature_key (longest-prefix-wins + shared map)
reset()
check("path /leads → sell.leads", E.feature_key_for_path("/leads"), "sell.leads")
check("path /leads/abc123 → sell.leads (param)", E.feature_key_for_path("/leads/abc123"), "sell.leads")
check("path /leads/hot → command.dashboard (shared map, NOT sell.leads)", E.feature_key_for_path("/leads/hot"), "command.dashboard")
check("path /stats → command.dashboard", E.feature_key_for_path("/stats"), "command.dashboard")
# A path with a {cid} param BETWEEN segments (/campaigns/<id>/ab) correctly falls back to the parent
# page grow.campaigns (the static /campaigns/ab prefix can't match a mid-path id). Parent-governs-child
# is the security-correct fallback: the sub-route is never LESS governed than its page.
check("path /campaigns/cid/ab → grow.campaigns (parent governs; id mid-path)", E.feature_key_for_path("/campaigns/cid/ab"), "grow.campaigns")
check("path /campaigns/cid → grow.campaigns", E.feature_key_for_path("/campaigns/cid"), "grow.campaigns")
# A route literally starting with the longer prefix resolves to the more-specific key (longest-wins).
check("path /workflows/publish → grow longest-wins (automate.workflows.publish)", E.feature_key_for_path("/workflows/publish"), "automate.workflows.publish")
check("path /me/entitlements → core.me_entitlements", E.feature_key_for_path("/me/entitlements"), "core.me_entitlements")
check("path /wallet/topup → core.wallet_pay", E.feature_key_for_path("/wallet/topup"), "core.wallet_pay")
check("ungoverned path → None", E.feature_key_for_path("/totally/unknown/route"), None)

# 14) effective_limits from plan
reset()
lim = E.effective_limits("t1")
check("plan_a limits: max_concurrency", lim.get("max_concurrency"), 3)
check("plan_a limits: monthly_credits", lim.get("monthly_credits"), 500000)
reset(); SCEN["plan_id"]="enterprise"; E.invalidate()
check("enterprise limits: max_concurrency", E.effective_limits("t1").get("max_concurrency"), 20)

# 15) OpenFeature facade returns identical result
reset(); SCEN["overrides"]={"grow.ads":"locked"}; E.invalidate()
check("facade evaluate == mode_for", E.evaluate("t1","grow.ads"), E.mode_for("t1","grow.ads"))

# 16) entitlements_payload shape
reset()
p = E.entitlements_payload("t1")
check("payload has modes/status/plan/version", sorted(p.keys()), ["modes","plan","status","version"])
check("payload status active", p["status"], "active")
check("payload plan plan_a", p["plan"], "plan_a")

print("\n=== SUMMARY ===")
if FAILS:
    print(f"FAILED ({len(FAILS)}): {FAILS}")
    sys.exit(1)
print("ALL SMOKE CHECKS PASSED")
sys.exit(0)
