"""Famit voice agent — native livekit-agents (NO pipecat).

Sarvam STT -> Groq LLM (single system prompt) -> ElevenLabs flash TTS, Silero VAD.
The LLM greets and runs the whole call from prompt.SYSTEM_PROMPT. Nothing hardcoded.

Run: python agent.py start   (registers with LiveKit as agent_name "capsy")
Env: /opt/famit-agent/.env
"""

from __future__ import annotations

import asyncio
import datetime as _datetime_module
import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli
from livekit.plugins import elevenlabs, groq, sarvam, silero
from livekit.plugins.elevenlabs import VoiceSettings

import memory as mem
from prompt import SYSTEM_PROMPT, GODREJ_FIELDS, build_system_prompt, _gender_of
# Founder #1 rule (NEVER self-label as AI/assistant/bot): reuse prompt.py's
# banned-phrase check (which itself prefers the voice_kernel block-list, single
# source of truth). Used to SCRUB the generated opener at the output boundary so a
# hallucinated "AI assistant" line can never reach the wire.
from prompt import _contains_banned_self_label as _opener_has_banned_label

# P2: per-turn language auto-detect + mirror (cheap heuristic; never breaks a call).
try:
    import langdetect as ld
except Exception:  # noqa: BLE001 — agent must run even if the module is missing
    ld = None

load_dotenv("/opt/famit-agent/.env")
load_dotenv(".env")

logger = logging.getLogger("famit-agent")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "capsy")
VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))
CAMPAIGN_DIR = Path(os.getenv("CAMPAIGN_DIR", str(VAR / "campaigns")))
TRANSCRIPT_DIR = VAR / "transcripts"
# WAVE A Unit1: per-call vendor metering. The agent runs as a SEPARATE process from
# the caller (no shared asyncio.Lock), and many calls run concurrently, so to avoid
# clobbering a single shared JSON we drop one file per ROOM into usage_events_raw/.
# The caller's scheduler drains these into var/usage_events.json (contention-free).
USAGE_RAW_DIR = VAR / "usage_events_raw"

# Vendor rate cards (configurable via env; Sarvam/Groq have NO billing API → estimated).
# Sarvam: STT ₹30/hour, Bulbul v3 TTS ₹30/10k chars.
SARVAM_STT_RATE_PER_HR = float(os.getenv("SARVAM_STT_RATE_PER_HR", "30") or 30)
SARVAM_TTS_RATE_PER_10K = float(os.getenv("SARVAM_TTS_RATE_PER_10K", "30") or 30)
# Groq: priced per million tokens (sensible defaults for llama-4-scout; override via env).
GROQ_RATE_IN_PER_MTOK = float(os.getenv("GROQ_RATE_IN_PER_MTOK", "0.11") or 0.11)
GROQ_RATE_OUT_PER_MTOK = float(os.getenv("GROQ_RATE_OUT_PER_MTOK", "0.34") or 0.34)
# ElevenLabs Flash v2.5 ≈ 0.5 credit/char; rupee/char only used as a hint (workspace
# analytics is the authoritative source). Default conservatively; override via env.
EL_RATE_PER_1K_CHARS = float(os.getenv("EL_RATE_PER_1K_CHARS", "1.5") or 1.5)
# USD→INR for any vendor priced in USD (Groq token defaults above are already in INR-ish
# small units; keep a knob in case rates are entered in USD).
USD_INR = float(os.getenv("USD_INR", "1") or 1)


# ── GROQ key round-robin ──────────────────────────────────────────────────────
# Free-tier Groq keys queue under load → occasional 3-4s TTFT spikes (seen on live
# calls). Spreading load across SEVERAL keys cuts queueing/429. We round-robin a
# key PER CALL (the per-call groq.LLM + the two httpx scout calls each pick the
# next key), so concurrent calls don't all hammer one key. Keys come from env:
#   GROQ_API_KEY  (required, the existing one) + GROQ_API_KEY_2 / _3 (optional).
# SAFE NO-OP on a single key: rotation just keeps returning that one key, so
# behaviour is byte-identical to before until you add _2/_3 to /opt/famit-agent/.env
# (no code change needed to activate). Keys are MASKED in every log line.
import itertools as _itertools  # noqa: E402
import threading as _threading  # noqa: E402

def _collect_groq_keys() -> list[str]:
    keys: list[str] = []
    for _name in ["GROQ_API_KEY"] + [f"GROQ_API_KEY_{_i}" for _i in range(2, 21)]:
        v = (os.getenv(_name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys

_GROQ_KEYS = _collect_groq_keys()
_GROQ_CYCLE = _itertools.cycle(_GROQ_KEYS) if _GROQ_KEYS else None
_GROQ_LOCK = _threading.Lock()

def _mask_key(k: str) -> str:
    if not k:
        return "<none>"
    return (k[:6] + "…" + k[-4:]) if len(k) > 12 else "<short>"

def _next_groq_key() -> str:
    """Round-robin the next Groq API key (thread-safe). Falls back to the single
    GROQ_API_KEY / env if no keys were collected. Never raises."""
    try:
        if _GROQ_CYCLE is not None:
            with _GROQ_LOCK:
                return next(_GROQ_CYCLE)
    except Exception:  # noqa: BLE001 — never break a call over key selection
        pass
    return (os.getenv("GROQ_API_KEY") or "").strip()

def _collect_sarvam_keys() -> list[str]:
    keys: list[str] = []
    for _name in ["SARVAM_API_KEY"] + [f"SARVAM_API_KEY_{_i}" for _i in range(2, 21)]:
        v = (os.getenv(_name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys

_SARVAM_KEYS = _collect_sarvam_keys()
_SARVAM_CYCLE = _itertools.cycle(_SARVAM_KEYS) if _SARVAM_KEYS else None
_SARVAM_LOCK = _threading.Lock()

def _next_sarvam_key() -> str:
    """Round-robin next Sarvam API key (thread-safe). Falls back to SARVAM_API_KEY. Never raises."""
    try:
        if _SARVAM_CYCLE is not None:
            with _SARVAM_LOCK:
                return next(_SARVAM_CYCLE)
    except Exception:
        pass
    return (os.getenv("SARVAM_API_KEY") or "").strip()


def _write_usage_raw(room: str, events: list[dict]) -> None:
    """Write this call's accumulated usage events to one per-room file. Best-effort;
    a metering failure must NEVER break the call."""
    try:
        if not room or not events:
            return
        USAGE_RAW_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in room if ch.isalnum() or ch in "-_")
        (USAGE_RAW_DIR / f"{safe}.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("usage_raw write failed room=%s err=%r", room, exc)


def _load_campaign(campaign_id: str) -> dict | None:
    """Load a per-call campaign {fields, system_prompt} written by the Caller. Never raises."""
    try:
        cid = "".join(ch for ch in (campaign_id or "") if ch.isalnum() or ch in "-_")
        p = CAMPAIGN_DIR / f"{cid}.json"
        if cid and p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("campaign load failed id=%s err=%r", campaign_id, exc)
    return None


def _summarize(turns: list[dict]) -> dict:
    """One Groq call → {summary, outcome, interest, next_action, opt_out, callback_at, callback_raw}.

    opt_out: caller asked to be removed / not called again (DND).
    callback_at: absolute IST datetime (ISO) the caller asked to be called back, else "".
    callback_raw: the spoken phrase ("kal subah", "5 baje") that produced callback_at.
    """
    base = {"summary": "", "outcome": "no_answer", "interest": 0, "next_action": "",
            "opt_out": False, "callback_at": "", "callback_raw": ""}
    convo = "\n".join(f"{t.get('role')}: {t.get('content')}" for t in turns if t.get("content"))[:4000]
    if not convo.strip():
        return base
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    now_ist = _dt.now(_tz(_td(hours=5, minutes=30)))
    now_str = now_ist.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + _next_groq_key()},
            json={"model": os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                  "temperature": 0.1, "max_tokens": 300,
                  "response_format": {"type": "json_object"},
                  "messages": [
                      {"role": "system", "content": (
                          "You are a sales-QA assistant. The current IST time is " + now_str + ". "
                          "Given a Hinglish real-estate tele-call transcript, return ONLY JSON: "
                          "{\"summary\": one-line English summary, "
                          "\"outcome\": one of [interested,not_interested,callback,no_answer,"
                          "wrong_number,answered,opt_out], "
                          "\"interest\": integer 0-100, "
                          "\"next_action\": short next step, "
                          "\"opt_out\": true if the caller asked NOT to be called again / remove / "
                          "do-not-call / 'dobara call mat karna', else false, "
                          "\"callback_at\": if the caller asked to be called back at a specific time, "
                          "resolve it to an ABSOLUTE IST datetime in ISO format "
                          "YYYY-MM-DDTHH:MM:SS relative to the current IST time above; else \"\", "
                          "\"callback_raw\": the exact spoken time phrase, else \"\"}.")},
                      {"role": "user", "content": convo},
                  ]},
            timeout=12,
        )
        d = json.loads(r.json()["choices"][0]["message"]["content"])
        opt_out = bool(d.get("opt_out", False))
        outcome = d.get("outcome", "answered")
        if opt_out:
            outcome = "opt_out"
        return {"summary": str(d.get("summary", ""))[:300], "outcome": outcome,
                "interest": int(d.get("interest", 0) or 0),
                "next_action": str(d.get("next_action", ""))[:200],
                "opt_out": opt_out,
                "callback_at": str(d.get("callback_at", "") or "")[:25],
                "callback_raw": str(d.get("callback_raw", "") or "")[:80]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("summary failed: %r", exc)
        return {**base, "outcome": "answered"}
def _llm_opener(agent_name: str, company: str, product: str, lead_name: str,
                gender: str = "female", disclose: bool = True,
                disclosure_phrase: str = "") -> str:
    """LLM-authored opening line, per-campaign + by-name, delivered via session.say().
    Identity + company + product NAME + 'abhi free?' — NO pitch. Falls back to a fixed line.
    P2: gender drives the Hindi verb form (no hardcoded feminine); AI disclosure is
    campaign-configurable (kept by default for TRAI; `disclose=False` drops it)."""
    name_part = f"{lead_name} जी, " if lead_name else ""
    speaking = "बोल रहा हूँ" if gender == "male" else "बोल रही हूँ"
    # Founder #1 rule: NEVER self-label as "AI"/"assistant". The default disclosure is
    # brand-human framing ("{company} की तरफ़ से") — a campaign MAY pass a custom phrase,
    # but it is SCRUBBED below (a banned self-label collapses to the clean brand form).
    _raw_disc = (disclosure_phrase or f"{company} की तरफ़ से").strip()
    disc_phrase = _raw_disc if not _opener_has_banned_label(_raw_disc) else f"{company} की तरफ़ से"
    # Fallback line (used if the LLM opener call fails) — gender-correct + brand-human disclosure.
    if disclose:
        fallback = (f"नमस्ते {name_part}…! मैं {agent_name}, {disc_phrase} {speaking}। "
                    f"{product} के बारे में बात करनी थी — क्या अभी दो minute बात हो सकती है?")
    else:
        fallback = (f"नमस्ते {name_part}…! मैं {agent_name}, {company} से {speaking}। "
                    f"{product} के बारे में बात करनी थी — क्या अभी दो minute बात हो सकती है?")
    try:
        gender_clause = ("Hindi में अपने बारे में पुल्लिंग (masculine) रूप इस्तेमाल करो "
                         "('बोल रहा हूँ', 'बताता हूँ')। ") if gender == "male" else (
                         "Hindi में अपने बारे में स्त्रीलिंग (feminine) रूप इस्तेमाल करो "
                         "('बोल रही हूँ', 'बताती हूँ')। ")
        disc_clause = (f"अपना naam {agent_name} बता कर {disc_phrase}, एक warm इंसान की तरह अपना परिचय "
                       f"दो (छोटा रखो, robotic नहीं) — कभी अपने आप को 'AI'/'assistant'/'bot'/'automated' "
                       f"मत कहना, और "
                       if disclose else
                       f"अपना naam {agent_name} बता कर {disc_phrase} natural रहो — कभी 'AI'/'assistant'/"
                       f"'bot'/'automated' मत कहना, फिर ")
        sysmsg = (
            f"तुम {agent_name} हो, {company} की telecaller। एक बहुत छोटी (15-25 शब्द), गर्मजोशी "
            f"वाली एक-line opener दो — बोलचाल की Hinglish में, Hindi Devanagari में। " + gender_clause
            + (f"caller का naam '{lead_name}' लेकर greet करो (जैसे 'नमस्ते {lead_name} जी…')। " if lead_name else "")
            + disc_clause
            # BUG3 (grammar): PIN the subject as first-person — this is an OUTBOUND call, WE
            # called THEM. Without pinning, a temp-0.5 model attaches "आपने" -> inbound grammar
            # ("aapne call kiya"). Never let it flip the direction.
            + f"पहला-purush में कहो कि 'हमने आपको {product} के बारे में call किया है' (कभी 'आपने call किया' "
            f"मत कहना — यह OUTBOUND call है, तुमने caller को फ़ोन किया है), फिर पूछो 'क्या अभी दो minute बात हो "
            f"सकती है?'। बस एक ही छोटी बोली जाने वाली line — कोई symbol/list नहीं, कोई दूसरा वाक्य नहीं। "
            f"Price/size/details बिलकुल मत बताओ।"
        )
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + _next_groq_key()},
            json={
                "model": os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                "temperature": 0.5, "max_tokens": 70,
                "messages": [
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": "अभी opener बोलो।"},
                ],
            },
            timeout=8,
        )
        text = r.json()["choices"][0]["message"]["content"].strip()
        if not text:
            return fallback
        # OUTPUT-BOUNDARY SCRUB (founder #1 rule, defense-in-depth): even a perfectly
        # instructed model can hallucinate "AI assistant". If the generated opener trips
        # the banned block-list, DISCARD it and speak the clean brand-human fallback —
        # the wire can NEVER carry an AI self-label.
        if _opener_has_banned_label(text):
            logger.warning("opener tripped banned self-label scrub -> clean fallback: %r", text[:120])
            return fallback
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("opener generation failed, using fallback: %r", exc)
        return fallback


# --- P2: language-mirror helpers -------------------------------------------------

# Map a campaign's free-text language field to a langdetect default bucket.
_LANG_FIELD_MAP = {
    "hindi": "hindi", "hi": "hindi",
    "english": "english", "en": "english", "eng": "english",
    "hinglish": "hinglish",
    "gujarati": "gujarati", "gu": "gujarati", "guj": "gujarati",
}


def _campaign_default_lang(fields: dict) -> str:
    raw = str(fields.get("primary_language") or fields.get("language") or "hinglish").strip().lower()
    return _LANG_FIELD_MAP.get(raw, "hinglish")


# Phrases that signal a CLEAR terminal outcome → confirm-then-hangup closure.
# We only end the call after the agent has confirmed a next step (or a hard no/opt-out),
# never mid-conversation. Detection is on the FULL recent transcript, cheaply.
_CLOSE_BOOK = (  # caller agreed to a concrete next step (Latin + Devanagari STT forms)
    "site visit", "visit fix", "visit रख", "visit kar", "aa jaung", "aa jaaung", "आ जाऊँ",
    "callback", "call back", "kal call", "baad me call", "बाद में call", "whatsapp bhej",
    "details bhej", "theek hai book", "book kar", "haan visit", "हाँ visit",
    # Devanagari/transliterated forms (Sarvam often writes these in Devanagari):
    "विज़िट", "विजिट", "साइट विज़िट", "बुक कर", "बुक कर दो", "विज़िट बुक", "मिलते हैं",
    "व्हाट्सएप", "कॉल बैक", "डिटेल भेज",
)
_CLOSE_NO = (  # caller is clearly done / not interested / opt-out (Latin + Devanagari)
    "not interested", "interest nahi", "interested nahi", "नहीं चाहिए", "nahi chahiye",
    "mat karo call", "dobara call mat", "do not call", "remove me", "opt out",
    "number hata", "rakhta hoon", "rakhti hoon", "bye", "रखता हूँ", "रखती हूँ",
    # Devanagari forms:
    "इंटरेस्ट नहीं", "दिलचस्पी नहीं", "दोबारा कॉल मत", "कॉल मत कर", "नंबर हटा",
    "मत करो कॉल", "अभी नहीं", "बाय",
)


def _last_user_turn(turns: list[dict]) -> str:
    for t in reversed(turns):
        if t.get("role") == "user":
            return (t.get("content") or "").lower()
    return ""


def _closure_signal(turns: list[dict]) -> str:
    """Inspect the recent exchange. Returns 'book' | 'no' | '' (no closure yet).

    Conservative on purpose — we'd rather keep talking than cut early:
      - 'no'   : the LATEST caller turn is a clear not-interested / opt-out / bye.
      - 'book' : a concrete next step (site visit/callback/WhatsApp) appears in the recent
                 tail AND the LATEST caller turn is an affirmative agreement. So we only
                 close AFTER the caller has agreed to the step the agent proposed.
    Cheap substring scan; never raises."""
    try:
        if len(turns) < 4:  # need a real exchange before we consider closing
            return ""
        last_user = _last_user_turn(turns)
        if not last_user.strip():
            return ""
        if any(k in last_user for k in _CLOSE_NO):
            return "no"
        tail = " ".join((t.get("content") or "") for t in turns[-4:]).lower()
        affirm = ("haan", "हाँ", "ok", "okay", "theek hai", "ठीक है", "sure", "kar do",
                  "kar lo", "chalega", "fix kar", "yes", "बिलकुल", "bilkul", "ji haan")
        if any(k in tail for k in _CLOSE_BOOK) and any(k in last_user for k in affirm):
            return "book"
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _goodbye_line(signal: str, agent_name: str, company: str, gender: str) -> str:
    """A warm, gender-correct closing line spoken before we end the call."""
    fem = gender != "male"
    if signal == "book":
        return ("बढ़िया! मैं details WhatsApp पर भेज " + ("देती हूँ" if fem else "देता हूँ") +
                f", और हमारी team आपसे जल्दी connect कर लेगी। बात करके अच्छा लगा — आपका दिन शुभ हो! 🙏")
    # polite no / opt-out
    return ("कोई बात नहीं, आपका समय देने के लिए शुक्रिया। ज़रूरत हो तो "
            f"{company} हमेशा हाज़िर है — आपका दिन अच्छा रहे! 🙏")


def _llm_close(signal: str, agent_name: str, company: str, gender: str,
               turns: list[dict]) -> str:
    """FIX B (BUG4): LLM-authored closing line — generated by Groq, context-aware, in the
    caller's own language — instead of the hardcoded `_goodbye_line`. `signal` is 'book'
    (a concrete next step was agreed) or 'no' (polite decline / opt-out). Falls back to
    `_goodbye_line` if the Groq call fails or returns empty, so we NEVER go silent at hangup.
    Gated by LLM_CLOSE at the call site; length bounded by CLOSE_MAX_TOKENS. Never raises."""
    fallback = _goodbye_line(signal, agent_name, company, gender)
    try:
        recent = "\n".join(f"{t.get('role')}: {t.get('content')}"
                           for t in (turns or [])[-6:] if t.get("content"))[:1200]
        gender_clause = ("अपने बारे में पुल्लिंग (masculine) रूप इस्तेमाल करो।"
                         if gender == "male" else
                         "अपने बारे में स्त्रीलिंग (feminine) रूप इस्तेमाल करो।")
        if signal == "book":
            intent = ("Caller एक next step (site visit / callback / WhatsApp details) के लिए राज़ी "
                      "हो गया है। एक छोटी, गर्मजोशी भरी closing line बोलो जो उसी agreed step को "
                      "naturally confirm करे और शुक्रिया कहे।")
        else:
            intent = ("Caller ने अभी interest नहीं दिखाया / दोबारा call न करने को कहा है। एक छोटी, "
                      "respectful closing line बोलो — politely शुक्रिया, बिना बहस, बिना दोबारा pitch।")
        sysmsg = (
            f"तुम {agent_name} हो, {company} की telecaller। {gender_clause} {intent} "
            f"सिर्फ़ एक ही छोटी (12-22 शब्द) बोली जाने वाली line दो — caller ने call में जिस भाषा "
            f"(Hindi/English/Hinglish) में बात की उसी भाषा में, गर्मजोशी से। कोई symbol/list/दूसरा "
            f"वाक्य नहीं, कोई नया सवाल नहीं, कोई price/legal promise नहीं।")
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + _next_groq_key()},
            json={
                "model": os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                "temperature": 0.4, "max_tokens": int(os.getenv("CLOSE_MAX_TOKENS", "60")),
                "messages": [
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": "हाल की बातचीत:\n" + (recent or "(—)") + "\n\nअब closing line बोलो।"},
                ],
            },
            timeout=8,
        )
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
        return text or fallback
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm close failed, using fallback: %r", exc)
        return fallback


async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()
    room_name = ctx.room.name
    logger.info("agent job connected room=%s", room_name)

    # Per-call campaign brain + lead name from dispatch metadata ({"campaign_id","lead_name"}).
    meta: dict = {}
    try:
        raw = getattr(getattr(ctx, "job", None), "metadata", "") or ""
        meta = json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        meta = {}
    lead_name = (meta.get("lead_name") or "").strip()
    fields = GODREJ_FIELDS
    system_prompt = SYSTEM_PROMPT
    camp = _load_campaign(meta.get("campaign_id", ""))
    if camp:
        fields = camp.get("fields") or fields
        # P2: RENDER the prompt from fields at call time with the v2 brain
        # (build_system_prompt) so the richer brain — negotiation ladder, objection bank,
        # escalation/closing, gender-correct body, configurable AI disclosure — is LIVE for
        # EVERY campaign, including ones whose stored `system_prompt` was baked pre-P2.
        # Fall back to the stored prompt only if rendering ever fails (never worse than today).
        try:
            system_prompt = build_system_prompt(fields)
        except Exception as exc:  # noqa: BLE001
            system_prompt = camp.get("system_prompt") or system_prompt
            logger.warning("build_system_prompt failed, using stored prompt: %r", exc)
        logger.info("campaign=%s product=%s lead=%s", meta.get("campaign_id"),
                    fields.get("product_name"), lead_name)
    # WAVE3 Unit3: A/B variant override. Caller stamps a partial fields_override in the
    # dispatch metadata; merge it over the campaign fields and rebuild the prompt so this
    # call uses the variant's opener/voice/agent_name. No override -> identical to before.
    try:
        override = meta.get("fields_override") or {}
        if isinstance(override, dict) and override:
            merged = dict(fields)
            merged.update({k: v for k, v in override.items() if v not in (None, "")})
            fields = merged
            system_prompt = build_system_prompt(fields)
            logger.info("variant=%s applied override keys=%s",
                        meta.get("variant_id"), list(override.keys()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("variant override failed: %r", exc)

    # Cross-call memory: recover the lead's phone from the room name, load prior call.
    phone = mem.parse_phone(room_name)
    recap = mem.build_recap(mem.load_memory(phone))
    base_instructions = system_prompt
    if lead_name:
        base_instructions += f"\n\nLEAD NAME (इस caller का naam): {lead_name} — opener में इसी naam से greet करो।"
    # FIX A (BUG3 double-greeting): the opener (greeting + naam + company + product) is
    # spoken ONCE via session.say at call start. Without this, the system prompt's OPENER
    # section + FLOW step-1 make the LLM re-greet on turn 1 (live-proven double "नमस्ते
    # {name}"). This one-line behavioral instruction (no hardcoded name/company) tells the
    # model it has already opened → never greet/repeat the naam again. Cache-safe (in the
    # one-time prefix, not per-turn). Gated + reversible. Default "0" so a deployed-but-not-
    # yet-flagged build is BYTE-IDENTICAL to today; Cycle-2 sets OPENER_ALREADY_SAID=1 (with
    # OPENER_IN_CTX=0) to enable the fix.
    if os.getenv("OPENER_ALREADY_SAID", "0") in ("1", "true", "True"):
        base_instructions += (
            "\n\n=== तुम पहले ही OPEN कर चुके हो (ज़रूरी) ===\n"
            "Call की शुरुआत में तुम greet कर के अपना परिचय (naam + company + किस product के "
            "बारे में call) पहले ही दे चुकी/चुके हो। इसलिए अपने किसी भी turn में अब दोबारा "
            "'नमस्ते'/'namaste'/greeting मत करो और अपना naam या परिचय दोबारा मत दोहराओ — "
            "सीधे बातचीत आगे बढ़ाओ: caller की बात का जवाब दो या अगला एक छोटा सवाल पूछो।")
    if recap:
        base_instructions += "\n\n=== PICHHLI BAAT (returning lead) ===\n" + recap
        logger.info("returning lead phone=%s recap_chars=%d", phone, len(recap))
    instructions = base_instructions

    # --- P2: language mirror + closure state -------------------------------------
    agent_gender = _gender_of(fields)
    default_lang = _campaign_default_lang(fields)
    # FIX D (BUG2): LANG_MIRROR_V2 unifies language detection into ONE per-turn detector
    # (on_user_turn_completed) that drives BOTH the LLM reply-language note AND the TTS
    # language code, in sync, for all 4 languages, only on an actual switch. Default "0" =
    # the exact current 2-mechanism behavior (instant revert). LANG_MIRROR_FLOOR lowers the
    # switch confidence floor (default 0.30) so short/bare English ("Hello"/"ok") is caught.
    _lang_v2 = os.getenv("LANG_MIRROR_V2", "0") in ("1", "true", "True")
    _lang_floor = float(os.getenv("LANG_MIRROR_FLOOR", "0.30") or 0.30)
    lang_tracker = ld.LanguageTracker(
        default=default_lang,
        conf_floor=(_lang_floor if _lang_v2 else 0.45),
    ) if ld else None
    # Shared mutable cell so the (sync) conversation callback can hand async work to the loop.
    # tts_code = the language code currently set on the TTS stream (so V2 only calls
    # update_options on a REAL code change — incl. reverting EN->HI — avoiding ws churn).
    ctl = {"closing": False, "active_lang": default_lang, "loop": None,
           "session": None, "agent": None, "tts": None, "tts_code": None}
    logger.info("P2 lang default=%s gender=%s v2=%s floor=%.2f", default_lang, agent_gender,
                _lang_v2, _lang_floor)

    turns: list[dict] = []
    amd: dict = {"first_user_at": None, "started_at": None}
    # WAVE A Unit1: per-call vendor usage counters (accumulated during the call,
    # flushed to one per-room file at shutdown). Best-effort, never breaks the call.
    import time as _time
    usage = {"started_at": _time.time(),
             "el_tts_chars": 0,        # ElevenLabs TTS characters synthesized (assistant text)
             "groq_in_tokens": 0,      # Groq prompt tokens (from LLMMetrics)
             "groq_out_tokens": 0,     # Groq completion tokens (from LLMMetrics)
             "sarvam_stt_audio_s": 0.0}  # Sarvam STT audio seconds (from STTMetrics, else call dur)
    campaign_id = meta.get("campaign_id", "")

    async def _persist_memory() -> None:
        mem.save_memory(phone, turns)
        # --- WAVE A Unit1: flush per-call vendor usage events (best-effort) ---
        try:
            call_dur_s = max(0.0, _time.time() - usage["started_at"])
            # Sarvam STT seconds: prefer measured audio seconds; fall back to call duration.
            stt_s = usage["sarvam_stt_audio_s"] or call_dur_s
            ts = _datetime_module.datetime.now().isoformat(timespec="seconds")
            base = {"ts": ts, "room": room_name, "campaign_id": campaign_id,
                    "tenant_id": "", "call_id": ""}  # caller joins tenant/call_id by room
            events = []
            # ElevenLabs TTS (chars). Workspace analytics is authoritative; this is a hint.
            if usage["el_tts_chars"] > 0:
                events.append({**base, "vendor": "elevenlabs", "service_type": "tts",
                               "qty": usage["el_tts_chars"], "unit": "chars",
                               "est_cost_inr": round(usage["el_tts_chars"] / 1000.0 * EL_RATE_PER_1K_CHARS, 6),
                               "actual_or_estimated": "estimated"})
            # Groq LLM tokens (in/out priced per Mtok).
            if usage["groq_in_tokens"] or usage["groq_out_tokens"]:
                gcost = (usage["groq_in_tokens"] / 1_000_000.0 * GROQ_RATE_IN_PER_MTOK
                         + usage["groq_out_tokens"] / 1_000_000.0 * GROQ_RATE_OUT_PER_MTOK) * USD_INR
                events.append({**base, "vendor": "groq", "service_type": "llm",
                               "qty": usage["groq_in_tokens"] + usage["groq_out_tokens"], "unit": "tokens",
                               "est_cost_inr": round(gcost, 6), "actual_or_estimated": "estimated",
                               "in_tokens": usage["groq_in_tokens"], "out_tokens": usage["groq_out_tokens"]})
            # Sarvam STT (audio seconds).
            if stt_s > 0:
                events.append({**base, "vendor": "sarvam", "service_type": "stt",
                               "qty": round(stt_s, 2), "unit": "seconds",
                               "est_cost_inr": round(stt_s / 3600.0 * SARVAM_STT_RATE_PER_HR, 6),
                               "actual_or_estimated": "estimated"})
            # LiveKit self-hosted = free (0) — emit a row so the vendor shows up at 0.
            events.append({**base, "vendor": "livekit", "service_type": "media",
                           "qty": round(call_dur_s, 2), "unit": "seconds",
                           "est_cost_inr": 0.0, "actual_or_estimated": "actual"})
            _write_usage_raw(room_name, events)
        except Exception as exc:  # noqa: BLE001
            logger.warning("usage flush failed: %r", exc)
        # Persist a per-call transcript + AI summary (keyed by room; backend joins by room).
        try:
            summ = _summarize(turns)
            # P0.4 AMD hint: if a human never spoke, mark it so backend can classify VM/no-answer.
            amd_hint = ""
            if amd["first_user_at"] is None:
                amd_hint = "no_user_audio"
            TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
            (TRANSCRIPT_DIR / f"{room_name}.json").write_text(json.dumps({
                "room": room_name, "phone": phone, "lead_name": lead_name,
                "campaign_id": meta.get("campaign_id", ""), "turns": turns,
                "amd_hint": amd_hint, **summ,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("transcript saved room=%s outcome=%s interest=%s",
                        room_name, summ.get("outcome"), summ.get("interest"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcript save failed: %r", exc)

    ctx.add_shutdown_callback(_persist_memory)

    # P2: start TTS in the campaign's default language (Hinglish→'hi'); switched per-turn.
    _init_tts_lang = ld.tts_language_code(default_lang) if ld else "hi"
    # FIX C (BUG1 escalation knob): apply_text_normalization controls how ElevenLabs renders
    # numbers / proper-nouns / English-in-Devanagari. Default "auto" = today's behavior; the
    # bug-1 probe ladder can try "on" via EL_TEXT_NORM with NO code redeploy. Clamp to valid.
    _el_text_norm = os.getenv("EL_TEXT_NORM", "auto")
    if _el_text_norm not in ("auto", "on", "off"):
        _el_text_norm = "auto"
    tts = elevenlabs.TTS(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        voice_id=(fields.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a")),
        model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
        language=_init_tts_lang,
        apply_text_normalization=_el_text_norm,
        # Realtime-warm voice settings (verified from ElevenLabs docs):
        # low stability = expressive, style=0 (style adds 20-50ms), speaker_boost off.
        voice_settings=VoiceSettings(
            stability=float(os.getenv("EL_STABILITY", "0.45")),
            similarity_boost=float(os.getenv("EL_SIMILARITY", "0.80")),
            style=0.0,
            use_speaker_boost=False,
            # VOICEFIX: nudge speaking rate up slightly. The opener (~30 words) took ~18s to
            # speak at 1.0 (~1.7 words/s — unnaturally slow for a phone agent). 1.08 trims every
            # utterance ~8% and feels snappier with no content change. Tune via EL_SPEED.
            speed=float(os.getenv("EL_SPEED", "1.08")),
        ),
        auto_mode=True,                          # sentence-level streaming = fast first audio
    )
    ctl["tts"] = tts
    ctl["tts_code"] = _init_tts_lang             # FIX D: track the TTS's current language code

    # GROQ key round-robin: pick this CALL's key for the hot-path LLM (rotates across
    # GROQ_API_KEY/_2/_3 so concurrent calls spread load → less free-tier queueing/429).
    _call_groq_key = _next_groq_key()
    logger.info("groq key for this call: %s (pool=%d)", _mask_key(_call_groq_key), len(_GROQ_KEYS))

    session = AgentSession(
        stt=sarvam.STT(
            api_key=_next_sarvam_key(),
            # VOICEFIX: auto-detect / code-mixed. Forcing "hi-IN" garbled Hinglish/English
            # (the caller's English words came out as nonsense Devanagari → mishearing).
            # Sarvam's own default for saarika:v2.5 is "unknown" = detect the language per
            # utterance, so ANY language / code-mix the caller speaks is transcribed in its
            # real script. No hardcoded language. Override with SARVAM_STT_LANG if ever needed.
            language=os.getenv("SARVAM_STT_LANG", "unknown"),
            model=os.getenv("SARVAM_STT_MODEL", "saarika:v2.5"),
        ),
        llm=groq.LLM(
            model=os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            api_key=_call_groq_key,
            temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            # CONCISE-BRAIN: this is a RUNAWAY BACKSTOP, NOT the length rule. Brevity is the
            # prompt's job (rule 2 = "1-2 short sentences then stop"); this cap only bounds the
            # worst case so a model that ever ignores the prompt can't wall-of-speech for 8-12s.
            # Measured on box: Devanagari is token-EXPENSIVE in llama BPE — a normal 1-2 sentence
            # Hinglish beat is only ~35-50 tokens, so 90 leaves comfortable headroom (a legit beat
            # ends well under the cap → NO mid-sentence truncation / clipped fillers) while bounding
            # a runaway to ~5-6s of speech. The OLD 140 ≈ 3-4 sentences = the monologue we're killing.
            # If completion_tokens ever PEGS at the cap on real calls, the model is being guillotined
            # → RAISE GROQ_MAX_TOKENS and tighten the prompt instead. Env-overridable, fully reversible.
            # NOTE: the param is `max_completion_tokens` (groq.LLM extends OpenAILLM); the
            # OpenAI-style `max_tokens` kwarg does NOT exist here → TypeError that crashes calls.
            max_completion_tokens=int(os.getenv("GROQ_MAX_TOKENS", "90")),
        ),
        tts=tts,
        vad=silero.VAD.load(),
        # --- low-latency telephony tuning (defaults are far too slow) ---
        preemptive_generation=True,                 # start LLM before turn finalized
        min_endpointing_delay=float(os.getenv("MIN_EP_DELAY", "0.25")),
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "0.45")),  # default ~6s!
        aec_warmup_duration=0.0,                     # default 3s start delay
        # VOICEFIX: lower so the caller can BARGE IN and cut a long reply (he complained he
        # couldn't interrupt / had to repeat). 0.25s of speech now interrupts the agent.
        min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.25")),
        false_interruption_timeout=1.0,
        turn_detection="vad",                        # fast; no heavy model
    )

    # --- VOICEFIX: language mirroring is now MODEL-NATIVE, not per-turn machinery -----
    # The old P2 worker rewrote the WHOLE 6049-char system prompt on every detected switch
    # (agent.update_instructions(...)). That busted Groq's prompt cache => 2.5s TTFT spikes,
    # AND forced ElevenLabs to a single language code (wrong for code-mix). Both hurt the
    # caller. The intelligent fix: the LLM is multilingual and is told ONCE (in the system
    # prompt) to reply in WHATEVER language the caller used; ElevenLabs flash_v2_5
    # auto-detects language from that text. So we do NOT touch instructions or force a TTS
    # language per turn. We keep a tiny, OPTIONAL, cache-safe TTS nudge for the rare strong
    # non-Latin/non-Devanagari script (e.g. Gujarati) so flash picks it instantly — gated by
    # LANG_TTS_NUDGE (default on) and wrapped so it can never break a call.
    _tts_nudge_on = os.getenv("LANG_TTS_NUDGE", "1") not in ("0", "false", "False")

    async def _apply_language_switch(new_lang: str) -> None:
        """Lightweight, cache-SAFE language adapt. NO prompt rewrite (the model mirrors
        language itself). Optionally nudges the ElevenLabs language code so a confidently
        non-Hindi script (Gujarati/etc.) speaks right. Never raises, never blocks the LLM."""
        try:
            ctl["active_lang"] = new_lang
            if not _tts_nudge_on or ld is None:
                logger.info("lang detected -> %s (model mirrors; no prompt rewrite)", new_lang)
                return
            # Only nudge TTS for a code that ElevenLabs needs help with; for hindi/hinglish/
            # english flash auto-detects from the text, so leave it alone (avoid churn).
            # ⚠️ CRITICAL (live-verified 2026-06-05): NEVER send a code flash_v2_5 can't
            # speak. Sending 'gu' (Gujarati) → unsupported_language(1008) → TTS websocket
            # dies → the agent goes SILENT for the rest of the call (update_options is
            # sticky). safe_tts_language_code() clamps any unspeakable language to 'hi',
            # so a Gujarati/Marathi/etc. caller hears Hindi audio instead of dead air.
            try:
                code = ld.safe_tts_language_code(new_lang)
                if _lang_v2:
                    # FIX D: track the last-sent TTS code and send update_options ONLY on a
                    # real change (incl. reverting EN->HI, which the V1 'skip hi' branch
                    # below never did — leaving the TTS stuck on 'en'). The plugin itself
                    # no-ops a same-language update_options (tts.py:267-271), so this only
                    # ever reconnects on a genuine language switch = the desired behavior.
                    if code != ctl.get("tts_code"):
                        tts.update_options(language=code)
                        ctl["tts_code"] = code
                else:
                    if code not in ("hi",):  # V1 (unchanged): hi is the default; en gets a hint
                        tts.update_options(language=code)
                logger.info("lang detected -> %s (tts code=%s, speakable=%s; model mirrors text)",
                            new_lang, code, ld.is_speakable(new_lang))
            except Exception as exc:  # noqa: BLE001
                logger.warning("tts language nudge failed lang=%s err=%r", new_lang, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("apply_language_switch failed: %r", exc)

    async def _confirm_then_hangup(signal: str) -> None:
        """Unit 5: when the outcome is clear, confirm the next step, say a warm goodbye,
        THEN end the call cleanly — never an abrupt mid-sentence cut."""
        if ctl["closing"]:
            return
        ctl["closing"] = True
        try:
            _agent_nm = fields.get("agent_name") or "Riya"
            _company_nm = fields.get("company_name") or "Famit"
            # FIX B (BUG4): generate the close from Groq (context-aware, language-mirrored)
            # instead of the hardcoded line. LLM_CLOSE=0 (default) keeps _goodbye_line
            # byte-identical; =1 enables the LLM close with _goodbye_line as the crash-safe
            # fallback (never dead air at hangup). Instant env revert.
            if os.getenv("LLM_CLOSE", "0") in ("1", "true", "True"):
                line = _llm_close(signal, _agent_nm, _company_nm, agent_gender, turns)
            else:
                line = _goodbye_line(signal, _agent_nm, _company_nm, agent_gender)
            logger.info("P2 closure signal=%s -> goodbye: %s", signal, line[:120])
            handle = session.say(line, allow_interruptions=False)
            try:
                await handle.wait_for_playout()      # let the goodbye fully play
            except Exception:  # noqa: BLE001
                await asyncio.sleep(2.5)             # fallback grace if handle API differs
            await asyncio.sleep(0.4)
        except Exception as exc:  # noqa: BLE001
            logger.warning("closure say failed: %r", exc)
        finally:
            try:
                await ctx.delete_room(room_name=room_name)  # clean end
            except Exception as exc:  # noqa: BLE001
                logger.warning("delete_room failed: %r", exc)

    # Log conversation items + drive per-turn language mirror & closure.
    @session.on("conversation_item_added")
    def _on_item(ev) -> None:  # noqa: ANN001
        try:
            role = getattr(ev.item, "role", "?")
            text = getattr(ev.item, "text_content", "") or ""
            logger.info("turn[%s]: %s", role, text[:200])
            if text and role in ("user", "assistant"):
                if role == "user" and amd["first_user_at"] is None:
                    import time as _t
                    amd["first_user_at"] = _t.time()
                # WAVE A Unit1: ElevenLabs TTS chars = sum of assistant text synthesized.
                if role == "assistant":
                    try:
                        usage["el_tts_chars"] += len(text)
                    except Exception:  # noqa: BLE001
                        pass
                turns.append({"role": role, "content": text})
                # Persist incrementally (cheap JSON write) so memory survives any call ending,
                # not just a clean shutdown. Save after assistant turns = complete exchanges.
                if role == "assistant":
                    mem.save_memory(phone, turns)
                # --- P2: per-turn language mirror (on the caller's turns only) ---
                # FIX D: in V2 the SINGLE detector lives in _MirrorAgent.on_user_turn_completed
                # (it updates the tracker + drives LLM note AND TTS together). Calling
                # lang_tracker.update() here too would double-feed the hysteresis and desync —
                # so this V1 path runs ONLY when V2 is off.
                loop = ctl.get("loop")
                if (not _lang_v2) and role == "user" and lang_tracker is not None and loop is not None and not ctl["closing"]:
                    try:
                        new_lang, switched = lang_tracker.update(text)
                        if switched:
                            asyncio.run_coroutine_threadsafe(_apply_language_switch(new_lang), loop)
                    except Exception:  # noqa: BLE001
                        pass
                # --- P2 Unit5: confident confirm-then-hangup closure ---
                if role == "assistant" and loop is not None and not ctl["closing"]:
                    try:
                        sig = _closure_signal(turns)
                        if sig:
                            asyncio.run_coroutine_threadsafe(_confirm_then_hangup(sig), loop)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    # Per-turn latency breakdown: EOU (end-of-utterance) + LLM ttft + TTS ttfb.
    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:  # noqa: ANN001
        try:
            m = ev.metrics
            t = type(m).__name__
            if t == "EOUMetrics":
                logger.info("LATENCY eou_delay=%.3fs", getattr(m, "end_of_utterance_delay", -1))
            elif t == "LLMMetrics":
                logger.info("LATENCY llm_ttft=%.3fs tokens=%s", getattr(m, "ttft", -1),
                            getattr(m, "completion_tokens", "?"))
                # WAVE A Unit1: accumulate Groq token usage for cost metering.
                try:
                    usage["groq_in_tokens"] += int(getattr(m, "prompt_tokens", 0) or 0)
                    usage["groq_out_tokens"] += int(getattr(m, "completion_tokens", 0) or 0)
                except Exception:  # noqa: BLE001
                    pass
            elif t == "TTSMetrics":
                logger.info("LATENCY tts_ttfb=%.3fs", getattr(m, "ttfb", -1))
            elif t == "STTMetrics":
                # WAVE A Unit1: accumulate Sarvam STT audio seconds.
                try:
                    usage["sarvam_stt_audio_s"] += float(getattr(m, "audio_duration", 0) or 0)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

    # VOICEFIX: cache-safe per-turn language steering via the on_user_turn_completed hook.
    # The model already mirrors language from the system prompt, but a 17B model with a fully
    # Hindi prompt drifts toward Hindi for English/Gujarati/etc. callers. So on each user turn
    # we run the CHEAP LOCAL langdetect (~0.01ms, no network) and, when the caller is confidently
    # NOT in the default language, append ONE short instruction to THIS turn's context only —
    # never rewriting the cached system instructions (so Groq's prompt prefix stays cached, no
    # TTFT spike). This makes language adaptation reliable for ANY language, the intelligent way.
    class _MirrorAgent(Agent):
        async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # noqa: ANN001
            try:
                if ld is None:
                    return
                txt = ""
                try:
                    c = getattr(new_message, "text_content", None)
                    txt = (c() if callable(c) else c) or getattr(new_message, "content", "") or ""
                    if isinstance(txt, (list, tuple)):
                        txt = " ".join(str(x) for x in txt)
                except Exception:  # noqa: BLE001
                    txt = ""
                if not str(txt).strip():
                    return
                # FIX D (BUG2): V2 = ONE detector drives BOTH the LLM reply-language note AND
                # the TTS code, in sync, for all 4 languages, ONLY on an actual switch (incl.
                # switching BACK to Hindi). Cache-safe: the note is appended AFTER the cached
                # prefix; on steady-state (no switch) NOTHING is added → zero token cost on the
                # dominant Hindi/Hinglish path. This is the single source of truth — the
                # conversation_item_added V1 path is disabled when V2 is on.
                if _lang_v2 and lang_tracker is not None:
                    new_lang, switched = lang_tracker.update(str(txt))
                    if switched:
                        try:
                            turn_ctx.add_message(role="system", content=ld.reply_instruction(new_lang))
                        except Exception:  # noqa: BLE001
                            pass
                        try:
                            await _apply_language_switch(new_lang)
                        except Exception:  # noqa: BLE001
                            pass
                        logger.info("lang mirror v2 -> %s (switched; LLM note + TTS synced)", new_lang)
                    return
                # --- V1 (default, unchanged): english/gujarati note at conf>=0.55 ---
                lang, conf = ld.classify_text(str(txt))
                # Only nudge when confident AND it differs from plain Hinglish/Hindi default,
                # so normal Hindi/Hinglish calls add nothing (zero overhead, no behavior change).
                if conf >= 0.55 and lang in ("english", "gujarati"):
                    note = {
                        "english": "The caller just spoke ENGLISH. Reply ONLY in natural English for this turn.",
                        # Our realtime TTS cannot SPEAK Gujarati → do NOT steer the LLM to
                        # emit Gujarati script (it'd be silent/garbled). Understand the
                        # Gujarati caller, but reply in simple Hindi (they understand Hindi).
                        "gujarati": "The caller just spoke GUJARATI. You understood them — but REPLY in simple, clear Hindi (Devanagari) for this turn, NOT in Gujarati script. Stay warm and on-topic.",
                    }[lang]
                    try:
                        turn_ctx.add_message(role="system", content=note)
                    except Exception:  # noqa: BLE001
                        pass
                    logger.info("lang nudge -> %s (conf=%.2f)", lang, conf)
            except Exception:  # noqa: BLE001
                pass

    # P2: capture the running loop + agent so the sync conversation callback can hand
    # async work (language switch / closure) back to this event loop.
    agent = _MirrorAgent(instructions=instructions)
    ctl["agent"] = agent
    ctl["session"] = session
    try:
        ctl["loop"] = asyncio.get_running_loop()
    except Exception:  # noqa: BLE001
        ctl["loop"] = None

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Greeting authored by the brain (Groq), per-campaign + by-name, via the reliable say() path.
    # P2: opener follows the campaign's voice gender + configurable AI disclosure.
    _disclose_ai = bool(fields.get("disclose_ai", True))
    _disc_phrase = str(fields.get("ai_disclosure") or "").strip()
    opener = _llm_opener(
        fields.get("agent_name") or "Riya",
        fields.get("company_name") or "Famit",
        fields.get("product_name") or "हमारी property",
        lead_name,
        gender=agent_gender,
        disclose=_disclose_ai,
        disclosure_phrase=_disc_phrase,
    )
    logger.info("opener: %s", opener[:200])
    # FIX A (BUG3): by livekit default, session.say() text is fed back into the LLM chat
    # context as a prior assistant turn — so the model SEES its own opener and (told by the
    # prompt to "open with a greeting") re-greets on turn 1. OPENER_IN_CTX=0 suppresses that
    # echo so there is no greeting for the model to repeat; the system-prompt persona still
    # holds its identity for "kaun bol raha hai?". Default "1" = byte-identical. Reversible.
    _opener_in_ctx = os.getenv("OPENER_IN_CTX", "1") not in ("0", "false", "False")
    await session.say(opener, allow_interruptions=True, add_to_chat_ctx=_opener_in_ctx)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=AGENT_NAME,
            port=int(os.getenv("AGENT_HTTP_PORT", "8090")),
        )
    )


if __name__ == "__main__":
    main()
