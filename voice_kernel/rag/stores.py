"""voice_kernel.rag.stores — the FOUR logical stores + stage-aware scoping.

RESEARCH-DECISIONS §1-2: a stage-aware voice RAG retrieves from DIFFERENT logical
stores depending on the dialogue stage, and on cheap stages (greet/intro) it
retrieves NOTHING (saves the budget). This module encodes that policy as data:

  RagStore (enum)            — the 4 logical stores.
  STAGE_STORES (dict)        — Stage -> ordered tuple of stores to query.
  scope_for(store)           — the kb/core scope filter + dense flag per store.

The four stores (RESEARCH-DECISIONS §1):
  CAMPAIGN_FACTS   product/price/USP/objection-answers (brochure/FAQ overflow).
                   The L3 card overflow + uploaded PDFs — the founder's "uploaded
                   PDF is not retrieved" bug lives here.
  PLAYBOOK         telecaller technique per stage (objection rebuttals, closing
                   lines). A small, mostly-static, mode-keyed corpus (shared
                   `_global` telecaller knowledge).
  OBJECTION_BANK   Q/A objection answers — separated from facts so an OBJECTION
                   stage can weight it first.
  SLOTS            booking availability — warm, precomputed, near-real-time.

LEAD-MEMORY is deliberately NOT here: it is a separate frozen contract
(MemoryService L4, one PG row at dial). We do not duplicate it. ANALYTICS-ARCHIVE
is offline only and never queried live.

Pure-stdlib (enum/dataclass) — import-safe, no DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..packet import Stage


class RagStore(str, Enum):
    """The four logical stores RagRuntime owns (lead-memory + analytics excluded
    by design — see module docstring)."""

    CAMPAIGN_FACTS = "campaign_facts"
    PLAYBOOK = "playbook"
    OBJECTION_BANK = "objection_bank"
    SLOTS = "slots"


@dataclass(frozen=True)
class StoreScope:
    """How a logical store maps onto the kb/core.retrieve filter args.

    `scope` is the kb_chunks.scope column filter ("" = no filter / business
    default). `doc_type_hint` is appended to the query to bias FTS toward the
    right chunks (kb/core has no doc_type filter param, so we bias the query).
    `include_global` controls the `_global` shared-corpus UNION (playbook lives
    in `_global`; tenant facts do not).
    """

    store: RagStore
    scope: str = ""
    include_global: bool = False
    doc_type_hint: str = ""


# kb/core.retrieve scope mapping per logical store. These are conservative — the
# scope column values match the kb ingest defaults (scope="business" for facts).
_STORE_SCOPES: dict[RagStore, StoreScope] = {
    RagStore.CAMPAIGN_FACTS: StoreScope(RagStore.CAMPAIGN_FACTS, scope="", include_global=False, doc_type_hint=""),
    RagStore.OBJECTION_BANK: StoreScope(RagStore.OBJECTION_BANK, scope="", include_global=True, doc_type_hint="objection"),
    RagStore.PLAYBOOK: StoreScope(RagStore.PLAYBOOK, scope="", include_global=True, doc_type_hint="technique"),
    RagStore.SLOTS: StoreScope(RagStore.SLOTS, scope="", include_global=False, doc_type_hint="slot availability"),
}


def scope_for(store: RagStore) -> StoreScope:
    return _STORE_SCOPES.get(store, StoreScope(store))


# --------------------------------------------------------------------------- #
# STAGE -> STORES policy (RESEARCH-DECISIONS §2)
# --------------------------------------------------------------------------- #
# Ordered: the FIRST store is weighted highest for that stage. Empty tuple =
# retrieve NOTHING this stage (the cheap-stage fast path — return empty in <1ms,
# never spend the 30ms budget). This is the single source of truth the runtime
# reads; it is data, not branching, so it is trivially testable + tunable.
STAGE_STORES: dict[Stage, tuple[RagStore, ...]] = {
    # GREET / PERMISSION / INTRO: scripted openers — NO retrieval (save budget).
    Stage.GREET: (),
    Stage.PERMISSION: (),
    Stage.INTRO: (),
    # QUALIFY: discovery — facts + a light objection bias (pre-empt pushback).
    Stage.QUALIFY: (RagStore.CAMPAIGN_FACTS, RagStore.OBJECTION_BANK),
    # OBJECTION: the heart — objection answers first, then the playbook technique.
    Stage.OBJECTION: (RagStore.OBJECTION_BANK, RagStore.PLAYBOOK, RagStore.CAMPAIGN_FACTS),
    # BOOKING: slots first, then closing facts (price/offer).
    Stage.BOOKING: (RagStore.SLOTS, RagStore.CAMPAIGN_FACTS),
    # CLOSE: closing-line playbook + price facts.
    Stage.CLOSE: (RagStore.PLAYBOOK, RagStore.CAMPAIGN_FACTS),
    # FOLLOWUP: facts (lead-memory is the SEPARATE MemoryService contract).
    Stage.FOLLOWUP: (RagStore.CAMPAIGN_FACTS,),
}


def stores_for_stage(stage: Stage) -> tuple[RagStore, ...]:
    """The ordered stores to query for a stage. Unknown stage -> facts-only
    (safe default). GREET/PERMISSION/INTRO -> () (no retrieval)."""
    return STAGE_STORES.get(stage, (RagStore.CAMPAIGN_FACTS,))


def is_retrieval_stage(stage: Stage) -> bool:
    """True iff this stage should retrieve at all. The cheap-stage gate: the
    runtime returns an empty TurnLayer immediately for a non-retrieval stage,
    never touching the cache or the corpus."""
    return bool(stores_for_stage(stage))
