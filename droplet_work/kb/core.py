"""kb/core.py — KB ingest + hybrid retrieval core (import-safe).

Storage = the shared `famit` Postgres (kb_sources/kb_documents/kb_chunks, kb/schema.sql). RLS is the
SAME db.engine.session(tenant_id, is_admin) GUC-in-txn discipline P1 uses everywhere (conn-per-op,
SET LOCAL app.tenant_id -> PgBouncer-safe, no cross-coroutine leak).

HYBRID RETRIEVAL (platform-knowledge-rag §4):
  * SPARSE leg (CORE, keyless): Postgres FTS `fts @@ plainto_tsquery('simple', q)` ranked by ts_rank_cd.
    Works with zero embedder + zero pgvector dense data. This is what makes the ingest->retrieve smoke
    pass today, RLS-scoped, with no external credential.
  * DENSE leg (DORMANT-until-embedder): pgvector `embedding <=> qvec` cosine ANN. Skipped entirely when
    the embedder is not configured (vendors.embeddings.status() != 'configured') or qvec is empty.
  * FUSION: Reciprocal Rank Fusion (RRF, k=60) when BOTH legs return; otherwise whichever leg fired.

EVENT-LOOP SAFETY: the only multi-second cost is embed() (a network round-trip). ingest() is a plain
sync function; its API call site MUST run it off the loop (asyncio.to_thread) — caller's responsibility,
documented at the endpoint. The (few-ms) PG upsert/select run sync on that same thread.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# --- tunables (env-overridable; all default-safe) ---
CHUNK_TOKENS = int(os.getenv("KB_CHUNK_TOKENS", "200") or 200)
CHUNK_OVERLAP = int(os.getenv("KB_CHUNK_OVERLAP", "30") or 30)
RRF_K = int(os.getenv("KB_RRF_K", "60") or 60)
FANOUT = int(os.getenv("KB_FANOUT", "20") or 20)
DEFAULT_TOP_K = int(os.getenv("KB_TOP_K", "6") or 6)
# Include the shared `_global` telecaller corpus in tenant retrieval (read-only UNION). Default ON;
# kill via KB_INCLUDE_GLOBAL=0 -> tenant-only recall (the `_global` poison kill-switch, RAG plan §8).
KB_INCLUDE_GLOBAL = (os.getenv("KB_INCLUDE_GLOBAL", "1") or "1").strip().lower() not in (
    "0", "false", "no", "off", "")
# kb_query_log retention TTL (days). purge_query_log() drops rows older than this.
KB_QUERY_LOG_TTL_DAYS = int(os.getenv("KB_QUERY_LOG_TTL_DAYS", "90") or 90)

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
_schema_ready: bool | None = None


# ============================================================================
# availability
# ============================================================================
def _engine():
    try:
        from db import engine  # type: ignore
        return engine
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    """True iff Postgres is usable (the corpus lives there). Embedder is independent."""
    eng = _engine()
    try:
        return bool(eng and eng.available())
    except Exception:  # noqa: BLE001
        return False


def status() -> dict:
    eng = _engine()
    embed_status = "not_configured"
    try:
        from vendors import embeddings  # type: ignore
        embed_status = embeddings.status()
    except Exception:  # noqa: BLE001
        pass
    return {
        "pg_available": available(),
        "schema_ready": bool(_schema_ready),
        "embedder": embed_status,
        "dense_leg": embed_status == "configured",
        "sparse_leg": True,  # FTS is always on when PG is up
    }


# ============================================================================
# schema bootstrap (famit_app-ownable DDL only; CREATE EXTENSION is provision-time/superuser)
# ============================================================================
def ensure_schema() -> bool:
    """Apply kb/schema.sql idempotently as the app role. Assumes `vector` extension pre-provisioned
    (superuser step). NEVER raises -> returns False on any failure (KB then degrades to no-op)."""
    global _schema_ready
    if _schema_ready:
        return True
    if not available():
        return False
    eng = _engine()
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
            ddl = fh.read()
        # admin GUC so DDL isn't subject to a tenant scope; raw exec of the whole script.
        # Use the RAW DBAPI cursor (not Connection.exec_driver_sql): under SQLAlchemy 2.0.50 the
        # latter forwards its default immutabledict() as `parameters` to psycopg2, which rejects a
        # param-less multi-statement DDL ("immutabledict is not a sequence"). The raw cursor takes
        # the SQL string alone. Schema is fully idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS),
        # so this is safe to (re)run even when every object already exists.
        with eng.session(tenant_id="", is_admin=True) as s:
            raw = s.connection().connection.cursor()
            try:
                raw.execute(ddl)
            finally:
                raw.close()
        _schema_ready = True
        logger.info("kb schema ensured")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.ensure_schema failed (degrade): %r", exc)
        _schema_ready = False
        return False


# ============================================================================
# chunker (section-aware; Devanagari-safe; tiktoken-free char~=token heuristic)
# ============================================================================
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
# ~4 chars/token heuristic -> token budget in chars
_CHARS_PER_TOKEN = 4


def chunk_text(content: str, *, default_section: str = "") -> list[dict[str, Any]]:
    """Split into ~CHUNK_TOKENS chunks with ~CHUNK_OVERLAP overlap, splitting on markdown headings /
    blank lines / sentence boundaries. Returns [{section, content}] in order. Tags `section` from the
    most-recent heading. Robust to empty input -> []."""
    if not content or not content.strip():
        return []
    max_chars = max(120, CHUNK_TOKENS * _CHARS_PER_TOKEN)
    overlap_chars = max(0, CHUNK_OVERLAP * _CHARS_PER_TOKEN)

    # 1) split into (section, block) by headings; blocks broken on blank lines.
    section = default_section
    blocks: list[tuple[str, str]] = []
    buf: list[str] = []
    for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            if buf:
                blocks.append((section, "\n".join(buf).strip()))
                buf = []
            section = m.group(2).strip()[:120]
            continue
        if line.strip() == "":
            if buf:
                blocks.append((section, "\n".join(buf).strip()))
                buf = []
            continue
        buf.append(line)
    if buf:
        blocks.append((section, "\n".join(buf).strip()))

    # 2) pack/split blocks into size-bounded chunks (sentence-aware on overflow).
    out: list[dict[str, Any]] = []
    for sec, block in blocks:
        if not block:
            continue
        if len(block) <= max_chars:
            out.append({"section": sec, "content": block})
            continue
        # overflow: split on sentence boundaries, then greedily pack with overlap.
        parts = re.split(r"(?<=[.!?।])\s+", block)
        cur = ""
        for part in parts:
            if not part:
                continue
            if len(cur) + len(part) + 1 <= max_chars:
                cur = (cur + " " + part).strip()
            else:
                if cur:
                    out.append({"section": sec, "content": cur})
                    tail = cur[-overlap_chars:] if overlap_chars else ""
                    cur = (tail + " " + part).strip() if tail else part
                else:
                    # a single mega-sentence: hard-slice.
                    for i in range(0, len(part), max_chars):
                        out.append({"section": sec, "content": part[i:i + max_chars]})
                    cur = ""
        if cur:
            out.append({"section": sec, "content": cur})
    return out


# word tokens for building an OR tsquery (keeps Devanagari + alnum; drops punctuation)
_WORD_RE = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)


def _or_tsquery_terms(query: str) -> list[str]:
    """Extract content terms from a free-text query for an OR-combined tsquery.

    Under the 'simple' FTS config there is NO stemming, so plainto_tsquery (which ANDs every term)
    misses a doc that has 'priced' when the query says 'price'. The sparse leg of a HYBRID retriever
    is recall-oriented: OR the terms (`a | b | c`) and let ts_rank_cd order by how many terms match,
    so partial overlap still surfaces the chunk and the best chunk ranks first. RRF + the dense leg
    (when configured) then refine precision."""
    toks = [t.lower() for t in _WORD_RE.findall(query or "") if len(t) >= 2]
    # de-dup preserving order; cap to keep the tsquery bounded
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:24]


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _id(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


# ============================================================================
# ingest (chunk -> fts -> optional-embed -> upsert), RLS-scoped, idempotent by source checksum
# ============================================================================
def ingest(tenant_id: str, content: str, *, title: str = "", kind: str = "paste",
           scope: str = "business", doc_type: str = "generic", channel_scope: str = "all",
           scope_campaign_id: str = "", scope_product_id: str = "",
           source_id: str = "", is_admin: bool = False) -> dict:
    """Register a source + document, chunk the content, populate FTS, embed if configured, and upsert
    chunks. Idempotent: if a prior source with the same checksum exists, no-op (returns existing).
    NEVER raises -> {ok, source_id, document_id, chunks, embedded, reason}.

    EVENT-LOOP: call this via asyncio.to_thread from an async handler (embed() may network round-trip).
    """
    if not tenant_id:
        return {"ok": False, "reason": "no_tenant"}
    if not available():
        return {"ok": False, "reason": "pg_unavailable"}
    if not ensure_schema():
        return {"ok": False, "reason": "schema_unavailable"}
    text_in = (content or "").strip()
    if not text_in:
        return {"ok": False, "reason": "empty_content"}

    checksum = _sha256(text_in)
    chunks = chunk_text(text_in)
    if not chunks:
        return {"ok": False, "reason": "no_chunks"}

    # optional dense embeddings (dormant-safe). [] when embedder not configured.
    vecs: list[list[float]] = []
    embedded = 0
    try:
        from vendors import embeddings  # type: ignore
        if embeddings.status() == "configured":
            vecs = embeddings.embed([c["content"] for c in chunks])
            embedded = len(vecs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.ingest embed skipped (degrade): %r", exc)
        vecs = []
        embedded = 0
    use_dense = bool(vecs) and len(vecs) == len(chunks)

    eng = _engine()
    from sqlalchemy import text as _sql
    src_id = source_id or _id()
    doc_id = _id()
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            # idempotency: same tenant + checksum -> reuse, no duplicate corpus.
            existing = s.execute(_sql(
                "SELECT id FROM kb_sources WHERE tenant_id=:t AND checksum=:c LIMIT 1"),
                {"t": tenant_id, "c": checksum}).first()
            if existing:
                return {"ok": True, "source_id": existing[0], "document_id": "",
                        "chunks": 0, "embedded": 0, "reason": "duplicate_checksum"}

            s.execute(_sql(
                "INSERT INTO kb_sources (id,tenant_id,kind,title,scope,channel_scope,status,"
                "kb_version,checksum,data) VALUES (:id,:t,:k,:ti,:sc,:cs,'ready',1,:ck,'{}')"),
                {"id": src_id, "t": tenant_id, "k": kind, "ti": title[:300],
                 "sc": scope, "cs": channel_scope, "ck": checksum})
            s.execute(_sql(
                "INSERT INTO kb_documents (id,tenant_id,source_id,doc_type,title,scope,"
                "scope_campaign_id,scope_product_id,kb_version,data) "
                "VALUES (:id,:t,:s,:dt,:ti,:sc,:cid,:pid,1,'{}')"),
                {"id": doc_id, "t": tenant_id, "s": src_id, "dt": doc_type, "ti": title[:300],
                 "sc": scope, "cid": scope_campaign_id, "pid": scope_product_id})

            for i, ch in enumerate(chunks):
                emb = vecs[i] if use_dense else None
                emb_param = ("[" + ",".join(str(x) for x in emb) + "]") if emb is not None else None
                s.execute(_sql(
                    "INSERT INTO kb_chunks (tenant_id,document_id,source_id,chunk_idx,content,section,"
                    "doc_type,scope,channel_scope,scope_campaign_id,scope_product_id,tokens,"
                    "embedding,fts,kb_version) VALUES "
                    "(:t,:d,:s,:idx,:c,:sec,:dt,:sc,:cs,:cid,:pid,:tok,"
                    "CAST(:emb AS vector),to_tsvector('simple',:c),1)"),
                    {"t": tenant_id, "d": doc_id, "s": src_id, "idx": i, "c": ch["content"],
                     "sec": ch.get("section", "")[:120], "dt": doc_type, "sc": scope,
                     "cs": channel_scope, "cid": scope_campaign_id, "pid": scope_product_id,
                     "tok": max(1, len(ch["content"]) // _CHARS_PER_TOKEN), "emb": emb_param})
        logger.info("kb.ingest tenant=%s chunks=%d embedded=%d", tenant_id, len(chunks), embedded)
        return {"ok": True, "source_id": src_id, "document_id": doc_id,
                "chunks": len(chunks), "embedded": embedded,
                "reason": "embedded" if use_dense else "fts_only"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.ingest failed: %r", exc)
        return {"ok": False, "reason": f"error:{type(exc).__name__}"}


# ============================================================================
# retrieve (hybrid; FTS core + dense dormant; RLS-scoped; provenance on every chunk)
# ============================================================================
def retrieve(tenant_id: str, query: str, *, top_k: int = DEFAULT_TOP_K,
             scope: str = "", channel: str = "all", scope_campaign_id: str = "",
             dense: bool = False, include_global: bool = True,
             is_admin: bool = False) -> list[dict]:
    """Hybrid retrieve up to top_k chunks for a tenant. Each result:
    {content, section, document_id, source_id, score, leg}. RLS-scoped (own tenant + the shared
    `_global` corpus when include_global). [] when PG unavailable / no query / no hits -> callers
    no-op gracefully. NEVER raises.

    LATENCY CONTRACT (RAG plan C-3 — the load-bearing one):
      * `dense=False` (the DEFAULT) makes ZERO network calls — no embeddings.status(), no embed().
        The reply-path sites (`lookup`, `pick_campaign` re-ground) pass dense=False FOREVER, so an
        EMBED_API_KEY flip can NEVER drop a 40-200ms embed RTT into the mid-call loop.
      * `dense=True` is connect-prefetch-ONLY (W4 grounding_cache), inside the SIP connect window,
        one embed/call max. Even then it no-ops cleanly if the embedder is `not_configured`.

    `_global` UNION: when include_global (and the KB_INCLUDE_GLOBAL env default), the shared telecaller
    corpus is folded in via an EXPLICIT `OR tenant_id='_global'` predicate, evaluated UNDER the caller's
    own `is_admin=False` GUC — never a `%` wildcard, never is_admin=True on a voice read. The kb_chunks
    RLS USING policy permits `_global` reads; its WITH CHECK does not (read-shared / write-locked)."""
    q = (query or "").strip()
    if not q or not tenant_id or not available():
        return []
    eng = _engine()
    from sqlalchemy import text as _sql
    use_global = bool(include_global) and KB_INCLUDE_GLOBAL

    # optional dense query vector — gated behind `dense` so the FTS-only default makes ZERO network
    # calls (no embeddings.status(), no embed()). dense=True is connect-prefetch-only (C-3).
    qvec: list[float] | None = None
    if dense:
        try:
            from vendors import embeddings  # type: ignore
            if embeddings.status() == "configured":
                ev = embeddings.embed([q])
                if ev:
                    qvec = ev[0]
        except Exception:  # noqa: BLE001
            qvec = None

    # OR-combined tsquery for the recall-oriented sparse leg (see _or_tsquery_terms).
    terms = _or_tsquery_terms(q)
    tsq = " | ".join(terms)  # safe: terms are [\w Devanagari]+ only, no tsquery metachars

    # optional scope filter (business / campaign:<id> / etc.) — applied to both legs
    scope_sql = ""
    params_common: dict[str, Any] = {"fan": FANOUT, "ch": channel}
    if scope:
        scope_sql += " AND scope = :scope"
        params_common["scope"] = scope
    if scope_campaign_id:
        scope_sql += " AND (scope_campaign_id = :cid OR scope_campaign_id = '')"
        params_common["cid"] = scope_campaign_id

    # `_global` UNION — fold the shared telecaller corpus into this tenant's recall via an EXPLICIT
    # `OR tenant_id='_global'` predicate, under the caller's own is_admin=False GUC. NEVER a `%`
    # wildcard; NEVER is_admin=True on a voice read. RLS still gates every other tenant out (the only
    # rows this opens are the caller's own + `_global`). When include_global is off, retrieval is
    # tenant-only (own-tenant rows only). The leading "AND" closes the WHERE the legs already opened.
    # When include_global is OFF, we must NOT rely on RLS alone to exclude `_global`: the kb_chunks
    # RLS USING policy READ-SHARES `_global` (own tenant OR `_global`), so a predicate-less WHERE under
    # a tenant GUC would still surface `_global` rows. The KB_INCLUDE_GLOBAL=0 poison kill-switch
    # (RAG plan §8: "OFF -> tenant-only retrieval") is therefore enforced HERE with an explicit
    # `tenant_id = :selftid` predicate that pins recall to own-tenant rows only.
    tenant_sql = " AND tenant_id = :selftid"
    params_common["selftid"] = tenant_id
    if use_global:
        tenant_sql = " AND (tenant_id = :selftid OR tenant_id = '_global')"

    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            # SPARSE leg (FTS) — always runs (core, keyless). OR-of-terms via to_tsquery; rank by
            # ts_rank_cd so the chunk matching the MOST query terms ranks first.
            sparse_rows = []
            if tsq:
                sp = dict(params_common, tsq=tsq)
                sparse_rows = s.execute(_sql(
                    "SELECT id, content, section, document_id, source_id, "
                    "ts_rank_cd(fts, to_tsquery('simple', :tsq)) AS rank "
                    "FROM kb_chunks "
                    "WHERE fts @@ to_tsquery('simple', :tsq) "
                    "AND (channel_scope = 'all' OR channel_scope = :ch)"
                    + scope_sql + tenant_sql + " "
                    "ORDER BY rank DESC LIMIT :fan"),
                    sp).fetchall()

            dense_rows = []
            if qvec is not None:
                p = dict(params_common)
                p["qv"] = "[" + ",".join(str(x) for x in qvec) + "]"
                dense_rows = s.execute(_sql(
                    "SELECT id, content, section, document_id, source_id, "
                    "(embedding <=> CAST(:qv AS vector)) AS dist "
                    "FROM kb_chunks "
                    "WHERE embedding IS NOT NULL "
                    "AND (channel_scope = 'all' OR channel_scope = :ch)"
                    + scope_sql + tenant_sql + " "
                    "ORDER BY embedding <=> CAST(:qv AS vector) ASC LIMIT :fan"),
                    p).fetchall()

        # --- fuse with RRF (or pass through whichever leg fired) ---
        fused: dict[int, dict] = {}

        def _add(rows, leg: str):
            for rank, row in enumerate(rows):
                cid = int(row[0])
                rec = fused.setdefault(cid, {
                    "content": row[1], "section": row[2], "document_id": row[3],
                    "source_id": row[4], "score": 0.0, "leg": leg})
                rec["score"] += 1.0 / (RRF_K + rank + 1)
                if leg not in rec["leg"]:
                    rec["leg"] = rec["leg"] + "+" + leg

        _add(sparse_rows, "sparse")
        _add(dense_rows, "dense")
        ranked = sorted(fused.values(), key=lambda r: r["score"], reverse=True)
        return ranked[: max(1, top_k)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.retrieve failed (return []): %r", exc)
        return []


# ============================================================================
# kb_query_log — observed-query logging (knowledge-gap loop) + retention TTL
#   FORCE-RLS, strictly per-tenant (no `_global` share). Write is BEST-EFFORT and MUST be off the
#   voice hot path: call via asyncio.to_thread / fire-and-forget from the caller — NEVER on the
#   per-turn reply loop (it opens a PG round-trip). NEVER raises.
# ============================================================================
def log_query(tenant_id: str, query: str, *, channel: str = "all", scope_campaign_id: str = "",
              grounded: bool = False, leg: str = "", top_ids: list | None = None,
              is_admin: bool = False) -> bool:
    """Record one observed retrieval query for the knowledge-gap loop. Tenant-scoped under RLS.
    Best-effort: returns False (never raises) on any failure so a logging miss can't break a call."""
    if not tenant_id or not (query or "").strip() or not available():
        return False
    if not ensure_schema():
        return False
    eng = _engine()
    from sqlalchemy import text as _sql
    import json as _json
    try:
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
            s.execute(_sql(
                "INSERT INTO kb_query_log (tenant_id,query,channel,scope_campaign_id,grounded,leg,top_ids) "
                "VALUES (:t,:q,:ch,:cid,:g,:leg,CAST(:ids AS jsonb))"),
                {"t": tenant_id, "q": (query or "").strip()[:2000], "ch": channel,
                 "cid": scope_campaign_id, "g": bool(grounded), "leg": leg,
                 "ids": _json.dumps([str(x) for x in (top_ids or [])])})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.log_query failed (degrade): %r", exc)
        return False


def purge_query_log(*, ttl_days: int | None = None) -> int:
    """Retention TTL sweep: delete kb_query_log rows older than ttl_days (default KB_QUERY_LOG_TTL_DAYS).
    Run under admin GUC (cross-tenant housekeeping, e.g. a daily Hatchet cron). Returns rows deleted
    (0 on any failure). NEVER raises. This bounds the PII liability of the raw-query log."""
    days = int(ttl_days if ttl_days is not None else KB_QUERY_LOG_TTL_DAYS)
    if days <= 0 or not available():
        return 0
    if not ensure_schema():
        return 0
    eng = _engine()
    from sqlalchemy import text as _sql
    try:
        with eng.session(tenant_id="", is_admin=True) as s:
            res = s.execute(_sql(
                "DELETE FROM kb_query_log WHERE created_at < now() - make_interval(days => :d)"),
                {"d": days})
            return int(res.rowcount or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.purge_query_log failed: %r", exc)
        return 0
