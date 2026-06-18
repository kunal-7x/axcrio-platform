"""W17 — metrics that matter: TTFA, tokens, cost-per-appointment (not per-turn)."""
from __future__ import annotations

from voice_ops.eval.metrics import (
    MetricsCollector,
    collect_conversation_metrics,
    measure_ttfa_core_ms,
)
from voice_ops.eval.verticals import all_goldens


# A generous CI bound: the brain's TTFA share (sync assemble_prefix_core, no await)
# must be small. On the box it is sub-millisecond; we assert << 50ms so the
# "no await between prefix-core and the opener" contract is enforced as a wall-clock
# bound, not just a comment.
_TTFA_CORE_BOUND_MS = 50.0


def test_ttfa_core_is_await_free_and_bounded():
    g = next(x for x in all_goldens() if x.name == "real_estate_sales_lean_sarvam")
    ttfa = measure_ttfa_core_ms(g.fields)
    assert ttfa >= 0.0
    assert ttfa < _TTFA_CORE_BOUND_MS, (
        f"assemble_prefix_core took {ttfa}ms (> {_TTFA_CORE_BOUND_MS}ms) — the opener path is not await-free"
    )


def test_per_conversation_metrics_shape():
    g = next(x for x in all_goldens() if x.name == "real_estate_sales_lean_sarvam")
    m = collect_conversation_metrics(g.name, g.fields, g.turns)
    assert m.prompt_tokens > 0
    assert m.turns == len(g.turns)
    assert m.total_tokens >= m.prompt_tokens
    assert m.est_cost_usd > 0.0
    # the real-estate sales golden ends on a site-visit booking intent.
    assert m.booked is True


def test_cost_per_appointment_is_the_unit_metric():
    """The batch metric is cost-per-APPOINTMENT, not per-turn. With >=1 booked
    conversation it is a finite number; the model divides total cost by bookings."""
    batch = MetricsCollector().collect_all_goldens()
    assert len(batch.conversations) == len(all_goldens())
    assert batch.appointments >= 1
    cpa = batch.cost_per_appointment_usd
    assert cpa is not None and cpa > 0.0
    # cost-per-appointment must be >= average per-conversation cost (fewer bookings
    # than conversations => the per-outcome cost is higher than per-conversation).
    avg_per_conv = batch.total_cost_usd / len(batch.conversations)
    assert cpa >= avg_per_conv


def test_cost_per_appointment_none_when_zero_booked():
    """Division-by-zero is surfaced explicitly (None), never a crash, when nothing
    booked — the founder sees 'n/a (0 booked)', an infinite cost, not a silent 0."""
    from voice_ops.eval.metrics import BatchMetrics, ConversationMetrics

    b = BatchMetrics(conversations=[
        ConversationMetrics("c1", 0.3, 1000, 2, 120, 1120, 0.001, booked=False),
    ])
    assert b.appointments == 0
    assert b.cost_per_appointment_usd is None
    assert "0 booked" in b.summary()


def test_max_ttfa_core_aggregate():
    batch = MetricsCollector().collect_all_goldens()
    assert batch.max_ttfa_core_ms < _TTFA_CORE_BOUND_MS
