"""voice_ops.booking.transfer — warm-transfer hardening HELPER (pure planner + state log).

WHAT THIS FIXES (founder bug 1): the warm transfer currently (a) says unnecessary things — phone
numbers, over-talk, verbose fallback paragraphs — and (b) doesn't reliably ring / play hold music.

Per the EARNER LAW the LIVE inbound agent (`aim_voice_agent.py`) is NOT edited here — the actual
edits are a PATCH DOC (design/W11-TRANSFER-BOOKING-GCAL-SEAM.md). This module is the TRACKED,
testable BRAIN the patch calls into:

  * `plan_transfer(...)` -> a TransferPlan: the EXACT ordered steps the agent must run —
      1. speak ONE short ack line (and NOTHING else),
      2. start looped hold music,
      3. dial the handoff number into the SAME SIP room,
      4. on answer: stop music, AI exits (session shutdown), room stays alive,
      5. on all-dials-fail: speak ONE short fallback line, then close.
    The plan also carries the single ack `say` string and the single fallback `say` string, so the
    agent never improvises a paragraph. The planner GUARANTEES exactly one short spoken line per
    branch (asserted in tests).

  * `TransferState` + `TransferLog` — the requested/started/connecting/completed/failed lifecycle
    the founder asked be logged, with timestamps, emitting the W8 `handoff_requested` /
    `handoff_done` events (fire-and-forget; never blocks the call).

PURE + droplet-free: no livekit, no SIP SDK, no droplet_work import at module load. The planner is
a pure function over (intent, handoff numbers, dial_who label). The agent supplies the live SIP
primitives (create_sip_participant into the caller's room, BackgroundAudioPlayer) — those stay in
aim_voice_agent; this module only decides WHAT to say and in WHAT ORDER, and records state.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

log = logging.getLogger("voice_ops.booking.transfer")


# --------------------------------------------------------------------------- #
# Transfer-intent detection (pure). The agent prompt is the primary gate; this is
# a deterministic backstop so the tool fires on the clear phrases.
# --------------------------------------------------------------------------- #
_INTENT_PATTERNS = [
    r"\b(team|human|insaan|aadmi|agent|representative|sales\s*person|salesman)\b",
    r"\b(baat\s*kar|connect\s*kar|transfer|kisi\s*se\s*baat)\b",
    r"\b(buy|kharid|purchase|book\s*now|paisa|payment|deal\s*final)\b",
    r"\b(manager|senior|owner|maalik)\b",
]
_INTENT_RE = re.compile("|".join(_INTENT_PATTERNS), re.IGNORECASE)


def detect_transfer_intent(text: str) -> bool:
    """True when the prospect clearly asks for a human / team / wants to buy. Pure."""
    return bool(_INTENT_RE.search(text or ""))


# --------------------------------------------------------------------------- #
# The plan the agent executes. ONE ack line, ONE fallback line, exact step order.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TransferPlan:
    """The deterministic transfer choreography. `ack_line` is the ONLY thing spoken before the
    dial; `fallback_line` is the ONLY thing spoken if every dial fails. `steps` is the ordered
    list of named actions the agent runs."""

    ack_line: str
    fallback_line: str
    dial_numbers: tuple[str, ...]
    play_hold_music: bool = True
    same_room: bool = True            # dial into the caller's EXISTING SIP room (no new room)
    ai_exit_after_bridge: bool = True
    delete_room_on_close: bool = False  # keep room alive so caller+human continue
    steps: tuple[str, ...] = ()

    @property
    def has_target(self) -> bool:
        return len(self.dial_numbers) > 0


# the canonical short lines (founder's exact spec: masculine, 'theek hai sar', no numbers, no stall)
_ACK_TEMPLATE = "Theek hai sar, main aapko {who} se connect kar raha hoon."
_ACK_DEFAULT = "Theek hai sar, main aapko team se connect kar raha hoon."
_FALLBACK_LINE = "Team abhi available nahin hai, hum aapko jaldi callback karenge."
_NO_TARGET_LINE = "Main aapki request team ko bhej raha hoon, woh aapko jaldi call karenge."


def _normalize_numbers(numbers: Any) -> tuple[str, ...]:
    """Coerce a handoff-list payload to a clean tuple of dialable numbers. Accepts a list of
    strings or a list of dicts ({'phone'|'number'|'msisdn': ...}). Drops blanks. Pure."""
    out: list[str] = []
    for item in (numbers or []):
        if isinstance(item, str):
            v = item.strip()
        elif isinstance(item, dict):
            v = str(item.get("phone") or item.get("number") or item.get("msisdn") or "").strip()
        else:
            v = str(item).strip()
        if v:
            out.append(v)
    return tuple(out)


def plan_transfer(
    *,
    handoff_numbers: Any,
    dial_who: str = "team",
) -> TransferPlan:
    """Build the deterministic transfer plan. GUARANTEES exactly ONE short ack line and ONE short
    fallback line — no phone numbers spoken, no over-talk, no verbose paragraph.

    `handoff_numbers` is the tenant's handoff list (strings or dicts). `dial_who` is a short label
    for the ack line ('team' / 'manager'). Pure — no SIP, no network, no clock."""
    numbers = _normalize_numbers(handoff_numbers)
    who = (dial_who or "team").strip() or "team"
    ack = _ACK_TEMPLATE.format(who=who) if who != "team" else _ACK_DEFAULT
    if not numbers:
        # No one to dial: still ONE short line, no music/dial, AI records + closes politely.
        return TransferPlan(
            ack_line=_NO_TARGET_LINE,
            fallback_line=_NO_TARGET_LINE,
            dial_numbers=(),
            play_hold_music=False,
            steps=("speak_ack", "log_requested", "log_failed_no_target", "close"),
        )
    return TransferPlan(
        ack_line=ack,
        fallback_line=_FALLBACK_LINE,
        dial_numbers=numbers,
        play_hold_music=True,
        same_room=True,
        ai_exit_after_bridge=True,
        delete_room_on_close=False,
        steps=(
            "log_requested",
            "speak_ack",            # the ONE short line, nothing else
            "start_hold_music",
            "log_started",
            "dial_into_same_room",  # CreateSIPParticipant into the caller's room, sequential over dial_numbers
            "on_answer_stop_music",
            "log_completed",
            "ai_exit_session_shutdown",  # delete_room_on_close=False -> caller+human continue
        ),
    )


# --------------------------------------------------------------------------- #
# Lifecycle state log (requested / started / connecting / completed / failed).
# --------------------------------------------------------------------------- #
class TransferState(str, Enum):
    REQUESTED = "requested"
    STARTED = "started"
    CONNECTING = "connecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TransferLog:
    """Mutable lifecycle record for ONE transfer attempt. The agent advances it through the
    states; each transition stamps UTC. Emits the W8 handoff_requested / handoff_done events
    (fire-and-forget) so the dashboard reflects the transfer in real time.

    `event_bus` is any object with async `emit(Event)` (W8) or None. Emission NEVER blocks or
    breaks the call."""

    call_id: str
    tenant_id: str
    reason: str = ""
    event_bus: Any = None
    state: TransferState = TransferState.REQUESTED
    target: str = ""
    history: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self._stamp(TransferState.REQUESTED, detail=self.reason)

    def _stamp(self, state: TransferState, *, detail: str = "") -> None:
        self.state = state
        self.history.append({
            "state": state.value,
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "detail": detail,
        })
        log.info("transfer %s call=%s tenant=%s %s", state.value, self.call_id,
                 self.tenant_id, detail)

    async def _emit(self, event) -> None:
        if self.event_bus is None or event is None:
            return
        try:
            await self.event_bus.emit(event)
        except Exception as exc:  # noqa: BLE001
            log.info("transfer event emit failed (non-fatal): %r", exc)

    async def requested(self) -> None:
        from voice_kernel.events import handoff_requested
        await self._emit(handoff_requested(self.call_id, self.tenant_id, reason=self.reason))

    async def started(self, target: str = "") -> None:
        self.target = target or self.target
        self._stamp(TransferState.STARTED, detail=f"dialing target")

    async def connecting(self, target: str = "") -> None:
        self.target = target or self.target
        self._stamp(TransferState.CONNECTING, detail="ringing")

    async def completed(self, agent: str = "") -> None:
        self._stamp(TransferState.COMPLETED, detail=agent or self.target)
        from voice_kernel.events import handoff_done
        await self._emit(handoff_done(self.call_id, self.tenant_id, agent=agent or self.target))

    async def failed(self, reason: str = "") -> None:
        self._stamp(TransferState.FAILED, detail=reason)
        # a failed transfer is still a handoff_done with a failure marker so the dashboard closes
        # the loop rather than showing a perpetual "connecting".
        from voice_kernel.events import handoff_done
        await self._emit(handoff_done(self.call_id, self.tenant_id, agent="",
                                      outcome="failed", reason=reason or "no_human_answered"))

    def snapshot(self) -> dict:
        return {"call_id": self.call_id, "tenant_id": self.tenant_id, "state": self.state.value,
                "target": self.target, "history": list(self.history)}
