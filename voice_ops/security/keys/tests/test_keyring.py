"""W23 — purpose-separated keyring tests.

THE LOAD-BEARING ASSERTION: a key derived for ONE purpose cannot sign/verify for ANOTHER. A
JWT-access key can't forge a step-up token. This is the whole point of W23 and is asserted from
several angles below."""
from __future__ import annotations

import pytest

from voice_ops.security.keys.keyring import KeyHandle, KeyManagerError, Keyring
from voice_ops.security.keys.purpose import COLLIDING_TODAY, KeyPurpose, all_purposes

_MASTER = b"unit-test-master-secret-0123456789abcdef"


def _kr(master: bytes = _MASTER) -> Keyring:
    return Keyring(get_master=lambda: master)


# --------------------------------------------------------------------------- #
# purpose separation — the W23 containment guarantee
# --------------------------------------------------------------------------- #
def test_every_purpose_derives_a_distinct_key():
    kr = _kr()
    fps = {p: kr.fingerprint(p) for p in all_purposes()}
    # all 6 fingerprints are unique -> 6 distinct keys from ONE master
    assert len(set(fps.values())) == len(all_purposes())


def test_jwt_key_cannot_forge_a_step_up_token():
    """The founder's exact requirement: 'a JWT key can't forge a step-up token'."""
    kr = _kr()
    payload = "sub=T1|scope=spend|exp=999"
    mac_under_access = kr.sign(KeyPurpose.JWT_ACCESS, payload)
    # the SAME payload, MAC made with the access key, must NOT verify as a step-up token
    assert kr.verify(KeyPurpose.STEP_UP, payload, mac_under_access) is False
    # and the reverse
    mac_under_stepup = kr.sign(KeyPurpose.STEP_UP, payload)
    assert kr.verify(KeyPurpose.JWT_ACCESS, payload, mac_under_stepup) is False


def test_same_purpose_roundtrips():
    kr = _kr()
    for p in all_purposes():
        mac = kr.sign(p, "hello-payload")
        assert kr.verify(p, "hello-payload", mac) is True


def test_no_two_purposes_share_a_mac():
    kr = _kr()
    payload = "x"
    macs = {p: kr.sign(p, payload) for p in all_purposes()}
    # every purpose produces a different MAC for the same payload
    assert len(set(macs.values())) == len(all_purposes())


def test_tampered_payload_fails_verify():
    kr = _kr()
    mac = kr.sign(KeyPurpose.STEP_UP, "amount=100")
    assert kr.verify(KeyPurpose.STEP_UP, "amount=999", mac) is False


def test_empty_mac_fails_closed():
    kr = _kr()
    assert kr.verify(KeyPurpose.JWT_ACCESS, "p", "") is False
    assert kr.verify(KeyPurpose.JWT_ACCESS, "p", None) is False  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# version separation -> per-purpose rotation without collateral
# --------------------------------------------------------------------------- #
def test_version_bump_changes_only_that_purposes_key():
    kr = _kr()
    before = {p: kr.fingerprint(p, version=1) for p in all_purposes()}
    # bump STEP_UP to v2
    su_v1, su_v2 = kr.fingerprint(KeyPurpose.STEP_UP, version=1), kr.fingerprint(KeyPurpose.STEP_UP, version=2)
    assert su_v1 != su_v2  # the rotated key changed
    # every OTHER purpose's v1 key is unchanged (no collateral logout)
    for p in all_purposes():
        if p is KeyPurpose.STEP_UP:
            continue
        assert kr.fingerprint(p, version=1) == before[p]


def test_token_at_old_version_fails_at_new_version():
    kr = _kr()
    mac_v1 = kr.sign(KeyPurpose.JWT_ACCESS, "p", version=1)
    assert kr.verify(KeyPurpose.JWT_ACCESS, "p", mac_v1, version=1) is True
    assert kr.verify(KeyPurpose.JWT_ACCESS, "p", mac_v1, version=2) is False


# --------------------------------------------------------------------------- #
# determinism + master dependence
# --------------------------------------------------------------------------- #
def test_derivation_is_deterministic_across_instances():
    a = _kr().fingerprint(KeyPurpose.SERVICE)
    b = _kr().fingerprint(KeyPurpose.SERVICE)
    assert a == b  # same master -> same key (survives restart)


def test_different_master_yields_different_keys():
    a = _kr(b"master-A-xxxxxxxxxxxxxxxxxxxxxxxxxxxx").fingerprint(KeyPurpose.STEP_UP)
    b = _kr(b"master-B-yyyyyyyyyyyyyyyyyyyyyyyyyyyy").fingerprint(KeyPurpose.STEP_UP)
    assert a != b


def test_missing_master_fails_closed_no_weak_key(monkeypatch):
    # no env set, default master resolver -> KeyManagerError, never an empty/weak key
    for env in ("KEYRING_MASTER_SECRET", "FAMIT_SIGNING_MASTER",
                "PROVIDER_REGISTRY_KEYSTORE_SECRET", "FAMIT_KEYSTORE_SECRET"):
        monkeypatch.delenv(env, raising=False)
    kr = Keyring()  # uses DEFAULT_GET_MASTER
    with pytest.raises(KeyManagerError):
        kr.sign(KeyPurpose.JWT_ACCESS, "p")


def test_empty_master_fails_closed():
    kr = Keyring(get_master=lambda: b"")
    with pytest.raises(KeyManagerError):
        kr.fingerprint(KeyPurpose.JWT_ACCESS)


# --------------------------------------------------------------------------- #
# key material never leaks
# --------------------------------------------------------------------------- #
def test_handle_repr_carries_no_key_bytes():
    kr = _kr()
    h = kr.handle(KeyPurpose.REVEAL_STEP_UP)
    assert isinstance(h, KeyHandle)
    r = repr(h)
    # the raw master must not appear anywhere in the safe-to-log handle
    assert _MASTER.decode("utf-8") not in r
    assert h.fingerprint in r


def test_keyring_exposes_no_raw_key_method():
    """There is intentionally NO public method that returns derived key bytes."""
    kr = _kr()
    public = [m for m in dir(kr) if not m.startswith("_")]
    # only secret-free surface
    assert set(public) == {"sign", "verify", "handle", "fingerprint", "legacy_compat_key_fingerprint"}


def test_colliding_today_is_a_subset_of_all_purposes():
    assert set(COLLIDING_TODAY) <= set(all_purposes())
    # the four families that share var/secret today
    assert KeyPurpose.JWT_ACCESS in COLLIDING_TODAY
    assert KeyPurpose.STEP_UP in COLLIDING_TODAY
    assert KeyPurpose.LEGACY_HMAC in COLLIDING_TODAY
    assert KeyPurpose.REVEAL_STEP_UP in COLLIDING_TODAY
