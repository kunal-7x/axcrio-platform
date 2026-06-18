"""W23 — OAuth/WABA refresh-token vault tests (mock master secret).

Proves: OAuth tokens are AAD AES-GCM encrypted at rest (reusing the config vault), the plaintext is
NEVER in the record/repr/to_record (so it never lands in var/*.json), a cross-tenant blob fails to
decrypt (fail-closed), and an empty token is refused. Uses an env-provided keystore master so the
test is hermetic (no real KMS, no real secret)."""
from __future__ import annotations

import json

import pytest

from voice_ops.security.keys.oauth_vault import (
    OAuthVaultError,
    VaultedToken,
    open_oauth_token,
    open_record,
    seal_oauth_token,
)

# a refresh token shaped like a Meta/WABA one — fabricated, never a real secret.
_TOKEN = "EAAGtest-refresh-zzz-0123456789-not-a-real-secret"


@pytest.fixture(autouse=True)
def _master(monkeypatch):
    # the config vault reads these envs; set one so derivation works without a real keystore.
    monkeypatch.setenv("CONFIG_VAULT_SECRET", "unit-test-keystore-master-secret-do-not-ship")
    yield


def test_seal_roundtrips():
    rec = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN, label="WABA prod")
    assert isinstance(rec, VaultedToken)
    plain = open_oauth_token("TENANT-A", "whatsapp", rec.ciphertext)
    assert plain == _TOKEN


def test_record_roundtrips_via_to_record():
    rec = seal_oauth_token("TENANT-A", "googlecal", _TOKEN)
    r = rec.to_record()
    assert open_record("TENANT-A", r) == _TOKEN


def test_plaintext_never_in_record_or_repr():
    rec = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN, label="prod")
    blob = repr(rec) + "||" + json.dumps(rec.to_record())
    # the FULL token must not appear anywhere persistable/loggable
    assert _TOKEN not in blob
    # but the masked + fingerprint forms DO exist (safe references)
    assert rec.fingerprint and rec.fingerprint in repr(rec)
    assert rec.masked and rec.masked != _TOKEN


def test_ciphertext_is_off_repr():
    rec = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN)
    assert "ciphertext" not in repr(rec)  # the bytes field is repr=False


def test_cross_tenant_decrypt_fails_closed():
    rec = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN)
    with pytest.raises(OAuthVaultError):
        open_oauth_token("TENANT-B", "whatsapp", rec.ciphertext)


def test_cross_provider_decrypt_fails_closed():
    rec = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN)
    with pytest.raises(OAuthVaultError):
        open_oauth_token("TENANT-A", "googlecal", rec.ciphertext)


def test_oauth_aad_is_namespaced_away_from_api_keys():
    """An OAuth token's AAD provider field is 'oauth:<provider>', so it can't be opened as if it were
    a provider API key for the same provider string."""
    rec = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN)
    assert rec.key_aad == "TENANT-A|oauth:whatsapp|1"


def test_empty_token_refused():
    with pytest.raises(OAuthVaultError):
        seal_oauth_token("TENANT-A", "whatsapp", "")


def test_missing_tenant_or_provider_refused():
    with pytest.raises(OAuthVaultError):
        seal_oauth_token("", "whatsapp", _TOKEN)
    with pytest.raises(OAuthVaultError):
        seal_oauth_token("TENANT-A", "", _TOKEN)


def test_two_seals_differ_by_nonce():
    a = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN)
    b = seal_oauth_token("TENANT-A", "whatsapp", _TOKEN)
    # same plaintext, random GCM nonce -> different ciphertext, SAME fingerprint (dedupe key)
    assert a.ciphertext != b.ciphertext
    assert a.fingerprint == b.fingerprint


def test_no_plaintext_filesystem_write():
    """Regression intent: sealing returns an in-memory record only; this module performs NO filesystem
    write of the token. Guard against a future edit adding a `var/*.json` plaintext path by AST-walking
    for file-write calls (open(...)/Path.write_text/json.dump) — not naive substring matching, which
    would false-positive on the docstring rationale + the `open_oauth_token` function name."""
    import ast
    import inspect

    from voice_ops.security.keys import oauth_vault

    tree = ast.parse(inspect.getsource(oauth_vault))
    forbidden_funcs = {"open"}                          # builtin file open
    forbidden_attrs = {"write_text", "write_bytes", "dump", "dumps_to_file"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in forbidden_funcs:
                offenders.append(f.id)
            if isinstance(f, ast.Attribute) and f.attr in forbidden_attrs:
                offenders.append(f.attr)
    assert offenders == [], f"oauth_vault must not write the token to disk; found calls: {offenders}"
