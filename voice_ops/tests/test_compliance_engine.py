"""W12/W26 compliance-engine tests (no box, no Redis, no droplet imports).

Proves the India dial-time gate:
  1. preflight BLOCKS a DND-listed number (scrub-before-dial).
  2. preflight BLOCKS an out-of-(legal-)window dial; the legal window floor CANNOT be
     widened by a tenant.
  3. preflight returns a warm disclosure_ctx (brand+purpose+record cue) that NEVER
     contains the banned "AI assistant" phrase.
  4. preflight BLOCKS a 10-digit-mobile CLI (number-series violation) and a tenant with
     no DLT registration (fail-closed).
  5. consent freshness is enforced AT DIAL TIME (expired/explicit-7d/revoked all block).
  6. the gate is FLAG-GATED: COMPLIANCE_ENABLED off -> allow + compliance_unenforced.
  7. tenant-isolated (blank tenant fails closed).

Async tests use the repo convention: asyncio.run() inside a sync test.
"""
from __future__ import annotations

import asyncio
import datetime as _dt

from voice_ops.compliance.cli_series import check as cli_check, SERIES_140, SERIES_MOBILE
from voice_ops.compliance.config import ComplianceConfig
from voice_ops.compliance.consent import (
    BASIS_EXPLICIT,
    BASIS_INFERRED,
    ConsentLedger,
    InMemoryConsentStore,
    TCCCPR_PLACE_CALL,
)
from voice_ops.compliance.disclosure import (
    BANNED_PHRASES,
    build_disclosure_ctx,
    contains_banned_phrase,
)
from voice_ops.compliance.dnd import DndScrubber, InMemoryDndStore
from voice_ops.compliance.engine import (
    ComplianceEngine,
    InMemoryRegistrationStore,
    RegistrationState,
)
from voice_ops.compliance.window_floor import (
    clamp_to_legal_floor,
    legal_floor,
    widens_floor,
)


FIXED_NOW = _dt.datetime(2026, 6, 18, 6, 30, tzinfo=_dt.timezone.utc)   # 12:00 IST (in window)


def _now():
    return FIXED_NOW


def _ready_registration(tenant="t1", cli="+911400000001"):
    reg = InMemoryRegistrationStore()
    reg.put(RegistrationState(
        tenant_id=tenant, pe_status="active",
        headers=[{"header": "FAMITX", "status": "active"}],
        templates=[{"template_id": "T1", "status": "approved"}],
        cli_numbers=[{"number": cli, "series": "140", "status": "active"}],
        autodialer_notified=True,
    ))
    return reg


def _engine(*, enabled=True, reg=None, consent=None, dnd=None):
    cfg = ComplianceConfig(enabled=enabled, number_hash_salt="testsalt",
                           explicit_consent_days=7, dnd_refresh_days=30)
    return ComplianceEngine(
        cfg,
        registration_store=reg or _ready_registration(),
        consent_ledger=consent,
        dnd_scrubber=dnd,
        now_fn=_now,
    )


def _fresh_consent_ledger(tenant="t1", principal="lead-1", scope=""):
    led = ConsentLedger(InMemoryConsentStore(), explicit_days=7, now_fn=_now)
    led.grant(tenant, principal, TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT, scope=scope)
    return led


def _clear_dnd(salt="testsalt"):
    """A DND scrubber where the number is scrubbed CLEAR (fresh, not listed)."""
    store = InMemoryDndStore()
    dnd = DndScrubber(store, salt=salt, refresh_days=30, now_fn=_now)
    return dnd


# --------------------------------------------------------------------------- #
# 1) DND block.
# --------------------------------------------------------------------------- #
def test_preflight_blocks_dnd_listed_number():
    dnd = _clear_dnd()
    dnd.cache_ncpr("+919812345678", listed=True)          # number is on the NCPR register
    eng = _engine(consent=_fresh_consent_ledger(principal="lead-1"), dnd=dnd)
    lead = {"phone": "+919812345678", "lead_id": "lead-1"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "dnd"


def test_preflight_blocks_on_dnd_cache_miss_fail_closed():
    dnd = _clear_dnd()                                    # nothing cached -> cache miss
    eng = _engine(consent=_fresh_consent_ledger(principal="lead-1"), dnd=dnd)
    lead = {"phone": "+919800000000", "lead_id": "lead-1"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "dnd"
    assert d.needs_rescrub is True                        # must re-scrub, not dial


def test_preflight_allows_clear_number():
    dnd = _clear_dnd()
    dnd.cache_ncpr("+919811111111", listed=False)         # scrubbed clear, fresh
    eng = _engine(consent=_fresh_consent_ledger(principal="lead-7"), dnd=dnd)
    lead = {"phone": "+919811111111", "lead_id": "lead-7"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign", "brand": "Godrej",
            "product": "3BHK"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "allow"
    assert d.disclosure_ctx is not None


# --------------------------------------------------------------------------- #
# 2) Window: out-of-window block + floor cannot widen.
# --------------------------------------------------------------------------- #
def test_preflight_blocks_out_of_window():
    # now = 12:00 IST; tenant window 14:00-16:00 -> outside -> block at window gate.
    dnd = _clear_dnd()
    dnd.cache_ncpr("+919811111111", listed=False)
    eng = _engine(consent=_fresh_consent_ledger(principal="lead-7"), dnd=dnd)
    lead = {"phone": "+919811111111", "lead_id": "lead-7"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign",
            "window_start": "14:00", "window_end": "16:00"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "window"


def test_legal_floor_cannot_be_widened_property():
    # for a battery of tenant windows, the clamped window is ALWAYS a subset of the floor.
    floor_open, floor_close = legal_floor("")
    candidates = [
        ((6, 0), (23, 0)),    # tries to widen both ends
        ((0, 0), (23, 59)),   # all day
        ((9, 0), (21, 0)),    # the ILLEGAL live default
        ((11, 0), (17, 0)),   # already tighter
        ((22, 0), (23, 0)),   # entirely outside floor
        ((5, 0), (5, 0)),     # degenerate
    ]
    for ts, te in candidates:
        (eff_s, eff_e), _note = clamp_to_legal_floor(ts, te)
        # never starts before the floor open nor ends after the floor close.
        assert (eff_s[0] * 60 + eff_s[1]) >= (floor_open[0] * 60 + floor_open[1])
        assert (eff_e[0] * 60 + eff_e[1]) <= (floor_close[0] * 60 + floor_close[1])
        assert widens_floor(ts, te) is False              # the explicit assertion


def test_bfsi_floor_opens_earlier():
    (s, _e) = legal_floor("bfsi")
    assert s == (8, 0)                                    # BFSI opens at 08:00, not 10:00
    (s2, _e2) = legal_floor("realestate")
    assert s2 == (10, 0)


def test_env_floor_cannot_widen_past_absolute_ceiling():
    # Finding 1 regression: a hostile/misconfigured env floor (00:00-23:30) must be
    # clamped to the ABSOLUTE statutory ceiling 10:00-19:00 (08:00-19:00 BFSI). The env
    # knob can only TIGHTEN, never authorize a dial outside the legal window.
    bad = ComplianceConfig(enabled=True, window_start="00:00", window_end="23:30",
                           bfsi_window_start="00:00", bfsi_window_end="23:59")
    (s, e) = legal_floor("realestate", bad)
    assert s == (10, 0) and e == (19, 0)                  # clamped to commercial ceiling
    (bs, be) = legal_floor("bfsi", bad)
    assert bs == (8, 0) and be == (19, 0)                 # clamped to BFSI ceiling
    # and clamp_to_legal_floor (which reads legal_floor) must also never authorize 23:30.
    (eff_s, eff_e), _n = clamp_to_legal_floor((9, 0), (23, 30), vertical="realestate", cfg=bad)
    assert (eff_e[0] * 60 + eff_e[1]) <= (19 * 60)        # never past 19:00


def test_env_floor_can_still_narrow():
    # a counsel-tightened env floor (11:00-17:00) is honoured verbatim — narrowing is fine.
    tight = ComplianceConfig(enabled=True, window_start="11:00", window_end="17:00")
    (s, e) = legal_floor("realestate", tight)
    assert s == (11, 0) and e == (17, 0)


def test_engine_blocks_dial_when_env_tries_to_widen_window():
    # Finding 1 end-to-end: now = 20:00 IST (past 19:00). Even with an env floor that
    # claims 23:30, the engine must BLOCK at the window gate (env clamped to 19:00).
    now_2000 = _dt.datetime(2026, 6, 18, 14, 30, tzinfo=_dt.timezone.utc)  # 20:00 IST
    cfg = ComplianceConfig(enabled=True, number_hash_salt="testsalt",
                           window_start="00:00", window_end="23:30")
    eng = ComplianceEngine(cfg, registration_store=_ready_registration(),
                           consent_ledger=_fresh_consent_ledger(principal="lead-7"),
                           dnd_scrubber=_clear_dnd(), now_fn=lambda: now_2000)
    eng.dnd.cache_ncpr("+919811111111", listed=False)
    lead = {"phone": "+919811111111", "lead_id": "lead-7"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "window"


# --------------------------------------------------------------------------- #
# 3) Disclosure ctx: warm, never banned.
# --------------------------------------------------------------------------- #
def test_disclosure_ctx_warm_and_never_banned():
    ctx = build_disclosure_ctx(brand="Godrej", product="3BHK flat", tier=0, record_cue=True)
    for line in (ctx.say_en, ctx.say_hinglish, ctx.say_hindi):
        assert line                                       # non-empty
        assert not contains_banned_phrase(line)           # NEVER "AI assistant" etc.
    assert "Godrej" in ctx.say_en
    assert ctx.record_cue is True
    assert "record" in ctx.say_en.lower()                 # record cue present


def test_disclosure_all_tiers_avoid_banned_phrase():
    for tier in (0, 1, 2):
        ctx = build_disclosure_ctx(brand="Acme", product="loan", tier=tier, record_cue=True)
        for line in (ctx.say_en, ctx.say_hinglish, ctx.say_hindi):
            assert not contains_banned_phrase(line), f"tier {tier}: {line!r}"


def test_disclosure_scrubs_smuggled_banned_brand():
    # a brand containing a banned phrase must NOT end up verbatim in the opener.
    ctx = build_disclosure_ctx(brand="AI assistant Corp", product="x", tier=0)
    assert not contains_banned_phrase(ctx.say_en)
    assert "ai assistant" not in ctx.brand.lower()


def test_banned_list_nonempty():
    assert "ai assistant" in BANNED_PHRASES


# --------------------------------------------------------------------------- #
# 4) Number-series + registration.
# --------------------------------------------------------------------------- #
def test_cli_series_blocks_mobile_for_campaign():
    v = cli_check("+919812345678", purpose="campaign")    # a 10-digit mobile
    assert v.series == SERIES_MOBILE
    assert v.eligible is False


def test_cli_series_allows_140_for_campaign():
    v = cli_check("+911400012345", purpose="campaign")
    assert v.series == SERIES_140
    assert v.eligible is True


def test_preflight_blocks_unregistered_tenant_fail_closed():
    eng = _engine(reg=InMemoryRegistrationStore(),                 # NO registration row
                  consent=_fresh_consent_ledger(principal="lead-1"),
                  dnd=_clear_dnd())
    lead = {"phone": "+919811111111", "lead_id": "lead-1"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "registration"


def test_preflight_blocks_mobile_cli_number_series_gate():
    eng = _engine(consent=_fresh_consent_ledger(principal="lead-1"), dnd=_clear_dnd())
    lead = {"phone": "+919811111111", "lead_id": "lead-1"}
    camp = {"id": "", "cli": "+919999988888", "purpose": "campaign"}   # mobile CLI
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "number_series"


# --------------------------------------------------------------------------- #
# 5) Consent freshness at dial time.
# --------------------------------------------------------------------------- #
def test_consent_block_when_none_on_record():
    eng = _engine(consent=ConsentLedger(InMemoryConsentStore(), now_fn=_now), dnd=_clear_dnd())
    lead = {"phone": "+919811111111", "lead_id": "lead-no-consent"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign"}
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "consent"


def test_consent_explicit_expires_after_7_days():
    led = ConsentLedger(InMemoryConsentStore(), explicit_days=7, now_fn=_now)
    led.grant("t1", "lead-x", TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT)
    # fresh now.
    assert led.is_fresh("t1", "lead-x").fresh is True
    # 8 days later it must be stale.
    led8 = ConsentLedger(led.store, explicit_days=7, now_fn=lambda: FIXED_NOW + _dt.timedelta(days=8))
    assert led8.is_fresh("t1", "lead-x").fresh is False


def test_consent_revocation_wins():
    led = ConsentLedger(InMemoryConsentStore(), explicit_days=7, now_fn=_now)
    led.grant("t1", "lead-r", TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT)
    led.revoke("t1", "lead-r", TCCCPR_PLACE_CALL)         # newest row = revoked
    v = led.is_fresh("t1", "lead-r")
    assert v.fresh is False
    assert v.reason == "consent_revoked"


def test_consent_inferred_without_expiry_is_weak():
    led = ConsentLedger(InMemoryConsentStore(), now_fn=_now)
    led.grant("t1", "lead-i", TCCCPR_PLACE_CALL, basis=BASIS_INFERRED)   # no expiry
    assert led.is_fresh("t1", "lead-i").fresh is False


def test_consent_scope_does_not_collapse_to_other_campaign():
    # Finding 2 regression: a lead consented ONLY to campaign "campA". An empty-scope
    # query (a no-id campaign) must NOT inherit campA's consent.
    led = ConsentLedger(InMemoryConsentStore(), explicit_days=7, now_fn=_now)
    led.grant("t1", "lead-s", TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT, scope="campA")
    # exact campaign A query -> fresh.
    assert led.is_fresh("t1", "lead-s", scope="campA").fresh is True
    # empty-scope (no-id campaign) query -> NOT fresh (no collapse onto campA).
    assert led.is_fresh("t1", "lead-s", scope="").fresh is False
    # a DIFFERENT specific campaign -> NOT fresh.
    assert led.is_fresh("t1", "lead-s", scope="campB").fresh is False


def test_consent_global_grant_satisfies_any_scope():
    # a true GLOBAL grant (scope="") is blanket consent — satisfies any campaign query.
    led = ConsentLedger(InMemoryConsentStore(), explicit_days=7, now_fn=_now)
    led.grant("t1", "lead-g", TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT, scope="")
    assert led.is_fresh("t1", "lead-g", scope="").fresh is True
    assert led.is_fresh("t1", "lead-g", scope="campA").fresh is True


def test_engine_blocks_when_consent_only_for_other_campaign():
    # Finding 2 end-to-end: consent granted for campA; a no-id campaign must BLOCK at consent.
    led = ConsentLedger(InMemoryConsentStore(), explicit_days=7, now_fn=_now)
    led.grant("t1", "lead-7", TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT, scope="campA")
    eng = _engine(consent=led, dnd=_clear_dnd())
    eng.dnd.cache_ncpr("+919811111111", listed=False)
    lead = {"phone": "+919811111111", "lead_id": "lead-7"}
    camp = {"id": "", "cli": "+911400000001", "purpose": "campaign"}   # no id -> scope ""
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "block"
    assert d.gate == "consent"


# --------------------------------------------------------------------------- #
# 6) Flag gating.
# --------------------------------------------------------------------------- #
def test_flag_off_allows_with_unenforced_marker():
    eng = _engine(enabled=False, dnd=_clear_dnd(), consent=ConsentLedger(InMemoryConsentStore(), now_fn=_now))
    lead = {"phone": "+919812345678"}                     # would normally be a DND cache miss
    camp = {"id": "", "cli": "+919999988888", "purpose": "campaign"}   # would fail number-series
    d = asyncio.run(eng.preflight("t1", lead, camp))
    assert d.verdict == "allow"
    assert d.compliance_unenforced is True
    assert d.disclosure_ctx is not None                   # still built so W2 can be tested


# --------------------------------------------------------------------------- #
# 7) Tenant isolation.
# --------------------------------------------------------------------------- #
def test_blank_tenant_fails_closed():
    eng = _engine(dnd=_clear_dnd(), consent=_fresh_consent_ledger())
    d = asyncio.run(eng.preflight("", {"phone": "+91x"}, {"cli": "+911400000001"}))
    assert d.verdict == "block"
    assert d.gate == "tenant"
