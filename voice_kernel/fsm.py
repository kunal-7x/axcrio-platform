"""voice_kernel.fsm — the dialogue-mode FSM (states, transitions, per-mode policy).

States = the `Stage` enum (greet → permission → intro → qualify → objection →
booking → close → followup). The FSM is MODE-PARAMETERIZED by `UseCase`: each
use-case has a policy table giving (a) the linear stage sequence (which stages
it skips) and (b) the per-stage `turn_directive`.

This module is the CORE driver. The richer `DialoguePolicy` (W6) can later own a
fuller table; the kernel imports the Protocol and falls back to THIS table via
`null_impls`. Pure, sync, HOT-path safe — no I/O, no awaits.

Design note (red-team): an objection can occur at any point, so from any stage a
turn flagged as an objection routes to OBJECTION, then resumes the linear path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .packet import Stage, UseCase

# Canonical full linear order.
_FULL_ORDER: tuple[Stage, ...] = (
    Stage.GREET,
    Stage.PERMISSION,
    Stage.INTRO,
    Stage.QUALIFY,
    Stage.OBJECTION,
    Stage.BOOKING,
    Stage.CLOSE,
    Stage.FOLLOWUP,
)


@dataclass(frozen=True)
class ModePolicy:
    """The per-UseCase policy: which stages are in-play, the terminal goal, and
    the per-stage directive text."""

    use_case: UseCase
    skips: frozenset[Stage] = field(default_factory=frozenset)
    terminal: Stage = Stage.CLOSE
    directives: dict[Stage, str] = field(default_factory=dict)

    def sequence(self) -> tuple[Stage, ...]:
        """The ordered, skip-filtered stage path for this mode (OBJECTION is
        always reachable on-demand, so it stays in the sequence even if 'skipped'
        from the linear flow — skipping only removes it from auto-advance)."""
        return tuple(s for s in _FULL_ORDER if s not in self.skips)

    def directive(self, stage: Stage) -> str:
        return self.directives.get(stage, "")


# --------------------------------------------------------------------------- #
# Per-UseCase policy table (arch §4). Directives are short stage nudges; W6 may
# enrich them, but these are real (not placeholders) so the kernel runs today.
# --------------------------------------------------------------------------- #
def _base_directives() -> dict[Stage, str]:
    return {
        Stage.GREET: "Warm, brief greeting. Use the lead's name if known.",
        Stage.PERMISSION: "Ask for a moment of their time before pitching.",
        Stage.INTRO: "One-line reason for the call. Lead with the benefit.",
        Stage.QUALIFY: "Ask one qualifying question at a time. Listen.",
        Stage.OBJECTION: "Acknowledge, empathise, then answer with one fact.",
        Stage.BOOKING: "Offer two concrete slots. Confirm one clearly.",
        Stage.CLOSE: "Confirm next step, thank them, end on a warm note.",
        Stage.FOLLOWUP: "Set the follow-up expectation and the channel.",
    }


_POLICIES: dict[UseCase, ModePolicy] = {
    UseCase.SALES: ModePolicy(
        UseCase.SALES, skips=frozenset(), terminal=Stage.CLOSE, directives=_base_directives()
    ),
    UseCase.SUPPORT: ModePolicy(
        UseCase.SUPPORT,
        skips=frozenset({Stage.PERMISSION, Stage.BOOKING}),
        terminal=Stage.FOLLOWUP,
        directives={**_base_directives(), Stage.CLOSE: "Confirm the issue is resolved."},
    ),
    UseCase.BOOKING: ModePolicy(
        UseCase.BOOKING,
        skips=frozenset({Stage.OBJECTION}),
        terminal=Stage.BOOKING,
        directives=_base_directives(),
    ),
    UseCase.REMINDER: ModePolicy(
        UseCase.REMINDER,
        skips=frozenset({Stage.QUALIFY, Stage.OBJECTION}),
        terminal=Stage.CLOSE,
        directives={**_base_directives(), Stage.INTRO: "State the reminder plainly."},
    ),
    UseCase.INBOUND: ModePolicy(
        UseCase.INBOUND,
        skips=frozenset({Stage.PERMISSION}),  # they called us
        terminal=Stage.BOOKING,
        directives={**_base_directives(), Stage.GREET: "They called us — greet warmly, ask how to help."},
    ),
}


def policy_for(use_case: UseCase) -> ModePolicy:
    """Return the policy for a use-case, defaulting to SALES (the richest path)."""
    return _POLICIES.get(use_case, _POLICIES[UseCase.SALES])


class DialogueFSM:
    """Drives stage transitions for a single call. Holds the current stage; pure
    transition logic, no I/O.

    `advance(is_objection=...)` is the core: an objection short-circuits to
    OBJECTION from any stage, then `advance()` resumes the linear path.
    """

    def __init__(self, use_case: UseCase = UseCase.SALES, start: Stage | None = None):
        self.policy = policy_for(use_case)
        seq = self.policy.sequence()
        self.use_case = use_case
        self.stage = start if start is not None else seq[0]

    def directive(self) -> str:
        return self.policy.directive(self.stage)

    def is_terminal(self) -> bool:
        return self.stage == self.policy.terminal

    def next_stage(self, *, is_objection: bool = False) -> Stage:
        """Compute the next stage WITHOUT mutating (pure peek).

        Auto-advance STOPS at the mode's terminal stage (the goal): once the
        FSM reaches `policy.terminal` it stays there. Stages after terminal in
        the linear order (e.g. FOLLOWUP after a SALES CLOSE) are reachable only
        by an explicit caller move, not by auto-advance — the call's objective
        is met at terminal.
        """
        if is_objection and Stage.OBJECTION not in self.policy.skips:
            return Stage.OBJECTION
        if self.stage == self.policy.terminal:
            return self.stage  # goal reached — hard stop
        seq = self.policy.sequence()
        if self.stage not in seq:
            # parked on an out-of-sequence stage (e.g. OBJECTION when it was
            # skipped); resume at the first sequence stage.
            return seq[0]
        i = seq.index(self.stage)
        if i + 1 < len(seq):
            nxt = seq[i + 1]
            # never auto-advance PAST the terminal: if the next stage would skip
            # over terminal, clamp to terminal.
            if self.policy.terminal in seq:
                ti = seq.index(self.policy.terminal)
                if i + 1 > ti:
                    return self.policy.terminal
            return nxt
        return self.stage  # already at the end — stay put

    def advance(self, *, is_objection: bool = False) -> Stage:
        """Transition and return the new stage (mutates self.stage)."""
        self.stage = self.next_stage(is_objection=is_objection)
        return self.stage
