"""Offline tests for ai_manager.identity — phone-norm, risk spine, default-deny permits.
No network, no creds, no PG. Run:
    cd droplet_work && python -m pytest ai_manager/tests/test_identity.py -q
"""
from __future__ import annotations

from ai_manager import identity as idn
from ai_manager import tools as _tools


# ---------------------------------------------------------------------------
# canonical_phone — every Indian form collapses to one canonical +91XXXXXXXXXX
# ---------------------------------------------------------------------------
def test_canonical_phone_collapses_all_forms():
    canon = "+919876543210"
    assert idn.canonical_phone("+919876543210") == canon       # E.164
    assert idn.canonical_phone("919876543210") == canon        # 91 prefix
    assert idn.canonical_phone("09876543210") == canon         # trunk 0
    assert idn.canonical_phone("9876543210") == canon          # bare 10
    assert idn.canonical_phone("+91 98765 43210") == canon     # spaces
    assert idn.canonical_phone("+91-98765-43210") == canon     # hyphens
    assert idn.canonical_phone("tel:+91 (98765) 43210") == canon  # junk + parens


def test_canonical_phone_empty_and_blank():
    assert idn.canonical_phone("") == ""
    assert idn.canonical_phone("   ") == ""
    assert idn.canonical_phone("not-a-phone") == ""  # no digits


def test_canonical_phone_short_number_best_effort():
    # too short to be an Indian mobile -> best-effort "+" + digits, never raises.
    out = idn.canonical_phone("12345")
    assert out.startswith("+") and out == "+12345"


# ---------------------------------------------------------------------------
# match_forms — caller-ID equivalence set (all forms the same number can arrive as)
# ---------------------------------------------------------------------------
def test_match_forms_contains_every_arrival_form():
    forms = idn.match_forms("9876543210")
    canon = "+919876543210"
    assert canon in forms
    assert "9876543210" in forms
    assert "09876543210" in forms
    assert "919876543210" in forms
    # any arrival form must normalize back into the SAME set
    for raw in ("+919876543210", "919876543210", "09876543210", "9876543210"):
        assert idn.canonical_phone(raw) in forms


def test_match_forms_is_consistent_across_forms():
    # every equivalent form yields a set that shares the canonical -> a registry keyed on any
    # form resolves the same number.
    a = idn.match_forms("+919876543210")
    b = idn.match_forms("09876543210")
    assert idn.canonical_phone("9876543210") in a
    assert idn.canonical_phone("9876543210") in b


def test_match_forms_empty_input():
    assert idn.match_forms("") == set()


# ---------------------------------------------------------------------------
# is_risky <-> classify_risk consistency across the FULL catalog
# ---------------------------------------------------------------------------
def _catalog_tools() -> list:
    reg = _tools.build_registry("stub")
    return sorted(reg.names())


def test_is_risky_iff_classify_not_safe_across_catalog():
    tools = _catalog_tools()
    assert tools, "catalog must expose tools"
    for tool in tools:
        risky = idn.is_risky(tool)
        risk = idn.classify_risk(tool)
        # the load-bearing invariant: is_risky(t) <=> classify_risk(t) != "safe"
        assert risky == (risk != "safe"), (tool, risky, risk)
        assert risk in ("safe", "bulk", "money", "destructive"), (tool, risk)


def test_known_risk_buckets():
    assert idn.classify_risk("ads.set_budget") == "money"
    assert idn.classify_risk("ads.create_campaign") == "money"
    assert idn.classify_risk("creative.generate_video") == "money"
    assert idn.classify_risk("whatsapp.generate_templates") == "money"
    assert idn.classify_risk("leads.delete") == "destructive"
    assert idn.classify_risk("leads.enqueue_calls") == "bulk"
    assert idn.classify_risk("whatsapp.send") == "bulk"
    assert idn.classify_risk("ads.pause") == "bulk"
    assert idn.classify_risk("workflow.activate") == "bulk"
    assert idn.classify_risk("workflow.run_now") == "bulk"
    # explicitly NOT risky (catalog risk_class=safe)
    for safe in ("analytics.read", "leads.read", "contacts.write", "suppression.add",
                 "campaigns.create", "workflow.create_draft", "booking.create",
                 "booking.cancel", "wallet.read", "brain.retrieve"):
        assert idn.classify_risk(safe) == "safe", safe
        assert not idn.is_risky(safe), safe


def test_classify_risk_unknown_tool_is_safe():
    assert idn.classify_risk("totally.unknown") == "safe"
    assert not idn.is_risky("totally.unknown")
    assert idn.classify_risk("") == "safe"


# ---------------------------------------------------------------------------
# stepup_scope — one budget PIN can't authorize a delete
# ---------------------------------------------------------------------------
def test_stepup_scope_per_bucket():
    assert idn.stepup_scope("ads.set_budget") == "spend"        # money -> spend
    assert idn.stepup_scope("leads.enqueue_calls") == "bulk"    # bulk  -> bulk
    assert idn.stepup_scope("leads.delete") == "destructive"    # destructive -> destructive
    assert idn.stepup_scope("analytics.read") == ""             # safe  -> no step-up


def test_stepup_scope_matches_classify_for_catalog():
    bucket_to_scope = {"money": "spend", "bulk": "bulk", "destructive": "destructive", "safe": ""}
    for tool in _catalog_tools():
        assert idn.stepup_scope(tool) == bucket_to_scope[idn.classify_risk(tool)], tool


# ---------------------------------------------------------------------------
# permits — default-deny capability check
# ---------------------------------------------------------------------------
def test_permits_admin_and_owner_can_do_everything():
    for role in ("admin", "owner"):
        for tool in ("leads.delete", "ads.set_budget", "analytics.read", "whatsapp.send"):
            assert idn.permits(role, [], tool), (role, tool)
        # case-insensitive role
        assert idn.permits(role.upper(), None, "leads.delete")


def test_permits_viewer_reads_only_with_empty_grants():
    # viewer/operator with NO grants: READS allowed in read modules...
    assert idn.permits("viewer", [], "analytics.read")
    assert idn.permits("viewer", [], "leads.read")
    assert idn.permits("operator", None, "wallet.read")
    assert idn.permits("viewer", [], "booking.read")
    # ...but a write/delete/spend is DENIED (default-deny).
    assert not idn.permits("viewer", [], "contacts.write")
    assert not idn.permits("viewer", [], "leads.delete")
    assert not idn.permits("operator", [], "ads.set_budget")
    # a read verb in a NON-read module is still denied with no grant.
    assert not idn.permits("viewer", [], "ads.read")


def test_permits_unknown_module_denied_for_low_role():
    # an unknown module with no grant -> denied for a non-full role.
    assert not idn.permits("viewer", [], "mystery.read")
    assert not idn.permits("operator", [], "mystery.do")


def test_permits_explicit_grants_narrow_and_allow():
    # whole-module grant allows any tool in that module...
    assert idn.permits("operator", ["ads"], "ads.set_budget")
    assert idn.permits("viewer", ["contacts"], "contacts.write")
    # specific-tool grant allows just that tool.
    assert idn.permits("operator", ["leads.delete"], "leads.delete")
    # ...but a NON-EMPTY grant set NEVER falls through to read-only: ungranted module denied.
    assert not idn.permits("operator", ["ads"], "leads.delete")
    assert not idn.permits("viewer", ["contacts"], "analytics.read")


def test_permits_manager_empty_grants_is_lenient_full():
    # a manager with no explicit grants gets the full set (mirrors endpoints _can fallback).
    assert idn.permits("manager", [], "ads.set_budget")
    assert idn.permits("manager", None, "leads.delete")
    # but an explicit grant narrows even a manager.
    assert idn.permits("manager", ["analytics"], "analytics.read")
    assert not idn.permits("manager", ["analytics"], "ads.set_budget")


def test_permits_blank_tool_denied():
    assert not idn.permits("admin", [], "")  # admin is full but an empty tool is meaningless
