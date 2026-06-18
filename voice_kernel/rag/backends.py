"""voice_kernel.rag.backends — the THIN, MOCKABLE adapter boundary.

This is the ONE place voice_kernel touches the live knowledge corpus. Two
contracts, both pure-stdlib Protocols (no Redis/PG/droplet imports at module
import time), so the whole rag package stays import-safe for aim_voice_agent.py
and every backend is trivially mockable in a test (no DB, no network).

  * `CorpusBackend` — read/write the chunk store. The PRODUCTION impl
    (`KbCorpusBackend`) wraps droplet_work/kb/core.py LAZILY (the import happens
    inside the method, never at module top) so:
      - importing voice_kernel.rag pulls in ZERO droplet modules (isolation), and
      - tests inject `InMemoryCorpusBackend` (or any mock) with no DB at all.
    kb/core.py is NEVER edited — we only call its public `retrieve` / `ingest` /
    `status` functions. That is the earner-law "wrap kb, don't touch it" rule.

  * `HotCache` — the <50ms get/set tier (L0 dict + optional L1 Redis). The
    production impl is sync-safe and degrades to a no-op when Redis is absent.

DEGRADE-TO-EMPTY: every backend method swallows its own failure and returns the
empty/false result. retrieval NEVER raises into the hot path — that guarantee is
the whole reason this seam exists (RagRuntime.retrieve must honour it).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

log = logging.getLogger("voice_kernel.rag.backends")


# --------------------------------------------------------------------------- #
# result shape returned by a CorpusBackend.retrieve (kb/core.py row shape)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CorpusHit:
    """One retrieved chunk, normalized from the kb/core.py row dict.

    Mirrors kb.core.retrieve()'s `{content, section, document_id, source_id,
    score, leg}` so the production wrap is a 1:1 field copy, but as a typed,
    backend-agnostic value the runtime + tests both depend on.
    """

    content: str
    source: str = ""  # human source label (section or document_id) for the fence
    document_id: str = ""
    source_id: str = ""
    score: float = 0.0
    leg: str = ""  # "sparse" | "dense" | "sparse+dense" (provenance/trace)


@runtime_checkable
class CorpusBackend(Protocol):
    """The read/write corpus seam. ALL methods are tenant-scoped and degrade to
    empty/false on any failure (never raise)."""

    def retrieve(
        self,
        tenant_id: str,
        query: str,
        *,
        top_k: int = 6,
        scope: str = "",
        channel: str = "all",
        scope_campaign_id: str = "",
        dense: bool = False,
        include_global: bool = True,
    ) -> list[CorpusHit]: ...

    def ingest(
        self,
        tenant_id: str,
        content: str,
        *,
        title: str = "",
        kind: str = "paste",
        scope: str = "business",
        doc_type: str = "generic",
        channel_scope: str = "all",
        scope_campaign_id: str = "",
        scope_product_id: str = "",
    ) -> dict: ...

    def status(self) -> dict: ...


@runtime_checkable
class HotCache(Protocol):
    """The <50ms get/set tier. Sync, key-scoped, degrade-to-noop. Keys are
    pre-namespaced by the caller (tenant-scoped — see RagConfig.cache_key)."""

    def get(self, key: str) -> Optional[list[CorpusHit]]: ...

    def set(self, key: str, hits: list[CorpusHit], ttl_s: int = 300) -> None: ...

    def stats(self) -> dict: ...


# --------------------------------------------------------------------------- #
# PRODUCTION CorpusBackend — wraps droplet_work/kb/core.py (lazy, read-only)
# --------------------------------------------------------------------------- #
class KbCorpusBackend:
    """Production CorpusBackend. Wraps kb/core.py via a LAZY import so importing
    this module pulls in no droplet/DB code. kb/core.py is never modified.

    The wrap is deliberately thin: we forward to `kb.core.retrieve/ingest/status`
    and normalize the row dicts to CorpusHit. Every call is wrapped so a kb import
    failure (e.g. CI checkout without droplet_work) degrades to []/no-op, NOT a
    crash — the runtime then returns an empty TurnLayer, which is correct.
    """

    def __init__(self) -> None:
        self._kb: Any = None
        self._kb_tried = False

    def _core(self) -> Any:
        """Lazily import droplet_work/kb/core.py the SAME isolated way conftest
        loads prompt.py — by file path, WITHOUT registering a droplet_work
        package and WITHOUT importing agent.py. Returns None if unavailable."""
        if self._kb is not None or self._kb_tried:
            return self._kb
        self._kb_tried = True
        try:
            import importlib.util
            from pathlib import Path

            root = Path(__file__).resolve().parents[2]
            p = root / "droplet_work" / "kb" / "core.py"
            if not p.exists():
                log.info("kb/core.py absent (%s) — corpus backend degrades to empty", p)
                return None
            spec = importlib.util.spec_from_file_location("_vk_kb_core", str(p))
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader is not None
            spec.loader.exec_module(mod)
            self._kb = mod
            return mod
        except Exception as exc:  # noqa: BLE001
            log.warning("kb/core.py load failed (degrade to empty): %r", exc)
            return None

    @staticmethod
    def _to_hits(rows: list[dict]) -> list[CorpusHit]:
        out: list[CorpusHit] = []
        for r in rows or []:
            content = str(r.get("content", "")).strip()
            if not content:
                continue
            source = str(r.get("section") or r.get("document_id") or "kb").strip() or "kb"
            out.append(
                CorpusHit(
                    content=content,
                    source=source,
                    document_id=str(r.get("document_id", "")),
                    source_id=str(r.get("source_id", "")),
                    score=float(r.get("score", 0.0) or 0.0),
                    leg=str(r.get("leg", "")),
                )
            )
        return out

    def retrieve(
        self,
        tenant_id: str,
        query: str,
        *,
        top_k: int = 6,
        scope: str = "",
        channel: str = "all",
        scope_campaign_id: str = "",
        dense: bool = False,
        include_global: bool = True,
    ) -> list[CorpusHit]:
        core = self._core()
        if core is None:
            return []
        try:
            rows = core.retrieve(
                tenant_id,
                query,
                top_k=top_k,
                scope=scope,
                channel=channel,
                scope_campaign_id=scope_campaign_id,
                dense=dense,
                include_global=include_global,
                is_admin=False,  # voice read = caller's own GUC, never admin (RLS law)
            )
            return self._to_hits(rows)
        except Exception as exc:  # noqa: BLE001
            log.warning("KbCorpusBackend.retrieve failed (return []): %r", exc)
            return []

    def ingest(
        self,
        tenant_id: str,
        content: str,
        *,
        title: str = "",
        kind: str = "paste",
        scope: str = "business",
        doc_type: str = "generic",
        channel_scope: str = "all",
        scope_campaign_id: str = "",
        scope_product_id: str = "",
    ) -> dict:
        core = self._core()
        if core is None:
            return {"ok": False, "reason": "kb_unavailable"}
        try:
            return core.ingest(
                tenant_id,
                content,
                title=title,
                kind=kind,
                scope=scope,
                doc_type=doc_type,
                channel_scope=channel_scope,
                scope_campaign_id=scope_campaign_id,
                scope_product_id=scope_product_id,
                is_admin=False,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("KbCorpusBackend.ingest failed: %r", exc)
            return {"ok": False, "reason": f"error:{type(exc).__name__}"}

    def status(self) -> dict:
        core = self._core()
        if core is None:
            return {"pg_available": False, "sparse_leg": False, "dense_leg": False, "wrapped": False}
        try:
            st = dict(core.status())
            st["wrapped"] = True
            return st
        except Exception as exc:  # noqa: BLE001
            log.warning("KbCorpusBackend.status failed: %r", exc)
            return {"pg_available": False, "wrapped": True, "error": type(exc).__name__}


# --------------------------------------------------------------------------- #
# PRODUCTION HotCache — L0 in-proc dict + optional L1 Redis (lazy, degrade)
# --------------------------------------------------------------------------- #
class InProcHotCache:
    """L0 in-process TTL dict. Sub-ms hits, bounded size, sync-safe. This is the
    always-on tier; Redis (L1) is layered on top by `RedisHotCache` when present.

    Bounded by `max_entries` (simple FIFO-ish eviction of the oldest insert) so a
    long-lived worker can't leak memory across thousands of calls.
    """

    def __init__(self, max_entries: int = 4096) -> None:
        self._max = max(16, int(max_entries))
        self._d: dict[str, tuple[float, list[CorpusHit]]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[list[CorpusHit]]:
        ent = self._d.get(key)
        if ent is None:
            self._misses += 1
            return None
        expires_at, hits = ent
        if expires_at and expires_at < time.monotonic():
            self._d.pop(key, None)
            self._misses += 1
            return None
        self._hits += 1
        return list(hits)

    def set(self, key: str, hits: list[CorpusHit], ttl_s: int = 300) -> None:
        if not key:
            return
        if len(self._d) >= self._max:
            # evict oldest insertion (dicts preserve insertion order)
            try:
                self._d.pop(next(iter(self._d)))
            except StopIteration:
                pass
        expires_at = time.monotonic() + ttl_s if ttl_s and ttl_s > 0 else 0.0
        self._d[key] = (expires_at, list(hits))

    def stats(self) -> dict:
        return {"tier": "l0_inproc", "entries": len(self._d), "hits": self._hits, "misses": self._misses}


class RedisHotCache:
    """L1 Redis tier in FRONT of an L0 dict. Get checks L0 then Redis (promoting
    a Redis hit into L0); set writes both. Redis is OPTIONAL and lazy — if no
    client is configured/reachable, this behaves EXACTLY like InProcHotCache
    (degrade-to-L0, never raise).

    `redis_client` is injected (so tests pass a fakeredis/mock); production builds
    it from REDIS_URL via `from_env`. Values are JSON-serialized CorpusHit lists.
    """

    def __init__(self, redis_client: Any = None, *, namespace: str = "vkrag", l0_max: int = 4096) -> None:
        self._l0 = InProcHotCache(max_entries=l0_max)
        self._r = redis_client
        self._ns = namespace
        self._r_hits = 0
        self._r_errors = 0

    @classmethod
    def from_env(cls, *, namespace: str = "vkrag") -> "RedisHotCache":
        """Build with a real redis client from REDIS_URL if redis is installed +
        reachable; otherwise return an L0-only cache (degrade). Never raises."""
        client = None
        try:
            import os

            url = os.getenv("REDIS_URL") or os.getenv("RAG_REDIS_URL")
            if url:
                import redis  # type: ignore

                client = redis.Redis.from_url(url, socket_timeout=0.05, socket_connect_timeout=0.05)
                client.ping()
        except Exception as exc:  # noqa: BLE001
            log.info("RedisHotCache: no live Redis (%r) — using L0 only", exc)
            client = None
        return cls(redis_client=client, namespace=namespace)

    def _rk(self, key: str) -> str:
        return f"{self._ns}:{key}"

    def get(self, key: str) -> Optional[list[CorpusHit]]:
        l0 = self._l0.get(key)
        if l0 is not None:
            return l0
        if self._r is None:
            return None
        try:
            raw = self._r.get(self._rk(key))
        except Exception as exc:  # noqa: BLE001
            self._r_errors += 1
            log.debug("RedisHotCache.get degraded: %r", exc)
            return None
        if not raw:
            return None
        try:
            import json

            data = json.loads(raw)
            hits = [
                CorpusHit(
                    content=d.get("content", ""),
                    source=d.get("source", ""),
                    document_id=d.get("document_id", ""),
                    source_id=d.get("source_id", ""),
                    score=float(d.get("score", 0.0) or 0.0),
                    leg=d.get("leg", ""),
                )
                for d in data
            ]
            self._r_hits += 1
            self._l0.set(key, hits)  # promote into L0 for the next sub-ms hit
            return hits
        except Exception as exc:  # noqa: BLE001
            self._r_errors += 1
            log.debug("RedisHotCache.get decode degraded: %r", exc)
            return None

    def set(self, key: str, hits: list[CorpusHit], ttl_s: int = 300) -> None:
        self._l0.set(key, hits, ttl_s=ttl_s)
        if self._r is None or not key:
            return
        try:
            import json

            payload = json.dumps([h.__dict__ for h in hits])
            self._r.set(self._rk(key), payload, ex=max(1, int(ttl_s)) if ttl_s else None)
        except Exception as exc:  # noqa: BLE001
            self._r_errors += 1
            log.debug("RedisHotCache.set degraded: %r", exc)

    def stats(self) -> dict:
        s = dict(self._l0.stats())
        s.update({"tier": "l0+l1_redis", "redis": self._r is not None, "redis_hits": self._r_hits, "redis_errors": self._r_errors})
        return s


# --------------------------------------------------------------------------- #
# IN-MEMORY test/dev CorpusBackend — zero DB, deterministic, tenant-isolated
# --------------------------------------------------------------------------- #
class InMemoryCorpusBackend:
    """A real, deterministic CorpusBackend with NO database — for tests + local
    dev. Stores chunks per (tenant_id) and does a naive token-overlap sparse
    match so stage-aware/tenant-scoping behaviour is testable without PG/Redis.

    Tenant isolation is ENFORCED here exactly as the production RLS does: a
    retrieve for tenant A can only ever see tenant A's rows (+ the shared
    `_global` tenant when include_global). This is what the cross-tenant test
    asserts against without needing Postgres.
    """

    def __init__(self) -> None:
        # tenant_id -> list[(content, source, doc_type, scope_campaign_id)]
        self._store: dict[str, list[tuple[str, str, str, str]]] = {}

    def ingest(
        self,
        tenant_id: str,
        content: str,
        *,
        title: str = "",
        kind: str = "paste",
        scope: str = "business",
        doc_type: str = "generic",
        channel_scope: str = "all",
        scope_campaign_id: str = "",
        scope_product_id: str = "",
    ) -> dict:
        if not tenant_id:
            return {"ok": False, "reason": "no_tenant"}
        text = (content or "").strip()
        if not text:
            return {"ok": False, "reason": "empty_content"}
        rows = self._store.setdefault(tenant_id, [])
        # naive single-chunk store (tests feed small docs); label by title/doc_type
        rows.append((text, title or doc_type or "kb", doc_type, scope_campaign_id))
        return {"ok": True, "source_id": f"mem-{len(rows)}", "chunks": 1, "embedded": 0, "reason": "fts_only"}

    def retrieve(
        self,
        tenant_id: str,
        query: str,
        *,
        top_k: int = 6,
        scope: str = "",
        channel: str = "all",
        scope_campaign_id: str = "",
        dense: bool = False,
        include_global: bool = True,
    ) -> list[CorpusHit]:
        q = (query or "").strip().lower()
        if not q or not tenant_id:
            return []
        qterms = {t for t in _split_terms(q)}
        if not qterms:
            return []
        candidates: list[tuple[str, str, str, str]] = list(self._store.get(tenant_id, []))
        if include_global:
            candidates += list(self._store.get("_global", []))
        scored: list[tuple[float, CorpusHit]] = []
        for content, source, _doc_type, row_cid in candidates:
            if scope_campaign_id and row_cid and row_cid != scope_campaign_id:
                continue
            terms = set(_split_terms(content.lower()))
            overlap = len(qterms & terms)
            if overlap <= 0:
                continue
            score = overlap / (len(qterms) or 1)
            scored.append((score, CorpusHit(content=content, source=source, score=score, leg="sparse")))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _s, h in scored[: max(1, top_k)]]

    def status(self) -> dict:
        return {"pg_available": True, "sparse_leg": True, "dense_leg": False, "wrapped": False, "in_memory": True}


def _split_terms(s: str) -> list[str]:
    import re

    return [t for t in re.findall(r"[\wऀ-ॿ]+", s or "") if len(t) >= 2]
