"""voice_kernel.memory — W7 structured LEAD MEMORY (the MemoryService L4 home).

Lead-centric (not call-centric) memory: replace a 500-telecaller team with a
system that REMEMBERS every lead across calls + WhatsApp.

  * hot/warm/cold split          — service.LeadMemoryService (cache + PG + COLD writes)
  * salient-facts extraction     — extraction.extract_rules / extract_with_llm
  * lifecycle + conversion score — lifecycle.classify_lifecycle / conversion_probability
  * AI summary card + NBA        — cards.build_summary_card / next_best_action_*
  * conversation continuity      — continuity.apply_lead_memory / continuity_opener_hint
  * right-to-erasure cascade     — erasure.LeadMemoryEraser (+ Purgeable protocol)
  * FORCE-RLS schema             — ddl_lead_memory.sql

Registered via the FROZEN factory:  build_kernel(cfg, memory=LeadMemoryService())

Imports NOTHING from droplet_work.agent / caller.py / aim_voice_agent.py.
"""
from __future__ import annotations

from .cache import LeadMemoryCache
from .cards import LeadCard, build_summary_card, next_best_action_llm, next_best_action_rules
from .continuity import apply_lead_memory, continuity_opener_hint, has_history
from .erasure import LeadMemoryEraser, Purgeable
from .extraction import extract_rules, extract_with_llm, prob_for
from .lifecycle import classify_lifecycle, classify_with_llm, conversion_probability
from .service import LeadMemoryService

__all__ = [
    "LeadMemoryService",
    "LeadMemoryCache",
    "LeadMemoryEraser",
    "Purgeable",
    "LeadCard",
    "build_summary_card",
    "next_best_action_rules",
    "next_best_action_llm",
    "apply_lead_memory",
    "continuity_opener_hint",
    "has_history",
    "extract_rules",
    "extract_with_llm",
    "prob_for",
    "classify_lifecycle",
    "classify_with_llm",
    "conversion_probability",
]
