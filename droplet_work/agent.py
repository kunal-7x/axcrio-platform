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
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli
# A3: booking voice-tool (gated). function_tool/RunContext imported guarded so an
# older livekit (without them) can NEVER stop the earner from importing — the tool
# is only ever attached when BOTH KERNEL_OUTBOUND=1 and BOOKING_TOOL_ENABLED=1.
try:
    from livekit.agents import RunContext as _LkRunContext  # type: ignore
    from livekit.agents import function_tool as _lk_function_tool  # type: ignore
except Exception:  # noqa: BLE001
    _LkRunContext = None  # type: ignore
    _lk_function_tool = None  # type: ignore
from livekit.plugins import elevenlabs, groq, sarvam, silero
from livekit.plugins.elevenlabs import VoiceSettings

# FREEZE-FIX (FF1): multi-key LLM failover. FallbackAdapter lets a rate-limited Groq key
# fail over to the next one INSTANTLY instead of dead-air-ing the call — the exact root
# cause of the 2026-06-23 booking freeze (one key hit Groq's 12K-TPM free-tier limit
# mid-call; all 4 retries 429'd; the agent went silent). Guarded so an older livekit
# without it can NEVER stop the earner from importing (we degrade to single-key).
try:
    from livekit.agents.llm import FallbackAdapter as _LkLLMFallback  # type: ignore
except Exception:  # noqa: BLE001
    _LkLLMFallback = None  # type: ignore

# TTS failover (Bulbul primary -> ElevenLabs safety net) so an India-hosted-TTS hiccup can't silence a call.
try:
    from livekit.agents.tts import FallbackAdapter as _LkTTSFallback  # type: ignore
except Exception:  # noqa: BLE001
    _LkTTSFallback = None  # type: ignore

# CEREBRAS PRIMARY (CB1): the OpenAI-compatible plugin lets us run the hot-path LLM on Cerebras
# (Llama-4-Scout, far faster + real throughput vs Groq's free-tier 429 storm) with Groq kept as the
# automatic fallback. GUARDED import so a build without the plugin can NEVER stop the agent importing
# — absent => Cerebras simply isn't offered and we run Groq exactly as before.
try:
    from livekit.plugins import openai as _lk_openai  # type: ignore
except Exception:  # noqa: BLE001
    _lk_openai = None  # type: ignore

import memory as mem
from prompt import SYSTEM_PROMPT, GODREJ_FIELDS, build_system_prompt, _gender_of

try:  # additive multi-vertical/persona/language layer — pure, default-OFF, byte-identical when off
    import verticals as _verticals
except Exception:  # noqa: BLE001 — its absence must never break the agent
    _verticals = None

# P2: per-turn language auto-detect + mirror (cheap heuristic; never breaks a call).
try:
    import langdetect as ld
except Exception:  # noqa: BLE001 — agent must run even if the module is missing
    ld = None

# W-INT-OUTBOUND (A4): the OFF-is-identity kernel adapter. KERNEL_OUTBOUND defaults
# OFF -> every helper short-circuits to the legacy-equivalent and this earner is
# BYTE-IDENTICAL to today. Imported fully-guarded: a kernel import bug can NEVER
# stop the earner (the OFF path doesn't even need this module). When None, all four
# seam points below fall through to the unchanged legacy code.
try:
    import voice_kernel.integrations.outbound as _vk
except Exception as _vk_exc:  # noqa: BLE001 — earner must run even if the kernel is absent
    _vk = None
    logging.getLogger("famit-agent").warning("voice_kernel adapter unavailable -> legacy only: %r", _vk_exc)

load_dotenv("/opt/famit-agent/.env")
load_dotenv(".env")

logger = logging.getLogger("famit-agent")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "capsy")
VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))
CAMPAIGN_DIR = Path(os.getenv("CAMPAIGN_DIR", str(VAR / "campaigns")))


def _voice_cfg(name: str, default: str = "") -> str:
    """Read a super-admin-managed agent setting/key from VAR/voice_keys.json (shared /data store the
    panel writes). '' / default if absent/unreadable. Lets STT provider + keys be set from the panel
    WITHOUT touching .env.deploy. NEVER raises into a call."""
    try:
        import json as _json
        p = VAR / "voice_keys.json"
        if not p.exists():
            return default
        d = _json.loads(p.read_text(encoding="utf-8")) or {}
        v = d.get(name)
        return str(v).strip() if v not in (None, "") else default
    except Exception:
        return default


# ── RE-INTRO STRIPPER ─────────────────────────────────────────────────────────────────────────────
# Some LLMs (notably Sarvam-30b) reflexively re-say "Namaste / Main Priya bol rahi hoon" at the START
# of EVERY reply, even mid-call — robotic on a phone call and impossible to fully prompt away. This
# deterministically strips a LEADING self-introduction from the agent's spoken text AFTER the opener
# (the opener's intro is intentional and untouched). Model-agnostic (a no-op for models that don't do
# it). Gated by REINTRO_STRIP=1 (default on). Never returns empty (falls back to the original).
import re as _re  # noqa: E402

# Markdown chars a voice line must never contain (TTS would speak/garble them).
_MD = _re.compile(r"[*_`#>]+")
# A leading speaker label the model emits from a script-style brain: "Riya:", "**Riya:**".
_LABEL = _re.compile(r"^\s*\**\s*[A-Za-z][A-Za-z .]{0,18}:\s*", _re.IGNORECASE)
# The model starting to WRITE A SCRIPT (a second/next speaker turn) — cut everything from here.
_NEXT_TURN = _re.compile(
    r"(?:\n|।|\.)\s*\**\s*(?:customer|grahak|graahak|user|caller|client|agent|priya|riya|you|me|"
    r"ग्राहक|कस्टमर|ग्राहक\s*जी)\s*\**\s*:", _re.IGNORECASE)
# Leading self-introduction / greeting (NAME-AGNOSTIC: Riya/Priya/anything).
_GREET = [
    _re.compile(r"^[\s,.!।]*namaste[\s,.!।जी]*", _re.IGNORECASE),
    _re.compile(r"^[\s,.!।]*main\s+[a-z]+\s+(?:bol\s+rah[ei]\s+hoon|hoon)[^.!?।]*[.!?।]\s*", _re.IGNORECASE),
    _re.compile(r"^[\s,.!।]*[a-z]+\s+bol\s+rah[ei]\s+hoon[^.!?।]*[.!?।]\s*", _re.IGNORECASE),
    _re.compile(r"^[\s,.!।]*main\s+famit[^.!?।]*[.!?।]\s*", _re.IGNORECASE),
]

# Gender-neutral re-steers used when the agent is about to SPEAK a near-verbatim repeat of a recent line
# (Sarvam loops on unclear input; it ignores the brain's anti-repeat rule, so this enforces it in code).
_ANTI_REPEAT_LINES = [
    "माफ़ कीजिए, शायद आवाज़ ठीक से नहीं आई — आप क्या जानना चाहेंगे?",
    "जी बताइए, किस बारे में पूछना चाहेंगे — price, location या कुछ और?",
    "कोई बात नहीं, ज़रा अपनी बात दोबारा बता दीजिए।",
]

# Robotic preamble Sarvam prepends ("मैं बता रही हूँ कि …") — pure filler with no info, makes it sound
# unnatural. Strip from the START so the reply opens on real content (the brain bans it, but Sarvam ignores
# rules). Deliberately does NOT touch "मैं समझ रही हूँ" (a legit acknowledgement of a caller's concern).
_PREAMBLE = _re.compile(
    r"^[\s,।:-]*(?:मैं\s+(?:आपको\s+)?बता\s+रह[ीि]\s+हूँ\s+कि|मैं\s+(?:आपको\s+)?बता\s+रहा\s+हूँ\s+कि|"
    r"मैं\s+आपको\s+बता(?:ती|ता)\s+हूँ\s+कि|main\s+(?:aapko\s+)?bata\s+rah[ie]\s+(?:hoon|hu|hoo)\s+ki|"
    r"i\s*'?\s*am\s+telling\s+you\s+that|let\s+me\s+tell\s+you\s+that)[\s,।:-]*", _re.IGNORECASE)


# ── SCRIPT-SAFETY (added): strip leaked tool-call syntax + fill template placeholders ──
# (1) Groq llama-3.3-70b sometimes emits a TEXTUAL function call
#     (`<function=book_site_visit>{…}</function>`) instead of a native tool call; with no booking
#     tool attached it would otherwise be SPOKEN. _strip_tool_calls removes it in the TTS path.
# (2) Vendor raw_scripts / persona templates carry `{{lead_name}}`-style placeholders; if not
#     filled the agent SPEAKS a literal "{lead_name}". _fill_lead_placeholders substitutes the
#     real lead name (graceful "आप" when unknown) + company/product/agent_name. Both NEVER raise.
_TOOLCALL_RE = _re.compile(r"<function[^>]*>.*?</function>", _re.S | _re.I)
_TOOLCALL_TAG_RE = _re.compile(r"</?function[^>]*>", _re.I)
_TOOLCALL_XML_RE = _re.compile(r"<tool_call>.*?</tool_call>", _re.S | _re.I)
_SPECIAL_TOK_RE = _re.compile(r"<\|[^|>]*\|>")


def _strip_tool_calls(text: str) -> str:
    """Remove any tool-call/function-call syntax a model leaked into spoken text. Never raises."""
    if not text:
        return text or ""
    try:
        t = _TOOLCALL_RE.sub(" ", text)
        t = _TOOLCALL_XML_RE.sub(" ", t)
        t = _TOOLCALL_TAG_RE.sub(" ", t)
        t = _SPECIAL_TOK_RE.sub(" ", t)
        t = _re.sub(r"[ \t]{2,}", " ", t).strip()
        return t or (text or "")
    except Exception:  # noqa: BLE001
        return text or ""


_PLACEHOLDER_RE = _re.compile(
    r"\{\{?\s*(lead_name|name|agent_name|company|company_name|product|product_name)\s*\}?\}")
_NAME_HON_RE = _re.compile(r"\{\{?\s*(?:lead_name|name)\s*\}?\}\s*(?:जी|ji\b)", _re.I)


def _fill_lead_placeholders(text: str, fields: dict, lead_name: str = "") -> str:
    """Substitute {lead_name}/{{lead_name}} (+ agent_name/company/product) placeholders that leak
    verbatim from vendor raw_scripts / persona templates with the real values. A MISSING lead name
    collapses '{lead_name} जी' -> 'आप' so the agent NEVER speaks a literal placeholder.
    Never raises (returns the input unchanged on any error)."""
    if not text:
        return text or ""
    try:
        f = fields if isinstance(fields, dict) else {}
        name = (lead_name or str(f.get("lead_name") or "")).strip()
        vals = {
            "lead_name": name, "name": name,
            "agent_name": str(f.get("agent_name") or "").strip(),
            "company": str(f.get("company_name") or "").strip(),
            "company_name": str(f.get("company_name") or "").strip(),
            "product": str(f.get("product_name") or "").strip(),
            "product_name": str(f.get("product_name") or "").strip(),
        }
        if not name:
            text = _NAME_HON_RE.sub("आप", text)   # "{lead_name} जी" -> "आप" (avoid "आप जी")
        text = _PLACEHOLDER_RE.sub(
            lambda m: vals.get(m.group(1), "") or ("आप" if m.group(1) in ("lead_name", "name") else ""),
            text)
        text = _re.sub(r"[ \t]{2,}", " ", text)
        return text
    except Exception:  # noqa: BLE001
        return text or ""


def _trim_truncated(text: str) -> str:
    """If a reply looks TRUNCATED (long AND doesn't end on sentence punctuation — the
    max_tokens mid-word cut that sounds like garbage/'stuck' at the end), trim back to the
    last complete sentence so TTS never speaks a half-word. SHORT replies (<150 chars) are
    left untouched so a brief question with a missing '?' still goes through. Never raises."""
    try:
        t = (text or "").rstrip()
        if len(t) < 150 or (t and t[-1] in ".?!।…"):
            return text or ""
        last = -1
        for mm in _re.finditer(r"[.?!।…]", t):
            last = mm.end()
        return t[:last] if last >= 40 else (text or "")
    except Exception:  # noqa: BLE001
        return text or ""


def _clean_reply(s: str, strip_intro: bool = True) -> str:
    """Make an LLM reply safe to SPEAK: cut any scripted next-turn, drop markdown, and (post-opener)
    strip a leading speaker-label + self-introduction. Robust to a script-style campaign brain
    (e.g. Sarvam emitting '**Riya:** Namaste! Main Riya bol rahi hoon ...'). Never returns empty."""
    out = s
    m = _NEXT_TURN.search(out)
    if m and m.start() > 0:
        out = out[:m.start()]              # the model began a fake dialogue — keep only the first line
    out = _MD.sub("", out)                 # drop markdown so TTS doesn't speak it
    out = _PREAMBLE.sub("", out)           # drop the robotic "मैं बता रही हूँ कि" preamble (Sarvam tic)
    if strip_intro:
        for _ in range(2):                 # 2 passes: "**Riya:** Namaste! Main Riya bol rahi hoon ..."
            out = _LABEL.sub("", out, count=1)
            for g in _GREET:
                out = g.sub("", out, count=1)
            out = _PREAMBLE.sub("", out)   # ...and again if a greeting preceded the preamble
    out = _strip_tool_calls(out)           # drop any leaked <function=…>/<tool_call> before TTS
    out = _trim_truncated(out)             # drop a cut-off trailing clause (max_tokens mid-word)
    out = out.strip(" ,.!।\t\n-")
    return out if out.strip() else _MD.sub("", s).strip()


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
# A6: 429 / quota cooling. When a key returns a 429 (rate-limit/quota), mark it
# "cooling" until now+GROQ_COOL_SECONDS; _next_groq_key SKIPS cooling keys so the
# round-robin stops handing out an exhausted key (the live TTFT-spike cause). Pure
# brain/logic — NOTHING in the TTS/voice path. Safe no-op on a single key: if every
# key is cooling we still return one (never starve a call). Default cool window 60s.
_GROQ_COOLING: dict[str, float] = {}  # masked-or-raw key -> epoch when it un-cools
_GROQ_COOL_SECONDS = float(os.getenv("GROQ_COOL_SECONDS", "60") or 60)

def _mask_key(k: str) -> str:
    if not k:
        return "<none>"
    return (k[:6] + "…" + k[-4:]) if len(k) > 12 else "<short>"

def mark_groq_key_cooling(key: str, *, seconds: float | None = None) -> None:
    """Mark a Groq key as cooling after a 429/quota error. Thread-safe; never raises.
    The key is skipped by _next_groq_key until the cool window elapses."""
    try:
        if not key:
            return
        import time as _t
        secs = _GROQ_COOL_SECONDS if seconds is None else float(seconds)
        with _GROQ_LOCK:
            _GROQ_COOLING[key] = _t.time() + max(1.0, secs)
        logging.getLogger("famit-agent").warning(
            "groq key cooling %s for %.0fs (429/quota)", _mask_key(key), max(1.0, secs))
    except Exception:  # noqa: BLE001 — cooling bookkeeping must never break a call
        pass


# ── Groq TOKEN BUDGET (panel-managed, proactive rotation) ──────────────────────
# Super-admin manages extra fallback keys + a per-key daily token LIMIT in VAR/groq_budget.json
# (CONFIG); this worker writes today's per-key token USAGE to VAR/groq_budget_status.json after each
# call and PROACTIVELY skips a key whose remaining daily budget is below the low threshold — the fix
# for the dead-air-on-quota glitch (a key hit its ~100k-tok/day free-tier wall mid-campaign). Every
# helper is best-effort + FAIL-OPEN: a missing/garbage file ⇒ behaves EXACTLY like the env-only path
# before this change (treats keys as healthy, never starves a call).
import hashlib as _hashlib  # noqa: E402

_GROQ_BUDGET_FILE = VAR / "groq_budget.json"
_GROQ_BUDGET_STATUS_FILE = VAR / "groq_budget_status.json"
_GROQ_TPD_DEFAULT = int(os.getenv("GROQ_TPD_DEFAULT", "100000") or 100000)
_GROQ_LOW_DEFAULT = int(os.getenv("GROQ_LOW_THRESHOLD", "10000") or 10000)
_groq_cfg_cache: dict = {"at": 0.0, "cfg": None}
_groq_status_cache: dict = {"at": 0.0, "data": None}
_GROQ_RR_INDEX = 0

def _groq_fp(key: str) -> str:
    """Stable 12-char fingerprint — IDENTICAL to caller.py _groq_fingerprint so the panel maps usage
    to keys. Never raises."""
    try:
        return _hashlib.sha256((key or "").strip().encode("utf-8")).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return ""

def _groq_utc_day() -> str:
    try:
        import datetime as _dt
        return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return ""

def _groq_budget_cfg() -> dict:
    """VAR/groq_budget.json (cached ~30s). {} on any error. Never raises."""
    import time as _t
    now = _t.time()
    if _groq_cfg_cache["cfg"] is not None and now - _groq_cfg_cache["at"] < 30:
        return _groq_cfg_cache["cfg"]
    cfg: dict = {}
    try:
        if _GROQ_BUDGET_FILE.exists():
            import json as _json
            d = _json.loads(_GROQ_BUDGET_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                cfg = d
    except Exception:  # noqa: BLE001
        cfg = {}
    _groq_cfg_cache["cfg"] = cfg
    _groq_cfg_cache["at"] = now
    return cfg

def _groq_budget_status_read() -> dict:
    """VAR/groq_budget_status.json (cached ~10s). {} on any error. Never raises."""
    import time as _t
    now = _t.time()
    if _groq_status_cache["data"] is not None and now - _groq_status_cache["at"] < 10:
        return _groq_status_cache["data"]
    data: dict = {}
    try:
        if _GROQ_BUDGET_STATUS_FILE.exists():
            import json as _json
            d = _json.loads(_GROQ_BUDGET_STATUS_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                data = d
    except Exception:  # noqa: BLE001
        data = {}
    _groq_status_cache["data"] = data
    _groq_status_cache["at"] = now
    return data

def _store_groq_keys() -> list[str]:
    """Panel-added Groq fallback keys (VAR/groq_budget.json keys[]) + the legacy single voice_keys.json
    groq_api_key. Raw keys, deduped, order-stable. Never raises."""
    out: list[str] = []
    try:
        for k in (_groq_budget_cfg().get("keys") or []):
            if isinstance(k, dict):
                v = str(k.get("key", "") or "").strip()
                if v and v not in out:
                    out.append(v)
    except Exception:  # noqa: BLE001
        pass
    try:
        v = _voice_cfg("groq_api_key", "")
        if v and v not in out:
            out.append(v)
    except Exception:  # noqa: BLE001
        pass
    return out

def _all_groq_keys() -> list[str]:
    """env keys (_GROQ_KEYS) + panel store keys, deduped, env-first. The live pool _next_groq_key /
    _build_call_llm rotate over. When no store keys exist this == _GROQ_KEYS (byte-identical to old)."""
    keys = list(_GROQ_KEYS)
    for k in _store_groq_keys():
        if k not in keys:
            keys.append(k)
    return keys

def _key_over_budget(key: str) -> bool:
    """True iff this key's remaining daily Groq token budget is below the low threshold. FAIL-OPEN:
    any error / missing snapshot / other-day snapshot ⇒ False (healthy), so a missing budget file can
    never starve a call. Pure read of the worker-written snapshot."""
    try:
        cfg = _groq_budget_cfg()
        low = int(cfg.get("low_threshold") or _GROQ_LOW_DEFAULT)
        default_lim = int(cfg.get("tpd_limit_default") or _GROQ_TPD_DEFAULT)
        fp = _groq_fp(key)
        lim = default_lim
        for k in (cfg.get("keys") or []):
            if isinstance(k, dict) and _groq_fp(str(k.get("key", ""))) == fp:
                lim = int(k.get("tpd_limit") or default_lim)
                break
        st = _groq_budget_status_read()
        if st.get("date") != _groq_utc_day():
            return False
        used = int(((st.get("keys") or {}).get(fp) or {}).get("tokens", 0) or 0)
        return (lim - used) < low
    except Exception:  # noqa: BLE001
        return False

def _record_groq_call_tokens(key: str, in_tok: int, out_tok: int) -> None:
    """Add this call's Groq tokens to today's per-key usage snapshot, flock-guarded so concurrent
    worker processes don't lose updates. Date-stamped (new UTC day resets). Never raises — pure
    bookkeeping that must NEVER affect a call."""
    try:
        total = int(in_tok or 0) + int(out_tok or 0)
        if total <= 0 or not key:
            return
        import json as _json, time as _t
        try:
            import fcntl as _fcntl
        except Exception:  # noqa: BLE001 — non-unix: degrade to lock-free write
            _fcntl = None
        fp = _groq_fp(key)
        day = _groq_utc_day()
        VAR.mkdir(parents=True, exist_ok=True)
        with open(_GROQ_BUDGET_STATUS_FILE, "a+", encoding="utf-8") as fh:
            if _fcntl is not None:
                try:
                    _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
                except Exception:  # noqa: BLE001
                    pass
            fh.seek(0)
            raw = fh.read()
            try:
                data = _json.loads(raw) if raw.strip() else {}
            except Exception:  # noqa: BLE001
                data = {}
            if not isinstance(data, dict) or data.get("date") != day:
                data = {"date": day, "keys": {}}
            keys = data.setdefault("keys", {})
            row = keys.setdefault(fp, {"tokens": 0, "calls": 0, "last_used_ms": 0, "last_429_ms": 0})
            row["tokens"] = int(row.get("tokens", 0) or 0) + total
            row["calls"] = int(row.get("calls", 0) or 0) + 1
            row["last_used_ms"] = int(_t.time() * 1000)
            data["updated_ms"] = int(_t.time() * 1000)
            fh.seek(0)
            fh.truncate()
            fh.write(_json.dumps(data, ensure_ascii=False))
            fh.flush()
        # invalidate our own status cache so a subsequent _key_over_budget sees the new total.
        _groq_status_cache["data"] = None
    except Exception:  # noqa: BLE001
        pass


def _next_groq_key() -> str:
    """Round-robin the next Groq API key (thread-safe), SKIPPING keys that are cooling from a recent
    429/quota (A6) OR proactively over their daily token budget (panel-managed). Rotates over env keys
    PLUS panel-added store keys. Falls back to the single env GROQ_API_KEY. If every key is skipped it
    still returns one (never starve a live call). Never raises — any error degrades to the env key."""
    global _GROQ_RR_INDEX
    try:
        keys = _all_groq_keys()
        if keys:
            import time as _t
            now = _t.time()
            with _GROQ_LOCK:
                n = len(keys)
                # pass 1: a key that is neither cooling nor over its daily token budget.
                for _ in range(n):
                    k = keys[_GROQ_RR_INDEX % n]
                    _GROQ_RR_INDEX = (_GROQ_RR_INDEX + 1) % n
                    cool_until = _GROQ_COOLING.get(k, 0.0)
                    if cool_until and cool_until > now:
                        continue
                    if _key_over_budget(k):
                        continue
                    if cool_until:
                        _GROQ_COOLING.pop(k, None)
                    return k
                # pass 2: budget snapshot may be stale — honor only cooling, ignore budget.
                for _ in range(n):
                    k = keys[_GROQ_RR_INDEX % n]
                    _GROQ_RR_INDEX = (_GROQ_RR_INDEX + 1) % n
                    cool_until = _GROQ_COOLING.get(k, 0.0)
                    if cool_until and cool_until > now:
                        continue
                    return k
                # everything cooling: return the next anyway (don't starve the call).
                k = keys[_GROQ_RR_INDEX % n]
                _GROQ_RR_INDEX = (_GROQ_RR_INDEX + 1) % n
                return k
    except Exception:  # noqa: BLE001 — never break a call over key selection
        pass
    return (os.getenv("GROQ_API_KEY") or "").strip()


# ── FF2: SambaNova final real-fallback LLM ───────────────────────────────────────────────────────
# When EVERY Groq key is capped — the recurring free-tier 100k-tokens/DAY wall that dead-airs calls —
# the conversation LLM falls over to SambaNova Llama-3.3-70B: a SEPARATE provider with its OWN quota,
# OpenAI-compatible. The key comes from the panel's provider-key store (Super Admin → Services →
# SambaNova) via the shared SAMBANOVA_POOL (blended with any SAMBANOVA_API_KEY env). The model is
# Meta-Llama-3.3-70B-Instruct by default, overridable via voice_keys.json `sambanova_model` or the
# SAMBANOVA_MODEL env. Fully guarded + dormant-safe: no key / no openai plugin => the chain is
# Groq-only, byte-identical to before. Never raises.
def _samba_key() -> str:
    """Least-used SambaNova key from the shared pool (panel store + env). '' when none."""
    try:
        from llm_router import SAMBANOVA_POOL  # noqa: PLC0415
        if SAMBANOVA_POOL is not None:
            picked = SAMBANOVA_POOL.pick()
            if picked and (picked.get("key") or "").strip():
                return picked["key"].strip()
    except Exception:  # noqa: BLE001
        pass
    return (os.getenv("SAMBANOVA_API_KEY", "") or "").strip()


def _mk_samba_llm(temp: float):
    """Build the SambaNova fallback LLM member, or None if unavailable. Never raises."""
    if _lk_openai is None:
        return None
    key = _samba_key()
    if not key:
        return None
    model = (_voice_cfg("sambanova_model", "") or os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct")).strip()
    try:
        return _lk_openai.LLM(
            model=model, api_key=key,
            base_url=os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1"),
            temperature=temp,
        )
    except Exception as exc:  # noqa: BLE001 — bad key/plugin => Groq-only, never break the earner
        logger.warning("FF2 SambaNova fallback LLM build failed -> Groq-only: %r", exc)
        return None


# ── FF3: Sarvam-30b (hosted India API) as a selectable PRIMARY LLM ─────────────────────────────────
# Sarvam's hosted Chat Completions API (api.sarvam.ai/v1) — India-hosted, no daily cap, OpenAI-compatible.
# Benchmarked fastest+steadiest for Hinglish telecalling (p50 ~180ms, 0 errors under load). Key from
# voice_keys.json `sarvam_llm_api_key` (falls back to `sarvam_api_key` / SARVAM_API_KEY env); model
# `sarvam-30b` (sarvam-m is deprecated on the hosted API). CRITICAL: disable Sarvam's "thinking" mode
# (default reasoning_effort="medium") by sending reasoning_effort:null via extra_body — else every turn
# reasons first and latency explodes. Selected as primary when llm_provider=="sarvam"; Groq stays fallback.
def _sarvam_key() -> str:
    return (_voice_cfg("sarvam_llm_api_key", "") or _voice_cfg("sarvam_api_key", "")
            or os.getenv("SARVAM_LLM_API_KEY", "") or os.getenv("SARVAM_API_KEY", "")).strip()


def _mk_sarvam_llm(temp: float):
    """Build the Sarvam-30b LLM (thinking disabled), or None. Never raises."""
    if _lk_openai is None:
        return None
    key = _sarvam_key()
    if not key:
        return None
    model = (_voice_cfg("sarvam_model", "") or os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")).strip()
    try:
        s = _lk_openai.LLM(
            model=model, api_key=key,
            base_url=os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1"),
            temperature=float(os.getenv("SARVAM_LLM_TEMPERATURE", "0.2") or 0.2),
            max_completion_tokens=int(os.getenv("SARVAM_MAX_TOKENS", "140") or 140),  # HARD cap: kills the 500-tok ramble
            extra_body={"reasoning_effort": None},   # disable Sarvam thinking-mode (else slow)
        )
        try:
            s._strict_tool_schema = False  # noqa: SLF001 — forgiving tool calls
        except Exception:  # noqa: BLE001
            pass
        return s
    except Exception as exc:  # noqa: BLE001 — never break the earner
        logger.warning("FF3 Sarvam LLM build failed -> Groq: %r", exc)
        return None


def _build_call_llm(primary_key: str, model_override: str = "", provider: str = ""):
    """FREEZE-FIX (FF1): build the hot-path conversation LLM with MULTI-KEY FAILOVER.

    Root cause of the 2026-06-23 booking freeze: the call's LLM was bound to ONE Groq key;
    when that key hit Groq's 12K-TPM free-tier limit mid-call, all 4 retries 429'd and the
    agent went DEAD-AIR (it never answered the caller's agreed slot). We have several keys,
    each with its OWN quota — so we wrap one groq.LLM PER key in a FallbackAdapter: a
    rate-limited key now fails over to the next one INSTANTLY instead of freezing the call.

    Starts on `primary_key` (the round-robin pick, so concurrent calls still spread load),
    then fails over to the remaining keys. GROQ_LLM_FALLBACK=0 reverts to the single-key
    path (byte-identical to before). Never raises: any wiring problem degrades to a plain
    single-key groq.LLM, exactly as today — the earner can never be broken by this."""
    # Per-campaign model override (Run Campaign → Advanced → LLM model) wins over the env default;
    # empty/unset => env default (byte-identical to today). A bad value still fails over to the
    # GROQ_FALLBACK_MODEL member below, so the earner can't dead-air on a typo.
    model = (model_override or "").strip() or os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    temp = float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3"))
    max_tok = int(os.getenv("GROQ_MAX_TOKENS", "90"))

    def _one(key: str, model_name: str = ""):
        return groq.LLM(model=model_name or model, api_key=key,
                        temperature=temp, max_completion_tokens=max_tok)

    # CB1: Cerebras as the PRIMARY hot-path LLM when CEREBRAS_API_KEY is set (OpenAI-compatible).
    # Llama-4-Scout on Cerebras is faster + has real throughput, so it removes the Groq free-tier
    # 429 storm that was causing the latency spikes + choppy audio. Groq stays as the fallback
    # member(s) below. Dormant-safe: no key (or no openai plugin) => Groq exactly as before.
    _cerebras = None
    _ck = (os.getenv("CEREBRAS_API_KEY") or "").strip()
    _cb_model = os.getenv("CEREBRAS_LLM_MODEL", "meta-llama/Llama-4-Scout-17B-16E-Instruct")
    if _ck and _lk_openai is not None:
        try:
            _cb_kwargs: dict = {}
            # gpt-oss is a REASONING model — without a LOW effort it reasons on every turn (latency
            # explodes, exactly like Sarvam's thinking-mode). Send reasoning_effort via extra_body for
            # gpt-oss (or whenever CEREBRAS_REASONING_EFFORT is set); plain Llama models ignore it.
            _cb_effort = os.getenv("CEREBRAS_REASONING_EFFORT",
                                   "low" if "gpt-oss" in _cb_model.lower() else "")
            if _cb_effort:
                _cb_kwargs["extra_body"] = {"reasoning_effort": _cb_effort}
            _cb_maxtok = os.getenv("CEREBRAS_MAX_TOKENS", "")
            if _cb_maxtok:
                _cb_kwargs["max_completion_tokens"] = int(_cb_maxtok)
            _cerebras = _lk_openai.LLM(
                model=_cb_model,
                api_key=_ck,
                base_url=os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"),
                temperature=temp,
                **_cb_kwargs,
            )
            try:
                _cerebras._strict_tool_schema = False  # noqa: SLF001 — forgiving tool calls
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001 — bad key/plugin => fall back to Groq, never break
            logger.warning("CB1 Cerebras LLM build failed -> Groq: %r", exc)
            _cerebras = None

    _samba = _mk_samba_llm(temp)    # SambaNova-70B (own quota) — fallback OR primary
    _sarvam = _mk_sarvam_llm(temp)  # Sarvam-30b (India hosted, no cap) — primary when selected
    # Which provider LEADS the chain? GLOBAL operator setting (voice-config `llm_provider`) WINS
    # fleet-wide — so the founder can force one model on every campaign regardless of a stale
    # per-campaign `llm_provider` field (the Run picker bakes "groq" in by default). Order: global
    # voice-config > per-campaign pick > env (LLM_PROVIDER) > default Groq. "sarvam"/"sambanova" run
    # PRIMARY with Groq demoted to fallback. (Clear the global to hand control back to per-campaign.)
    want = (_voice_cfg("llm_provider", "") or provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
    sarvam_primary = (want == "sarvam" and _sarvam is not None)
    samba_primary = (want == "sambanova" and _samba is not None)
    try:
        use_fb = os.getenv("GROQ_LLM_FALLBACK", "1") not in ("0", "false", "False")
        keys = [k for k in _all_groq_keys() if k]   # env + panel-added store keys
        # Build a FallbackAdapter when a hosted primary leads, OR Cerebras is primary, OR a SambaNova
        # fallback exists, OR there are >=2 Groq keys.
        if _LkLLMFallback is not None and (sarvam_primary or samba_primary or _cerebras is not None or _samba is not None or (use_fb and len(keys) > 1)):
            ordered = ([primary_key] + [k for k in keys if k != primary_key]) if keys else []
            members = []
            if sarvam_primary:
                members.append(_sarvam)                         # Sarvam-30b PRIMARY (founder-selected)
            elif samba_primary:
                members.append(_samba)                          # SambaNova-70B PRIMARY
            if _cerebras is not None:
                members.append(_cerebras)                       # Cerebras Scout (primary unless Sarvam/Samba leads)
            # GROQ_IN_CHAIN=0 removes Groq from the chain entirely (founder wants pure Sarvam, no Groq
            # fallback). TRADE-OFF: with no Groq/Cerebras/SambaNova left, the chain is Sarvam-ONLY — a
            # Sarvam outage then dead-airs that turn (no failover). That is the explicit cost of removing it.
            _groq_in_chain = os.getenv("GROQ_IN_CHAIN", "1") not in ("0", "false", "False")
            if _groq_in_chain:
                members += [_one(k) for k in ordered]           # Groq keys (primary by default, else failover)
            # OPTIONAL last resort: a separate model (its OWN quota) when everything above is capped.
            fb_model = (os.getenv("GROQ_FALLBACK_MODEL", "") or "").strip()
            if fb_model and ordered and _groq_in_chain:
                members.append(_one(ordered[0], fb_model))
            if _samba is not None and not samba_primary:
                members.append(_samba)                          # SambaNova-70B deeper real fallback
            if members:
                adapter = _LkLLMFallback(
                    members,
                    attempt_timeout=float(os.getenv("GROQ_ATTEMPT_TIMEOUT", "6.0")),
                )
                _fb = (" + fallback " + fb_model) if (fb_model and ordered and _groq_in_chain) else ""
                _sb = " + SambaNova" if (_samba is not None and not samba_primary) else ""
                if sarvam_primary:
                    _sv_name = (_voice_cfg("sarvam_model", "") or os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")).strip() or "sarvam"
                    logger.info("LLM chain: %s (primary) -> %d Groq key(s)%s%s", _sv_name,
                                (len(ordered) if _groq_in_chain else 0), _fb, _sb)
                elif samba_primary:
                    logger.info("LLM chain: SambaNova-70B (primary) -> %d Groq key(s)%s", len(ordered), _fb)
                else:
                    logger.info("LLM chain: %s%d Groq key(s)%s%s",
                                (f"Cerebras {_cb_model} -> " if _cerebras else f"Groq {model} x"), len(ordered), _fb, _sb)
                return adapter
    except Exception as exc:  # noqa: BLE001 — never let failover wiring break the earner
        logger.warning("LLM failover wiring failed -> single: %r", exc)
    # single-LLM path: the founder's hosted pick, else Cerebras, else the legacy Groq key.
    if sarvam_primary:
        return _sarvam
    if samba_primary:
        return _samba
    if _cerebras is not None:
        return _cerebras
    return _one(primary_key)


# ── System Logs reporting (best-effort) ───────────────────────────────────────
# The agent records notable events/errors to the SAME shared /data system-events log that the
# backend's super-admin "System Logs" page + notification bell read — so a booking, a call
# freeze, or an LLM wipeout shows up for the operator (and pushes a Telegram alert). Fully
# guarded + dormant-safe: logging is NEVER allowed to affect a live call.
_LOG_INIT_DONE = False


def _sys_log(level: str, source: str, message: str, *, tenant_id: str = "",
             call_id: str = "", error_type: str = "", context: dict | None = None) -> None:
    global _LOG_INIT_DONE
    try:
        import logging_service as _ls
        if not _LOG_INIT_DONE:
            try:
                # reuse the module-level VAR so the agent + backend default to the IDENTICAL
                # path (FAMIT_VAR) — the backend reads this same file for the System Logs panel.
                _ls.init(str(VAR / "system_events.jsonl"))
            except Exception:  # noqa: BLE001
                pass
            _LOG_INIT_DONE = True
        _ls.record(level, source, message, tenant_id=tenant_id, call_id=call_id,
                   error_type=error_type, context=context or {})
    except Exception:  # noqa: BLE001
        pass


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
    _gk = _next_groq_key()  # A6: capture so a 429 can cool THIS key
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + _gk},
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
                          "\"opt_out\": true ONLY when the caller EXPLICITLY demands to be removed / "
                          "never called again — e.g. 'remove my number', 'number hata do', 'dobara "
                          "call mat karna', 'do not call', 'मुझे call मत करना'. A polite goodbye, "
                          "'thank you', 'bye', 'rakhta hoon', 'not interested', 'abhi nahi'/'baad mein', "
                          "'busy', 'sochkar batata hoon', or just hanging up is NOT opt_out. When in "
                          "any doubt, false, "
                          "\"callback_at\": if the caller asked to be called back at a specific time, "
                          "resolve it to an ABSOLUTE IST datetime in ISO format "
                          "YYYY-MM-DDTHH:MM:SS relative to the current IST time above; else \"\", "
                          "\"callback_raw\": the exact spoken time phrase, else \"\"}.")},
                      {"role": "user", "content": convo},
                  ]},
            timeout=12,
        )
        if getattr(r, "status_code", 200) == 429:
            mark_groq_key_cooling(_gk)
            _sys_log("warning", "llm", "Groq rate-limit (429); rotating key",
                     error_type="rate_limit_429", context={"stage": "summary"})
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


async def _prewarm_groq(key: str, model: str, system_prompt: str) -> None:
    """PRE-WARM (turn-1 latency): fire ONE tiny throwaway completion at call-connect so Groq's
    prompt cache is HOT for this call's (key, model, system-prompt prefix). Turn-1's real LLM call
    then hits the warm cache (~0.4s) instead of paying the ~1.2s cold-prefix cost — the persistent
    "#1 turn slow, #2+ fast" pattern in the per-turn breakdown. Best-effort: never blocks, never raises."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            await cli.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={"model": model, "max_tokens": 1, "temperature": 0,
                      "messages": [{"role": "system", "content": system_prompt},
                                   {"role": "user", "content": "ok"}]})
        logger.info("LLM prewarm sent (model=%s, prompt=%d chars)", model, len(system_prompt))
    except Exception:  # noqa: BLE001 — warmup is best-effort; failure just leaves turn-1 cold
        pass


async def _prewarm_chat(url: str, key: str, model: str, system_prompt: str,
                        extra_body: dict | None = None) -> None:
    """Generic OpenAI-compatible PRE-WARM for the LIVE PRIMARY provider. Sarvam supports prompt
    caching, so firing one tiny completion with the FULL system prompt at call-connect warms its
    server-side prefix cache — turn-1 then hits the warm cache (~0.3s) instead of the ~0.9s cold
    prefix cost (the "#1 slow, #2+ fast" pattern). The old _prewarm_groq only warmed Groq, which
    did nothing when Sarvam was primary. Best-effort: never blocks, never raises."""
    try:
        body: dict = {"model": model, "max_tokens": 1, "temperature": 0,
                      "messages": [{"role": "system", "content": system_prompt},
                                   {"role": "user", "content": "ok"}]}
        if extra_body:
            body.update(extra_body)
        async with httpx.AsyncClient(timeout=8.0) as cli:
            await cli.post(url, headers={"Authorization": "Bearer " + key}, json=body)
        _host = url.split("//", 1)[-1].split("/", 1)[0]
        logger.info("LLM prewarm sent (host=%s model=%s, prompt=%d chars)", _host, model, len(system_prompt))
    except Exception:  # noqa: BLE001 — warmup is best-effort; failure just leaves turn-1 cold
        pass


async def _prewarm_llm_conn(call_llm, system_prompt: str) -> None:
    """PRE-WARM the LIVE LLM's PLUGIN CONNECTION (not just the server cache) at call-connect, by firing
    one tiny .chat() on the SAME llm object the session uses. This opens the TLS/HTTP2 socket to the
    provider (api.sarvam.ai) AND warms its prompt-prefix cache, so the caller's FIRST real turn is hot
    (~0.3s) instead of paying the ~0.9s cold-connection cost. We stop after the first token and close
    the stream, so it costs ~1 token. Best-effort, runs during the opener; never blocks/raises."""
    try:
        from livekit.agents import llm as _Lllm  # noqa: PLC0415
        cc = _Lllm.ChatContext.empty()
        cc.add_message(role="system", content=system_prompt)
        cc.add_message(role="user", content="ok")
        stream = call_llm.chat(chat_ctx=cc)
        try:
            async for _ in stream:   # first chunk proves the socket + prefix are warm
                break
        finally:
            try:
                await stream.aclose()
            except Exception:  # noqa: BLE001
                pass
        logger.info("LLM prewarm (plugin connection) done")
    except Exception as exc:  # noqa: BLE001 — best-effort; failure just leaves turn-1 cold
        logger.warning("LLM conn prewarm failed (non-fatal): %r", exc)


def _ist_time_of_day() -> dict:
    """REAL current IST time-of-day, for a time-correct (never hardcoded) greeting.

    Returns {"hour": 0-23, "bucket": morning|afternoon|evening,
             "en": "good morning"/..., "hi": ENGLISH greeting hint (kept English on
             purpose — pure-Hindi wishes like सुप्रभात/शुभ रात्रि are BANNED)}.
    The LLM AUTHORS the greeting; this only tells it which part of the day it is so
    the ENGLISH wish "good morning/afternoon/evening" matches reality. The buckets
    are computed in REAL IST (UTC+5:30), so 11:00 IST => 'morning'. Never raises."""
    try:
        now_ist = _datetime_module.datetime.now(
            _datetime_module.timezone(_datetime_module.timedelta(hours=5, minutes=30)))
        h = now_ist.hour
    except Exception:  # noqa: BLE001
        h = 10  # safe daytime default
    # Labels are ENGLISH only — never emit Hindi wishes (सुप्रभात/शुभ रात्रि/नमस्ते).
    if 4 <= h < 12:
        bucket, en, hi = "morning", "good morning", "good morning (subah — say it in ENGLISH)"
    elif 12 <= h < 17:
        bucket, en, hi = "afternoon", "good afternoon", "good afternoon (dopahar — say it in ENGLISH)"
    elif 17 <= h < 21:
        bucket, en, hi = "evening", "good evening", "good evening (shaam — say it in ENGLISH)"
    else:
        # Late night / very early: still greet in clean English, never 'good morning' wrongly.
        bucket, en, hi = "evening", "good evening", "good evening (raat — greet warmly in ENGLISH, not 'good morning')"
    return {"hour": h, "bucket": bucket, "en": en, "hi": hi}


def _first_name(full: str) -> str:
    """The first token of a name, for natural address ('कुणाल कुमार' -> 'कुणाल').
    A telecaller greets by FIRST name + 'जी', never the full legal name. Never raises."""
    return (full or "").strip().split()[0] if (full or "").strip() else ""


# VP3: pure-Hindi greeting wishes are BANNED (the wish must be ENGLISH 'good morning'…).
# Deterministic scrub so a banned word never reaches TTS even if the LLM disobeys: drop the
# banned token; if that leaves the opener with no greeting, prepend the correct English wish.
# NOTE: Python re '\b' is ASCII-only, so it does NOT anchor a Devanagari word; a trailing
# Devanagari lookahead is also unsafe (words end in combining vowel signs). These greeting
# words are distinctive — strip them directly + any trailing separator. Latin forms get an
# ASCII boundary so we never clip an unrelated English word.
_BANNED_GREETING_RE = re.compile(
    r"(?:सुप्रभात|शुभ\s*प्रभात|शुभ\s*रात्रि|शुभ\s*संध्या|नमस्ते|नमस्कार"
    r"|(?<![A-Za-z])(?:subratri|shubh\s*ratri|suprabhat)(?![A-Za-z]))"
    r"[\s,!।]*",
    re.IGNORECASE,
)


def _fix_opener_greeting(text: str, english_wish: str) -> str:
    """Strip any BANNED pure-Hindi greeting from an LLM opener; ensure it opens with the
    ENGLISH time-of-day wish. `english_wish` is e.g. 'good morning'. Never raises."""
    try:
        had_banned = bool(_BANNED_GREETING_RE.search(text or ""))
        out = _BANNED_GREETING_RE.sub("", text or "").strip()
        low = out.lower()
        wish_present = ("good morning" in low or "good afternoon" in low or "good evening" in low)
        if had_banned and not wish_present:
            # we removed the greeting and there's no English wish -> lead with the correct one
            out = f"{english_wish.capitalize()}, {out}".strip()
        # Drop a redundant "hello"/"hello जी" right after the English wish — the founder
        # wants "Good evening, Nikhil जी", NOT "Good evening, hello Nikhil जी".
        out = re.sub(r"((?:good\s+(?:morning|afternoon|evening))[\s,]*)hello\s*(?:जी)?[\s,]*",
                     r"\1", out, flags=re.IGNORECASE)
        return re.sub(r"^[\s,!।]+", "", out).strip() or text or ""
    except Exception:  # noqa: BLE001
        return text or ""


def _collapse_repeats(text: str) -> str:
    """TTS stutter guard: collapse an immediately-repeated word ('evening evening'
    -> 'evening', 'हो हो' -> 'हो', 'Joy Joy' -> 'Joy'). Compares tokens case-
    insensitively, ignoring surrounding punctuation; keeps the variant WITH the
    trailing punctuation (comma/danda) so sentence boundaries survive. Never raises."""
    try:
        import unicodedata as _ud

        def _norm(t: str) -> str:
            return _ud.normalize("NFKC", t).strip(" ,.!?।–—…\"'`’").lower()

        out: list = []
        for tok in (text or "").split():
            if out and _norm(tok) and _norm(tok) == _norm(out[-1]):
                if len(tok) > len(out[-1]):
                    out[-1] = tok
                continue
            out.append(tok)
        return " ".join(out).strip() or (text or "")
    except Exception:  # noqa: BLE001
        return text or ""


def _llm_opener(agent_name: str, company: str, product: str, lead_name: str,
                gender: str = "female", disclose: bool = True,
                disclosure_phrase: str = "", purpose: str = "") -> str:
    """DETERMINISTIC opener in the founder's fixed format — reliable, exact, no LLM/Groq
    dependency (the old LLM-authored version drifted in format + depended on a Groq key):

      "{Greeting}, {Name} जी, मैं {Company} से {AgentName} बात कर {रही/रहा} हूँ, {purpose}, क्या अभी दो minute बात हो सकती है?"

    - Greeting = ENGLISH time-of-day (good morning/afternoon/evening) — pure-Hindi greetings
      (सुप्रभात/नमस्ते) BANNED; lead addressed by FIRST name + 'जी'; gender-correct verb.
    - `purpose` = the per-campaign SHORT reason for the call (fields.opener_purpose); falls back
      to a neutral product mention. This is the only style/campaign-varying slot.
    - Said ONCE via session.say. The brain must NOT re-introduce/re-state company afterwards
      (OPENER_ALREADY_SAID guard) — a second self-intro is the #1 robotic tell + the repeat bug.
    OPENER_LLM=1 restores the old LLM-authored path (rollback)."""
    fname = _first_name(lead_name)            # 'कुणाल कुमार' -> 'कुणाल' (first name only)
    name_part = f"{fname} जी, " if fname else ""
    tod = _ist_time_of_day()  # REAL IST time-of-day → time-correct greeting
    if os.getenv("OPENER_LLM", "0") not in ("1", "true", "True"):
        speaking_v = "बात कर रहा हूँ" if gender == "male" else "बात कर रही हूँ"
        company_part = (disclosure_phrase.strip() or company or "").strip()
        purp = (purpose or "").strip() or f"{product} के बारे में थोड़ी बात करनी थी"
        line = (f"{tod['en'].capitalize()}, {name_part}मैं {company_part} से {agent_name} "
                f"{speaking_v}, {purp}, क्या अभी दो minute बात हो सकती है?")
        return _collapse_repeats(line)
    # ---- legacy LLM-authored path (OPENER_LLM=1) ----
    speaking = "बोल रहा हूँ" if gender == "male" else "बोल रही हूँ"
    disc_phrase = (disclosure_phrase or f"{company} से").strip()
    # Fallback line (used if the LLM opener call fails) — ENGLISH time-of-day wish + 'hello',
    # NEVER 'namaste'/'suprabhat'; gender-correct + configurable disclosure; first-name address.
    if disclose:
        fallback = (f"{tod['en'].capitalize()}, {name_part}मैं {agent_name}, {disc_phrase} {speaking}। "
                    f"{product} के बारे में बात करनी थी — क्या अभी दो minute बात हो सकती है?")
    else:
        fallback = (f"{tod['en'].capitalize()}, {name_part}मैं {agent_name}, {company} से {speaking}। "
                    f"{product} के बारे में बात करनी थी — क्या अभी दो minute बात हो सकती है?")
    try:
        gender_clause = ("Hindi में अपने बारे में पुल्लिंग (masculine) रूप इस्तेमाल करो "
                         "('बोल रहा हूँ', 'बताता हूँ')। ") if gender == "male" else (
                         "Hindi में अपने बारे में स्त्रीलिंग (feminine) रूप इस्तेमाल करो "
                         "('बोल रही हूँ', 'बताती हूँ')। ")
        disc_clause = (f"अपना naam {agent_name} बताओ और एक छोटा सा natural disclosure दो कि तुम "
                       f"{disc_phrase} हो (छोटा रखो, robotic नहीं), और "
                       if disclose else
                       f"अपना naam {agent_name} बताओ और natural रहो, फिर ")
        sysmsg = (
            f"तुम {agent_name} हो, {company} की telecaller। एक बहुत छोटी (15-25 शब्द), गर्मजोशी "
            f"वाली एक-line opener दो — बोलचाल की Hinglish में, Hindi Devanagari में (पर नीचे बताए "
            f"English शब्द English में ही रखो)। "
            f"अभी India में {tod['bucket']} का समय है, इसलिए greeting की शुरुआत ENGLISH में "
            f"'{tod['en']}' से करो, फिर सीधे caller के naam 'जी' के साथ — कोई 'hello' मत जोड़ो। time-of-day का wish हमेशा "
            f"ENGLISH में बोलो ('good morning'/'good afternoon'/'good evening') — कभी गलत समय मत बोलो। "
            f"ये greeting शब्द बिलकुल मना हैं, कभी मत बोलो: 'सुप्रभात', 'शुभ प्रभात', 'शुभ रात्रि', "
            f"'शुभ संध्या', 'नमस्ते', 'नमस्कार'। " + gender_clause
            + (f"caller को FIRST naam '{fname}' से 'जी' लगाकर greet करो (जैसे '{tod['en'].capitalize()}, "
               f"{fname} जी…') — पूरा naam मत बोलो, सिर्फ़ '{fname} जी'। " if fname else "")
            + disc_clause
            + f"साफ़ बताओ कि यह OUTBOUND call है — TUMNE caller को call किया है, उसने तुम्हें नहीं। "
            f"इसलिए पहला-purush (first person) में framing करो — जैसे 'मैंने आपको '{product}' के "
            f"बारे में call किया है' या 'आपने '{product}' में interest dikhaya tha, इसलिए call कर "
            f"रही/रहा हूँ' (gender-appropriate)। कभी मत कहो 'आपने call किया था' / 'आपने हमें contact "
            f"किया था' (वो INBOUND framing है, यह call OUTBOUND है)। फिर पूछो 'क्या अभी दो minute बात हो "
            f"सकती है?'। company और product के नाम ('{company}', '{product}') और कोई भी English "
            f"brand/proper-noun English अक्षरों में ही लिखो — Devanagari में transliterate मत करो। "
            f"बस एक ही छोटी बोली जाने वाली line — कोई symbol/list नहीं, कोई दूसरा वाक्य नहीं। "
            f"Price/size/details बिलकुल मत बताओ।"
        )
        _gk = _next_groq_key()  # A6: capture so a 429 can cool THIS key
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + _gk},
            json={
                "model": os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                "temperature": 0.5, "max_tokens": int(os.getenv("OPENER_MAX_TOKENS", "110") or 110),
                "messages": [
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": "अभी opener बोलो।"},
                ],
            },
            timeout=8,
        )
        if getattr(r, "status_code", 200) == 429:
            mark_groq_key_cooling(_gk)
            _sys_log("warning", "llm", "Groq rate-limit (429); rotating key",
                     error_type="rate_limit_429", context={"stage": "opener"})
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = _fix_opener_greeting(text, tod["en"])  # VP3: ban Hindi greeting, force English wish
        text = _collapse_repeats(text)  # kill word-stutter ('evening evening' / 'हो हो')
        return text or fallback
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


def _strong_lang_note(lang: str) -> str:
    """A FORCEFUL per-turn language directive (role=system). The all-Hindi system
    prompt biases the model to Hindi; a soft hint gets ignored, so when the caller
    switches we issue an explicit, scoped command for THIS turn only (cache-safe —
    appended after the cached prefix, emitted only on a non-default language)."""
    if lang == "english":
        return ("LANGUAGE OVERRIDE: the caller is speaking ENGLISH right now. Reply to THIS "
                "turn in fluent, natural English ONLY — absolutely no Hindi words and no "
                "Devanagari. Keep replying in English until the caller clearly switches back.")
    return (f"LANGUAGE OVERRIDE: the caller is speaking {lang} right now. Reply to THIS turn "
            f"in {lang} (or simple, clear Hindi if you truly cannot), matching the caller.")


# Forced per-turn directive when the caller first tries to end the call with nothing booked:
# make the model OFFER a next step instead of saying goodbye (a buried prompt rule was ignored).
_BYE_OFFER_NOTE = (
    "CLOSING ATTEMPT: the caller is trying to end the call and NOTHING is booked yet. In your "
    "VERY NEXT reply, make ONE short, warm offer — a quick site visit OR a callback at their "
    "convenient time — and ask which suits. Do NOT say goodbye, do NOT end the call, do NOT pitch "
    "more features. Reply in the caller's current language."
)


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
_CLOSE_OPTOUT = (  # HARD: not interested / opt-out -> respect, close immediately (never push)
    "not interested", "interest nahi", "interested nahi", "नहीं चाहिए", "nahi chahiye",
    "mat karo call", "dobara call mat", "do not call", "remove me", "opt out",
    "number hata", "इंटरेस्ट नहीं", "दिलचस्पी नहीं", "दोबारा कॉल मत", "कॉल मत कर",
    "नंबर हटा", "मत करो कॉल",
)
_CLOSE_BYE = (  # SOFT: caller wants to end / "not now" -> OFFER a next step ONCE, then close
    "bye", "बाय", "rakhta hoon", "rakhti hoon", "रखता हूँ", "रखती हूँ", "abhi nahi", "अभी नहीं",
    "baad me", "बाद में", "rehne do", "रहने दो", "no thanks", "nahi bas", "bas karo", "नहीं बस",
)

# BC1 wind-down: ONLY consulted AFTER a successful booking, when the agent has just asked
# "anything else?". A negative then means "nothing else" -> warm goodbye + hang up (the exact
# flow the founder asked for). Short tokens are matched as WHOLE WORDS (so 'no' never matches
# 'now'/'know'); multi-word forms are matched as substrings.
_POST_BOOK_NO_WORDS = {
    "no", "nope", "nahi", "nahin", "नहीं", "bas", "बस", "done", "nothing", "nada",
}
_POST_BOOK_NO_PHRASES = (
    "that's all", "thats all", "nothing else", "no thanks", "no thank", "i'm good", "im good",
    "all good", "we're good", "that's it", "thats it", "kuch nahi", "kuch nahin", "कुछ नहीं",
    "aur kuch nahi", "और कुछ नहीं", "bas yahi", "bas itna", "ho gaya", "ho gya", "theek hai bas",
)

# Signals that the caller is CONTINUING (a question / 'also' / 'and') — these veto the bare-word
# negative so "no, can you also send the address?" is NOT treated as "nothing else".
_FOLLOWUP_SIGNALS = (
    "?", "kya", "क्या", "kaise", "कैसे", "kab", "कब", "kitna", "कितना", "kaha", "कहाँ", "कहां",
    "aur", "और", "also", "bhi", "भी", "but", "lekin", "लेकिन", "question", "puch", "पूछ",
    "bata", "बता", "send", "bhej", "भेज", "address", "price", "rate", "detail",
)


def _is_post_book_no(low: str) -> bool:
    """True only if a post-booking turn clearly means 'nothing else'. A clear closing PHRASE
    always counts; a bare negative WORD counts ONLY when the utterance is short (<=4 words) and
    carries NO follow-up signal — so 'no, can you also send the address?' / 'nahi nahi address
    galat hai' keep the call going instead of hanging up mid-conversation."""
    try:
        if any(p in low for p in _POST_BOOK_NO_PHRASES):
            return True
        words = re.findall(r"[a-zऀ-ॿ']+", low)
        return (len(words) <= 4
                and bool(set(words) & _POST_BOOK_NO_WORDS)
                and not any(s in low for s in _FOLLOWUP_SIGNALS))
    except Exception:  # noqa: BLE001
        return False


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
        # 'book' first: caller affirmed a next step the agent proposed -> close WITH the win.
        tail = " ".join((t.get("content") or "") for t in turns[-4:]).lower()
        affirm = ("haan", "हाँ", "ok", "okay", "theek hai", "ठीक है", "sure", "kar do",
                  "kar lo", "chalega", "fix kar", "yes", "बिलकुल", "bilkul", "ji haan")
        if any(k in tail for k in _CLOSE_BOOK) and any(k in last_user for k in affirm):
            return "book"
        # hard opt-out / not-interested -> respect, close now (never push).
        if any(k in last_user for k in _CLOSE_OPTOUT):
            return "optout"
        # soft 'bye' / 'not now' -> caller wants to end; offer a next step ONCE then close.
        if any(k in last_user for k in _CLOSE_BYE):
            return "bye"
        return ""
    except Exception:  # noqa: BLE001
        return ""


# VSE FIX 6: farewell markers the LLM uses when IT already said goodbye — so the
# confirm-then-hangup closure can detect that and NOT speak a second goodbye.
_FAREWELL_MARKERS = (
    "दिन शुभ", "दिन अच्छा", "दिन मंगलमय", "अलविदा", "शुक्रिया", "धन्यवाद", "बात करके अच्छा लगा",
    "good day", "have a nice day", "have a great day", "take care", "goodbye", "bye",
    "thank you for your time", "samay dene ke liye", "baat karke accha", "din shubh", "din accha",
)

# STRONG, end-of-call-ONLY sign-offs (never said mid-conversation). When the AGENT itself
# speaks one of these, the call is over -> hang up. Without this the agent says goodbye but
# stays on the line, and the caller's next 'hello' makes it re-greet. Tight on purpose
# (no bare 'thanks'/'धन्यवाद', which occur mid-call).
_STRONG_OUTRO = (
    # Hindi sign-offs
    "आपका दिन शुभ हो", "दिन शुभ हो", "आपका दिन अच्छा", "दिन अच्छा रहे", "दिन मंगलमय",
    "फिर मिलते हैं", "din shubh ho", "din accha rahe",
    # English sign-offs — day-part / phrase anchored so they only match a real goodbye,
    # never a mid-call line (the agent said "Have a great EVENING ... Bye for now" and the
    # old list only had "have a great DAY", so hangup never fired).
    "have a great day", "have a great evening", "have a great afternoon", "have a great weekend",
    "have a good day", "have a good evening", "have a nice day", "have a nice evening",
    "have a wonderful day", "have a wonderful evening", "good day to you",
    "bye for now", "goodbye", "good bye", "take care", "talk to you soon", "talk soon",
)


def _last_assistant_is_farewell(turns: list[dict]) -> bool:
    """True iff the most recent ASSISTANT turn already reads as a goodbye/farewell.
    Used by the closure to avoid speaking a SECOND goodbye after the LLM said one."""
    try:
        for t in reversed(turns or []):
            if (t.get("role") or "") == "assistant":
                txt = (t.get("content") or "").lower()
                return any(m.lower() in txt for m in _FAREWELL_MARKERS)
    except Exception:  # noqa: BLE001
        return False
    return False


# VP3: 'अलविदा' (Alvida/goodbye) is BANNED. Even though the close prompt forbids it,
# this deterministic scrub guarantees it never reaches TTS if the LLM disobeys: strip the
# word (and any trailing separator) so the rest of the warm line is still spoken.
# '\b' is ASCII-only (won't anchor 'अलविदा'), and a trailing Devanagari lookahead is unsafe
# (the word ends in a combining vowel sign). The word is distinctive enough to strip directly,
# plus any separator/punctuation around it. Latin forms are guarded with an ASCII boundary.
_ALVIDA_RE = re.compile(
    r"[\s,–—-]*(?:अलविदा|(?<![A-Za-z])(?:alvida|alavida)(?![A-Za-z]))[।.!\s]*",
    re.IGNORECASE,
)


def _strip_alvida(text: str) -> str:
    """Remove the banned farewell word 'अलविदा' (and transliterations) from a spoken
    line, leaving the rest intact. Never raises; returns a stripped, tidy string."""
    try:
        out = _ALVIDA_RE.sub(" ", text or "").strip()
        # tidy any leftover dangling separators at the end (', ' / '— ' / '. ')
        out = re.sub(r"[\s,।.–—-]+$", "", out).strip()
        # if the line now ends without terminal punctuation, add a soft '।'
        return out or (text or "")
    except Exception:  # noqa: BLE001
        return text or ""


def _goodbye_line(signal: str, agent_name: str, company: str, gender: str) -> str:
    """A warm, gender-correct closing line spoken before we end the call."""
    fem = gender != "male"
    if signal == "book":
        return ("बढ़िया! मैं details WhatsApp पर भेज " + ("देती हूँ" if fem else "देता हूँ") +
                ", और हमारी team आपसे जल्दी connect कर लेगी। बात करके अच्छा लगा — आपका दिन शुभ हो!")
    # polite no / opt-out
    return ("कोई बात नहीं, आपका समय देने के लिए शुक्रिया। ज़रूरत हो तो "
            f"{company} हमेशा हाज़िर है — आपका दिन अच्छा रहे!")


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
                      "हो गया है। एक छोटी, गर्मजोशी भरी closing line बोलो जो उसी ACTUAL agreed step "
                      "को (जैसे 'कल शाम site visit' / 'WhatsApp पर details' / 'callback') naturally "
                      "उसके अपने नाम से confirm करे और thank करे — जैसे एक असली इंसान करता है।")
        else:
            intent = ("Caller ने अभी interest नहीं दिखाया / दोबारा call न करने को कहा है। एक छोटी, "
                      "respectful closing line बोलो — politely thank करो, बिना बहस, बिना दोबारा pitch।")
        sysmsg = (
            f"तुम {agent_name} हो, {company} की telecaller। {gender_clause} {intent} "
            f"सिर्फ़ एक ही छोटी (12-22 शब्द) बोली जाने वाली line दो — caller ने call में जिस भाषा "
            f"(Hindi/English/Hinglish) में बात की उसी भाषा में, गर्मजोशी से।\n"
            f"🔑 हर बार बिलकुल अलग, ताज़ी line बनाओ — कोई fixed/रटा-रटाया closing template मत दोहराओ। "
            f"line इसी call के outcome से जुड़ी हो (ऊपर दी 'हाल की बातचीत' को देखकर) — हर call पर अलग "
            f"शब्द, अलग वाक्य। तुम्हारा thank-you और sign-off हर बार natural variation के साथ हो "
            f"(जैसे कभी 'बात करके अच्छा लगा', कभी 'time देने के लिए शुक्रिया', कभी 'मिलते हैं', कभी "
            f"'अच्छा रहेगा आपसे' — पर इनमें से किसी एक को रट कर मत दोहराओ, हर बार अपने शब्दों में)। "
            f"कभी मत बोलो/लिखो: 'अलविदा' (alvida)। company/product और कोई भी English brand-name English "
            f"अक्षरों में ही लिखो। कोई symbol/list/दूसरा वाक्य नहीं, कोई नया सवाल नहीं, कोई price/legal "
            f"promise नहीं।")
        _gk = _next_groq_key()  # A6: capture so a 429 can cool THIS key
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + _gk},
            json={
                "model": os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                # CLOSE_TEMP higher (default 0.8) so the close VARIES per call (the old 0.4 +
                # a canned-phrase steer made every goodbye identical — the founder's BUG2).
                "temperature": float(os.getenv("CLOSE_TEMP", "0.8")), "max_tokens": int(os.getenv("CLOSE_MAX_TOKENS", "60")),
                "messages": [
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": "हाल की बातचीत:\n" + (recent or "(—)") + "\n\nअब closing line बोलो।"},
                ],
            },
            timeout=8,
        )
        if getattr(r, "status_code", 200) == 429:
            mark_groq_key_cooling(_gk)
            _sys_log("warning", "llm", "Groq rate-limit (429); rotating key",
                     error_type="rate_limit_429", context={"stage": "close"})
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
        text = _strip_alvida(text)  # VP3: hard-guarantee no 'अलविदा' reaches TTS
        return text or fallback
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm close failed, using fallback: %r", exc)
        return fallback


# ── BC1: fast booking CAPTURE (default ON) ────────────────────────────────────
# The DEFAULT, always-available booking path. When the caller agrees a slot, the agent speaks
# a short "ok, booking that now — one moment" filler (so there is NEVER a silent wait — the
# very gap that froze Colin's call), then DURABLY captures the agreed slot to the shared /data
# store + System Logs. No calendar config / external service needed (the full availability
# engine lands later). Fully wrapped: any failure returns a spoken-safe string, never raises.
def _booking_filler_line(gender: str) -> str:
    """A short, warm 'I'm booking it now, one moment' said BEFORE the (fast) capture so the
    caller is never met with silence while we work."""
    fem = gender != "male"
    return ("ठीक है, मैं अभी आपकी site visit book कर " + ("देती हूँ" if fem else "देता हूँ")
            + " — बस एक second…")


def booking_capture_enabled() -> bool:
    """Default ON. Set BOOKING_CAPTURE_ENABLED=0 to detach (agent byte-identical to before)."""
    try:
        if _lk_function_tool is None or _LkRunContext is None:
            return False
        return (os.getenv("BOOKING_CAPTURE_ENABLED", "1") or "1").strip().lower() not in (
            "0", "false", "no", "off")
    except Exception:  # noqa: BLE001
        return False


def _capture_booking(*, tenant_id: str, phone: str, lead_name: str, when_text: str,
                     campaign_id: str = "", notes: str = "", room: str = "") -> dict:
    """Durably capture an agreed site-visit slot. Resolves the spoken time to ISO when the
    resolver is available (else stores the raw spoken text), APPENDS one row to the shared
    /data/bookings.jsonl (append-only => race-free across the agent + backend processes), and
    surfaces it in System Logs. Fast + reliable; never raises -> {ok, datetime_iso, id}."""
    import uuid as _uuid
    from datetime import datetime as _d, timezone as _z
    iso = ""
    try:
        from voice_ops.booking.datetime_resolve import resolve_slot_start
        slot = resolve_slot_start(when_text or "", now=_d.now(_z.utc), tz="Asia/Kolkata")
        iso = slot.isoformat() if slot is not None else ""
    except Exception:  # noqa: BLE001 — resolver optional; raw spoken text still captured
        iso = ""
    try:
        rec = {
            "id": _uuid.uuid4().hex[:10], "tenant_id": tenant_id or "", "phone": phone or "",
            "name": lead_name or "", "when_text": when_text or "", "datetime_iso": iso,
            "campaign_id": campaign_id or "", "notes": notes or "", "room": room or "",
            "source": "voice", "status": "captured", "created_at": _d.now(_z.utc).isoformat(),
        }
        path = str(VAR / "bookings.jsonl")  # same VAR (FAMIT_VAR) the backend reads from
        with open(path, "a", encoding="utf-8") as fh:  # O_APPEND => atomic small writes
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _sys_log("info", "booking",
                 f"site visit booked for {phone or '—'} — {when_text or iso or 'time TBD'}",
                 tenant_id=tenant_id, call_id=room,
                 context={"when": when_text, "iso": iso, "name": lead_name, "phone": phone})
        return {"ok": True, "datetime_iso": iso, "id": rec["id"]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("booking capture failed: %r", exc)
        _sys_log("warning", "booking", f"booking capture failed for {phone}: {exc!r}",
                 tenant_id=tenant_id, call_id=room, error_type=type(exc).__name__)
        return {"ok": False, "reason": "capture_error"}


# ── A3: booking voice-tool support ────────────────────────────────────────────
# The agent can BOOK a real appointment when the prospect agrees a slot. Runs
# IN-PROCESS on the box (booking.core uses its own RLS db session, tenant-scoped),
# exactly like lead-memory persists — NO new cross-box HTTP / service token. Fully
# wrapped: any failure returns a spoken-safe "couldn't book" string, never raises
# into the call. Pure brain/logic — NOTHING in the TTS/voice path.
def booking_tool_enabled() -> bool:
    """ON only when BOTH the kernel is on AND BOOKING_TOOL_ENABLED=1 (default OFF =>
    no tool attached => the agent is byte-identical to today)."""
    try:
        if _lk_function_tool is None or _LkRunContext is None:
            return False
        kern = os.getenv("KERNEL_OUTBOUND", "0") in ("1", "true", "True")
        flag = os.getenv("BOOKING_TOOL_ENABLED", "0") in ("1", "true", "True")
        return kern and flag
    except Exception:  # noqa: BLE001
        return False


# ── R5VF: booking voice-tool over the caller.py HTTP contract ──────────────────
# A SECOND booking path that works on the LIVE P0 brain (KERNEL_OUTBOUND=0), where
# the in-process `booking_tool_enabled()` tool above can NEVER attach (it is gated on
# the kernel being ON). This one POSTs the slot to the caller.py endpoint on the SAME
# box — `POST http://127.0.0.1:8209/booking/book` {phone, lead_name, datetime_iso,
# campaign_id, notes} — so the real booking is created by the backend (the team
# building that endpoint in parallel). Gated behind its OWN flag, INDEPENDENT of the
# kernel, DEFAULT OFF => no tool attached => the agent is byte-identical to today. Pure
# brain/logic + one localhost HTTP call — NOTHING in the TTS/voice path. Fully wrapped:
# any failure returns a spoken-safe string, never raises into the call.
def booking_http_tool_enabled() -> bool:
    """ON only when BOOKING_HTTP_ENABLED=1 (default OFF). Works on the P0 brain
    (does NOT require KERNEL_OUTBOUND) — that is the whole point: the live earner runs
    KERNEL_OUTBOUND=0, so this is the booking tool that can actually attach today. OFF
    => no tool => byte-identical to today."""
    try:
        if _lk_function_tool is None or _LkRunContext is None:
            return False
        return os.getenv("BOOKING_HTTP_ENABLED", "0") in ("1", "true", "True")
    except Exception:  # noqa: BLE001
        return False


def _do_booking_http(phone: str, *, when_text: str, lead_name: str = "",
                     campaign_id: str = "", notes: str = "",
                     tz: str = "Asia/Kolkata") -> dict:
    """Resolve the spoken slot to an ISO datetime, then POST it to the caller.py
    booking endpoint on localhost (the R5 contract). Returns a small dict:
      {"ok": True, ...}  on success
      {"ok": False, "reason": "bad_slot"|"http_<code>"|"no_phone"|"post_error"}  otherwise
    Never raises. The endpoint is on the SAME box (127.0.0.1:8209); an optional
    BOOKING_HTTP_TOKEN is sent as a Bearer header if configured (the backend decides
    whether it is required)."""
    if not phone:
        return {"ok": False, "reason": "no_phone"}
    # Natural-language slot ("kal sham 5 baje", "tomorrow 11am") -> ISO 8601, reusing
    # the same resolver the in-process tool uses (consistent slot parsing both ways).
    iso = ""
    try:
        from datetime import datetime as _d3, timezone as _z3
        from voice_ops.booking.datetime_resolve import resolve_slot_start  # type: ignore
        slot = resolve_slot_start(when_text or "", now=_d3.now(_z3.utc), tz=tz)
        if slot is not None:
            iso = slot.isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("http booking slot resolve failed: %r", exc)
        iso = ""
    if not iso:
        return {"ok": False, "reason": "bad_slot"}
    url = os.getenv("BOOKING_HTTP_URL", "http://127.0.0.1:8209/booking/book")
    payload = {
        "phone": phone,
        "lead_name": lead_name or "",
        "datetime_iso": iso,
        "campaign_id": campaign_id or "",
        "notes": notes or "",
    }
    headers = {"Content-Type": "application/json"}
    _tok = (os.getenv("BOOKING_HTTP_TOKEN", "") or "").strip()
    if _tok:
        headers["Authorization"] = "Bearer " + _tok
    try:
        r = httpx.post(url, json=payload, headers=headers,
                       timeout=float(os.getenv("BOOKING_HTTP_TIMEOUT", "6")))
        code = getattr(r, "status_code", 0)
        if 200 <= code < 300:
            try:
                body = r.json()
            except Exception:  # noqa: BLE001
                body = {}
            # Honor an explicit conflict/ok flag from the backend if present.
            if isinstance(body, dict) and body.get("ok") is False:
                return {"ok": False, "reason": str(body.get("reason") or "rejected"),
                        "datetime_iso": iso, **({k: body[k] for k in ("conflict",) if k in body})}
            return {"ok": True, "datetime_iso": iso, "resp": body}
        # 409 => slot conflict (common booking semantics); surface it for a re-offer.
        if code == 409:
            return {"ok": False, "reason": "slot_taken", "datetime_iso": iso}
        return {"ok": False, "reason": f"http_{code}", "datetime_iso": iso}
    except Exception as exc:  # noqa: BLE001
        logger.warning("http booking POST failed url=%s err=%r", url, exc)
        return {"ok": False, "reason": "post_error"}


def _resolve_default_resource_id(org_id: str) -> str:
    """First active booking resource for the tenant (the slot we book against).
    Returns "" if none / not configured. Never raises."""
    try:
        from db import engine as _eng  # type: ignore
        with _eng.session(tenant_id=org_id, is_admin=False) as s:
            from sqlalchemy import text as _sqltext  # type: ignore
            row = s.execute(_sqltext(
                "SELECT id FROM booking_resources WHERE org_id=:org "
                "ORDER BY created_at ASC LIMIT 1"
            ), {"org": org_id}).fetchone()
            return str(row[0]) if row else ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("booking resource resolve failed org=%s err=%r", org_id, exc)
        return ""


def _do_booking(org_id: str, phone: str, *, when_text: str, name: str = "",
                campaign_id: str = "", tz: str = "Asia/Kolkata") -> dict:
    """Resolve a default resource + a spoken slot time, then atomically claim it via
    booking.core.book (in-box RLS). Returns the core.book dict (ok/conflict/error)."""
    if not org_id:
        return {"ok": False, "reason": "no_tenant"}
    rid = _resolve_default_resource_id(org_id)
    if not rid:
        return {"ok": False, "reason": "no_resource"}
    try:
        from datetime import datetime as _d2, timezone as _z2
        from voice_ops.booking.datetime_resolve import resolve_slot_start  # type: ignore
        slot = resolve_slot_start(when_text or "", now=_d2.now(_z2.utc), tz=tz)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slot resolve failed: %r", exc)
        slot = None
    if slot is None:
        return {"ok": False, "reason": "bad_slot"}
    try:
        from booking import core as _bk  # type: ignore
        return _bk.book(org_id, rid, phone, slot_start=slot.isoformat(), name=name,
                        title="Appointment", source="voice", campaign_id=campaign_id,
                        is_admin=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("booking.core.book failed: %r", exc)
        return {"ok": False, "reason": "book_error"}


# MINIMAL PERSONA (MP1): a ~720-char warm persona an 8B can FULLY hold (the 6.7K brain overflows it
# into repetition / random goodbye / rambling). Flag-gated (MINIMAL_PERSONA=1). Placeholders filled
# from the campaign fields; female forms, never-reveal-AI, and the anti-collapse rules baked in tersely
# + 4 micro-examples (objections + a CLOSE). Reversible: MINIMAL_PERSONA=0 keeps the full brain.
_MINIMAL_PERSONA_TMPL = (
    "तुम रिया हो — Famit से {lead} को call कर रही हो। warm लड़की, सुनती हो, दिल से चाहती हो इन्हें सही "
    "घर मिले। {proj}, {price} में {usp}। मकसद: एक free site visit fix हो।\n\n"
    "polite रोज़मर्रा Hinglish, female रूप — बोल रही हूँ, समझ सकती हूँ। हर turn: पहले उनकी बात पर "
    "react, फिर एक छोटी नई line, फिर रुको। naam सिर्फ़ शुरू में एक बार — हर turn '{lead} जी' मत "
    "दोहराओ। एक feature एक ही बार; अपना पिछला वाक्य/pitch कभी दोबारा मत बोलो। caller 'हाँ'/interest "
    "दे तो दोबारा मत समझाओ — सीधे visit: 'कौन सा दिन?'. ⚠️ caller 'बाद में/थोड़ी देर में call करो' कहे "
    "तो book बिलकुल मत करो — सिर्फ़ time पूछो ('किस time call करूँ?') और रुक जाओ। 'आपका दिन कैसा है' "
    "जैसे बेकार सवाल कभी मत पूछो। नंबर शब्दों में। वो call काटें तभी अलविदा। AI मत बताओ।\n\n"
    "काॅलर: Hello / हाँ बोलिए।\nरिया: जी, मैं Riya — आपने {proj} में interest दिखाया था इसलिए call "
    "किया। दो minute हैं आपके पास?\n\n"
    "काॅलर: अभी busy हूँ / बाद में call करना।\nरिया: ज़रूर, समझ सकती हूँ — किस time call करूँ, शाम "
    "ठीक रहेगा?\n\n"
    "काॅलर: budget tight है।\nरिया: समझती हूँ — easy EMI पे आराम से बैठ जाता है, एक बार देख तो "
    "लीजिए।\n\n"
    "काॅलर: सोचना पड़ेगा।\nरिया: बिलकुल — इसीलिए एक बार site देख लीजिए, फिर decide करना।\n\n"
    "काॅलर: हाँ, ठीक है।\nरिया: बहुत अच्छा! कौन सा दिन — शनिवार या रविवार? address WhatsApp पे भेज "
    "देती हूँ।"
)


def _render_minimal_persona(fields: dict, lead_name: str = "") -> str:
    """Fill the minimal persona template from campaign fields. Best-effort; caller also guards."""
    f = fields if isinstance(fields, dict) else {}
    lead = (lead_name or f.get("lead_name") or "").strip() or "जी"
    proj = " ".join(b for b in [str(f.get("product_name") or f.get("project_name") or "").strip(),
                                str(f.get("location") or "").strip()] if b) or "हमारी property"
    price = str(f.get("price_offer") or "").strip() or "अच्छी range"
    u = f.get("usps")
    usp = (str(u[0]).strip() if isinstance(u, list) and u else "") \
        or str(f.get("product_summary") or "").strip() or "बढ़िया option"
    return _MINIMAL_PERSONA_TMPL.format(lead=lead[:40], proj=proj[:80], price=price[:60], usp=usp[:90])


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
    # BC1 FIX: derive the campaign's tenant UNCONDITIONALLY here. It used to be assigned ONLY
    # inside the KERNEL_OUTBOUND block below, so on the live config (kernel OFF) the default-on
    # booking-capture tool hit a NameError on `_camp_tenant` and silently never attached. Now
    # every booking path resolves it on every config. (The kernel block re-derives the same
    # value harmlessly.)
    _camp_tenant = str((camp or {}).get("tenant_id", "")).strip()
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
            # VERTICALS: fill the CAMPAIGN override's persona/language identity BEFORE merging it
            # over the (possibly golden GODREJ) base, so a selected persona's name/gender beats a
            # baked default. No-op unless FEATURE_VERTICALS + a vertical (returns the same dict).
            if _verticals is not None:
                override = _verticals.fill_fields(override)
            merged = dict(fields)
            merged.update({k: v for k, v in override.items() if v not in (None, "")})
            fields = merged
            system_prompt = build_system_prompt(fields)
            logger.info("variant=%s applied override keys=%s",
                        meta.get("variant_id"), list(override.keys()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("variant override failed: %r", exc)
    # VERTICALS: multi-vertical / multi-persona / multi-language. Fill the persona &
    # language identity (name/gender/persona-line) onto the campaign fields, then re-render
    # the brain so a SELECTED persona is LIVE. No-op unless FEATURE_VERTICALS=1 and a
    # vertical is chosen (fill_fields returns the SAME dict otherwise). Runs BEFORE
    # brain_override so a hand-authored script still wins. NEVER raises.
    if _verticals is not None:
        try:
            _vf = _verticals.fill_fields(fields)
            if _vf is not fields:
                fields = _vf
                system_prompt = build_system_prompt(fields)
                logger.info("VERTICALS active campaign=%s vertical=%s persona=%s",
                            meta.get("campaign_id"), fields.get("vertical"), fields.get("persona"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("verticals fill_fields failed -> keeping brain: %r", exc)
    # BRAIN-OVERRIDE (per-campaign hand-authored script): when a campaign's fields carry a non-empty
    # `brain_override`, use it VERBATIM as the system prompt instead of the heavy auto-brain. This is how
    # a lean, human script (e.g. the Joyville Opus script) drives ONE specific campaign — ~5x fewer tokens
    # than build_system_prompt, so no cold-cache turn-1 lag, and exactly the words you want. Campaign-
    # scoped + reversible (clear the field to revert). Opener-already-said + booking guidance below still
    # apply on top. NEVER raises — any error keeps the brain built above.
    try:
        _bo = (fields.get("brain_override") or "").strip() if isinstance(fields, dict) else ""
        if _bo:
            system_prompt = _bo
            logger.info("BRAIN-OVERRIDE active campaign=%s (%d chars)", meta.get("campaign_id"), len(_bo))
    except Exception as exc:  # noqa: BLE001
        logger.warning("brain_override failed -> keeping built brain: %r", exc)
    # MP1: when MINIMAL_PERSONA is on, replace the full brain with the tiny field-filled persona an 8B
    # can fully hold. ANY error keeps whatever system_prompt was built above (never worse than today).
    if os.getenv("MINIMAL_PERSONA", "0") in ("1", "true", "True"):
        try:
            system_prompt = _render_minimal_persona(fields, lead_name)
            logger.info("MP1 minimal persona active (%d chars)", len(system_prompt))
        except Exception as exc:  # noqa: BLE001
            logger.warning("MP1 minimal persona render failed -> full brain: %r", exc)

    # VSE FIX 4 (named identity-confirm): thread the dispatch lead_name INTO the fields
    # dict so the kernel brain pack (delivery_directive) can confirm identity BY THE REAL
    # NAME ("क्या मेरी बात {name} से हो रही है?") instead of the generic "सही व्यक्ति".
    # Only set it when present and not already provided; never overwrites a campaign value.
    if lead_name and not str(fields.get("lead_name") or "").strip():
        try:
            fields = {**fields, "lead_name": lead_name}
        except Exception:  # noqa: BLE001 — never break the earner over a field merge
            pass

    # Cross-call memory: recover the lead's phone from the room name, load prior call.
    phone = mem.parse_phone(room_name)
    recap = mem.build_recap(mem.load_memory(phone))

    # W-INT-OUTBOUND (A4) — seam 1/4: build the per-call kernel façade, or None.
    # KERNEL_OUTBOUND OFF (default) => build_for_call returns None => the brain/turn/
    # persist seams below all run their UNCHANGED legacy path (byte-identical earner).
    # Fully wrapped: ANY error -> _ik=None -> legacy. The campaign-record's owning
    # tenant is the ONLY tenant source (fail-closed in build_for_call); blank/mismatch
    # -> None -> legacy, never a dropped or cross-tenant lead call.
    _ik = None
    try:
        if _vk is not None and _vk.kernel_outbound_enabled():
            _camp_tenant = str((camp or {}).get("tenant_id", "")).strip()
            _ik = _vk.build_for_call(
                tenant_id=_camp_tenant,
                call_id=room_name,
                lead_phone=phone,
                campaign_id=meta.get("campaign_id", ""),
                campaign_tenant_id=_camp_tenant,
                fields=fields,
                recap=recap,
                locale="hi-IN",
            )
    except Exception as _ik_exc:  # noqa: BLE001 — the kernel can never break the earner
        logger.warning("kernel build_for_call failed -> legacy: %r", _ik_exc)
        _ik = None

    base_instructions = _fill_lead_placeholders(system_prompt, fields, lead_name)
    if lead_name and os.getenv("MINIMAL_PERSONA", "0") not in ("1", "true", "True"):
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
            "\n\n=== तुम पहले ही OPEN कर चुके हो (सबसे ज़रूरी — repeat मत करो) ===\n"
            "Call की शुरुआत में तुम एक बार में ये सब बोल चुकी/चुके हो: greeting + अपना naam + company + "
            "किस product के बारे में call + 'क्या अभी दो minute बात हो सकती है?'। इसलिए अब किसी भी turn में:\n"
            "• दोबारा 'नमस्ते'/greeting मत करो; अपना naam/company/परिचय दोबारा मत दोहराओ।\n"
            "• 'दो minute'/'time है?'/'बात हो सकती है?'/'call किया था' या कोई भी permission/मंज़ूरी "
            "दोबारा मत माँगो — ये पहले ही पूछ चुके हो।\n"
            "• 'क्या मेरी बात X जी से हो रही है?' — naam confirm भी दोबारा मत पूछो (greeting में naam इस्तेमाल हो चुका)।\n"
            "caller के पहले जवाब ('हाँ'/'हैलो'/'जी बोलिए') पर सबसे पहला काम — एक-दो लाइन में साफ़ बताओ कि तुमने "
            "call क्यों किया: अपने product/offer का एक छोटा purpose + एक hook (पूरा brochure मत गिनाओ, बस एक "
            "line जो interest जगाए) — और उसी turn को एक हल्के follow-up सवाल पर ख़त्म करो जो caller की situation/"
            "ज़रूरत समझे (जैसे 'क्या आप अभी ये देख रहे हैं — अपने लिए या...?')। सीधे सूखे सवाल से मत शुरू करो, "
            "और सारी details एक साथ मत डालो। उसके बाद हर turn: एक नई छोटी बात/जवाब + एक follow-up सवाल — "
            "सिर्फ़ statement देकर चुप मत हो, और कोई भी पिछली बात दोबारा मत बोलो।")
    if recap:
        base_instructions += (
            "\n\n=== background context (सिर्फ़ तुम्हारी समझ के लिए) ===\n"
            "इस lead का पहले का हल्का context नीचे है। इसे सिर्फ़ अपनी जानकारी के लिए रखो — "
            "call को एक fresh, natural बातचीत की तरह चलाओ; खुद से 'पिछली बार हमने बात की थी' "
            "जैसा कभी मत कहो। caller खुद पिछली बात का ज़िक्र करे, तभी हल्के से acknowledge करना।\n" + recap)
        logger.info("returning lead phone=%s recap_chars=%d", phone, len(recap))
    # 8b-HARDENING (HV1): the small llama-3.1-8b runtime collapses into a few SPECIFIC failures we
    # saw live — random mid-call "अलविदा/goodbye", repeating the same time/number ("पाँच बजे या पाँच
    # बजे"), "मैंने आपकी बात नहीं सुनी / हैलो हैलो" dead-air rambling, mangling the company name, and
    # dumping several facts at once. These HARD, concrete rules target exactly those. Additive to the
    # one-time prefix (cache-safe), default-ON; PROMPT_HARDEN=0 reverts to byte-identical.
    if (os.getenv("PROMPT_HARDEN", "1") in ("1", "true", "True")
            and os.getenv("MINIMAL_PERSONA", "0") not in ("1", "true", "True")):  # minimal already has them
        base_instructions += (
            "\n\n=== सख़्त नियम (हमेशा, कोई अपवाद नहीं) ===\n"
            "- कभी 'अलविदा' / 'bye' / 'फिर मिलते हैं' / 'थोड़ी देर के लिए' मत बोलो जब तक caller खुद बात "
            "ख़त्म न कर दे — बीच बातचीत में विदा बिलकुल मत लो।\n"
            "- एक ही वाक्य में कोई समय / तारीख़ / नंबर / शब्द दो बार मत दोहराओ ('शाम पाँच बजे या शाम पाँच "
            "बजे' ❌) — एक बार साफ़ बोलो।\n"
            "- 'मैंने आपकी बात नहीं सुनी' / 'मेरी बात आ रही है' / 'हैलो हैलो' जैसी भरती कभी मत बोलो। अगर "
            "सच में समझ न आए तो सिर्फ़ एक छोटा साफ़ सवाल पूछो: 'ज़रा फिर से बताइएगा?'\n"
            "- एक turn में सिर्फ़ एक बात बोलो, फिर रुक जाओ — दो-तीन बातें एक साथ मत जोड़ो।\n"
            "- company / project का naam एक बार पूरा और साफ़ बोलो, टुकड़ों में मत तोड़ो।\n"
            "- अपना पिछला वाक्य या caller का वाक्य दोबारा मत दोहराओ — हर turn एक नई, आगे बढ़ाने वाली बात हो।")
    # BAKE-OFF GUARDRAILS (BG1): the truth/honesty rules the stress-test surfaced — models (esp.
    # Sarvam-30b) otherwise invent builder project names, fabricate facts, promise guaranteed returns,
    # pretend to do human things, or falsely claim to be human. Additive to the one-time prefix
    # (cache-safe), default-ON; BRAIN_GUARDRAILS=0 reverts. Pairs with the deterministic re-intro
    # stripper in tts_node (which owns the no-re-introduce behaviour).
    if os.getenv("BRAIN_GUARDRAILS", "1") in ("1", "true", "True"):
        base_instructions += (
            "\n\n=== सच्चाई और भरोसे के नियम (हमेशा, कोई अपवाद नहीं) ===\n"
            "- सिर्फ़ वही जानकारी बोलो जो तुम्हें brain में दी गई है। school के naam, exact carpet area, "
            "कितने units बचे, या कोई number/detail जो नहीं दिया गया — कभी मत बनाओ। न पता हो तो बोलो: "
            "'ये detail मैं पता करके आपको बता देती हूँ।'\n"
            "- builder के किसी पुराने या दूसरे project का naam कभी मत लो/मत बनाओ; पूछें तो बोलो: 'उनका "
            "लंबा strong track record है, उसकी details मैं आपको भेज देती हूँ' — फिर इसी launch पर focus करो।\n"
            "- कभी guaranteed return / पक्का profit / fixed appreciation का वादा मत करो — ईमानदार रहो।\n"
            "- इंसानी कामों का दिखावा मत करो (cricket/IPL score, news, weather देखना) — politely बात property "
            "पर वापस लाओ।\n"
            "- अगर कोई पूछे तुम AI/robot/इंसान हो: झूठ मत बोलो कि 'मैं इंसान हूँ' — बोलो 'मैं Famit की तरफ़ से "
            "आपकी property search में मदद कर रही हूँ' और बातचीत आगे बढ़ाओ।\n"
            "- EMI/calculation पूछे तो जवाब छोटा रखो लेकिन final number पूरा बोलो, अधूरा मत छोड़ो।")
    # OUTPUT-FORMAT GUARD (OF1): appended LAST = highest-priority. Stops a model (esp. Sarvam-30b)
    # from emitting a markdown dialogue SCRIPT ("**Riya:** ... **Customer:** ...") instead of one
    # spoken line. Pairs with the tts_node sanitizer (which also strips/cuts these). Default-ON;
    # REPLY_FORMAT_GUARD=0 reverts.
    if os.getenv("REPLY_FORMAT_GUARD", "1") in ("1", "true", "True"):
        base_instructions += (
            "\n\n=== कैसे BOLNA hai — OUTPUT FORMAT (sabse ऊपर, har cheez se zaroori) ===\n"
            "Tum ek LIVE phone call par ho. Sirf apni EK baari ke bole jaane wale shabd do — aur kuch nahi:\n"
            "- Koi script mat likho: 'Riya:', 'Customer:', 'ग्राहक:', 'Agent:' jaise speaker-label kabhi mat lagao.\n"
            "- Koi markdown/symbol nahi: **, *, #, bullet, heading, ya brackets mein direction — kuch nahi.\n"
            "- Saamne wale (customer) ki line KHUD mat banao; uska jawab mat likho — bas apni ek line bolo aur ruk jao.\n"
            "- Sirf 1-2 chhote sentence, natural Hinglish. Poora pitch ek saath kabhi mat bolo.")
    # W-INT-OUTBOUND (A4) — seam 2/4: the instruction (brain) seam. OFF / _ik=None /
    # ANY error => EXACTLY base_instructions (byte-identical to today). ON => the
    # kernel packet-assembled outbound persona (the W2-W7 brain). The legacy block
    # ABOVE is passed verbatim as the fallback lambda, so the OFF earner is unchanged.
    if _ik is not None:
        instructions = _vk.assemble_outbound_instructions(
            _ik, legacy_render=lambda: base_instructions, fields=fields, recap=recap,
        )
    else:
        instructions = base_instructions

    # VERTICALS: append the lean domain directive (objective + slots + compliance) to the
    # FINAL instructions — a cache-safe one-time suffix that survives the kernel seam above.
    # Provider-aware (so the language nudge never asks for a script the active engine can't
    # speak). Identity when off / no vertical.
    if _verticals is not None:
        _v_tp = (_voice_cfg("tts_provider", "") or os.getenv("TTS_PROVIDER", "elevenlabs")).strip().lower()
        instructions = _verticals.apply_to_prompt(instructions, fields, tts_provider=_v_tp)

    # NOTE: the booking guidance is appended LATER (after the tool-attach blocks), gated on
    # whether a booking tool ACTUALLY attached — so the prompt and the tool never disagree
    # (BC1 fix: previously this was gated on booking_http_tool_enabled() only, so the default-on
    # capture tool attached with NO guidance to use it).

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
    # VERTICALS international: a WORLD (non-Indic) language runs as a FIXED-language call — pin the
    # TTS to that language and DISABLE per-turn langdetect mirroring (langdetect can't tell e.g.
    # Spanish from English and would flip the call). Legacy hi/en/hinglish/regional campaigns:
    # _intl_lang is None -> lang_tracker + mirroring stay EXACTLY as today (byte-identical).
    _intl_lang = _verticals.tts_language(fields, "elevenlabs") if _verticals is not None else None
    _intl_pin = bool(_intl_lang)
    if _intl_pin:
        lang_tracker = None
        _lang_v2 = False
        default_lang = _intl_lang
        logger.info("VERTICALS international: fixed-language call lang=%s (mirroring OFF)", _intl_lang)
    # Shared mutable cell so the (sync) conversation callback can hand async work to the loop.
    # tts_code = the language code currently set on the TTS stream (so V2 only calls
    # update_options on a REAL code change — incl. reverting EN->HI — avoiding ws churn).
    ctl = {"closing": False, "active_lang": default_lang, "loop": None,
           "session": None, "agent": None, "tts": None, "tts_code": None,
           "post_booking": False}  # BC1: set True after a successful booking (wind-down close)
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

    # P1 voice analytics: per-call + per-turn latency telemetry (flag-gated, dormant-safe; the live
    # call is NEVER affected — see voice_analytics.py). The recorder is created just before the
    # metrics hook below (once the call context is resolved); here we only reserve the name and
    # register the shutdown flush (the single network write happens off the speech path at call end).
    _va = None
    try:
        import voice_analytics as _va_mod
    except Exception:  # noqa: BLE001
        _va_mod = None

    async def _va_finish() -> None:
        try:
            if _va is not None:
                _va.finish(duration_s=max(0.0, _time.time() - usage["started_at"]))
        except Exception:  # noqa: BLE001
            pass
        # P2.2: flush this call's per-key provider usage so the backend's /usage sees cross-process
        # key utilization (the worker's in-process health is otherwise invisible to the API process).
        try:
            if _pm is not None and _pm_used and _va_mod is not None:
                try:
                    snap = _pm.health()  # {provider: {keys: [{fingerprint, score, status, ...}]}}
                except Exception:  # noqa: BLE001
                    snap = {}

                def _kh(prov, fp):
                    for k in (snap.get(prov, {}) or {}).get("keys", []):
                        if k.get("fingerprint") == fp:
                            return k
                    return {}

                rows = []
                for (prov, fp), u in _pm_used.items():
                    kh = _kh(prov, fp)
                    rows.append({
                        "provider": prov, "fingerprint": fp,
                        "success": u.get("success", 0),
                        "latency_ms_avg": int(u["lat_sum"] / u["n"]) if u.get("n") else 0,
                        "score": kh.get("score", 0.0), "status": kh.get("status", ""),
                    })
                _va_mod.flush_provider_key_usage({"tenant_id": _camp_tenant, "call_id": room_name}, rows)
        except Exception:  # noqa: BLE001
            pass
    ctx.add_shutdown_callback(_va_finish)

    # P2: managed provider layer (multi-key, health-scored selection + failover). FLAG-GATED
    # (PROVIDER_MANAGER_ENABLED, default OFF) + import-guarded. When OFF / unavailable / no managed
    # key configured, _resolve_key returns the LEGACY env key — BYTE-IDENTICAL to today. It can only
    # ever fall BACK to current behavior and NEVER raises into the call. _pm_fps records the chosen
    # fingerprint per provider so the metrics hook can feed success/latency health to the right key.
    _pm = None
    _pm_fps: dict = {}
    _pm_used: dict = {}   # P2.2: per-call key-usage tally {(provider, fp): {success, lat_sum, n}}
    if (os.getenv("PROVIDER_MANAGER_ENABLED", "0") or "0").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from voice_ops.config.router_bridge import get_key_router as _pm_get_router
            _pm = _pm_get_router(os.getenv("PLATFORM_TENANT_ID", "_platform"), is_admin=True)
        except Exception:  # noqa: BLE001
            _pm = None

    def _resolve_key(provider: str, legacy_fn):
        """Healthiest managed key for `provider`, else the LEGACY key (manager OFF/unavailable/empty).
        ALWAYS returns a usable key; never raises. Stashes the chosen fingerprint in _pm_fps."""
        if _pm is None:
            return legacy_fn()
        try:
            rk = _pm.resolve_key(provider)
            if getattr(rk, "found", False) and getattr(rk, "plaintext", ""):
                _pm_fps[provider] = getattr(rk, "fingerprint", "")
                return rk.plaintext
        except Exception:  # noqa: BLE001
            pass
        return legacy_fn()

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
        # W-INT-OUTBOUND (A4) — seam 4/4: COLD post-call kernel memory (W7). Writes
        # structured lead memory under the server-stamped tenant. OFF / _ik=None =>
        # no-op (the legacy mem.save_memory + transcript above are the only writers).
        # persist_post_call NEVER raises into this shutdown callback (earner-safe).
        if _ik is not None:
            try:
                _raw_summary = ""
                try:
                    _raw_summary = str((_summarize(turns) or {}).get("summary", ""))
                except Exception:  # noqa: BLE001
                    _raw_summary = ""
                await _vk.persist_post_call(
                    _ik, lead_phone=phone, turns=turns, name=lead_name,
                    raw_summary=_raw_summary,
                )
            except Exception as exc:  # noqa: BLE001 — COLD path, never break hangup
                logger.warning("kernel persist_post_call failed (non-fatal): %r", exc)

    ctx.add_shutdown_callback(_persist_memory)

    # P2: start TTS in the campaign's default language (Hinglish→'hi'); switched per-turn.
    _init_tts_lang = _intl_lang or (ld.tts_language_code(default_lang) if ld else "hi")
    # FIX C (BUG1 escalation knob): apply_text_normalization controls how ElevenLabs renders
    # numbers / proper-nouns / English-in-Devanagari. Default "auto" = today's behavior; the
    # bug-1 probe ladder can try "on" via EL_TEXT_NORM with NO code redeploy. Clamp to valid.
    _el_text_norm = os.getenv("EL_TEXT_NORM", "auto")
    if _el_text_norm not in ("auto", "on", "off"):
        _el_text_norm = "auto"
    # VERTICALS persona voice (ElevenLabs namespace). Empty {} unless a persona maps a REAL
    # EL voice for this call; today that is None, so this is a no-op fallback to fields/cfg/env.
    _vv_el = _verticals.resolve_voice(fields, "elevenlabs") if _verticals is not None else {}
    _el_tts = elevenlabs.TTS(
        api_key=_resolve_key("elevenlabs", lambda: os.environ["ELEVENLABS_API_KEY"]),
        voice_id=(_vv_el.get("voice_id") or fields.get("voice_id") or _voice_cfg("voice_id", "") or os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a")),
        model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
        # AUDIO-SMOOTHNESS (opt-in): default is the plugin's mp3_22050_32 (byte-identical to before).
        # Set EL_ENCODING=pcm_16000 (or pcm_8000, telephony-native) to skip mp3 decode + re-framing on
        # the worker — removes the micro-gaps that can make narrowband audio "break". Reverts via env.
        encoding=os.getenv("EL_ENCODING", "mp3_22050_32"),
        language=_init_tts_lang,
        apply_text_normalization=_el_text_norm,
        # Realtime-warm voice settings (verified from ElevenLabs docs):
        # low stability = expressive, style=0 (style adds 20-50ms), speaker_boost off.
        voice_settings=VoiceSettings(
            stability=float(_voice_cfg("el_stability", "") or os.getenv("EL_STABILITY", "0.45")),
            similarity_boost=float(_voice_cfg("el_similarity", "") or os.getenv("EL_SIMILARITY", "0.80")),
            style=float(_voice_cfg("el_style", "") or os.getenv("EL_STYLE", "0.0")),
            use_speaker_boost=((_voice_cfg("el_speaker_boost", "") or os.getenv("EL_SPEAKER_BOOST", "")).strip().lower() in ("1", "true", "yes", "on")),
            # VOICEFIX: nudge speaking rate up slightly. The opener (~30 words) took ~18s to
            # speak at 1.0 (~1.7 words/s — unnaturally slow for a phone agent). 1.08 trims every
            # utterance ~8% and feels snappier with no content change. Tune via EL_SPEED.
            speed=float(_voice_cfg("el_speed", "") or os.getenv("EL_SPEED", "1.08")),
        ),
        auto_mode=True,                          # sentence-level streaming = fast first audio
    )
    # TTS PROVIDER: default ElevenLabs. TTS_PROVIDER=sarvam => Sarvam Bulbul (India-hosted) — removes the
    # NA/EU->India transcontinental hop that jitters/under-runs the audio (the #1 controllable cause of
    # the "voice cutting/breaking" you hear). Bulbul is PRIMARY with ElevenLabs as automatic fallback, so
    # a Bulbul hiccup can NEVER silence the call. Instantly reversible: TTS_PROVIDER=elevenlabs.
    _tts_provider = (_voice_cfg("tts_provider", "") or os.getenv("TTS_PROVIDER", "elevenlabs")).strip().lower()
    tts = _el_tts
    if _tts_provider == "sarvam":
        try:
            # VERTICALS persona voice (Sarvam namespace): real Bulbul speaker + Indic language
            # for the selected persona/language. Empty {} unless FEATURE_VERTICALS + a vertical.
            _vv_sv = _verticals.resolve_voice(fields, "sarvam") if _verticals is not None else {}
            _bulbul = sarvam.TTS(
                target_language_code=(_vv_sv.get("sarvam_lang") or os.getenv("SARVAM_TTS_LANG", "hi-IN")),
                model=(_voice_cfg("sarvam_tts_model", "") or os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")),
                speaker=(_vv_sv.get("speaker") or _voice_cfg("sarvam_tts_speaker", "") or os.getenv("SARVAM_TTS_SPEAKER", "anushka")),
                api_key=_resolve_key("sarvam", _sarvam_key),
            )
            tts = _LkTTSFallback([_bulbul, _el_tts]) if _LkTTSFallback is not None else _bulbul
            logger.info("TTS: Sarvam Bulbul (%s/%s)%s",
                        os.getenv("SARVAM_TTS_MODEL", "bulbul:v2"), os.getenv("SARVAM_TTS_SPEAKER", "anushka"),
                        " + ElevenLabs fallback" if _LkTTSFallback is not None else "")
        except Exception as exc:  # noqa: BLE001 — Bulbul build failed -> ElevenLabs, never break the call
            logger.warning("Bulbul TTS build failed -> ElevenLabs: %r", exc)
            tts = _el_tts
    else:
        logger.info("TTS: ElevenLabs %s", os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"))
    ctl["tts"] = tts
    ctl["tts_code"] = _init_tts_lang             # FIX D: track the TTS's current language code

    # GROQ key round-robin: pick this CALL's key for the hot-path LLM (rotates across
    # GROQ_API_KEY/_2/_3 so concurrent calls spread load → less free-tier queueing/429).
    _call_groq_key = _resolve_key("groq", _next_groq_key)
    logger.info("groq key for this call: %s (pool=%d)", _mask_key(_call_groq_key), len(_all_groq_keys()))

    # Groq token-budget bookkeeping: at call end, attribute this call's Groq tokens to the key it rode
    # so the panel + the proactive-rotation skip (_key_over_budget) see today's per-key usage. The
    # FallbackAdapter may have failed over to a sibling key mid-call, but attributing to the primary
    # is the right signal for "this key is getting hammered today". Best-effort; off the speech path.
    async def _groq_budget_flush() -> None:
        try:
            _record_groq_call_tokens(_call_groq_key,
                                     int(usage.get("groq_in_tokens", 0) or 0),
                                     int(usage.get("groq_out_tokens", 0) or 0))
        except Exception:  # noqa: BLE001
            pass
    ctx.add_shutdown_callback(_groq_budget_flush)

    # STT provider switch (A/B): default Sarvam (best Hinglish). STT_PROVIDER=deepgram uses Deepgram
    # nova-3 'multi' (code-switching Hindi/English), which finalizes in ~0.3s vs Sarvam's ~1.2s — so
    # the turn-detect pause drops and the call feels far snappier. Falls back to Sarvam on ANY error
    # (incl. a missing DEEPGRAM_API_KEY or plugin), so the earner can never be broken by this.
    _stt = None
    # ANALYTICS-FIX: track the ACTUAL stt provider/model (the va.start below used to HARD-CODE "sarvam"
    # + "saarika:v2.5", so Deepgram calls were mislabeled as Sarvam in Voice Performance).
    _stt_prov, _stt_mdl = "sarvam", os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")
    if (_voice_cfg("stt_provider") or os.getenv("STT_PROVIDER", "sarvam")).strip().lower() == "deepgram":
        try:
            from livekit.plugins import deepgram as _dg  # noqa: PLC0415
            _stt = _dg.STT(
                api_key=_resolve_key("deepgram", lambda: _voice_cfg("deepgram_api_key") or os.environ["DEEPGRAM_API_KEY"]),
                model=os.getenv("DEEPGRAM_STT_MODEL", "nova-3"),
                language=os.getenv("DEEPGRAM_STT_LANG", "multi"),
            )
            _stt_prov = "deepgram"
            _stt_mdl = os.getenv("DEEPGRAM_STT_MODEL", "nova-3") + " (" + os.getenv("DEEPGRAM_STT_LANG", "multi") + ")"
            logger.info("STT: Deepgram %s/%s", os.getenv("DEEPGRAM_STT_MODEL", "nova-3"),
                        os.getenv("DEEPGRAM_STT_LANG", "multi"))
        except Exception as _dg_exc:  # noqa: BLE001 — no key/plugin -> Sarvam; never break the call
            logger.warning("Deepgram STT build failed -> Sarvam: %r", _dg_exc)
            _stt = None
    if _stt is None:
        # VOICEFIX: Sarvam auto-detect / code-mixed. "unknown" = detect language per utterance so ANY
        # language / code-mix is transcribed in its real script (forcing hi-IN garbled English words).
        _stt = sarvam.STT(
            api_key=_resolve_key("sarvam", _next_sarvam_key),
            language=os.getenv("SARVAM_STT_LANG", "unknown"),
            model=os.getenv("SARVAM_STT_MODEL", "saarika:v2.5"),
        )
        _stt_prov, _stt_mdl = "sarvam", os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")

    # Capture the built LLM so we can prewarm its ACTUAL plugin connection on turn-0 (the raw-httpx
    # prewarm only warmed Sarvam's server cache, not the socket — so turn-1 stayed cold ~0.9s).
    _call_llm = _build_call_llm(_call_groq_key,
                                model_override=((fields.get("llm_model") if isinstance(fields, dict) else "") or ""),
                                provider=((fields.get("llm_provider") if isinstance(fields, dict) else "") or ""))
    session = AgentSession(
        stt=_stt,
        # FREEZE-FIX (FF1): multi-key failover LLM (was a single-key groq.LLM bound to
        # _call_groq_key — the root cause of the booking freeze). _build_call_llm wraps one
        # groq.LLM PER key in a FallbackAdapter so a rate-limited key fails over instantly
        # instead of dead-air. Model/temperature/max_completion_tokens are unchanged (they
        # live inside _build_call_llm); GROQ_LLM_FALLBACK=0 reverts to the old single-key
        # path. See _build_call_llm for the full rationale + the CONCISE-BRAIN token cap.
        llm=_call_llm,
        tts=tts,
        # TURN-DETECTION latency knob: silero's default min_silence_duration (0.55s) IS the eou_delay
        # term you feel (NOT min/max_endpointing_delay). Default 0.55 = byte-identical; VAD_MIN_SILENCE=0.40
        # cuts ~150ms off every turn's turn-detection. Don't go below ~0.35 or it clips mid-thought pauses.
        vad=silero.VAD.load(min_silence_duration=float(os.getenv("VAD_MIN_SILENCE", "0.55") or 0.55)),
        # --- low-latency telephony tuning (defaults are far too slow) ---
        # VSE FIX 1c (knob): preemptive_generation starts the LLM before the turn is
        # finalized (faster first audio). It can re-run the opening generation on early
        # turns; default stays ON (=byte-identical latency). If the greeting still
        # restarts, set PREEMPTIVE_GEN=0 via the systemd drop-in and measure — no redeploy.
        preemptive_generation=(os.getenv("PREEMPTIVE_GEN", "1") not in ("0", "false", "False")),
        min_endpointing_delay=float(os.getenv("MIN_EP_DELAY", "0.25")),
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "0.45")),  # default ~6s!
        aec_warmup_duration=0.0,                     # default 3s start delay
        # INTERRUPTION TUNING: 0.25s was FAR too trigger-happy — a backchannel ("हां"/"अच्छा"), breath,
        # or line echo was cutting the agent's LLM generation mid-sentence (the "sentence incomplete"
        # bug: replies ended on a comma). Require sustained speech (0.6s) AND >=3 words to interrupt, so
        # short backchannels never cut the agent; resume_false_interruption RESUMES the sentence if a
        # false interrupt still slips through. A genuine interruption (sustained, multi-word) still works.
        min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.6")),
        min_interruption_words=int(os.getenv("MIN_INT_WORDS", "3") or 3),
        false_interruption_timeout=1.0,
        resume_false_interruption=(os.getenv("RESUME_FALSE_INT", "1") not in ("0", "false", "False")),
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
            # VSE FIX 6 (double-ending): if the LLM's OWN last assistant turn was ALREADY a
            # farewell, do NOT speak a second goodbye — just give it a beat to finish and end
            # the room. This kills the "two goodbyes" even when the assistant-turn closure path
            # fires right after the model said its own bye. The USER-turn trigger above normally
            # pre-empts the LLM, but this is the belt-and-braces guard for the book/assistant path.
            if _last_assistant_is_farewell(turns):
                logger.info("P2 closure: LLM already said goodbye -> skip 2nd, end cleanly")
                await asyncio.sleep(1.2)
                return
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
                # FREEZE-FIX: bound the wait so a stalled TTS playout can NEVER hang the close
                # forever (which would leave the room open = dead air). On timeout we proceed to
                # delete_room anyway. Tunable via CLOSE_PLAYOUT_TIMEOUT (default 12s).
                await asyncio.wait_for(handle.wait_for_playout(),
                                       timeout=float(os.getenv("CLOSE_PLAYOUT_TIMEOUT", "12")))
            except Exception:  # noqa: BLE001 (incl. asyncio.TimeoutError + handle API differences)
                await asyncio.sleep(2.5)             # fallback grace
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
                # VSE FIX 6 (double-ending): trigger the closure on the USER's closing turn
                # (e.g. "bye"/"बाय"/opt-out) so our single warm goodbye fires BEFORE the LLM
                # composes its own farewell — and the closure's say(allow_interruptions=False)
                # interrupts any LLM goodbye-in-progress, so only ONE goodbye is ever spoken.
                # We still keep the assistant-turn trigger for the 'book' (agreed-next-step)
                # path, where the user said only "haan" and the closing signal lives in the
                # surrounding context — but we do NOT double-fire (ctl["closing"] guards it).
                if loop is not None and not ctl["closing"]:
                    try:
                        # The ONLY close trigger here: the agent SIGNED OFF on its own (a strong
                        # end-of-call line) -> end the call. We deliberately do NOT fire on a
                        # detected 'book' signal — that mis-fired when the agent merely ASKED
                        # "site visit?" and spoke a canned "booking confirmed" outro as if the
                        # caller had agreed ("she said yes herself"). A real booking now closes
                        # naturally: the agent confirms + says its own warm outro -> this fires ->
                        # _confirm_then_hangup sees the farewell already said -> clean delete_room,
                        # no 2nd/canned goodbye. (opt-out/bye are owned by on_user_turn_completed.)
                        if role == "assistant" and any(m in (text or "").lower() for m in _STRONG_OUTRO):
                            asyncio.run_coroutine_threadsafe(_confirm_then_hangup("book"), loop)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    # P1 voice analytics: create the per-call recorder now the call context is resolved (no-op
    # unless VOICE_ANALYTICS_ENABLED + a ClickHouse write URL are set). _va is closed over by the
    # shutdown flush + the metrics hook below.
    # ANALYTICS-FIX: resolve the ACTUAL leading LLM provider+model (was hardcoded "groq" + a stale
    # fields.llm_model → every call mislabeled as Groq-70B even when Sarvam answered). Mirror
    # _build_call_llm precedence (global voice-config > per-campaign field > env). Used by the
    # analytics row AND the per-turn provider-health feed below so BOTH report the real provider.
    _an_prov = ((_voice_cfg("llm_provider", "") or
                 (fields.get("llm_provider") if isinstance(fields, dict) else "") or
                 os.getenv("LLM_PROVIDER", "") or "groq").strip().lower())
    if _an_prov == "sarvam":
        _an_model = (_voice_cfg("sarvam_model", "") or os.getenv("SARVAM_LLM_MODEL", "") or "sarvam-30b")
    elif _an_prov == "cerebras":
        _an_model = (os.getenv("CEREBRAS_LLM_MODEL", "") or "gpt-oss-120b")
    elif _an_prov == "sambanova":
        _an_model = (os.getenv("SAMBANOVA_LLM_MODEL", "") or "sambanova")
    else:  # groq (default)
        _an_model = ((fields.get("llm_model") if isinstance(fields, dict) else "") or
                     os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile"))
    if _va_mod is not None:
        try:
            _va = _va_mod.start(
                call_id=room_name, tenant_id=_camp_tenant, campaign_id=campaign_id,
                agent_name=((fields.get("agent_name") if isinstance(fields, dict) else "") or AGENT_NAME),
                phone=phone, lead_name=lead_name,
                stt_provider=_stt_prov, llm_provider=_an_prov, tts_provider=_tts_provider,
                stt_model=_stt_mdl,
                llm_model=_an_model,
                tts_model=(os.getenv("SARVAM_TTS_MODEL", "bulbul:v2") if _tts_provider == "sarvam"
                           else os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")),
                voice_id=((fields.get("voice_id") if isinstance(fields, dict) else "")
                          or os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a")),
                language=str(default_lang or ""),
            )
        except Exception:  # noqa: BLE001
            _va = None

    # Network / TELECOM latency (phone leg): best-effort capture of LiveKit connection quality AND, when
    # the SDK exposes it, the real RTP round-trip time → voice analytics ("Telecom" column). The handler
    # is fully guarded; arg order + the rtt attribute name vary by livekit version, so we sniff both the
    # quality enum and any rtt-like field. Never affects the call.
    if _va is not None:
        try:
            def _extract_rtt_ms(obj) -> float:
                """Real RTT in ms from a LiveKit object, across SDK versions. 0.0 when not present.
                A value < 10 is treated as SECONDS and scaled to ms (LiveKit reports rtt in seconds)."""
                for attr in ("rtt", "round_trip_time", "rtt_ms", "rtt_seconds", "rttMs"):
                    try:
                        v = getattr(obj, attr, None)
                        if v is None and isinstance(obj, dict):
                            v = obj.get(attr)
                        if v:
                            f = float(v)
                            if f > 0:
                                return f * 1000.0 if f < 10 else f
                    except Exception:  # noqa: BLE001
                        continue
                return 0.0

            def _on_conn_quality(*args) -> None:  # noqa: ANN002
                try:
                    nm = ""
                    rtt_ms = 0.0
                    for a in args:
                        q = getattr(a, "name", None)
                        if q and str(q).upper() in ("EXCELLENT", "GOOD", "POOR", "LOST"):
                            nm = q
                        r = _extract_rtt_ms(a)
                        if r > rtt_ms:
                            rtt_ms = r
                    if nm or rtt_ms:
                        _va.set_network(quality=nm, rtt_ms=int(rtt_ms))
                except Exception:  # noqa: BLE001
                    pass
            ctx.room.on("connection_quality_changed", _on_conn_quality)
        except Exception:  # noqa: BLE001
            pass

    # Per-turn latency breakdown: EOU (end-of-utterance) + LLM ttft + TTS ttfb.
    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:  # noqa: ANN001
        try:
            m = ev.metrics
            t = type(m).__name__
            if _va is not None:
                _va.record(t, m)
            # P2: feed success + latency health to the managed provider router (no-op fp '' is safe)
            # and tally per-key usage for the call-end flush (P2.2). STTMetrics.audio_duration is the
            # USER's speech length, NOT STT latency — so STT reports success WITHOUT latency (feeding
            # audio_duration would pollute the EWMA and wrongly tank Sarvam's score; do not "fix").
            if _pm is not None:
                try:
                    prov, lat = "", 0.0
                    if t == "LLMMetrics":
                        prov, lat = _an_prov, float(getattr(m, "ttft", 0) or 0) * 1000
                    elif t == "TTSMetrics":
                        prov, lat = _tts_provider, float(getattr(m, "ttfb", 0) or 0) * 1000
                    elif t == "STTMetrics":
                        prov = _stt_prov
                    if prov:
                        fp = _pm_fps.get(prov, "")
                        _pm.report_success(prov, fp, latency_ms=lat)
                        u = _pm_used.setdefault((prov, fp), {"success": 0, "lat_sum": 0.0, "n": 0})
                        u["success"] += 1
                        if lat > 0:
                            u["lat_sum"] += lat
                            u["n"] += 1
                except Exception:  # noqa: BLE001
                    pass
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
        def tts_node(self, text, model_settings):  # noqa: ANN001
            # (1) DETERMINISTIC de-emphasis: ElevenLabs raises pitch/volume on '!' -> replace with ','.
            # (2) RE-INTRO STRIP: buffer the leading sentence and drop a self-intro ("Namaste / Main
            #     Priya bol rahi hoon") on POST-opener turns (Sarvam's reflex). Gated by _spoke_intro
            #     (set after the opener) + REINTRO_STRIP env. Then delegate to the default TTS node.
            do_strip = (getattr(self, "_spoke_intro", False)
                        and os.getenv("REINTRO_STRIP", "1") not in ("0", "false", "False"))
            sanitize = os.getenv("REPLY_SANITIZE", "1") not in ("0", "false", "False")

            # ANTI-REPEAT (deterministic): if a reply is a near-verbatim repeat of a recent one, speak a
            # short re-steer instead of looping. Sarvam ignores the brain's anti-repeat rule, so code
            # enforces it. Only substantive lines (>=20 chars), matched on a 40-char prefix; short acks
            # ("जी"/"हाँ") can repeat freely. Gated by ANTI_REPEAT.
            def _antirep(out: str) -> str:
                if not out or os.getenv("ANTI_REPEAT", "1") in ("0", "false", "False"):
                    return out
                norm = _re.sub(r"\s+", " ", _MD.sub("", out)).strip().lower()
                if len(norm) < 20:
                    return out
                k = norm[:40]
                recent = getattr(self, "_recent_keys", [])
                if k in recent:
                    idx = getattr(self, "_repeat_n", 0)
                    self._repeat_n = idx + 1
                    out = _ANTI_REPEAT_LINES[idx % len(_ANTI_REPEAT_LINES)]
                    k = _re.sub(r"\s+", " ", out).strip().lower()[:40]
                    logger.info("anti-repeat fired -> re-steer")
                self._recent_keys = (recent + [k])[-4:]
                return out

            async def _proc():
                # Buffer the full reply, then clean it (cut scripted next-turns, drop markdown, strip a
                # leading self-intro) before TTS. Buffering a SHORT capped reply costs ~0.3-0.5s but is
                # the only reliable way to kill the '**Riya:** ...547-token script' failure. '!'->','.
                buf = []
                said = False
                async for chunk in text:
                    if isinstance(chunk, str):
                        buf.append(chunk)
                        continue
                    if buf:
                        out = (_clean_reply("".join(buf), do_strip) if sanitize else "".join(buf)).replace("!", ",")
                        out = _antirep(out)
                        if out:
                            yield out
                            said = True
                        buf = []
                    yield chunk
                if buf:
                    out = (_clean_reply("".join(buf), do_strip) if sanitize else "".join(buf)).replace("!", ",")
                    out = _antirep(out)
                    if out:
                        yield out
                        said = True
                # ANTI-SILENCE: the LLM produced nothing speakable (empty / 0-token reply) — speak a short
                # natural filler instead of dead air (the caller would otherwise hear silence + say "Hello?").
                if not said and os.getenv("ANTI_SILENCE", "1") not in ("0", "false", "False"):
                    yield os.getenv("EMPTY_REPLY_FILLER", "जी, बताइए।")
            return Agent.default.tts_node(self, _proc(), model_settings)

        async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # noqa: ANN001
            try:
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
                # --- CLOSE handling FIRST (runs before the LLM reply; works even if langdetect
                # is absent). This is the single owner of opt-out/bye; conversation_item_added
                # only closes on a confirmed BOOK, so there is no double-fire. ---
                low = str(txt).lower()
                if not ctl["closing"]:
                    # BC1 wind-down: after a booking the agent asked "anything else?" — a "no"
                    # now means we're done -> warm booking goodbye + hang up (no dangling silence).
                    if ctl.get("post_booking") and _is_post_book_no(low):
                        await _confirm_then_hangup("book")
                        return
                    if any(k in low for k in _CLOSE_OPTOUT):
                        await _confirm_then_hangup("no")        # not interested/opt-out -> respect, close now
                        return
                    if any(k in low for k in _CLOSE_BYE):
                        if ctl.get("close_offered"):
                            await _confirm_then_hangup("no")    # 2nd bye -> warm outro + auto-hangup
                            return
                        ctl["close_offered"] = True             # 1st bye -> FORCE one booking/callback offer
                        try:
                            turn_ctx.add_message(role="system", content=_BYE_OFFER_NOTE)
                        except Exception:  # noqa: BLE001
                            pass
                        return                                   # let the LLM speak the offer this turn
                if ld is None:
                    return
                # DIRECT per-turn language override (the proven mirror fix): classify THIS turn
                # itself — NOT the sticky LanguageTracker, whose hysteresis lags an English switch
                # by ≥1 turn, which is exactly why English callers kept getting Hindi. classify_text
                # tags real English at conf 0.9-1.0, so a confident English turn now forces an
                # English reply immediately. (Tracker still drives the TTS voice switch below.)
                try:
                    _cur_lang, _cur_conf = ld.classify_text(str(txt))
                except Exception:  # noqa: BLE001
                    _cur_lang, _cur_conf = "", 0.0
                # STICKY English: fire on a confident English turn (conf>=0.5) OR when English is
                # already the active language and this turn isn't a clear Hindi switch. This keeps
                # the reply in English on short/garbled turns ('Two BHK', 'O BHK one') that the
                # per-turn classifier can't score — the caller's language must persist, not flap.
                _active_lang = lang_tracker.active if lang_tracker is not None else ""
                # SYMMETRIC per-turn steering. BUGFIX: previously only English was ever forced, so once
                # English went sticky a Hindi/Hinglish turn never switched back (caller spoke Hindi, agent
                # kept replying English). Now a confident turn in EITHER direction switches immediately;
                # only ambiguous/short turns keep the active language.
                _is_eng = (_cur_lang == "english" and _cur_conf >= 0.5)
                _is_hin = (_cur_lang in ("hindi", "hinglish") and _cur_conf >= 0.5)
                # VERTICALS international fixed-language mode: skip ALL langdetect steering (it would
                # misread the world language as English and flip the call). The prompt directive
                # already tells the LLM to converse in the campaign's language. Legacy: _intl_pin=False.
                _want = "" if _intl_pin else ("english" if _is_eng
                         else "hindi" if _is_hin
                         else ("english" if _active_lang == "english" else ""))
                if _want == "english":
                    try:
                        turn_ctx.add_message(role="system", content=_strong_lang_note("english"))
                        # ALSO a blunt user-side aside — the position a 17B model attends to MOST.
                        turn_ctx.add_message(
                            role="user",
                            content="(Reply to this in ENGLISH only — no Hindi words, no Devanagari.)")
                        logger.info("lang directive -> english (cur=%s conf=%.2f active=%s)",
                                    _cur_lang, _cur_conf, _active_lang)
                    except Exception:  # noqa: BLE001
                        pass
                elif _want == "hindi":
                    try:
                        turn_ctx.add_message(role="system", content=_strong_lang_note("hindi"))
                        turn_ctx.add_message(
                            role="user",
                            content="(Reply to this in HINDI / Hinglish — Devanagari, jaise caller abhi bol raha hai.)")
                        if lang_tracker is not None:
                            try:
                                lang_tracker.active = "hindi"   # break English stickiness for next turns
                            except Exception:  # noqa: BLE001 — active may be read-only; per-turn directive still switches
                                pass
                        logger.info("lang directive -> hindi (cur=%s conf=%.2f active=%s)",
                                    _cur_lang, _cur_conf, _active_lang)
                    except Exception:  # noqa: BLE001
                        pass
                # W-INT-OUTBOUND (A4) — seam 3/4: SOFT per-turn kernel RAG suffix (W4).
                # Runs each turn once the turn text is read. OFF / _ik=None => skipped
                # entirely (legacy turn unchanged). ON => on_turn (its OWN hard deadline +
                # try/except, never blocks) may return a small RAG suffix, appended as a
                # USER-side aside (role="user") — NEVER a role="system" command, so it can
                # never override the LLM. Wrapped so a kernel fault never breaks the turn.
                # Placed BEFORE the language branches because those early-return; the kernel
                # hook must run on every turn. The A1 language detection still owns the
                # reply-language note below; this only injects retrieved knowledge.
                if _ik is not None:
                    try:
                        _detected = ""
                        try:
                            _dl, _dc = ld.classify_text(str(txt)) if ld is not None else ("", 0.0)
                            _detected = _dl if _dc >= 0.55 else ""
                        except Exception:  # noqa: BLE001
                            _detected = ""
                        _kt = await _vk.on_turn(_ik, user_text=str(txt), detected_lang=_detected)
                        _rag = (_kt or {}).get("rag_suffix")
                        if _rag:
                            try:
                                turn_ctx.add_message(role="user", content=_rag)
                            except Exception:  # noqa: BLE001
                                pass
                    except Exception as _kt_exc:  # noqa: BLE001 — kernel never breaks a turn
                        logger.warning("kernel on_turn failed (non-fatal): %r", _kt_exc)
                # FIX D (BUG2): V2 = ONE detector drives BOTH the LLM reply-language note AND
                # the TTS code, in sync, for all 4 languages, ONLY on an actual switch (incl.
                # switching BACK to Hindi). Cache-safe: the note is appended AFTER the cached
                # prefix; on steady-state (no switch) NOTHING is added → zero token cost on the
                # dominant Hindi/Hinglish path. This is the single source of truth — the
                # conversation_item_added V1 path is disabled when V2 is on.
                if _lang_v2 and lang_tracker is not None:
                    # A1: on SHORT fragments ("haan", "ok", "ji") do NOT re-classify —
                    # a 1-2 word turn carries almost no language signal and the old
                    # detector would mis-flip it (often defaulting toward English). CARRY
                    # the prior confirmed language instead (tracker.active is unchanged),
                    # and only re-emit a hint when that carried language is english (so the
                    # model doesn't drift back to Hindi on a bare "ok"). Never default to EN.
                    if len(str(txt).split()) < 4:
                        carried = lang_tracker.active
                        if carried == "english":
                            try:
                                turn_ctx.add_message(role="system", content=_strong_lang_note(carried))
                            except Exception:  # noqa: BLE001
                                pass
                        return
                    new_lang, switched = lang_tracker.update(str(txt))
                    # FORCEFUL per-turn language override (role=system). The soft user-aside hint
                    # was demonstrably ignored by scout-17b under the all-Hindi prompt, so for a
                    # non-default language (always for English, on switch for others) we issue an
                    # explicit scoped command for THIS turn only. Cache-safe: appended after the
                    # cached prefix, never on the dominant Hinglish path → no TTFT spike there.
                    # English is handled by the DIRECT per-turn injector above; Hindi/Hinglish are
                    # the default (the prompt is already Hindi) so they need NO override. Only steer
                    # OTHER languages (gujarati/marathi/…) on a confirmed switch — minimises the
                    # extra system messages that can confuse the 17B model.
                    # LANG-ALLOWLIST (Punjabi-switch fix): Riya's TTS + brain are Hindi/English
                    # (Hinglish) only. The tracker sometimes mis-tags a Hinglish turn as Punjabi/
                    # Marathi/etc., which then made her actually REPLY + SPEAK that language (the live
                    # "switched to Punjabi" bug). Only ever mirror to english or hindi/hinglish; for ANY
                    # other detected language, IGNORE the switch and stay in the campaign default —
                    # never steer the model or the TTS into a language we don't support.
                    if switched and new_lang not in ("hinglish", "english", "hindi"):
                        return
                    if switched and new_lang == "english":
                        try:
                            turn_ctx.add_message(role="system", content=_strong_lang_note(new_lang))
                        except Exception:  # noqa: BLE001
                            pass
                    if switched:
                        try:
                            await _apply_language_switch(new_lang)
                        except Exception:  # noqa: BLE001
                            pass
                        logger.info("lang mirror v2 -> %s (switched; soft hint + TTS synced)", new_lang)
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

    # A3: booking voice-tool — attached ONLY when booking_tool_enabled() (KERNEL_OUTBOUND=1
    # AND BOOKING_TOOL_ENABLED=1). DEFAULT OFF => _MirrorAgent(instructions=...) is built with
    # NO tools, byte-identical to today. ON => one extra @function_tool the LLM can call to book
    # a real appointment in-process (RLS-scoped, no HTTP). Fully wrapped; never breaks the call.
    _booking_tools: list = []
    if booking_tool_enabled():
        try:
            _bk_tenant = _camp_tenant
            _bk_phone = phone
            _bk_name = lead_name
            _bk_campaign = campaign_id

            @_lk_function_tool
            async def book_appointment(context: "_LkRunContext", when: str) -> str:  # noqa: F821
                """Book the prospect's site-visit / meeting AFTER they verbally agree a day & time.
                Only call this once the caller has clearly agreed to a specific slot.

                Args:
                    when: the slot the caller agreed, in their words (e.g. "kal sham 5 baje",
                          "tomorrow 11am", "Friday evening") or an ISO datetime if known.
                """
                try:
                    res = await asyncio.to_thread(
                        _do_booking, _bk_tenant, _bk_phone, when_text=when,
                        name=_bk_name, campaign_id=_bk_campaign,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("book_appointment tool error: %r", exc)
                    return ("booking_failed: I couldn't lock that slot just now — tell the caller "
                            "you'll confirm the appointment shortly; do NOT claim it is booked.")
                if res and res.get("ok"):
                    return ("booked=true: the appointment is confirmed. Warmly confirm the day & time "
                            "back to the caller in their language.")
                reason = str((res or {}).get("reason", "")) or "unknown"
                if reason == "slot_taken":
                    return ("slot_taken: that exact time is already booked — politely offer a nearby "
                            "time and call book_appointment again with the new time.")
                if reason in ("bad_slot",):
                    return ("need_time: I didn't catch an exact day & time — ask the caller to confirm "
                            "a specific day and time, then call book_appointment again.")
                # no_resource / not_configured / errors -> never fake a booking
                return ("booking_unavailable: do NOT tell the caller it is booked — say you'll confirm "
                        "the appointment shortly and continue the conversation naturally.")

            _booking_tools = [book_appointment]
            logger.info("A3 booking tool ATTACHED (tenant=%s)", _bk_tenant)
        except Exception as _bt_exc:  # noqa: BLE001 — tool wiring never breaks the earner
            logger.warning("A3 booking tool wiring failed -> no tool: %r", _bt_exc)
            _booking_tools = []

    # R5VF: booking voice-tool over the caller.py HTTP contract — attaches on the LIVE
    # P0 brain (KERNEL_OUTBOUND=0), where the in-process tool above cannot. Only when
    # BOOKING_HTTP_ENABLED=1 (default OFF => byte-identical to today) AND no tool already
    # attached. The LLM calls book_site_visit(when, notes) once the caller agrees a slot;
    # it POSTs to 127.0.0.1:8209/booking/book and confirms naturally. Fully wrapped.
    if not _booking_tools and booking_http_tool_enabled():
        try:
            _bkh_phone = phone
            _bkh_name = lead_name
            _bkh_campaign = meta.get("campaign_id", "") or ""

            @_lk_function_tool
            async def book_site_visit(context: "_LkRunContext", when: str,
                                      notes: str = "") -> str:  # noqa: F821
                """Book the prospect's site visit / meeting AFTER they verbally agree a day & time.
                Only call this once the caller has clearly agreed to a specific slot.

                Args:
                    when: the slot the caller agreed, in their words (e.g. "kal sham 5 baje",
                          "tomorrow 5pm", "Friday evening") or an ISO datetime if known.
                    notes: any short context to attach (optional, e.g. "wants 3 BHK, self-use").
                """
                try:
                    res = await asyncio.to_thread(
                        _do_booking_http, _bkh_phone, when_text=when,
                        lead_name=_bkh_name, campaign_id=_bkh_campaign, notes=notes,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("book_site_visit tool error: %r", exc)
                    return ("booking_failed: I couldn't lock that slot just now — tell the caller "
                            "you'll confirm the appointment shortly; do NOT claim it is booked.")
                if res and res.get("ok"):
                    return ("booked=true: the site visit is confirmed. Warmly confirm the day & time "
                            "back to the caller in their language, in one short line.")
                reason = str((res or {}).get("reason", "")) or "unknown"
                if reason == "slot_taken":
                    return ("slot_taken: that exact time is already booked — politely offer a nearby "
                            "time and call book_site_visit again with the new time.")
                if reason == "bad_slot":
                    return ("need_time: I didn't catch an exact day & time — ask the caller to confirm "
                            "a specific day and time, then call book_site_visit again.")
                # no_phone / http_* / post_error -> never fake a booking
                return ("booking_unavailable: do NOT tell the caller it is booked — say you'll confirm "
                        "the appointment shortly and continue the conversation naturally.")

            _booking_tools = [book_site_visit]
            logger.info("R5VF http booking tool ATTACHED (phone=%s campaign=%s)",
                        _bkh_phone, _bkh_campaign)
        except Exception as _bth_exc:  # noqa: BLE001 — tool wiring never breaks the earner
            logger.warning("R5VF http booking tool wiring failed -> no tool: %r", _bth_exc)
            _booking_tools = []

    # BC1: DEFAULT fast-capture booking tool — attaches when no heavier booking path above is
    # active AND BOOKING_CAPTURE_ENABLED!=0. Speaks a "booking now, one moment" filler (no more
    # silent waits), durably captures the agreed slot, sets ctl["post_booking"] so the wind-down
    # close can fire on a simple "no", and instructs the LLM to confirm + ask "anything else?".
    if not _booking_tools and booking_capture_enabled():
        try:
            _bc_tenant = _camp_tenant
            _bc_phone = phone
            _bc_name = lead_name
            _bc_campaign = (meta.get("campaign_id", "") if isinstance(meta, dict) else "") or campaign_id or ""

            @_lk_function_tool
            async def book_site_visit(context: "_LkRunContext", when: str,  # noqa: F811,F821
                                      notes: str = "") -> str:
                """Book the prospect's site visit AFTER they verbally agree a day & time.
                Only call this once the caller has clearly agreed to a specific slot.

                Args:
                    when: the slot the caller agreed, in their words (e.g. "kal sham 5 baje",
                          "tomorrow 5pm", "Thursday after 12") or an ISO datetime if known.
                    notes: any short context to attach (optional, e.g. "wants 3 BHK, self-use").
                """
                # FILLER FIRST: never leave the caller in silence while we book.
                try:
                    session.say(_booking_filler_line(agent_gender), allow_interruptions=False)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    res = await asyncio.to_thread(
                        _capture_booking, tenant_id=_bc_tenant, phone=_bc_phone,
                        lead_name=_bc_name, when_text=when, campaign_id=_bc_campaign,
                        notes=notes, room=room_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("book_site_visit(capture) tool error: %r", exc)
                    return ("booking_failed: I couldn't lock that slot just now — tell the caller "
                            "you'll confirm the appointment shortly; do NOT claim it is booked.")
                if res and res.get("ok"):
                    ctl["post_booking"] = True
                    return ("booked=true: the site visit is confirmed. In ONE short, warm, natural "
                            "line, confirm the day & time back to the caller in their language, add "
                            "that your team will send the details on WhatsApp and you'll see them at "
                            "the visit — then a warm goodbye and STOP. Do NOT ask 'anything else', "
                            "do NOT keep the call going.")
                return ("booking_unavailable: do NOT tell the caller it is booked — say you'll "
                        "confirm the appointment shortly and continue the conversation naturally.")

            _booking_tools = [book_site_visit]
            logger.info("BC1 capture booking tool ATTACHED (tenant=%s phone=%s)",
                        _bc_tenant, _bc_phone)
        except Exception as _bc_exc:  # noqa: BLE001 — tool wiring never breaks the earner
            logger.warning("BC1 capture booking tool wiring failed -> no tool: %r", _bc_exc)
            _booking_tools = []

    # BOOKING guidance — added IFF a booking tool actually attached (HTTP or capture), so the
    # prompt and the attached tool can never disagree. When no tool attached this is a no-op =>
    # instructions byte-identical to today. (The book_site_visit name covers both the capture +
    # HTTP paths; the niche A3 in-process path supplies its own kernel-assembled instructions.)
    if _booking_tools:
        instructions += (
            "\n\n=== BOOKING (site visit) ===\n"
            "तुम्हारे पास एक tool है `book_site_visit(when, notes)`। जब caller किसी concrete दिन-समय "
            "पर site visit के लिए साफ़ राज़ी हो जाए (जैसे 'कल शाम पाँच बजे', 'tomorrow 5pm', 'Thursday "
            "after 12'), तभी यह tool call करो — caller के बोले हुए time को 'when' में उसके अपने शब्दों "
            "में भेजो। पहले खुद से booked मत कह देना; tool के नतीजे के बाद ही एक ही warm line में naturally "
            "confirm करके बात गर्मजोशी से ख़त्म करो (team WhatsApp पर details भेज देगी, site पर मिलते हैं) — "
            "'और कुछ help चाहिए?' दोबारा मत पूछो, बात को खींचो मत।")

    # ── TOLEX: agent tooling & capability system (FLAG-GATED TOLEX_ENABLED, default OFF). When ON and
    # the campaign has granted tools, build dynamic LiveKit function-tools wrapped in the Tolex policy
    # engine + audit (tolex.execute). DEFAULT OFF / no grants => _tolex_tools is empty and the agent is
    # byte-identical to today. EVERY step is guarded: any failure => no Tolex tools, never breaks the call.
    _tolex_tools: list = []
    try:
        import tolex as _tolex  # noqa: E402
    except Exception:  # noqa: BLE001
        _tolex = None
    if _tolex is not None and _lk_function_tool is not None and _tolex.enabled():
        try:
            _tx_campaign = (meta.get("campaign_id", "") if isinstance(meta, dict) else "") or campaign_id or ""

            def _tx_book(when: str, notes: str = "") -> dict:  # reuse the real BC1 capture path
                try:
                    return _capture_booking(tenant_id=_camp_tenant, phone=phone, lead_name=lead_name,
                                            when_text=when, campaign_id=_tx_campaign, notes=notes,
                                            room=room_name) or {}
                except Exception:  # noqa: BLE001
                    return {}

            _tx_ctx = {"campaign_id": _tx_campaign, "tenant_id": _camp_tenant, "phone": phone,
                       "lead_name": lead_name, "call_id": room_name, "book_fn": _tx_book}

            def _mk_tolex_tool(_spec, _ctx):
                """Build ONE dynamic function tool from a Tolex catalog spec. The handler runs
                tolex.execute (policy + audit) off-thread and returns its result string to the LLM."""
                _key = _spec["key"]

                async def _tx_handler(*a, **kw):  # tolerate LiveKit's raw-args calling conventions
                    _args = None
                    if isinstance(kw.get("raw_arguments"), dict):
                        _args = kw["raw_arguments"]
                    else:
                        for _x in a:
                            if isinstance(_x, dict):
                                _args = _x
                                break
                        if _args is None:
                            _args = {k: v for k, v in kw.items() if k not in ("context", "ctx", "raw_arguments")}
                    try:
                        _res = await asyncio.to_thread(_tolex.execute, _key, _args or {}, _ctx)
                        return _res.get("llm") or "done"
                    except Exception as _he:  # noqa: BLE001
                        logger.warning("tolex tool %s exec error: %r", _key, _he)
                        return "tool_failed: tell the caller the team will follow up; do NOT claim it's done."

                return _lk_function_tool(
                    _tx_handler,
                    raw_schema={"type": "function", "name": _key,
                                "description": _spec.get("llm_description") or _spec.get("description") or _key,
                                "parameters": _spec.get("params") or {"type": "object", "properties": {}}},
                )

            _tx_names: list = []
            for _spec, _grant in _tolex.granted_tools(_camp_tenant, _tx_campaign):
                _k = _spec.get("key")
                if not _k:
                    continue
                if _booking_tools and _k == "book_site_visit":
                    continue  # the dedicated booking tool already covers this
                try:
                    _obj = _mk_tolex_tool(_spec, dict(_tx_ctx))
                except Exception as _be:  # noqa: BLE001
                    logger.warning("tolex tool build failed key=%s: %r", _k, _be)
                    _obj = None
                if _obj is not None:
                    _tolex_tools.append(_obj)
                    _tx_names.append(_spec.get("name", _k))

            if _tolex_tools:
                instructions += (
                    "\n\n=== AGENT TOOLS (Tolex) ===\n"
                    "You can take real actions with these tools: " + ", ".join(_tx_names) + ". "
                    "Call a tool ONLY when the caller's intent clearly calls for it, and use the caller's own "
                    "words for free-text arguments. For anything sensitive (sending messages, money, transfers) "
                    "confirm the key detail with the caller in ONE short line BEFORE calling the tool. After a "
                    "tool returns, act on its result text: never claim something is done if the result says it is "
                    "queued, needs approval, or unavailable — in those cases tell the caller the team will follow up.")
                logger.info("TOLEX tools ATTACHED (%d): %s", len(_tolex_tools), ", ".join(_tx_names))
        except Exception as _tx_exc:  # noqa: BLE001 — tooling never breaks the earner
            logger.warning("TOLEX wiring failed -> no tolex tools: %r", _tx_exc)
            _tolex_tools = []

    # P2: capture the running loop + agent so the sync conversation callback can hand
    # async work (language switch / closure) back to this event loop.
    _all_tools = (_booking_tools or []) + (_tolex_tools or [])
    agent = (
        _MirrorAgent(instructions=instructions, tools=_all_tools)
        if _all_tools else _MirrorAgent(instructions=instructions)
    )
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

    # PRE-WARM (turn-1 latency fix): the moment the call connects, fire a tiny throwaway completion to
    # warm Groq's prompt cache for THIS call's (key, model, system-prompt). It runs in the BACKGROUND
    # while the opener is generated + spoken (~3-5s), so the caller's first real turn hits a HOT cache
    # (~0.4s) instead of the cold ~1.2s prefix cost (the persistent "#1 slow, #2+ fast" pattern).
    # Gated (LLM_PREWARM=0 to disable), best-effort — never blocks or breaks the call.
    if os.getenv("LLM_PREWARM", "1") not in ("0", "false", "False"):
        try:
            # Warm the ACTUAL session LLM connection (works for whichever provider is primary). This is
            # what cuts the cold first turn — the old raw-httpx prewarm warmed only the server cache.
            asyncio.create_task(_prewarm_llm_conn(_call_llm, instructions))
        except Exception:  # noqa: BLE001 — prewarm scheduling never breaks the call
            pass

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
        purpose=str(fields.get("opener_purpose") or "").strip(),
    )
    logger.info("opener: %s", opener[:200])
    # FIX A (BUG3): by livekit default, session.say() text is fed back into the LLM chat
    # context as a prior assistant turn — so the model SEES its own opener and (told by the
    # prompt to "open with a greeting") re-greets on turn 1. OPENER_IN_CTX=0 suppresses that
    # echo so there is no greeting for the model to repeat; the system-prompt persona still
    # holds its identity for "kaun bol raha hai?". Default "1" = byte-identical. Reversible.
    _opener_in_ctx = os.getenv("OPENER_IN_CTX", "1") not in ("0", "false", "False")
    # VSE FIX 5 (hello-collision): give the SIP/RTP path a moment to settle after
    # session.start() before the opener plays, so the agent's greeting does not collide
    # with the callee's own opening "hello?". Tunable via OPENER_DELAY_S (default 0.8s).
    # The opener is spoken with allow_interruptions=False so a half-second of callee
    # speech can't truncate the greeting (the single clean opener must finish).
    try:
        await asyncio.sleep(float(os.getenv("OPENER_DELAY_S", "0.8")))
    except Exception:  # noqa: BLE001
        pass
    await session.say(opener, allow_interruptions=False, add_to_chat_ctx=_opener_in_ctx)
    # TRANSCRIPT FIX: record the opener as the FIRST transcript turn. When OPENER_IN_CTX=0 (set to stop
    # the model re-greeting) say() does NOT fire conversation_item_added, so the intro was missing from
    # the transcript — which also shifted the transcript out of sync with the audio (audio had the opener
    # at 0:00, transcript started with the caller). Insert it at position 0, idempotently (no dup if
    # OPENER_IN_CTX=1 already added it).
    try:
        if not any(t.get("role") == "assistant" and t.get("content") == opener for t in turns):
            turns.insert(0, {"role": "assistant", "content": opener})
    except Exception:  # noqa: BLE001 — transcript bookkeeping never breaks the call
        pass
    # Opener (the ONE intentional self-introduction) is done — from now on tts_node strips any
    # reflexive re-introduction from the LLM's replies (Sarvam tic; no-op for models that don't).
    try:
        agent._spoke_intro = True  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass


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
