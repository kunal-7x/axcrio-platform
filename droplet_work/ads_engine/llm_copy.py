"""ads_engine.llm_copy — the FIRST LLM feature: ad-copy + brief generation. PROPOSAL-ONLY.

Routed entirely through `llm_gateway` (the per-tenant vault-configured reasoning model). This
module owns NO key, NO provider client, NO spend authority. It builds prompts, calls the gateway,
and returns STRUCTURED PROPOSALS the operator reviews — it never mutates a campaign, never
launches, never spends. The moat's deterministic bandit/allocator decide spend; the LLM only
drafts words a human approves.

Two features:
  * generate_ad_copy(tenant_id, brief)  -> N on-brand headline/primary/description triplets +
    a one-line rationale per angle. Hinglish-aware (India real-estate default), RERA-safe nudge.
  * parse_brief(tenant_id, campaign_fields) -> a Partial<AdsBrief>-shaped draft inferred from a
    selected voice campaign's fields (the "stop re-typing the brief" feature).

Every output is fail-closed: if the gateway is not_configured / unavailable the function returns
{ok:False, reason} (the UI renders an empty proposal panel), never a guess and never an exception.
"""

from __future__ import annotations

from typing import Any, Optional

from . import llm_gateway

# Hard ceiling on how many angles we ever ask for (cost + UI sanity).
_MAX_ANGLES = 6

_COPY_SYSTEM = (
    "You are an expert Indian real-estate performance-marketing copywriter. You write ad copy "
    "for Meta/Google/WhatsApp campaigns aimed at Indian home-buyers. Style: crisp, benefit-led, "
    "Hinglish when the brief language is hinglish (Roman script, natural code-mixing), else the "
    "requested language. NEVER write discriminatory housing copy (no exclusion by religion/caste/"
    "marital status/diet) — it is illegal under India's HEC rules. If the brief has a RERA id, "
    "weave it into the description. Output STRICT JSON only, no prose, no markdown fences."
)

_BRIEF_SYSTEM = (
    "You convert a CRM/voice-campaign record into a structured ad brief for a real-estate "
    "performance campaign. Infer sensible defaults for any missing field but never invent a RERA "
    "id or a price you were not given. Output STRICT JSON only."
)


def _angles(brief: dict) -> int:
    try:
        n = int(brief.get("variants") or brief.get("angles") or 3)
    except Exception:  # noqa: BLE001
        n = 3
    return max(1, min(_MAX_ANGLES, n))


def generate_ad_copy(tenant_id: str, brief: dict, *,
                     complete_impl: Optional[Any] = None, **opts: Any) -> dict:
    """Generate N on-brand ad-copy angles for a brief. PROPOSAL-ONLY (no mutation, no spend).

    Returns:
      { ok, angles: [ {headline, primary_text, description, rationale}, ... ],
        provider, model, cost_minor, reason }
    On a gateway miss: { ok:False, angles:[], reason } (not_configured/gateway_unavailable/...).
    """
    brief = brief if isinstance(brief, dict) else {}
    n = _angles(brief)
    product = str(brief.get("product") or brief.get("project") or brief.get("headline") or "").strip()
    if not product and not brief.get("prompt"):
        return {"ok": False, "angles": [], "reason": "empty_brief",
                "provider": "", "model": "", "cost_minor": 0}

    lang = str(brief.get("language") or "hinglish")
    user = (
        f"Brief (JSON): {_compact(brief)}\n\n"
        f"Write {n} DISTINCT ad-copy angles in {lang}. Each angle: a punchy headline (<=40 chars), "
        f"a primary_text (<=125 chars), a description (<=30 words, include the RERA id if present), "
        f"and a one-line rationale explaining the angle. "
        f'Respond as JSON: {{"angles":[{{"headline":"","primary_text":"","description":"",'
        f'"rationale":""}}]}}'
    )
    messages = [{"role": "system", "content": _COPY_SYSTEM},
                {"role": "user", "content": user}]
    res = llm_gateway.complete_json(tenant_id, messages, complete_impl=complete_impl,
                                    trace_name="ads.copy.generate", **opts)
    if not res.get("ok"):
        return {"ok": False, "angles": [], "reason": res.get("reason", "error"),
                "provider": res.get("provider", ""), "model": res.get("model", ""),
                "cost_minor": res.get("cost_minor", 0)}

    angles = _coerce_angles((res.get("data") or {}), n)
    return {
        "ok": True, "angles": angles,
        "provider": res.get("provider", ""), "model": res.get("model", ""),
        "cost_minor": res.get("cost_minor", 0),
        "month_spend_minor": res.get("month_spend_minor", 0),
        "reason": "ok",
    }


def parse_brief(tenant_id: str, campaign_fields: dict, *,
                complete_impl: Optional[Any] = None, **opts: Any) -> dict:
    """Infer a Partial<AdsBrief> draft from a selected voice-campaign's fields. PROPOSAL-ONLY.

    Returns { ok, brief: {...}, source_campaign_id, provider, model, cost_minor, reason }.
    The returned brief is a DRAFT the operator edits in the Run wizard — it is never auto-launched.
    """
    fields = campaign_fields if isinstance(campaign_fields, dict) else {}
    src_id = str(fields.get("id") or fields.get("campaign_id") or "")
    if not fields:
        return {"ok": False, "brief": {}, "reason": "empty_campaign",
                "source_campaign_id": src_id, "provider": "", "model": "", "cost_minor": 0}

    user = (
        f"Voice-campaign record (JSON): {_compact(fields)}\n\n"
        f"Produce an ad brief as JSON with keys: product, headline, primary_text, description, "
        f"language (default hinglish), audience (short string), rera_id (only if present in the "
        f"record, else \"\"), is_property (true for real-estate). Keep it faithful to the record."
    )
    messages = [{"role": "system", "content": _BRIEF_SYSTEM},
                {"role": "user", "content": user}]
    res = llm_gateway.complete_json(tenant_id, messages, complete_impl=complete_impl,
                                    trace_name="ads.brief.parse", **opts)
    if not res.get("ok"):
        return {"ok": False, "brief": {}, "source_campaign_id": src_id,
                "reason": res.get("reason", "error"),
                "provider": res.get("provider", ""), "model": res.get("model", ""),
                "cost_minor": res.get("cost_minor", 0)}

    brief = _coerce_brief((res.get("data") or {}), src_id)
    return {
        "ok": True, "brief": brief, "source_campaign_id": src_id,
        "provider": res.get("provider", ""), "model": res.get("model", ""),
        "cost_minor": res.get("cost_minor", 0),
        "month_spend_minor": res.get("month_spend_minor", 0),
        "reason": "ok",
    }


# ---------------------------------------------------------------------------
# Coercion helpers — defensive parsing of the model's JSON (never trust shape).
# ---------------------------------------------------------------------------
def _coerce_angles(data: dict, n: int) -> list:
    raw = []
    if isinstance(data, dict):
        raw = data.get("angles") if isinstance(data.get("angles"), list) else []
    elif isinstance(data, list):
        raw = data
    out = []
    for a in (raw or [])[:n]:
        if not isinstance(a, dict):
            continue
        out.append({
            "headline": str(a.get("headline") or "")[:120],
            "primary_text": str(a.get("primary_text") or a.get("primary") or "")[:600],
            "description": str(a.get("description") or "")[:400],
            "rationale": str(a.get("rationale") or "")[:300],
        })
    return out


def _coerce_brief(data: dict, src_id: str) -> dict:
    d = data if isinstance(data, dict) else {}
    return {
        "product": str(d.get("product") or "")[:200],
        "headline": str(d.get("headline") or "")[:120],
        "primary_text": str(d.get("primary_text") or d.get("primary") or "")[:600],
        "description": str(d.get("description") or "")[:400],
        "language": str(d.get("language") or "hinglish")[:32],
        "audience": str(d.get("audience") or "")[:200],
        "rera_id": str(d.get("rera_id") or "")[:64],
        "is_property": bool(d.get("is_property", True)),
        "source_campaign_id": src_id,
    }


def _compact(obj: Any, limit: int = 2000) -> str:
    import json as _json
    try:
        s = _json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        s = str(obj)
    return s[:limit]


__all__ = ["generate_ad_copy", "parse_brief"]
