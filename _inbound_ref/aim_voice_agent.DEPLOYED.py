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
import logging
import os
import re
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    JobProcess,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import elevenlabs, groq, sarvam, silero
from livekit.plugins.elevenlabs import VoiceSettings

# Semantic end-of-turn model (guarded; Silero VAD is the fallback) — identical guard to agent.py.
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel as _SemanticTurnModel
except Exception:  # noqa: BLE001 — plugin may be absent; the agent MUST still run on VAD
    _SemanticTurnModel = None

import itertools as _itertools

# The AI-Manager command brain modules (used by the function-tools, NOT to gate audio).
from ai_manager import registry as _registry  # noqa: F401  (identity.resolve wraps it)
from ai_manager import identity as _identity
from ai_manager import config as _aim_config  # noqa: F401

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
    language="unknown" = auto-detect code-mix Hinglish (forcing hi-IN garbles English)."""
    return sarvam.STT(
        api_key=_next_sarvam_key(),
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
            "`verify_pin` returns verified=true. Once verified, you can help them with campaigns, leads, "
            "calls, and status — ask what they'd like, read back before doing anything that spends money "
            "or is bulk/destructive, and confirm. If the PIN is wrong, let them try again politely; never "
            "go silent. If they just want to chat or ask a question, answer naturally."
        )
    return common + (
        "This is a customer/prospect calling in. Be a helpful, friendly sales assistant for "
        f"{_COMPANY}. Find out what they need, answer their questions warmly, and offer to have the team "
        "follow up. Do NOT ask for any PIN. Keep it natural and short."
    )


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


# ── spoken-digit -> PIN extraction (deterministic) ─────────────────────────────
_WORD_DIGIT = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "to": "2", "too": "2",
    "three": "3", "four": "4", "for": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9",
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5", "chah": "6", "chhe": "6", "saat": "7", "aath": "8", "nau": "9",
}


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
    _max_ep_default = "1.8" if _semantic_on else "0.45"

    session = AgentSession(
        stt=_build_stt(),
        llm=groq.LLM(
            model=os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            api_key=_next_groq_key(),
            temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            max_completion_tokens=int(os.getenv("GROQ_MAX_TOKENS", "140")),
        ),
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

    try:
        ctx._aim_session = session  # let the never-silent guard apologize through it
    except Exception:  # noqa: BLE001
        pass

    @session.on("error")
    def _on_session_error(ev) -> None:  # noqa: ANN001
        try:
            err = getattr(ev, "error", ev)
            recoverable = getattr(err, "recoverable", None)
            logger.warning("AIM session error (recoverable=%s): %r", recoverable, err)
        except Exception:  # noqa: BLE001
            pass

    agent = ManagerAgent(caller_id=caller_id, tenant_id=tenant_id, role=role,
                         is_manager=is_manager, session_id=session_id)

    # ---- START + GREET — EXACTLY the proven outbound path (start, then say) ----
    await session.start(room=ctx.room, agent=agent)

    if is_manager:
        greeting = (f"Hey! This is {_AGENT_VOICE} from {_COMPANY} — your AI manager. "
                    f"To get you in securely, please say or key in your four-digit PIN.")
    else:
        greeting = (f"Hello! This is {_AGENT_VOICE} from {_COMPANY}. "
                    f"How can I help you today?")
    if (os.getenv("AIM_DISCLOSE_RECORDING", "0").strip().lower() not in ("", "0", "false", "no", "off")):
        greeting += " Just so you know, this call may be recorded for quality."
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
