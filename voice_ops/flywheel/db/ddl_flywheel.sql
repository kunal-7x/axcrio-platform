-- ============================================================================
-- Haptica Flywheel — ClickHouse DDL (the self-improvement-engine warehouse).
--
-- Apply ONCE by the operator (also appended to deploy/observability/voice_analytics.sql).
-- The Python writers (voice_ops/flywheel/store.py) NEVER auto-create a table — a missing
-- table fails the INSERT silently (logged WARNING), never the call.
--
-- Conventions mirror famit_research_* exactly: MergeTree, PARTITION BY toYYYYMMDD(ts),
-- ORDER BY (tenant_id, ...), LowCardinality for enums/tenant, Nullable only when truly
-- optional, TTL for retention, index_granularity = 8192. The two CONTROL tables (arm
-- posteriors, challengers) are ReplacingMergeTree(ts) so the latest row per key wins —
-- read them with `... FINAL`. The DATASET tables are append-only MergeTree.
--
-- TENANT ISOLATION: ClickHouse has no row-level security. Every backend read binds
-- WHERE tenant_id = {tid:String}; the Python scope IS the boundary.
-- ============================================================================

-- One row PER agent turn — the RL (state, action, reward) unit. The credit-assignment
-- output (credit_advantage) + per-move tag is what answers "which move was +/-".
CREATE TABLE IF NOT EXISTS flywheel_trajectories
(
    ts                      DateTime64(3),
    tenant_id               LowCardinality(String),
    call_id                 String,
    turn_num                UInt16,
    campaign_id             LowCardinality(String),
    vertical                LowCardinality(String),
    lead_temperature        LowCardinality(String),   -- hot|warm|cold|dead|unknown
    move_type               LowCardinality(String),   -- opening|probe|objection_rebuttal|...
    objection_type          LowCardinality(String),   -- price|loan|location|...|none
    arm_model               LowCardinality(String),   -- the live LLM arm
    arm_voice               LowCardinality(String),   -- the live TTS voice arm
    arm_variant             LowCardinality(String),   -- the live A/B variant arm
    propensity              Float32,                  -- P(arm|policy) at decision time (OPE-load-bearing)
    state_friction          Float32,                  -- caller affect (Famit Research), 0..100
    state_arousal           Float32,
    state_regime            LowCardinality(String),
    affect_delta            Float32,                  -- PBRS friction-shaping (tier-3, conf-gated)
    judge_score             Float32,                  -- RLAIF rubric scalar (tier-3, sampled; 0 if unjudged)
    rubric_json             String,                   -- per-dimension judge breakdown
    credit_advantage        Float32,                  -- credit.py per-turn advantage (the +/- signal)
    reward_raw              Float32,
    reward_capped           Float32,
    reward_components_json  String,                   -- RewardComponents provenance (honest science)
    confidence              Float32,
    low_conf                UInt8,
    judge_model_id          LowCardinality(String),   -- pinned cross-family judge (provenance)
    rubric_version          LowCardinality(String),   -- a bump re-triggers the gate
    agent_text              String,                   -- what Riya said (the action)
    caller_text             String                    -- the caller turn that prompted it
)
-- ReplacingMergeTree(ts): the sync finalize hook writes a fast SEED row; the worker later
-- rewrites the ENRICHED row (judge + refined credit) with a newer ts and the latest wins.
-- Idempotent re-processing. Read with `... FINAL` (store.read_trajectory does).
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, call_id, turn_num)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- The proprietary (chosen, rejected) preference MOAT. Outcome-anchored + compliant only.
CREATE TABLE IF NOT EXISTS flywheel_preferences
(
    ts                  DateTime64(3),
    tenant_id           LowCardinality(String),
    pair_id             String,
    state_embedding_id  String,                       -- matched-state bucket key
    objection_type      LowCardinality(String),
    lead_temperature    LowCardinality(String),
    regime              LowCardinality(String),
    vertical            LowCardinality(String),
    chosen_text         String,
    rejected_text       String,
    chosen_move_id      String,                       -- call_id:turn_num
    rejected_move_id    String,
    margin              Float32,                      -- reward(chosen) - reward(rejected)
    source              LowCardinality(String),       -- within_call|matched_state|rubric_pairwise
    survived_swap       UInt8,                        -- pairwise judge survived A/B position swap
    confidence          Float32,
    compliant           UInt8,                        -- chosen passed the Tier-1 hard gate
    outcome_anchored    UInt8,                        -- chosen sits on a real converted call
    campaign_id         LowCardinality(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, objection_type, lead_temperature)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- Hierarchical Thompson-sampling bandit state. ReplacingMergeTree(ts): latest per arm wins.
CREATE TABLE IF NOT EXISTS flywheel_arm_posteriors
(
    ts                          DateTime64(3),
    tenant_id                   LowCardinality(String),
    campaign_id                 LowCardinality(String),
    vertical                    LowCardinality(String),
    knob                        LowCardinality(String),   -- model|voice|variant|opening|rebuttal
    arm_id                      LowCardinality(String),
    context_bucket              LowCardinality(String),   -- e.g. lead_temperature
    alpha                       Float32,                  -- Beta(alpha,beta) success pseudo-count
    beta                        Float32,                  -- failure pseudo-count
    plays                       UInt32,
    reward_sum                  Float32,
    last_reward_ts              DateTime64(3),
    discounted                  Float32,                  -- discounted mass (non-stationarity)
    guardrail_optout_rate       Float32,
    guardrail_cost_per_booking  Float32
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, campaign_id, knob, arm_id, context_bucket)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- Per-move process reward model P(book | move at state) — Math-Shepherd style, with CIs.
CREATE TABLE IF NOT EXISTS flywheel_move_prm
(
    ts                  DateTime64(3),
    tenant_id           LowCardinality(String),
    vertical            LowCardinality(String),
    move_type           LowCardinality(String),
    objection_type      LowCardinality(String),
    regime              LowCardinality(String),
    lead_temperature    LowCardinality(String),
    book_rate           Float32,                      -- P(book | this move at this state)
    baseline_rate       Float32,                      -- cohort base rate
    lift                Float32,                      -- book_rate - baseline_rate (the +/- signal)
    n_samples           UInt32,
    ci_low              Float32,
    ci_high             Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, vertical, move_type, regime)
TTL toDateTime(ts) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- Gated promotion queue + audit trail. ReplacingMergeTree(ts): latest status per challenger.
CREATE TABLE IF NOT EXISTS flywheel_challengers
(
    ts                      DateTime64(3),
    tenant_id               LowCardinality(String),
    challenger_id           String,
    kind                    LowCardinality(String),   -- bandit_arm|prompt|rebuttal|variant
    campaign_id             LowCardinality(String),
    proposed_config_json    String,
    rationale               String,
    ope_snips_value         Float32,                  -- off-policy estimate from logged calls
    gates_passed            UInt8,
    replay_delta            Float32,                  -- cost-per-appointment delta vs champion
    shadow_ok               UInt8,
    status                  LowCardinality(String),   -- proposed|gated|approved|promoted|rejected|reverted
    approved_by             LowCardinality(String),
    reward_lift             Float32,
    ttft_ms                 UInt32,                   -- latency budget (voice cares about TTFT)
    cost_per_appointment    Float32
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, challenger_id)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- The triggered RLHF human-label queue (the HITL spend — ~1-5% of calls).
CREATE TABLE IF NOT EXISTS flywheel_human_labels
(
    ts                      DateTime64(3),
    tenant_id               LowCardinality(String),
    call_id                 String,
    turn_num                UInt16,
    trigger                 LowCardinality(String),   -- judge_affect_disagreement|high_value_lost|...
    label                   LowCardinality(String),   -- '' = unlabeled (open queue item)
    labeler                 LowCardinality(String),
    rationale               String,
    used_for_calibration    UInt8
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (tenant_id, ts)
TTL toDateTime(ts) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- Degrading-flywheel detectors (the Goodhart canary).
CREATE TABLE IF NOT EXISTS flywheel_monitors
(
    ts                  DateTime64(3),
    tenant_id           LowCardinality(String),
    metric              LowCardinality(String),       -- judge_vs_outcome_corr|optout_rate|...
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
