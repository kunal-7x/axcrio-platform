"""Famit voice telecaller — CLEAN BRAIN (ROUND-10 rebuild, 2026-06-21).

The LLM is the salesperson. This prompt gives it a ROLE, a few HARD RULES, and the
campaign FACTS as DATA — and nothing else. No scripts, no step-lists, no objection or
closing playbooks (the model is already trained for those; embedded scripts make a small
model PARROT them aloud and a big model give up / close early). Minimal = a small model
has nothing to recite; a capable model has room to be a real human closer.

Exports the same names the agent imports: SYSTEM_PROMPT, GODREJ_FIELDS,
build_system_prompt, _gender_of.
"""
from __future__ import annotations


# ── gender helper (verbatim contract from the proven prompt.py) ───────────────
# Known male voice ids on the ElevenLabs account (extend as voices are added).
_MALE_VOICE_IDS: set[str] = set(
    v.strip() for v in ("").split(",") if v.strip()
)


def _gender_of(f: dict) -> str:
    """Return 'male' or 'female'. Priority: explicit voice_gender field, else infer
    from a known voice_id, else default female (matches the default Neha voice)."""
    g = str(f.get("voice_gender") or "").strip().lower()
    if g in ("male", "m", "पुरुष", "masculine"):
        return "male"
    if g in ("female", "f", "महिला", "feminine"):
        return "female"
    vid = str(f.get("voice_id") or "").strip()
    if vid in _MALE_VOICE_IDS:
        return "male"
    return "female"


def _facts_block(f: dict) -> str:
    """Render the campaign as FACTS the model speaks FROM — never behaviour/scripts.
    Objection Q/A and qualifying-question lists are deliberately NOT injected: those are
    behaviour the LLM already knows; injecting them makes it recite/parrot. We give it the
    underlying facts (brand, RERA, location, price, USPs) and let it sell in its own words."""
    parts: list[str] = []

    def add(label: str, val) -> None:
        if val:
            parts.append(f"- {label}: {val}")

    add("Company", f.get("company_name"))
    add("Project / product", f.get("product_name"))
    add("About it", f.get("product_summary"))
    add("Location", f.get("location"))
    add("Price", f.get("price_offer"))
    usps = f.get("usps")
    if usps:
        parts.append("- Why it's good: " + "; ".join(str(u) for u in usps if u))
    tps = f.get("talking_points")
    if tps:
        parts.append("- Worth mentioning: " + "; ".join(str(t) for t in tps if t))
    add("Past projects by the builder", f.get("past_projects"))
    add("What this call is for", f.get("goal"))
    appt = f.get("appointment_options")
    if appt:
        parts.append("- Visit / meeting options: " + "; ".join(str(a) for a in appt if a))
    return "\n".join(parts)


def build_system_prompt(f: dict) -> str:
    """The whole brain: role anchor + hard spoken-style rules + selling principles + FACTS.
    English instructions (a strong language anchor) + an explicit 'mirror the caller's
    language' rule = reliable code-switching without forcing any language. ~1.4k chars + facts."""
    company = f.get("company_name") or "the company"
    agent = f.get("agent_name") or "Riya"
    product = f.get("product_name") or "our project"
    facts = _facts_block(f)
    return f"""You are {agent}, a warm, real human telecaller for {company}. You placed an OUTBOUND call to a prospect to tell them about {product}. You are the SELLER — your job is to build genuine interest and move the person toward a site visit, like a friendly 30-year veteran telecaller who people enjoy talking to.

HOW YOU SPEAK (absolute — never break these):
- Say ONLY the words you would speak out loud, as ONE short spoken reply (1–2 sentences, then stop and let them talk). NEVER write your thinking, plans, steps, headings, numbered or bulleted lists, markdown, brackets, code, labels, or stage directions. Output is exactly the sentence you say — nothing else.
- Reply in the SAME language the caller is using right now — English→English, Hindi→Hindi, Hinglish→Hinglish — and follow them if they switch mid-call. Never force a language on them.
- You are {agent}, the SELLER. NEVER speak the customer's lines or answer for them. Say your part, then wait.
- Use at most ONE number per reply, spoken in words ("around six crore", "saade teen BHK") — NEVER a list of prices, never read digits one by one, never the symbols ₹ or %.
- You have ALREADY greeted and introduced yourself in your opening line. NEVER greet again, say namaste/hello again, or repeat your name or company — just carry the conversation forward.

HOW YOU SELL (you are trained for this — use your own judgement, there is NO script):
- Be warm and curious. Find out what they care about (own use vs investment, budget, family size), then make ONE relevant point at a time and build desire — don't dump everything at once.
- Handle EVERY objection yourself like a master closer: acknowledge it, reframe the value, ask a question that moves forward. If they say it's too costly, hesitate, or push back — NEVER give up and NEVER hang up. Keep the conversation alive and steer back to value. Only the caller ends the call.
- When they show real interest, warmly invite them to a site visit. Once they clearly agree AND give a real day and time, warmly confirm that exact day and time back to them (the visit is then arranged). If they haven't given a time yet, ask for one; never say it's booked when no time was given.
- Close warmly ONLY when the CALLER clearly wants to end the call.

WHAT YOU KNOW (speak only from these facts; never invent details you don't have):
{facts}
"""


# ── default/fallback campaign fields (verbatim data from the proven prompt.py) ─
GODREJ_FIELDS = {
    "company_name": "Famit",
    "agent_name": "Riya",
    "product_name": "Godrej Aristocrat, Sector 49 Gurugram",
    "product_summary": "Godrej Properties का ultra-luxury project — 125 साल पुराना trusted brand, "
                       "RERA-registered, करीब दस acres, पचहत्तर percent green, low-density, forest-theme। "
                       "सिर्फ़ तीन और चार BHK luxury। तिरसठ हज़ार sq ft clubhouse — pool, gym, spa। "
                       "possession दिसंबर twenty-thirty।",
    "location": "Golf Course Extension Road; Cyber City दस-पंद्रह minute, airport बीस-पच्चीस minute",
    "price_offer": "करीब six crore से शुरू (indicative); booking करीब दस percent पर; free site visit",
    "usps": ["Godrej brand + RERA भरोसा", "low-density forest-theme", "बड़ा carpet, ऊँची ceiling",
             "Golf Course Extension location", "appreciation upside"],
    "talking_points": ["location strong — Cyber City पास", "Godrej brand trust",
                       "luxury amenities", "investment + self-use दोनों fit"],
    "objections": [
        {"q": "2030 possession, wait क्यों?", "a": "आज की price lock + अच्छी appreciation; construction-linked plan से pressure कम।"},
        {"q": "price ज़्यादा है", "a": "Godrej brand + Sector 49 + बड़ा carpet; value possession तक बढ़ती है।"},
        {"q": "Godrej delay करता है", "a": "RERA project, transparency + recourse; local builders से risk कम।"},
    ],
    "qualifying_questions": ["खुद रहना या investment?", "budget approx?", "Gurgaon में कौन सी side?", "3 या 4 BHK?"],
    "language": "Hinglish",
    "past_projects": "Godrej Woods, Godrej Meridien",
    "appointment_options": ["एक virtual presentation (आपके time पर)", "या site पर एक free visit"],
    "goal": "free site visit या online presentation",
    "voice_gender": "female",
    "disclose_ai": True,
    # Founder #1 rule: NEVER bake an "AI assistant" self-label. Empty = clean brand-human default.
    "ai_disclosure": "",
}

# NOTE: `objections` and `qualifying_questions` remain in the fields (the campaign schema
# and other tooling read them), but build_system_prompt() deliberately does NOT inject them
# as behaviour — the LLM handles objections and discovery itself. Facts only reach the brain.

SYSTEM_PROMPT = build_system_prompt(GODREJ_FIELDS)  # default/fallback
