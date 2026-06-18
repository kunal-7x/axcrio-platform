"""voice_kernel.context.campaign_compiler — the DUAL-LAYER campaign compiler.

Fixes Founder's #2 complaint: the live path (caller.py:1409 extract_fields +
caller.py:1372 _sanitize_extracted) LOSSY-COMPRESSES the rich vendor brief into a
tiny ~4k-char JSON and the FULL brief is NEVER persisted, so the agent behaves as
if it never read the brochure.

This compiler is RETRIEVAL-OVER-TRUNCATION:

  T0 RAW (lossless)        — the full brief + vendor script + docs, verbatim,
                             carried as a FencedText(CAMPAIGN_BRIEF) and stored
                             behind `raw_script_ref` (a POINTER, never inlined
                             into every prompt).
  T1 FULL-STRUCTURED       — `full_product_summary`, `full_usps` and the full
     (lossless)              objection bank — the lossless distilled layer W4
                             FTS-indexes for mid-call recall.
  T2 COMPACT CARD          — the ≤~900-token in-prompt CampaignCard subset that
     (in-prompt)             ships every turn; `summary_overflow`/`usps_overflow`
                             flag that more is retrievable from `raw_script_ref`.

The compile runs at SAVE-TIME (when a vendor saves/edits a campaign), producing a
`CompiledCampaign` artifact. The hot `ContextEngine.build_card` is then a pure,
sync read of this artifact — no per-turn distillation.

NEVER hardcodes campaign content. Vendor-authored structured fields ALWAYS win
over anything inferred (vendor-authored > inferred). Pure-stdlib; the LLM
distillation hook is OPTIONAL and injected (so tests + the no-key path run with a
deterministic heuristic distiller).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..packet import (
    CampaignCard,
    FencedText,
    Objection,
    SourceTrust,
    fence,
)
from ..tokens import clamp_chars, clamp_list
from .text_hygiene import sanitize
from .understanding import CampaignUnderstanding, classify

# In-prompt soft caps (mirror packet.py central caps — the COMPACT layer only).
_SUMMARY_CHARS = 600
_USPS_MAX = 5
_TALKING_MAX = 5
_QUALIFYING_MAX = 3
_OBJECTIONS_MAX = 6
# Full-text safety clamp (matches live _RAW_SCRIPT_RENDER_MAX) — this is a
# pathological-input guard, NOT lossy compression; real briefs are far under it.
_RAW_MAX = 24000


@dataclass(frozen=True)
class CompiledCampaign:
    """The SAVE-TIME artifact. Persisted per (tenant_id, campaign_id).

    - `raw_fenced`   : T0 lossless brief, ALREADY fenced (CAMPAIGN_BRIEF). The
                       full text the model "behaves like it read".
    - `card`         : T2 compact in-prompt card (with T1 lossless full_* fields
                       carried inside it via the H13 schema).
    - `understanding`: the editable use_case/industry/objective/capabilities.
    - `raw_script_ref`: the POINTER stored on the card so W4 can recall T0.
    """

    tenant_id: str
    campaign_id: str
    raw_fenced: FencedText
    card: CampaignCard
    understanding: CampaignUnderstanding
    raw_script_ref: str = ""
    # provenance for the UI: which card fields came from the vendor vs inferred.
    field_sources: dict = field(default_factory=dict)

    @property
    def full_brief(self) -> str:
        """The lossless full brief text (un-fenced body) — what W4 indexes."""
        return self.raw_fenced.content


# A distiller turns the full brief into a SHORT in-prompt summary. The default is
# a deterministic heuristic (no LLM, no key) so the compiler runs everywhere; a
# later wave can inject a one-shot LLM distiller with the SAME signature.
Distiller = Callable[[str, dict], str]


def _heuristic_distiller(full_brief: str, fields: dict) -> str:
    """Deterministic, dependency-free distiller: prefer the vendor's own
    `product_summary` field; else take the lead paragraph(s) of the brief. NEVER
    invents content — it only selects/truncates the vendor's own words."""
    vendor_summary = str((fields or {}).get("product_summary", "")).strip()
    if vendor_summary:
        return vendor_summary
    # fall back to the opening of the brief (first non-empty paragraph block).
    paras = [p.strip() for p in (full_brief or "").split("\n\n") if p.strip()]
    return paras[0] if paras else ""


def _list_field(fields: dict, key: str) -> tuple[str, ...]:
    v = fields.get(key) or []
    if isinstance(v, str):
        v = [v]
    return tuple(str(x).strip() for x in v if str(x).strip())


def _objections(fields: dict) -> tuple[Objection, ...]:
    out: list[Objection] = []
    for o in fields.get("objections") or []:
        if isinstance(o, dict):
            q, a = str(o.get("q", "")).strip(), str(o.get("a", "")).strip()
            if q or a:
                out.append(Objection(q=q, a=a))
        elif isinstance(o, str) and o.strip():
            out.append(Objection(q=o.strip(), a=""))
    return tuple(out)


def _gather_raw(brief: str, fields: dict) -> str:
    """Build the T0 lossless text: the explicit brief PLUS the vendor `raw_script`
    PLUS any attached docs, concatenated verbatim (sanitized, never clamped-lossy).
    This is what we preserve so the model behaves like it read the WHOLE thing."""
    parts: list[str] = []
    if brief and brief.strip():
        parts.append(brief.strip())
    f = fields or {}
    raw_script = str(f.get("raw_script", "")).strip()
    if raw_script and raw_script not in (brief or ""):
        parts.append(raw_script)
    for doc in f.get("docs") or []:
        text = doc.get("text") if isinstance(doc, dict) else str(doc)
        if text and str(text).strip():
            parts.append(str(text).strip())
    joined = "\n\n".join(parts)
    # sanitize (NFKC + zero-width strip + defang forged fence tags) — lossless.
    cleaned = sanitize(joined)
    # pathological-length guard ONLY (real briefs are far under 24k).
    if len(cleaned) > _RAW_MAX:
        cleaned = cleaned[:_RAW_MAX]
    return cleaned


def compile_campaign(
    *,
    tenant_id: str,
    campaign_id: str,
    brief: str = "",
    fields: Optional[dict] = None,
    distiller: Optional[Distiller] = None,
    understanding: Optional[CampaignUnderstanding] = None,
) -> CompiledCampaign:
    """Ingest a brief + vendor-script + docs into a DUAL-LAYER CompiledCampaign.

    SAVE-TIME entry point. Steps:
      1. Gather T0 lossless raw text (brief + raw_script + docs), sanitized,
         fenced as CAMPAIGN_BRIEF.
      2. Run the Understanding Engine (editable result) if not supplied.
      3. Distill the in-prompt summary (vendor field wins; heuristic fallback).
      4. Build the COMPACT CampaignCard with the H13 lossless full_* fields set
         and overflow flags computed by the COMPILER (so packet.clamp stays
         idempotent), and `raw_script_ref` pointing at T0.

    Vendor-authored structured fields ALWAYS win over inference. NO lossy clamp
    of the full layer — only the in-prompt COMPACT copy is shortened.
    """
    f = dict(fields or {})

    # 1. T0 — lossless raw, fenced ------------------------------------------
    full_text = _gather_raw(brief, f)
    raw_fenced = fence(SourceTrust.CAMPAIGN_BRIEF, full_text)
    raw_script_ref = f"campaign:{campaign_id}#source" if full_text else ""

    # 2. understanding (editable) -------------------------------------------
    und = understanding or classify(full_text, f)

    # 3. distill the in-prompt summary --------------------------------------
    dist = distiller or _heuristic_distiller
    full_summary = sanitize(dist(full_text, f)) or sanitize(str(f.get("product_summary", "")))
    in_prompt_summary = clamp_chars(full_summary, _SUMMARY_CHARS)
    summary_overflow = len(full_summary) > len(in_prompt_summary)

    # 4. USPs — full (lossless) vs in-prompt (compact) ----------------------
    full_usps = _list_field(f, "usps")
    in_prompt_usps = clamp_list(full_usps, _USPS_MAX)
    usps_overflow = len(full_usps) > len(in_prompt_usps)

    # vendor-authored fields win; everything sanitized.
    card = CampaignCard(
        product_name=sanitize(f.get("product_name", "")).strip(),
        product_summary=in_prompt_summary,
        full_product_summary=full_summary,  # T1 lossless
        summary_overflow=summary_overflow,
        location=sanitize(f.get("location", "")).strip(),
        landmark=sanitize(f.get("landmark", "")).strip(),
        price_offer=sanitize(f.get("price_offer", "")).strip(),
        usps=in_prompt_usps,
        full_usps=full_usps,  # T1 lossless
        usps_overflow=usps_overflow,
        talking_points=clamp_list(_list_field(f, "talking_points"), _TALKING_MAX),
        qualifying_questions=clamp_list(_list_field(f, "qualifying_questions"), _QUALIFYING_MAX),
        objections=_objections(f)[:_OBJECTIONS_MAX],
        negotiation_ladder=_list_field(f, "negotiation_ladder"),
        closing_lines=_list_field(f, "closing_lines"),
        escalation_rules=sanitize(f.get("escalation_rules", "")).strip(),
        raw_script_ref=raw_script_ref,  # POINTER to T0 (W4 recall)
        tone=sanitize(f.get("tone", "")).strip(),
        greeting=sanitize(f.get("greeting", "")).strip(),
        language=str(f.get("language", "Hinglish")).strip() or "Hinglish",
        do=_list_field(f, "do"),
        dont=_list_field(f, "dont"),
    )

    field_sources = {
        "product_summary": "vendor" if f.get("product_summary") else "distilled",
        "use_case": und.source,
        "industry": und.source,
        "usps": "vendor" if full_usps else "empty",
    }

    return CompiledCampaign(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        raw_fenced=raw_fenced,
        card=card,
        understanding=und,
        raw_script_ref=raw_script_ref,
        field_sources=field_sources,
    )
