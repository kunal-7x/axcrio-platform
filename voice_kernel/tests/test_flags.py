"""KernelConfig flag tests: default OFF for EVERY direction with no env set;
scoped inbound flag does not enable outbound; shadow never enables replacement."""
from __future__ import annotations

import pytest

from voice_kernel.config import KernelConfig
from voice_kernel.errors import ConfigError

_FLAG_VARS = ["KERNEL_ENABLED", "KERNEL_INBOUND", "KERNEL_OUTBOUND_SHADOW", "KERNEL_MAX_TOTAL_TOKENS"]


@pytest.fixture
def clean_env(monkeypatch):
    for v in _FLAG_VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_unset_env_is_off_for_every_direction(clean_env):
    cfg = KernelConfig.from_env()
    assert cfg.enabled is False
    assert cfg.inbound is False
    assert cfg.outbound_shadow is False
    for direction in ("outbound", "inbound", "", "OUTBOUND", None):
        assert cfg.enabled_for(direction) is False


def test_inbound_flag_enables_inbound_only(clean_env):
    clean_env.setenv("KERNEL_INBOUND", "1")
    cfg = KernelConfig.from_env()
    assert cfg.enabled_for("inbound") is True
    assert cfg.enabled_for("outbound") is False  # earner stays OFF


def test_master_flag_enables_both(clean_env):
    clean_env.setenv("KERNEL_ENABLED", "true")
    cfg = KernelConfig.from_env()
    assert cfg.enabled_for("inbound") is True
    assert cfg.enabled_for("outbound") is True


def test_shadow_never_enables_outbound_replacement(clean_env):
    clean_env.setenv("KERNEL_OUTBOUND_SHADOW", "1")
    cfg = KernelConfig.from_env()
    assert cfg.shadow_active() is True
    assert cfg.enabled_for("outbound") is False  # shadow only computes+logs


def test_codebase_native_truthy_values(clean_env):
    for val in ("1", "true", "True"):
        clean_env.setenv("KERNEL_ENABLED", val)
        assert KernelConfig.from_env().enabled is True
    for val in ("0", "false", "False", "", "yes", "no"):
        clean_env.setenv("KERNEL_ENABLED", val)
        assert KernelConfig.from_env().enabled is False


def test_invalid_budget_raises(clean_env):
    clean_env.setenv("KERNEL_MAX_TOTAL_TOKENS", "0")
    with pytest.raises(ConfigError):
        KernelConfig.from_env()


def test_direct_construction_default_off():
    assert KernelConfig().enabled_for("outbound") is False
    assert KernelConfig().enabled_for("inbound") is False
