"""voice_ops.eval.metrics — the metrics that MATTER for a voice brain.

The founder asked for the RIGHT metrics, not vanity ones:

  * TTFA — Time To First Audio. The brain's contribution to TTFA is the wall-clock
    cost of `assemble_prefix_core(ctx)` — the SYNC, await-free L0..L3 assembly used
    to construct the Agent and fire the opener with NO network I/O. The kernel
    CONTRACT says there is no await between prefix-core and the opener; this module
    MEASURES that core assembly latency and lets a gate assert a wall-clock bound.

  * TOKENS — the system-prompt token footprint (drives both LLM cost AND TTFT). We
    estimate it from the assembled prompt via the kernel's own estimator.

  * COST-PER-OUTCOME — cost per APPOINTMENT (or per booked next step), NOT per turn.
    A brain that is cheap per turn but never books is expensive; a brain that costs
    more per turn but books reliably is cheap. We model
        cost_per_appointment = total_llm_cost / appointments_booked
    over a batch of replayed conversations, using per-provider $/1k-token rates and
    the per-conversation outcome. This is the unit economics number the founder
    cares about (it mirrors the sales-research "cost-per-resolved-contact").

Pure + droplet-free. The kernel is driven only through the tracked façade; the box
is never touched. Timing uses time.perf_counter (monotonic).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .regression_gates import build_facade, kernel_outbound_on

# Indicative per-provider LLM $/1k-token rates (input). These are TUNABLE knobs for
# the unit-economics model, NOT a billing source of truth — the founder's real
# meter lives in droplet_work/wallet. Defaults are conservative public list prices
# for the kinds of models the router selects (Groq Llama-class).
DEFAULT_RATE_PER_1K_TOKENS: float = 0.0006  # USD per 1k input tokens (Groq-class)

# A typical reply length (output tokens) per turn, for the cost model. The system
# prompt is sent once (cacheable); each turn adds a small completion. Tunable.
DEFAULT_OUTPUT_TOKENS_PER_TURN: int = 60


@dataclass(frozen=True)
class ConversationMetrics:
    """Per-conversation metrics derived by replaying it through the kernel."""

    name: str
    ttfa_core_ms: float  # wall-clock cost of assemble_prefix_core (the brain's TTFA share)
    prompt_tokens: int  # system-prompt token footprint
    turns: int
    output_tokens: int  # estimated completion tokens across turns
    total_tokens: int  # prompt + per-turn output
    est_cost_usd: float  # estimated LLM cost for this conversation
    booked: bool  # did this conversation reach a booked next step / appointment?


@dataclass
class BatchMetrics:
    """Aggregate metrics over a batch of replayed conversations."""

    conversations: list[ConversationMetrics] = field(default_factory=list)
    rate_per_1k: float = DEFAULT_RATE_PER_1K_TOKENS

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c.est_cost_usd for c in self.conversations), 6)

    @property
    def appointments(self) -> int:
        return sum(1 for c in self.conversations if c.booked)

    @property
    def cost_per_appointment_usd(self) -> Optional[float]:
        """THE metric: total LLM cost / appointments booked. None if zero booked
        (an infinite cost — surfaced explicitly, never silently divided by zero)."""
        n = self.appointments
        if n == 0:
            return None
        return round(self.total_cost_usd / n, 6)

    @property
    def max_ttfa_core_ms(self) -> float:
        return round(max((c.ttfa_core_ms for c in self.conversations), default=0.0), 3)

    def summary(self) -> str:
        cpa = self.cost_per_appointment_usd
        cpa_s = f"${cpa:.6f}" if cpa is not None else "n/a (0 booked)"
        return (
            f"conversations={len(self.conversations)} appointments={self.appointments} "
            f"total_cost=${self.total_cost_usd:.6f} cost_per_appointment={cpa_s} "
            f"max_ttfa_core={self.max_ttfa_core_ms}ms"
        )


def measure_ttfa_core_ms(fields: dict, *, repeat: int = 5) -> float:
    """Measure the wall-clock cost (ms) of the kernel's sync, await-free
    `assemble_prefix_core` — the brain's TTFA contribution (the opener fires off
    this with NO network I/O). Takes the MIN over `repeat` runs (least-noisy
    estimate of the pure compute cost). Asserts the path is await-free by timing a
    purely synchronous call."""
    from voice_kernel.errors import KernelError

    with kernel_outbound_on():
        ik = build_facade(fields)
        if ik is None:
            raise KernelError("kernel did not engage for TTFA measurement")
        ctx = ik.base_ctx
        best = float("inf")
        for _ in range(max(1, repeat)):
            t0 = time.perf_counter()
            ik.kernel.assemble_prefix_core(ctx)  # SYNC, no await
            dt = (time.perf_counter() - t0) * 1000.0
            best = min(best, dt)
    return round(best, 4)


def _conversation_booked(turns) -> bool:
    """Heuristic outcome model for the golden/replay sets: a conversation counts as
    a booked appointment if a caller turn carries a booking/visit/confirm intent.
    Real production wires this to the booking record (voice_ops.booking); for the
    eval batch we infer it from the golden turns so the cost-per-appointment model
    is exercised deterministically."""
    intents = ("site visit", "book", "appointment", "confirmed", "confirm", "visit karna", "visit")
    for t in turns:
        text = (t[0] if isinstance(t, tuple) else getattr(t, "user_text", "")).lower()
        if any(k in text for k in intents):
            return True
    return False


def collect_conversation_metrics(
    name: str,
    fields: dict,
    turns,
    *,
    rate_per_1k: float = DEFAULT_RATE_PER_1K_TOKENS,
    output_tokens_per_turn: int = DEFAULT_OUTPUT_TOKENS_PER_TURN,
) -> ConversationMetrics:
    """Replay one conversation's WARM assembly + count tokens + estimate cost +
    derive the booked outcome. `turns` is a sequence of GoldenTurn or
    (user_text, stt_lang, ...) tuples."""
    from voice_kernel.tokens import estimate_tokens

    import voice_kernel.integrations.outbound as ob

    ttfa = measure_ttfa_core_ms(fields)
    with kernel_outbound_on():
        ik = build_facade(fields, campaign_id=f"camp-{name}")
        prompt = ob.assemble_outbound_instructions(ik, legacy_render=lambda: "")
    prompt_tokens = estimate_tokens(prompt)
    n_turns = len(list(turns))
    output_tokens = n_turns * output_tokens_per_turn
    total_tokens = prompt_tokens + output_tokens
    # cost model: the system prompt is paid once; per-turn output is the completion.
    est_cost = (total_tokens / 1000.0) * rate_per_1k
    return ConversationMetrics(
        name=name,
        ttfa_core_ms=ttfa,
        prompt_tokens=prompt_tokens,
        turns=n_turns,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        est_cost_usd=round(est_cost, 8),
        booked=_conversation_booked(turns),
    )


class MetricsCollector:
    """Collects metrics across a batch of conversations and computes the unit
    economics (cost-per-appointment). The shape the founder asked for; production
    swaps `booked` for the real booking record + the real wallet meter."""

    def __init__(self, rate_per_1k: float = DEFAULT_RATE_PER_1K_TOKENS) -> None:
        self.batch = BatchMetrics(rate_per_1k=rate_per_1k)

    def add_golden(self, g) -> ConversationMetrics:
        m = collect_conversation_metrics(g.name, g.fields, g.turns, rate_per_1k=self.batch.rate_per_1k)
        self.batch.conversations.append(m)
        return m

    def collect_all_goldens(self) -> BatchMetrics:
        from .verticals import all_goldens

        for g in all_goldens():
            self.add_golden(g)
        return self.batch


__all__ = [
    "DEFAULT_RATE_PER_1K_TOKENS", "DEFAULT_OUTPUT_TOKENS_PER_TURN",
    "ConversationMetrics", "BatchMetrics",
    "measure_ttfa_core_ms", "collect_conversation_metrics", "MetricsCollector",
]
