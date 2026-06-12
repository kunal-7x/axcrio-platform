"""aim_voice_agent.py — the INBOUND AI Manager voice agent (LiveKit persona agent_name="manager").

⚠️ ADDITIVE / SEPARATE worker. This is a SECOND LiveKit worker registered ALONGSIDE the live
outbound earner (agent.py, agent_name="capsy"). It NEVER imports, restarts, or mutates agent.py /
caller.py / the outbound trunks. Deploy = its OWN systemd unit on the famit-livekit box. Dormant
until an inbound SIP dispatch rule routes the AI-Manager DID (+918071583488) to agent_name="manager".

WHAT IT DOES (the inbound command line the founder phones):
  1. Inbound SIP call -> dispatch rule -> a room -> THIS worker joins (entrypoint).
  2. Read the caller-ID off the SIP participant attribute `sip.phoneNumber`. Extra hard gate:
     only the authorized caller (AIM_AUTHORIZED_CALLER, default +917861019021) proceeds.
  3. Greet ("Hello, this is your Famit AI Manager. Please say or enter your PIN.").
  4. Drive the ALREADY-BUILT, offline-tested `ai_manager.state_machine.CommandMachine` — the SAME
     deterministic safety spine the chat Test Console uses (endpoints._run_test_command /
     _transition_command). The voice layer is a THIN transport adapter; it owns NONE of the
     auth / PIN / risk / delegate logic.
        S0 connect -> S1 identify (registry.lookup by caller-ID) -> S2 PIN (firewall.check_pin,
        anti-spoof, BEFORE any data) -> S3 context headline -> S4 capture intent (STT -> NLU)
        -> S5 permission -> S6 step-up PIN for risky -> S7 confirm -> S8 delegate to
        workforce.run_agent (= delegate.execute) -> S9 speak the result -> loop.
  5. PIN capture: DTMF preferred (digits arrive as SIP events, NEVER through STT/recording);
     spoken-digit fallback with a tiny deterministic number-word map. Recorder PAUSED around the
     secret span (state_machine._collect_secret already wraps rec.pause()/resume()).

VOICE STACK = agent.py's tuned, low-latency stack, COPIED not re-derived (so the ~1.1s/turn moat is
inherited): Sarvam STT saarika:v2.5 language="unknown", Groq llama-4-scout (round-robin env creds),
TTS via ElevenLabs and Sarvam, preemptive_generation + the endpointing/barge-in kwargs + turn-detection.
The ONE deliberate difference: this session has NO sales-pitch LLM persona — the LLM is used only by
the state machine's NLU (closed-enum IntentMatch); turn-taking/STT/TTS are the agent's job.

ASYNC/SYNC BRIDGE (the load-bearing structural fact): CommandMachine.run() is SYNCHRONOUS (speak/
listen/collect_secret). LiveKit AgentSession is ASYNC. So we run machine.run(caller_id) in a worker
THREAD (asyncio.to_thread) and the VoiceTransport hops every call back onto the event loop with
asyncio.run_coroutine_threadsafe(...).result(). The agent loop owns the mic/turns; the machine owns
the policy. Neither blocks the other.

Run (NOT in this task — written locally, ready to deploy):
  python aim_voice_agent.py start   (registers agent_name="manager")
Env: /opt/famit-agent/.env  (reuses the box's Sarvam/Groq/ElevenLabs keys + FIREWALL secret).
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
from livekit.agents import Agent, AgentSession, JobProcess, RoomInputOptions, WorkerOptions, cli
from livekit.agents import APIConnectOptions, stt as _lk_stt
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import elevenlabs, groq, sarvam, silero
from livekit.plugins.elevenlabs import VoiceSettings

# Semantic end-of-turn model (guarded; Silero VAD is the fallback) — identical guard to agent.py.
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel as _SemanticTurnModel
except Exception:  # noqa: BLE001 — plugin may be absent; the agent MUST still run on VAD
    _SemanticTurnModel = None

import inspect as _inspect
import itertools as _itertools

# The AI-Manager command brain — the SAME modules the chat Test Console drives in-process.
from ai_manager.state_machine import CommandMachine, Transport
from ai_manager import config as _aim_config
from ai_manager import store as _aim_store
from ai_manager import endpoints as _aim_endpoints
from ai_manager import recorder as _aim_recorder

load_dotenv("/opt/famit-agent/.env")
load_dotenv(".env")

logger = logging.getLogger("aim-voice")


# ── firewall init (LOAD-BEARING) ───────────────────────────────────────────────
# In the live API process, caller.py calls firewall.init(secret=<var/secret>, pin_file=<var/pins.json>)
# at startup. THIS is a separate worker process, so NOTHING has init'd the firewall — and an
# un-init'd firewall fail-CLOSES: check_pin() returns False for EVERYTHING, so the founder's correct
# PIN (4827) would be wrongly REJECTED and he could never authenticate. So we replicate caller.py's
# init here, exactly once at startup, reusing the SAME var/secret + var/pins.json. NEVER raises;
# if it degrades, the PIN gate stays fail-closed (deny) — which is the safe direction.
_FAMIT_VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))


def _load_secret() -> str:
    """Read the SAME hmac secret caller.py uses (var/secret). Mirrors caller._load_secret (read-only;
    we never create it — if absent we fall back to env, then degrade fail-closed)."""
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
    """Init the live firewall module once (idempotent). Returns True if the step-up path is available."""
    try:
        import firewall as _fw  # the F4 Action Firewall (same module the bridge/workforce import)
        ready = bool(_fw.init(secret=_load_secret(), pin_file=_FAMIT_VAR / "pins.json"))
        logger.info("AIM firewall init: ready=%s available=%s", ready, _fw.available())
        return ready
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM firewall init FAILED (PIN gate will fail-closed/deny): %r", exc)
        return False


_FIREWALL_READY = _init_firewall()

# ── identity / gating ─────────────────────────────────────────────────────────
AGENT_NAME = os.getenv("AIM_VOICE_AGENT_NAME", "manager")
# Hard extra gate ON TOP of registry.lookup + the in-call PIN: only this caller-ID proceeds.
# (Caller-ID is a HINT, never a credential — the PIN in S2 is the real proof. This is belt-and-braces
#  so a spoofed unknown number is dropped before any prompt.) Empty -> rely on registry only.
AUTHORIZED_CALLER = os.getenv("AIM_AUTHORIZED_CALLER", "+917861019021").strip()
# Extra caller-IDs that should also pass the (optional) allowlist. The founder's number is
# presented by Vobiz as 06375548830 (NOT his SIM MSISDN +917861019021), so include it as
# belt-and-braces. Comma-separated; merged into the allowlist below.
AIM_EXTRA_AUTHORIZED = os.getenv("AIM_EXTRA_AUTHORIZED", "06375548830,+917861019021").strip()
# ⚠️ SECURITY MODEL: the caller-ID is a HINT, NEVER a credential. The PIN (firewall, 4827) is the
# real proof and gates ALL data/actions in S2. Caller-IDs are masked/spoofable/unreliable, so by
# DEFAULT we DO NOT reject on caller-ID — every inbound call is GREETED and PIN-gated. Set
# AIM_REQUIRE_AUTHORIZED_CALLER=1 ONLY if you want the (weaker) hard caller-ID allowlist back.
REQUIRE_AUTHORIZED_CALLER = (os.getenv("AIM_REQUIRE_AUTHORIZED_CALLER", "0").strip().lower()
                            not in ("", "0", "false", "no", "off"))
# The tenant whose firewall PIN (4827) gates the founder. Registry.lookup normally supplies this;
# this is the fallback used only if the number isn't registered yet (single-tenant box convenience).
ADMIN_TENANT = os.getenv("AIM_ADMIN_TENANT", "admin").strip()


def _canon(phone: str) -> str:
    """'+' + digits only (mirrors registry.canonical_phone) for caller-ID comparison."""
    if not phone:
        return ""
    s = str(phone).strip()
    plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    return (("+" if plus else "") + digits) if digits else ""


def _match_forms(phone: str) -> set[str]:
    """The CRM-core silent-join expansion: a '+91…' record must match a caller-ID arriving as
    bare-10 / leading-0. Returns every digit-rep of the inbound number."""
    digits = re.sub(r"\D", "", phone or "")
    forms = {digits}
    if digits.startswith("91") and len(digits) > 10:
        forms.add(digits[2:])
    if len(digits) == 10:
        forms.add("91" + digits)
        forms.add("0" + digits)
    if digits.startswith("0"):
        forms.add(digits[1:])
    return {f for f in forms if f}


# ── Groq + Sarvam key round-robin (COPIED from agent.py so concurrent turns spread load) ───────────
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


# ── tuned-voice-stack helpers (COPIED verbatim from agent.py — do NOT re-derive) ───────────────────
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


def _session_kwargs_filter(kwargs: dict) -> dict:
    """Drop any AgentSession kwarg the installed build doesn't accept (portability/crash-safety)."""
    try:
        sig = _inspect.signature(AgentSession.__init__)
        if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            return kwargs
        allowed = set(sig.parameters)
        return {k: v for k, v in kwargs.items() if k in allowed}
    except Exception:  # noqa: BLE001
        return kwargs


def _barge_in_kwargs() -> dict:
    out: dict = {}
    miw = (os.getenv("MIN_INT_WORDS") or "").strip()
    if miw:
        try:
            out["min_interruption_words"] = int(miw)
        except ValueError:
            pass
    rfi = (os.getenv("RESUME_FALSE_INT") or "").strip()
    if rfi:
        out["resume_false_interruption"] = rfi not in ("0", "false", "False")
    return out


# ── spoken-digit -> PIN extraction (deterministic; NO LLM on the hot path) ─────────────────────────
_WORD_DIGIT = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "to": "2", "too": "2",
    "three": "3", "four": "4", "for": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9",
    # Hindi spoken digits (Sarvam often transcribes these)
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5", "chah": "6", "chhe": "6", "saat": "7", "aath": "8", "nau": "9",
}


def _extract_digits(text: str, n: int = 4) -> str:
    """Pull a PIN out of a spoken/transcribed utterance. Bare digits first ('4827', '4 8 2 7'),
    then number-words ('four eight two seven' / 'char aath do saat'). Returns up to n digits.
    NEVER logs the result; the caller masks it. NEVER raises."""
    try:
        t = (text or "").strip()
        # Devanagari digits -> ASCII
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


# ── the VoiceTransport: bridges the SYNC state machine <-> the ASYNC AgentSession ──────────────────
class VoiceTransport(Transport):
    """Implements the state machine's transport contract (speak / listen / collect_secret) on top of a
    live LiveKit AgentSession. Every method is called from the WORKER THREAD running machine.run(); it
    hops onto the AgentSession's event loop via run_coroutine_threadsafe(...).result(). NEVER raises
    (the machine treats "" as hangup)."""

    def __init__(self, session: AgentSession, loop: asyncio.AbstractEventLoop, *,
                 user_turns: "asyncio.Queue[str]", dtmf_buf: list, dtmf_event: asyncio.Event,
                 hung_up: threading.Event, pin_len: int = 4, listen_timeout: float = 30.0):
        self.s = session
        self.loop = loop
        self.user_turns = user_turns          # final user transcripts pushed by the session callbacks
        self.dtmf_buf = dtmf_buf              # collected DTMF digits (mutated on the loop thread)
        self.dtmf_event = dtmf_event         # set when a '#'/enough digits arrive
        self.hung_up = hung_up
        self.pin_len = pin_len
        self.listen_timeout = listen_timeout

    # -- speak: session.say(text) and wait for the audio to finish (so turns don't overlap) --
    def speak(self, text: str) -> None:
        if not text or self.hung_up.is_set():
            return
        async def _say() -> None:
            try:
                handle = self.s.say(text, allow_interruptions=True)
                try:
                    await handle.wait_for_playout()
                except Exception:  # noqa: BLE001 — handle API drift: best-effort grace
                    await asyncio.sleep(min(0.06 * max(1, len(text)), 6.0))
            except Exception as exc:  # noqa: BLE001
                logger.warning("speak failed: %r", exc)
        try:
            asyncio.run_coroutine_threadsafe(_say(), self.loop).result(timeout=30)
        except Exception:  # noqa: BLE001
            pass

    # -- listen: block (on the worker thread) for the next FINAL user transcript --
    def listen(self) -> str:
        if self.hung_up.is_set():
            return ""
        async def _next() -> str:
            try:
                return await asyncio.wait_for(self.user_turns.get(), timeout=self.listen_timeout)
            except asyncio.TimeoutError:
                return ""           # silence -> treat as hangup (the machine ends gracefully)
            except Exception:  # noqa: BLE001
                return ""
        try:
            return asyncio.run_coroutine_threadsafe(_next(), self.loop).result(
                timeout=self.listen_timeout + 5) or ""
        except Exception:  # noqa: BLE001
            return ""

    # -- collect_secret: DTMF preferred (digits as SIP events, never via STT); spoken fallback --
    def collect_secret(self, n: int = 4, mode: str = "voice_pin") -> str:
        if self.hung_up.is_set():
            return ""
        # The recorder is paused by state_machine._collect_secret around THIS call (PIN-audio hygiene).
        # 1) DTMF: drain any keypad digits the caller pressed (collected by _on_dtmf into dtmf_buf).
        async def _wait_dtmf() -> str:
            try:
                self.dtmf_event.clear()
                # if digits already buffered, use them immediately
                if len("".join(self.dtmf_buf)) >= n:
                    digits = "".join(self.dtmf_buf)[:n]
                    self.dtmf_buf.clear()
                    return digits
                try:
                    await asyncio.wait_for(self.dtmf_event.wait(), timeout=12.0)
                except asyncio.TimeoutError:
                    return ""
                digits = "".join(self.dtmf_buf)
                self.dtmf_buf.clear()
                # strip a trailing '#' terminator if present, keep the digits
                return re.sub(r"\D", "", digits)[:n]
            except Exception:  # noqa: BLE001
                return ""
        try:
            dtmf = asyncio.run_coroutine_threadsafe(_wait_dtmf(), self.loop).result(timeout=15) or ""
        except Exception:  # noqa: BLE001
            dtmf = ""
        if dtmf:
            return dtmf
        # 2) Spoken fallback: the NEXT user turn -> extract digits with the number-word map.
        spoken = self.listen()
        return _extract_digits(spoken, n=n)


# ── prewarm (worker process, BEFORE any call) ──────────────────────────────────
def prewarm(proc: JobProcess) -> None:
    """VOICEFIX: load the blocking Silero VAD ONCE per worker process here — NOT inside the per-call
    entrypoint. Doing the CPU-heavy `silero.VAD.load()` during `session.start()` saturated the event
    loop and starved the DNS resolver thread, which lost the Sarvam STT connect race -> silence
    (design/silence-stt.md §7b). With VAD warm in the worker, session bring-up has headroom for the
    STT WS connect + early audio. NEVER raises (a failed prewarm just falls back to an inline load)."""
    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("AIM prewarm: Silero VAD loaded")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM prewarm VAD load failed (will load inline per call): %r", exc)


# ── the worker entrypoint ──────────────────────────────────────────────────────
async def entrypoint(ctx: agents.JobContext) -> None:
    """NEVER-SILENT outer guard: the real work is in _entrypoint_impl. If ANYTHING raises before
    we hand off to the CommandMachine (stack build, gate, greet), we still try to speak an apology
    and always hang up cleanly — a caller must never hear 30s of silence."""
    try:
        await _entrypoint_impl(ctx)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM entrypoint guard caught: %r", exc)
        # best-effort apology over whatever session/room exists, then clean hangup.
        try:
            room = getattr(ctx, "room", None)
            sess = getattr(ctx, "_aim_session", None)
            if sess is not None:
                try:
                    handle = sess.say("Sorry, the Famit AI Manager hit a problem. Please call again in a moment.")
                    await handle.wait_for_playout()
                except Exception:  # noqa: BLE001
                    pass
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
        # wait briefly for the SIP participant to materialize
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

    # ---- build the tuned voice stack (COPIED from agent.py) ----
    tts = _build_tts()
    _call_groq_key = _next_groq_key()
    _td = _resolve_turn_detection()
    _semantic_on = not isinstance(_td, str)
    _max_ep_default = "1.8" if _semantic_on else "0.45"

    # VOICEFIX: use the VAD loaded ONCE in prewarm (worker process, before the call) instead of
    # blocking the event loop with silero.VAD.load() inside session bring-up. That CPU spike is what
    # starved the loop's resolver thread and lost the Sarvam DNS race -> silence (design/silence-stt.md
    # §7b). Fall back to a fresh load only if prewarm didn't run (e.g. dev `python … connect`).
    _vad = None
    try:
        _vad = ctx.proc.userdata.get("vad")
    except Exception:  # noqa: BLE001
        _vad = None
    if _vad is None:
        logger.info("AIM VAD not prewarmed; loading inline (fallback)")
        _vad = silero.VAD.load()
    # VOICEFIX: session-level STT connect tolerance — a transient DNS/connect stall must RETRY, not
    # crash the call. Default was max_retry=3/timeout=10; widen so a momentary resolver race survives.
    _stt_conn = APIConnectOptions(
        max_retry=int(os.getenv("AIM_STT_MAX_RETRY", "6")),
        retry_interval=float(os.getenv("AIM_STT_RETRY_INTERVAL", "1.0")),
        timeout=float(os.getenv("AIM_STT_TIMEOUT", "20")),
    )
    session = AgentSession(
        stt=_build_stt(_vad),
        conn_options=SessionConnectOptions(stt_conn_options=_stt_conn),
        llm=groq.LLM(
            model=os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            api_key=_call_groq_key,
            temperature=float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            max_completion_tokens=int(os.getenv("GROQ_MAX_TOKENS", "140")),  # NOT max_tokens (crashes)
        ),
        tts=tts,
        vad=_vad,
        preemptive_generation=True,
        min_endpointing_delay=float(os.getenv("MIN_EP_DELAY", "0.25")),
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", _max_ep_default)),
        aec_warmup_duration=0.0,
        min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.25")),
        false_interruption_timeout=float(os.getenv("FALSE_INT_TIMEOUT", "1.0")),
        turn_detection=_td,
        **_session_kwargs_filter(_barge_in_kwargs()),
    )

    loop = asyncio.get_running_loop()
    try:
        ctx._aim_session = session  # let the never-silent guard apologize through it
    except Exception:  # noqa: BLE001
        pass
    user_turns: asyncio.Queue[str] = asyncio.Queue()
    dtmf_buf: list[str] = []
    dtmf_event = asyncio.Event()
    hung_up = threading.Event()

    # ---- capture FINAL user transcripts -> the listen() queue (skip during PIN spans is handled by
    #      the state machine pausing the recorder; the queue only carries finalized user turns) ----
    @session.on("conversation_item_added")
    def _on_item(ev) -> None:  # noqa: ANN001
        try:
            role = getattr(ev.item, "role", "?")
            text = getattr(ev.item, "text_content", "") or ""
            if role == "user" and text:
                logger.info("turn[user]: %s", text[:120])
                loop.call_soon_threadsafe(user_turns.put_nowait, text)
        except Exception:  # noqa: BLE001
            pass

    # ---- DTMF keypad digits arrive as RTC-ROOM events (livekit.rtc.Room emits "sip_dtmf_received"
    #      with a SipDTMF{digit,code,participant}), NOT as AgentSession events — so register on
    #      ctx.room, never on the session. They never transit STT/recording. (Verified against the
    #      box's livekit 1.5.17: rtc/room.py:950 emits it; AgentSession.EventTypes has no DTMF.) ----
    @ctx.room.on("sip_dtmf_received")
    def _on_dtmf(ev) -> None:  # noqa: ANN001
        try:
            digit = getattr(ev, "digit", None)
            if digit is None:
                code = getattr(ev, "code", None)
                digit = str(code) if code is not None else ""
            digit = str(digit)
            if not digit:
                return
            if digit == "#":
                loop.call_soon_threadsafe(dtmf_event.set)
                return
            d = re.sub(r"\D", "", digit)
            if not d:
                return
            dtmf_buf.append(d)
            # auto-fire once we likely have a full PIN so the caller needn't press '#'
            if len("".join(dtmf_buf)) >= int(os.getenv("AIM_PIN_LEN", "4")):
                loop.call_soon_threadsafe(dtmf_event.set)
        except Exception:  # noqa: BLE001
            pass

    @ctx.room.on("disconnected")
    def _on_disc(*_a) -> None:  # noqa: ANN002
        hung_up.set()
        try:
            loop.call_soon_threadsafe(user_turns.put_nowait, "")
        except Exception:  # noqa: BLE001
            pass

    # ---- VOICEFIX: session-level error handler. The framework emits "error" for recoverable STT/TTS/
    #      LLM hiccups (incl. a Sarvam connect retry). We LOG it and KEEP THE CALL ALIVE — a transient
    #      STT connect blip must NEVER silent-kill the session (the old crash). The state machine keeps
    #      driving; the widened session conn_options (6 retries / 20s) handles the recovery underneath. ----
    @session.on("error")
    def _on_session_error(ev) -> None:  # noqa: ANN001
        try:
            err = getattr(ev, "error", ev)
            recoverable = getattr(err, "recoverable", None)
            src_obj = getattr(ev, "source", None)
            logger.warning("AIM session error (recoverable=%s, source=%s): %r",
                           recoverable, type(src_obj).__name__, err)
        except Exception:  # noqa: BLE001
            pass

    # The agent has no system-prompt persona of its own (no sales pitch) — turn-taking/STT/TTS only.
    # All speech is authored by the state machine via transport.speak(); the LLM serves the NLU.
    # VOICEFIX: close_on_disconnect=False — a transient input/STT-track disconnect must NOT auto-close
    # the AgentSession (which would suppress the greeting / kill the call). The session stays alive so
    # the greeting always plays and the STT can reconnect underneath (per design/silence-session.md +
    # inbound-stt-fix.md). delete_room_on_close stays default (we own hangup via _hangup()).
    await session.start(
        room=ctx.room,
        agent=Agent(instructions=(
            "You are the transport layer for a command assistant. Do not volunteer content. "
            "Only the controller speaks; you transcribe the caller and synthesize the controller's text.")),
        room_input_options=RoomInputOptions(close_on_disconnect=False),
    )

    pin_len = int(os.getenv("AIM_PIN_LEN", "4"))
    transport = VoiceTransport(session, loop, user_turns=user_turns, dtmf_buf=dtmf_buf,
                               dtmf_event=dtmf_event, hung_up=hung_up, pin_len=pin_len)

    # ---- GREET FIRST, ALWAYS (human-like, independent of caller-ID and STT) ----
    # The VERY FIRST action on join is a spoken, NATURAL greeting so the caller ALWAYS hears a warm
    # human voice within ~1-2s of connecting. This fires BEFORE any gate and BEFORE the STT pump
    # matters — no code path may reach silence. A transient STT failure cannot suppress this
    # (say() uses TTS only). Human tone, not "I am an AI assistant from…". A brief, natural recording
    # disclosure is appended only if AIM_DISCLOSE_RECORDING=1 (off by default; flip on if legally req'd).
    _agent_voice = os.getenv("AIM_AGENT_VOICE_NAME", "Riya").strip() or "Riya"
    _company = os.getenv("AIM_COMPANY_NAME", "Famit").strip() or "Famit"
    _greeting = (f"Hey! This is {_agent_voice} from {_company} — your AI manager. "
                 f"To get you in securely, please say or key in your four-digit PIN.")
    if (os.getenv("AIM_DISCLOSE_RECORDING", "0").strip().lower() not in ("", "0", "false", "no", "off")):
        _greeting += " Just so you know, this call may be recorded for quality."
    try:
        transport.speak(_greeting)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM greeting speak failed (continuing): %r", exc)

    # ---- GATE 0: caller-ID allowlist is now OPTIONAL/SOFT. By default we DO NOT reject — the PIN
    #      is the real proof. We hard-reject on caller-ID ONLY if AIM_REQUIRE_AUTHORIZED_CALLER=1.
    allow_forms = _match_forms(AUTHORIZED_CALLER) if AUTHORIZED_CALLER else set()
    for _extra in re.split(r"[\s,]+", AIM_EXTRA_AUTHORIZED or ""):
        if _extra:
            allow_forms |= _match_forms(_extra)
    _caller_known = bool(_match_forms(caller_id) & allow_forms)
    if not _caller_known:
        if REQUIRE_AUTHORIZED_CALLER:
            logger.warning("AIM inbound REJECT unauthorized caller=%s (AIM_REQUIRE_AUTHORIZED_CALLER=1)",
                           _mask(caller_id))
            try:
                transport.speak("Sorry, this number is not authorized for the Famit AI Manager. Goodbye.")
            except Exception:  # noqa: BLE001
                pass
            await _hangup(ctx, room_name)
            return
        # SOFT mode (default): proceed — greet (already done) + PIN-gate this unknown caller.
        logger.info("AIM inbound caller=%s not in allowlist -> proceeding (soft); PIN will gate",
                    _mask(caller_id))

    # ---- pre-mint the session id so the recording object-key + the persisted session row share ONE id.
    #      (The state machine would otherwise mint its own; we pass ours in via machine.run(session_id=).)
    session_id = "vs_" + uuid.uuid4().hex[:12]

    # ---- CALL RECORDING (P1): start a LiveKit egress -> DO Spaces. DORMANT until AIM_RECORDING_ENABLED
    #      + Spaces creds are set (else a NullRecorder -> the call runs exactly as before). The recorder
    #      is started in a worker thread (its LiveKit API call is sync-over-async) so it never blocks the
    #      event loop. NEVER raises -> a recording failure can never break/silence the call. ----
    recorder = _aim_recorder.build(room_name, session_id)
    rec_tenant = ""  # set once identity resolves (the machine writes the session row); used at stop
    try:
        rec_handle = await asyncio.to_thread(recorder.start)
        logger.info("AIM recording handle: status=%s egress=%s",
                    rec_handle.get("status"), rec_handle.get("egress_id", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM recording start failed (call continues unrecorded): %r", exc)

    # ---- hand the WHOLE session to the deterministic CommandMachine in a worker thread ----
    #      (greeting already spoken above, greet-first, before the gate). ----
    def _run_machine() -> object:
        machine = CommandMachine(
            transport,
            recorder=recorder,             # egress recorder (or no-op); machine pauses around PIN spans
            firewall=None,                 # bridge imports the live firewall (PIN 4827, var/pins.json)
            runner=None,                   # delegate.execute -> workforce.run_agent (chat-console path)
            tenant_by_id=_tenant_by_id,    # caller-ID -> registry row already supplies tenant/role
            channel="phone",
        )
        # The machine re-reads identity from caller_id (registry.lookup). For an un-registered admin box,
        # _tenant_by_id falls back to the ADMIN_TENANT so the founder's PIN still gates (single-tenant).
        return machine.run(caller_id, session_id=session_id)

    result = None
    try:
        result = await asyncio.to_thread(_run_machine)
        logger.info("AIM inbound session done outcome=%s actions=%s",
                    getattr(result, "outcome", "?"), getattr(result, "n_actions", 0))
        rec_tenant = getattr(result, "tenant_id", "") or ""
        # Ship the masked session to the JSONL mirror too (legacy/back-compat readers). The PG session
        # row + per-turn rows are already written incrementally by the state machine — the panel read
        # API prefers PG. Best-effort; never blocks hangup.
        try:
            _aim_endpoints._append_session(  # PIN-masked JSONL mirror for /ai-manager/sessions
                _aim_endpoints._sanitize_session(result.to_record(caller_id=_mask(caller_id))))
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIM machine run failed: %r", exc)
    finally:
        # ---- STOP RECORDING + persist the recording handle on the session row (best-effort). The tenant
        #      is whatever identity resolved to; without it (un-authed call) we can't RLS-write, so skip. ----
        try:
            rec_final = await asyncio.to_thread(recorder.stop)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIM recording stop failed: %r", exc)
            rec_final = {}
        try:
            if rec_tenant and rec_final and rec_final.get("status") not in (None, "disabled"):
                _aim_store.set_recording(
                    rec_tenant, session_id,
                    status=rec_final.get("status", ""),
                    egress_id=rec_final.get("egress_id", ""),
                    bucket=rec_final.get("bucket", ""),
                    key=rec_final.get("key", ""),
                    duration_s=int(rec_final.get("duration_s", 0) or 0))
        except Exception:  # noqa: BLE001
            pass
        await _hangup(ctx, room_name)


class _ResilientSarvamSTT(sarvam.STT):
    """VOICEFIX (the LOAD-BEARING fix for inbound silence): the stock Sarvam plugin forces
    `max_retry=0` on the STREAMING path (`_single_attempt_conn_options`, stt.py:567-571), so the
    AgentSession-level `SessionConnectOptions(stt_conn_options=APIConnectOptions(max_retry=6,…))` is
    read but SILENTLY NEUTERED — the first transient WS-connect blip (a DNS resolver race during
    session bring-up) raises `recoverable=False`, livekit tears the session down, and the greeting
    never plays -> total silence. We override that one staticmethod to PRESERVE the caller's
    `max_retry`, so the widened conn_options actually retries the connect (6x / 20s) instead of dying
    on the first attempt. Nothing else about Sarvam is changed (same model/language/key path). This is
    the subclass approach blessed by design/silence-stt.md §7c (NOT a FallbackAdapter, which would
    false-fail on quiet turns). NEVER raises."""

    @staticmethod
    def _single_attempt_conn_options(conn_options: APIConnectOptions) -> APIConnectOptions:
        # Keep the framework's retry budget instead of zeroing it. Guard against an API-shape drift.
        try:
            return APIConnectOptions(
                max_retry=int(getattr(conn_options, "max_retry", 0) or 0),
                retry_interval=float(getattr(conn_options, "retry_interval", 1.0) or 1.0),
                timeout=float(getattr(conn_options, "timeout", 20.0) or 20.0),
            )
        except Exception:  # noqa: BLE001 — never break STT construction
            return conn_options


def _make_sarvam_stt():
    """One resilient Sarvam STT instance with a rotated key (identical config to the earner, except
    the retry-budget un-neutering above so a transient connect blip self-heals instead of going silent)."""
    return _ResilientSarvamSTT(
        api_key=_next_sarvam_key(),
        language=os.getenv("SARVAM_STT_LANG", "unknown"),   # code-mix Hinglish (do NOT force hi-IN)
        model=os.getenv("SARVAM_STT_MODEL", "saarika:v2.5"),
    )


def _build_stt(vad=None):  # noqa: ARG001 — vad kept for call-site stability; unused (single STT)
    """VOICEFIX: STT, faithful to the proven outbound earner (single Sarvam STT, 96 live calls).

    Root cause of inbound silence (2026-06-11 17:16): the Sarvam streaming WS connect lost a transient
    DNS resolver race (_resolve_host CancelledError -> TimeoutError -> APIConnectionError). The raw
    `_stt_pump` task had ZERO tolerance (the inbound session ran with NO widened connect retry), so the
    WHOLE job process exited BEFORE the greeting was heard -> total silence.

    Fix (the real lever, design/silence-stt.md §7): a layered defence —
      (a) `/etc/hosts` pins api.sarvam.ai (removes the exact `_resolve_host` call that threw);
      (b) Silero VAD is loaded in `prewarm` (off the call path) so session bring-up doesn't starve
          the resolver thread;
      (c) the STT here is `_ResilientSarvamSTT`, which OVERRIDES the plugin's `max_retry=0` forcing so
          the AgentSession-level `SessionConnectOptions(stt_conn_options=APIConnectOptions(max_retry=6,
          retry_interval=1.0, timeout=20))` ACTUALLY retries the connect up to 6x instead of being
          silently neutered. A `session.on("error")` handler logs/contains any residual hiccup and
          `close_on_disconnect=False` keeps the session alive so the greeting always plays.
    We deliberately do NOT use a FallbackAdapter: it treats a quiet turn (no event within
    attempt_timeout) as a failure and would prematurely fail over / alter transcription. A single
    resilient Sarvam STT — config-identical to the earner — is what is proven to work. NEVER raises.
    """
    return _make_sarvam_stt()


def _build_tts():
    """ElevenLabs flash TTS with agent.py's realtime-warm voice settings (style=0, speed nudge)."""
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


def _tenant_by_id(tid: str) -> dict:
    """Supply the tenant_dict the machine carries into delegate.execute. Pull the AI-Manager profile if
    present; default the founder to admin so the full operate set is permitted by voice. NEVER raises."""
    try:
        prof = _aim_store.get_profile(tid) or {}
    except Exception:  # noqa: BLE001
        prof = {}
    role = prof.get("role") or ("admin" if tid == ADMIN_TENANT else "manager")
    return {"tenant_id": tid, "role": role, "is_admin": role == "admin"}


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
            prewarm_fnc=prewarm,                                     # VOICEFIX: warm Silero VAD off the call path
            agent_name=AGENT_NAME,                                   # "manager" — dispatch routes the DID here
            port=int(os.getenv("AIM_AGENT_HTTP_PORT", "8091")),     # SEPARATE from agent.py's 8090
        )
    )


if __name__ == "__main__":
    main()
