-- ============================================================================
-- P1 Voice Performance Analytics — ClickHouse schema (run ONCE on the obs droplet's ClickHouse).
--
--   clickhouse-client --multiquery < voice_analytics.sql
--   # or over HTTP:
--   curl -s "$CLICKHOUSE_URL/" --data-binary @voice_analytics.sql
--
-- Written by the voice agent (droplet_work/voice_analytics.py, gated by VOICE_ANALYTICS_ENABLED).
-- Read by the backend (droplet_work/obs_query.py) for the panel's Voice Performance page.
-- Tables live in the `default` database with a haptica_ prefix (SigNoz owns signoz_*); the agent
-- INSERTs unqualified names, so they MUST be in `default`.
--
-- Sizing: LowCardinality on every filter dimension (cheap dictionary encoding); quantile() over the
-- UInt32 *_ms columns gives P95/P99; daily partitions + a 90-day TTL cap storage automatically.
-- ============================================================================

-- One row PER metric event (stage-tagged) → per-utterance timeline + the latency distributions.
CREATE TABLE IF NOT EXISTS haptica_voice_turns
(
    ts                 DateTime64(3),
    call_id            String,
    tenant_id          LowCardinality(String),
    campaign_id        LowCardinality(String),
    agent_name         LowCardinality(String),
    phone              String,
    lead_name          String,                   -- WHO we called (from dispatch metadata)
    stt_provider       LowCardinality(String),
    llm_provider       LowCardinality(String),
    tts_provider       LowCardinality(String),
    stt_model          LowCardinality(String),
    llm_model          LowCardinality(String),
    tts_model          LowCardinality(String),
    voice_id           LowCardinality(String),   -- TTS voice
    voice_name         LowCardinality(String),
    language           LowCardinality(String),
    turn_index         UInt16,
    stage              LowCardinality(String),   -- 'eou' | 'stt' | 'llm' | 'tts'
    speech_id          String,
    latency_ms         UInt32,                   -- eou_delay / transcription_delay(STT) / llm ttft / tts ttfb
    prompt_tokens      UInt32,
    completion_tokens  UInt32,
    tokens_per_second  Float32,                  -- LLM generation rate
    characters         UInt32                    -- TTS characters synthesised
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts, call_id)
TTL toDateTime(ts) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- One header row PER call → live-dashboard KPIs + the filterable call list.
CREATE TABLE IF NOT EXISTS haptica_voice_calls
(
    ts                 DateTime64(3),            -- call start
    ended_at           DateTime64(3),
    call_id            String,
    tenant_id          LowCardinality(String),
    campaign_id        LowCardinality(String),
    agent_name         LowCardinality(String),
    phone              String,
    lead_name          String,                   -- WHO we called
    stt_provider       LowCardinality(String),
    llm_provider       LowCardinality(String),
    tts_provider       LowCardinality(String),
    stt_model          LowCardinality(String),
    llm_model          LowCardinality(String),
    tts_model          LowCardinality(String),
    voice_id           LowCardinality(String),
    voice_name         LowCardinality(String),
    language           LowCardinality(String),
    duration_ms        UInt32,
    status             LowCardinality(String),   -- completed | failed | ...
    outcome            LowCardinality(String),
    turns              UInt32,                   -- user-utterance count (EOU events)
    llm_calls          UInt32,
    tts_calls          UInt32,
    stt_calls          UInt32,
    rate_limit_429     UInt32,
    errors             UInt32,
    in_tokens          UInt32,
    out_tokens         UInt32,
    speech_ms          UInt32,                   -- total USER speech captured (was mislabeled "STT latency")
    characters         UInt32,                   -- total TTS characters synthesised
    net_quality        LowCardinality(String),   -- worst phone-leg LiveKit quality: EXCELLENT|GOOD|POOR|LOST
    net_rtt_ms         UInt32,
    net_packet_loss    Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts, call_id)
TTL toDateTime(ts) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- Idempotent migration for EXISTING installs (the agent now writes these). Safe to re-run.
ALTER TABLE haptica_voice_turns
    ADD COLUMN IF NOT EXISTS lead_name          String,
    ADD COLUMN IF NOT EXISTS voice_id           LowCardinality(String),
    ADD COLUMN IF NOT EXISTS voice_name         LowCardinality(String),
    ADD COLUMN IF NOT EXISTS tokens_per_second  Float32,
    ADD COLUMN IF NOT EXISTS characters         UInt32;

ALTER TABLE haptica_voice_calls
    ADD COLUMN IF NOT EXISTS lead_name        String,
    ADD COLUMN IF NOT EXISTS voice_id         LowCardinality(String),
    ADD COLUMN IF NOT EXISTS voice_name       LowCardinality(String),
    ADD COLUMN IF NOT EXISTS speech_ms        UInt32,
    ADD COLUMN IF NOT EXISTS characters       UInt32,
    ADD COLUMN IF NOT EXISTS net_quality      LowCardinality(String),
    ADD COLUMN IF NOT EXISTS net_rtt_ms       UInt32,
    ADD COLUMN IF NOT EXISTS net_packet_loss  Float32;

-- Performance dashboard (APM) — one row PER HTTP request, written by the backend's http_metrics.py
-- (replaces the SigNoz signoz_traces source). The backend AUTO-CREATES this on first flush; it's
-- here for fresh installs + documentation. Read by obs_query.py (summary/red/routes/status/...).
CREATE TABLE IF NOT EXISTS haptica_http_requests
(
    ts            DateTime64(3),
    service       LowCardinality(String),   -- 'backend'
    method        LowCardinality(String),   -- GET / POST / ...
    route         String,                   -- matched route template (else raw path)
    status_code   UInt16,
    duration_ms   Float32,
    has_error     UInt8,                    -- 1 when status_code >= 500
    tenant_id     LowCardinality(String),
    trace_id      String
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (service, ts)
TTL toDateTime(ts) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- P2.2: per-call, per-key provider usage (cross-process). The agent worker accumulates key health
-- in-process; this table makes it visible to the backend's /admin/provider-pool/usage. One row per
-- (call, provider, key) used — counts are PER-CALL DELTAS (SUM-safe; never lifetime totals).
CREATE TABLE IF NOT EXISTS haptica_provider_key_usage
(
    ts                 DateTime64(3),
    tenant_id          LowCardinality(String),
    provider           LowCardinality(String),   -- groq | sarvam | elevenlabs | ...
    fingerprint        String,                   -- the key's non-reversible fingerprint (never the secret)
    call_id            String,
    calls              UInt32,                    -- 1 per row (this call used this key)
    success            UInt32,                    -- successful provider events this call
    failures           UInt32,
    rate_limits        UInt32,
    latency_ms_avg     UInt32,                    -- avg observed latency for this key this call
    score              Float32,                   -- the key's health score at call end (0..1)
    status             LowCardinality(String)     -- healthy | degraded | cooling
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts, provider)
TTL toDateTime(ts) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- FAMIT RESEARCH — instrumented conversation science (side-pipeline; FAMIT_RESEARCH_ENABLED).
--
-- Written POST-CALL by droplet_work/research_analytics.py (off the live agent loop); read,
-- tenant-scoped, by droplet_work/research_query.py for the panel's "Famit Research" dashboard.
-- ClickHouse has NO row-level security, so tenant isolation is enforced in Python: every read
-- query binds WHERE tenant_id = {tid:String}. Apply ONCE (not auto-created).
--
-- HONEST-SCHEMA NOTE: prosody (F0/loudness/speech-rate/pause) is the shippable 8 kHz-telephony
-- signal; arousal/friction are the online Bayesian-filter latents and EACH carries its variance
-- so the UI draws an uncertainty band. jitter/shimmer/HNR are Nullable + never headline (telephone-
-- band perturbation measures are unreliable per the verdict).
-- ============================================================================

-- One row PER caller turn → the per-call affect/prosody time-series (the call-detail traces).
CREATE TABLE IF NOT EXISTS famit_research_turns
(
    ts                 DateTime64(3),
    tenant_id          LowCardinality(String),
    call_id            String,
    turn_num           UInt16,
    t_sec              Float32,                  -- seconds since call start (trace x-axis)
    speaker            LowCardinality(String),   -- 'caller' (we model the caller)
    f0_mean_hz         Float32,
    f0_range_hz        Float32,
    f0_slope_hz_s      Float32,
    f0_var_hz          Float32,
    loudness_db        Float32,
    speech_rate_sps    Float32,                  -- ASR-timestamp / de Jong-Wempe nuclei
    pause_ratio        Float32,
    turn_latency_ms    Float32,
    voiced_sec         Float32,
    arousal            Float32,                  -- 0..100 index (50 = caller baseline)
    arousal_var        Float32,                  -- filter variance → band 1σ = sqrt(var)
    friction           Float32,
    friction_var       Float32,
    engagement         Float32,                  -- conversational engagement/entrainment axis (0..100)
    engagement_var     Float32,
    valence_hint       Float32,                  -- transcript-sentiment nudge, -1..1
    intent             LowCardinality(String),   -- LLM/heuristic stance (interested|objecting|...)
    intervene          UInt8,                    -- conformal "intervene now" flag this turn
    confidence         Float32,                  -- 0..1 (drives the low-confidence badge)
    source             LowCardinality(String),   -- asr_metadata | acoustic_pyin | egemaps | demo
    regime             LowCardinality(String),   -- steady|warming|rising_friction|disengaging|resolving
    low_conf           UInt8,
    transcript         String,
    -- multimodal channels + predictive (Nullable: present only when that channel/phase is active)
    conversion_risk    Nullable(Float32),        -- 0..100 cumulative conversion-risk through this turn
    llm_valence        Nullable(Float32),        -- LLM buying-stance read, -1..1 (Upgrade #1)
    objection          Nullable(Float32),
    buying_intent      Nullable(Float32),
    talk_share         Nullable(Float32),        -- conversational-dynamics (Upgrade #2)
    backchannel_rate   Nullable(Float32),
    entrainment        Nullable(Float32),
    ssl_arousal        Nullable(Float32),        -- live learned-SER arousal estimate (Upgrade #3)
    jitter_local       Nullable(Float32),        -- clinical extras: confidence-gated, NEVER headline
    shimmer_local      Nullable(Float32),
    hnr_db             Nullable(Float32)
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, call_id, turn_num)
TTL toDateTime(ts) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- One header row PER call → the dashboard KPIs, the call list, and the Outcomes-Lab correlation.
CREATE TABLE IF NOT EXISTS famit_research_calls
(
    ts                 DateTime64(3),
    tenant_id          LowCardinality(String),
    call_id            String,
    turns              UInt16,
    duration_s         Float32,
    arousal_mean       Float32,
    arousal_peak       Float32,
    friction_mean      Float32,
    friction_peak      Float32,
    arousal_trend      Float32,                  -- net first→last (warming vs cooling)
    friction_trend     Float32,
    engagement_mean    Float32,
    engagement_peak    Float32,
    engagement_trend   Float32,
    conversion_risk    Float32,                  -- final calibrated conversion-risk 0..100
    intervene          UInt8,                    -- the call crossed the conformal intervene trigger
    top_intent         LowCardinality(String),   -- most common stance on the call
    f0_mean_hz         Float32,
    speech_rate_sps    Float32,
    pause_ratio        Float32,
    confidence         Float32,
    source             LowCardinality(String),
    regimes            String,                   -- comma-joined regime run (in order seen)
    outcome            LowCardinality(String),   -- lead_status / funnel_stage / booking_status
    converted          UInt8,
    has_outcome        UInt8,                    -- 0 when the outcome is not yet known
    deal_value         Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts, call_id)
TTL toDateTime(ts) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- HAPTICA FLYWHEEL — the self-improvement-engine warehouse (RLHF/RLAIF data moat).
-- Source of truth: voice_ops/flywheel/db/ddl_flywheel.sql (kept in lockstep with this copy).
-- Same conventions as famit_research_* above. The two CONTROL tables (arm posteriors,
-- challengers) are ReplacingMergeTree(ts) — read them with `... FINAL`.
-- ============================================================================

CREATE TABLE IF NOT EXISTS flywheel_trajectories
(
    ts                      DateTime64(3),
    tenant_id               LowCardinality(String),
    call_id                 String,
    turn_num                UInt16,
    campaign_id             LowCardinality(String),
    vertical                LowCardinality(String),
    lead_temperature        LowCardinality(String),
    move_type               LowCardinality(String),
    objection_type          LowCardinality(String),
    arm_model               LowCardinality(String),
    arm_voice               LowCardinality(String),
    arm_variant             LowCardinality(String),
    propensity              Float32,
    state_friction          Float32,
    state_arousal           Float32,
    state_regime            LowCardinality(String),
    affect_delta            Float32,
    judge_score             Float32,
    rubric_json             String,
    credit_advantage        Float32,
    reward_raw              Float32,
    reward_capped           Float32,
    reward_components_json  String,
    confidence              Float32,
    low_conf                UInt8,
    judge_model_id          LowCardinality(String),
    rubric_version          LowCardinality(String),
    agent_text              String,
    caller_text             String
)
-- ReplacingMergeTree(ts): seed-then-enrich (worker rewrites with a newer ts); read with FINAL.
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, call_id, turn_num)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS flywheel_preferences
(
    ts                  DateTime64(3),
    tenant_id           LowCardinality(String),
    pair_id             String,
    state_embedding_id  String,
    objection_type      LowCardinality(String),
    lead_temperature    LowCardinality(String),
    regime              LowCardinality(String),
    vertical            LowCardinality(String),
    chosen_text         String,
    rejected_text       String,
    chosen_move_id      String,
    rejected_move_id    String,
    margin              Float32,
    source              LowCardinality(String),
    survived_swap       UInt8,
    confidence          Float32,
    compliant           UInt8,
    outcome_anchored    UInt8,
    campaign_id         LowCardinality(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, objection_type, lead_temperature)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS flywheel_arm_posteriors
(
    ts                          DateTime64(3),
    tenant_id                   LowCardinality(String),
    campaign_id                 LowCardinality(String),
    vertical                    LowCardinality(String),
    knob                        LowCardinality(String),
    arm_id                      LowCardinality(String),
    context_bucket              LowCardinality(String),
    alpha                       Float32,
    beta                        Float32,
    plays                       UInt32,
    reward_sum                  Float32,
    last_reward_ts              DateTime64(3),
    discounted                  Float32,
    guardrail_optout_rate       Float32,
    guardrail_cost_per_booking  Float32
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, campaign_id, knob, arm_id, context_bucket)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS flywheel_move_prm
(
    ts                  DateTime64(3),
    tenant_id           LowCardinality(String),
    vertical            LowCardinality(String),
    move_type           LowCardinality(String),
    objection_type      LowCardinality(String),
    regime              LowCardinality(String),
    lead_temperature    LowCardinality(String),
    book_rate           Float32,
    baseline_rate       Float32,
    lift                Float32,
    n_samples           UInt32,
    ci_low              Float32,
    ci_high             Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, vertical, move_type, regime)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS flywheel_challengers
(
    ts                      DateTime64(3),
    tenant_id               LowCardinality(String),
    challenger_id           String,
    kind                    LowCardinality(String),
    campaign_id             LowCardinality(String),
    proposed_config_json    String,
    rationale               String,
    ope_snips_value         Float32,
    gates_passed            UInt8,
    replay_delta            Float32,
    shadow_ok               UInt8,
    status                  LowCardinality(String),
    approved_by             LowCardinality(String),
    reward_lift             Float32,
    ttft_ms                 UInt32,
    cost_per_appointment    Float32
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, challenger_id)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS flywheel_human_labels
(
    ts                      DateTime64(3),
    tenant_id               LowCardinality(String),
    call_id                 String,
    turn_num                UInt16,
    trigger                 LowCardinality(String),
    label                   LowCardinality(String),
    labeler                 LowCardinality(String),
    rationale               String,
    used_for_calibration    UInt8
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS flywheel_monitors
(
    ts                  DateTime64(3),
    tenant_id           LowCardinality(String),
    metric              LowCardinality(String),
    value               Float32,
    arm_id              LowCardinality(String),
    threshold_breached  UInt8
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- HAPTICA FLYWHEEL — POWER-UP TIER (B1–B7) additive DDL (apply after the base flywheel tables).
-- ALTERs are idempotent (ADD COLUMN IF NOT EXISTS). Model/control tables are ReplacingMergeTree(ts)
-- (latest-per-key; read with `... FINAL`). Same MergeTree conventions as above.
-- ============================================================================

ALTER TABLE flywheel_trajectories
    ADD COLUMN IF NOT EXISTS v_state               Float32,
    ADD COLUMN IF NOT EXISTS v_momentum            Float32,
    ADD COLUMN IF NOT EXISTS ensemble_mean         Float32,
    ADD COLUMN IF NOT EXISTS ensemble_var          Float32,
    ADD COLUMN IF NOT EXISTS lcb_reward            Float32,
    ADD COLUMN IF NOT EXISTS value_head            Float32,
    ADD COLUMN IF NOT EXISTS counterfactual_delta  Float32,
    ADD COLUMN IF NOT EXISTS counterfactual_n      UInt32,
    ADD COLUMN IF NOT EXISTS list_source           LowCardinality(String),
    ADD COLUMN IF NOT EXISTS play_template_id       LowCardinality(String),
    ADD COLUMN IF NOT EXISTS state_feature_json    String;

ALTER TABLE flywheel_challengers
    ADD COLUMN IF NOT EXISTS sim_reward_lift   Float32,
    ADD COLUMN IF NOT EXISTS sim_preeval_json  String,
    ADD COLUMN IF NOT EXISTS ope_cs_lower      Float32,
    ADD COLUMN IF NOT EXISTS ope_cs_upper      Float32,
    ADD COLUMN IF NOT EXISTS reward_cs_lower   Float32,
    ADD COLUMN IF NOT EXISTS optout_cs_upper   Float32,
    ADD COLUMN IF NOT EXISTS seq_significant   UInt8,
    ADD COLUMN IF NOT EXISTS practical_sig     UInt8,
    ADD COLUMN IF NOT EXISTS adapter_uri       String,
    ADD COLUMN IF NOT EXISTS base_model        LowCardinality(String),
    ADD COLUMN IF NOT EXISTS method            LowCardinality(String),
    ADD COLUMN IF NOT EXISTS serving_endpoint  String,
    ADD COLUMN IF NOT EXISTS is_shadow         UInt8;

-- B4 — doubly-robust X-learner CATE per (move, state): causal booking lift, honest CI, beside raw_lift.
CREATE TABLE IF NOT EXISTS flywheel_move_cate
(
    ts                DateTime64(3),
    tenant_id         LowCardinality(String),
    vertical          LowCardinality(String),
    move_type         LowCardinality(String),
    objection_type    LowCardinality(String),
    regime            LowCardinality(String),
    lead_temperature  LowCardinality(String),
    cate              Float32,
    cate_se           Float32,
    cate_lower        Float32,
    cate_upper        Float32,
    raw_lift          Float32,
    n_treated         UInt32,
    n_control         UInt32,
    overlap_min       Float32,
    estimator         LowCardinality(String),
    sign_agree        UInt8
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, vertical, move_type, regime)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- B3 — learned V(state)->P(book) critic (coefficients + Platt calibration), latest per tenant.
CREATE TABLE IF NOT EXISTS flywheel_critic_models
(
    ts          DateTime64(3),
    tenant_id   LowCardinality(String),
    vertical    LowCardinality(String),
    model_type  LowCardinality(String),
    coef_json   String,
    platt_a     Float32,
    platt_b     Float32,
    auc         Float32,
    ece         Float32,
    n_rows      UInt32,
    active      UInt8
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, vertical)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- B6 — contextual LinTS per-state selector (per-arm sufficient stats + 3-leg OPE), latest per tenant.
CREATE TABLE IF NOT EXISTS flywheel_policy_models
(
    ts          DateTime64(3),
    tenant_id   LowCardinality(String),
    campaign_id LowCardinality(String),
    vertical    LowCardinality(String),
    knob        LowCardinality(String),
    n_features  UInt16,
    arms_json   String,
    ope_snips   Float32,
    ope_fqe     Float32,
    ope_magic   Float32,
    ope_lower   Float32,
    active      UInt8
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, campaign_id, knob)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- B6 — the data-defined per-tenant rebuttal/play action space the policy selects over.
CREATE TABLE IF NOT EXISTS flywheel_play_library
(
    ts              DateTime64(3),
    tenant_id       LowCardinality(String),
    template_id     LowCardinality(String),
    objection_type  LowCardinality(String),
    text            String,
    label           LowCardinality(String),
    active          UInt8
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, template_id)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- B5 — mined caller archetypes (intent + affect template + temperament) the simulator role-plays.
CREATE TABLE IF NOT EXISTS flywheel_archetypes
(
    ts                    DateTime64(3),
    tenant_id             LowCardinality(String),
    archetype_id          LowCardinality(String),
    label                 LowCardinality(String),
    objection_hist_json   String,
    affect_template_json  String,
    temperament           LowCardinality(String),
    base_book_rate        Float32,
    weight                Float32,
    n_calls               UInt32
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, archetype_id)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- B5 — simulator rollout audit (the sim is FILTER-ONLY: it proposes/removes, never promotes).
CREATE TABLE IF NOT EXISTS flywheel_sim_rollouts
(
    ts            DateTime64(3),
    tenant_id     LowCardinality(String),
    archetype_id  LowCardinality(String),
    challenger_id String,
    policy_label  LowCardinality(String),
    sim_outcome   LowCardinality(String),
    sim_reward    Float32,
    turns         UInt16,
    usi           Float32,
    ece           Float32,
    notes         String
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts)
TTL toDateTime(ts) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- B7 — KTO/SimPO QLoRA training-run audit (the adapter ships ONLY as a shadow challenger).
CREATE TABLE IF NOT EXISTS flywheel_distill_runs
(
    ts             DateTime64(3),
    tenant_id      LowCardinality(String),
    run_id         String,
    method         LowCardinality(String),
    base_model     LowCardinality(String),
    n_desirable    UInt32,
    n_undesirable  UInt32,
    status         LowCardinality(String),
    adapter_uri    String,
    metrics_json   String
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- B2 — persisted running sufficient stats for the anytime-valid promotion test (survives restarts).
CREATE TABLE IF NOT EXISTS flywheel_sequential_state
(
    ts            DateTime64(3),
    tenant_id     LowCardinality(String),
    challenger_id String,
    metric        LowCardinality(String),
    n             UInt32,
    running_mean  Float32,
    running_var   Float32,
    cs_lower      Float32,
    cs_upper      Float32,
    significant   UInt8
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, challenger_id, metric)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- B2 — Mondrian (group-conditional) split-conformal q_hat per cohort bucket, latest per key.
CREATE TABLE IF NOT EXISTS flywheel_conformal_calib
(
    ts         DateTime64(3),
    tenant_id  LowCardinality(String),
    model_key  LowCardinality(String),
    bucket     String,
    q_hat      Float32,
    alpha      Float32,
    n_calib    UInt32
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, model_key, bucket)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;
