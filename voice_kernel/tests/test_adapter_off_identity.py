"""THE UNIT-LEVEL EARNER GATE.

When KERNEL_ENABLED is OFF for a direction, `instructions_provider` MUST return
the EXACT legacy string, byte-for-byte. The red-team requires this be proven
against the ACTUAL production prompt builder (droplet_work/prompt.py
build_system_prompt), not a stubbed legacy_render — otherwise a mocked stub
trivially passes and the gate proves nothing.

So this test imports the REAL build_system_prompt and runs its output through
the adapter with cfg=OFF, across a matrix of fields, asserting byte-equality.

We NEVER import droplet_work.agent. We load prompt.py as an isolated file
(conftest.load_legacy_prompt_module) which imports only stdlib.
"""
from __future__ import annotations

import pytest

from voice_kernel import KernelConfig, instructions_provider
from voice_kernel.contracts import CallContext
from voice_kernel.packet import PacketMeta

from .conftest import load_legacy_prompt_module

_legacy = load_legacy_prompt_module()
_HAS_LEGACY = _legacy is not None

pytestmark = pytest.mark.skipif(
    not _HAS_LEGACY, reason="droplet_work/prompt.py not present in this checkout"
)

OFF = KernelConfig()  # all flags default False -> kernel OFF for every direction


def _meta(direction: str = "outbound") -> PacketMeta:
    return PacketMeta(
        tenant_id="t1", campaign_id="c1", call_id="call1", room="room1",
        direction=direction,
    )


def _matrix():
    """Field variants that exercise the legacy builder's branches."""
    base = dict(_legacy.GODREJ_FIELDS)
    variant = dict(base, price_offer="SPECIAL ₹99 today only", agent_name="Anjali")
    recap_fields = dict(base)
    minimal = {"agent_name": "Riya", "company_name": "Famit", "product_name": "X"}
    empty: dict = {}
    return {
        "default_godrej": base,
        "variant_override": variant,
        "recap_present": recap_fields,
        "minimal": minimal,
        "empty": empty,
    }


@pytest.mark.parametrize("name,fields", list(_matrix().items()))
@pytest.mark.parametrize("direction", ["outbound", "inbound"])
def test_off_is_byte_identical_to_real_legacy(name, fields, direction):
    """OFF adapter output == the REAL build_system_prompt(fields) output, byte
    for byte, for every field variant and both directions."""
    legacy_str = _legacy.build_system_prompt(fields)

    # the agent passes its OWN existing output as legacy_render (zero-arg).
    def legacy_render() -> str:
        return _legacy.build_system_prompt(fields)

    ctx = CallContext(meta=_meta(direction), fields=fields)
    out = instructions_provider(legacy_render, ctx, cfg=OFF)

    assert out == legacy_str, f"OFF must be byte-identical to legacy ({name}/{direction})"
    assert isinstance(out, str)
    assert len(out) == len(legacy_str)


def test_off_does_not_invoke_kernel(monkeypatch):
    """With OFF, the kernel assembly path must not run at all — legacy_render is
    the only thing called. We prove it by making the kernel raise if touched."""
    import voice_kernel.adapter as adapter_mod

    def boom(*a, **k):
        raise AssertionError("kernel build_kernel must NOT be called when OFF")

    monkeypatch.setattr(adapter_mod, "build_kernel", boom)
    called = {"n": 0}

    def legacy_render() -> str:
        called["n"] += 1
        return "LEGACY-EXACT"

    ctx = CallContext(meta=_meta("outbound"), fields={})
    out = instructions_provider(legacy_render, ctx, cfg=OFF)
    assert out == "LEGACY-EXACT"
    assert called["n"] == 1


def test_on_failure_falls_back_to_legacy_not_silent(monkeypatch, caplog):
    """When ON but the kernel raises, the adapter returns the legacy string AND
    logs a warning (never silently fails — LEARNINGS §1)."""
    import logging
    import voice_kernel.adapter as adapter_mod

    def boom(*a, **k):
        raise RuntimeError("kernel exploded")

    monkeypatch.setattr(adapter_mod, "build_kernel", boom)
    on = KernelConfig(enabled=True)

    def legacy_render() -> str:
        return "SAFE-LEGACY-FALLBACK"

    ctx = CallContext(meta=_meta("outbound"), fields={})
    with caplog.at_level(logging.WARNING):
        out = instructions_provider(legacy_render, ctx, cfg=on)
    assert out == "SAFE-LEGACY-FALLBACK"
    assert any("falling back to legacy" in r.message for r in caplog.records)
