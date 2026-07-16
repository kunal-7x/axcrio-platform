"""script_gen — AI drafting of a campaign call-script with Claude Sonnet 3.5 via OpenRouter.

Powers the Script Studio's "Generate with AI" button. Given a campaign's fields (company,
product, USPs, objections, goal, language…) + an optional brief, it asks Claude Sonnet 3.5
(through OpenRouter — the platform's existing LLM gateway, OpenAI-compatible) to write a
natural, spoken-style outbound telecalling script that the operator can then edit/save.

LAWS: import-guarded usage in caller.py; dormant-safe — returns {"ok": False, "error": ...}
(never raises) when OPENROUTER_API_KEY is unset or the call fails, so the panel degrades cleanly.
"""
from __future__ import annotations

import json
import os
import re

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Claude Sonnet via OpenRouter. The operator asked for Sonnet 3.5, but OpenRouter has RETIRED
# 3.5 — its catalogue now only carries claude-sonnet-4/4.5/4.6. We use the latest Sonnet (4.6),
# which is strictly better than 3.5. Override with SCRIPT_GEN_MODEL (any OpenRouter model id).
MODEL = os.getenv("SCRIPT_GEN_MODEL", "anthropic/claude-sonnet-4.6")
MODEL_LABEL = os.getenv("SCRIPT_GEN_MODEL_LABEL", "Claude Sonnet 4.6")

# ── HUMAN-CRAFT ENGINE ───────────────────────────────────────────────────────────────────────────
# The distilled craft that makes a generated script sound like a REAL human telecaller instead of a
# bookish robot. Learned from a live failed call (an 8B runtime collapsed a nuanced prompt into a
# repeated opener + ellipsis tic + formal Hindi + a forced question every turn). We bake the cure
# straight into the drafting model's instructions so EVERY generated line already models good speech
# — the small runtime then has clean, casual, varied lines to imitate. Shared by the full-script and
# per-block generators. Pure text; no behaviour change unless a generator references it.
CRAFT = (
    "HOW EVERY LINE MUST SOUND — this is read ALOUD by a voice agent on a live phone call, so write "
    "SPOKEN words a real person would say, never screen text:\n"
    "- Sound like a warm, real, slightly chatty Indian telecaller — a person, never a bot, never "
    "bookish. The prospect must feel you actually listened to them.\n"
    "- Use natural everyday Hinglish the way real Indian sales reps talk: float English nouns freely "
    "(budget, location, EMI, loan, site visit, possession, ready-to-move, 2 BHK, carpet area, slot, "
    "booking, payment plan) inside short warm Hindi. Write the Hindi parts in DEVANAGARI so the voice "
    "engine pronounces them correctly; keep the English words in English. (If the campaign language "
    "is English, write natural spoken English instead.)\n"
    "- Keep every turn SHORT — one or two sentences — then stop so the prospect can talk. It's a "
    "two-way chat, not a monologue. One point at a time; never dump everything at once.\n"
    "- VARY how lines begin; never start two lines the same way; mostly just start with the point. "
    "NEVER use the opener combo \"अच्छा, ठीक है… देखिए\".\n"
    "- NEVER write \"…\" / \"...\" (ellipsis) and NEVER write \"!\". End lines on \".\" or a single \"?\".\n"
    "- NOT every line is a question. Mix warm statements with the occasional genuine, useful "
    "question — a few real questions across the whole call is plenty. Never tack a question onto "
    "every line.\n"
    "- REACT first: echo the prospect's own words before pitching (e.g. \"एक से दो crore — बढ़िया "
    "range है\"), never a generic \"आपके बजट के अनुसार\".\n"
    "- Numbers spoken in words (\"सवा करोड़\", \"एक से दो crore\") — never digits, \"₹\" or \"Cr\". One "
    "price/config at a time.\n"
    "- Real human warmth + texture: \"हम्म\", \"समझ सकती हूँ\", \"सच कहूँ तो\", a light laugh where it "
    "fits.\n"
    "- NEVER reveal it is an AI / bot / assistant / automated — it is a real person from the brand.\n"
    "- NEVER use bookish/Sanskritised words. Swap them: गोपनीयता→privacy · प्रदान करना→देना/दिखा देंगे · "
    "विकल्प→option · विस्तार से→detail में · चर्चा→बात · शुभ→अच्छा · अनोखा/अद्वितीय→ख़ास/special · "
    "महत्वपूर्ण→ज़रूरी · आरामदायक→सुकून वाला · वातावरण→माहौल. (\"आपका दिन शुभ हो\"→\"आपका दिन अच्छा "
    "जाए\".)\n"
    "- On any objection: never give up and never sign off with \"best of luck\". First genuinely "
    "acknowledge, then show the value, then offer ONE concrete next step (EMI / payment plan / a "
    "smaller unit / a free site visit), and try once more."
)

# Optional operator dials (all default to the warm, standard, balanced baseline — absent => no change).
_TONE = {
    "warm": "Tone: warm and friendly, like a helpful person who genuinely likes the prospect.",
    "professional": "Tone: polished and professional, still warm — confident, never stiff or formal.",
    "energetic": "Tone: upbeat and energetic, a little excited about the product, but never pushy or loud.",
    "calm": "Tone: calm, patient and reassuring — unhurried, lets the prospect think.",
}
_LENGTH = {
    "crisp": "Length: very crisp — the shortest lines that still feel human; trim every spare word.",
    "standard": "Length: short conversational turns (one to two sentences each).",
    "detailed": "Length: a touch more texture per turn (still max two sentences), richer on value points.",
}
_PUSH = {
    "gentle": "Persistence: gentle — offer the next step softly, back off fast if the prospect resists.",
    "balanced": "Persistence: balanced — never give up on the first objection, but stay respectful and warm.",
    "assertive": "Persistence: assertive — confidently drive toward the booking, always offering a next step (still polite, never rude).",
}


def _style(lang: str, tone: str = "", length: str = "", push: str = "") -> str:
    """Combine the craft with the optional operator dials into one directive block. Unknown/blank
    dials fall back to the warm/standard/balanced baseline, so callers that pass nothing get a strong
    default and the result is fully backward-compatible."""
    bits = [CRAFT, f"Speak in: {lang or 'Hinglish'} (follow the language rules above)."]
    bits.append(_TONE.get((tone or "warm").strip().lower(), _TONE["warm"]))
    bits.append(_LENGTH.get((length or "standard").strip().lower(), _LENGTH["standard"]))
    bits.append(_PUSH.get((push or "balanced").strip().lower(), _PUSH["balanced"]))
    return "\n".join(bits)


def _fields_brief(f: dict) -> str:
    """Compact, model-friendly rendering of the campaign fields (only what's set)."""
    def g(k):
        return f.get(k)
    lines = []
    pairs = [
        ("Company", g("company_name")), ("Agent name", g("agent_name")),
        ("Product", g("product_name")), ("Product summary", g("product_summary")),
        ("Location", g("location")), ("Pricing / offer", g("price_offer")),
        ("Language", g("language")), ("Voice gender", g("voice_gender")),
        ("Call goal", g("goal")), ("Past projects", g("past_projects")),
    ]
    for label, v in pairs:
        if v:
            lines.append(f"- {label}: {v}")
    for label, key in [("USPs", "usps"), ("Talking points", "talking_points"),
                       ("Qualifying questions", "qualifying_questions"),
                       ("Appointment options", "appointment_options")]:
        v = g(key)
        if isinstance(v, list) and v:
            lines.append(f"- {label}: " + "; ".join(str(x) for x in v if x))
    obj = g("objections")
    if isinstance(obj, list) and obj:
        lines.append("- Likely objections + responses:")
        for o in obj[:8]:
            if isinstance(o, dict) and (o.get("q") or o.get("a")):
                lines.append(f"    • {o.get('q','')} -> {o.get('a','')}")
    disclose = f.get("disclose_ai", True)
    lines.append(f"- Disclose it's an AI assistant: {'yes' if disclose else 'no (warm human brand intro)'}")
    return "\n".join(lines) if lines else "(no campaign details provided)"


async def generate(fields: dict, brief: str = "", tone: str = "", length: str = "", push: str = "") -> dict:
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "error": "no_openrouter_key",
                "message": "Set OPENROUTER_API_KEY to enable AI script drafting."}
    fields = fields if isinstance(fields, dict) else {}
    lang = str(fields.get("language") or "Hinglish")
    agent = str(fields.get("agent_name") or "Riya")
    company = str(fields.get("company_name") or "the company")

    system = (
        f"You are a master outbound-telecalling script writer. You write the call script for "
        f"'{agent}', a real-sounding human telecaller phoning prospects on behalf of {company}. The "
        f"script is executed LIVE, turn by turn, by a small voice-AI model that IMITATES your lines — "
        f"so the lines themselves must already model perfect, natural, human speech.\n\n"
        + _style(lang, tone, length, push) +
        "\n\nSTRUCTURE it the way a real call flows, as short spoken lines under brief section "
        "headers: (1) a warm opener + identity and a quick two-minute permission ask; (2) one "
        "qualifying question to learn the prospect's real need (khud rehna / investment, size, "
        "budget); (3) a value pitch DRIPPED one point at a time from the USPs, each line reacting to "
        "the prospect; (4) objection handling that acknowledges -> shows value -> offers ONE next "
        "step (using the provided objection responses), never giving up; (5) a warm close that drives "
        "to the call goal — book a free site visit or online presentation and take a date/time; (6) a "
        "graceful opt-out. Where a reply really varies, you may show ONE short example "
        "'caller: … / " + agent + ": …' turn so the runtime has a good line to copy. Use {{lead_name}} "
        "for the prospect's name (filled at call time).\n"
        "Keep the WHOLE script TIGHT and COMPLETE — aim for roughly 1100-1300 tokens; concise beats "
        "long, and it must never get cut off. No markdown tables, no bold, no stage directions in "
        "brackets — just short section headers and the spoken lines. Output ONLY the finished script."
    )
    user = "Campaign details:\n" + _fields_brief(fields)
    if (brief or "").strip():
        user += f"\n\nExtra guidance from the operator (honour this on top of the rules above):\n{brief.strip()[:1500]}"
    user += "\n\nNow write the complete call script, fully finished."

    try:
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": "Bearer " + key,
                    "content-type": "application/json",
                    # optional OpenRouter attribution headers (harmless if ignored)
                    "HTTP-Referer": (os.getenv("PANEL_BASE_URL") or "https://haptica.famit.in"),
                    "X-Title": "Haptica Script Studio",
                },
                json={"model": MODEL, "max_tokens": 2048, "temperature": 0.65,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
            )
        if r.status_code != 200:
            return {"ok": False, "error": f"http_{r.status_code}", "message": (r.text or "")[:200]}
        data = r.json()
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty"}
        return {"ok": True, "script": text, "model": MODEL, "model_label": MODEL_LABEL}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "request_failed", "message": type(exc).__name__}


# ── P7.3: per-block AI assist (Script Studio 2.0) ────────────────────────────────────────────────
# The JSON shape we ask the model to return for ONE block — mirrors the frontend block schema so the
# builder can merge the result straight onto the block.
_BLOCK_SCHEMAS = {
    "greeting": '{"text": "the spoken opener/greeting line(s)"}',
    "qualification": '{"text": "the single most important qualifying question", "items": ["1-3 more short qualifiers"]}',
    "discovery": '{"items": ["3-5 short discovery questions, one per item"]}',
    "objection": '{"qa": [{"q": "a likely objection", "a": "a warm persuasive 1-2 sentence response"}]}',
    "faq": '{"qa": [{"q": "a common question", "a": "a short clear answer"}]}',
    "closing": '{"goal": "the call goal in a few words", "options": ["2-3 appointment / next-step options"]}',
    "followup": '{"text": "a short post-call follow-up note"}',
    "escalation": '{"text": "when and how to hand off to a human"}',
    "condition": '{"text": "a short branching / condition note"}',
}
_TEXT_BLOCKS = ("greeting", "followup", "escalation", "condition")

# What "good" looks like for each block, in the human-craft voice — steers generate_block per type.
_BLOCK_GUIDE = {
    "greeting": "a warm, varied opener + identity (who you are, which brand) and a quick two-minute "
                "permission ask. Friendly, never a stiff script-read.",
    "qualification": "the single most important qualifying question to learn the real need (khud "
                     "rehna / investment, size, budget), plus 1-3 short follow-ups — natural, one at a time.",
    "discovery": "3-5 short, genuinely useful discovery questions that move the deal forward — never "
                 "empty 'how do you feel' filler.",
    "objection": "likely objections with responses that ACKNOWLEDGE the concern, then show value, then "
                 "offer ONE concrete next step (EMI / payment plan / smaller unit / free site visit). "
                 "Never give up, never bookish.",
    "faq": "common questions with short, clear, casual spoken answers.",
    "closing": "the call goal in a few words + 2-3 warm next-step options (free site visit / online "
               "presentation) that take a date and time.",
    "followup": "a short, warm post-call WhatsApp/follow-up note in the same casual voice.",
    "escalation": "when and how to warmly hand off to a human teammate.",
    "condition": "a short, natural branching note.",
}


def _strip_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    return s


def _parse_block_json(text: str) -> dict | None:
    """Extract + validate the first JSON object into a clean block-fields dict. None on failure."""
    m = re.search(r"\{.*\}", _strip_fence(text), re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    out: dict = {}
    if isinstance(d.get("text"), str) and d["text"].strip():
        out["text"] = d["text"].strip()[:1500]
    if isinstance(d.get("items"), list):
        items = [str(x).strip()[:300] for x in d["items"] if str(x).strip()]
        if items:
            out["items"] = items[:8]
    if isinstance(d.get("options"), list):
        opts = [str(x).strip()[:200] for x in d["options"] if str(x).strip()]
        if opts:
            out["options"] = opts[:6]
    if isinstance(d.get("goal"), str) and d["goal"].strip():
        out["goal"] = d["goal"].strip()[:200]
    if isinstance(d.get("qa"), list):
        qa = [{"q": str(p.get("q", "")).strip()[:300], "a": str(p.get("a", "")).strip()[:500]}
              for p in d["qa"]
              if isinstance(p, dict) and (str(p.get("q", "")).strip() or str(p.get("a", "")).strip())]
        if qa:
            out["qa"] = qa[:10]
    return out or None


async def _chat(system: str, user: str, max_tokens: int = 700) -> dict:
    """One OpenRouter chat call. Returns {ok, text} or {ok:False, error,...}. Never raises."""
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "error": "no_openrouter_key",
                "message": "Set OPENROUTER_API_KEY to enable AI drafting."}
    try:
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.post(
                OPENROUTER_URL,
                headers={"Authorization": "Bearer " + key, "content-type": "application/json",
                         "HTTP-Referer": (os.getenv("PANEL_BASE_URL") or "https://haptica.famit.in"),
                         "X-Title": "Haptica Script Studio"},
                json={"model": MODEL, "max_tokens": max_tokens, "temperature": 0.6,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
            )
        if r.status_code != 200:
            return {"ok": False, "error": f"http_{r.status_code}", "message": (r.text or "")[:200]}
        text = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return {"ok": True, "text": text} if text else {"ok": False, "error": "empty"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "request_failed", "message": type(exc).__name__}


async def generate_block(fields: dict, block_type: str, brief: str = "",
                         tone: str = "", length: str = "", push: str = "") -> dict:
    """Draft ONE script block with Claude Sonnet 4.6. Returns {ok, block:{type,...}} where block
    carries only the fields relevant to its type (text / items / qa / options+goal). Dormant-safe."""
    bt = (block_type or "").strip().lower()
    schema = _BLOCK_SCHEMAS.get(bt)
    if not schema:
        return {"ok": False, "error": "unknown_block", "message": f"unknown block type '{bt}'"}
    fields = fields if isinstance(fields, dict) else {}
    lang = str(fields.get("language") or "Hinglish")
    agent = str(fields.get("agent_name") or "Riya")
    company = str(fields.get("company_name") or "the company")
    system = (
        f"You write ONE section ('{bt}') of an outbound call script for '{agent}', a real-sounding "
        f"human telecaller calling on behalf of {company}. The lines are spoken aloud by a voice agent "
        f"and imitated live by a small model, so they must already be perfect, natural human speech.\n\n"
        + _style(lang, tone, length, push) +
        f"\n\nTHIS SECTION ('{bt}'): {_BLOCK_GUIDE.get(bt, 'write this section naturally.')}\n"
        "Use {{lead_name}} for the prospect's name (filled at call time). Return ONLY strict JSON "
        "(no code fence, no prose, no markdown), the spoken lines living inside the JSON values, "
        f"matching EXACTLY this schema: {schema}"
    )
    user = "Campaign details:\n" + _fields_brief(fields)
    if (brief or "").strip():
        user += f"\n\nOperator guidance (honour on top of the rules):\n{brief.strip()[:1000]}"
    user += f"\n\nNow write the '{bt}' section as the JSON above."
    # objection/faq blocks carry several rich q→a pairs; give them room so the JSON never truncates
    # (a cut-off response => invalid JSON => parse_failed). Lighter blocks finish well under this.
    res = await _chat(system, user, max_tokens=1400)
    if not res.get("ok"):
        return res
    text = res.get("text", "")
    block = _parse_block_json(text)
    if block is None and bt in _TEXT_BLOCKS:
        block = {"text": _strip_fence(text)[:1500]}  # plain-text fallback for free-text blocks
    if not block:
        return {"ok": False, "error": "parse_failed", "message": text[:200]}
    block["type"] = bt
    return {"ok": True, "block": block, "model": MODEL, "model_label": MODEL_LABEL}
