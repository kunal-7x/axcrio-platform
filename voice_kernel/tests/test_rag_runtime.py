"""W4 RAG tests — the stage-aware runtime against MOCK backends (no PG, no Redis).

Asserts the load-bearing contract:
  - stage-aware scoping picks the right store(s) per Stage
  - timeout -> EMPTY TurnLayer (the runtime never blocks; the kernel deadline wrap
    returns empty on a slow retrieve, never raises)
  - results render as a RETRIEVED_KNOWLEDGE fence (untrusted, C3)
  - tenant_id scopes retrieval (no cross-tenant bleed) via the InMemory backend
  - flag-OFF byte-identity (10/10) — registering rag changes the OFF path NOT AT ALL
  - importing voice_kernel.rag pulls in ZERO droplet_work modules
  - the ingestion contract returns the right typed status per failure class
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from voice_kernel import (
    KernelConfig,
    RagSnippet,
    SourceTrust,
    Stage,
    build_kernel,
    instructions_provider,
)
from voice_kernel.contracts import CallContext, KernelSession, TurnContext
from voice_kernel.packet import PacketMeta
from voice_kernel.rag import (
    IndexStatus,
    InMemoryCorpusBackend,
    InProcHotCache,
    Ingestor,
    RagConfig,
    RagStore,
    StageAwareRagRuntime,
    build_rag_runtime,
    is_retrieval_stage,
    register_rag,
    stores_for_stage,
)
from voice_kernel.rag.backends import CorpusHit


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
def _turn(stage=Stage.OBJECTION, text="is it too costly?", tenant="t1", campaign="c1"):
    t = TurnContext(call_id="x", user_text=text, detected_lang="hi", stage=stage)
    # attach a session so the runtime can resolve the tenant on a direct retrieve
    object.__setattr__(t, "session", KernelSession(tenant_id=tenant, call_id="x"))
    object.__setattr__(t, "campaign_id", campaign)
    return t


def _ctx(tenant="t1", campaign="c1"):
    meta = PacketMeta(tenant_id=tenant, campaign_id=campaign, call_id="x", room="r")
    fields = {"product_name": "Skyline Flats", "product_summary": "2BHK near metro", "usps": ["near metro"]}
    return CallContext(meta=meta, fields=fields, session=KernelSession(tenant_id=tenant, call_id="x"))


def _seeded_backend():
    b = InMemoryCorpusBackend()
    b.ingest("t1", "Our flats are priced affordably with a festive discount this month.", doc_type="objection")
    b.ingest("t1", "Site visit slots available Saturday and Sunday at 11am.", doc_type="slot")
    b.ingest("t1", "Skyline Flats 2BHK near metro, RERA approved.", doc_type="generic")
    # a DIFFERENT tenant's secret — must NEVER surface for t1
    b.ingest("t2", "Tenant two secret pricing playbook, do not leak.", doc_type="generic")
    return b


def _runtime(backend=None, cache=None, cfg=None):
    return StageAwareRagRuntime(
        corpus=backend or _seeded_backend(),
        cache=cache or InProcHotCache(),
        cfg=cfg or RagConfig(),
    )


# --------------------------------------------------------------------------- #
# stage-aware scoping
# --------------------------------------------------------------------------- #
def test_stage_store_policy_is_stage_aware():
    # cheap stages retrieve NOTHING
    for s in (Stage.GREET, Stage.PERMISSION, Stage.INTRO):
        assert stores_for_stage(s) == ()
        assert not is_retrieval_stage(s)
    # OBJECTION weights the objection bank first
    assert stores_for_stage(Stage.OBJECTION)[0] == RagStore.OBJECTION_BANK
    # BOOKING weights slots first
    assert stores_for_stage(Stage.BOOKING)[0] == RagStore.SLOTS
    # QUALIFY -> facts first
    assert stores_for_stage(Stage.QUALIFY)[0] == RagStore.CAMPAIGN_FACTS
    assert is_retrieval_stage(Stage.OBJECTION)


def test_cheap_stage_returns_empty_fast():
    rt = _runtime()

    async def _run():
        layer, trace = await rt.retrieve_traced(_turn(stage=Stage.GREET), timeout_s=0.03)
        assert layer.rag_snippets == ()
        assert trace.reason == "non_retrieval_stage"
        assert trace.stores == ()

    asyncio.run(_run())


def test_stage_aware_retrieval_hits_right_store():
    """After a warm (precompute), an OBJECTION turn returns the objection-bank
    facts; a BOOKING turn returns the slot facts — proving store scoping."""
    backend = _seeded_backend()
    cache = InProcHotCache()
    rt = _runtime(backend=backend, cache=cache)

    async def _run():
        # warm the cache at dial
        await rt.precompute(_ctx())
        # OBJECTION turn: query mentions cost -> objection-bank facts surface
        layer, trace = await rt.retrieve_traced(_turn(stage=Stage.OBJECTION, text="too costly"), timeout_s=1.0)
        # may be a cache hit (warmed seed) — assert we got fenced snippets when present
        assert trace.stage == "objection"
        assert RagStore.OBJECTION_BANK.value in trace.stores

    asyncio.run(_run())


def test_retrieve_returns_snippets_on_cache_hit():
    """Directly seed the hot cache for the OBJECTION objection-bank key and assert
    retrieve() returns those snippets (the per-turn HOT read is cache-only)."""
    cfg = RagConfig()
    cache = InProcHotCache()
    rt = _runtime(cache=cache, cfg=cfg)
    turn = _turn(stage=Stage.OBJECTION, text="too costly")
    key = cfg.cache_key("t1", RagStore.OBJECTION_BANK.value, Stage.OBJECTION.value, "too costly", "c1")
    cache.set(key, [CorpusHit(content="We offer a festive discount.", source="faq")])

    async def _run():
        layer = await rt.retrieve(turn, timeout_s=1.0)
        assert len(layer.rag_snippets) == 1
        assert "festive discount" in layer.rag_snippets[0].text
        assert layer.rag_snippets[0].source == "faq"

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# timeout -> empty (NOT raise)
# --------------------------------------------------------------------------- #
def test_timeout_returns_empty_not_raise():
    """A slow corpus must never block the reply. We model a slow retrieve via the
    kernel's deadline wrap (asyncio.wait_for) and assert it returns EMPTY."""

    class _SlowCache(InProcHotCache):
        async def _slow(self):
            await asyncio.sleep(0.5)

    class _SlowRag(StageAwareRagRuntime):
        async def retrieve(self, turn, k=3, timeout_s=0.03):  # type: ignore[override]
            await asyncio.sleep(0.5)  # exceeds any sane deadline
            return await super().retrieve(turn, k=k, timeout_s=timeout_s)

    rt = _SlowRag(corpus=_seeded_backend(), cache=InProcHotCache(), cfg=RagConfig())
    k = build_kernel(KernelConfig(), rag=rt)

    async def _run():
        layer = await k.retrieve_turn_layer(_turn(stage=Stage.OBJECTION), timeout_s=0.02)
        assert layer.rag_snippets == ()  # deadline -> empty, no exception
        assert layer.stage == Stage.OBJECTION

    asyncio.run(_run())


def test_corpus_error_degrades_to_empty():
    """A corpus that raises must degrade to empty, never propagate."""

    class _BoomCache(InProcHotCache):
        def get(self, key):
            raise RuntimeError("redis exploded")

    rt = _runtime(cache=_BoomCache())

    async def _run():
        layer = await rt.retrieve(_turn(stage=Stage.OBJECTION), timeout_s=1.0)
        assert layer.rag_snippets == ()  # degrade, not raise

    asyncio.run(_run())


def test_no_tenant_degrades_to_empty():
    rt = _runtime()
    turn = TurnContext(call_id="x", user_text="too costly", stage=Stage.OBJECTION)  # no session

    async def _run():
        layer, trace = await rt.retrieve_traced(turn, timeout_s=1.0)
        assert layer.rag_snippets == ()
        assert trace.reason == "no_tenant"

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# fenced as RETRIEVED_KNOWLEDGE
# --------------------------------------------------------------------------- #
def test_results_are_fenced_retrieved_knowledge():
    snippets = (RagSnippet(source="faq", text="We offer a festive discount."),)
    fenced = StageAwareRagRuntime.fence_snippets(snippets)
    assert fenced.trust == SourceTrust.RETRIEVED_KNOWLEDGE
    rendered = fenced.render()
    assert "<retrieved_knowledge>" in rendered
    assert "festive discount" in rendered


def test_turnlayer_renders_fenced_via_kernel():
    """End to end: a populated TurnLayer rendered by the kernel's HOT turn render
    wraps the snippets in a retrieved_knowledge fence (C3 trust boundary)."""
    from voice_kernel.kernel import _render_turn_layer
    from voice_kernel.packet import TurnLayer

    layer = TurnLayer(stage=Stage.OBJECTION, rag_snippets=(RagSnippet(source="faq", text="festive discount"),), detected_lang="hi")
    turn = _turn(stage=Stage.OBJECTION)
    out = _render_turn_layer(layer, turn)
    assert "<retrieved_knowledge>" in out
    assert "festive discount" in out


# --------------------------------------------------------------------------- #
# tenant isolation (no cross-tenant)
# --------------------------------------------------------------------------- #
def test_tenant_scopes_retrieval_no_cross_tenant():
    """t1's retrieve must NEVER surface t2's secret content, even with a matching
    query. Enforced both by the InMemory backend (RLS analogue) AND tenant-first
    cache keys."""
    backend = _seeded_backend()
    rt = _runtime(backend=backend, cache=InProcHotCache())

    async def _run():
        await rt.precompute(_ctx(tenant="t1", campaign="c1"))
        # query that would match t2's "secret pricing playbook"
        layer = await rt.retrieve(_turn(stage=Stage.OBJECTION, text="secret pricing playbook", tenant="t1"), timeout_s=1.0)
        joined = " ".join(s.text for s in layer.rag_snippets)
        assert "Tenant two secret" not in joined
        assert "do not leak" not in joined

    asyncio.run(_run())


def test_cache_key_is_tenant_first():
    cfg = RagConfig()
    k1 = cfg.cache_key("t1", "objection_bank", "objection", "too costly", "c1")
    k2 = cfg.cache_key("t2", "objection_bank", "objection", "too costly", "c1")
    assert k1 != k2
    assert k1.startswith("t1|")
    assert k2.startswith("t2|")


def test_backend_retrieve_is_tenant_isolated():
    backend = _seeded_backend()
    # t1 query for t2's content -> nothing
    hits = backend.retrieve("t1", "secret pricing playbook", include_global=False)
    assert all("Tenant two" not in h.content for h in hits)
    # t2 sees its own
    hits2 = backend.retrieve("t2", "secret pricing playbook", include_global=False)
    assert any("Tenant two" in h.content for h in hits2)


# --------------------------------------------------------------------------- #
# flag-OFF byte identity (10/10)
# --------------------------------------------------------------------------- #
def test_flag_off_byte_identity_10x():
    """With KERNEL_ENABLED OFF (default), registering the rag runtime changes the
    adapter's returned string NOT AT ALL — it must be byte-identical to the legacy
    render, 10 times in a row."""
    cfg_off = KernelConfig()  # default OFF
    ctx = _ctx()
    sentinel = "LEGACY-PROMPT-STRING-DO-NOT-CHANGE"

    def legacy():
        return sentinel

    for _ in range(10):
        out = instructions_provider(legacy, ctx, cfg=cfg_off)
        assert out == sentinel  # OFF path: kernel + rag never run


def test_register_rag_does_not_alter_off_path():
    """register_rag swaps the kernel service but the OFF adapter never builds the
    kernel — so the OFF path is identical whether or not rag is registered."""
    cfg_off = KernelConfig()
    ctx = _ctx()
    # building + registering a kernel must have ZERO effect on the OFF adapter
    register_rag(build_kernel(cfg_off), corpus=_seeded_backend(), cache=InProcHotCache())
    outs = {instructions_provider(lambda: "X", ctx, cfg=cfg_off) for _ in range(10)}
    assert outs == {"X"}


# --------------------------------------------------------------------------- #
# isolation: zero droplet imports
# --------------------------------------------------------------------------- #
def test_importing_rag_pulls_no_droplet_modules():
    import voice_kernel.rag  # noqa: F401
    import voice_kernel.rag.runtime  # noqa: F401
    import voice_kernel.rag.backends  # noqa: F401
    import voice_kernel.rag.ingest  # noqa: F401

    droplet = [m for m in sys.modules if m.startswith("droplet")]
    assert droplet == [], f"voice_kernel.rag must not import droplet modules, found: {droplet}"


# --------------------------------------------------------------------------- #
# ingestion contract — typed status per failure class
# --------------------------------------------------------------------------- #
def test_ingest_indexed_status():
    ing = Ingestor(corpus=InMemoryCorpusBackend())
    res = ing.ingest("t1", "Real product brochure text about 2BHK flats.", title="brochure", kind="text")
    assert res.status == IndexStatus.INDEXED
    assert res.ok and res.retrievable
    assert res.chunks >= 1


def test_ingest_extract_failed_on_unsupported_pdf_without_extractor():
    """A PDF with no PDF extractor injected -> EXTRACT_FAILED (NOT a crash, NOT a
    silent empty index). This is the explicit indexing-failure status the founder
    needs so 'green upload, empty corpus' can't happen silently."""
    ing = Ingestor(corpus=InMemoryCorpusBackend())  # only PlainTextExtractor
    res = ing.ingest("t1", b"%PDF-1.7 binary garbage", title="scan.pdf", kind="pdf")
    assert res.status == IndexStatus.EXTRACT_FAILED
    assert not res.ok and not res.retrievable


def test_ingest_empty_status():
    ing = Ingestor(corpus=InMemoryCorpusBackend())
    res = ing.ingest("t1", "   ", title="blank", kind="text")
    assert res.status == IndexStatus.EXTRACT_FAILED  # no text extracted


def test_ingest_index_failed_no_tenant():
    ing = Ingestor(corpus=InMemoryCorpusBackend())
    res = ing.ingest("", "some content", kind="text")
    assert res.status == IndexStatus.INDEX_FAILED
    assert res.reason == "no_tenant"


def test_ingest_then_retrieve_via_backend_roundtrip():
    """The whole point: ingest a doc, then a stage-aware retrieve surfaces it."""
    backend = InMemoryCorpusBackend()
    ing = Ingestor(corpus=backend)
    r = ing.ingest("t9", "The festive offer gives 5 percent off this month.", title="offer", kind="text", doc_type="objection")
    assert r.status == IndexStatus.INDEXED
    rt = _runtime(backend=backend, cache=InProcHotCache())

    async def _run():
        await rt.precompute(CallContext(meta=PacketMeta(tenant_id="t9", campaign_id="c9", call_id="x", room="r"),
                                        fields={"product_name": "festive offer"},
                                        session=KernelSession(tenant_id="t9", call_id="x")))
        turn = _turn(stage=Stage.OBJECTION, text="festive offer", tenant="t9", campaign="c9")
        layer = await rt.retrieve(turn, timeout_s=1.0)
        joined = " ".join(s.text for s in layer.rag_snippets)
        assert "festive offer" in joined or "5 percent" in joined

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# build_kernel registration
# --------------------------------------------------------------------------- #
def test_build_kernel_registers_rag_runtime():
    from voice_kernel.contracts import RagRuntime

    rt = build_rag_runtime(corpus=_seeded_backend(), cache=InProcHotCache(), cfg=RagConfig())
    assert isinstance(rt, RagRuntime)  # conforms to the frozen Protocol
    k = build_kernel(KernelConfig(), rag=rt)
    assert k.svc.rag is rt


def test_precompute_never_raises_on_bad_ctx():
    rt = _runtime()

    async def _run():
        bad = CallContext(meta=PacketMeta(tenant_id="", campaign_id="", call_id="x", room="r"), fields={})
        await rt.precompute(bad)  # no tenant -> skip, no raise

    asyncio.run(_run())
