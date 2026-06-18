"""voice_kernel.memory.extraction — structured LEAD-MEMORY extraction.

The COLD post-call step that turns a finished call into a tiny `LeadMemory`
(the FROZEN L4 shape, packet.py:212-219). The whole point: store the SALIENT
~5% — commitments, objections-resolved, budget signal, preferred callback,
interest, booking/handoff state, next action — NOT the raw transcript. Mem0 /
Memori report ~90% token reduction by storing structured salient memory and
discarding the rest; the FROZEN LeadMemory already embodies that slice, so we
extract INTO it and never widen it.

Two-tier (the universal pattern):
  * `extract_rules(...)` — HOT/cheap, deterministic, await-free. Pulls salient
    signals from the call's turns/summary with regex + keyword heuristics. Used
    on the post-call path with ZERO model cost and ZERO latency variance.
  * `extract_with_llm(...)` — COLD async LLM-ASSIST HOOK. Optional; given an
    `llm` callable it refines the deterministic draft. Degrades to the rules
    draft on any error/timeout (never raises into the call lifecycle).

Write-side sanitize: every stored string is run through the W3 text-hygiene
`sanitize()` (NFKC + zero-width strip + fence defang) so a prompt-injected prior
call cannot smuggle an invisible fence-breakout into the store (S4). The packet
renderer fences the stored memory on READ; we sanitize on WRITE — both legs.

Pure-stdlib + voice_kernel only. Imports NOTHING from droplet_work.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Awaitable, Callable, Optional, Sequence

from ..packet import Lifecycle, LeadMemory
from .hygiene import sanitize
from ..tokens import clamp_chars
from .lifecycle import classify_lifecycle, conversion_probability

# The store cap for the rolling summary. clamp_chars appends a 1-char ellipsis
# on truncation, so we clamp to 299 to keep the STORED value within the DB CHECK
# (<= 300) and the prompt L4 cap (300). 299 + "…" = 300 worst case.
_SUMMARY_CHARS = 299
_MAX_COMMITMENTS = 5
_MAX_DNM = 5


# --------------------------------------------------------------------------- #
# Salient-signal vocabularies (Hinglish-aware; the agent talks Hindi+English).
# --------------------------------------------------------------------------- #
# Commitment / promise markers ("I'll check with my wife", "kal call karna").
_COMMIT_RE = re.compile(
    r"\b("
    r"i'?ll|i will|let me|let me check|i need to|main\s+\w+\s*karunga|karungi|"
    r"sochke|soch ke|check kar|baat kar|wapas|callback|call me back|"
    r"kal|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"agle|next week|baad mein|after|budget|emi|loan|finance"
    r")\b",
    re.IGNORECASE,
)

# Objection markers (price, time, trust, need, competitor).
_OBJECTION_RE = re.compile(
    r"\b(mahenga|expensive|too costly|costly|budget nahi|no budget|paisa nahi|"
    r"busy|no time|abhi nahi|not now|baad mein|think about it|sochna|"
    r"trust|fraud|scam|spam|already have|pehle se|interested nahi|not interested)\b",
    re.IGNORECASE,
)

# Hard-negative / DEAD markers (DND, abuse, explicit opt-out).
_DEAD_RE = re.compile(
    r"\b(do not call|don'?t call|dnd|stop calling|remove (my )?number|"
    r"mat karo call|band karo|complaint|legal|police|report)\b",
    re.IGNORECASE,
)

# Booking / handoff state markers.
_BOOKED_RE = re.compile(
    r"\b(book(ed)?|appointment|schedule[d]?|visit|meeting fix|fix kar|"
    r"slot|confirm(ed)?|aa jaunga|aaungi|aaunga)\b",
    re.IGNORECASE,
)
_HANDOFF_RE = re.compile(
    r"\b(manager|senior|human|transfer|connect me|baat karao|escalate)\b",
    re.IGNORECASE,
)

# Preferred callback time extraction (very rough; the LLM-assist refines it).
_CALLBACK_RE = re.compile(
    r"\b(kal|tomorrow|today|aaj|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|morning|subah|afternoon|dopahar|evening|shaam|"
    r"\d{1,2}\s*(am|pm|baje|o'?clock))\b",
    re.IGNORECASE,
)

# Things we should NOT bring up again (sensitive: medical, family loss, etc.).
_DNM_RE = re.compile(
    r"\b(hospital|sick|bimar|death|guzar|passed away|divorce|talaq|"
    r"job loss|naukri chali|allergic|allergy)\b",
    re.IGNORECASE,
)


def _user_text(turns: Sequence[dict]) -> str:
    """Concatenate only the LEAD's (user) utterances — the agent's own lines are
    not evidence about the lead. Accepts the inbound/outbound turn shape
    {"role": "user"|"assistant"|"agent", "text"|"content": ...}."""
    out: list[str] = []
    for t in turns or ():
        role = str(t.get("role", "")).lower()
        if role in ("user", "lead", "customer", "human"):
            out.append(str(t.get("text") or t.get("content") or ""))
    return "\n".join(p for p in out if p)


def _dedup(seq: Sequence[str], cap: int) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        s2 = s.strip()
        k = s2.lower()
        if s2 and k not in seen:
            seen.add(k)
            out.append(s2)
        if len(out) >= cap:
            break
    return tuple(out)


def _salient_lines(text: str, pattern: re.Pattern) -> list[str]:
    """Return the lines that carry a salient signal — the ~5% that matters."""
    hits: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and pattern.search(line):
            hits.append(clamp_chars(line, 120))
    return hits


def extract_rules(
    *,
    turns: Sequence[dict],
    prior: Optional[LeadMemory] = None,
    raw_summary: str = "",
    name: str = "",
) -> LeadMemory:
    """DETERMINISTIC, await-free salient extraction → a FROZEN LeadMemory.

    Keeps ONLY salient facts (commitments / objections / callback / booking /
    handoff / do-not-mention), reconciled with the prior memory. NEVER stores the
    raw transcript. Every stored string is write-side sanitized. lifecycle +
    conversion_prob are derived (deterministic) from the same signals.
    """
    prior = prior or LeadMemory()
    user = _user_text(turns)

    # --- salient signals (lead utterances only) ----------------------------- #
    commitments = _salient_lines(user, _COMMIT_RE)
    objections = _salient_lines(user, _OBJECTION_RE)
    dnm = _salient_lines(user, _DNM_RE)

    booked = bool(_BOOKED_RE.search(user))
    handoff = bool(_HANDOFF_RE.search(user))
    dead = bool(_DEAD_RE.search(user))

    callback = ""
    m = _CALLBACK_RE.search(user)
    if m:
        callback = clamp_chars(m.group(0).strip(), 60)

    # --- rolling summary: a salient one-liner, NOT the transcript ------------ #
    # Prefer an explicitly-passed raw_summary (the agent's own end-of-call
    # summary line); else synthesize from the top salient signals.
    if raw_summary:
        summary = raw_summary
    else:
        bits: list[str] = []
        if booked:
            bits.append("booked/appointment discussed")
        if handoff:
            bits.append("asked for human/manager")
        if commitments:
            bits.append("said: " + commitments[0])
        if objections:
            bits.append("objection: " + objections[0])
        if callback:
            bits.append("callback: " + callback)
        summary = "; ".join(bits)

    # --- reconcile with prior (UPDATE/MERGE, the Mem0 ADD/UPDATE pattern) ---- #
    merged_commitments = _dedup(
        list(commitments) + list(prior.open_commitments), _MAX_COMMITMENTS
    )
    merged_dnm = _dedup(list(dnm) + list(prior.do_not_mention), _MAX_DNM)
    merged_callback = callback or prior.preferred_callback_ts

    # --- lifecycle + conversion probability (deterministic; lifecycle.py) ---- #
    lifecycle = classify_lifecycle(
        prior=prior.lifecycle,
        booked=booked,
        handoff=handoff,
        dead=dead,
        had_objection=bool(objections),
        had_commitment=bool(commitments),
        engaged=bool(user.strip()),
    )
    prob = conversion_probability(
        lifecycle=lifecycle,
        booked=booked,
        handoff=handoff,
        n_commitments=len(merged_commitments),
        n_objections=len(objections),
        engaged_chars=len(user),
    )

    # --- assemble + WRITE-SIDE SANITIZE every stored string (S4) ------------- #
    mem = LeadMemory(
        name=sanitize(name or prior.name),
        lifecycle=lifecycle,
        last_call_summary=clamp_chars(sanitize(summary), _SUMMARY_CHARS),
        open_commitments=tuple(sanitize(c) for c in merged_commitments),
        preferred_callback_ts=sanitize(merged_callback),
        do_not_mention=tuple(sanitize(d) for d in merged_dnm),
    )
    # carry the derived probability out-of-band via a private attr on a copy is
    # not possible on a frozen dataclass; the service reads `prob`/`lifecycle`
    # from the returned tuple below. We attach via the helper return.
    return _Extraction(memory=mem, conversion_prob=prob).memory_with_prob()


class _Extraction:
    """Internal carrier so the deterministic extractor can hand the service both
    the FROZEN LeadMemory AND the derived conversion_prob (which is NOT a field
    on the frozen contract — it is an internal score the service persists in the
    `conversion_prob` column). We thread it via a module-level side table keyed by
    object identity to keep the public return type exactly `LeadMemory`."""

    def __init__(self, memory: LeadMemory, conversion_prob: int):
        self.memory = memory
        self.conversion_prob = conversion_prob

    def memory_with_prob(self) -> LeadMemory:
        _PROB_SIDE_TABLE[id(self.memory)] = self.conversion_prob
        return self.memory


# Object-identity side table: maps an extracted LeadMemory -> its internal
# conversion_prob (0..100). The service reads it via `prob_for(mem)` right after
# extraction (same process, same object) and persists it to the column. Bounded:
# entries are popped on read. This keeps the FROZEN LeadMemory contract un-widened.
_PROB_SIDE_TABLE: dict[int, int] = {}


def prob_for(mem: LeadMemory) -> int:
    """Pop the internal conversion_prob derived for `mem` (0 if none)."""
    return _PROB_SIDE_TABLE.pop(id(mem), 0)


async def extract_with_llm(
    *,
    turns: Sequence[dict],
    prior: Optional[LeadMemory] = None,
    raw_summary: str = "",
    name: str = "",
    llm: Optional[Callable[[str], Awaitable[str]]] = None,
    timeout_s: float = 8.0,
) -> LeadMemory:
    """COLD async LLM-ASSIST HOOK. Builds the deterministic draft first (always),
    then — if an `llm` callable is supplied — asks it to refine the rolling
    SUMMARY only (the highest-value, lowest-risk field). On ANY error/timeout it
    returns the deterministic draft unchanged. Never raises into the call
    lifecycle; never widens the FROZEN LeadMemory.
    """
    import asyncio

    draft = extract_rules(turns=turns, prior=prior, raw_summary=raw_summary, name=name)
    prob = prob_for(draft)  # preserve across the refine
    if llm is None:
        _PROB_SIDE_TABLE[id(draft)] = prob
        return draft
    try:
        prompt = (
            "Summarize this sales call for the NEXT call's opener in <=300 chars, "
            "in the lead's language, salient facts only (commitment, objection, "
            "callback, interest, booking). Do NOT include the raw transcript.\n\n"
            + _user_text(turns)
        )
        refined = await asyncio.wait_for(llm(prompt), timeout=timeout_s)
        refined = clamp_chars(sanitize(refined or ""), _SUMMARY_CHARS)
        if refined:
            draft = replace(draft, last_call_summary=refined)
    except Exception:
        pass  # degrade to the deterministic draft (never raise into the lifecycle)
    _PROB_SIDE_TABLE[id(draft)] = prob
    return draft
