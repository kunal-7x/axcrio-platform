"""Contract tests: every null impl satisfies its runtime_checkable Protocol, the
kernel constructs + runs end-to-end with the null defaults, and importing
voice_kernel pulls in ZERO droplet_work modules (the isolation guarantee)."""
from __future__ import annotations

import asyncio
import sys

from voice_kernel import (
    BrainPackProvider,
    ContextEngine,
    DialoguePolicy,
    EventBus,
    MemoryService,
    ProviderRouter,
    RagRuntime,
    SpeechPlanner,
    VendorScriptEngine,
    build_kernel,
)
from voice_kernel.config import KernelConfig
from voice_kernel.contracts import CallContext, Event, TurnContext
from voice_kernel.null_impls import (
    NullBrainPackProvider,
    NullContextEngine,
    NullDialoguePolicy,
    NullEventBus,
    NullMemoryService,
    NullProviderRouter,
    NullRagRuntime,
    NullSpeechPlanner,
    NullVendorScriptEngine,
)
from voice_kernel.packet import PacketMeta, Stage, UseCase


def test_null_impls_conform_to_protocols():
    assert isinstance(NullContextEngine(), ContextEngine)
    assert isinstance(NullVendorScriptEngine(), VendorScriptEngine)
    assert isinstance(NullBrainPackProvider(), BrainPackProvider)
    assert isinstance(NullRagRuntime(), RagRuntime)
    assert isinstance(NullSpeechPlanner(), SpeechPlanner)
    assert isinstance(NullProviderRouter(), ProviderRouter)
    assert isinstance(NullMemoryService(), MemoryService)
    assert isinstance(NullEventBus(), EventBus)
    assert isinstance(NullDialoguePolicy(), DialoguePolicy)


def _ctx(direction="outbound"):
    meta = PacketMeta(tenant_id="t", campaign_id="c", call_id="x", room="r", direction=direction)
    fields = {
        "agent_name": "Riya",
        "company_name": "Famit",
        "product_name": "Flats",
        "product_summary": "Nice flats near metro.",
        "usps": ["near metro", "2BHK"],
        "objections": [{"q": "too costly", "a": "we have offers"}],
        "language": "Hinglish",
        "goal": "book a site visit",
    }
    return CallContext(meta=meta, fields=fields)


def test_kernel_constructs_and_assembles_with_nulls():
    k = build_kernel(KernelConfig())
    prefix = k.assemble_prefix(_ctx())
    assert "Riya" in prefix and "Famit" in prefix and "Flats" in prefix
    assert isinstance(prefix, str) and len(prefix) > 0


def test_prefix_core_is_sync_and_returns_packet():
    k = build_kernel(KernelConfig())
    text, packet = k.assemble_prefix_core(_ctx())
    assert isinstance(text, str)
    assert packet.identity.agent_name == "Riya"


def test_assemble_turn_in_memory_no_rag_by_default():
    k = build_kernel(KernelConfig())
    turn = TurnContext(call_id="x", user_text="haan bolo", detected_lang="hi", stage=Stage.QUALIFY)
    out = k.assemble_turn(turn)
    assert out is not None
    assert "qualify" in out and "hi" in out


def test_async_paths_run_with_nulls():
    async def _run():
        k = build_kernel(KernelConfig())
        ctx = _ctx()
        await k.precompute(ctx)  # null = noop
        turn = TurnContext(call_id="x", user_text="kya hai?", stage=Stage.INTRO)
        layer = await k.retrieve_turn_layer(turn, timeout_s=0.01)  # null = empty
        assert layer.rag_snippets == ()
        # enrich (null memory -> empty lead)
        _text, packet = k.assemble_prefix_core(ctx)
        enriched = await k.enrich_prefix(ctx, packet)
        assert enriched.lead.name == ""
        await k.svc.events.emit(Event("test", "x", "t", "", {}))  # null = drop

    asyncio.run(_run())


def test_build_kernel_accepts_impl_overrides():
    class MyRag(NullRagRuntime):
        pass

    k = build_kernel(KernelConfig(), rag=MyRag())
    assert isinstance(k.svc.rag, MyRag)


def test_importing_voice_kernel_pulls_no_droplet_modules():
    """The kernel never imports the live agent. Assert no droplet_work module is
    in sys.modules after importing voice_kernel + its sub-packages."""
    import voice_kernel  # noqa: F401
    import voice_kernel.shadow.runner  # noqa: F401

    droplet = [m for m in sys.modules if m.startswith("droplet")]
    assert droplet == [], f"voice_kernel must not import droplet modules, found: {droplet}"
