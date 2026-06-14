"""comm.brain — the channel-neutral LLM conversation brain (Wave 2, REPLY-ONLY).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §2.4 (the LLM brain) + WAVE 2
("copy `_wa_reply_text` -> comm/brain.py + a per-channel system-prompt suffix; ONE Groq
`llama-4-scout` call; tools OFF at launch `COMM_TOOLS_ENABLED=0`; the pre-LLM keyword
opt-out/handoff gate runs FIRST").

WHAT THIS IS (and is deliberately NOT):
  * This is a COPY of caller.py's `_wa_reply_text` (caller.py:2189), lifted to a channel-neutral
    module. WhatsApp's own `_wa_reply_text` stays byte-identical — we did NOT move it (additive-
    and-isolated beats DRY when the shared code rides the earner). The grounding shape (campaign
    brand + call grounding + cross-call memory recap + last-N turns + persona) mirrors it 1:1.
  * REPLY-ONLY. `COMM_TOOLS_ENABLED` is OFF this wave -> the brain emits plain text, never a tool
    call. The one agentic tool (book_slot) is Wave 4, behind the S3 injection gate.

THE TWO PUBLIC SEAMS:
  * `precheck(text) -> PreCheck`  — the PRE-LLM, FREE, ungameable keyword gate. Runs FIRST,
    BEFORE any Groq call: opt-out (STOP/unsubscribe) -> suppress; handoff (talk to human) ->
    needs_human. Returns the decision so the webhook can short-circuit without spending a token.
  * `generate_reply(ctx) -> ReplyPlan`  — ONE Groq call grounded in `ctx` (a plain dict the
    webhook assembles from the comm_session + the cross-call grounding). Returns a ReplyPlan
    with the reply text (or "" on any LLM failure -> the webhook still acks 200, no reply sent).

EARNER / SAFETY LAW (mirrors the rest of the comm package):
  * imports NO agent.py and NO caller.py (the Groq client is a SELF-CONTAINED thin httpx call,
    NOT a caller.py import — so brain.py is import-safe on any box, and the earner helper is
    never coupled to this module),
  * ZERO I/O at import; the Groq HTTP call happens only inside generate_reply, with a hard
    timeout; httpx absent / no key -> "" (degrade, never raise),
  * NEVER raises out of either seam,
  * the model/key/flags are read at CALL time (a flip takes effect with no restart).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("comm.brain")

# ---------------------------------------------------------------------------
# the keyword gates — a COPY of caller.py:2017 _WA_OPTOUT_WORDS / :2020 _WA_HANDOFF_WORDS,
# kept here so the brain's pre-LLM gate is identical to the WhatsApp earner's (and free).
# ---------------------------------------------------------------------------
OPTOUT_WORDS = (
    "stop", "unsubscribe", "opt out", "optout", "band karo", "band karein",
    "mat bhejo", "remove me", "do not", "dont contact", "don't contact", "block",
)
HANDOFF_WORDS = (
    "talk to human", "human agent", "real person", "call me",
    "agent se baat", "complaint", "manager",
)


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on", "y", "t")


def tools_enabled() -> bool:
    """Are agentic tools ON? OFF this wave (reply-only). Read at call time."""
    return _truthy(os.environ.get("COMM_TOOLS_ENABLED"))


def reply_max_turns() -> int:
    """Human turns in a session before the brain hands off to a human (mirrors WA_MAX_TURNS)."""
    raw = os.environ.get("COMM_REPLY_MAX_TURNS", "")
    try:
        return int(raw) if raw.strip() else 12
    except Exception:  # noqa: BLE001
        return 12


# ---------------------------------------------------------------------------
# value objects.
# ---------------------------------------------------------------------------
@dataclass
class PreCheck:
    """The pre-LLM keyword-gate decision. `action` ∈ noted|opted_out|needs_human. When
    `short_circuit` is True the webhook must NOT call the LLM (a free, ungameable decision)."""
    action: str = "noted"
    short_circuit: bool = False
    reply: str = ""               # optional canned reply for opted_out / needs_human


@dataclass
class ReplyPlan:
    """The brain's output. `text` is the reply to send ("" => send nothing, still ack 200).
    `tool_calls` is always empty this wave (tools OFF). `meta` is diagnostic only."""
    text: str = ""
    action: str = "replied"
    tool_calls: List[dict] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# (1) the pre-LLM keyword gate — FREE, runs FIRST, before any token is spent.
# ---------------------------------------------------------------------------
def precheck(text: str) -> PreCheck:
    """The ungameable keyword gate (opt-out / handoff), identical to the WhatsApp earner's.
    Runs BEFORE generate_reply so a STOP never reaches the LLM (free + cannot be prompt-injected
    around). NEVER raises."""
    low = (text or "").strip().lower()
    if not low:
        return PreCheck(action="noted", short_circuit=False)
    if any(w in low for w in OPTOUT_WORDS):
        return PreCheck(
            action="opted_out", short_circuit=True,
            reply="You're unsubscribed — we won't message you here again. Reply if you change your mind.",
        )
    if any(w in low for w in HANDOFF_WORDS):
        return PreCheck(
            action="needs_human", short_circuit=True,
            reply="Sure — I'll have a human from our team reach out to you shortly.",
        )
    return PreCheck(action="noted", short_circuit=False)


# ---------------------------------------------------------------------------
# the Groq client — a SELF-CONTAINED copy of caller.py:_groq_chat (NOT an import of caller.py).
# ---------------------------------------------------------------------------
def _groq_chat(messages: list, *, max_tokens: int = 220, temperature: float = 0.6,
               timeout: float = 20.0) -> str:
    """ONE Groq chat completion. Returns the assistant text, or "" on ANY failure (never raises).

    This duplicates caller.py:_groq_chat (the earner's WA-draft client) on purpose — the brain
    must not import the live earner module. Key + model are read from the SAME env vars the box
    already sets (GROQ_KEY / GROQ_MODEL), so it rides the existing Groq config with no new secret."""
    key = (os.environ.get("GROQ_KEY") or os.environ.get("GROQ_API_KEY") or "").strip()
    model = (os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    if not key or not messages:
        return ""
    try:
        import httpx  # type: ignore
    except Exception:  # noqa: BLE001
        return ""
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json={"model": model, "temperature": temperature,
                  "max_tokens": max_tokens, "messages": messages},
            timeout=timeout,
        )
        return (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# (2) grounding + the ONE LLM call — the reply brain (copy of _wa_reply_text).
# ---------------------------------------------------------------------------
def _build_grounding(ctx: Dict[str, Any]) -> str:
    """Assemble the call-grounding paragraph (mirrors _wa_reply_text's grounding block)."""
    call_summary = (ctx.get("call_summary") or "").strip()
    next_action = (ctx.get("next_action") or "").strip()
    call_outcome = (ctx.get("outcome") or "").strip()
    interest = ctx.get("interest", "")
    mem_recap = (ctx.get("memory_recap") or "").strip()
    grounding = ""
    if call_summary:
        grounding += f"What happened on the phone call: {call_summary[:400]}. "
    if next_action:
        grounding += f"Agreed/suggested next step from the call: {next_action[:160]}. "
    if call_outcome:
        grounding += f"Call outcome: {call_outcome} (interest {interest}). "
    if mem_recap:
        grounding += f"Earlier history with this person: {mem_recap[:500]}. "
    return grounding


def _channel_suffix(channel: str) -> str:
    """A small per-channel system-prompt suffix (§2.4). Telegram is a casual chat surface."""
    ch = (channel or "telegram").strip().lower()
    if ch == "telegram":
        return " You are chatting on Telegram — keep it conversational and brief."
    if ch == "email":
        return " You are writing an email — a touch more formal, but still warm and short."
    if ch == "sms":
        return " You are writing an SMS — very short (under 2 sentences), no emoji."
    return ""


def build_system_prompt(ctx: Dict[str, Any]) -> str:
    """The system message — a COPY of _wa_reply_text's sysmsg, channel-neutral + a channel suffix.
    Exposed so a test can assert the grounding is actually injected. NEVER raises."""
    agent = (ctx.get("agent_name") or "Riya").strip() or "Riya"
    company = (ctx.get("company_name") or "").strip()
    product = (ctx.get("product_name") or "").strip()
    summary = (ctx.get("product_summary") or "").strip()
    name = (ctx.get("name") or "").strip() or "ji"
    channel = (ctx.get("channel") or "telegram").strip() or "telegram"
    grounding = _build_grounding(ctx)
    ch_label = "WhatsApp" if channel == "whatsapp" else channel.capitalize()
    sysmsg = (
        "You are " + agent + (f", a sales assistant for {company}" if company else "")
        + f". You are continuing a conversation with {name} on {ch_label} AFTER a phone call. "
        "Reply to the customer's message in SHORT natural Hinglish (Roman script), "
        "1-3 sentences, warm and helpful, at most one emoji, no markdown. "
        + (f"You are following up about: {product}. " if product else "")
        + (f"Product/offer context: {summary[:300]}. " if summary else "")
        + (grounding if grounding else "")
        + "Use the call context above so you don't repeat yourself or contradict the call. "
        "Move the conversation toward a clear next step (site visit / share details / schedule "
        "a callback / booking). If they ask something you don't know, offer to have a human call "
        "them. Do not invent facts beyond the context. Output ONLY the reply text."
        + _channel_suffix(channel)
    )
    return sysmsg


def generate_reply(ctx: Dict[str, Any]) -> ReplyPlan:
    """ONE Groq call -> the grounded reply, mirroring _wa_reply_text.

    `ctx` (a plain dict the webhook assembles) carries:
      channel, agent_name, company_name, product_name, product_summary, name,
      call_summary, next_action, outcome, interest, memory_recap,
      turns (the rolling window [{role,text}], oldest-first), incoming (the new user message).

    Returns a ReplyPlan(text=...). On ANY failure (no key, httpx absent, empty reply) text=""
    -> the webhook acks 200 with no reply (never an error to Telegram). NEVER raises.
    Tools are OFF this wave -> tool_calls is always empty."""
    try:
        incoming = (ctx.get("incoming") or "").strip()
        sysmsg = build_system_prompt(ctx)
        msgs: List[dict] = [{"role": "system", "content": sysmsg}]
        # the rolling window (last N turns) — labelled assistant/user, oldest-first.
        for t in (ctx.get("turns") or [])[-10:]:
            role = "assistant" if (t or {}).get("role") == "assistant" else "user"
            body = str((t or {}).get("text", "") or "")
            if body:
                msgs.append({"role": role, "content": body})
        if incoming:
            msgs.append({"role": "user", "content": incoming})
        text = _groq_chat(msgs, max_tokens=220, temperature=0.6)
        if not text:
            return ReplyPlan(text="", action="draft_failed", meta={"reason": "empty_llm"})
        return ReplyPlan(text=text, action="replied",
                         meta={"tools": tools_enabled(), "grounded": bool(_build_grounding(ctx))})
    except Exception as exc:  # noqa: BLE001 — never raise out of the brain
        _log.warning("comm.brain.generate_reply failed: %r", type(exc).__name__)
        return ReplyPlan(text="", action="error", meta={"reason": type(exc).__name__})
