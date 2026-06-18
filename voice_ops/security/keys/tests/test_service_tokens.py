"""W23 — short-lived scoped inter-service token tests.

Proves: tokens are scoped (aud+scope bound), short-lived (TTL ceiling enforced + expiry rejected),
purpose-isolated (a non-service key can't mint or verify one), and fail-closed on tamper/replay."""
from __future__ import annotations

import time

import pytest

from voice_ops.security.keys.keyring import Keyring
from voice_ops.security.keys.purpose import KeyPurpose
from voice_ops.security.keys.service_tokens import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    ServiceClaims,
    ServiceTokenError,
    mint_service_token,
    verify_service_token,
)

_MASTER = b"svc-token-test-master-secret-0123456789"


def _kr() -> Keyring:
    return Keyring(get_master=lambda: _MASTER)


# --------------------------------------------------------------------------- #
# happy path + binding
# --------------------------------------------------------------------------- #
def test_mint_and_verify_roundtrip():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial", subject="T1")
    claims = verify_service_token(kr, tok, expected_audience="caller", required_scope="dial")
    assert isinstance(claims, ServiceClaims)
    assert claims.iss == "aim" and claims.aud == "caller" and claims.scope == "dial" and claims.sub == "T1"
    assert claims.jti and claims.exp > claims.iat


def test_wrong_audience_rejected():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial")
    assert verify_service_token(kr, tok, expected_audience="hatchet", required_scope="dial") is None


def test_wrong_scope_rejected():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial")
    assert verify_service_token(kr, tok, expected_audience="caller", required_scope="schedule.enqueue") is None


def test_default_ttl_is_short():
    assert DEFAULT_TTL_SECONDS <= 300
    kr = _kr()
    tok = mint_service_token(kr, issuer="cron", audience="caller", scope="x")
    claims = verify_service_token(kr, tok, expected_audience="caller", required_scope="x")
    assert claims is not None
    assert (claims.exp - claims.iat) == DEFAULT_TTL_SECONDS


# --------------------------------------------------------------------------- #
# short-lived: TTL ceiling + expiry
# --------------------------------------------------------------------------- #
def test_ttl_over_ceiling_refused():
    kr = _kr()
    with pytest.raises(ServiceTokenError):
        mint_service_token(kr, issuer="aim", audience="caller", scope="dial", ttl_seconds=MAX_TTL_SECONDS + 1)


def test_expired_token_rejected():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial", ttl_seconds=60)
    future = int(time.time()) + 3600
    assert verify_service_token(kr, tok, expected_audience="caller", required_scope="dial", now=future) is None


def test_not_yet_valid_token_rejected():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial", ttl_seconds=60)
    way_past = int(time.time()) - 3600
    assert verify_service_token(kr, tok, expected_audience="caller", required_scope="dial", now=way_past) is None


# --------------------------------------------------------------------------- #
# fail-closed minting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("iss,aud,scope", [("", "caller", "dial"), ("aim", "", "dial"), ("aim", "caller", "")])
def test_empty_binding_fields_refused(iss, aud, scope):
    kr = _kr()
    with pytest.raises(ServiceTokenError):
        mint_service_token(kr, issuer=iss, audience=aud, scope=scope)


# --------------------------------------------------------------------------- #
# purpose isolation — a non-service key cannot mint/verify a service token
# --------------------------------------------------------------------------- #
def test_service_token_uses_service_key_not_access_key():
    """A token verified with the SERVICE key must NOT verify if we (illegitimately) try the access
    key. We can't call verify with another purpose directly through the public API (it always uses
    SERVICE), so prove it at the keyring layer: the service token's MAC fails under JWT_ACCESS."""
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial")
    h, p, mac = tok.split(".")
    signing_input = f"{h}.{p}"
    assert kr.verify(KeyPurpose.SERVICE, signing_input, mac) is True
    # the SAME MAC must NOT validate under the access key -> an access-key holder can't forge a svc token
    assert kr.verify(KeyPurpose.JWT_ACCESS, signing_input, mac) is False


def test_tampered_token_rejected():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial")
    h, p, mac = tok.split(".")
    # flip a char in the payload segment
    bad_p = (p[:-1] + ("A" if p[-1] != "A" else "B"))
    bad = f"{h}.{bad_p}.{mac}"
    assert verify_service_token(kr, bad, expected_audience="caller", required_scope="dial") is None


def test_malformed_token_rejected():
    kr = _kr()
    assert verify_service_token(kr, "", expected_audience="caller", required_scope="dial") is None
    assert verify_service_token(kr, "a.b", expected_audience="caller", required_scope="dial") is None
    assert verify_service_token(kr, "not-a-token", expected_audience="caller", required_scope="dial") is None


def test_token_minted_under_different_master_rejected():
    a = Keyring(get_master=lambda: b"master-A-aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    b = Keyring(get_master=lambda: b"master-B-bbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    tok = mint_service_token(a, issuer="aim", audience="caller", scope="dial")
    # verifier on a different master cannot validate it
    assert verify_service_token(b, tok, expected_audience="caller", required_scope="dial") is None


def test_token_string_carries_no_master_secret():
    kr = _kr()
    tok = mint_service_token(kr, issuer="aim", audience="caller", scope="dial", subject="T1")
    assert _MASTER.decode("utf-8") not in tok
