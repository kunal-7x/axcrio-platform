"""kb/seed_global.py — idempotent loader for the shared `_global` telecaller corpus (RAG W2).

WHAT THIS IS
------------
The `_global` corpus is universal, business-neutral TELECALLER BEHAVIOUR — objection handlers,
rapport/backchannel patterns, close techniques, pricing/value framing, vertical product-explainer
scaffolds — Hinglish-first, FTS-keyword-rich. It is READ-SHARED into every tenant's recall via the
`OR tenant_id='_global'` UNION in kb.retrieve (RAG plan §2 rule 2), but WRITE-LOCKED: the kb_chunks
RLS `WITH CHECK` deliberately omits `_global`, so the ONLY path that can insert a `_global` row is one
running under the admin GUC (`app.is_admin='1'`). This loader passes `is_admin=True` to `kb.ingest`,
and is reachable ONLY from the super-admin-gated `POST /kb/seed-telecaller` endpoint (or a hand-run of
this module on the box as the app role) — a tenant request path can NEVER write `_global`.

IDEMPOTENCY (re-run = zero dupes)
---------------------------------
Each corpus ENTRY is ingested as its own kb_source. `kb.ingest` already dedups by
`(tenant_id, checksum)` where `checksum = sha256(content.strip())` — if a source with that checksum
already exists for `_global`, it no-ops (`reason='duplicate_checksum'`) and inserts nothing. So the
loader's idempotency reduces to making each entry's ingested text DETERMINISTIC: we build the chunk
text from a stable template — `# <topic>\n\n<content>\n\nKeywords: <sorted-unique tags>` — so the same
corpus file always hashes the same way. Re-running the seeder (or hitting the endpoint twice) inserts
nothing the second time. Editing one entry's content/tags changes only THAT entry's checksum, so only
that entry re-ingests (as a new source/version) on the next run.

NB: ingest stores ONE source per entry; the per-source checksum is the dedup key. We do NOT delete or
mutate prior rows here (additive/append — safe, RLS-consistent). A future "refresh" that prunes stale
entries is a separate, founder-signed concern (corpus versioning, RAG plan §7-11).

EVENT-LOOP: `kb.ingest` is sync (it may network round-trip for the optional embedder; EMBED_API_KEY is
UNSET on the box so it's FTS-only). The endpoint runs this via `asyncio.to_thread`. NEVER raises ->
returns a summary dict so a partial failure degrades gracefully and is observable.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

GLOBAL_TENANT = "_global"

# the curated corpus lives next to this module (gitignored scratch on the box: kb/seed_global_corpus.json)
_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "seed_global_corpus.json")

# entry topic -> kb doc_type (helps the grounding formatter section/label chunks; default 'objection'
# only for explicit objection_* topics, else a sensible bucket). Purely cosmetic for retrieval ranking.
_DOC_TYPE_HINTS = (
    ("objection", "objection"),
    ("pricing", "pricing"),
    ("price", "pricing"),
    ("product_explainer", "product"),
    ("telecaller_script", "script"),
    ("whatsapp", "faq"),
)


def _doc_type_for(topic: str) -> str:
    t = (topic or "").lower()
    for needle, dt in _DOC_TYPE_HINTS:
        if needle in t:
            return dt
    return "generic"


def _chunk_text_for(entry: dict[str, Any]) -> str:
    """Build the DETERMINISTIC ingested text for one corpus entry.

    Stable across runs -> stable sha256 -> kb.ingest dedups on re-run. We fold the tags into a
    `Keywords:` line so the FTS tsvector ('simple' config, no stemming) covers every keyword the
    chunk author intended — this is what makes the FTS-only (EMBED_API_KEY unset) recall good.
    Tags are sorted+de-duped so reordering the source list never changes the hash."""
    topic = str(entry.get("topic", "") or "").strip()
    content = str(entry.get("content", "") or "").strip()
    tags = entry.get("tags") or []
    # sorted + unique -> deterministic; lower-cased for FTS consistency.
    norm_tags = sorted({str(x).strip().lower() for x in tags if str(x).strip()})
    parts = []
    if topic:
        parts.append(f"# {topic}")
    if content:
        parts.append(content)
    if norm_tags:
        parts.append("Keywords: " + ", ".join(norm_tags))
    return "\n\n".join(parts).strip()


def load_corpus(path: str = "") -> list[dict[str, Any]]:
    """Read + validate the corpus JSON. NEVER raises -> [] on any error. Each entry needs a non-empty
    `content` (topic/tags optional but expected)."""
    p = path or _CORPUS_PATH
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb.seed_global: corpus load failed (%s): %r", p, exc)
        return []
    if not isinstance(data, list):
        logger.warning("kb.seed_global: corpus root is not a list (%s)", p)
        return []
    out: list[dict[str, Any]] = []
    for e in data:
        if isinstance(e, dict) and str(e.get("content", "") or "").strip():
            out.append(e)
    return out


def seed(*, path: str = "", actor: str = "system") -> dict:
    """Idempotently ingest the `_global` telecaller corpus. Returns a summary:
      {ok, tenant, total, ingested, duplicate, failed, chunks, details:[...]}.

    - `ingested`  = entries written this run (new/changed content).
    - `duplicate` = entries already present (checksum match -> no-op) — the steady state on re-run.
    - `failed`    = entries kb.ingest could not write (returns ok=False; surfaced, never fatal).

    NEVER raises. Writes run under is_admin=True (the ONLY path RLS lets write `_global`)."""
    import kb  # the package; lazy import keeps this module import-safe in any context

    summary: dict[str, Any] = {
        "ok": False, "tenant": GLOBAL_TENANT, "total": 0, "ingested": 0,
        "duplicate": 0, "failed": 0, "chunks": 0, "details": [],
    }

    if not kb.available():
        summary["reason"] = "pg_unavailable"
        return summary

    corpus = load_corpus(path)
    summary["total"] = len(corpus)
    if not corpus:
        summary["reason"] = "empty_corpus"
        return summary

    for entry in corpus:
        topic = str(entry.get("topic", "") or "").strip() or "untitled"
        text = _chunk_text_for(entry)
        if not text:
            summary["failed"] += 1
            summary["details"].append({"topic": topic, "result": "empty_text"})
            continue
        doc_type = _doc_type_for(topic)
        # is_admin=True -> writes `_global` (RLS WITH CHECK admin branch). scope='business' (universal,
        # not campaign-bound); channel_scope='all' (behaviour applies to voice + WhatsApp alike).
        res = kb.ingest(
            GLOBAL_TENANT, text,
            title=topic[:300], kind="module", scope="business",
            doc_type=doc_type, channel_scope="all", is_admin=True,
        )
        reason = str(res.get("reason", "") or "")
        if res.get("ok") and reason == "duplicate_checksum":
            summary["duplicate"] += 1
            summary["details"].append({"topic": topic, "result": "duplicate"})
        elif res.get("ok"):
            summary["ingested"] += 1
            summary["chunks"] += int(res.get("chunks", 0) or 0)
            summary["details"].append(
                {"topic": topic, "result": "ingested", "chunks": res.get("chunks", 0)})
        else:
            summary["failed"] += 1
            summary["details"].append({"topic": topic, "result": f"failed:{reason or 'unknown'}"})

    summary["ok"] = summary["failed"] == 0
    logger.info(
        "kb.seed_global by=%s total=%d ingested=%d duplicate=%d failed=%d chunks=%d",
        actor, summary["total"], summary["ingested"], summary["duplicate"],
        summary["failed"], summary["chunks"],
    )
    return summary


# CLI: run on the box as the app role to seed/refresh `_global` without the HTTP endpoint.
#   cd /opt/famit-agent && python -m kb.seed_global
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    result = seed(actor="cli")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, indent=2))
    print(f"details: {len(result.get('details', []))} entries")
