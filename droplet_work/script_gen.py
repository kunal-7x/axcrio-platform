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


# ── STYLE FRAMEWORKS ─────────────────────────────────────────────────────────────────────────────
# Validated, proven telecalling/sales/counselling frameworks (research-backed). The campaign picks a
# CATEGORY → the generator injects that framework's flow/questioning/objection/close so the script is
# built like an experienced senior telecaller in that discipline (not a generic pitch).
STYLES = {
    "sales": {"label": "Sales Telecaller", "framework": "AIDA + permission opener",
              "flow": "react to their reply → benefit-anchored reason-for-call (not 'hum X bechte hain') → one-line outcome/social-proof hook → one micro-yes fit check → single clear CTA (two-slot alternative-choice) → confirm + WhatsApp recap",
              "questioning": "minimal, benefit-forward; at most one micro-yes; no interrogation",
              "objection": "acknowledge without agreeing → ONE curious question → respond; Feel-Felt-Found for price; 'no' = not-yet → a booked follow-up",
              "close": "two-slot alternative-choice ('kal 6 baje ya 7?'); assumptive glide to logistics on yes",
              "when": "simple / low-consideration offers, festival or launch promos, single decision-maker"},
    "consultative": {"label": "Consultative Advisor", "framework": "SPIN + Sandler up-front contract",
              "flow": "one-line up-front contract ('do minute, phir aap decide kijiye') → 1 Situation Q → 1 Problem Q → 1 Implication Q (amplify the cost of inaction) → 1 Need-payoff Q (let THEM state the value) → confirm → single capability pitch tied to their stated need → close",
              "questioning": "diagnostic; weight Implication + Need-payoff, light on Situation; react to every answer; 3-4 questions max",
              "objection": "genuine empathy → one solid reframe (brand / location / timing value) → a small next step",
              "close": "Sandler's 3 outcomes only — yes, no, or a clearly-scheduled next step; two-slot for the visit",
              "when": "high-consideration purchases — home, home-loan, insurance, education, B2B"},
    "counselling": {"label": "Counsellor / Support", "framework": "Motivational Interviewing (OARS) + active listening + tactical empathy",
              "flow": "one open question about THEM (not the product) → reflect/paraphrase + label the emotion ('aisa lagta hai thodi jhijhak hai…') → evoke their own reasons for change → light info → one small ask (a WhatsApp follow-up)",
              "questioning": "open kaise/kya (never kyun — sounds accusatory); reflective; listen ~70/30; progress on terse replies",
              "objection": "never push — validate, reflect, support autonomy ('decision poori tarah aapka')",
              "close": "soft — one small next step, never a hard close",
              "when": "sensitive topics (education, healthcare, support) where trust comes first"},
    "followup": {"label": "Customer-Success Follow-up", "framework": "relationship persuasion (Cialdini liking + unity + reciprocity) + MI evoke",
              "flow": "genuine check-in ('ab tak kaisa raha?') → reflect + a specific affirmation (run LAER if a complaint surfaces) → reinforce the value they've already received → a gentle renewal/upsell framed as a benefit they evoke",
              "questioning": "relationship-first open questions + affirmations; listen generously",
              "objection": "LAER (Listen-Acknowledge-Explore-Respond); problem-solving posture",
              "close": "low-pressure: confirm continued value, or a two-slot for a renewal/upsell call",
              "when": "existing customers — renewal, upsell, satisfaction check-in"},
    "appointment": {"label": "Appointment-Setter / Qualifier", "framework": "light BANT + disqualify-not-sell",
              "flow": "disqualify-not-sell framing to drop defences ('aaj kuch bechna nahi, sirf dekhna fit banta hai ya nahi') → reason as an outcome for similar customers → Need Q → 1 Implication Q (urgency) → soft authority + timeline read → two-slot book",
              "questioning": "tight triage, 2-3 questions max; budget framed softly as 'fit', never an early interrogation",
              "objection": "quick reframe → straight back to the slot",
              "close": "two-slot alternative-choice (reframes 'should I?' to 'which one?'); assumptive book",
              "when": "fast qualify-and-book; high lead volume"},
    "collections": {"label": "Polite Collections / Renewal", "framework": "RPC → Reason → Promise-to-Pay + RBI Fair Practices (binding)",
              "flow": "RIGHT-PARTY-CONTACT check FIRST (confirm it's the borrower before any money detail) → reminder/help framing (never a demand) → state the fact as a benefit (amount + due date, avoid the late fee) → ask the reason → offer help (extension / part-pay) → lock the Promise-to-Pay (restate amount + date) → send the payment link",
              "questioning": "respectful and sparse; one calibrated reason question, then listen",
              "objection": "empathy + a concrete help option; NEVER threaten, abuse, or disclose the debt to others",
              "close": "lock the Promise-to-Pay (amount + date), send the link",
              "when": "payment / renewal reminders (compliance-bound; call 8am-7pm only)"},
    "marketing": {"label": "Marketing / Awareness", "framework": "AIDA-lite + curiosity hook + single soft CTA",
              "flow": "a curiosity/benefit hook about the offer → one engaging line of value → one light interest check → ONE soft CTA (send details on WhatsApp / register interest / a callback)",
              "questioning": "one light interest-check; mostly informing, warmly",
              "objection": "keep it light, zero pressure; offer to send info",
              "close": "one soft CTA — send details, register, or a callback",
              "when": "awareness, offers, event invites, broad first-touch outreach"},
}

# 13 universal rules (validated) every generated script must obey — the distilled "don't be a robot".
GLOBAL_RULES = (
    "UNIVERSAL RULES (obey ALL — these are what separate a senior human telecaller from a robot):\n"
    "- The OPENER (greeting + your name + company + purpose + permission) is spoken ONCE at call start by a SEPARATE system. NEVER re-introduce yourself, re-state the company, or re-ask permission anywhere in this script — a second self-intro is the #1 robotic tell. BEGIN the script at the first real move AFTER the prospect responds to the opener.\n"
    "- आप always (never तू/तुम); 'जी' on the name and on yes/no ('Sharma जी', 'haan जी').\n"
    "- Vary acknowledgers (जी / अच्छा / समझ गई / बिल्कुल / हम्म / सही कहा आपने); never reuse the same filler twice in a row.\n"
    "- React, don't recite — every line builds on the prospect's last answer; never fire a rigid scripted row of questions.\n"
    "- NOT every line ends in a question; never three questions in a row; mix warm statements with a few genuine questions.\n"
    "- ONE disarming device only (warmth OR honesty OR permission) — never stack; NEVER open apologetically ('bura time toh nahi?' = proven ~40% booking drop).\n"
    "- Lock the price table: speak only the prices given; never invent a number; never fabricate an EMI figure (say the finance team calculates it on the prospect's numbers).\n"
    "- No markdown, stage directions, speaker labels, or the prospect's lines — only the agent's spoken turns (one short illustrative caller→agent example per varying branch is allowed).\n"
    "- Reply in the prospect's language; if they ask for English, switch fully to spoken English (no Hindi bleed).\n"
    "- Numbers spoken in words; phone digit-by-digit; NEVER reveal it's an AI."
)

OPENER_NOTE = (
    "OPENER FORMAT (generated separately, spoken once — do NOT write it into the script): "
    "'Good [morning/afternoon/evening] [Name] जी, मैं [Company] से [AgentName] बात कर रही हूँ, [purpose], "
    "क्या अभी दो minute बात हो सकती है?'. Your script begins at the first move AFTER the prospect replies to it."
)

# Operator-facing option catalogue (the Script Studio renders these; keys are passed back in `opts`).
GOALS = {
    "book_visit": "Book a site visit / in-person meeting (take a date + time).",
    "qualify": "Qualify the lead (need, budget-fit, timeline) and tag hot/warm/cold.",
    "callback": "Schedule a callback / connect to a human expert.",
    "demo": "Book an online demo / presentation.",
    "signup": "Get a sign-up / registration / form fill.",
    "payment": "Secure a payment / renewal Promise-to-Pay.",
    "info": "Share info and get permission to send details on WhatsApp.",
}
LEAD_WARMTH = {
    "warm": "Warm lead — they already enquired/showed interest; reference that lightly.",
    "cold": "Cold lead — earn attention fast with a benefit hook; no assumed prior interest.",
    "existing": "Existing customer — warm, relationship-first; never a cold intro.",
}


def studio_meta() -> dict:
    """Option catalogue for the Script Studio UI (categories, goals, personas, warmth, dials)."""
    return {
        "categories": [{"id": k, "label": v["label"], "when": v["when"], "framework": v["framework"]}
                       for k, v in STYLES.items()],
        "goals": [{"id": k, "label": v} for k, v in GOALS.items()],
        "lead_warmth": [{"id": k, "label": v} for k, v in LEAD_WARMTH.items()],
        "tones": list(_TONE.keys()), "lengths": list(_LENGTH.keys()), "push": list(_PUSH.keys()),
        "model": MODEL, "model_label": MODEL_LABEL,
    }


def _opts_directives(opts: dict) -> str:
    """Turn the rich Script-Studio options into a directive block: the chosen framework + goal +
    lead-warmth + persona + proof/do/don't + opener purpose. Absent keys are simply skipped."""
    o = opts if isinstance(opts, dict) else {}
    out = []
    st = STYLES.get(str(o.get("category") or "").strip().lower())
    if st:
        out.append(
            f"CALL STYLE — {st['label']} (framework: {st['framework']}). Build the call this way:\n"
            f"- Flow: {st['flow']}\n- Questioning: {st['questioning']}\n"
            f"- Objections: {st['objection']}\n- Close: {st['close']}")
    g = GOALS.get(str(o.get("goal") or "").strip().lower())
    if g:
        out.append(f"PRIMARY GOAL of the call: {g}")
    w = LEAD_WARMTH.get(str(o.get("lead_warmth") or "").strip().lower())
    if w:
        out.append(f"LEAD CONTEXT: {w}")
    persona = str(o.get("persona") or "").strip()
    if persona:
        out.append(f"AGENT PERSONA: {persona[:300]}")
    pp = o.get("proof_points")
    if isinstance(pp, list) and pp:
        out.append("CREDIBILITY / PROOF to weave in (only where natural): " + "; ".join(str(x) for x in pp if x)[:400])
    dos = o.get("must_say")
    if isinstance(dos, list) and dos:
        out.append("MUST mention at least once: " + "; ".join(str(x) for x in dos if x)[:400])
    donts = o.get("never_say")
    if isinstance(donts, list) and donts:
        out.append("NEVER say / avoid: " + "; ".join(str(x) for x in donts if x)[:400])
    purp = str(o.get("opener_purpose") or "").strip()
    if purp:
        out.append(f"OPENER PURPOSE (the [purpose] slot of the separate opener — write the script assuming this was already said): {purp[:200]}")
    return "\n".join(out)


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


async def generate(fields: dict, brief: str = "", tone: str = "", length: str = "", push: str = "",
                   opts: dict | None = None) -> dict:
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "error": "no_openrouter_key",
                "message": "Set OPENROUTER_API_KEY to enable AI script drafting."}
    fields = fields if isinstance(fields, dict) else {}
    lang = str(fields.get("language") or "Hinglish")
    agent = str(fields.get("agent_name") or "Riya")
    company = str(fields.get("company_name") or "the company")
    # opts may also carry tone/length/push (Script Studio dials) — let them override the args.
    opts = opts if isinstance(opts, dict) else {}
    tone = str(opts.get("tone") or tone or "")
    length = str(opts.get("length") or length or "")
    push = str(opts.get("push") or push or "")
    style_block = _opts_directives(opts)
    st_label = STYLES.get(str(opts.get("category") or "").strip().lower(), {}).get("label", "")

    system = (
        "You are a master outbound-telecalling script writer"
        + (f" + a senior {st_label}" if st_label else "")
        + f". You write the call script for '{agent}', a real-sounding human telecaller phoning "
        f"prospects on behalf of {company}. The script is executed LIVE, turn by turn, by a small "
        f"voice-AI model that IMITATES your lines — so the lines must already model perfect, natural, "
        f"human speech.\n\n"
        + _style(lang, tone, length, push)
        + "\n\n" + GLOBAL_RULES
        + "\n\n" + OPENER_NOTE
        + (("\n\n" + style_block) if style_block else "")
        + ("\n\nSTRUCTURE the script as short spoken lines under brief section headers, following the "
           "CALL STYLE flow above and STARTING AFTER the opener. End on the close that drives the "
           "PRIMARY GOAL, then a graceful opt-out."
           if style_block else
           "\n\nSTRUCTURE it as short spoken lines under brief section headers, STARTING AFTER the "
           "opener: (1) react to their reply + one qualifying question for the real need; (2) a value "
           "pitch DRIPPED one point at a time, each line reacting to the prospect; (3) objection "
           "handling — acknowledge → show value → offer ONE next step, never giving up; (4) a warm "
           "close that drives the call goal (book a visit/demo, take a date+time); (5) a graceful opt-out.")
        + " Where a reply really varies, show ONE short 'caller: … / " + agent + ": …' example so the "
        "runtime has a good line to copy. Use {{lead_name}} for the prospect's name (filled at call time).\n"
        "Keep the WHOLE script TIGHT and COMPLETE — roughly 1100-1400 tokens; concise beats long and "
        "it must never get cut off. No markdown tables, no bold, no stage directions — just short "
        "section headers and the spoken lines. Output ONLY the finished script."
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
