"""voice_ops.research.llm_affect — the LLM-as-valence/friction sensor (Upgrade #1).

THE highest accuracy-per-effort change in the whole plan. The deep research is unambiguous: the
Friction/valence axis — the one that actually predicts conversion — is ~80% LINGUISTIC content
(Wagner et al. TPAMI-2023 prove the SSL "valence gap" win is implicit text; AlloSat arXiv:2310.04481
on real 8 kHz telephone: text CCC .92 vs acoustic .81). Prosody-only handcrafted features physically
CANNOT read it. We already run an LLM every turn and already have the transcript — so the cheapest,
strongest upgrade is to let the LLM emit a structured affect/intent read and feed it as the friction
observation z_t, replacing the brittle 12-word lexicon.

Honest guardrails: the LLM read is context-helped but NOT a calibrated oracle (arXiv:2309.12881) and
is prompt-sensitive — so it enters the filter CONFIDENCE-WEIGHTED (as one observation with its own
conf), never as a headline single-turn truth.

Pluggable: pass any `llm(prompt:str)->str` callable (wire the existing Groq/OpenRouter router in
production). With no client it falls back to an improved bilingual (English+Hinglish) heuristic that is
strictly better than the old `_valence_hint` word-count and keeps the module testable offline.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, Optional

LLM_AFFECT_PROMPT = """You are a real-time sales-call affect sensor. Read the CUSTOMER's latest turn \
in context and rate it. Output ONLY compact JSON, no prose:
{"objection":-1..1,"hesitation":-1..1,"price_concern":-1..1,"frustration":-1..1,"buying_intent":-1..1,"label":"<one word>"}
Scale: -1 = clearly absent/opposite, 0 = neutral, 1 = strongly present. "label" is a single word for the turn's stance (e.g. interested, hesitant, objecting, price-resistant, annoyed, neutral, committed).

CONTEXT (recent turns):
{context}

CUSTOMER TURN: "{turn}"
JSON:"""

# heuristic keyword banks (English + Hinglish) — the offline fallback / cold-start path.
_OBJECTION = {"no", "not", "nahi", "nahin", "but", "lekin", "problem", "issue", "won't", "wont",
              "can't", "cannot", "don't", "dont", "naa", "mat", "nope"}
_PRICE = {"expensive", "costly", "cost", "price", "budget", "mehenga", "mehanga", "afford",
          "paisa", "paise", "discount", "cheaper", "emi", "kitna", "kitne", "rate"}
_HESITATION = {"maybe", "later", "think", "sochenge", "sochta", "sochti", "baad", "busy",
               "not sure", "shayad", "dekhenge", "confused", "umm", "hmm", "actually"}
_FRUSTRATION = {"stop", "remove", "annoying", "again", "band", "pareshan", "irritate", "tang",
                "why", "kyun", "kyu", "waste", "bekaar", "useless"}
_INTENT = {"yes", "haan", "interested", "sure", "okay", "ok", "theek", "achha", "great", "perfect",
           "book", "proceed", "want", "chahiye", "karenge", "ready", "done", "lets", "deal"}


def _heuristic(text: str) -> Dict:
    toks = re.findall(r"[a-z'ऀ-ॿ]+", (text or "").lower())
    if not toks:
        return {"objection": 0.0, "hesitation": 0.0, "price_concern": 0.0, "frustration": 0.0,
                "buying_intent": 0.0, "label": "neutral"}
    n = max(4.0, len(toks) ** 0.6)
    def score(bank):
        return max(-1.0, min(1.0, sum(1 for t in toks if t in bank) / n))
    obj, price, hes, fr, intent = (score(_OBJECTION), score(_PRICE), score(_HESITATION),
                                   score(_FRUSTRATION), score(_INTENT))
    label = max(
        [("objecting", obj), ("price-resistant", price), ("hesitant", hes),
         ("annoyed", fr), ("interested", intent), ("neutral", 0.25)],
        key=lambda kv: kv[1])[0]
    return {"objection": obj, "hesitation": hes, "price_concern": price, "frustration": fr,
            "buying_intent": intent, "label": label}


def _to_friction_valence(d: Dict) -> Dict:
    """Map the structured read → a friction observation in Z-UNITS + a valence in [-1,1]. Friction
    blends the resistance signals minus buying intent; the *2.2 scale puts a strong objection near the
    +2σ rail (matching the z-scaled prosody observations the filter already consumes)."""
    obj = float(d.get("objection", 0) or 0)
    hes = float(d.get("hesitation", 0) or 0)
    price = float(d.get("price_concern", 0) or 0)
    fr = float(d.get("frustration", 0) or 0)
    intent = float(d.get("buying_intent", 0) or 0)
    friction_raw = (0.32 * obj + 0.22 * price + 0.20 * hes + 0.20 * fr - 0.30 * intent)
    valence = max(-1.0, min(1.0, intent - 0.5 * obj - 0.4 * fr - 0.2 * price))
    return {
        "llm_friction_z": round(max(-4.0, min(4.0, friction_raw * 2.2)), 4),
        "llm_valence": round(valence, 4),
        "intent": str(d.get("label", "neutral"))[:24],
        "objection": round(obj, 3), "hesitation": round(hes, 3),
        "price_concern": round(price, 3), "buying_intent": round(intent, 3),
    }


def llm_affect_for_turn(
    transcript: str, *, context: str = "", llm: Optional[Callable[[str], str]] = None,
) -> Dict:
    """Return the friction/valence/intent observation for one caller turn. Uses `llm` when provided
    (production wires the Groq/OpenRouter router), else the bilingual heuristic. NEVER raises —
    a bad LLM response falls back to the heuristic. `llm_conf` reflects which path produced it."""
    if llm is not None and (transcript or "").strip():
        try:
            raw = llm(LLM_AFFECT_PROMPT.replace("{context}", (context or "")[:600]).replace("{turn}", transcript[:400]))
            m = re.search(r"\{.*\}", raw or "", re.S)
            if m:
                parsed = json.loads(m.group(0))
                out = _to_friction_valence(parsed)
                out["llm_conf"] = 0.75            # an actual model read — trust it more
                out["source"] = "llm"
                return out
        except Exception:  # noqa: BLE001 — never let the affect sensor break a turn
            pass
    out = _to_friction_valence(_heuristic(transcript))
    out["llm_conf"] = 0.4                          # heuristic floor — weaker, so the filter leans on prior
    out["source"] = "heuristic"
    return out
