"""Tests for voice_ops.flywheel.compliance — the Tier-1 HARD eligibility GATE.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_compliance
Validates the anti-Goodhart firewall (compliance is a GATE, never a reward term):
  * check_text catches the #1 rule — an AI self-label ('main ek AI assistant hoon') — even
    in romanized Hinglish, and catches manufactured/fake scarcity ('sirf aaj ke liye, last unit');
  * a clean, on-script sales line passes with ZERO violations;
  * check_trajectory verdict is INELIGIBLE on ANY violation (a converted-but-coercive call
    earns no learning signal).
NO network, NO ClickHouse, NO model call — pure keyword scan.
"""
from __future__ import annotations

from voice_ops.flywheel.compliance import (
    ComplianceVerdict, check_text, check_trajectory,
)


def test_check_text_flags_ai_self_label_romanized_hinglish():
    """The #1 rule (must NEVER be missed): the agent must not out itself as a bot, in any
    language. Romanized Hinglish self-label is caught."""
    codes = check_text("Hello, main ek AI assistant hoon from Famit", stance="sales")
    assert "ai_self_label" in codes, codes
    # English variant too.
    assert "ai_self_label" in check_text("I am an AI bot calling about your property", stance="sales")


def test_check_text_does_not_flag_a_prohibition_line():
    """A script that NAMES the label as a prohibition ('I will never say I am an AI') is NOT a
    self-label — vetoing it would starve the loop of an honest disclosure-management line."""
    assert "ai_self_label" not in check_text("I will never say I am an AI assistant", stance="sales")


def test_check_text_flags_fake_scarcity():
    """Manufactured urgency is the founder's 'pushy' canary."""
    codes = check_text("Sirf aaj ke liye offer hai, last unit bacha hai, jaldi karein", stance="sales")
    assert "fake_scarcity" in codes, codes


def test_check_text_clean_sales_line_passes():
    clean = ("Namaste Rahul ji, main Skyline Realty se baat kar rahi hoon. "
             "Yeh 3 BHK project Whitefield mein hai.")
    assert check_text(clean, stance="sales") == [], check_text(clean, stance="sales")


def test_check_text_invented_price_needs_a_fabrication_cue_near_a_price():
    """A fabrication cue ('guaranteed'/'pakka') NEAR a price token fires; an ordinary quoted
    price does not."""
    assert "invented_price" in check_text("This is guaranteed only 50 lakh, pakka", stance="sales")
    assert "invented_price" not in check_text("The launch price is 95 lakh rupees", stance="sales")


def test_check_trajectory_clean_call_is_eligible():
    good = [
        {"role": "agent", "agent_text": "Namaste ji, main Skyline Realty se baat kar rahi hoon."},
        {"role": "caller", "caller_text": "Haan boliye"},
        {"role": "agent", "agent_text": "Project Dec 2027 mein ready ho jayega."},
    ]
    v = check_trajectory(good, stance="sales")
    assert isinstance(v, ComplianceVerdict)
    assert v.eligible is True and v.violations == (), v


def test_check_trajectory_ineligible_on_any_self_label():
    v = check_trajectory([{"role": "agent", "agent_text": "main ek robot hoon"}], stance="sales")
    assert v.eligible is False and "ai_self_label" in v.violations, v


def test_check_trajectory_ineligible_on_scarcity():
    v = check_trajectory(
        [{"role": "agent", "agent_text": "Sirf aaj ke liye, last unit hai, jaldi karein"}],
        stance="sales")
    assert v.eligible is False and "fake_scarcity" in v.violations, v


def test_check_trajectory_optout_then_pitch_is_vetoed():
    """Once a caller says stop/remove/do-not-call, any later agent pitch is 'optout_not_honored'
    and the whole call is ineligible to seed the learning loop."""
    bad = [
        {"role": "caller", "caller_text": "Do not call me, remove my number"},
        {"role": "agent", "agent_text": "But sir, please site visit book kar lijiye, best deal hai"},
    ]
    v = check_trajectory(bad, stance="sales")
    assert v.eligible is False and "optout_not_honored" in v.violations, v


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_compliance OK")


if __name__ == "__main__":
    _run_all()
