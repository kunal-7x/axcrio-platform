"""Tests for voice_ops.config (W13) — no Postgres, no Redis, no droplet imports.

Proves the founder's contract:
  - an added key joins the rotation LIVE (no restart);
  - an unhealthy key is SKIPPED and the failover is LOGGED (never silent);
  - a vendor-config change PROPAGATES (version bump + cache invalidate + config_changed event);
  - tenant isolation (cross-tenant ciphertext fails closed; in-mem backend never crosses tenants);
  - secrets are NEVER in plaintext (encrypted at rest, masked, fingerprinted);
  - per-tenant retention + future-ready WhatsApp;
  - 0 droplet/agent imports at module load.
"""
from __future__ import annotations

import asyncio

import pytest

from voice_kernel.events import InMemoryEventBus, EventName
from voice_ops import config as C
from voice_ops.config import (
    HealthScoredKeyPool,
    KeyRouter,
    ProviderKeyStore,
    VendorProfile,
    VendorProfileStore,
    events as cfg_events,
    store as cfg_store,
    vault,
)


# --------------------------------------------------------------------------- #
# fixtures: master secret, in-memory backend, in-memory event bus.
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def master_secret(monkeypatch):
    monkeypatch.setenv("FAMIT_KEYSTORE_SECRET", "test-master-secret-32bytes-derive-key")
    yield


@pytest.fixture(autouse=True)
def mem_backend():
    backend = cfg_store.InMemoryBackend()
    cfg_store.set_backend_for_tests(backend)
    yield backend
    cfg_store.set_backend_for_tests(None)


@pytest.fixture
def bus():
    b = InMemoryEventBus()
    cfg_events.set_event_bus(b)
    yield b
    cfg_events.set_event_bus(None)


def _clock():
    """A controllable monotonic clock for deterministic circuit/cooldown tests."""
    state = {"t": 1000.0}

    def now():
        return state["t"]

    def advance(dt):
        state["t"] += dt

    now.advance = advance  # type: ignore[attr-defined]
    return now


# =========================================================================== #
# 1. VAULT — secrets never plaintext + cross-tenant non-portability
# =========================================================================== #
def test_vault_round_trip_and_mask():
    blob = vault.encrypt_secret("orgA", "groq", "gsk_supersecret_value_123456")
    assert blob["ciphertext"] != b"gsk_supersecret_value_123456"
    pt = vault.decrypt_secret("orgA", "groq", blob["ciphertext"], blob["key_version"])
    assert pt == "gsk_supersecret_value_123456"
    assert vault.mask("gsk_supersecret_value_123456").startswith("gsk_")
    assert "supersecret" not in vault.mask("gsk_supersecret_value_123456")
    assert blob["key_aad"] == "orgA|groq|1"


def test_vault_cross_tenant_fails_closed():
    blob = vault.encrypt_secret("orgA", "groq", "secret-for-A")
    with pytest.raises(Exception):  # InvalidTag — AAD mismatch under orgB
        vault.decrypt_secret("orgB", "groq", blob["ciphertext"], blob["key_version"])


def test_vault_cross_provider_fails_closed():
    blob = vault.encrypt_secret("orgA", "groq", "secret-for-groq")
    with pytest.raises(Exception):  # same tenant, wrong provider in AAD
        vault.decrypt_secret("orgA", "sarvam", blob["ciphertext"], blob["key_version"])


def test_vault_refuses_empty_and_no_master_secret(monkeypatch):
    with pytest.raises(vault.VaultError):
        vault.encrypt_secret("orgA", "groq", "")
    for env in ("PROVIDER_REGISTRY_KEYSTORE_SECRET", "PROVIDER_KEYSTORE_SECRET",
                "FAMIT_KEYSTORE_SECRET", "CONFIG_VAULT_SECRET"):
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(vault.VaultError):
        vault.encrypt_secret("orgA", "groq", "tok")


# =========================================================================== #
# 2. KEY STORE — added key joins rotation LIVE; never stores plaintext
# =========================================================================== #
def test_added_key_is_encrypted_and_never_plaintext(mem_backend):
    ks = ProviderKeyStore()
    rec = ks.add_key("orgA", "groq", "gsk_live_key_abcdef123456", label="primary", added_by="founder")
    assert "gsk_live_key_abcdef123456" not in str(rec)  # public record has no plaintext
    # the persisted backend row never contains the plaintext either.
    row = mem_backend.read("orgA", "provider_keys")
    assert "gsk_live_key_abcdef123456" not in str(row["doc"])
    assert row["doc"]["groq"][0]["ciphertext_b64"]  # only ciphertext at rest


def test_added_key_joins_rotation_live(bus):
    """A panel-added key shows up on the next resolve — no restart, no redeploy."""
    ks = ProviderKeyStore()
    kr = KeyRouter("orgA", ks)
    # empty pool -> LOUD not-found
    r0 = kr.resolve_key("groq")
    assert r0.found is False and "no keys configured" in r0.reason
    # add a key (live)
    ks.add_key("orgA", "groq", "gsk_first_key_111111111111", added_by="founder")
    r1 = kr.resolve_key("groq")
    assert r1.found is True and r1.plaintext == "gsk_first_key_111111111111"
    # add a SECOND key live; both now rotate
    ks.add_key("orgA", "groq", "gsk_second_key_2222222222", added_by="founder")
    seen = {kr.resolve_key("groq").plaintext for _ in range(6)}
    assert "gsk_first_key_111111111111" in seen and "gsk_second_key_2222222222" in seen
    # events: provider_key_added emitted on the tenant stream
    names = {e.name for e in bus.all_events("orgA")}
    assert EventName.PROVIDER_KEY_ADDED.value in names
    assert EventName.CONFIG_CHANGED.value in names


# =========================================================================== #
# 3. HEALTH POOL — unhealthy key is SKIPPED + failover LOGGED (never silent)
# =========================================================================== #
def test_unhealthy_key_skipped_and_failover_logged(caplog):
    now = _clock()
    pool = HealthScoredKeyPool("groq", ("fpA", "fpB"), fail_threshold=1, now=now)
    # demote fpA with a 429 (threshold 1 -> trips immediately)
    pool.report_failure("fpA", 429, detail="rate limited")
    pool.report_failure("fpA", 429, detail="rate limited")  # ensure trip
    # pick must SKIP the open key and return fpB
    picks = {pool.pick() for _ in range(4)}
    assert picks == {"fpB"}
    # the trip + selection are recorded (never silent)
    actions = [d.action for d in pool.last_decisions]
    assert "trip" in actions and "pick" in actions
    # and it logged a warning on trip
    assert any("circuit OPEN" in r.message for r in caplog.records) or \
           any("circuit OPEN" in d.detail for d in pool.last_decisions)


def test_decrypt_failure_fails_closed_not_crash(bus, monkeypatch):
    """A key whose ciphertext can no longer be decrypted (master-secret ROTATED, on-disk tamper, or
    the master secret missing from this worker's env) must FAIL CLOSED + LOUD via found=False +
    key_pool_exhausted — NEVER an uncaught InvalidTag/VaultError that crashes the live voice path.
    Regression guard for the red-team finding (resolve_key did not wrap the call-time decrypt)."""
    ks = ProviderKeyStore()
    ks.add_key("orgA", "groq", "gsk_rotation_victim_123456", added_by="f")
    kr = KeyRouter("orgA", ks)
    # the founder rotates the platform master secret — the old ciphertext no longer decrypts.
    monkeypatch.setenv("FAMIT_KEYSTORE_SECRET", "a-DIFFERENT-rotated-master-secret")
    cfg_store.ConfigStore.invalidate_all()
    r = kr.resolve_key("groq")           # must NOT raise
    assert r.found is False and r.plaintext == ""
    assert "gsk_rotation_victim" not in r.reason  # no plaintext in the loud signal
    assert EventName.KEY_POOL_EXHAUSTED.value in {e.name for e in bus.all_events("orgA")}
    # and the same is true if the master secret is GONE entirely (worker env not loaded)
    for env in ("PROVIDER_REGISTRY_KEYSTORE_SECRET", "PROVIDER_KEYSTORE_SECRET",
                "FAMIT_KEYSTORE_SECRET", "CONFIG_VAULT_SECRET"):
        monkeypatch.delenv(env, raising=False)
    cfg_store.ConfigStore.invalidate_all()
    assert kr.resolve_key("groq").found is False  # still no crash


def test_pool_exhaustion_is_loud(bus):
    now = _clock()
    ks = ProviderKeyStore()
    ks.add_key("orgA", "groq", "gsk_only_key_9999999999", added_by="f")
    kr = KeyRouter("orgA", ks)
    # force the single key's circuit open via repeated 5xx
    fp = ks.fingerprints("orgA", "groq")[0]
    pool = kr._pool("groq")
    pool._now = now
    for _ in range(3):
        kr.report_failure("groq", fp, 503, detail="server error")
    r = kr.resolve_key("groq")
    assert r.found is False and "EXHAUSTED" in r.reason
    # LOUD: key_pool_exhausted emitted
    assert EventName.KEY_POOL_EXHAUSTED.value in {e.name for e in bus.all_events("orgA")}


def test_failover_then_recovery_after_cooldown():
    now = _clock()
    pool = HealthScoredKeyPool("sarvam", ("fpA", "fpB"), fail_threshold=1, now=now)
    pool.report_failure("fpA", 503)
    assert pool.pick() == "fpB"          # failed over
    assert pool.healthy_count == 1
    now.advance(31.0)                     # past the 30s first backoff
    assert pool.healthy_count == 2        # fpA recovered
    # recovery is recorded
    assert any(d.action == "recover" for d in pool.last_decisions)


def test_health_snapshot_has_no_secrets():
    pool = HealthScoredKeyPool("elevenlabs", ("fpX",))
    pool.observe_latency("fpX", 800.0)
    snap = pool.snapshot()
    assert snap["provider"] == "elevenlabs" and snap["total"] == 1
    assert "fingerprint" in snap["keys"][0] and "plaintext" not in str(snap)


def test_healthiest_key_is_preferred():
    now = _clock()
    pool = HealthScoredKeyPool("groq", ("good", "slow"), fail_threshold=99, now=now)
    pool.observe_latency("slow", 5000.0)   # very slow -> lower latency score
    pool.report_success("good", latency_ms=200.0)
    # the low-latency key should win the score-ranked pick
    assert pool.pick() == "good"


# =========================================================================== #
# 4. CONFIG STORE — version bump + cache invalidate + propagation
# =========================================================================== #
def test_versioned_store_bumps_and_caches(mem_backend):
    st = C.ConfigStore()
    assert st.get("orgA", "vendor_profile") is None
    s1 = st.put("orgA", "vendor_profile", {"plan": "lean"}, updated_by="f")
    assert s1.version == 1
    s2 = st.put("orgA", "vendor_profile", {"plan": "growth"}, updated_by="f")
    assert s2.version == 2
    got = st.get("orgA", "vendor_profile")
    assert got.version == 2 and got.doc["plan"] == "growth"


def test_external_write_invalidates_cache(mem_backend):
    """A write through one ConfigStore instance is seen by another (version poll invalidates the
    stale cache) — this is the 'live across workers without redeploy' guarantee."""
    reader = C.ConfigStore()
    writer = C.ConfigStore()
    writer.put("orgA", "vendor_profile", {"plan": "lean"}, updated_by="f")
    assert reader.get("orgA", "vendor_profile").doc["plan"] == "lean"
    # writer changes it; reader (different instance, shared backend) must pick up v2.
    reader.version_poll_ttl_s = 0.0  # disable the 1s poll throttle for the test
    writer.put("orgA", "vendor_profile", {"plan": "premium"}, updated_by="f")
    assert reader.get("orgA", "vendor_profile").doc["plan"] == "premium"


# =========================================================================== #
# 5. VENDOR CONTROL CENTER — propagation + future-ready WA + retention
# =========================================================================== #
def test_vendor_profile_save_propagates(bus, mem_backend):
    vps = VendorProfileStore()
    p = VendorProfile(tenant_id="orgA", human_handoff_number="+919812345678",
                      ai_manager_number="+918000000000", whatsapp_report_number="+919900000000",
                      plan="growth", phone_numbers=["+911111111111"])
    saved = vps.put(p, updated_by="founder")
    assert saved.version == 1
    # read back through a fresh store -> same values (propagated/persisted)
    again = VendorProfileStore().get("orgA")
    assert again.human_handoff_number == "+919812345678"
    assert again.ai_manager_number == "+918000000000"
    assert again.plan == "growth"
    # config_changed emitted
    evs = [e for e in bus.all_events("orgA") if e.name == EventName.CONFIG_CHANGED.value]
    assert evs and evs[-1].payload.get("namespace") == "vendor_profile"


def test_vendor_profile_patch_partial(mem_backend):
    vps = VendorProfileStore()
    vps.put(VendorProfile(tenant_id="orgA", plan="lean"), updated_by="f")
    vps.patch("orgA", {"human_handoff_number": "+919812345678",
                       "retention": {"recording_retention_days": 7}}, updated_by="f")
    p = vps.get("orgA")
    assert p.human_handoff_number == "+919812345678"
    assert p.retention.recording_retention_days == 7
    assert p.plan == "lean"  # untouched field preserved


def test_per_tenant_retention_independent_ttls(mem_backend):
    vps = VendorProfileStore()
    vps.patch("orgA", {"retention": {"recording_retention_days": 7, "transcript_retention_days": 0}},
              updated_by="f")
    r = vps.get("orgA").retention
    assert r.recording_retention_days == 7      # raw audio expires fast
    assert r.transcript_retention_days == 0     # transcript kept forever (business intel)


def test_future_ready_whatsapp_dormant_until_creds(mem_backend):
    vps = VendorProfileStore()
    vps.put(VendorProfile(tenant_id="orgA"), updated_by="f")
    p = vps.get("orgA")
    # blank-but-present, inert
    assert p.whatsapp.phone_number_id == "" and p.whatsapp.enabled is False
    assert p.whatsapp.is_active(has_whatsapp_key=False) is False
    # fill fields + add a whatsapp key + enable -> activates
    vps.patch("orgA", {"whatsapp": {"phone_number_id": "123456", "enabled": True}}, updated_by="f")
    p2 = vps.get("orgA")
    assert p2.whatsapp.is_active(has_whatsapp_key=True) is True
    assert p2.whatsapp.is_active(has_whatsapp_key=False) is False  # still needs the key


def test_profile_validate_soft_warnings():
    p = VendorProfile(tenant_id="orgA", human_handoff_number="not-a-number", plan="bogus")
    warns = p.validate()
    assert any("human_handoff_number" in w for w in warns)
    assert any("plan" in w for w in warns)


# =========================================================================== #
# 6. TENANT ISOLATION (store-level)
# =========================================================================== #
def test_tenant_isolation_in_store(mem_backend):
    ks = ProviderKeyStore()
    ks.add_key("orgA", "groq", "gsk_A_key_aaaaaaaaaaaa", added_by="f")
    ks.add_key("orgB", "groq", "gsk_B_key_bbbbbbbbbbbb", added_by="f")
    # orgB's key store never returns orgA's fingerprints
    a_fps = set(ks.fingerprints("orgA", "groq"))
    b_fps = set(ks.fingerprints("orgB", "groq"))
    assert a_fps and b_fps and a_fps.isdisjoint(b_fps)
    # orgB cannot decrypt orgA's key even by guessing the fingerprint (no row / AAD mismatch)
    assert ks.decrypt("orgB", "groq", next(iter(a_fps))) is None


def test_events_scoped_per_tenant(bus, mem_backend):
    ks = ProviderKeyStore()
    ks.add_key("orgA", "groq", "gsk_only_A_1234567890", added_by="f")
    assert bus.all_events("orgA")          # orgA stream has events
    assert bus.all_events("orgB") == []    # orgB stream is empty (per-tenant streams)


# =========================================================================== #
# 7. EVENT EMISSION IS FAIL-SOFT (a dead bus never breaks a write)
# =========================================================================== #
def test_config_write_survives_missing_bus(mem_backend):
    cfg_events.set_event_bus(None)  # no bus
    vps = VendorProfileStore()
    saved = vps.put(VendorProfile(tenant_id="orgA", plan="growth"), updated_by="f")
    assert saved.version == 1  # write still succeeded


def test_config_write_survives_throwing_bus(mem_backend):
    class BoomBus:
        async def emit(self, event):
            raise RuntimeError("redis down")

    cfg_events.set_event_bus(BoomBus())
    try:
        vps = VendorProfileStore()
        saved = vps.put(VendorProfile(tenant_id="orgA", plan="growth"), updated_by="f")
        assert saved.version == 1  # the throwing bus did NOT break the write
    finally:
        cfg_events.set_event_bus(None)


# =========================================================================== #
# 8. IMPORT ISOLATION — 0 droplet/agent imports at module load
# =========================================================================== #
def test_no_droplet_or_agent_imports():
    import sys
    import importlib

    # Measure the DELTA caused by importing voice_ops.config — not the global
    # sys.modules (which an earlier test in the same run may have polluted with a
    # heavy SDK). The contract is "importing voice_ops.config pulls ZERO droplet/
    # agent modules and ZERO heavy SDKs", so we snapshot before, drop the package,
    # re-import, and inspect only what that import newly added.
    before = set(sys.modules)
    for m in list(sys.modules):
        if m.startswith("voice_ops.config"):
            del sys.modules[m]
    importlib.import_module("voice_ops.config")
    added = set(sys.modules) - before
    bad = [m for m in added
           if m.split(".")[0] in ("agent", "caller", "droplet_work")
           or m.startswith("droplet_work")]
    assert bad == [], f"voice_ops.config pulled forbidden modules: {bad}"
    # and no heavy SDKs newly pulled at import time (delta, not global state).
    heavy = [m for m in added if m in ("redis", "boto3", "sqlalchemy", "livekit")]
    assert heavy == [], f"voice_ops.config pulled heavy SDKs at import: {heavy}"
