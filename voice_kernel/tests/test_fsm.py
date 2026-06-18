"""DialogueFSM tests: per-UseCase transitions, skips, objection routing, directives."""
from __future__ import annotations

from voice_kernel.fsm import DialogueFSM, ModePolicy, policy_for
from voice_kernel.packet import Stage, UseCase


def test_sales_full_linear_path():
    fsm = DialogueFSM(UseCase.SALES)
    seen = [fsm.stage]
    for _ in range(10):
        nxt = fsm.advance()
        if nxt == seen[-1]:
            break
        seen.append(nxt)
    assert seen[0] == Stage.GREET
    assert Stage.PERMISSION in seen
    assert Stage.CLOSE in seen
    assert fsm.is_terminal()  # ends at CLOSE


def test_support_skips_permission_and_booking():
    pol = policy_for(UseCase.SUPPORT)
    seq = pol.sequence()
    assert Stage.PERMISSION not in seq
    assert Stage.BOOKING not in seq
    assert pol.terminal == Stage.FOLLOWUP


def test_inbound_skips_permission():
    seq = policy_for(UseCase.INBOUND).sequence()
    assert Stage.PERMISSION not in seq
    # inbound greets warmly — directive customised
    assert "warmly" in policy_for(UseCase.INBOUND).directive(Stage.GREET).lower()


def test_reminder_skips_qualify_and_objection():
    seq = policy_for(UseCase.REMINDER).sequence()
    assert Stage.QUALIFY not in seq
    assert Stage.OBJECTION not in seq


def test_objection_short_circuits_from_any_stage():
    fsm = DialogueFSM(UseCase.SALES, start=Stage.QUALIFY)
    assert fsm.next_stage(is_objection=True) == Stage.OBJECTION


def test_objection_ignored_when_skipped():
    """REMINDER skips OBJECTION -> an objection signal does NOT route there."""
    fsm = DialogueFSM(UseCase.REMINDER, start=Stage.INTRO)
    assert fsm.next_stage(is_objection=True) != Stage.OBJECTION


def test_terminal_stays_put():
    fsm = DialogueFSM(UseCase.SALES, start=Stage.CLOSE)
    assert fsm.advance() == Stage.CLOSE  # at end, stays


def test_unknown_usecase_defaults_to_sales():
    pol = policy_for(UseCase.FEEDBACK)  # not in table -> SALES default
    assert isinstance(pol, ModePolicy)
    assert pol.sequence()[0] == Stage.GREET


def test_directive_lookup_nonempty_for_core_stages():
    pol = policy_for(UseCase.SALES)
    for st in (Stage.GREET, Stage.QUALIFY, Stage.BOOKING, Stage.CLOSE):
        assert pol.directive(st)


def test_advance_mutates_peek_does_not():
    fsm = DialogueFSM(UseCase.SALES, start=Stage.GREET)
    peeked = fsm.next_stage()
    assert fsm.stage == Stage.GREET  # peek didn't mutate
    fsm.advance()
    assert fsm.stage == peeked  # advance moved to the peeked stage
