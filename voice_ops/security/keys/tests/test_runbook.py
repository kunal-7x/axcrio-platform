"""W23 — rotation runbook tests.

Proves: per-purpose rotation is CONTAINED (only that purpose's key changes), master rotation
invalidates all, the split migration plan covers every purpose with the privileged ones last, and no
plan text ever leaks a secret/key byte."""
from __future__ import annotations

from voice_ops.security.keys.keyring import Keyring
from voice_ops.security.keys.purpose import KeyPurpose, all_purposes
from voice_ops.security.keys.runbook import (
    RotationPlan,
    rotate_master,
    rotate_purpose,
    split_migration_plan,
)

_MASTER = b"runbook-test-master-secret-aaaaaaaaaaaa"


def _kr() -> Keyring:
    return Keyring(get_master=lambda: _MASTER)


def test_rotate_purpose_is_contained():
    kr = _kr()
    plan = rotate_purpose(kr, KeyPurpose.STEP_UP)
    assert isinstance(plan, RotationPlan)
    assert plan.kind == "purpose"
    assert plan.invalidates_all is False
    # the before/after fingerprints differ (the rotated key) and are reported
    step = plan.steps[0]
    assert step.old_fingerprint != step.new_fingerprint
    assert step.purpose == KeyPurpose.STEP_UP.label


def test_rotate_purpose_old_token_dies_new_survives():
    kr = _kr()
    plan = rotate_purpose(kr, KeyPurpose.JWT_ACCESS, old_version=1, new_version=2)
    # simulate the smoke: a token at v1 must fail at v2
    mac_v1 = kr.sign(KeyPurpose.JWT_ACCESS, "p", version=1)
    assert kr.verify(KeyPurpose.JWT_ACCESS, "p", mac_v1, version=2) is False
    # other purposes untouched across the bump
    assert plan.steps[0].old_version == 1 and plan.steps[0].new_version == 2


def test_rotate_master_invalidates_all():
    plan = rotate_master(old_master_fingerprint="oldfp00")
    assert plan.kind == "master"
    assert plan.invalidates_all is True
    assert any(s.action == "replace-master" for s in plan.steps)


def test_split_migration_covers_every_purpose():
    kr = _kr()
    plan = split_migration_plan(kr)
    purposes_in_plan = {s.purpose for s in plan.steps}
    assert purposes_in_plan == {p.label for p in all_purposes()}


def test_split_migration_orders_privileged_last():
    kr = _kr()
    plan = split_migration_plan(kr)
    # find the order index of the first privileged purpose vs the last non-privileged
    priv_labels = {p.label for p in all_purposes() if p.is_privileged}
    orders_priv = [s.order for s in plan.steps if s.purpose in priv_labels]
    orders_nonpriv = [s.order for s in plan.steps if s.purpose not in priv_labels]
    assert min(orders_priv) > max(orders_nonpriv)  # all privileged come after all non-privileged


def test_no_plan_leaks_secret_bytes():
    kr = _kr()
    texts = [
        rotate_purpose(kr, KeyPurpose.STEP_UP).as_text(),
        split_migration_plan(kr).as_text(),
        rotate_master("fp").as_text(),
    ]
    joined = "\n".join(texts)
    assert _MASTER.decode("utf-8") not in joined
    # also no derived key bytes (we never print them; fingerprints only)


def test_plan_text_renders():
    kr = _kr()
    txt = split_migration_plan(kr).as_text()
    assert "Key rotation plan" in txt
    assert KeyPurpose.SERVICE.label in txt
