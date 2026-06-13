"""aim_voice_agent.py — INBOUND AI Manager voice agent (LiveKit persona agent_name="manager").

⚠️ ADDITIVE / SEPARATE worker. A SECOND LiveKit worker registered ALONGSIDE the live outbound earner
(agent.py, agent_name="capsy"). It NEVER imports, restarts, or mutates agent.py / caller.py / the
outbound trunks / firewall / SIP container. Its OWN systemd unit `aim-voice-agent` on :8091.

════════════════════════════════════════════════════════════════════════════════════════════════════
REBUILD 2026-06-12 (OWN, the silence fix). WHY: the prior build ran the SYNC `CommandMachine` in a
worker thread and bridged speak/listen via `run_coroutine_threadsafe`, with a custom
`SessionConnectOptions` + `_ResilientSarvamSTT` subclass + `close_on_disconnect=False`. On REAL SIP
calls `session.start()` blocked ~30s on the Sarvam STT first-connect (event-loop starvation during
bring-up — PROVEN not DNS: the same WS connects in 0.16s standalone from the box), so the greeting
(which ran AFTER `session.start()`) never fired -> 30s of SILENCE -> PIN machine burned attempts on
empty input -> `reject:lockout`. The OUTBOUND earner does NONE of that: it builds a plain
`AgentSession(stt=sarvam.STT(...), vad=silero.VAD.load(), ...)`, calls `session.start(...)`, then
`await session.say(opener)` — and greets in ~1s on every real call.

THE FIX (mirror the proven outbound pattern): plain AgentSession with the EXACT outbound STT/VAD/TTS/
turn config (NO SessionConnectOptions, NO STT subclass, NO close_on_disconnect override, NO
sync-thread bridge gating the greeting). Greet via `await session.say(greeting)` immediately after
`session.start()` (the proven audio path). The manager PIN-gate + command logic is layered as Agent
**function-tools** the LLM calls — so policy/firewall/registry/audit are preserved, but they can
NEVER block or suppress the greeting/audio. A customer (non-manager) caller gets a warm sales-style
assistant. Audio first, always.

VOICE STACK = agent.py's tuned low-latency stack, copied not re-derived (so the ~1.1s/turn moat is
inherited): Sarvam STT saarika:v2.5 language="unknown", Groq llama-4-scout, ElevenLabs flash TTS,
preemptive_generation + endpointing/barge-in kwargs + VAD turn-detection.

Run:  python aim_voice_agent.py start   (registers agent_name="manager")
Env:  /opt/famit-agent/.env  (reuses the box's Sarvam/Groq/ElevenLabs keys + FIREWALL secret).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    APIConnectOptions,
    JobProcess,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)

# HOLD-AUDIO (calm reassurance while a human is being rung) — played to the CALLER, in the CALLER's
# CURRENT room, by US (never a side room). BackgroundAudioPlayer publishes a looped clip on its own
# track in the room; we stop it the instant the human answers. Import-guarded: if the API is absent
# the transfer still works (spoken reassurance only, no music) — a missing clip NEVER breaks a call.
try:
    from livekit.agents import BackgroundAudioPlayer as _BgAudio, BuiltinAudioClip as _Clip, AudioConfig as _AudioCfg
except Exception:  # noqa: BLE001 — older/newer agents: degrade to spoken-reassurance only.
    _BgAudio = None  # type: ignore
    _Clip = None  # type: ignore
    _AudioCfg = None  # type: ignore

# SessionConnectOptions is not publicly re-exported; import it directly. Lets us set per-session
# llm_conn_options (FAIL-FAST: drop max_retry so a doomed/rejected LLM inference can't storm-retry
# 4x into minutes of dead air). Guarded so an API rename can't brick the worker.
try:
    from livekit.agents.voice.agent_session import SessionConnectOptions as _SessionConnectOptions
except Exception:  # noqa: BLE001
    _SessionConnectOptions = None
from livekit.plugins import elevenlabs, groq, sarvam, silero
# EMERG-FIX (Groq daily-TPD exhaustion restore): pull in the OpenAI-compatible plugin so AIM can
# fall back to an INDEPENDENT free LLM pool (OpenRouter) when Groq's shared 500k/day bucket is dead.
# Import-guarded: if either is absent, AIM degrades to pure-Groq (no behaviour change).
try:
    from livekit.plugins import openai as _openai  # type: ignore
except Exception:  # noqa: BLE001
    _openai = None  # type: ignore
try:
    from livekit.agents import llm as _lk_llm  # type: ignore
except Exception:  # noqa: BLE001
    _lk_llm = None  # type: ignore
# LPR-POOL: smart provider key pool (least-used + skip-cooling + instant re-pick on 429) +
# SambaNova final fallback + hot-reloadable key-store. Import-guarded: absent -> legacy rotation.
try:
    from llm_router import GROQ_POOL as _GROQ_POOL, SARVAM_POOL as _SARVAM_POOL, \
        SAMBANOVA_POOL as _SAMBA_POOL, OPENROUTER_POOL as _OR_POOL  # type: ignore
    from llm_router.pool_llm import PoolLLM as _PoolLLM  # type: ignore
    _LPR_OK = True
except Exception as _lpr_exc:  # noqa: BLE001
    _GROQ_POOL = _SARVAM_POOL = _SAMBA_POOL = _OR_POOL = None  # type: ignore
    _PoolLLM = None  # type: ignore
    _LPR_OK = False
from livekit.plugins.elevenlabs import VoiceSettings

# Semantic end-of-turn model (guarded; Silero VAD is the fallback) — identical guard to agent.py.
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel as _SemanticTurnModel
except Exception:  # noqa: BLE001 — plugin may be absent; the agent MUST still run on VAD
    _SemanticTurnModel = None

# ── HUMAN WARM TRANSFER (BUILD#6 — DIRECT-BRIDGE, HOFX) ─────────────────────────
# We dial the human DIRECTLY INTO THE CALLER'S CURRENT ROOM via create_sip_participant on the
# OUTBOUND trunk (the EXACT primitive the earner uses in caller.py:/run). Same room == an instant
# 2-way conference bridge: the caller and the human hear each other immediately, the AI whispers one
# line and steps back. No side room, no secondary briefing agent, no hold music (those were the
# WarmTransferTask path that left the caller stuck on hold while the merge never fired). Carrier-
# agnostic (no SIP REFER). We REUSE the earner's outbound trunk ID as a STRING ONLY — never editing
# the trunk / dispatch / agent.py / firewall / SIP container.
from livekit import api as _lk_api                      # CreateSIPParticipantRequest (same as earner)
try:
    from livekit.protocol.types import Duration as _DurationLK   # ringing_timeout proto
except Exception:  # noqa: BLE001 — proto path varies by livekit version; try the api re-export.
    try:
        from livekit.api import Duration as _DurationLK  # type: ignore
    except Exception:  # noqa: BLE001
        from google.protobuf.duration_pb2 import Duration as _DurationLK  # final fallback
# get_job_context() yields the live JobContext (room + api) for the CURRENTLY-RUNNING call — this is
# how we obtain the caller's room to bridge INTO. Guarded so an API rename can't brick the worker.
try:
    from livekit.agents import get_job_context as _get_job_context
except Exception:  # noqa: BLE001
    try:
        from livekit.agents.job import get_job_context as _get_job_context  # type: ignore
    except Exception:  # noqa: BLE001
        _get_job_context = None  # type: ignore

# Live-call registry (cross-process, file-backed). The voice worker WRITES active-call + handoff
# state here; caller.py's GET /ai-manager/live READS it. Import-guarded: a missing module degrades to
# no live-call visibility, never a crash / a broken call.
try:
    from ai_manager import live_registry as _live
except Exception as _live_exc:  # noqa: BLE001
    _live = None
    logging.getLogger("aim-voice").warning("live_registry import failed (live-calls OFF): %r", _live_exc)


def _live_upsert(room: str, **kw) -> None:
    """Best-effort write to the live-call registry. NEVER raises."""
    if _live is None or not room:
        return
    try:
        _live.upsert(room, **kw)
    except Exception:  # noqa: BLE001
        pass


def _live_set_handoff(room: str, handoff: str, target: str = "") -> None:
    if _live is None or not room:
        return
    try:
        _live.set_handoff(room, handoff, target=target)
    except Exception:  # noqa: BLE001
        pass


def _live_remove(room: str) -> None:
    if _live is None or not room:
        return
    try:
        _live.remove(room)
    except Exception:  # noqa: BLE001
        pass

# Read-only reuse of the earner's outbound trunk id (env LIVEKIT_SIP_TRUNK_ID). NEVER mutated here.
_OUTBOUND_TRUNK = (os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa") or "ST_fmtVmNJmpzKa").strip()
_TRANSFER_RING_TIMEOUT = float(os.getenv("AIM_TRANSFER_RING_TIMEOUT", "25"))

import itertools as _itertools

# The AI-Manager command brain modules (used by the function-tools, NOT to gate audio).
from ai_manager import registry as _registry  # noqa: F401  (identity.resolve wraps it)
from ai_manager import identity as _identity
from ai_manager import config as _aim_config  # noqa: F401
# voice_tools = the loopback bridge to the SAME backend the chat Test Console uses (caller.py:8209).
# Reads (leads/calls/analytics/wallet) + the PROVEN /run dial path for run_campaign. Never raises;
# a failure returns a spoken-friendly string. Guarded so the worker still boots if it's absent.
try:
    from ai_manager import voice_tools as _vt
except Exception as _vt_exc:  # noqa: BLE001
    _vt = None
    logging.getLogger("aim-voice").warning("voice_tools import failed (command tools degraded): %r", _vt_exc)

# DURABLE SESSION LOGGING + RECORDING (BUILD QUEUE #8). store = PG-native, RLS-scoped persistence of the
# per-call session row + transcript turns + executed commands + outcome (degrade-safe: a PG outage is a
# silent no-op, NEVER breaks/silences the live call). recorder = LiveKit room-composite Egress -> DO
# Spaces (dormant NullRecorder until AIM_RECORDING_ENABLED + creds). Both are read by the panel Call
# History page via GET /ai-manager/sessions[/{id}]. Import-guarded so a missing module can never stop the
# worker booting. We NEVER touch agent.py / the earner / trunks / firewall / SIP.
try:
    from ai_manager import store as _aim_store
except Exception as _store_exc:  # noqa: BLE001
    _aim_store = None
    logging.getLogger("aim-voice").warning("ai_manager.store import failed (PG session logging OFF): %r", _store_exc)
try:
    from ai_manager import recorder as _aim_recorder
except Exception as _rec_exc:  # noqa: BLE001
    _aim_recorder = None
    logging.getLogger("aim-voice").warning("ai_manager.recorder import failed (recording OFF): %r", _rec_exc)

# READ-ONLY reuse of the OUTBOUND earner's proven sales brain + cross-call memory. We IMPORT these
# modules (never edit them) so the inbound CUSTOMER (sales) agent runs the EXACT same campaign brain
# the outbound dialer uses. Guarded: if either is absent the customer agent still works on a generic
# friendly-sales fallback (never crashes the worker, never goes silent).
try:
    import prompt as _prompt  # build_system_prompt(fields) -> the human telecaller brain (READ-ONLY)
except Exception as _prompt_exc:  # noqa: BLE001
    _prompt = None
    logging.getLogger("aim-voice").warning("prompt import failed (sales brain degraded): %r", _prompt_exc)
try:
    import memory as _memory  # load_memory/build_recap/save_memory keyed by phone digits (READ-ONLY)
except Exception as _memory_exc:  # noqa: BLE001
    _memory = None
    logging.getLogger("aim-voice").warning("memory import failed (cross-call recap degraded): %r", _memory_exc)

# READ-ONLY reuse of the hybrid RAG engine (kb/core.py: FTS sparse leg keyless today + pgvector dense
# when an embedder is configured). Used for (a) a fire-and-forget GROUNDING prefetch at call connect,
# folded into the sales instructions, and (b) a mid-call `lookup` tool for deep/edge questions. STRICTLY
# import-safe-degrade: a KB/PG outage returns [] -> the call runs EXACTLY as before. We NEVER write to kb
# from here (only kb.retrieve, read-only) and NEVER touch agent.py / the outbound earner.
try:
    import kb as _kb  # kb.retrieve(tenant, query, top_k, scope, channel, scope_campaign_id) (READ-ONLY)
except Exception as _kb_exc:  # noqa: BLE001
    _kb = None
    logging.getLogger("aim-voice").warning("kb import failed (RAG grounding degraded -> no-op): %r", _kb_exc)

load_dotenv("/opt/famit-agent/.env")
load_dotenv(".env")

logger = logging.getLogger("aim-voice")


# ── firewall init (LOAD-BEARING for the PIN tool) ──────────────────────────────
# Separate worker process -> nothing has init'd firewall -> an un-init'd firewall fail-CLOSES
# (check_pin False for everything). Replicate caller.py's init once at startup against the SAME
# var/secret + var/pins.json. NEVER raises; degrades fail-closed (deny) = the safe direction.
_FAMIT_VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))


def _load_secret() -> str:
    try:
        sf = _FAMIT_VAR / "secret"
        if sf.exists():
            s = sf.read_text(encoding="utf-8").strip()
            if s:
                return s
    except Exception:  # noqa: BLE001
        pass
    return (os.getenv("FIREWALL_SECRET") or os.getenv("JWT_SECRET") or "").strip()


def _init_firewall() -> bool:
    try:
        import firewall as _fw
        ready = bool(_fw.init(secret=_load_secret(), pin_file=_FAMIT_VAR / "pins.json"))
        logger.info("AIM firewall init: ready=%s available=%s", ready, _fw.available())
        return ready
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM firewall init FAILED (PIN tool will fail-closed/deny): %r", exc)
        return False


_FIREWALL_READY = _init_firewall()


# ── PG engine init (LOAD-BEARING for #8 session logging) ───────────────────────
# This worker is a SEPARATE process from caller.py, so db.engine has NOT been wired here. Without
# engine.init() the strangler stays in "PG disabled" mode and every store.* write is a silent no-op
# (the call still runs, but nothing is logged). Replicate caller.py's one-time init against the SAME
# PG_DSN already loaded from .env above. Idempotent + NEVER raises (degrades to available()==False).
def _init_db() -> bool:
    try:
        from db import engine as _db_engine
        ok = bool(_db_engine.init())
        logger.info("AIM db.engine init: available=%s", ok)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM db.engine init failed (PG session logging OFF, call unaffected): %r", exc)
        return False


_DB_READY = _init_db()

# ── identity / config ──────────────────────────────────────────────────────────
AGENT_NAME = os.getenv("AIM_VOICE_AGENT_NAME", "manager")
ADMIN_TENANT = os.getenv("AIM_ADMIN_TENANT", "admin").strip()
_AGENT_VOICE = os.getenv("AIM_AGENT_VOICE_NAME", "Riya").strip() or "Riya"
_COMPANY = os.getenv("AIM_COMPANY_NAME", "Famit").strip() or "Famit"
_PIN_LEN = int(os.getenv("AIM_PIN_LEN", "4"))


def _canon(phone: str) -> str:
    if not phone:
        return ""
    s = str(phone).strip()
    plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    return (("+" if plus else "") + digits) if digits else ""


# ── Groq + Sarvam key round-robin (COPIED from agent.py) ───────────────────────
def _collect_keys(base: str) -> list[str]:
    keys: list[str] = []
    for name in [base] + [f"{base}_{i}" for i in range(2, 21)]:
        v = (os.getenv(name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys


_GROQ_KEYS = _collect_keys("GROQ_API_KEY")
_GROQ_CYCLE = _itertools.cycle(_GROQ_KEYS) if _GROQ_KEYS else None
_GROQ_LOCK = threading.Lock()
_SARVAM_KEYS = _collect_keys("SARVAM_API_KEY")
_SARVAM_CYCLE = _itertools.cycle(_SARVAM_KEYS) if _SARVAM_KEYS else None
_SARVAM_LOCK = threading.Lock()


def _next_groq_key() -> str:
    try:
        if _GROQ_CYCLE is not None:
            with _GROQ_LOCK:
                return next(_GROQ_CYCLE)
    except Exception:  # noqa: BLE001
        pass
    return (os.getenv("GROQ_API_KEY") or "").strip()


def _next_sarvam_key() -> str:
    try:
        if _SARVAM_CYCLE is not None:
            with _SARVAM_LOCK:
                return next(_SARVAM_CYCLE)
    except Exception:  # noqa: BLE001
        pass
    return (os.getenv("SARVAM_API_KEY") or "").strip()


# ── tuned-voice-stack helpers (mirrors agent.py) ───────────────────────────────
def _resolve_turn_detection():
    mode = (os.getenv("TURN_DETECTION", "vad") or "vad").strip().lower()
    if mode == "semantic" and _SemanticTurnModel is not None:
        try:
            model = _SemanticTurnModel()
            logger.info("turn_detection: SEMANTIC (MultilingualModel) loaded")
            return model
        except Exception as exc:  # noqa: BLE001
            logger.warning("turn_detection: VAD (semantic load failed: %r)", exc)
            return "vad"
    return "vad"


def _build_stt():
    """Plain Sarvam STT — IDENTICAL to the outbound earner (agent.py:510). No subclass, no forced
    conn_options. The earner proves this exact construction connects fast + transcribes on real calls.
    MULTILINGUAL/ADAPTIVE STT: language="unknown" is Sarvam saarika's AUTO-DETECT mode — it transcribes
    whatever language the caller actually speaks turn-by-turn (English stays English, Hindi stays Hindi,
    code-mixed Hinglish is handled). This is what lets the caller switch language mid-call and still be
    heard correctly. It is deliberately NOT pinned to a fixed language: pinning hi-IN garbles English
    words (verified on live calls — under auto, an English "Hello" is captured verbatim). Override via
    SARVAM_STT_LANG only if a single tenant genuinely needs a forced language."""
    # LPR-POOL: pick the least-used, not-cooling Sarvam key (a rate-limited key is skipped
    # instantly instead of a linear walk). Falls back to the legacy round-robin if the pool
    # is unavailable. A 429 cooldown is best-effort marked by the resilient STT subclass below.
    _sk = None
    try:
        if _SARVAM_POOL is not None:
            _picked = _SARVAM_POOL.pick()
            _sk = _picked["key"] if _picked else None
    except Exception:  # noqa: BLE001
        _sk = None
    return sarvam.STT(
        api_key=_sk or _next_sarvam_key(),
        language=os.getenv("SARVAM_STT_LANG", "unknown"),
        model=os.getenv("SARVAM_STT_MODEL", "saarika:v2.5"),
    )


def _build_tts():
    """ElevenLabs flash TTS with agent.py's realtime-warm voice settings."""
    return elevenlabs.TTS(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a"),
        model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
        language=os.getenv("AIM_TTS_LANG", "hi"),
        voice_settings=VoiceSettings(
            stability=float(os.getenv("EL_STABILITY", "0.45")),
            similarity_boost=float(os.getenv("EL_SIMILARITY", "0.80")),
            style=0.0,
            use_speaker_boost=False,
            speed=float(os.getenv("EL_SPEED", "1.08")),
        ),
        auto_mode=True,
    )


# ── FIX (C): FILLER SPEECH around any tool fetch that may take >~300ms ──────────
# Before a data fetch / dial we speak a short, natural Hinglish holding phrase so the caller NEVER
# hears silence while we hit the backend. We rotate a few so it doesn't sound canned, and we fire it
# without awaiting (allow_interruptions) so it overlaps the fetch instead of adding latency.
_FILLER_LINES = [
    "Ek second, dekh rahi hoon…",
    "Haan ji, abhi check kar rahi hoon…",
    "Bas ek pal, nikaal rahi hoon…",
    "Theek hai, dekhti hoon abhi…",
]
_filler_cycle = _itertools.cycle(_FILLER_LINES)
_FILLER_LOCK = threading.Lock()


async def _say_filler(context, custom: str = "") -> None:
    """Speak a brief holding phrase over the session so a tool fetch never sits in dead air. Never
    raises; if the session/say is unavailable it's a silent no-op (the fetch still runs)."""
    if (os.getenv("AIM_FILLER", "1").strip().lower() in ("0", "false", "no", "off")):
        return
    try:
        sess = getattr(context, "session", None)
        if sess is None:
            return
        if custom:
            line = custom
        else:
            with _FILLER_LOCK:
                line = next(_filler_cycle)
        # don't await: let the holding phrase play WHILE the fetch runs (zero added latency)
        await sess.say(line, allow_interruptions=True, add_to_chat_ctx=False)
    except Exception:  # noqa: BLE001
        pass


# ── RAG grounding helpers (kb.retrieve, READ-ONLY, import-safe-degrade) ─────────
# VoiceAgentRAG pattern (design/latency-research.md §6): at call connect, run ONE off-hot-path
# kb.retrieve for the resolved campaign and fold the chunks into the agent instructions as a
# "GROUNDING (verified facts)" block (zero per-turn latency); a `lookup` tool then covers deep
# questions mid-call. Every entrypoint returns "" / [] on any failure -> a KB outage cannot break
# a call. The query SEED is the campaign name + product + a few sales-relevant probe words so the
# prefetch surfaces the price / location / USP / objection chunks the agent most often needs.
_GROUNDING_PREFETCH_K = int(os.getenv("AIM_KB_PREFETCH_K", "5") or 5)
_GROUNDING_LOOKUP_K = int(os.getenv("AIM_KB_LOOKUP_K", "3") or 3)
_GROUNDING_CHAR_CAP = int(os.getenv("AIM_KB_GROUNDING_CHARS", "1400") or 1400)


def _kb_retrieve(tenant_id: str, query: str, *, campaign_id: str, top_k: int) -> list[dict]:
    """Thin READ-ONLY wrapper over kb.retrieve, scoped to this tenant + campaign + the voice channel.
    Returns [] on any failure (KB absent / PG down / no hits) so every caller no-ops cleanly."""
    if _kb is None or not tenant_id or not (query or "").strip():
        return []
    try:
        return _kb.retrieve(tenant_id, query, top_k=top_k, scope="business",
                            channel="voice", scope_campaign_id=campaign_id or "") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM kb.retrieve degrade (return []): %r", exc)
        return []


def _format_grounding(rows: list[dict], *, char_cap: int = _GROUNDING_CHAR_CAP) -> str:
    """Render retrieved chunks into a compact, prompt-ready GROUNDING block (char-capped). '' when no
    rows -> the instructions are unchanged (exactly today's behaviour)."""
    if not rows:
        return ""
    lines: list[str] = []
    used = 0
    for r in rows:
        body = (r.get("content") or "").strip()
        if not body:
            continue
        sec = (r.get("section") or "").strip()
        piece = (f"- ({sec}) {body}" if sec else f"- {body}")
        piece = " ".join(piece.split())  # collapse newlines/whitespace for a tight block
        if used + len(piece) > char_cap:
            piece = piece[: max(0, char_cap - used)]
        if not piece:
            break
        lines.append(piece)
        used += len(piece)
        if used >= char_cap:
            break
    if not lines:
        return ""
    return (
        "\n\n=== GROUNDING (verified facts retrieved for THIS project — quote these for "
        "price / location / specs / objections; if a detail isn't here, call the `lookup` tool or "
        "say the team will confirm — NEVER invent specifics) ===\n" + "\n".join(lines) + "\n"
    )


def _grounding_seed(fields: dict) -> str:
    """Build the prefetch query seed from the resolved campaign fields: project + product + location
    + a few high-frequency sales probe words so the top chunks cover price/USP/objection up front."""
    f = fields or {}
    parts = [
        str(f.get("_campaign_name") or ""),
        str(f.get("product_name") or ""),
        str(f.get("product_summary") or "")[:160],
        str(f.get("location") or ""),
        "price location amenities USP objection",
    ]
    return " ".join(p for p in parts if p).strip()[:400]


# ── the Manager Agent (persona + PIN gate + command tools) ─────────────────────
def _build_instructions(caller_id: str, is_manager: bool, role: str) -> str:
    """The system prompt. Greeting is spoken separately via session.say(); this drives the convo
    AFTER the greeting. Manager (registered + PIN) vs customer (sales) phrased here."""
    common = (
        f"You are {_AGENT_VOICE}, the AI manager for {_COMPANY}. You are on a LIVE phone call. "
        "Speak like a warm, natural human — short, conversational sentences (1-2 at a time), in the "
        "SAME language/code-mix the caller uses (Hinglish/Hindi/English). NEVER sound robotic and "
        "NEVER say 'I am an AI assistant from'. Keep replies brief; let the caller talk.\n\n"
    )
    if is_manager:
        return common + (
            "This caller is a REGISTERED MANAGER of the business. Before revealing ANY business data "
            "or running ANY action, you MUST verify their identity: ask for their 4-digit PIN and call "
            "the `verify_pin` tool with what they say. Do NOT reveal data or run actions until "
            "`verify_pin` returns verified=true. If the PIN is wrong, let them try again politely; never "
            "go silent.\n\n"
            "ONCE VERIFIED you have FULL read + action access to this whole account, through REAL tools:\n"
            "• `list_campaigns` — ALL campaigns with their names and status. Call this for 'how many "
            "campaigns / what campaigns do I have / my other campaigns / list them', AND before you "
            "resolve any campaign by name.\n"
            "• `campaign_details(campaign)` — full info on ONE campaign (status, product, goal, "
            "language, calling window).\n"
            "• `campaign_analytics(campaign)` — that campaign's real numbers (dialed/connected/"
            "answered/interested/qualified/voicemail).\n"
            "• `check_leads(campaign)` — lead counts (total / hot / warm / cold). campaign is optional.\n"
            "• `recent_calls(count)` — a summary of the latest calls.\n"
            "• `analytics` — overall totals (calls, answered, voicemail) across campaigns.\n"
            "• `wallet_status` — their balance / plan.\n"
            "• `run_campaign(campaign, segment, count, confirmed)` — STARTS a real calling campaign "
            "(this DIALS phones and spends money).\n\n"
            "🚫 NO HALLUCINATION — THIS IS THE #1 RULE: For ANY fact, number, name, status, count, list "
            "or result — campaigns, leads, calls, analytics, wallet — you MUST call a tool and say ONLY "
            "what the tool returns. NEVER invent or guess a campaign name, a count, a number, or a "
            "result, and never answer from memory. If you don't know a campaign's name, call "
            "list_campaigns first. If a tool returns nothing or an error, SAY SO plainly ('I don't see "
            "a campaign by that name' / 'I couldn't pull that just now') — do not make something up. If "
            "there is genuinely no tool for what they asked, say you can't fetch that yet. It is always "
            "better to say 'let me check' and call a tool than to answer from your head.\n\n"
            "TOOL-ARG TIP: it is SAFE to pass numbers and yes/no as plain strings (count=\"5\", "
            "confirmed=\"true\"); always include every argument. Pass the campaign name exactly as the "
            "manager said it — the tools match it forgivingly.\n\n"
            "RUNNING A CAMPAIGN (risky — dials real phones + spends money): slot-fill conversationally "
            "FIRST. If they didn't name a campaign, call list_campaigns and ask which one. If they "
            "didn't say which leads, ask 'hot, warm, or all?' (treat 'everyone'/'all corporates'/any "
            "group word as 'all'). Then call run_campaign with confirmed=\"false\" to get a read-back, "
            "SPEAK that exact read-back, and only call run_campaign again with confirmed=\"true\" AFTER "
            "they clearly say yes. Do NOT tell the caller you are dialing until run_campaign actually "
            "returns its result — speak the real outcome it gives you (e.g. how many leads are dialing). "
            "Never claim a call went out unless the tool confirmed it.\n\n"
            "• `transfer_to_human(reason)` — connect to a REAL person on the team (warm transfer). The "
            "MOMENT they ask to talk to a human/person/insaan, call this tool IMMEDIATELY in the SAME "
            "turn — do NOT ask 'shall I transfer you' first and do NOT just SAY you're connecting them "
            "and then wait; calling the tool is what actually connects them, merely talking about it "
            "leaves the caller in silence. Call it only when they explicitly ask for a human or you "
            "genuinely cannot handle what they need. It dials a team member into the call; once it hands "
            "off, stop talking and let the human take over.\n\n"
            "• `list_handoff()` / `add_handoff(phone,name,priority)` / `remove_handoff(phone)` — manage "
            "the manager's HUMAN HANDOFF TEAM (the people you warm-transfer and send hot-lead alerts "
            "to). When they say things like 'add Rajesh +91… to my handoff team', 'list my handoff "
            "team', 'remove that number', call these. Read back the number you heard to confirm before "
            "adding. These are verified-manager only.\n\n"
            "Keep every reply short and natural; let the manager talk. If they just want to chat, answer."
        )
    return common + (
        "This is a customer/prospect calling in. Be a helpful, friendly sales assistant for "
        f"{_COMPANY}. Find out what they need, answer their questions warmly, and offer to have the team "
        "follow up. Do NOT ask for any PIN. Keep it natural and short."
    )


# ── HUMAN WARM TRANSFER helper (shared by BOTH agents) ─────────────────────────
def _transfer_whisper(reason: str, name: str, phone: str, summary: str) -> str:
    """ULTRA-BRIEF in-room hand-off line spoken once as the human joins, then the AI exits (aclose).
    NOTE: per-participant private audio isn't possible in a shared SIP room, so the CALLER hears this
    too — so it must stay clean: no phone number, no reason, no AI-disclosure, no summary dump. Just a
    one-line nudge to the human to take over. (reason/phone/summary kept in the signature for callers
    and chat_ctx but intentionally NOT spoken into the shared room.)"""
    who = (name or "").strip()
    if who:
        return f"{who} aapse baat karna chahte hain — aap baat kar sakte hain."
    return "Aap dono ab baat kar sakte hain."


# ── HANDOFF VOICE-UX HELPERS (hold audio · availability gate · per-attempt analytics) ───────────
# All best-effort + NEVER raise: any failure here degrades the UX (e.g. no music) but can never break
# or silence the live call. The bridge itself (create_sip_participant into the caller room) is left
# exactly as it was — these only wrap it with reassurance, gating, visibility, and a durable log.
_HOLD_VOLUME = float(os.getenv("AIM_HOLD_VOLUME", "0.5") or 0.5)
_HOLD_ENABLED = os.getenv("AIM_HOLD_AUDIO", "1").strip().lower() not in ("0", "false", "no", "off")
# durable per-attempt analytics sink (JSONL, next to the other var/ state; mirrors live_registry base).
_HANDOFF_LOG = os.getenv(
    "AIM_HANDOFF_LOG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "var", "aim_handoff_attempts.jsonl"),
)
_IST_OFFSET_SEC = 5 * 3600 + 30 * 60  # Asia/Kolkata, no DST


def _now_ist_hm() -> str:
    """Current wall-clock 'HH:MM' in IST (no tz database dependency)."""
    try:
        return datetime.fromtimestamp(time.time() + _IST_OFFSET_SEC, tz=timezone.utc).strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return ""


def _within_hours(hours: str) -> bool:
    """Availability gate for ONE handoff number. `hours` is a free string from the tenant's brain:
    "24x7"/"always"/"" -> always available; "HH:MM-HH:MM" (IST) -> in-window only (handles wrap past
    midnight). Anything unparseable -> treat as available (fail-OPEN: never block a transfer on a
    formatting quirk — we'd rather try the number than skip a reachable human)."""
    h = (hours or "").strip().lower()
    if not h or h in ("24x7", "24/7", "always", "anytime", "all", "any"):
        return True
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-–to]+\s*(\d{1,2}):(\d{2})", h)
    if not m:
        return True
    try:
        s = f"{int(m.group(1)):02d}:{m.group(2)}"
        e = f"{int(m.group(3)):02d}:{m.group(4)}"
        now = _now_ist_hm()
        if not now:
            return True
        if s <= e:
            return s <= now <= e
        return now >= s or now <= e  # window wraps past midnight (e.g. 21:00-06:00)
    except Exception:  # noqa: BLE001
        return True


def _handoff_log_attempt(tenant_id: str, room: str, number: str, idx: int,
                         outcome: str, wait_s: float, reason: str = "") -> None:
    """Append ONE handoff attempt to the durable JSONL analytics sink. NEVER raises."""
    try:
        os.makedirs(os.path.dirname(_HANDOFF_LOG), exist_ok=True)
        rec = {
            "ts": round(time.time(), 3),
            "iso": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id or "",
            "room": room or "",
            "number": number or "",
            "attempt": int(idx),
            "outcome": outcome or "",          # answered | no_answer | busy | invalid | out_of_hours | error
            "wait_s": round(float(wait_s or 0), 2),
            "reason": (reason or "")[:160],
        }
        with open(_HANDOFF_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


async def _start_hold_audio(room_obj, session):
    """Start calm HOLD music to the CALLER, in the CALLER's CURRENT room (NOT a side room), played by
    US on our own track. Returns (player, handle) so the caller can stop it the instant the human
    answers — or (None, None) if the audio API/room is unavailable (then we degrade to spoken
    reassurance only). NEVER raises: hold music is a comfort layer, never load-bearing."""
    if not (_HOLD_ENABLED and _BgAudio is not None and _Clip is not None and room_obj is not None):
        return None, None
    try:
        # thinking/ambient OFF — we drive the clip ourselves so we fully control start/stop.
        player = _BgAudio(thinking_sound=None)
        await player.start(room=room_obj, agent_session=session)
        if _AudioCfg is not None:
            clip = _AudioCfg(_Clip.HOLD_MUSIC, volume=_HOLD_VOLUME)
        else:  # pragma: no cover — config class absent; play the raw clip enum
            clip = _Clip.HOLD_MUSIC
        handle = player.play(clip, loop=True)  # loop so it never runs out under a long ring
        return player, handle
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM hold-audio start failed (degrading to spoken-only): %r", exc)
        return None, None


async def _stop_hold_audio(player, handle):
    """Stop hold music + release the player track. Idempotent + NEVER raises. Called the instant the
    human answers (so the caller doesn't hear music over the live human) and on every exit path."""
    try:
        if handle is not None:
            try:
                handle.stop()
            except Exception:  # noqa: BLE001
                pass
        if player is not None:
            try:
                await player.aclose()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


async def _do_warm_transfer(agent, context, reason: str) -> str:
    """Bridge the LIVE caller to a real human. Picks the first eligible handoff number and DIALS
    that human INTO the current room via LiveKit's native WarmTransferTask (CreateSIPParticipant on
    the OUTBOUND trunk -> brief with chat_ctx -> MoveParticipant = warm conference; carrier-agnostic,
    no REFER). Speaks a brief line to the caller first, and fires the hot-lead WhatsApp SIMULTANEOUSLY
    (belt-and-braces). If no human answers / dial fails on every number, falls back to a logged
    callback + the (already-sent) hot-lead WhatsApp — NEVER a dead drop. Returns a spoken-friendly
    string for the LLM to read. NEVER raises."""
    tenant_id = getattr(agent, "_tenant_id", "") or ADMIN_TENANT
    caller_id = getattr(agent, "_caller_id", "") or ""
    name = getattr(agent, "_caller_name", "") or ""
    summary = _summary_for_handoff(agent)

    session = getattr(context, "session", None)

    # 1) read the vendor handoff team (filesystem, no HTTP/auth). Priority-sorted already.
    team = []
    if _vt is not None:
        try:
            team = await asyncio.to_thread(_vt.handoff_list, tenant_id) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM handoff_list failed: %r", exc)
            team = []

    # 1b) GATING: keep only ENABLED numbers that are WITHIN their availability hours (priority order).
    #     A disabled/out-of-hours number is skipped (and logged as such for analytics), never dialed.
    eligible = []
    for h in team:
        if h.get("enabled") is False:
            continue
        eligible.append(h)
    dialable = [h for h in eligible if _within_hours(str(h.get("hours", "") or ""))]

    # 2) REASSURANCE — speak ONE clean line to the caller immediately (off-loop so it overlaps the dial;
    #    the caller is NEVER in dead air). The hold AUDIO is started below, just before the first ring.
    #    The line NAMES the person we're connecting them to and NOTHING ELSE — no phone number, no
    #    reason, no AI-disclosure (the dialed person = the first eligible handoff entry, priority order;
    #    fallback "apni team" when no name/role is on the entry). Caller-language Hinglish.
    _dial_who = "apni team"
    if dialable:
        _d0 = dialable[0]
        _dn = str(_d0.get("name", "") or "").strip() or str(_d0.get("role", "") or "").strip()
        if _dn:
            _dial_who = _dn
    await _say_filler(
        context,
        f"Ek second, main aapko {_dial_who} se connect kar rahi hoon.")

    # 3) fire the hot-lead WhatsApp SIMULTANEOUSLY (belt-and-braces; lands the lead in the team's chat).
    if _vt is not None and team:
        try:
            asyncio.create_task(asyncio.to_thread(
                _vt.notify_handoff_team, name, caller_id, summary, 80))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM handoff WA notify spawn failed: %r", exc)

    # 4) if no team configured (or none enabled/in-hours) -> capture + WhatsApp(if any) + callback.
    if not team:
        logger.info("AIM transfer_to_human: NO handoff team (tenant=%s) -> callback fallback", tenant_id)
        return ("no_human_available: there's no team member on the handoff list to connect right now. "
                "Warmly tell the caller our team will call them back very shortly, confirm their number, "
                "and close politely — never leave them hanging.")

    # 5) resolve the LIVE room + a LiveKit API handle from the running job. This is the SAME room the
    #    caller is in -> dialing the human here = an instant 2-way conference bridge (no side room, no
    #    secondary agent). We REUSE the earner's outbound trunk id as a STRING only.
    job_ctx = None
    try:
        job_ctx = _get_job_context()
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM transfer_to_human: no job context (%r) -> WA+callback fallback", exc)
        job_ctx = None
    room_obj = getattr(job_ctx, "room", None) if job_ctx is not None else None
    room_name = getattr(room_obj, "name", "") or getattr(agent, "_room_name", "") or ""
    lk_api = getattr(job_ctx, "api", None) if job_ctx is not None else None
    if job_ctx is None or not room_name or lk_api is None:
        logger.warning("AIM transfer_to_human: room/api unavailable (room=%r api=%s) -> WA+callback fallback",
                       room_name, lk_api is not None)
        _live_set_handoff(room_name, "Failed")
        return ("handoff_logged: I couldn't open a live bridge just now, but I've alerted the team with "
                "the caller's details on WhatsApp. Tell the caller a team member will call them right "
                "back, confirm the number, and close warmly.")

    # 5b) if EVERY number is disabled or out-of-hours -> never dead air: apology + callback + WA(already).
    if not dialable:
        logger.info("AIM transfer_to_human: no eligible number (enabled+in-hours) tenant=%s -> callback",
                    tenant_id)
        for h in eligible:
            _handoff_log_attempt(tenant_id, room_name,
                                 (h.get("phone") or h.get("whatsapp") or ""), 0,
                                 "out_of_hours", 0.0, str(h.get("hours", "")))
        _live_set_handoff(room_name, "Failed")
        return ("no_human_available_now: the team isn't available at this hour, but I've alerted them with "
                "the caller's details on WhatsApp. Warmly tell the caller a team member will call them back, "
                "confirm their number, and close politely — never leave them hanging.")

    _live_set_handoff(room_name, "Requested")
    # HCRB fix (h): journal the handoff REQUEST so the lifecycle (requested -> dialing #N -> bridged ->
    # ai-exited -> human-hangup) is fully traceable in journalctl for a real call.
    logger.info("AIM handoff lifecycle: REQUESTED (tenant=%s caller=%s reason=%r eligible=%d) room %s",
                tenant_id, _mask(caller_id), (reason or "")[:80], len(dialable), room_name)

    # 5c) HOLD AUDIO — start calm music to the CALLER, in the CALLER's room, played by US. It loops
    #     under the whole ring sequence and is STOPPED the instant a human answers (step 6). If the
    #     audio API is unavailable we degrade to spoken-reassurance only (never blocks the bridge).
    hold_player, hold_handle = await _start_hold_audio(room_obj, session)

    # 6) dial each eligible human DIRECTLY INTO THE CALLER'S CURRENT ROOM (priority order) until one
    #    answers. The dial runs in a BACKGROUND TASK so the caller keeps hearing hold music while the
    #    human's phone rings (no dead air); we await the task with a hard timeout. On answer we STOP
    #    the hold, whisper ONE context line to the human, then step back. create_sip_participant(
    #    room_name=<caller room>) = the EXACT earner dial primitive (caller.py:/run) — same room, so
    #    caller + human hear each other immediately. The hot-lead WA already fired (step 3).
    last_err = ""
    bridged_num = ""
    try:
        for i, h in enumerate(dialable, start=1):
            num = (h.get("phone") or h.get("whatsapp") or "").strip()
            if not num:
                continue
            # invalid phone -> log + skip to next (never dial a malformed number).
            if not (num.startswith("+") and num[1:].isdigit() and 10 <= len(num[1:]) <= 15):
                logger.info("AIM transfer_to_human: invalid number %s (attempt #%d) -> next", _mask(num), i)
                _handoff_log_attempt(tenant_id, room_name, num, i, "invalid", 0.0, "bad_format")
                last_err = "invalid_number"
                continue
            logger.info("AIM transfer_to_human: dialing #%d human %s (role=%s) INTO caller room %s",
                        i, _mask(num), h.get("role", ""), room_name)
            # LIVE registry: surface the CURRENT number + attempt index (panel shows "Dialing #1 → …").
            _live_set_handoff(room_name, f"Dialing #{i}", target=num)
            t0 = time.time()
            try:
                req = _lk_api.CreateSIPParticipantRequest(
                    sip_trunk_id=_OUTBOUND_TRUNK,          # read-only reuse of the earner's trunk id
                    sip_call_to=num,
                    room_name=room_name,                   # ← the CALLER'S room == the bridge
                    participant_identity=f"human-handoff-{num}",
                    participant_name=(h.get("role") or "Team") + " (human)",
                    participant_metadata="aim-human-handoff",
                    wait_until_answered=True,              # task blocks until answer/fail; caller hears hold
                    ringing_timeout=_DurationLK(seconds=int(_TRANSFER_RING_TIMEOUT)),
                )
                # run the (blocking) dial in a background task so the caller's hold music keeps playing.
                dial_task = asyncio.create_task(
                    lk_api.sip.create_sip_participant(req, timeout=_TRANSFER_RING_TIMEOUT + 15))
                await asyncio.wait_for(dial_task, timeout=_TRANSFER_RING_TIMEOUT + 12)
            except asyncio.TimeoutError:
                last_err = "ring_timeout"
                logger.info("AIM transfer_to_human: %s no-answer (ring timeout) #%d -> next", _mask(num), i)
                _handoff_log_attempt(tenant_id, room_name, num, i, "no_answer", time.time() - t0, "timeout")
                continue
            except Exception as exc:  # noqa: BLE001 — busy(486) / declined / no-answer -> next number
                last_err = f"{type(exc).__name__}:{str(exc)[:120]}"
                low = last_err.lower()
                outcome = "busy" if ("486" in low or "busy" in low) else "no_answer"
                logger.info("AIM transfer_to_human: %s didn't connect (%s) #%d -> next",
                            _mask(num), last_err, i)
                _handoff_log_attempt(tenant_id, room_name, num, i, outcome, time.time() - t0, last_err)
                continue
            # answered -> the human is now a participant in the caller's room (audibly bridged).
            bridged_num = num
            wait_s = time.time() - t0
            logger.info("AIM transfer_to_human: BRIDGED %s into room %s (#%d, %.1fs)",
                        _mask(num), room_name, i, wait_s)
            _handoff_log_attempt(tenant_id, room_name, num, i, "answered", wait_s)
            # STOP the hold music the INSTANT the human answers (caller must not hear music over them).
            await _stop_hold_audio(hold_player, hold_handle)
            hold_player, hold_handle = None, None
            _live_set_handoff(room_name, "Bridged", target=num)
            # WHISPER ONE line of context as the human joins (brief in-room line — per-participant
            # private audio isn't available in a shared SIP room, so we say it in-room, THEN step back).
            try:
                whisper = _transfer_whisper(reason, name, caller_id, summary)
                if session is not None:
                    await session.say(whisper, allow_interruptions=False, add_to_chat_ctx=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM transfer whisper failed (non-fatal): %r", exc)
            # HCRB fix (e) — AI EXIT (CORE). The soft return-string "now stop talking" was the
            # documented root cause: it leaves the AgentSession ALIVE (still consuming STT/LLM), so
            # the AI keeps reacting over the human. Mute alone is NOT enough (the session stays alive).
            # The real exit = aclose() the AgentSession AFTER the human is bridged + the one short
            # whisper has played out: the AI's STT/LLM/TTS stop and it disconnects, while the ROOM,
            # the CALLER and the bridged HUMAN all persist (the human and caller keep talking). The
            # room-disconnect shutdown hooks (memory/lead persist, _slog.finish, _live_remove) still
            # run as normal. We log the lifecycle for observability (fix h).
            logger.info("AIM transfer_to_human: AI-EXITED (session.aclose) after bridge -> %s room %s",
                        _mask(bridged_num), room_name)
            _live_set_handoff(room_name, "AI exited (human live)", target=bridged_num)
            if session is not None:
                try:
                    await session.aclose()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AIM session.aclose after bridge failed (non-fatal): %r", exc)
            return ("handed_off")
    finally:
        # belt-and-braces: never leave hold music playing on any exit path.
        await _stop_hold_audio(hold_player, hold_handle)

    # 7) nobody answered on any number -> never a dead drop. The hot-lead WA already fired (step 3).
    _live_set_handoff(room_name, "Failed")
    logger.info("AIM transfer_to_human: no human answered (last_err=%s) -> callback fallback", last_err)
    return ("no_human_answered: I couldn't reach a team member live, but I've alerted them with the "
            "caller's details on WhatsApp. Reassure the caller warmly that the team will call them "
            "back very shortly, confirm their number, and close politely — never leave them hanging.")


def _summary_for_handoff(agent) -> str:
    """Best-effort one-line context for the human/WhatsApp: campaign + caller name + any interest note."""
    parts = []
    nm = getattr(agent, "_caller_name", "") or ""
    if nm:
        parts.append(f"Caller: {nm}")
    fields = getattr(agent, "_fields", {}) or {}
    cn = fields.get("_campaign_name") or getattr(agent, "_campaign_name", "") or ""
    if cn:
        parts.append(f"Project: {cn}")
    note = fields.get("_interest_note") or ""
    if note:
        parts.append(f"Wants: {note}")
    return " | ".join(parts) if parts else "Hot inbound caller — wants to speak to a human."


class ManagerAgent(Agent):
    """A normal LiveKit Agent (mirrors the outbound _MirrorAgent shape) carrying the PIN-verify and
    command tools. The LLM speaks; tools enforce policy. NOTHING here gates the greeting/audio."""

    def __init__(self, *, caller_id: str, tenant_id: str, role: str, is_manager: bool,
                 session_id: str) -> None:
        super().__init__(instructions=_build_instructions(caller_id, is_manager, role))
        self._caller_id = caller_id
        self._tenant_id = tenant_id or ADMIN_TENANT
        self._role = role or "manager"
        self._is_manager = is_manager
        self._session_id = session_id
        self._verified = False

    @function_tool
    async def verify_pin(self, context: RunContext, pin: str) -> str:
        """Verify the manager's spoken/keyed 4-digit PIN before any data or action.

        Args:
            pin: the digits the caller said or keyed (e.g. "4827"). Spoken words like "four eight two
                 seven" should be converted to digits before calling.
        """
        digits = _extract_digits(pin or "", n=_PIN_LEN)
        if len(digits) < _PIN_LEN:
            return "no_pin_heard: ask the caller to clearly say or key their 4-digit PIN again."
        try:
            import firewall as _fw
            ok = bool(_fw.check_pin(self._tenant_id, digits))
        except Exception as exc:  # noqa: BLE001
            logger.warning("verify_pin firewall error: %r", exc)
            ok = False
        if ok:
            self._verified = True
            logger.info("AIM PIN verified tenant=%s caller=%s", self._tenant_id, _mask(self._caller_id))
            return "verified=true: identity confirmed. You may now help the manager. Greet them warmly and ask what they'd like to do."
        logger.info("AIM PIN mismatch tenant=%s caller=%s", self._tenant_id, _mask(self._caller_id))
        return "verified=false: that PIN didn't match. Politely ask the caller to try once more (never go silent)."

    @function_tool
    async def manager_status(self, context: RunContext) -> str:
        """After the manager is verified, give a brief spoken business status (campaigns/leads/calls).
        Returns a short summary string the assistant should read out naturally."""
        if not self._verified:
            return "not_verified: ask for the PIN and call verify_pin first; do not reveal any data yet."
        try:
            summary = _quick_status(self._tenant_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("manager_status failed: %r", exc)
            summary = "I couldn't pull the latest numbers right now."
        return summary

    # ── SAFE READ tools (verified manager only; no extra PIN) ──────────────────
    def _gate_read(self) -> str | None:
        if not self._verified:
            return "not_verified: ask for the PIN and call verify_pin first; do not reveal any data yet."
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the system right now."
        return None

    @function_tool
    async def check_leads(self, context: RunContext, campaign: str = "") -> str:
        """Report the manager's REAL lead counts (total + hot/warm/cold). Use for "how many leads",
        "lead counts", "how many hot leads". Safe read — needs the manager already PIN-verified.

        Args:
            campaign: the campaign name the manager mentioned, or "" if they didn't name one (counts
                      are the whole lead pool either way). ALWAYS optional — never block on it.
        """
        gate = self._gate_read()
        if gate:
            return gate
        # WARM-SNAPSHOT (fix D): if we prefetched lead counts at connect, answer from memory (<5ms)
        snap = getattr(self, "_hot_leads_summary", "")
        if snap and not (campaign or "").strip():
            logger.info("AIM check_leads -> warm snapshot hit")
            return snap
        await _say_filler(context)  # fix C: no dead air while we fetch
        try:
            res = await asyncio.to_thread(_vt.lead_counts, campaign)
        except Exception as exc:  # noqa: BLE001
            logger.warning("check_leads failed: %r", exc)
            return "I couldn't pull the lead numbers right now."
        logger.info("AIM check_leads -> %s", res.get("summary", "")[:80])
        return res.get("summary", "I couldn't pull the lead numbers right now.")

    @function_tool
    async def recent_calls(self, context: RunContext, count: str = "5") -> str:
        """Give a short spoken summary of the most RECENT calls (name + outcome). Safe read.

        Args:
            count: how many recent calls to summarize (use "5" if the manager didn't specify; max 20).
                   It is SAFE to pass this as a plain string like "5".
        """
        gate = self._gate_read()
        if gate:
            return gate
        count = _to_int(count, 5)
        if not count or count < 1:
            count = 5
        await _say_filler(context)  # fix C
        try:
            res = await asyncio.to_thread(_vt.recent_calls, count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("recent_calls failed: %r", exc)
            return "I couldn't pull the recent calls right now."
        return res.get("summary", "I couldn't pull the recent calls right now.")

    @function_tool
    async def analytics(self, context: RunContext) -> str:
        """Give a spoken analytics summary — total calls, answered, voicemail, across campaigns. Safe read."""
        gate = self._gate_read()
        if gate:
            return gate
        await _say_filler(context)  # fix C
        try:
            res = await asyncio.to_thread(_vt.analytics)
        except Exception as exc:  # noqa: BLE001
            logger.warning("analytics failed: %r", exc)
            return "I couldn't pull the analytics right now."
        return res.get("summary", "I couldn't pull the analytics right now.")

    @function_tool
    async def wallet_status(self, context: RunContext) -> str:
        """Tell the manager their current wallet balance / plan. Safe read."""
        gate = self._gate_read()
        if gate:
            return gate
        await _say_filler(context)  # fix C
        try:
            res = await asyncio.to_thread(_vt.wallet_status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wallet_status failed: %r", exc)
            return "I couldn't reach the wallet right now."
        return res.get("summary", "I couldn't reach the wallet right now.")

    @function_tool
    async def list_campaigns(self, context: RunContext) -> str:
        """List ALL of the manager's REAL campaigns (count + each name and status). Use this WHENEVER
        the caller asks "how many campaigns / what campaigns do I have / list my campaigns / my other
        campaigns" — or before resolving a campaign by name. Speak ONLY the names this returns; NEVER
        invent a campaign name or count. Safe read."""
        gate = self._gate_read()
        if gate:
            return gate
        # WARM-SNAPSHOT (fix D): answer from the connect-time prefetch when present (<5ms, no fetch)
        snap = getattr(self, "_hot_campaigns_summary", "")
        if snap:
            logger.info("AIM list_campaigns -> warm snapshot hit")
            return snap
        await _say_filler(context)  # fix C
        try:
            res = await asyncio.to_thread(_vt.campaigns_summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_campaigns failed: %r", exc)
            return "I couldn't pull your campaigns right now."
        logger.info("AIM list_campaigns -> count=%s", res.get("count"))
        return res.get("summary", "I couldn't pull your campaigns right now.")

    @function_tool
    async def campaign_details(self, context: RunContext, campaign: str = "") -> str:
        """Full details for ONE campaign (status, product, goal, language, calling window) — REAL data
        from the backend. Use when the caller asks about a specific campaign ("tell me about <name>",
        "what's the status of <name>", "details of <name>"). Resolves the spoken name forgivingly; if
        no match it says so and lists the real ones. NEVER invent details.

        Args:
            campaign: the campaign name or id the caller said (e.g. "Codename Joy", "DLF The Crest").
        """
        gate = self._gate_read()
        if gate:
            return gate
        if not (campaign or "").strip():
            return ("Which campaign would you like details on? You can ask me to list your campaigns "
                    "first.")
        await _say_filler(context)  # fix C
        try:
            res = await asyncio.to_thread(_vt.campaign_details, campaign)
        except Exception as exc:  # noqa: BLE001
            logger.warning("campaign_details failed: %r", exc)
            return f"I couldn't pull the details for {campaign} right now."
        logger.info("AIM campaign_details(%r) -> ok=%s", campaign, res.get("ok"))
        return res.get("summary", f"I couldn't pull the details for {campaign} right now.")

    @function_tool
    async def campaign_analytics(self, context: RunContext, campaign: str = "") -> str:
        """Per-campaign performance numbers (dialed, connected, answered, interested, qualified,
        voicemail) — REAL data. Use when the caller asks "how is <campaign> doing / numbers for
        <campaign> / results of <campaign>". Resolves the name first. NEVER invent numbers.

        Args:
            campaign: the campaign name or id the caller said.
        """
        gate = self._gate_read()
        if gate:
            return gate
        if not (campaign or "").strip():
            return ("Which campaign's numbers would you like? I can list your campaigns first if you "
                    "want.")
        await _say_filler(context)  # fix C
        try:
            res = await asyncio.to_thread(_vt.campaign_analytics, campaign)
        except Exception as exc:  # noqa: BLE001
            logger.warning("campaign_analytics failed: %r", exc)
            return f"I couldn't pull the numbers for {campaign} right now."
        logger.info("AIM campaign_analytics(%r) -> ok=%s", campaign, res.get("ok"))
        return res.get("summary", f"I couldn't pull the numbers for {campaign} right now.")

    # ── RISKY ACTION: run_campaign (dials phones) — PIN-gated + read-back confirm ──
    @function_tool
    async def run_campaign(self, context: RunContext, campaign: str = "",
                           segment: str = "all", count: str = "0", confirmed: str = "false") -> str:
        """START a real calling campaign — this DIALS phones (spends money). RISKY.

        BEFORE calling this with confirmed=true you MUST have: (1) the manager PIN-verified, and (2)
        read the action back to them ("I'll call N <segment> leads for <campaign> — should I go ahead?")
        and heard a clear yes. If you have NOT yet confirmed, call this with confirmed=false to get a
        read-back string to speak; only call again with confirmed=true after the manager agrees.

        Args:
            campaign: the campaign name the manager said (e.g. "Codename Joy").
            segment: which leads — "hot", "warm", "cold", or "all". Use "all" if they didn't specify
                     or said something free-form like "everyone"/"all corporates".
            count: how many leads to dial; use "0" to dial all in that segment. SAFE to pass as a
                   plain string like "5".
            confirmed: "false" the FIRST time (to get the read-back to speak); "true" ONLY after you
                       read the action back and the manager clearly said yes. SAFE to pass as the
                       string "true" or "false".
        """
        if not self._verified:
            return ("not_verified: this dials real phones — ask for the PIN and call verify_pin first. "
                    "Do not start any campaign until verified.")
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the calling system right now."
        # Coerce realtime-LLM stringy args (this is THE fix: strict int/bool typing made the validator
        # reject the call so the dial never fired). Accept strings, normalize here.
        n_count = _to_int(count, 0)
        is_confirmed = _to_bool(confirmed, False)
        seg = (segment or "all").strip().lower()
        if seg not in ("hot", "warm", "cold"):
            seg = "all"  # everyone / all corporates / free-text -> whole pool (never silent 0)
        logger.info("AIM run_campaign args campaign=%r segment=%r->%s count=%r->%d confirmed=%r->%s",
                    campaign, segment, seg, count, n_count, confirmed, is_confirmed)
        if not (campaign or "").strip():
            return ("need_campaign: ask the manager which campaign to run. If unsure, call "
                    "list_campaigns and read them the options first. Do not dial without a campaign.")
        # PRE-CONFIRM: return a read-back the agent speaks; do NOT dial yet.
        if not is_confirmed:
            await _say_filler(context)  # fix C: no dead air while we resolve campaign + audience
            try:
                camp = await asyncio.to_thread(_vt.resolve_campaign, campaign)
            except Exception:  # noqa: BLE001
                camp = None
            if camp is None:
                return (f"no_match: I couldn't find a campaign called {campaign}. "
                        "Call list_campaigns and read the manager the real options.")
            cname = _vt._camp_name(camp) or campaign
            try:
                aud = await asyncio.to_thread(_vt.resolve_audience, seg, n_count)
            except Exception:  # noqa: BLE001
                aud = []
            n = len(aud)
            if n == 0:
                return (f"no_leads: there are no {seg if seg != 'all' else ''} leads to call for "
                        f"{cname}. Ask the manager to pick a different group.")
            seg_txt = "" if seg == "all" else f"{seg} "
            return ("readback: SAY THIS and wait for a clear yes before calling run_campaign with "
                    f"confirmed=true — \"I'll start calling {n} {seg_txt}lead{'s' if n != 1 else ''} "
                    f"for {cname}. Should I go ahead?\"")
        # CONFIRMED: actually dial via the proven /run path.
        logger.info("AIM run_campaign CONFIRMED campaign=%r segment=%s count=%d caller=%s",
                    campaign, seg, n_count, _mask(self._caller_id))
        await _say_filler(context, "Theek hai, abhi calls start kar rahi hoon…")  # fix C
        try:
            res = await asyncio.to_thread(_vt.run_campaign, campaign, seg, n_count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_campaign failed: %r", exc)
            return "I hit a problem starting the campaign. Please try again in a moment."
        logger.info("AIM run_campaign result ok=%s job=%s count=%s",
                    res.get("ok"), res.get("job_id", ""), res.get("count", ""))
        # #8: persist this risky, PIN-gated command onto the session's command chain (best-effort).
        try:
            slog = getattr(self, "_slog", None)
            if slog is not None:
                slog.note_command(
                    intent="run_campaign",
                    args={"campaign": campaign, "segment": seg, "count": n_count},
                    result={"ok": res.get("ok"), "job_id": res.get("job_id", ""),
                            "count": res.get("count", "")},
                    pin_required=True, pin_verified=bool(self._verified),
                    risk_level=3, status=("executed" if res.get("ok") else "failed"))
        except Exception:  # noqa: BLE001
            pass
        return res.get("summary", "I couldn't start the campaign just now.")

    # ── test_call_me: ring the manager's OWN verified phone (the founder feels a real call) ──
    @function_tool
    async def test_call_me(self, context: RunContext) -> str:
        """Place a REAL test call to the MANAGER'S OWN phone — the verified caller-id they're calling
        from — so they can feel a live AI call ring their own handset. Use when the manager says things
        like "call me", "ring my phone", "give me a test call", "let me hear a sample call", "call my
        number". Needs the manager PIN-verified first (it dials a real phone + spends money). Dials via
        the same proven path as a campaign; speak ONLY the result it returns (don't claim it rang until
        the tool confirms)."""
        if not self._verified:
            return ("not_verified: this places a real call — ask for the PIN and call verify_pin first, "
                    "then try the test call.")
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the calling system right now."
        target = self._caller_id
        if not (target or "").strip():
            return ("no_number: I don't have your caller-id to ring back. Ask them to confirm the number "
                    "to call, or try from a number that shows its caller-id.")
        logger.info("AIM test_call_me -> dialing manager own number caller=%s", _mask(target))
        await _say_filler(context, "Theek hai, abhi aapke number par call laga rahi hoon…")  # fix C
        try:
            res = await asyncio.to_thread(_vt.test_call, "Manager", target, "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("test_call_me failed: %r", exc)
            return "I couldn't place the test call just now. Please try again in a moment."
        logger.info("AIM test_call_me result ok=%s job=%s", res.get("ok"), res.get("job_id", ""))
        return res.get("summary", "I couldn't place the test call just now.")

    @function_tool
    async def transfer_to_human(self, context: RunContext, reason: str = "") -> str:
        """Connect the caller to a REAL human team member (warm transfer). DEFAULT = handle it yourself;
        do NOT offer or jump to a human. Call this ONLY when the manager EXPLICITLY asks to talk to a
        person/human/insaan, OR you genuinely cannot handle their request. When one of those is true,
        call it IMMEDIATELY, in the same turn, the moment it applies (do not first ask 'shall I transfer
        you' or merely say you're connecting them and then wait — calling this tool is the ONLY thing
        that actually connects them). Dials the next available human from the handoff list INTO this call
        (a warm bridge) and steps you back; if no one answers, the team is alerted on WhatsApp and will
        call back. Speak the result it returns; once handed off, stop talking and let the human take
        over.

        Args:
            reason: a short reason for the transfer (e.g. "wants to speak to a person", "billing
                    dispute I can't resolve"). Pass as a plain string.
        """
        logger.info("AIM transfer_to_human (manager) reason=%r tenant=%s", (reason or "")[:80],
                    getattr(self, "_tenant_id", ""))
        return await _do_warm_transfer(self, context, reason or "")

    # ── HANDOFF-TEAM MANAGEMENT (conversational CRUD; verified manager only) ─────────────────────
    # The manager can curate WHO the AI warm-transfers / hot-lead-alerts to, by voice/chat:
    # "add Rajesh +91… to my handoff team", "remove +91…", "list my handoff team". Tenant-scoped to
    # the verified caller (self._tenant_id from their token), validated +91, durably audited.
    @function_tool
    async def list_handoff(self, context: RunContext) -> str:
        """List THIS manager's human-handoff team (the people the AI warm-transfers / alerts to).
        Use for "list my handoff team", "who's on my handoff list", "who do you transfer to".
        Verified-manager only. Reads the live list; speak it back naturally."""
        if not self._verified:
            return "not_verified: ask for the PIN and call verify_pin first; do not reveal any data yet."
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the system right now."
        try:
            team = await asyncio.to_thread(_vt.handoff_list, self._tenant_id) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM list_handoff failed: %r", exc)
            return "I couldn't pull your handoff team just now. Please try again in a moment."
        if not team:
            return ("handoff_empty: there's no one on your handoff team yet. Offer to add a team "
                    "member — ask for their name and mobile number.")
        lines = []
        for h in team:
            who = (h.get("name") or h.get("role") or "Team").strip() or "Team"
            num = h.get("phone") or h.get("whatsapp") or ""
            state = "" if h.get("enabled", True) else " (paused)"
            lines.append(f"{who} on {num}{state}")
        spoken = "; ".join(lines)
        return (f"handoff_team ({len(team)}): {spoken}. "
                "Read this back to the manager naturally, in priority order.")

    @function_tool
    async def add_handoff(self, context: RunContext, phone: str = "", name: str = "",
                          priority: str = "", whatsapp: str = "") -> str:
        """Add (or update) a person on THIS manager's human-handoff team so the AI can warm-transfer
        and send hot-lead alerts to them. Use for "add Rajesh +916375548830 to my handoff team",
        "add my sales head 98765…". Verified-manager only.

        Args:
            phone: the team member's mobile, ANY spoken form ("+91 63755 48830", "six three…",
                   "9876543210"). It is canonicalised to +91XXXXXXXXXX; reject non-Indian-mobiles.
            name:  who they are / their role (e.g. "Rajesh", "sales head"). Optional.
            priority: dialing order as a STRING ("1" = tried first). "" = append at the end. Optional.
            whatsapp: a different WhatsApp number if they gave one; "" = same as phone. Optional.
        """
        if not self._verified:
            return ("not_verified: this changes who real calls get transferred to — ask for the PIN "
                    "and call verify_pin first.")
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the system right now."
        prio = _to_int(priority, 0)
        await _say_filler(context, "Theek hai, add kar rahi hoon…")
        try:
            res = await asyncio.to_thread(_vt.add_handoff, self._tenant_id, phone or "",
                                          name or "", prio, whatsapp or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM add_handoff failed: %r", exc)
            return "I couldn't add that number just now. Please try again in a moment."
        if not res.get("ok"):
            if res.get("note") == "invalid_phone":
                return res.get("spoken", "That number didn't look valid — please say a 10-digit Indian mobile.")
            return "I couldn't add that number just now. Please try again in a moment."
        n = len(res.get("handoff", []) or [])
        who = (name or "that person").strip() or "that person"
        logger.info("AIM add_handoff tenant=%s added=%s total=%d", self._tenant_id,
                    _mask(res.get("added", "")), n)
        return (f"added: {who} is now on your handoff team ({res.get('added','')}). You now have "
                f"{n} team member{'s' if n != 1 else ''}. Confirm this back to the manager warmly.")

    @function_tool
    async def remove_handoff(self, context: RunContext, phone: str = "") -> str:
        """Remove a person from THIS manager's human-handoff team. Use for "remove +916375548830
        from my handoff team", "take Rajesh off the list". Verified-manager only.

        Args:
            phone: the mobile to remove, ANY spoken form (canonicalised to +91XXXXXXXXXX).
        """
        if not self._verified:
            return ("not_verified: this changes who real calls get transferred to — ask for the PIN "
                    "and call verify_pin first.")
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the system right now."
        await _say_filler(context, "Theek hai, hata rahi hoon…")
        try:
            res = await asyncio.to_thread(_vt.remove_handoff, self._tenant_id, phone or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM remove_handoff failed: %r", exc)
            return "I couldn't update your handoff team just now. Please try again in a moment."
        if not res.get("ok"):
            return "I couldn't update your handoff team just now. Please try again in a moment."
        n = len(res.get("handoff", []) or [])
        if not res.get("removed"):
            return ("not_found: that number wasn't on your handoff team. Offer to list the team so the "
                    "manager can pick who to remove.")
        logger.info("AIM remove_handoff tenant=%s total=%d", self._tenant_id, n)
        return (f"removed: done — that number is off your handoff team. You now have {n} team "
                f"member{'s' if n != 1 else ''}. Confirm back to the manager warmly.")


# ── the Customer (sales) Agent — a natural human salesperson for NON-manager callers ───────────
def _build_sales_instructions(fields: dict, recap: str, caller_name: str,
                              is_returning: bool, pending_disambig: bool,
                              campaign_options: list[dict] | None,
                              grounding: str = "") -> str:
    """Render the inbound CUSTOMER persona. Body REUSES the outbound earner brain verbatim
    (prompt.build_system_prompt(fields)) when a campaign is resolved, so an inbound prospect gets the
    SAME proven Hinglish human-telecaller flow as an outbound call — but reframed for INBOUND (they
    called us). When no campaign is resolved yet, ask ONE open question to disambiguate. NEVER mentions
    a PIN. Greeting is spoken separately via session.say()."""
    company = (fields.get("company_name") if fields else "") or _COMPANY
    agent = (fields.get("agent_name") if fields else "") or _AGENT_VOICE

    head = (
        f"You are {agent}, a warm, real human salesperson for {company} on a LIVE INBOUND phone call — "
        "the CALLER dialled US because they're interested. Speak in short, natural beats (one or two "
        "sentences, then STOP and listen), in the SAME language/code-mix the caller uses "
        "(Hinglish/Hindi/English). NEVER sound robotic, NEVER say 'I am an AI assistant from', and "
        "NEVER ask for any PIN or password — this is a customer, not a manager. This is INBOUND: do "
        "NOT do the outbound 'is this a good time / do you have two minutes' permission opener — they "
        "called you, so get straight to warmly helping them.\n\n"
    )

    # Disambiguation mode (new caller, no campaign resolved yet): ONE open question, then match.
    if pending_disambig:
        opts = campaign_options or []
        names = "; ".join(o.get("name", "") for o in opts if o.get("name"))[:400]
        ask = (
            "You do NOT yet know which project/property this caller is asking about. Your FIRST job is "
            "to find out with ONE friendly open question — ask: \"Aap kis project ke baare mein jaanna "
            "chahte hain?\" (or the same idea in the caller's language). LISTEN to their answer, then "
            "call the `pick_campaign` tool with what they said so I can load the right project's "
            "details. Do NOT pitch any specifics until pick_campaign confirms a project — you must not "
            "give the wrong project's script.\n"
        )
        if names:
            ask += (f"\nFor YOUR reference only (do NOT read this whole list out unless they ask "
                    f"what's available), the active projects are: {names}. If they clearly name or "
                    "describe one, call pick_campaign with it. If they're unsure or just exploring, "
                    "you may briefly mention one or two by name and ask which interests them — then "
                    "call pick_campaign.\n")
        return head + ask + (
            "\nIf after a couple of tries you genuinely can't tell which project they mean, call "
            "`capture_interest` with their name and what they're looking for so the team can follow "
            "up — never leave them with the wrong details and never go silent.\n"
            "If the caller asks to talk to a human/person/agent/insaan, call the `transfer_to_human"
            "(reason)` tool IMMEDIATELY in that same turn (do NOT ask 'shall I transfer' or just say "
            "you're connecting them and wait — calling the tool is what actually connects them)."
        )

    # Campaign resolved. We REUSE the outbound earner brain (prompt.build_system_prompt) ONLY for its
    # campaign FACTS/knowledge (product, price, location, USPs, objection rebuttals, qualifying Qs) --
    # NOT for its conversation flow. That brain is written for an OUTBOUND cold call (scripted self-
    # intro + 'do minute hain?' permission + a top-down telecaller flow). For INBOUND we must NOT run
    # that opener/flow, so we fence the brain between a strong override header + footer that tell the
    # LLM: this is reference knowledge to ANSWER from, the customer leads, you react.
    brain = ""
    if _prompt is not None and fields:
        try:
            # HCRB fix (b): build the INBOUND brain with AI-disclosure OFF. We do NOT change
            # prompt.py defaults (the OUTBOUND earner reuses build_system_prompt with its own
            # disclose_ai=True default — untouched). We pass a per-call override dict that sets
            # disclose_ai=False, so the disclosure clause is NOT injected into this inbound brain.
            # The override does not mutate the caller's fields dict.
            _inb_fields = dict(fields)
            _inb_fields["disclose_ai"] = False
            brain = _prompt.build_system_prompt(_inb_fields)
        except Exception as exc:  # noqa: BLE001
            logger.warning("build_system_prompt failed (sales fallback): %r", exc)
            brain = ""
    if not brain:
        # Fallback brain if prompt module/fields unavailable — still helpful, still never silent.
        prod = (fields.get("product_name") if fields else "") or "our project"
        brain = (
            f"Help this caller about {prod}. Answer their questions warmly and accurately from what you "
            "know, find out what they're looking for (budget, configuration, timeline), and offer a "
            "site visit or a callback from the team. Keep it natural and short.\n"
        )

    recap_block = ""
    if is_returning and recap:
        nm = f" ({caller_name})" if caller_name else ""
        recap_block = (
            "\n\n=== PICHHLI BAAT (this SAME caller spoke to us before — CONTINUE that conversation, "
            f"don't restart) ==={nm}\n" + recap.strip() + "\n"
            "Greet them like someone you already know, briefly reference what you discussed last time, "
            "and pick the sale up from there — do NOT re-introduce the project from zero.\n"
        )
    elif caller_name:
        recap_block = f"\n\nThe caller's name on file is {caller_name} — use it warmly.\n"

    inbound_note = (
        "\n\nINBOUND REMINDER: they called YOU, so skip the outbound permission/identity opener — just "
        "warmly help. When the moment is right, move toward a concrete next step (site visit OR a "
        "callback / sharing details on WhatsApp) and confirm it. Keep every turn to one or two short "
        "sentences, then listen.\n\n"
        "HANDOFF TO A HUMAN — RARE, NOT A DEFAULT: your job is to handle the WHOLE call yourself and "
        "book the deal. Do NOT offer a human, do NOT suggest connecting them to someone, and do NOT jump "
        "to a human for ordinary questions, prices, objections, or a ready-to-buy lead — YOU close those "
        "yourself. Call the `transfer_to_human(reason)` tool ONLY in two cases: (1) the caller EXPLICITLY "
        "asks to talk to a person/human/agent/insaan/aadmi/banda (in ANY language), or (2) the caller is "
        "genuinely very hot or frustrated AND you truly cannot resolve or close it yourself. When one of "
        "those is true, ACT — DON'T ANNOUNCE: call transfer_to_human(reason) IMMEDIATELY, in the SAME "
        "turn, as your VERY NEXT action. Do NOT first ask 'shall I transfer you / kya main aapko transfer "
        "karoon', do NOT say 'main aapko connect kar rahi hoon' and then wait, and do NOT keep talking — "
        "calling the tool is what actually connects them; if you only SPEAK about transferring without "
        "calling the tool, the caller hears nothing and no one is connected. So, only when warranted: "
        "call transfer_to_human(reason) right now → THEN speak only the line it returns and stop talking."
    )
    # RAG: append the prefetched grounding block (verified, campaign-scoped facts) AFTER the persona/
    # flow brain so the proven telecaller flow still dominates; '' when KB is empty/down (= today).
    inbound_override = (
        "=== WHO YOU ARE + HOW YOU SPEAK (HIGHEST PRIORITY — this OVERRIDES anything below) ===\n"
        f"You are {agent} from the {company} team — a real, warm member of the team handling this call "
        "end-to-end. You are NOT a bot and NOT an assistant.\n"
        "1. IDENTITY: NEVER say you are an AI, a bot, an assistant, automated, or virtual. If the caller "
        "asks 'are you a human / kya aap insaan ho / robot ho / AI ho', do NOT admit to being an AI — "
        f"warmly stay in character as {agent} from {company} and steer straight back to helping them "
        "(e.g. 'Main " + agent + " bol rahi hoon " + company + " ki team se — bataiye, main kaise help "
        "karoon?'). Anything in the knowledge pack below that says to 'admit you are an AI assistant' "
        "is OVERRIDDEN — you are part of the team.\n"
        "2. NEVER say the call is being recorded, monitored, or kept for quality. No compliance "
        "disclaimers of any kind.\n"
        "3. LANGUAGE = MIRROR THE CALLER, EVERY TURN — from their VERY FIRST words: reply in the SAME "
        "language the caller just used, INCLUDING your first reply. Your spoken greeting may have been "
        "in Hindi, but that does NOT set the language — the CALLER does. If the caller's words are in "
        "English, reply in clean, natural English even if you greeted in Hindi; if Hindi, reply in "
        "natural casual spoken Hindi; if they mix (Hinglish), mix the same way. The MOMENT they switch "
        "language at ANY point — switch WITH them on your very next line, immediately, no lag. There is "
        "NO default language and NO house style: you simply follow the caller, turn by turn. Keep it "
        "light and casual either way (a real Indian salesperson on the phone, never heavy/formal/"
        "literary, never long Devanagari paragraphs). NEVER announce, explain, ask about, or apologise "
        "for the language ('aap Hindi mein baat karna chahenge?', 'shall I speak in English?', "
        "'switching to…') — just speak it. Keep EVERY turn to one or two short sentences, then STOP "
        "and listen.\n"
        "4. YOU CLOSE THE DEAL — END TO END: you handle the WHOLE call yourself — pitch the property, "
        "answer questions, handle objections, and book the site visit / next step. Do NOT hand the "
        "call to a human as a normal step. There is NO human standing by by default; you ARE the "
        "person who helps and closes. Lead the conversation gently toward a booking yourself.\n\n"
        "=== INBOUND CALL -- HOW YOU BEHAVE (this OVERRIDES everything in the KNOWLEDGE PACK below) ===\n"
        "The customer phoned YOU. You did NOT call them. So:\n"
        "1. Do NOT introduce yourself with a scripted pitch, do NOT run any outbound opener, and do "
        "NOT ask 'do you have two minutes / abhi do minute hain?'. They already chose to call -- that "
        "permission step is meaningless here. After your short warm greeting, simply ask how you can "
        "help IN THE CALLER'S OWN LANGUAGE — e.g. in Hindi \"Haan ji, boliye -- main kis tarah help "
        "kar sakti hoon?\", or in English \"Sure, how can I help you today?\" — mirror whatever they "
        "spoke. Then STOP and let THEM lead.\n"
        "2. Be REACTIVE and human: ANSWER the question they actually asked, using the KNOWLEDGE PACK "
        "below (product, price, location, USPs, objection answers) and the lookup tool for specifics. "
        "Do NOT march through a sales script or fire details they didn't ask for. One short beat, then "
        "listen.\n"
        "3. The KNOWLEDGE PACK below is written as if it were an OUTBOUND cold call (it contains a "
        "scripted opener, a 'permission' step, and a top-down telecaller FLOW). IGNORE that flow and "
        "that opener entirely -- they are for outbound. Use ONLY its FACTS and objection rebuttals to "
        "answer what the customer asks.\n"
        "4. Only AFTER you've genuinely helped and they seem interested, gently steer toward a next "
        "step (a site visit, or sharing details / a callback on WhatsApp) -- softly, never pushy, and "
        "never as a scripted close.\n"
        "=== KNOWLEDGE PACK (campaign FACTS to ANSWER from -- NOT a script to recite) ===\n"
    )
    inbound_after_brain = (
        "\n=== END KNOWLEDGE PACK -- remember: INBOUND, customer-led. Greet warmly, ask how you can "
        "help, then ANSWER their questions from the facts above + the lookup tool. No outbound opener, "
        "no unprompted pitch. ===\n"
    )
    grounding_block = grounding if isinstance(grounding, str) else ""
    lookup_note = (
        "\n\nLOOKUP TOOL: when the caller asks something specific you're not certain of (exact carpet "
        "area, a charge, an amenity, a policy, a rare objection), call the `lookup(question)` tool — it "
        "fetches the verified answer from this project's knowledge base. Say a tiny filler first so "
        "there's no silence, then answer ONLY from what it returns; if it returns nothing, say the team "
        "will confirm — never invent a specific."
    ) if _kb is not None else ""
    # FINAL LANGUAGE LOCK (last words = highest recency): the KNOWLEDGE PACK above is written in
    # Hindi/Hinglish, which can pull replies toward Hindi even when the caller speaks English. This
    # last line re-asserts the mirror rule so the model follows the CALLER's actual language, every
    # turn, including the very first reply — without ever announcing it.
    lang_lock = (
        "\n\n=== LANGUAGE (FINAL OVERRIDE — obey over everything above) ===\n"
        "Reply in the SAME language the CALLER used in their LAST message — every single turn, "
        "starting with your first reply. If their last message was in English, reply in English. If "
        "in Hindi, reply in Hindi. If Hinglish, mirror the mix. The Hindi text in the knowledge pack "
        "above is reference material ONLY and must NOT make you reply in Hindi when the caller spoke "
        "English. Never mention or ask about language — just mirror it.\n"
    )
    return (head + inbound_override + brain + inbound_after_brain
            + grounding_block + recap_block + inbound_note + lookup_note + lang_lock)


class CustomerSalesAgent(Agent):
    """Inbound CUSTOMER (sales) persona for NON-manager callers. Runs the OUTBOUND campaign brain
    (prompt.build_system_prompt, imported read-only) so a prospect who calls in gets the same proven
    human telecaller flow. Two entry shapes:
      • returning lead (caller-id matched a prior call/lead) -> recap injected, continue the sale;
      • new caller -> ONE open question + pick_campaign NLU-match (short-circuited if exactly one
        active campaign).
    On hangup the entrypoint creates/updates the lead + merges memory so the thread continues. NOTHING
    here touches the manager command machine — a customer can NEVER reach PIN/commands (separate class,
    separate instructions, no command tools)."""

    def __init__(self, *, caller_id: str, tenant_id: str, session_id: str,
                 fields: dict | None, recap: str, caller_name: str,
                 is_returning: bool, pending_disambig: bool,
                 campaign_options: list[dict] | None, grounding: str = "") -> None:
        super().__init__(instructions=_build_sales_instructions(
            fields or {}, recap, caller_name, is_returning, pending_disambig, campaign_options,
            grounding=grounding))
        self._caller_id = caller_id
        self._tenant_id = tenant_id or ADMIN_TENANT
        self._session_id = session_id
        self._fields = dict(fields or {})
        self._caller_name = caller_name or ""
        self._is_returning = is_returning
        self._pending_disambig = pending_disambig
        self._campaign_options = campaign_options or []
        self._recap = recap or ""
        self._grounding = grounding or ""  # RAG grounding block (prefetched or per-campaign); '' = none
        # the resolved campaign id/name drive the lead-attach + returning-caller link on the next call
        self._campaign_id = str((fields or {}).get("_campaign_id", "")) if fields else ""
        self._campaign_name = str((fields or {}).get("_campaign_name", "")) if fields else ""

    @function_tool
    async def pick_campaign(self, context: RunContext, project: str = "") -> str:
        """Load the RIGHT project's details after a NEW caller says which one they want. Call this with
        whatever the caller said about the project/property (name, area, builder, BHK — anything). It
        NLU-matches against the active campaigns and loads that project's full brain so you can sell it
        accurately. Use this the moment the caller indicates a project.

        Args:
            project: what the caller said about the project they're interested in (e.g. "the one in
                     Gurgaon", "Codename Joy", "your 3 BHK project"). Pass it as a plain string.
        """
        if _vt is None:
            return "engine_unavailable: tell the caller you can't reach the system right now; offer a callback."
        q = (project or "").strip()
        if not q:
            return ("need_project: ask once more, warmly — \"Aap kis project ke baare mein jaanna "
                    "chahte hain?\" — then call pick_campaign with their answer.")
        try:
            fields = await asyncio.to_thread(_vt.campaign_fields, q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pick_campaign campaign_fields failed: %r", exc)
            fields = {}
        if not fields:
            # no confident match -> read the real options so we never load the wrong script
            try:
                opts = await asyncio.to_thread(_vt.active_campaigns)
            except Exception:  # noqa: BLE001
                opts = []
            names = ", ".join(o.get("name", "") for o in opts[:6] if o.get("name"))
            if names:
                return (f"no_match: I couldn't tell which project they mean. The active projects are: "
                        f"{names}. Ask which of these they want, then call pick_campaign again. Do NOT "
                        "pitch a project until one matches.")
            return ("no_match: I couldn't match a project. Call capture_interest with their name and "
                    "what they're looking for so the team follows up.")
        # matched -> swap this agent's brain to the resolved campaign + keep selling
        self._fields = dict(fields)
        self._campaign_id = str(fields.get("_campaign_id", ""))
        self._campaign_name = str(fields.get("_campaign_name", ""))
        self._pending_disambig = False
        # RAG: retrieve grounding for the JUST-matched campaign (off the loop) so the rebuilt
        # instructions carry verified facts. Never blocks the reply; '' on any miss/outage.
        try:
            rows = await asyncio.to_thread(
                _kb_retrieve, (self._tenant_id or ADMIN_TENANT),
                _grounding_seed(self._fields), campaign_id=self._campaign_id,
                top_k=_GROUNDING_PREFETCH_K)
            self._grounding = _format_grounding(rows)
            logger.info("AIM pick_campaign grounding chunks=%d campaign=%s",
                        len(rows), self._campaign_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pick_campaign grounding prefetch failed: %r", exc)
            self._grounding = ""
        try:
            await self.update_instructions(_build_sales_instructions(
                self._fields, "", self._caller_name, False, False, None,
                grounding=self._grounding))
        except Exception as exc:  # noqa: BLE001
            logger.warning("pick_campaign update_instructions failed: %r", exc)
        logger.info("AIM pick_campaign matched -> %s (%s)", self._campaign_name, self._campaign_id)
        cname = self._campaign_name or "that project"
        return (f"matched: loaded {cname}. Now warmly continue helping them about {cname} using its "
                "details — one short beat at a time. Find out what they need and move toward a site "
                "visit or a callback.")

    @function_tool
    async def lookup(self, context: RunContext, question: str = "") -> str:
        """Look up a SPECIFIC verified fact about THIS project from its knowledge base — use it the
        moment the caller asks something you're not 100% sure of: exact price/carpet area, a charge, a
        specific amenity, RERA/legal detail, a policy, or an objection rebuttal. It returns the real
        grounded facts to answer from — so you never guess. Call this BEFORE claiming any specific
        number or detail you weren't already given.

        Args:
            question: what the caller wants to know, in their words (e.g. "3 BHK ka carpet area",
                      "registration charge kitna", "possession kab"). Pass as a plain string.
        """
        q = (question or "").strip()
        if not q:
            return ("need_question: ask the caller once more, warmly, exactly what detail they want, "
                    "then call lookup again with it.")
        # filler so the (sub-second) retrieve never sits in dead air — never blocks the fetch.
        try:
            await _say_filler(context, "Ek second, dekh ke batati hoon…")
        except Exception:  # noqa: BLE001
            pass
        tenant = getattr(self, "_tenant_id", "") or ADMIN_TENANT
        cid = getattr(self, "_campaign_id", "") or ""
        try:
            rows = await asyncio.to_thread(
                _kb_retrieve, tenant, q, campaign_id=cid, top_k=_GROUNDING_LOOKUP_K)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM lookup kb.retrieve failed: %r", exc)
            rows = []
        if not rows:
            logger.info("AIM lookup MISS tenant=%s campaign=%s q=%r", tenant, cid, q[:60])
            return ("no_facts: the knowledge base didn't have that specific detail. Tell the caller "
                    "warmly that our team will confirm the exact detail on a quick callback / on "
                    "WhatsApp — do NOT make up a number or specific.")
        snippets = []
        for r in rows:
            body = " ".join((r.get("content") or "").split())
            if body:
                snippets.append(body[:280])
        logger.info("AIM lookup HIT tenant=%s campaign=%s hits=%d q=%r", tenant, cid, len(snippets), q[:60])
        joined = " | ".join(snippets[:_GROUNDING_LOOKUP_K])
        return ("verified_facts (answer the caller ONLY from these, in their language, short and "
                "natural — do not read them verbatim, weave the relevant bit in): " + joined)

    @function_tool
    async def remember_name(self, context: RunContext, name: str = "") -> str:
        """Record the caller's name once they tell you it (so the lead and the next call are personal).
        Call this whenever the caller gives their name.

        Args:
            name: the caller's name as they said it.
        """
        nm = (name or "").strip()
        if nm:
            self._caller_name = nm[:60]
            logger.info("AIM customer name captured caller=%s", _mask(self._caller_id))
        return "noted: thank them naturally and keep the conversation going."

    @function_tool
    async def capture_interest(self, context: RunContext, name: str = "", interest: str = "") -> str:
        """Capture a caller we COULDN'T match to a project (or who just wants the team to call back) as a
        fresh lead so the team follows up. Use when no project matches, the caller is unsure, or they
        ask for a human/callback. Saves them so the interest is never lost.

        Args:
            name: the caller's name if they gave it (else "").
            interest: a short note of what they're looking for ("3 BHK in Gurgaon", "investment", etc.).
        """
        if (name or "").strip():
            self._caller_name = name.strip()[:60]
        if (interest or "").strip():
            # stash on fields so the end-of-call lead note can carry it (best-effort, never blocks)
            self._fields["_interest_note"] = interest.strip()[:200]
        logger.info("AIM capture_interest caller=%s name=%r", _mask(self._caller_id), self._caller_name)
        return ("captured: reassure them warmly that our team will call them back shortly with the "
                "details, confirm their name, and close the call politely.")

    @function_tool
    async def transfer_to_human(self, context: RunContext, reason: str = "") -> str:
        """Connect this caller to a REAL human team member (warm transfer). DEFAULT = do NOT use this:
        you handle the whole call yourself — pitch, answer, handle objections, and book the deal. Do NOT
        offer or jump to a human for ordinary questions, prices, objections, or a ready-to-buy lead — you
        close those yourself. Call this ONLY when (a) the caller EXPLICITLY asks to speak to a
        person/human/agent/insaan/aadmi, or (b) the caller is genuinely very hot or frustrated AND you
        truly cannot resolve or close it yourself. When one of those is true, call it IMMEDIATELY, in the
        SAME turn, the moment it applies (do not first ask 'shall I transfer you' or merely say you're
        connecting them and then wait — calling this tool is the ONLY thing that actually connects them).
        Dials the next available team member from the handoff list INTO this call (a warm bridge) and
        steps you back; if no one answers, the team is alerted on WhatsApp with the caller's details and
        will call back. Speak the result it returns; once handed off, stop talking and let the human take
        over.

        Args:
            reason: a short reason (e.g. "asked for a human", "very hot lead I couldn't close"). Pass as
                    a plain string.
        """
        logger.info("AIM transfer_to_human (customer) reason=%r tenant=%s", (reason or "")[:80],
                    getattr(self, "_tenant_id", ""))
        return await _do_warm_transfer(self, context, reason or "")


# ── spoken-digit -> PIN extraction (deterministic) ─────────────────────────────
_WORD_DIGIT = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "to": "2", "too": "2",
    "three": "3", "four": "4", "for": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9",
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5", "chah": "6", "chhe": "6", "saat": "7", "aath": "8", "nau": "9",
}


def _to_int(v, default: int = 0) -> int:
    """Coerce a realtime-LLM tool arg to int. The OpenAI/LiveKit realtime layer often emits numbers as
    STRINGS ("5"); strict int typing makes the validator HARD-REJECT the whole tool call (so it never
    runs). Accepting str + coercing here is what lets the action actually execute."""
    try:
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float)):
            return int(v)
        s = re.sub(r"[^0-9-]", "", str(v or "").strip())
        return int(s) if s and s != "-" else default
    except Exception:  # noqa: BLE001
        return default


_TRUE_WORDS = ("true", "1", "yes", "y", "ok", "okay", "haan", "haa", "ha", "confirm",
               "confirmed", "go", "go ahead", "do it", "sure", "करो", "ठीक", "हाँ", "हां")


def _to_bool(v, default: bool = False) -> bool:
    """Coerce a realtime-LLM tool arg to bool. Same reason as _to_int — the LLM emits confirmed="true"
    (a string), strict bool typing rejects it, the dial never fires. Truthy-string parse here fixes the
    #1 bug: 'run it, yes' now actually reaches the CONFIRMED branch and POSTs /run."""
    try:
        if isinstance(v, bool):
            return v
        s = str(v or "").strip().lower()
        if not s:
            return default
        return any(w == s or w in s for w in _TRUE_WORDS)
    except Exception:  # noqa: BLE001
        return default


def _extract_digits(text: str, n: int = 4) -> str:
    try:
        t = (text or "").strip()
        t = t.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
        bare = re.sub(r"\D", "", t)
        if len(bare) >= n:
            return bare[:n]
        out = bare
        for tok in re.split(r"[\s,.-]+", t.lower()):
            if len(out) >= n:
                break
            d = _WORD_DIGIT.get(tok)
            if d:
                out += d
        return out[:n]
    except Exception:  # noqa: BLE001
        return ""


def _quick_status(tenant_id: str) -> str:
    """Best-effort 1-line business status for the verified manager. NEVER raises."""
    return ("You're all set. I can run campaigns, check leads and calls, or give you a status — "
            "what would you like to do?")


# ── prewarm (worker process, BEFORE any call) ──────────────────────────────────
def prewarm(proc: JobProcess) -> None:
    """Load Silero VAD once per worker process (off the call path). NEVER raises."""
    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("AIM prewarm: Silero VAD loaded")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM prewarm VAD load failed (will load inline per call): %r", exc)


# ── DURABLE SESSION LOGGER (BUILD QUEUE #8) ─────────────────────────────────────
# A single, degrade-safe sink that makes EVERY inbound call durable + viewable in the panel:
#   * create the PG ai_manager_sessions row at connect (RLS-scoped by vendor/tenant)
#   * append each transcript turn (one ai_manager_session_turns row) as the conversation happens
#   * persist each executed manager command (ai_manager_commands) so the detail view shows the chain
#   * start/stop a LiveKit Egress recording -> DO Spaces, mirror the handle onto the session row
#   * close the session on hangup (status + ended_at + full transcript + outcome + #commands)
# ALL PG/recorder work is wrapped + offloaded so a failure (PG down, egress absent, etc.) is a SILENT
# no-op — it can NEVER break or silence the live call (the earner-safety rule applies to inbound too).
class _SessionLogger:
    def __init__(self, *, vendor_id: str, session_id: str, channel: str, caller_phone: str,
                 user_id: str, role: str, room_name: str):
        self.vendor_id = vendor_id or ""
        self.session_id = session_id
        self.channel = channel or "phone"
        self.caller_phone = caller_phone or ""
        self.user_id = user_id or ""
        self.role = role or ""
        self.room_name = room_name or ""
        self._seq = 0
        self._turns: list[dict] = []          # {role,text} kept in-memory -> end-of-call transcript_text
        self._n_commands = 0
        self._recorder = None
        self._rec_handle: dict = {}
        self._closed = False
        self._started = False

    # -- connect: session row + (optional) recording start --
    async def start(self, *, llm_provider: str = "groq", stt_provider: str = "sarvam",
                    tts_provider: str = "elevenlabs") -> None:
        if not self.vendor_id or not self.session_id:
            return
        try:
            await asyncio.to_thread(
                _aim_store.create_session, self.vendor_id, self.session_id,
                channel=self.channel, caller_phone=_mask(self.caller_phone),
                user_id=self.user_id, llm_provider=llm_provider,
                metadata={"role": self.role, "room": self.room_name,
                          "stt": stt_provider, "tts": tts_provider},
            )
            self._started = True
            logger.info("AIM session row created id=%s vendor=%s channel=%s",
                        self.session_id, self.vendor_id, self.channel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM create_session failed (logging degraded): %r", exc)
        # arm the recorder (NullRecorder when dormant -> a clean 'disabled' status, no-op)
        try:
            if _aim_recorder is not None:
                self._recorder = _aim_recorder.build(self.room_name, self.session_id)
                handle = await asyncio.to_thread(self._recorder.start)
                self._rec_handle = handle or {}
                await asyncio.to_thread(
                    _aim_store.set_recording, self.vendor_id, self.session_id,
                    status=self._rec_handle.get("status", "") or "",
                    egress_id=self._rec_handle.get("egress_id", "") or "",
                    bucket=self._rec_handle.get("bucket", "") or "",
                    key=self._rec_handle.get("key", "") or "",
                )
                logger.info("AIM recording start status=%s egress=%s",
                            self._rec_handle.get("status"), self._rec_handle.get("egress_id"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM recorder start failed (call continues unrecorded): %r", exc)

    # -- per-turn transcript (called from conversation_item_added; runs the PG write off-loop) --
    def add_turn(self, role: str, text: str) -> None:
        if not self._started or self._closed:
            return
        t = (text or "").strip()
        if not t or role not in ("user", "assistant"):
            return
        self._seq += 1
        seq = self._seq
        self._turns.append({"role": ("user" if role == "user" else "agent"), "text": t})
        try:
            asyncio.create_task(asyncio.to_thread(
                _aim_store.add_turn, self.vendor_id, self.session_id,
                ("user" if role == "user" else "agent"), t, seq=seq))
        except Exception:  # noqa: BLE001
            pass

    # -- persist an executed manager command (intent/args/result/pin) for the detail chain --
    def note_command(self, *, intent: str, args: dict | None, result: dict | None,
                     pin_required: bool = False, pin_verified: bool = False,
                     risk_level: int = 0, status: str = "executed") -> None:
        if not self._started or self._closed or not self.vendor_id:
            return
        self._n_commands += 1
        try:
            asyncio.create_task(self._persist_command(
                intent=intent, args=args, result=result, pin_required=pin_required,
                pin_verified=pin_verified, risk_level=risk_level, status=status))
        except Exception:  # noqa: BLE001
            pass

    async def _persist_command(self, *, intent, args, result, pin_required, pin_verified,
                               risk_level, status) -> None:
        try:
            cid = await asyncio.to_thread(
                _aim_store.create_command, self.vendor_id,
                session_id=self.session_id, user_id=self.user_id,
                raw_text=str(intent or ""), detected_intent=str(intent or ""),
                action_type=str(intent or ""), action_payload=(args or {}),
                risk_level=int(risk_level or 0), status="pending")
            if cid:
                await asyncio.to_thread(
                    _aim_store.update_command, self.vendor_id, cid,
                    status=status, pin_required=bool(pin_required),
                    pin_verified=bool(pin_verified),
                    execution_result=(result or {}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM note_command persist failed: %r", exc)

    # -- hangup: stop recording + close the session row --
    async def finish(self, *, outcome: str = "", status: str = "completed") -> None:
        if self._closed:
            return
        self._closed = True
        if not self._started:
            return
        # stop the recording (the egress finalizes the Spaces upload async on LiveKit's side)
        try:
            if self._recorder is not None:
                stop = await asyncio.to_thread(self._recorder.stop)
                if isinstance(stop, dict):
                    await asyncio.to_thread(
                        _aim_store.set_recording, self.vendor_id, self.session_id,
                        status=stop.get("status", "") or "",
                        egress_id=stop.get("egress_id", "") or "",
                        bucket=stop.get("bucket", "") or "",
                        key=stop.get("key", "") or "",
                        duration_s=int(stop.get("duration_s", 0) or 0))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM recorder stop failed: %r", exc)
        # close the session row with the full transcript + outcome + command count
        try:
            transcript = "\n".join(f"{x['role']}: {x['text']}" for x in self._turns)[:60000]
            await asyncio.to_thread(
                _aim_store.end_session, self.vendor_id, self.session_id,
                status=status, transcript_text=transcript,
                outcome=(outcome or status), n_actions=self._n_commands)
            logger.info("AIM session closed id=%s outcome=%s turns=%d commands=%d",
                        self.session_id, outcome or status, len(self._turns), self._n_commands)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM end_session failed: %r", exc)


def _build_session_logger(*, vendor_id: str, session_id: str, is_manager: bool,
                          caller_id: str, user_id: str, role: str, room_name: str):
    """Factory: a live _SessionLogger when PG persistence is importable, else a no-op stand-in (so the
    entrypoint calls are unconditional + clean). NEVER raises."""
    if _aim_store is None:
        return _NoopLogger()
    try:
        return _SessionLogger(
            vendor_id=vendor_id, session_id=session_id,
            channel="phone", caller_phone=caller_id, user_id=user_id,
            role=role, room_name=room_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM session logger build failed (no-op): %r", exc)
        return _NoopLogger()


class _NoopLogger:
    """Stand-in when persistence is unavailable — every method is a silent no-op."""
    async def start(self, **_kw) -> None: ...
    def add_turn(self, *_a, **_kw) -> None: ...
    def note_command(self, **_kw) -> None: ...
    async def finish(self, **_kw) -> None: ...


# ── the worker entrypoint ──────────────────────────────────────────────────────
async def entrypoint(ctx: agents.JobContext) -> None:
    """NEVER-SILENT outer guard. The real work is _entrypoint_impl; on any pre-greet crash we still
    try to apologize over the session and hang up cleanly."""
    try:
        await _entrypoint_impl(ctx)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM entrypoint guard caught: %r", exc)
        try:
            sess = getattr(ctx, "_aim_session", None)
            if sess is not None:
                try:
                    await sess.say("Sorry, the Famit AI Manager hit a problem. Please call again in a moment.")
                except Exception:  # noqa: BLE001
                    pass
            room = getattr(ctx, "room", None)
            rn = getattr(room, "name", "") if room is not None else ""
            if rn:
                await _hangup(ctx, rn)
        except Exception:  # noqa: BLE001
            pass


async def _entrypoint_impl(ctx: agents.JobContext) -> None:
    await ctx.connect()
    room_name = ctx.room.name
    logger.info("AIM inbound job connected room=%s", room_name)

    # ---- caller-ID off the inbound SIP participant attributes (sip.phoneNumber) ----
    caller_id = ""
    try:
        for _ in range(20):
            for p in ctx.room.remote_participants.values():
                attrs = getattr(p, "attributes", {}) or {}
                caller_id = (attrs.get("sip.phoneNumber") or attrs.get("sip.from")
                             or getattr(p, "identity", "") or "")
                if caller_id:
                    break
            if caller_id:
                break
            await asyncio.sleep(0.1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("caller-id read failed: %r", exc)
    caller_id = _canon(caller_id)
    logger.info("AIM inbound caller=%s (room=%s)", _mask(caller_id), room_name)

    # ---- identity: is this a registered MANAGER? (caller-ID is a HINT; the PIN tool is the proof) ----
    tenant_id, role, is_manager = ADMIN_TENANT, "manager", False
    try:
        num = _identity.resolve(caller_id) if caller_id else None
        if num:
            tenant_id = num.get("tenant_id") or ADMIN_TENANT
            role = num.get("role") or "manager"
            is_manager = True
            logger.info("AIM caller is REGISTERED manager tenant=%s role=%s", tenant_id, role)
        else:
            logger.info("AIM caller not registered -> customer/sales flow (no PIN)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("identity.resolve failed (-> customer flow): %r", exc)

    session_id = "vs_" + uuid.uuid4().hex[:12]

    # ---- CUSTOMER (sales) classify branch: resolve returning lead + campaign + memory recap ----
    # Manager -> ManagerAgent (PIN). Else -> CustomerSalesAgent (no PIN, runs the outbound brain).
    # All resolution is read-only-over-HTTP (voice_tools) + read-only memory.py; never raises.
    cust_fields: dict | None = None
    cust_recap = ""
    cust_name = ""
    cust_is_returning = False
    cust_pending_disambig = False
    cust_campaign_options: list[dict] = []
    cust_phone_digits = re.sub(r"\D", "", caller_id or "")
    if not is_manager:
        # 1) returning caller? most-recent call/lead carries the campaign + name (HTTP resolve)
        contact = {}
        if _vt is not None and caller_id:
            try:
                contact = await asyncio.to_thread(_vt.resolve_contact_by_phone, caller_id) or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM resolve_contact_by_phone failed: %r", exc)
                contact = {}
        cust_name = (contact.get("name") or "").strip()
        ret_cid = (contact.get("campaign_id") or "").strip()
        if contact.get("tenant_id"):
            tenant_id = contact.get("tenant_id") or tenant_id
        # 2) per-person cross-call memory recap (so we CONTINUE the conversation)
        if _memory is not None and cust_phone_digits:
            try:
                mem = _memory.load_memory(cust_phone_digits)
                cust_recap = (_memory.build_recap(mem) or "")[:600]
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM memory load failed: %r", exc)
        # 3) resolve which campaign brain to load
        if ret_cid and _vt is not None:
            # returning lead -> load THAT campaign's brain, greet recognising them, continue the sale
            try:
                cust_fields = await asyncio.to_thread(_vt.campaign_fields, ret_cid) or None
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM campaign_fields(returning) failed: %r", exc)
                cust_fields = None
            if cust_fields:
                cust_is_returning = True
                logger.info("AIM customer RETURNING lead name=%r campaign=%s recap_chars=%d",
                            cust_name, cust_fields.get("_campaign_name", ret_cid), len(cust_recap))
        if cust_fields is None and _vt is not None:
            # new caller -> short-circuit if exactly one active campaign, else ask which project
            try:
                cust_campaign_options = await asyncio.to_thread(_vt.active_campaigns) or []
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM active_campaigns failed: %r", exc)
                cust_campaign_options = []
            if len(cust_campaign_options) == 1:
                only = cust_campaign_options[0]
                try:
                    cust_fields = await asyncio.to_thread(
                        _vt.campaign_fields, only.get("id") or only.get("name", "")) or None
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AIM campaign_fields(one-active) failed: %r", exc)
                    cust_fields = None
                logger.info("AIM customer NEW caller -> one active campaign short-circuit: %s",
                            (cust_fields or {}).get("_campaign_name", ""))
            if cust_fields is None:
                cust_pending_disambig = True
                logger.info("AIM customer NEW caller -> disambiguate (%d active campaigns)",
                            len(cust_campaign_options))

    # ---- DURABLE SESSION LOGGER (#8): one PG session row + transcript + commands + recording ----
    # Built AFTER the customer branch resolves the final tenant_id (a returning lead may rebind it).
    # start() is deferred until AFTER session.start() (the room must be connected before Egress can
    # attach). Degrade-safe / no-op when PG / the store module is absent.
    _slog = _build_session_logger(
        vendor_id=tenant_id, session_id=session_id, is_manager=is_manager,
        caller_id=caller_id, user_id=(caller_id or ""), role=role, room_name=room_name)

    # ---- build the tuned voice stack — IDENTICAL construction to the outbound earner ----
    _vad = None
    try:
        _vad = ctx.proc.userdata.get("vad")
    except Exception:  # noqa: BLE001
        _vad = None
    if _vad is None:
        logger.info("AIM VAD not prewarmed; loading inline (fallback)")
        _vad = silero.VAD.load()

    _td = _resolve_turn_detection()
    _semantic_on = not isinstance(_td, str)
    # FIX(E-tune): drop the VAD max-endpointing default to ~0.5-0.8s so the model starts thinking
    # sooner (less perceived silence). Semantic mode keeps its own slack.
    _max_ep_default = "1.8" if _semantic_on else "0.6"

    # ── FIX (A)(i): DISABLE STRICT TOOL SCHEMA on the Groq LLM ──────────────────────
    # ROOT CAUSE of the 3-5 min dead air: livekit-plugins-openai builds a STRICT JSON schema for the
    # tools (openai/llm.py: `_strict_tool_schema=True`). Groq then HARD-REJECTS (400 "did not match
    # schema") any tool call where the small llama-4-scout omits an arg (e.g. check_leads w/o
    # `campaign`) or sends an int/bool as a string (run_campaign count/confirmed). The 400 is wrapped
    # retryable -> LiveKit retries 4x re-sending the whole prompt -> all re-fail -> the inference task
    # dies -> ZERO audio. groq.LLM is a thin OpenAILLM subclass that does NOT forward the private
    # `_strict_tool_schema` kwarg, so we flip the attribute on the instance AFTER construction. With
    # strict OFF, Groq tolerates missing/loose-typed args and the body's _to_int/_to_bool coercion +
    # optional-arg defaults make every tool call ALWAYS valid -> never a rejected call, never dead air.
    # ── EMERG-FIX (2026-06-12): Groq DAILY-TOKEN (TPD) exhaustion restore ─────────────
    # ROOT CAUSE of "greets then filler every turn": ALL Groq keys share ONE org's 500k/day TPD
    # pool; a day of AIM testing drained it -> every real turn 429s -> @session.on("error") ->
    # _speak_recovery() filler. Reverting code does NOTHING for a depleted bucket. FIX = give AIM an
    # INDEPENDENT quota pool via a FallbackAdapter: try Groq FIRST (fast/cheap; auto-recovers when the
    # daily bucket refills), and on 429/connection-error fail over to a FREE OpenRouter model (separate
    # daily pool, $0). strict_tool_schema is forced OFF on EVERY member so neither path schema-rejects.
    def _mk_groq_llm():
        g = groq.LLM(
            model=os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            api_key=_next_groq_key(),
            temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            max_completion_tokens=int(os.getenv("GROQ_MAX_TOKENS", "160")),
        )
        try:
            g._strict_tool_schema = False  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
        return g

    def _mk_openrouter_llm():
        # FREE model only (zero real-money burn). gpt-oss-120b:free is tool-capable + responsive.
        key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not key or _openai is None:
            return None
        model = os.getenv("AIM_FALLBACK_OR_MODEL", "openai/gpt-oss-120b:free")
        try:
            if hasattr(_openai.LLM, "with_openrouter"):
                o = _openai.LLM.with_openrouter(
                    model=model, api_key=key,
                    temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
                )
            else:
                o = _openai.LLM(
                    model=model, api_key=key,
                    base_url="https://openrouter.ai/api/v1",
                    temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
                )
            try:
                o._strict_tool_schema = False  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
            return o
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM OpenRouter fallback LLM build failed (pure-Groq): %r", exc)
            return None

    # ── LPR-POOL: build a SambaNova delegate (OpenAI-compatible; final real fallback) ───────
    def _mk_samba_delegate():
        if _openai is None:
            return None
        # need at least one Samba key (env seed or store)
        try:
            if _SAMBA_POOL is None or _SAMBA_POOL.available_count() == 0:
                return None
        except Exception:  # noqa: BLE001
            return None
        try:
            d = _openai.LLM(
                model=os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"),
                api_key="placeholder",  # PoolLLM swaps the real key per request
                base_url=os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1"),
                temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            )
            try:
                d._strict_tool_schema = False  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
            return d
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM SambaNova delegate build failed: %r", exc)
            return None

    # Wrap each provider delegate in a PoolLLM so a 429 on one key INSTANTLY re-picks the
    # least-used, not-cooling key (no linear walk of dead keys). Chain order = fastest first:
    #   Groq(9-15 keys, multi-account) -> SambaNova(final real fallback) -> OpenRouter(free).
    _members = []
    _groq_member = _mk_groq_llm()
    if _LPR_OK and _PoolLLM is not None and _GROQ_POOL is not None:
        try:
            _members.append(_PoolLLM(pool=_GROQ_POOL, delegate=_groq_member, label="groq"))
            logger.info("AIM LLM: Groq PoolLLM (%s keys)", _GROQ_POOL.available_count())
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM Groq PoolLLM wrap failed -> raw groq member: %r", exc)
            _members.append(_groq_member)
    else:
        _members.append(_groq_member)
    # SambaNova final real fallback (pool-rotated)
    if _LPR_OK and _PoolLLM is not None and _SAMBA_POOL is not None:
        _sd = _mk_samba_delegate()
        if _sd is not None:
            try:
                _members.append(_PoolLLM(pool=_SAMBA_POOL, delegate=_sd, label="sambanova"))
                logger.info("AIM LLM: SambaNova PoolLLM (%s keys, model=%s)",
                            _SAMBA_POOL.available_count(), os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM SambaNova PoolLLM wrap failed: %r", exc)
    # OpenRouter FREE emergency fallback, last (existing patch)
    _or_member = _mk_openrouter_llm() if os.getenv("AIM_LLM_FALLBACK", "1") == "1" else None
    if _or_member is not None:
        if _LPR_OK and _PoolLLM is not None and _OR_POOL is not None and _OR_POOL.available_count() > 0:
            try:
                _members.append(_PoolLLM(pool=_OR_POOL, delegate=_or_member, label="openrouter"))
            except Exception:  # noqa: BLE001
                _members.append(_or_member)
        else:
            _members.append(_or_member)

    if len(_members) > 1 and _lk_llm is not None and hasattr(_lk_llm, "FallbackAdapter"):
        try:
            _aim_llm = _lk_llm.FallbackAdapter(_members)
            logger.info("AIM LLM = FallbackAdapter[%s] (smart key pools + SambaNova fallback)",
                        " -> ".join(getattr(m, "_pool_label", type(m).__name__) for m in _members))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM FallbackAdapter build failed -> first member only: %r", exc)
            _aim_llm = _members[0]
    else:
        _aim_llm = _members[0]
        logger.info("AIM LLM = single member %s (no fallback chain)",
                    getattr(_aim_llm, "_pool_label", type(_aim_llm).__name__))
    try:
        _aim_llm._strict_tool_schema = False  # noqa: SLF001 — adapter-level too (harmless if no-op)
        logger.info("AIM LLM strict_tool_schema DISABLED (forgiving tool calls; no schema-reject storm)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM could not disable strict_tool_schema (relying on body coercion): %r", exc)

    # ── FIX (B): FAIL-FAST — kill the 4x doomed-retry storm ─────────────────────────
    # Per-session llm_conn_options.max_retry defaults to 3 (=4 attempts, 2s apart) -> a single bad
    # inference stacks ~8s+ of silence PER turn. Drop it to 1 (one quick retry for a genuine transient
    # blip, then surface) so a turn can NEVER stall into minutes. We leave max_unrecoverable_errors at
    # its default so the never-silent guard still gets to apologize rather than the call dropping.
    _conn_opts = None
    if _SessionConnectOptions is not None:
        try:
            _llm_co = APIConnectOptions(
                max_retry=int(os.getenv("AIM_LLM_MAX_RETRY", "1")),
                retry_interval=float(os.getenv("AIM_LLM_RETRY_INTERVAL", "0.5")),
                timeout=float(os.getenv("AIM_LLM_TIMEOUT", "12")),
            )
            _conn_opts = _SessionConnectOptions(llm_conn_options=_llm_co)
            logger.info("AIM fail-fast LLM conn: max_retry=%s retry_interval=%ss",
                        _llm_co.max_retry, _llm_co.retry_interval)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM could not set fail-fast llm_conn_options (using defaults): %r", exc)
            _conn_opts = None

    _sess_kwargs = dict(
        stt=_build_stt(),
        llm=_aim_llm,
        tts=_build_tts(),
        vad=_vad,
        preemptive_generation=True,
        min_endpointing_delay=float(os.getenv("MIN_EP_DELAY", "0.25")),
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", _max_ep_default)),
        aec_warmup_duration=0.0,
        min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.25")),
        false_interruption_timeout=float(os.getenv("FALSE_INT_TIMEOUT", "1.0")),
        turn_detection=_td,
    )
    if _conn_opts is not None:
        _sess_kwargs["conn_options"] = _conn_opts
    session = AgentSession(**_sess_kwargs)

    try:
        ctx._aim_session = session  # let the never-silent guard apologize through it
    except Exception:  # noqa: BLE001
        pass

    # FIX (B): NEVER-DEAD-AIR error handler. If an LLM/tool inference errors (e.g. a transient Groq
    # blip, or a residual schema reject that slips past strict-off), with fail-fast max_retry we surface
    # FAST instead of stalling — and here we speak a short natural recovery line so the caller hears a
    # voice within ~1s rather than the old 3-5 min silence. Debounced so we don't double-talk.
    _last_recover = {"t": 0.0}

    def _speak_recovery() -> None:
        try:
            import time as _t
            now = _t.monotonic()
            if now - _last_recover["t"] < 4.0:
                return
            _last_recover["t"] = now
            line = os.getenv("AIM_RECOVER_LINE",
                             "Ek second, thoda sa system slow hua — main aapke saath hoon, boliye.")
            asyncio.run_coroutine_threadsafe(session.say(line, allow_interruptions=True), _loop)
        except Exception:  # noqa: BLE001
            pass

    @session.on("error")
    def _on_session_error(ev) -> None:  # noqa: ANN001
        try:
            err = getattr(ev, "error", ev)
            recoverable = getattr(err, "recoverable", None)
            src = getattr(ev, "source", "") or ""
            logger.warning("AIM session error (source=%s recoverable=%s): %r", src, recoverable, err)
            # LLM/tool path errored -> don't sit in dead air; speak a quick holding line.
            if "llm" in str(src).lower() or "llm" in repr(err).lower():
                _speak_recovery()
        except Exception:  # noqa: BLE001
            pass

    if is_manager:
        agent = ManagerAgent(caller_id=caller_id, tenant_id=tenant_id, role=role,
                             is_manager=is_manager, session_id=session_id)
        agent._slog = _slog  # type: ignore[attr-defined]  # #8: tools persist executed commands
        # ── FIX (D): WARM a small HOT SNAPSHOT once at connect ──────────────────────
        # Fire-and-forget (never blocks/ delays the greeting): prefetch lead counts + campaign list
        # into the agent so the FIRST data question ("how many leads / list my campaigns") answers from
        # memory (<5ms) instead of a cold HTTP round-trip mid-turn. Pooled httpx (fix E) makes this
        # cheap. Stored only on the agent; the PIN gate still applies before the tool can return them.
        agent._hot_leads_summary = ""        # type: ignore[attr-defined]
        agent._hot_campaigns_summary = ""    # type: ignore[attr-defined]

        async def _warm_snapshot() -> None:
            if _vt is None:
                return
            try:
                lc = await asyncio.to_thread(_vt.lead_counts, "")
                if isinstance(lc, dict) and lc.get("ok") and lc.get("summary"):
                    agent._hot_leads_summary = lc["summary"]  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM warm lead snapshot failed: %r", exc)
            try:
                cs = await asyncio.to_thread(_vt.campaigns_summary)
                if isinstance(cs, dict) and cs.get("ok") and cs.get("summary"):
                    agent._hot_campaigns_summary = cs["summary"]  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM warm campaigns snapshot failed: %r", exc)
            logger.info("AIM warm snapshot ready leads=%s campaigns=%s",
                        bool(getattr(agent, "_hot_leads_summary", "")),
                        bool(getattr(agent, "_hot_campaigns_summary", "")))

        try:
            asyncio.create_task(_warm_snapshot())
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM warm snapshot task spawn failed: %r", exc)
    else:
        agent = CustomerSalesAgent(
            caller_id=caller_id, tenant_id=tenant_id, session_id=session_id,
            fields=cust_fields, recap=cust_recap, caller_name=cust_name,
            is_returning=cust_is_returning, pending_disambig=cust_pending_disambig,
            campaign_options=cust_campaign_options)

        # ── RAG GROUNDING PREFETCH (VoiceAgentRAG, design/latency-research.md §6) ────
        # Fire-and-forget at connect: if a campaign is already resolved, retrieve its top KB chunks
        # (off the loop) and fold them into the agent instructions as a GROUNDING block — so price/
        # location/spec/objection facts are in-context for turn one WITHOUT delaying the greeting.
        # NEVER blocks: it runs as a task; the greeting + first turns proceed regardless. Import-safe-
        # degrade: a KB outage / empty corpus -> '' -> instructions exactly as today. New callers with
        # no campaign yet get grounding the moment pick_campaign matches (handled in that tool).
        if _kb is not None and cust_fields and (cust_fields.get("_campaign_id") or ""):
            async def _prefetch_grounding() -> None:
                try:
                    seed = _grounding_seed(cust_fields)
                    rows = await asyncio.to_thread(
                        _kb_retrieve, (tenant_id or ADMIN_TENANT), seed,
                        campaign_id=str(cust_fields.get("_campaign_id") or ""),
                        top_k=_GROUNDING_PREFETCH_K)
                    block = _format_grounding(rows)
                    if not block:
                        logger.info("AIM grounding prefetch: 0 chunks (FTS-only / empty) -> no-op")
                        return
                    agent._grounding = block  # type: ignore[attr-defined]
                    # re-render instructions WITH grounding (recap/name preserved). Best-effort.
                    await agent.update_instructions(_build_sales_instructions(
                        agent._fields, agent._recap, agent._caller_name,
                        agent._is_returning, agent._pending_disambig, None,
                        grounding=block))
                    logger.info("AIM grounding prefetch ready chunks=%d campaign=%s chars=%d",
                                len(rows), cust_fields.get("_campaign_id"), len(block))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AIM grounding prefetch failed (degrade): %r", exc)

            try:
                asyncio.create_task(_prefetch_grounding())
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM grounding prefetch task spawn failed: %r", exc)

    # ---- DTMF keypad PIN (so an exhausted founder can KEY the PIN, not only speak it) ----
    # SIP DTMF arrives as a livekit.rtc.Room event "sip_dtmf_received" (SipDTMF{digit,code}). We
    # buffer the digits; once a full PIN (or '#') arrives we inject it into the conversation as a
    # user turn so the LLM fires its verify_pin tool. This never blocks audio; spoken PIN still works.
    _dtmf_buf: list[str] = []
    _loop = asyncio.get_running_loop()

    # ---- HCRB fix (h): OBSERVABILITY — log the STT FINAL transcript + each assistant turn to the
    #      JOURNAL (journalctl -u aim-voice-agent), so a real inbound call is traceable end-to-end
    #      WITHOUT having to read PG. The diagnosis found ZERO transcript logging (and an empty
    #      ai_manager_session_turns table), so a "real call" was half-blind. The existing
    #      conversation_item_added handlers feed the PG transcript via _slog.add_turn; THIS adds the
    #      live journal trace. Universal (manager + customer). Best-effort; never affects the call.
    #      Manager turns can carry a spoken PIN, so we scrub any 4+ digit run before logging.
    def _scrub_pin(t: str) -> str:
        try:
            return re.sub(r"\d{4,}", "****", t)
        except Exception:  # noqa: BLE001
            return t

    @session.on("user_input_transcribed")
    def _on_stt_final(ev) -> None:  # noqa: ANN001
        try:
            if not getattr(ev, "is_final", True):
                return
            txt = (getattr(ev, "transcript", "") or "").strip()
            if not txt:
                return
            logger.info("AIM STT-final [%s caller=%s]: %s",
                        ("mgr" if is_manager else "cust"), _mask(caller_id),
                        _scrub_pin(txt)[:300])
        except Exception:  # noqa: BLE001
            pass

    @session.on("conversation_item_added")
    def _on_item_journal(ev) -> None:  # noqa: ANN001
        try:
            item = getattr(ev, "item", None)
            role = getattr(item, "role", "") if item is not None else ""
            text = (getattr(item, "text_content", "") or "") if item is not None else ""
            if text and role in ("user", "assistant"):
                logger.info("AIM turn [%s] %s: %s", ("mgr" if is_manager else "cust"),
                            role, _scrub_pin(text)[:300])
        except Exception:  # noqa: BLE001
            pass

    async def _submit_keyed_pin(digits: str) -> None:
        try:
            logger.info("AIM DTMF PIN received (len=%d) -> injecting for verify_pin", len(digits))
            await session.generate_reply(
                user_input=f"My PIN is {' '.join(list(digits))}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM DTMF submit failed: %r", exc)

    @ctx.room.on("sip_dtmf_received")
    def _on_dtmf(ev) -> None:  # noqa: ANN001
        if not is_manager:
            return  # customers have no PIN — DTMF is a no-op on the sales path
        try:
            digit = getattr(ev, "digit", None)
            if digit is None:
                code = getattr(ev, "code", None)
                digit = str(code) if code is not None else ""
            digit = str(digit or "")
            if not digit:
                return
            if digit == "#":
                d = "".join(_dtmf_buf); _dtmf_buf.clear()
                if d:
                    asyncio.run_coroutine_threadsafe(_submit_keyed_pin(d[:_PIN_LEN]), _loop)
                return
            d = re.sub(r"\D", "", digit)
            if not d:
                return
            _dtmf_buf.append(d)
            if len("".join(_dtmf_buf)) >= _PIN_LEN:
                full = "".join(_dtmf_buf)[:_PIN_LEN]; _dtmf_buf.clear()
                asyncio.run_coroutine_threadsafe(_submit_keyed_pin(full), _loop)
        except Exception:  # noqa: BLE001
            pass

    # ---- CUSTOMER (sales) cross-call thread: collect turns + persist lead/memory on hangup ----
    # Mirrors the outbound earner's memory pattern (agent.py): accumulate {role,content} turns from the
    # session, then on room-disconnect (a) merge+save_memory so the NEXT call continues the thread, and
    # (b) create/update the lead (caller-id + name asked in-call) so the inbound sale is visible in the
    # panel. All best-effort; a persistence failure NEVER affects the live call. Managers persist via
    # their own command-audit path (not here).
    _cust_turns: list[dict] = []
    _cust_persisted = {"done": False}

    if not is_manager:
        @session.on("conversation_item_added")
        def _on_cust_item(ev) -> None:  # noqa: ANN001
            try:
                item = getattr(ev, "item", None)
                role = getattr(item, "role", "") if item is not None else ""
                text = (getattr(item, "text_content", "") or "") if item is not None else ""
                if text and role in ("user", "assistant"):
                    _cust_turns.append({"role": role, "content": text})
                    _slog.add_turn(role, text)   # #8: durable per-turn PG transcript (off-loop)
            except Exception:  # noqa: BLE001
                pass

        async def _persist_customer() -> None:
            if _cust_persisted["done"]:
                return
            _cust_persisted["done"] = True
            # (a) merge with prior memory + save so the thread continues next time
            try:
                if _memory is not None and cust_phone_digits and _cust_turns:
                    prior = _memory.load_memory(cust_phone_digits) or {}
                    prior_hist = list(prior.get("history") or [])
                    merged = prior_hist + _cust_turns
                    _memory.save_memory(cust_phone_digits, merged,
                                        summary=str(prior.get("summary") or ""))
                    logger.info("AIM customer memory saved phone-digits=%s turns=%d",
                                cust_phone_digits[-4:] if cust_phone_digits else "", len(merged))
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM customer memory save failed: %r", exc)
            # (b) create/update the lead so the inbound sale is visible (caller-id + name from the call)
            try:
                if _vt is not None and caller_id:
                    nm = getattr(agent, "_caller_name", "") or cust_name or ""
                    cid = getattr(agent, "_campaign_id", "") or ""
                    res = await asyncio.to_thread(_vt.create_lead, nm, caller_id, cid)
                    logger.info("AIM customer lead upsert ok=%s added=%s name=%r",
                                res.get("ok"), res.get("added"), nm)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AIM customer lead create failed: %r", exc)

        @ctx.room.on("disconnected")
        def _on_room_disconnected(*_a) -> None:  # noqa: ANN002
            try:
                asyncio.run_coroutine_threadsafe(_persist_customer(), _loop)
            except Exception:  # noqa: BLE001
                pass

    # ---- #8 DURABLE SESSION LOGGING — UNIVERSAL (manager + customer) ----
    # Capture EVERY turn into the PG transcript (the customer branch also feeds _slog above; for the
    # MANAGER this is the ONLY transcript listener — managers had none). The PIN tool masks digits to
    # '****' upstream, so no secret ever reaches the transcript. On hangup, close the session row +
    # stop the recording (idempotent; _slog.finish guards a double-close). Best-effort throughout.
    if is_manager:
        @session.on("conversation_item_added")
        def _on_mgr_item(ev) -> None:  # noqa: ANN001
            try:
                item = getattr(ev, "item", None)
                role = getattr(item, "role", "") if item is not None else ""
                text = (getattr(item, "text_content", "") or "") if item is not None else ""
                if text and role in ("user", "assistant"):
                    _slog.add_turn(role, text)
            except Exception:  # noqa: BLE001
                pass

    # ---- HCRB fix (f): HUMAN-HANGUP — end the caller call gracefully when the bridged human leaves ----
    # After a warm transfer the AI has aclose()'d (fix e), so the room contains only the CALLER and the
    # bridged HUMAN (identity "human-handoff-<num>", set at the create_sip_participant call). When THAT
    # human disconnects, the caller would otherwise be left alone on a dead leg (hang / awkward silence).
    # So: detect the human-handoff participant leaving, speak ONE brief goodbye to the caller if the AI
    # session somehow still exists (best-effort — usually it's already gone), log the lifecycle (fix h),
    # then delete the room so the caller's call ends cleanly. Keyed STRICTLY on the human-handoff-* id so
    # a normal caller/agent disconnect never triggers this.
    _human_hangup_done = {"done": False}

    async def _end_after_human_left(human_id: str) -> None:
        if _human_hangup_done["done"]:
            return
        _human_hangup_done["done"] = True
        logger.info("AIM handoff lifecycle: HUMAN-HANGUP (%s left) room %s -> ending caller call",
                    human_id, room_name)
        _live_set_handoff(room_name, "Human hung up", target="")
        # best-effort goodbye to the caller (only fires if the AI session is still live; after a warm
        # transfer it has aclose()'d so this is usually a no-op — guarded so it never raises).
        try:
            if session is not None:
                await session.say(
                    "Thank you so much for calling — have a wonderful day!",
                    allow_interruptions=True, add_to_chat_ctx=False)
                await asyncio.sleep(2.5)
        except Exception:  # noqa: BLE001
            pass
        try:
            await _hangup(ctx, room_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM human-hangup _hangup failed (non-fatal): %r", exc)

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(participant) -> None:  # noqa: ANN001
        try:
            ident = str(getattr(participant, "identity", "") or "")
            if ident.startswith("human-handoff-"):
                asyncio.run_coroutine_threadsafe(_end_after_human_left(ident), _loop)
        except Exception:  # noqa: BLE001
            pass

    @ctx.room.on("disconnected")
    def _on_room_disconnected_log(*_a) -> None:  # noqa: ANN002
        try:
            asyncio.run_coroutine_threadsafe(
                _slog.finish(outcome="completed", status="completed"), _loop)
        except Exception:  # noqa: BLE001
            pass
        # HOFX: drop the live-call record so GET /ai-manager/live stops showing a dead call.
        _live_remove(room_name)

    # ---- START + GREET — EXACTLY the proven outbound path (start, then say) ----
    await session.start(room=ctx.room, agent=agent)

    # ---- HOFX: register this call in the cross-process live-call registry (panel reads it via
    #      GET /ai-manager/live). Best-effort; a registry failure never affects the call. ----
    _live_upsert(room_name, tenant_id=(tenant_id or ADMIN_TENANT),
                 caller=caller_id, mode=("manager" if is_manager else "customer"),
                 state="active", handoff=_live.HANDOFF_NONE if _live is not None else "none")

    # #8: now the room is connected -> create the PG session row + arm the recorder (Egress attaches
    # to a live room). Deferred to here so recording captures the greeting onward. Never blocks/raises.
    try:
        await _slog.start(llm_provider="groq", stt_provider="sarvam", tts_provider="elevenlabs")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM session logger start failed (call continues unlogged): %r", exc)

    if is_manager:
        greeting = (f"Hey! This is {_AGENT_VOICE} from {_COMPANY} — your AI manager. "
                    f"To get you in securely, please say or key in your four-digit PIN.")
    else:
        # CUSTOMER (sales): warm human greeting; recognise returning callers; ask the open question
        # for a new caller who needs disambiguation. NEVER a PIN. Persona name follows the campaign.
        sales_agent_name = (cust_fields.get("agent_name") if cust_fields else "") or _AGENT_VOICE
        sales_company = (cust_fields.get("company_name") if cust_fields else "") or _COMPANY
        # Clean single warm opener (no "Hello/Haan" stutter). The greeting is LANGUAGE-NEUTRAL — a
        # universal "Namaste" + a short ENGLISH question — so the AI's OWN opener does NOT pin the
        # call to Hindi. The CALLER's very first reply then sets the language, and the mirror rule
        # (instructions point 3 + the final LANGUAGE LOCK) makes every reply follow them. This is
        # what lets "caller speaks English -> AI replies English" actually work on a cold open, while
        # a Hindi caller is mirrored straight back into Hindi.
        if cust_is_returning:
            who = f" {cust_name.split()[0]}" if cust_name else ""
            greeting = (f"Namaste{who}, this is {sales_agent_name} from {sales_company}. "
                        "Good to talk again — how can I help you today?")
        elif cust_pending_disambig:
            greeting = (f"Namaste, this is {sales_agent_name} from {sales_company}. "
                        "Which project would you like to know about?")
        else:
            who = f" {cust_name.split()[0]}" if cust_name else ""
            proj = (cust_fields.get("_campaign_name") if cust_fields else "") or ""
            proj_txt = f" about {proj}" if proj else ""
            greeting = (f"Namaste{who}, this is {sales_agent_name} from {sales_company}. "
                        f"Thanks for calling{proj_txt} — how can I help you today?")
    # HCRB fix (a): NEVER announce recording / quality monitoring. The old conditional
    # "this call may be recorded for quality" append is removed entirely — the AI presents as
    # a member of the team and never reads a compliance/recording disclaimer to the caller.
    logger.info("AIM greeting (manager=%s): %s", is_manager, greeting[:120])
    try:
        await session.say(greeting, allow_interruptions=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM greeting say failed (continuing): %r", exc)

    # The LLM agent + its tools now drive the rest of the call (PIN verify, command, or sales).
    # The session runs until the caller hangs up; the worker process exits on room disconnect.


def _mask(phone: str) -> str:
    p = (phone or "").strip()
    if len(p) <= 5:
        return "***"
    return p[:3] + "***" + p[-2:]


async def _hangup(ctx: agents.JobContext, room_name: str) -> None:
    try:
        await asyncio.sleep(0.4)
        await ctx.delete_room(room_name=room_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("hangup/delete_room failed: %r", exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,                                   # "manager"
            port=int(os.getenv("AIM_AGENT_HTTP_PORT", "8091")),     # SEPARATE from agent.py's 8090
        )
    )


if __name__ == "__main__":
    main()
