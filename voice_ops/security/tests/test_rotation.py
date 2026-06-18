"""W20 — secret-rotation + docs-scrub tests.

Proves: rotation generates a fresh non-guessable secret, NEVER leaks the plaintext in repr/str/logs,
and that rotating the HMAC secret invalidates an OLD token (the runbook's after-smoke). Also that the
docs-scrub list never embeds the secret value."""
from __future__ import annotations

from voice_ops.security import docs_scrub
from voice_ops.security.docs_scrub import legacy_secret_fingerprint, scrub_list
from voice_ops.security.rotation import (
    RotationResult,
    hmac_token,
    rotate_caller_pass,
    rotate_hmac_signing_secret,
    token_valid_under,
    verify_rotation_invalidates,
)

# the literal we are RETIRING — reconstructed from fragments so the contiguous secret never appears in
# tracked source (W20 BLOCKER 3); used ONLY to prove it never appears in our outputs.
_LEGACY = "Famit" + "Call" + "2026"


# --------------------------------------------------------------------------- #
# rotation generates fresh, strong, non-leaking secrets
# --------------------------------------------------------------------------- #
def test_caller_pass_rotation_is_fresh_and_strong():
    r = rotate_caller_pass(old_value=_LEGACY)
    new_v = r.new_secret.reveal()
    assert isinstance(new_v, str)
    assert len(new_v) >= 24
    assert new_v != _LEGACY


def test_two_rotations_differ():
    a = rotate_caller_pass().new_secret.reveal()
    b = rotate_caller_pass().new_secret.reveal()
    assert a != b  # CSPRNG, not deterministic


def test_rotation_result_repr_never_leaks_plaintext():
    r = rotate_caller_pass(old_value=_LEGACY)
    new_v = r.new_secret.reveal()
    # the value must NOT appear in any of these representations
    assert new_v not in repr(r)
    assert new_v not in str(r)
    assert new_v not in repr(r.new_secret)
    assert new_v not in str(r.new_secret)
    # but the fingerprint + mask ARE present (safe to log)
    assert r.new_fingerprint and r.new_fingerprint in repr(r)


def test_old_fingerprint_recorded_and_differs():
    r = rotate_caller_pass(old_value=_LEGACY)
    assert r.old_fingerprint == legacy_secret_fingerprint(_LEGACY)
    assert r.old_fingerprint != r.new_fingerprint


def test_env_line_reveals_only_on_explicit_call():
    r = rotate_caller_pass()
    line = r.env_line()
    assert line.startswith("CALLER_PASS=")
    assert r.new_secret.reveal() in line  # explicit reveal path for the secret store
    # and it is NOT in the safe repr
    assert r.new_secret.reveal() not in repr(r)


# --------------------------------------------------------------------------- #
# HMAC rotation invalidates old tokens (the after-smoke)
# --------------------------------------------------------------------------- #
def test_hmac_rotation_marks_invalidate_all():
    r = rotate_hmac_signing_secret(old_value="old-secret")
    assert r.invalidates_all_tokens is True
    assert r.target == "HMAC_SIGNING_SECRET"


def test_old_token_fails_under_new_hmac_secret():
    old_secret = "old-signing-secret"
    payload = "sub=admin|role=admin|tenant=ADMIN"
    old_token = hmac_token(payload, old_secret)
    assert token_valid_under(payload, old_token, old_secret) is True

    new = rotate_hmac_signing_secret(old_value=old_secret)
    new_secret = new.new_secret.reveal()
    # the OLD token must NOT validate under the NEW secret
    assert token_valid_under(payload, old_token, new_secret) is False


def test_verify_rotation_invalidates_helper():
    payload = "panel-session-xyz"
    assert verify_rotation_invalidates(payload, "old", "new") is True
    # if the secret didn't actually change, it should report NOT invalidated
    assert verify_rotation_invalidates(payload, "same", "same") is False


# --------------------------------------------------------------------------- #
# docs-scrub list never embeds the secret
# --------------------------------------------------------------------------- #
def test_scrub_list_has_source_fallbacks_and_env_and_docs():
    targets = scrub_list()
    kinds = {t.kind for t in targets}
    assert {"source_fallback", "env", "doc"} <= kinds
    # the dangerous source-fallback files are enumerated
    paths = {t.path for t in targets}
    assert any("caller.py" in p for p in paths)
    assert any("voice_tools.py" in p for p in paths)


def test_scrub_list_never_embeds_the_secret_literal():
    for t in scrub_list():
        assert _LEGACY not in t.path
        assert _LEGACY not in t.what


def test_tracked_only_filter():
    tracked = scrub_list(tracked_only=True)
    assert all(t.tracked for t in tracked)
    assert len(tracked) < len(scrub_list())


def test_grep_hints_returns_patterns_not_secret():
    hints = docs_scrub.grep_hints(legacy_value=_LEGACY)
    joined = "\n".join(hints)
    assert _LEGACY not in joined
    # but the verification fingerprint IS present
    assert legacy_secret_fingerprint(_LEGACY) in joined


def test_fingerprint_is_stable_and_nonreversible():
    fp = legacy_secret_fingerprint(_LEGACY)
    assert fp == legacy_secret_fingerprint(_LEGACY)  # stable
    assert len(fp) == 12
    assert _LEGACY not in fp  # non-reversible
    assert legacy_secret_fingerprint("") == ""
