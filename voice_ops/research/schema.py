"""voice_ops.research.schema — the Famit Research wire contract.

ONE row per conversational turn (`ResearchTurn`) + one rollup per call/range
(`ResearchSummary`). These dataclasses are the single source of truth for:
  * the ClickHouse `famit_research_turns` columns (research_analytics.py),
  * the JSON the backend serves to the panel (research_query.py),
  * the TypeScript `ResearchTurn` / `ResearchSummary` types (famit-panel/lib/api.ts).
Keep the three in lockstep.

Field design follows the honest-science verdict (see package docstring):
  * Prosody features are the SHIPPABLE set on 8 kHz telephony: F0 statistics,
    loudness, ASR-derived speech rate, pause/turn timing.
  * `arousal` / `friction` are the latent affect axes from the Bayesian filter; each
    carries a *variance* (the filter covariance) so the UI can draw an uncertainty
    band — a number without its uncertainty is not a measurement.
  * `confidence` (0..1) drives the in-product "low-confidence on 8 kHz" badge.
  * `source` records HOW the row was produced ('asr_metadata' = cheap in-call signal,
    'acoustic_pyin' = post-call F0 tracker, 'egemaps' = full functional set, 'demo' =
    synthetic). The UI shows this verbatim so a viewer always knows the provenance.
  * `jitter_local` / `shimmer_local` exist but are OPTIONAL, segment-aggregated and
    `low_conf` — never headline (telephone-band perturbation measures are unreliable).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ResearchTurn:
    # --- identity / routing ------------------------------------------------- #
    tenant_id: str = ""
    call_id: str = ""
    turn_num: int = 0
    ts_iso: str = ""                       # canonical UTC timestamp of the turn
    t_sec: float = 0.0                     # seconds since call start (x-axis on traces)
    speaker: str = "caller"               # 'caller' | 'agent' (we model the caller)

    # --- prosody (the defensible, shippable acoustic set) ------------------- #
    f0_mean_hz: float = 0.0                # mean voiced F0 over the turn (pyin)
    f0_range_hz: float = 0.0              # voiced F0 max-min (expressiveness)
    f0_slope_hz_s: float = 0.0           # linear F0 trend across the turn
    f0_var_hz: float = 0.0               # F0 contour variability (persuasion-relevant)
    loudness_db: float = 0.0             # RMS energy in dB (relative)
    speech_rate_sps: float = 0.0         # syllables/sec — ASR timestamps or de Jong-Wempe
    pause_ratio: float = 0.0             # fraction of the turn window that was silence
    turn_latency_ms: float = 0.0         # end-of-user-speech → agent reply (responsiveness)
    voiced_sec: float = 0.0              # voiced duration the features were computed over

    # --- latent affect state (online multimodal Kalman; NOT fake physics) --- #
    arousal: float = 0.0                  # calibrated 0..100 index (50 = caller baseline)
    arousal_var: float = 0.0             # filter variance → uncertainty band half-width
    friction: float = 0.0                 # cognitive-friction index, 0..100 (50 = baseline)
    friction_var: float = 0.0
    engagement: float = 50.0             # conversational engagement/entrainment, 0..100
    engagement_var: float = 0.0
    valence_hint: float = 0.0            # optional transcript-sentiment nudge, -1..1

    # --- LLM-as-valence sensor (Upgrade #1) + conversational dynamics (#2) --- #
    llm_valence: Optional[float] = None  # LLM read of buying-stance, -1..1
    intent: str = ""                     # one-word LLM/heuristic stance (interested|objecting|...)
    objection: Optional[float] = None
    buying_intent: Optional[float] = None
    talk_share: Optional[float] = None   # caller share of recent talk time (0..1)
    backchannel_rate: Optional[float] = None
    entrainment: Optional[float] = None  # prosodic rate stability (0..1; higher = entrained)
    ssl_arousal: Optional[float] = None  # learned-SER arousal estimate (0..1) when the tap is live

    # --- predictive (Phase 2): per-turn calibrated conversion risk + trigger - #
    conversion_risk: Optional[float] = None   # 0..100, cumulative through this turn
    intervene: bool = False                   # conformal "intervene now" flag

    # --- honesty metadata --------------------------------------------------- #
    confidence: float = 0.0              # 0..1 overall feature confidence (drives badge)
    source: str = "asr_metadata"         # provenance (see module docstring)
    regime: str = "steady"               # steady|warming|rising_friction|disengaging|resolving
    low_conf: bool = False               # True when any value is flagged unreliable

    # --- optional clinical extras (NEVER headline; telephone-band-unreliable) #
    jitter_local: Optional[float] = None
    shimmer_local: Optional[float] = None
    hnr_db: Optional[float] = None

    # --- context (call-detail only; PII-light) ----------------------------- #
    transcript: str = ""

    def to_row(self) -> dict:
        """ClickHouse JSONEachRow dict (None optionals dropped — the table has them
        Nullable, but a missing key is cleaner than an explicit null)."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class ResearchSummary:
    """Per-call (or per-range) rollup the dashboard hero cards read."""
    tenant_id: str = ""
    call_id: str = ""
    started_iso: str = ""                # canonical UTC call start — the header ClickHouse `ts`
                                         # (so a backfill/seed lands in the right time window/partition,
                                         # not under "now"). Derived from the first turn when not set.
    turns: int = 0
    duration_s: float = 0.0

    # affect trajectory shape (the "what happened to the caller" headline)
    arousal_mean: float = 50.0
    arousal_peak: float = 50.0
    friction_mean: float = 50.0
    friction_peak: float = 50.0
    arousal_trend: float = 0.0           # net change first→last (warming vs cooling)
    friction_trend: float = 0.0
    engagement_mean: float = 50.0
    engagement_peak: float = 50.0
    engagement_trend: float = 0.0

    # predictive headline (Phase 2)
    conversion_risk: float = 0.0         # final calibrated conversion-risk 0..100
    intervene: bool = False              # the call crossed the conformal intervene trigger
    top_intent: str = ""                 # most common LLM/heuristic stance on the call

    # prosody headline
    f0_mean_hz: float = 0.0
    speech_rate_sps: float = 0.0
    pause_ratio: float = 0.0

    # honesty
    confidence: float = 0.0
    source: str = "asr_metadata"
    regimes: list = field(default_factory=list)   # regimes observed, in order seen

    # outcome join (filled from the reporting FactCall when available)
    outcome: str = ""                    # lead_status / funnel_stage / booking_status
    converted: Optional[bool] = None
    deal_value: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
