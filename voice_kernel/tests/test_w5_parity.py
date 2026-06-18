"""W5 parity / earner-safety tests.

(1) FLAG-OFF byte-identity 10/10: a default-built kernel (no W5 impls registered)
    still uses the Null pass-through planner + null router — registering W5 is
    PURELY ADDITIVE, the default path is byte-identical run-to-run and unchanged.
(2) W5 determinism: the planner is a pure function — same input -> byte-identical
    output 10/10 (no randomness in fillers/normalization).
(3) The default kernel's speech/router are the Null impls (W5 dormant until wired).
"""
from __future__ import annotations

from voice_kernel.kernel import build_kernel
from voice_kernel.null_impls import NullProviderRouter, NullSpeechPlanner
from voice_kernel.packet import CampaignCard
from voice_kernel.speech import build_speech_planner

CARD = CampaignCard(language="Hinglish")
RAW = "Iski keemat ₹58 lakh hai. Call 9876543210 par. Yeh mahatvapurn baat hai"


def test_default_kernel_uses_null_w5_impls():
    k = build_kernel()
    assert isinstance(k.svc.speech, NullSpeechPlanner)
    assert isinstance(k.svc.router, NullProviderRouter)


def test_flag_off_null_planner_is_passthrough_byte_identical_10x():
    null = NullSpeechPlanner()
    first = null.plan(RAW, "hi-IN", CARD)
    assert first.text == RAW  # pass-through, byte-identical to input
    assert first.normalized is False
    for _ in range(10):
        again = null.plan(RAW, "hi-IN", CARD)
        assert again.text == first.text  # 10/10 identical
        assert again == first


def test_w5_planner_is_deterministic_10x():
    p = build_speech_planner("sarvam")
    base = p.plan(RAW, "hi-IN", CARD)
    for _ in range(10):
        again = p.plan(RAW, "hi-IN", CARD)
        assert again.text == base.text  # pure function, no randomness
        assert again.segments == base.segments


def test_registering_w5_does_not_mutate_default_kernel():
    # building a kernel WITH W5 must not change a separately-built default kernel
    default = build_kernel()
    _withw5 = build_kernel(speech=build_speech_planner("sarvam"))
    assert isinstance(default.svc.speech, NullSpeechPlanner)  # default untouched
