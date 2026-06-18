"""voice_kernel.rag.runtime — StageAwareRagRuntime: the RagRuntime impl.

Binds the FROZEN `voice_kernel.contracts.RagRuntime` Protocol:
    async precompute(ctx: CallContext) -> None
    async retrieve(turn, k=3, timeout_s=0.03) -> TurnLayer

Properties (RESEARCH-DECISIONS, all load-bearing):
  STAGE-AWARE   retrieval store is chosen by `turn.stage` (stores.py policy); on
                GREET/PERMISSION/INTRO it returns EMPTY in <1ms (no cache, no DB).
  SELECTIVE     not every turn hits the corpus — the per-turn retrieve reads the
                HOT CACHE only (warmed by precompute). A cache MISS returns empty
                rather than paying the 50-300ms DB+embed cost on the hot path.
  TENANT-SCOPED every query carries KernelSession.tenant_id; cache keys are
                tenant-FIRST (config.cache_key) so a hit can never cross tenants;
                the corpus read is is_admin=False (RLS) with no `%` wildcard.
  DEGRADE       any failure (no tenant, cache down, corpus error, timeout) ->
                EMPTY TurnLayer. NEVER raises into the hot path.
  FENCED        snippets are returned as RagSnippet; the packet renderer fences
                them as SourceTrust.RETRIEVED_KNOWLEDGE (untrusted data). We also
                expose `fence_snippets()` so a caller/test can render the fence
                directly and assert the trust boundary.

THE HOT/WARM SPLIT (the latency contract):
  precompute()  WARM, at dial. For the PREDICTABLE stage path it queries the
                corpus ONCE per (store, stage) and writes the result into the hot
                cache. This is where the DB/embed cost is paid — off the hot path.
  retrieve()    HOT, per turn. Reads the hot cache ONLY (dense forced OFF). Sub-ms
                on a hit; empty on a miss. The kernel runs it under asyncio.wait_for
                parallel to the LLM start, so even a slow cache is bounded.

This module imports NO droplet code and NO Redis at import time (all lazy/injected).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from ..contracts import CallContext, TurnContext
from ..packet import FencedText, RagSnippet, SourceTrust, Stage, TurnLayer, fence
from ..tokens import clamp_chars
from .backends import CorpusBackend, CorpusHit, HotCache, InProcHotCache, KbCorpusBackend
from .config import RagConfig
from .stores import RagStore, is_retrieval_stage, scope_for, stores_for_stage

log = logging.getLogger("voice_kernel.rag.runtime")

_RAG_TEXT_CHARS = 120  # mirrors packet._RAG_TEXT_CHARS (snippet hard clamp)


@dataclass(frozen=True)
class RetrieveTrace:
    """Observability for a single retrieve() — what store, cache hit/miss, count.
    Returned by `retrieve_traced` (the test/UI entrypoint), NEVER on the hot path
    (retrieve() returns a plain TurnLayer)."""

    stage: str
    stores: tuple[str, ...]
    cache_hit: bool
    n_hits: int
    degraded: bool
    reason: str = ""


class StageAwareRagRuntime:
    """The production RagRuntime. Inject a CorpusBackend + HotCache (both default
    to the safe production impls); tests inject InMemory + InProc."""

    def __init__(
        self,
        *,
        corpus: Optional[CorpusBackend] = None,
        cache: Optional[HotCache] = None,
        cfg: Optional[RagConfig] = None,
    ) -> None:
        self.cfg = cfg or RagConfig.from_env()
        self.corpus: CorpusBackend = corpus or KbCorpusBackend()
        self.cache: HotCache = cache or InProcHotCache()

    # --------------------------------------------------------------- tenant #
    @staticmethod
    def _tenant_of(turn_or_ctx) -> str:
        """Resolve the tenant_id from a CallContext (precompute) or TurnContext
        (retrieve). TurnContext carries no tenant directly, so the runtime relies
        on the precompute-seeded cache being tenant-keyed; for a direct retrieve
        the tenant is read from an attached session if present, else ''."""
        sess = getattr(turn_or_ctx, "session", None)
        if sess is not None and getattr(sess, "tenant_id", ""):
            return sess.tenant_id
        meta = getattr(turn_or_ctx, "meta", None)
        if meta is not None and getattr(meta, "tenant_id", ""):
            return meta.tenant_id
        return ""

    # ------------------------------------------------------------ WARM path #
    async def precompute(self, ctx: CallContext) -> None:
        """WARM, at dial. Query the corpus for the predictable stages ONCE and
        warm the hot cache. Off the hot path; failure is non-fatal (returns None).

        The kernel calls this fire-and-forget (kernel.precompute swallows errors),
        so this method also self-guards: ANY failure logs + returns, never raises.
        """
        try:
            tenant = self._tenant_of(ctx)
            if not tenant:
                log.debug("rag.precompute: no tenant on ctx — skipping warm")
                return
            campaign_id = getattr(ctx.meta, "campaign_id", "") or ""
            # Seed queries: the campaign product + the predictable stage path.
            base_q = self._seed_query(ctx)
            if not base_q:
                log.debug("rag.precompute: no seed query — nothing to warm")
                return
            # Warm EVERY store the hot path will probe for each retrieval stage.
            # CRITICAL (W4 red-team fix): the warm entry is written under the SEED
            # cache key (query="") — the exact key retrieve() probes as its
            # `seed_key` fallback when the per-query key misses on turn 1. Warming
            # under base_q (the old behaviour) wrote a key NO hot read ever looked
            # up, so the warm was dead and the FIRST objection/booking of a call
            # always returned empty. The corpus QUERY still uses base_q (relevance);
            # only the cache SLOT is the query-agnostic seed for this (store,stage).
            warmed = 0
            seen: set[tuple[str, str]] = set()
            for stage in (Stage.QUALIFY, Stage.OBJECTION, Stage.BOOKING, Stage.CLOSE, Stage.FOLLOWUP):
                for store in stores_for_stage(stage):
                    sig = (store.value, stage.value)
                    if sig in seen:
                        continue
                    seen.add(sig)
                    hits = await asyncio.to_thread(
                        self._corpus_query, tenant, base_q, store, campaign_id, self.cfg.dense_enabled
                    )
                    if not hits:
                        continue  # don't cache an empty seed (keeps miss->bg-warm alive)
                    seed_key = self.cfg.cache_key(tenant, store.value, stage.value, "", campaign_id)
                    self.cache.set(seed_key, hits, ttl_s=self.cfg.cache_ttl_s)
                    warmed += 1
            log.info("rag.precompute warmed %d (store,stage) seed cache entries for tenant=%s", warmed, tenant)
        except Exception as exc:  # noqa: BLE001  -- precompute MUST never raise
            log.warning("rag.precompute failed (non-fatal): %r", exc)
            return

    @staticmethod
    def _seed_query(ctx: CallContext) -> str:
        f = dict(getattr(ctx, "fields", {}) or {})
        parts = [
            str(f.get("product_name", "")),
            str(f.get("product_summary", "")),
            " ".join(f.get("usps", []) if isinstance(f.get("usps"), list) else []),
        ]
        return " ".join(p for p in parts if p).strip()[:400]

    # ------------------------------------------------------------- HOT path #
    async def retrieve(self, turn: TurnContext, k: int = 3, timeout_s: float = 0.03) -> TurnLayer:
        """HOT, per turn. Reads the HOT CACHE only (dense forced OFF). Returns a
        populated TurnLayer on a cache hit, else an EMPTY TurnLayer. NEVER raises;
        NEVER blocks beyond the cache read. The kernel additionally wraps this in
        asyncio.wait_for(timeout_s) as a hard ceiling."""
        layer, _trace = await self._retrieve_impl(turn, k=k, timeout_s=timeout_s)
        return layer

    async def retrieve_traced(self, turn: TurnContext, k: int = 3, timeout_s: float = 0.03):
        """Test/UI entrypoint: same as retrieve() but ALSO returns a RetrieveTrace
        (store chosen, cache hit/miss, count, degrade reason) for a future
        retrieve-test UI. Off the hot path — agents call retrieve(), not this."""
        return await self._retrieve_impl(turn, k=k, timeout_s=timeout_s)

    async def _retrieve_impl(self, turn: TurnContext, k: int, timeout_s: float):
        stage = turn.stage or Stage.GREET
        empty = TurnLayer(stage=stage, detected_lang=turn.detected_lang)

        # cheap-stage gate: GREET/PERMISSION/INTRO retrieve nothing (save budget).
        if not is_retrieval_stage(stage):
            return empty, RetrieveTrace(stage.value, (), False, 0, False, "non_retrieval_stage")

        tenant = self._tenant_of(turn)
        if not tenant:
            # no tenant on a per-turn read -> cannot scope safely -> degrade empty.
            return empty, RetrieveTrace(stage.value, (), False, 0, True, "no_tenant")

        query = (turn.user_text or "").strip()
        if not query:
            return empty, RetrieveTrace(stage.value, (), False, 0, False, "empty_query")

        stores = stores_for_stage(stage)
        campaign_id = getattr(turn, "campaign_id", "") or ""
        try:
            # HOT path: cache reads ONLY. Read each stage store's cache in order;
            # take the first non-empty. Cache miss across all -> empty (degrade).
            hits: list[CorpusHit] = []
            cache_hit = False
            for store in stores:
                key = self.cfg.cache_key(tenant, store.value, stage.value, query, campaign_id)
                cached = self.cache.get(key)
                if cached:
                    hits = cached
                    cache_hit = True
                    break
                # opportunistic warm seed: also try the precompute seed key, which
                # precompute() filled (query-agnostic facts for this stage/store).
                seed_key = self.cfg.cache_key(tenant, store.value, stage.value, "", campaign_id)
                cached_seed = self.cache.get(seed_key)
                if cached_seed:
                    hits = cached_seed
                    cache_hit = True
                    break

            if not hits:
                # MISS: do NOT pay the DB/embed cost on the hot path (latency law).
                # Kick a background warm so the NEXT turn is a hit, then return empty.
                self._schedule_warm(tenant, query, stores, campaign_id, stage)
                return empty, RetrieveTrace(stage.value, tuple(s.value for s in stores), False, 0, False, "cache_miss")

            snippets = self._to_snippets(hits, k=min(k, self.cfg.top_k))
            layer = TurnLayer(stage=stage, rag_snippets=snippets, detected_lang=turn.detected_lang)
            return layer, RetrieveTrace(
                stage.value, tuple(s.value for s in stores), cache_hit, len(snippets), False, "ok"
            )
        except Exception as exc:  # noqa: BLE001  -- degrade-to-empty, never raise
            log.warning("rag.retrieve degraded to empty: %r", exc)
            return empty, RetrieveTrace(stage.value, tuple(s.value for s in stores), False, 0, True, f"error:{type(exc).__name__}")

    # ---------------------------------------------------------- internals #
    def _corpus_query(self, tenant: str, query: str, store: RagStore, campaign_id: str, dense: bool) -> list[CorpusHit]:
        """SYNC corpus read for one store (runs in a thread from precompute /
        background warm). Applies the store's scope + global-union policy. Biases
        the FTS query with the store's doc_type hint. NEVER raises."""
        try:
            sc = scope_for(store)
            q = (query + (" " + sc.doc_type_hint if sc.doc_type_hint else "")).strip()
            return self.corpus.retrieve(
                tenant,
                q,
                top_k=self.cfg.fanout,
                scope=sc.scope,
                channel="all",
                scope_campaign_id=campaign_id,
                dense=bool(dense),  # only ever True in precompute, never hot path
                include_global=self.cfg.include_global and sc.include_global,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("rag corpus query failed (store=%s): %r", store, exc)
            return []

    def _schedule_warm(self, tenant: str, query: str, stores, campaign_id: str, stage: Stage) -> None:
        """Fire-and-forget background warm of the cache for THIS query, so the
        next turn is a hit. Never blocks; failure is swallowed."""
        async def _warm():
            try:
                for store in stores[:1]:
                    hits = await asyncio.to_thread(
                        self._corpus_query, tenant, query, store, campaign_id, False
                    )
                    key = self.cfg.cache_key(tenant, store.value, stage.value, query, campaign_id)
                    self.cache.set(key, hits, ttl_s=self.cfg.cache_ttl_s)
            except Exception as exc:  # noqa: BLE001
                log.debug("background warm degraded: %r", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_warm())
        except RuntimeError:
            pass  # no running loop (e.g. a sync test) -> skip the warm, return empty

    @staticmethod
    def _to_snippets(hits: list[CorpusHit], k: int) -> tuple[RagSnippet, ...]:
        out: list[RagSnippet] = []
        for h in hits[: max(1, k)]:
            text = clamp_chars((h.content or "").strip(), _RAG_TEXT_CHARS)
            if not text:
                continue
            out.append(RagSnippet(source=h.source or "kb", text=text))
        return tuple(out)

    # --------------------------------------------------------------- fence #
    @staticmethod
    def fence_snippets(snippets: tuple[RagSnippet, ...]) -> FencedText:
        """Render snippets as a RETRIEVED_KNOWLEDGE fence (untrusted data). The
        packet renderer does this on the prompt path; this helper lets a caller or
        test assert the trust boundary directly."""
        rendered = "; ".join(f"[{s.source}] {s.text}" for s in snippets if s.text)
        return fence(SourceTrust.RETRIEVED_KNOWLEDGE, "RELEVANT: " + rendered if rendered else "")


# --------------------------------------------------------------------------- #
# build helpers — register the runtime into the kernel via build_kernel
# --------------------------------------------------------------------------- #
def build_rag_runtime(
    *,
    corpus: Optional[CorpusBackend] = None,
    cache: Optional[HotCache] = None,
    cfg: Optional[RagConfig] = None,
) -> StageAwareRagRuntime:
    """Factory for the runtime (production defaults to KbCorpusBackend + InProc)."""
    return StageAwareRagRuntime(corpus=corpus, cache=cache, cfg=cfg)
