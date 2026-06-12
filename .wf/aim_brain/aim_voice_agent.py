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
    APIConnectOptions,
    JobProcess,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)

# SessionConnectOptions is not publicly re-exported; import it directly. Lets us set per-session
# llm_conn_options (FAIL-FAST: drop max_retry so a doomed/rejected LLM inference can't storm-retry
# 4x into minutes of dead air). Guarded so an API rename can't brick the worker.
try:
    from livekit.agents.voice.agent_session import SessionConnectOptions as _SessionConnectOptions
except Exception:  # noqa: BLE001
    _SessionConnectOptions = None
from livekit.plugins import elevenlabs, groq, sarvam, silero
from livekit.plugins.elevenlabs import VoiceSettings

# Semantic end-of-turn model (guarded; Silero VAD is the fallback) — identical guard to agent.py.
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel as _SemanticTurnModel
except Exception:  # noqa: BLE001 — plugin may be absent; the agent MUST still run on VAD
    _SemanticTurnModel = None

# ── HUMAN WARM TRANSFER (BUILD#6) ──────────────────────────────────────────────
# LiveKit's NATIVE warm-transfer task: dials the human INTO the room over the OUTBOUND trunk
# (CreateSIPParticipant -> brief with chat_ctx -> MoveParticipant = a true warm conference bridge).
# Carrier-agnostic (no SIP REFER needed). We REUSE the earner's outbound trunk ID as a STRING ONLY —
# never editing the trunk / dispatch / agent.py. Guarded so the worker still boots if the beta API
# is renamed/absent (transfer then degrades to the WhatsApp+callback fallback, never a dead drop).
try:
    from livekit.agents.beta.workflows import WarmTransferTask as _WarmTransferTask
except Exception:  # noqa: BLE001
    _WarmTransferTask = None
    logging.getLogger("aim-voice").warning(
        "WarmTransferTask import failed; transfer_to_human will use WhatsApp+callback fallback only")

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
            "• `transfer_to_human(reason)` — connect the manager to a REAL person on the team (warm "
            "transfer). Call this ONLY if they explicitly ask to talk to a human/person, or you "
            "genuinely cannot handle what they need. It dials a team member into the call; once it "
            "hands off, stop talking and let the human take over.\n\n"
            "Keep every reply short and natural; let the manager talk. If they just want to chat, answer."
        )
    return common + (
        "This is a customer/prospect calling in. Be a helpful, friendly sales assistant for "
        f"{_COMPANY}. Find out what they need, answer their questions warmly, and offer to have the team "
        "follow up. Do NOT ask for any PIN. Keep it natural and short."
    )


# ── HUMAN WARM TRANSFER helper (shared by BOTH agents) ─────────────────────────
def _transfer_whisper(reason: str, name: str, phone: str, summary: str) -> str:
    """The one-line private brief the AI speaks to the human as they join (rides chat_ctx too)."""
    who = (name or "the caller").strip() or "the caller"
    bits = [f"Connecting you to {who}"]
    if phone:
        bits.append(f"on {phone}")
    if (reason or "").strip():
        bits.append(f"— reason: {reason.strip()}")
    if (summary or "").strip():
        bits.append(f". Context: {summary.strip()[:200]}")
    bits.append(". Over to you — please take it from here.")
    return " ".join(bits)


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

    # 1) read the vendor handoff team (filesystem, no HTTP/auth).
    team = []
    if _vt is not None:
        try:
            team = await asyncio.to_thread(_vt.handoff_list, tenant_id) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM handoff_list failed: %r", exc)
            team = []

    # 2) bridge line to the caller (off-loop so it overlaps the dial; never silent).
    await _say_filler(context, "Bilkul — ek second, main aapko abhi ek team member se connect karti hoon…")

    # 3) fire the hot-lead WhatsApp SIMULTANEOUSLY (belt-and-braces; lands the lead in the team's chat).
    if _vt is not None and team:
        try:
            asyncio.create_task(asyncio.to_thread(
                _vt.notify_handoff_team, name, caller_id, summary, 80))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM handoff WA notify spawn failed: %r", exc)

    # 4) if no team configured -> capture + WhatsApp(if any) + tell caller the team will call back.
    if not team:
        logger.info("AIM transfer_to_human: NO handoff team (tenant=%s) -> callback fallback", tenant_id)
        return ("no_human_available: there's no team member on the handoff list to connect right now. "
                "Warmly tell the caller our team will call them back very shortly, confirm their number, "
                "and close politely — never leave them hanging.")

    # 5) WarmTransferTask present? if not, degrade to the WhatsApp+callback fallback (already fired).
    if _WarmTransferTask is None:
        logger.warning("AIM transfer_to_human: WarmTransferTask unavailable -> WA+callback fallback")
        return ("handoff_logged: I couldn't open a live bridge just now, but I've alerted the team with "
                "the caller's details on WhatsApp. Tell the caller a team member will call them right "
                "back, confirm the number, and close warmly.")

    # 6) dial each eligible human INTO the room (priority order) until one answers.
    chat_ctx = getattr(agent, "chat_ctx", None)
    last_err = ""
    for h in team:
        num = (h.get("phone") or h.get("whatsapp") or "").strip()
        if not num:
            continue
        logger.info("AIM transfer_to_human: dialing human %s (role=%s) into room",
                    _mask(num), h.get("role", ""))
        try:
            task_kwargs = dict(
                sip_call_to=num,
                sip_trunk_id=_OUTBOUND_TRUNK,           # read-only reuse of the earner's trunk id
                instructions=_transfer_whisper(reason, name, caller_id, summary),
                ringing_timeout=_TRANSFER_RING_TIMEOUT,
            )
            if chat_ctx is not None:
                task_kwargs["chat_ctx"] = chat_ctx
            task = _WarmTransferTask(**task_kwargs)
            await task                                    # inline-task: dial -> brief -> merge into room
            logger.info("AIM transfer_to_human: HANDED OFF to %s", _mask(num))
            return ("handed_off: a team member is now on the line with the caller. Briefly tell the "
                    "caller you're connecting them, then STOP talking and let the human take over.")
        except Exception as exc:  # noqa: BLE001 — no-answer / busy / decline -> next number
            last_err = type(exc).__name__
            logger.info("AIM transfer_to_human: %s didn't connect (%s) -> next number",
                        _mask(num), last_err)
            continue

    # 7) nobody answered -> never a dead drop. The hot-lead WA already fired (step 3).
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
        """Connect the caller to a REAL human team member NOW (warm transfer). Use ONLY when the
        manager explicitly asks to talk to a person, or you genuinely cannot handle their request.
        Dials the next available human from the handoff list INTO this call (a warm bridge) and steps
        you back; if no one answers, the team is alerted on WhatsApp and will call back. Speak the
        result it returns; once handed off, stop talking and let the human take over.

        Args:
            reason: a short reason for the transfer (e.g. "wants to speak to a person", "billing
                    dispute I can't resolve"). Pass as a plain string.
        """
        logger.info("AIM transfer_to_human (manager) reason=%r tenant=%s", (reason or "")[:80],
                    getattr(self, "_tenant_id", ""))
        return await _do_warm_transfer(self, context, reason or "")


# ── the Customer (sales) Agent — a natural human salesperson for NON-manager callers ───────────
def _build_sales_instructions(fields: dict, recap: str, caller_name: str,
                              is_returning: bool, pending_disambig: bool,
                              campaign_options: list[dict] | None) -> str:
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
            "If the caller explicitly asks to talk to a human/person/agent, call the "
            "`transfer_to_human(reason)` tool to connect a real team member into the call."
        )

    # Campaign resolved -> run the FULL outbound sales brain (reused read-only), reframed for inbound.
    brain = ""
    if _prompt is not None and fields:
        try:
            brain = _prompt.build_system_prompt(fields)
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
        "HANDOFF TO A HUMAN: if the caller explicitly asks to talk to a person/human/agent, OR they're "
        "clearly a HOT, ready-to-buy lead who'd close better with a human, call the `transfer_to_human"
        "(reason)` tool — it connects a real team member into the call. Once it hands off, stop talking "
        "and let the human take over. Don't offer a human for ordinary questions you can answer yourself."
    )
    return head + brain + recap_block + inbound_note


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
                 campaign_options: list[dict] | None) -> None:
        super().__init__(instructions=_build_sales_instructions(
            fields or {}, recap, caller_name, is_returning, pending_disambig, campaign_options))
        self._caller_id = caller_id
        self._tenant_id = tenant_id or ADMIN_TENANT
        self._session_id = session_id
        self._fields = dict(fields or {})
        self._caller_name = caller_name or ""
        self._is_returning = is_returning
        self._pending_disambig = pending_disambig
        self._campaign_options = campaign_options or []
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
        try:
            await self.update_instructions(_build_sales_instructions(
                self._fields, "", self._caller_name, False, False, None))
        except Exception as exc:  # noqa: BLE001
            logger.warning("pick_campaign update_instructions failed: %r", exc)
        logger.info("AIM pick_campaign matched -> %s (%s)", self._campaign_name, self._campaign_id)
        cname = self._campaign_name or "that project"
        return (f"matched: loaded {cname}. Now warmly continue helping them about {cname} using its "
                "details — one short beat at a time. Find out what they need and move toward a site "
                "visit or a callback.")

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
        """Connect this caller to a REAL human salesperson NOW (warm transfer). Use when the caller
        explicitly asks to speak to a person/human/agent, OR when they're clearly a HOT, ready-to-buy
        lead who'd be best served by a human closing the deal, OR when you genuinely can't help. Dials
        the next available team member from the handoff list INTO this call (a warm bridge) and steps
        you back; if no one answers, the team is alerted on WhatsApp with the caller's details and will
        call back. Speak the result it returns; once handed off, stop talking and let the human take over.

        Args:
            reason: a short reason (e.g. "asked for a human", "hot lead ready to book", "needs the
                    builder directly"). Pass as a plain string.
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
    _aim_llm = groq.LLM(
        model=os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
        api_key=_next_groq_key(),
        temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
        max_completion_tokens=int(os.getenv("GROQ_MAX_TOKENS", "160")),
    )
    try:
        _aim_llm._strict_tool_schema = False  # noqa: SLF001 — intentional, isolated to THIS agent
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

    # ---- DTMF keypad PIN (so an exhausted founder can KEY the PIN, not only speak it) ----
    # SIP DTMF arrives as a livekit.rtc.Room event "sip_dtmf_received" (SipDTMF{digit,code}). We
    # buffer the digits; once a full PIN (or '#') arrives we inject it into the conversation as a
    # user turn so the LLM fires its verify_pin tool. This never blocks audio; spoken PIN still works.
    _dtmf_buf: list[str] = []
    _loop = asyncio.get_running_loop()

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

    # ---- START + GREET — EXACTLY the proven outbound path (start, then say) ----
    await session.start(room=ctx.room, agent=agent)

    if is_manager:
        greeting = (f"Hey! This is {_AGENT_VOICE} from {_COMPANY} — your AI manager. "
                    f"To get you in securely, please say or key in your four-digit PIN.")
    else:
        # CUSTOMER (sales): warm human greeting; recognise returning callers; ask the open question
        # for a new caller who needs disambiguation. NEVER a PIN. Persona name follows the campaign.
        sales_agent_name = (cust_fields.get("agent_name") if cust_fields else "") or _AGENT_VOICE
        sales_company = (cust_fields.get("company_name") if cust_fields else "") or _COMPANY
        if cust_is_returning:
            who = f" {cust_name.split()[0]}" if cust_name else ""
            greeting = (f"Hi{who}! This is {sales_agent_name} from {sales_company}. "
                        "Good to hear from you again — picking up from where we left off, "
                        "how can I help you today?")
        elif cust_pending_disambig:
            greeting = (f"Hello! This is {sales_agent_name} from {sales_company}. "
                        "Aap kis project ke baare mein jaanna chahte hain?")
        else:
            who = f" {cust_name.split()[0]}" if cust_name else ""
            proj = (cust_fields.get("_campaign_name") if cust_fields else "") or ""
            proj_txt = f" about {proj}" if proj else ""
            greeting = (f"Hello{who}! This is {sales_agent_name} from {sales_company}. "
                        f"Thanks for calling{proj_txt} — how can I help you today?")
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
