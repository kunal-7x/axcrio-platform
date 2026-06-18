"""W8 EARNER GATE: the event backbone is purely ADDITIVE and INERT when OFF.

Two proofs:

1. ZERO droplet/agent imports — the entire voice_kernel.events package and its
   transitive imports never touch droplet_work, agent.py, caller.py, or
   aim_voice_agent.py. (The package is disjoint by construction; this asserts it.)

2. FLAG-OFF BYTE-IDENTITY 12/12 — with EVENTBUS_ENABLED OFF (default), assembling
   the OFF prompt is byte-for-byte identical whether or not an EventBus is
   registered on the kernel. Registering RedisEventBus/InMemoryEventBus must NOT
   perturb the OFF assembly output (the bus is wired at a LATER seam, never on
   the OFF assembly path). 6 field variants x 2 directions = 12 cases.
"""
from __future__ import annotations

import sys

import pytest

from voice_kernel import KernelConfig, instructions_provider
from voice_kernel.contracts import CallContext
from voice_kernel.events import InMemoryEventBus, RedisEventBus
from voice_kernel.kernel import build_kernel
from voice_kernel.packet import PacketMeta

from .conftest import load_legacy_prompt_module

_legacy = load_legacy_prompt_module()
_HAS_LEGACY = _legacy is not None

OFF = KernelConfig()  # EVENTBUS_ENABLED is irrelevant to OFF assembly; kernel OFF


# --------------------------------------------------------------------------- #
# 1. zero droplet / agent imports
# --------------------------------------------------------------------------- #
def test_events_package_imports_no_droplet_or_agent():
    import voice_kernel.events as ev  # noqa: F401
    import voice_kernel.events.bus  # noqa: F401
    import voice_kernel.events.consumer  # noqa: F401
    import voice_kernel.events.fake  # noqa: F401
    import voice_kernel.events.taxonomy  # noqa: F401
    import voice_kernel.events.timeutil  # noqa: F401
    import voice_kernel.events.serde  # noqa: F401
    import voice_kernel.events.config  # noqa: F401

    forbidden = ("droplet_work", "agent", "caller", "aim_voice_agent")
    leaked = [
        m for m in sys.modules
        if any(m == f or m.startswith(f + ".") for f in forbidden)
    ]
    assert leaked == [], f"events package leaked forbidden imports: {leaked}"


def test_event_module_source_has_no_forbidden_imports():
    """AST-level: no import statement in the events package targets a forbidden
    module. (Prose mentions of 'droplet_work' in docstrings are fine — only real
    imports would couple us to the earner.)"""
    import ast
    import inspect
    import voice_kernel.events as ev
    import voice_kernel.events.bus as bus
    import voice_kernel.events.consumer as consumer
    import voice_kernel.events.fake as fake
    import voice_kernel.events.taxonomy as taxonomy
    import voice_kernel.events.timeutil as timeutil
    import voice_kernel.events.serde as serde
    import voice_kernel.events.config as config

    forbidden_roots = {"droplet_work", "agent", "caller", "aim_voice_agent"}
    for mod in (ev, bus, consumer, fake, taxonomy, timeutil, serde, config):
        tree = ast.parse(inspect.getsource(mod))
        targets: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    targets.append(node.module)
        for t in targets:
            root = t.split(".")[0]
            assert root not in forbidden_roots, f"{mod.__name__} imports forbidden module {t!r}"


# --------------------------------------------------------------------------- #
# 2. flag-OFF byte-identity 12/12 (skipped if legacy prompt absent in checkout)
# --------------------------------------------------------------------------- #
pytestmark = pytest.mark.skipif(
    not _HAS_LEGACY, reason="droplet_work/prompt.py not present in this checkout"
)


def _meta(direction: str) -> PacketMeta:
    return PacketMeta(tenant_id="t1", campaign_id="c1", call_id="call1", room="room1", direction=direction)


def _matrix() -> dict:
    base = dict(_legacy.GODREJ_FIELDS)
    return {
        "default": base,
        "variant": dict(base, price_offer="SPECIAL", agent_name="Anjali"),
        "recap": dict(base),
        "minimal": {"agent_name": "Riya", "company_name": "Famit", "product_name": "X"},
        "empty": {},
        "long_usps": dict(base, usps=["a", "b", "c", "d", "e", "f", "g"]),
    }


_CASES = [(n, f, d) for n, f in _matrix().items() for d in ("outbound", "inbound")]


@pytest.mark.parametrize("name,fields,direction", _CASES)
def test_off_assembly_byte_identical_with_or_without_event_bus(name, fields, direction):
    """12/12: OFF output is identical whether NO bus, an InMemoryEventBus, or a
    RedisEventBus is registered. The event backbone never perturbs OFF assembly."""
    def legacy_render() -> str:
        return _legacy.build_system_prompt(fields)

    ctx = CallContext(meta=_meta(direction), fields=fields)

    baseline = instructions_provider(legacy_render, ctx, cfg=OFF)

    # Registering a bus on a freshly-built kernel must not change the OFF path.
    build_kernel(OFF, event_bus=InMemoryEventBus())
    with_mem = instructions_provider(legacy_render, ctx, cfg=OFF)

    build_kernel(OFF, event_bus=RedisEventBus())
    with_redis = instructions_provider(legacy_render, ctx, cfg=OFF)

    assert baseline == with_mem == with_redis
    assert baseline == _legacy.build_system_prompt(fields)
