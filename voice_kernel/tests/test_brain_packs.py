"""W2 brain-pack tests. Proves the founder laws + the contract binding:

  - support mode does NOT push sales (stance flag + objective + objection tilt)
  - real-estate vocabulary NEVER leaks cross-vertical (industry vocab is scoped)
  - the disclosure default has NO banned phrase (spoken line clean, every tier)
  - packs are swappable (store override beats the shipped default)
  - versioning transitions work (draft->test->publish->rollback + campaign pin)
  - the provider conforms to the FROZEN BrainPackProvider Protocol
  - building a kernel with the provider imports ZERO droplet_work modules
  - flag-OFF byte-identity: the adapter still returns the legacy string verbatim
"""
from __future__ import annotations

import sys

import pytest

from voice_kernel.brain_packs import (
    BrainPacks,
    DisclosureConfig,
    DisclosureTier,
    JsonBrainPackStore,
    VersionState,
    all_industry_packs,
    all_use_case_packs,
    build_brain_packs,
    build_disclosure_str,
    contains_banned_phrase,
    contains_banned_literary,
    get_use_case_pack,
    language_directive,
    stance_for,
    strip_guardrail,
)
from voice_kernel.brain_packs.registry import BrainPackStore
from voice_kernel.contracts import BrainPackProvider
from voice_kernel.packet import IndustryLayer, ModeLayer, UseCase


# --------------------------------------------------------------------------- #
# 1. Protocol conformance — the provider binds the FROZEN contract.
# --------------------------------------------------------------------------- #
def test_provider_conforms_to_frozen_protocol():
    prov = build_brain_packs()
    assert isinstance(prov, BrainPackProvider)  # runtime_checkable structural check
    assert isinstance(prov.use_case_layer(UseCase.SALES, {}), ModeLayer)
    assert isinstance(prov.industry_layer({}), IndustryLayer)


def test_one_pack_per_use_case_enum_member():
    covered = {p.use_case for p in all_use_case_packs()}
    assert covered == set(UseCase), f"missing packs for {set(UseCase) - covered}"


# --------------------------------------------------------------------------- #
# 2. SUPPORT does NOT push sales.
# --------------------------------------------------------------------------- #
def test_support_pack_does_not_push_sale():
    support = get_use_case_pack(UseCase.SUPPORT)
    assert support.stance.pushes_sale is False
    assert support.stance.empathy_first is True
    # the support objective is resolve-not-sell.
    obj = support.objective_template.lower()
    assert "resolve" in obj
    assert "sell" not in obj or "no selling" in obj or "not a sales" in support.success_criteria.lower()


def test_support_modelayer_has_no_sales_advance_directive():
    prov = build_brain_packs()
    m = prov.use_case_layer(UseCase.SUPPORT, {"company_name": "X", "goal": "fix the router"})
    low = m.objective_str.lower()
    # the SALES objective verb 'advance the lead ... revenue next step' must be absent
    assert "advance the lead" not in low
    assert "purchase intent" not in low
    assert "booked next step" not in low
    # the support success criterion explicitly says NOT a sales close
    assert "not a sales close" in m.success_criteria.lower() or "satisfaction" in m.success_criteria.lower()


def test_support_objection_stance_is_de_escalation_not_counter_sell():
    stance = stance_for(UseCase.SUPPORT)
    joined = " ".join(stance).lower()
    assert "do not counter-sell" in joined or "not counter-sell" in joined
    # sales stance, by contrast, ends on a soft re-close (a sell move)
    sales_stance = " ".join(stance_for(UseCase.SALES)).lower()
    assert "re-close" in sales_stance


def test_complaint_and_feedback_do_not_push_sale():
    for uc in (UseCase.COMPLAINT, UseCase.FEEDBACK, UseCase.AFTER_SALES):
        assert get_use_case_pack(uc).stance.pushes_sale is False


def test_service_modes_objective_carries_no_sales_coaching_hook():
    """RED-TEAM regression: the objection HOOK MENU (not just the 5-step stance)
    must not inject sales-coaching ('establish VALUE before price', 'break price
    into EMI/appreciation', 'reframe on differentiators', fabricate scarcity) into
    a no-push mode. Previously every mode dumped the full hook menu, leaking sell
    moves into support/complaint/reminder/feedback."""
    prov = build_brain_packs()
    sell_phrases = (
        "establish value before price",
        "break price into",
        "cost-of-inaction",
        "defer discounts",
        "reframe on the campaign's genuine differentiators",
        "scarcity",
    )
    for uc in (UseCase.SUPPORT, UseCase.COMPLAINT, UseCase.REMINDER, UseCase.FEEDBACK, UseCase.AFTER_SALES, UseCase.ONBOARDING):
        low = prov.use_case_layer(uc, {"company_name": "Acme", "goal": "help the customer"}).objective_str.lower()
        leaked = [p for p in sell_phrases if p in low]
        assert not leaked, f"{uc.value} objective leaked sales-coaching hooks: {leaked}"
    # the revenue modes STILL carry the full sell menu (not over-filtered)
    for uc in (UseCase.SALES, UseCase.RENEWAL):
        low = prov.use_case_layer(uc, {"company_name": "Acme"}).objective_str.lower()
        assert "establish value before price" in low, f"{uc.value} lost its sales hooks"


# --------------------------------------------------------------------------- #
# 3. Real-estate vocabulary NEVER leaks cross-vertical.
# --------------------------------------------------------------------------- #
def _real_estate_terms() -> set[str]:
    re_pack = next(p for p in all_industry_packs() if p.id == "real_estate.v1")
    return {t.lower() for t in re_pack.vertical_terms}


def test_real_estate_industry_resolves_only_for_real_estate():
    prov = build_brain_packs()
    re_layer = prov.industry_layer({"product_name": "3 BHK flat", "company_name": "Godrej Properties"})
    assert re_layer.pack_id == "real_estate.v1"
    assert "site visit" in {t.lower() for t in re_layer.vertical_terms}


def test_real_estate_vocab_does_not_leak_into_other_verticals():
    prov = build_brain_packs()
    re_terms = _real_estate_terms()
    # an insurance campaign + a support call + a neutral call: NONE may carry RE vocab
    cases = [
        {"product_name": "term life policy", "company_name": "LIC", "product_summary": "premium and claim"},
        {"company_name": "Acme", "product_summary": "router not working, need support"},
        {"company_name": "Generic Co"},
    ]
    for fields in cases:
        ind = prov.industry_layer(fields)
        layer_terms = {t.lower() for t in ind.vertical_terms}
        leaked = layer_terms & re_terms
        assert not leaked, f"real-estate vocab leaked into {ind.pack_id}: {leaked}"
        assert ind.pack_id != "real_estate.v1"


def test_support_modelayer_carries_no_real_estate_vocab():
    prov = build_brain_packs()
    re_terms = _real_estate_terms()
    m = prov.use_case_layer(UseCase.SUPPORT, {"company_name": "Acme", "product_summary": "router broken"})
    low = m.objective_str.lower()
    for term in re_terms:
        # the SUPPORT L1 objective must not name any real-estate-specific vocab
        assert term not in low, f"real-estate term {term!r} leaked into SUPPORT objective"


def test_neutral_industry_is_empty():
    prov = build_brain_packs()
    ind = prov.industry_layer({"company_name": "Mystery Co"})
    assert ind.pack_id == "neutral.v1"
    assert ind.vertical_terms == ()


# --------------------------------------------------------------------------- #
# 4. Disclosure default has NO banned phrase (every tier, spoken line clean).
# --------------------------------------------------------------------------- #
def test_disclosure_default_tier0_has_no_banned_phrase():
    s = build_disclosure_str("Godrej", "your enquiry about the 3 BHK")
    spoken = strip_guardrail(s)
    assert not contains_banned_phrase(spoken), spoken
    # Tier 0 default names the brand + a record cue, never an AI label.
    assert "Godrej" in spoken
    assert "recording" in spoken.lower() or "record" in spoken.lower()


def test_disclosure_all_tiers_have_no_banned_spoken_phrase():
    for tier in (DisclosureTier.BRAND_IDENTITY, DisclosureTier.ASSISTANT_CUE, DisclosureTier.EXPLICIT_AI):
        for lang in ("hinglish", "english"):
            cfg = DisclosureConfig(tier=tier, language=lang)
            spoken = strip_guardrail(build_disclosure_str("Acme", "your order", cfg))
            assert not contains_banned_phrase(spoken), f"tier={tier} lang={lang}: {spoken!r}"


def test_identity_layer_disclosure_is_structural_always_on():
    prov = build_brain_packs()
    idl = prov.identity_layer({"company_name": "Godrej", "goal": "site visit"})
    assert idl.disclose_ai is True
    assert idl.ai_disclosure_str.strip() != ""
    assert not contains_banned_phrase(strip_guardrail(idl.ai_disclosure_str))


def test_disclosure_rejects_a_banned_vendor_override():
    # a vendor tries to inject the banned self-label -> rejected, structural default used
    cfg = DisclosureConfig(vendor_script_disclosure="Hi, I am an AI assistant from Acme.")
    spoken = strip_guardrail(build_disclosure_str("Acme", "your demo", cfg))
    assert not contains_banned_phrase(spoken)


def test_disclosure_honours_a_clean_vendor_override():
    clean = "Namaste, main Riya bol rahi hoon Acme ki taraf se."
    cfg = DisclosureConfig(vendor_script_disclosure=clean, record_consent=False)
    out = strip_guardrail(build_disclosure_str("Acme", "", cfg))
    assert clean in out


# --------------------------------------------------------------------------- #
# 5. Packs are SWAPPABLE — a store override beats the shipped default.
# --------------------------------------------------------------------------- #
def _sales_override_body() -> dict:
    return {
        "id": "sales",
        "use_case": "sales",
        "stance": {"key": "advance", "description": "x", "pushes_sale": True},
        "objective_template": "CUSTOM-SALES-OBJECTIVE-OVERRIDE",
        "success_criteria": "CUSTOM-SUCCESS",
        "opening_style": "custom open",
        "data_to_collect": ["a", "b"],
        "behavior_pack_ids": [],
    }


def test_packs_are_swappable_via_published_store_override():
    store = BrainPackStore()
    pv = store.create_draft("use_case", "sales", _sales_override_body())
    store.publish("use_case", "sales", pv.version)
    prov = BrainPacks(store=store)
    m = prov.use_case_layer(UseCase.SALES, {"company_name": "X"})
    assert "CUSTOM-SALES-OBJECTIVE-OVERRIDE" in m.objective_str
    assert m.success_criteria == "CUSTOM-SUCCESS"
    # without publishing, the default stands
    prov_default = build_brain_packs()
    assert "CUSTOM-SALES-OBJECTIVE-OVERRIDE" not in prov_default.use_case_layer(UseCase.SALES, {}).objective_str


def test_industry_pack_is_swappable():
    store = BrainPackStore()
    body = {"id": "real_estate.v1", "label": "RE", "match": ["flat"], "vertical_terms": ["NEW-RE-TERM"]}
    pv = store.create_draft("industry", "real_estate.v1", body)
    store.publish("industry", "real_estate.v1", pv.version)
    prov = BrainPacks(store=store)
    ind = prov.industry_layer({"product_name": "a flat"})
    assert "NEW-RE-TERM" in ind.vertical_terms


# --------------------------------------------------------------------------- #
# 6. Versioning transitions + campaign pin (the RenderBrain store).
# --------------------------------------------------------------------------- #
def test_version_lifecycle_draft_test_publish_rollback():
    store = BrainPackStore()
    v1 = store.create_draft("use_case", "sales", _sales_override_body(), note="v1")
    assert v1.state == VersionState.DRAFT and v1.version == 1
    store.mark_tested("use_case", "sales", 1)
    p1 = store.publish("use_case", "sales", 1)
    assert p1.state == VersionState.PUBLISHED
    assert store.published("use_case", "sales").version == 1

    # a second version publishes and archives the first
    body2 = dict(_sales_override_body(), objective_template="V2-OBJ")
    store.create_draft("use_case", "sales", body2)
    store.publish("use_case", "sales", 2)
    assert store.published("use_case", "sales").version == 2
    assert store.get("use_case", "sales", 1).state == VersionState.ARCHIVED

    # rollback re-publishes v1
    store.rollback("use_case", "sales", 1)
    assert store.published("use_case", "sales").version == 1
    assert store.get("use_case", "sales", 2).state == VersionState.ARCHIVED


def test_published_versions_are_immutable():
    store = BrainPackStore()
    store.create_draft("use_case", "sales", _sales_override_body())
    store.publish("use_case", "sales", 1)
    with pytest.raises(ValueError):
        store.update_draft("use_case", "sales", 1, {"objective_template": "x"})


def test_campaign_pin_overrides_published_version():
    store = BrainPackStore()
    store.create_draft("use_case", "sales", dict(_sales_override_body(), objective_template="V1"))
    store.publish("use_case", "sales", 1)
    store.create_draft("use_case", "sales", dict(_sales_override_body(), objective_template="V2"))
    store.publish("use_case", "sales", 2)  # default published = v2
    store.pin_campaign("campaignA", "use_case", "sales", 1)  # A pinned to v1

    prov = BrainPacks(store=store)
    m_pinned = prov.use_case_layer(UseCase.SALES, {"campaign_id": "campaignA"})
    m_float = prov.use_case_layer(UseCase.SALES, {"campaign_id": "campaignB"})
    assert "V1" in m_pinned.objective_str
    assert "V2" in m_float.objective_str

    bindings = store.campaign_bindings("campaignA")
    assert bindings["use_case:sales"] == 1


def test_json_store_persists_and_reloads(tmp_path):
    p = tmp_path / "packs.json"
    store = JsonBrainPackStore(p)
    store.create_draft("use_case", "sales", _sales_override_body())
    store.publish("use_case", "sales", 1)
    store.pin_campaign("c9", "use_case", "sales", 1)
    # reload from disk into a fresh store
    store2 = JsonBrainPackStore(p)
    assert store2.published("use_case", "sales").version == 1
    assert store2.version_for_campaign("c9", "use_case", "sales").version == 1


def test_rollback_to_unpublished_draft_is_rejected():
    store = BrainPackStore()
    store.create_draft("use_case", "sales", _sales_override_body())  # v1 draft, never published
    with pytest.raises(ValueError):
        store.rollback("use_case", "sales", 1)


# --------------------------------------------------------------------------- #
# 7. Objective engine: campaign goal is LAYERED IN, never replacing behavior.
# --------------------------------------------------------------------------- #
def test_campaign_goal_specialises_but_does_not_replace_behavior():
    prov = build_brain_packs()
    pack = get_use_case_pack(UseCase.SALES)
    m = prov.use_case_layer(UseCase.SALES, {"goal": "book a Diwali-offer site visit", "company_name": "Godrej"})
    # the abstract behavioral template is still present (not replaced) ...
    assert pack.objective_template[:30] in m.objective_str
    # ... AND the campaign goal is layered in.
    assert "book a Diwali-offer site visit" in m.objective_str


def test_no_goal_still_yields_correct_mode_behavior():
    prov = build_brain_packs()
    m = prov.use_case_layer(UseCase.REMINDER, {"company_name": "Acme"})  # no goal configured
    assert m.brain_pack_id == "reminder.v1"
    assert m.objective_str.strip() != ""  # the pack template stands alone


# --------------------------------------------------------------------------- #
# 8. Casual-Hinglish layer (W6 §E).
# --------------------------------------------------------------------------- #
def test_language_directive_bans_literary_words():
    d = language_directive().lower()
    assert "literary" in d or "sanskrit" in d
    # the directive itself names what to avoid; the detector flags literary text.
    assert contains_banned_literary("yeh project atyant mahatvapurn hai")
    assert not contains_banned_literary("yeh project aapke liye kaafi sahi hai")


# --------------------------------------------------------------------------- #
# 9. Isolation: building a kernel with the provider imports ZERO droplet modules.
# --------------------------------------------------------------------------- #
def test_brain_packs_import_no_droplet_modules():
    """The W2 brain-pack package must add ZERO droplet_work modules to sys.modules.

    Delta-based (not absolute): a concurrent sibling wave's test (e.g. W7 memory
    erasure) may have pre-loaded `droplet_work.db.engine` into this same pytest
    process. We assert that IMPORTING + BUILDING the brain packs adds no NEW
    droplet module — i.e. OUR code imports none — which is the real isolation
    guarantee and is order-independent."""
    from voice_kernel.kernel import build_kernel

    before = {m for m in sys.modules if m.startswith("droplet")}
    import voice_kernel.brain_packs  # noqa: F401

    build_kernel(brain_packs=build_brain_packs())
    after = {m for m in sys.modules if m.startswith("droplet")}
    added = sorted(after - before)
    assert added == [], f"brain packs must not import droplet modules, added: {added}"


def test_kernel_folds_in_the_provider_on_warm_path():
    """End-to-end: register the provider via build_kernel and assert the L1/L2
    layers actually land in the assembled prefix (C2 session required)."""
    from voice_kernel.contracts import CallContext, KernelSession
    from voice_kernel.kernel import build_kernel
    from voice_kernel.config import KernelConfig
    from voice_kernel.packet import PacketMeta

    kernel = build_kernel(KernelConfig(enabled=True), brain_packs=build_brain_packs())
    meta = PacketMeta(tenant_id="t1", campaign_id="c1", call_id="call-1", room="r")
    ctx = CallContext(
        meta=meta,
        fields={"company_name": "Godrej", "product_name": "3 BHK flat", "goal": "book a site visit", "agent_name": "Riya"},
        session=KernelSession(tenant_id="t1", call_id="call-1"),
    )
    prefix, packet = kernel.assemble_prefix_core(ctx)
    assert packet.mode.brain_pack_id == "sales.v1"
    assert packet.industry.pack_id == "real_estate.v1"
    assert "OBJECTIVE:" in prefix
    assert "VERTICAL TERMS:" in prefix


# --------------------------------------------------------------------------- #
# 10. Flag-OFF byte-identity holds (the adapter is untouched by W2).
# --------------------------------------------------------------------------- #
def test_flag_off_adapter_returns_legacy_string_verbatim():
    from voice_kernel.adapter import instructions_provider
    from voice_kernel.config import KernelConfig
    from voice_kernel.contracts import CallContext
    from voice_kernel.packet import PacketMeta

    legacy = "LEGACY-LIVE-PROMPT-STRING-UNCHANGED"
    cfg = KernelConfig()  # default OFF (outbound master switch off)
    meta = PacketMeta(tenant_id="t", campaign_id="c", call_id="x", room="r", direction="outbound")
    ctx = CallContext(meta=meta, fields={"company_name": "Godrej", "product_name": "flat"})
    out = instructions_provider(lambda: legacy, ctx, cfg=cfg)
    # OFF -> byte-identical legacy; the W2 brain packs are never reached.
    assert out == legacy
