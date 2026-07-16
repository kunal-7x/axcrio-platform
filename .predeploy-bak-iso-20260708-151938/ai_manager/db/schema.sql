-- ============================================================================
-- ai_manager/db/schema.sql
-- AI Manager — FORCE-RLS persistence, vendor/tenant isolated.
-- Spec: plans/AI_MANAGER_MASTER_PROMPT.md §8 + AIM_CALL_LOGGING_STATE.md (P1).
--
-- RLS = admin-GUC policy shape verbatim (ddl_grow.sql / ddl_wallet.sql):
--   USING/WITH CHECK ( current_setting('app.is_admin',true)='1'
--                      OR vendor_id = current_setting('app.tenant_id',true) ).
-- famit_app = NOSUPERUSER/NOBYPASSRLS so FORCE ROW LEVEL SECURITY binds the owner.
-- Idempotent; re-runnable. Applied LAZILY by db.engine.ensure_schema() only when
-- AIM_PG_DSN is set. Applying it changes NOTHING in the live request path on its own.
-- ============================================================================

-- ====================================================================== --
-- 1) ai_manager_profiles : one row per vendor — AI-Manager enablement + guardrails
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_profiles (
    id                          TEXT        PRIMARY KEY,
    vendor_id                   TEXT        NOT NULL,
    enabled                     BOOLEAN     NOT NULL DEFAULT FALSE,
    ai_manager_phone_number     TEXT        NOT NULL DEFAULT '',
    language_preference         TEXT        NOT NULL DEFAULT 'en',
    default_voice_provider      TEXT        NOT NULL DEFAULT '',
    require_pin_for_level        INTEGER     NOT NULL DEFAULT 3,   -- risk level @ which PIN kicks in
    daily_spend_limit           NUMERIC(14,2) NOT NULL DEFAULT 0,  -- paise/INR; 0 = unset
    monthly_spend_limit         NUMERIC(14,2) NOT NULL DEFAULT 0,
    max_bulk_leads_without_pin  INTEGER     NOT NULL DEFAULT 0,
    allowed_call_start_time     TEXT        NOT NULL DEFAULT '',   -- 'HH:MM' local
    allowed_call_end_time       TEXT        NOT NULL DEFAULT '',
    timezone                    TEXT        NOT NULL DEFAULT 'Asia/Kolkata',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_manager_profiles_vendor_uq UNIQUE (vendor_id)
);
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS enabled                    BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS ai_manager_phone_number    TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS language_preference        TEXT        NOT NULL DEFAULT 'en';
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS default_voice_provider     TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS require_pin_for_level       INTEGER     NOT NULL DEFAULT 3;
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS daily_spend_limit          NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS monthly_spend_limit        NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS max_bulk_leads_without_pin INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS allowed_call_start_time    TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS allowed_call_end_time      TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS timezone                   TEXT        NOT NULL DEFAULT 'Asia/Kolkata';
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS created_at                 TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE ai_manager_profiles ADD COLUMN IF NOT EXISTS updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_profiles_vendor_idx ON ai_manager_profiles (vendor_id);

-- ====================================================================== --
-- 2) ai_manager_authorized_users : who may issue commands; PIN store; lockout
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_authorized_users (
    id                      TEXT        PRIMARY KEY,
    vendor_id               TEXT        NOT NULL,
    user_id                 TEXT        NULL,
    name                    TEXT        NOT NULL DEFAULT '',
    phone_number            TEXT        NOT NULL DEFAULT '',
    normalized_phone_number TEXT        NOT NULL DEFAULT '',   -- E.164, for caller match
    role                    TEXT        NOT NULL DEFAULT 'member', -- owner|admin|member|viewer
    permissions             JSONB       NOT NULL DEFAULT '{}'::jsonb,
    is_active               BOOLEAN     NOT NULL DEFAULT TRUE,
    pin_hash                TEXT        NULL,                  -- never store raw PIN
    pin_set_at              TIMESTAMPTZ NULL,
    failed_pin_attempts     INTEGER     NOT NULL DEFAULT 0,
    locked_until            TIMESTAMPTZ NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS user_id                 TEXT        NULL;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS name                    TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS phone_number            TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS normalized_phone_number TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS role                    TEXT        NOT NULL DEFAULT 'member';
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS permissions             JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS is_active               BOOLEAN     NOT NULL DEFAULT TRUE;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS pin_hash                TEXT        NULL;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS pin_set_at              TIMESTAMPTZ NULL;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS failed_pin_attempts     INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS locked_until            TIMESTAMPTZ NULL;
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS created_at              TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE ai_manager_authorized_users ADD COLUMN IF NOT EXISTS updated_at              TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_users_vendor_idx ON ai_manager_authorized_users (vendor_id, is_active);
CREATE INDEX IF NOT EXISTS ai_manager_users_phone_idx  ON ai_manager_authorized_users (vendor_id, normalized_phone_number);

-- ====================================================================== --
-- 3) ai_manager_sessions : one row per conversation (phone/whatsapp/dashboard)
--    Base §8 cols + P1 ADD: recording_* / outcome / n_actions (8 new cols).
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_sessions (
    id                  TEXT        PRIMARY KEY,
    vendor_id           TEXT        NOT NULL,
    user_id             TEXT        NULL,
    channel             TEXT        NOT NULL DEFAULT 'phone',   -- phone|whatsapp|dashboard
    provider_call_id    TEXT        NULL,
    caller_phone        TEXT        NOT NULL DEFAULT '',
    status              TEXT        NOT NULL DEFAULT 'active',  -- active|completed|failed|blocked
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ NULL,
    transcript_text     TEXT        NOT NULL DEFAULT '',
    stt_provider        TEXT        NOT NULL DEFAULT '',
    tts_provider        TEXT        NOT NULL DEFAULT '',
    llm_provider        TEXT        NOT NULL DEFAULT '',
    metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- P1 call-logging / recording / outcome additions ---------------------
    recording_status    TEXT        NOT NULL DEFAULT 'none',    -- none|recording|stored|failed
    recording_key       TEXT        NOT NULL DEFAULT '',        -- DO Spaces object key
    recording_url       TEXT        NOT NULL DEFAULT '',        -- presigned (read side); '' if boto3 absent
    recording_provider  TEXT        NOT NULL DEFAULT '',        -- 'livekit-egress'
    recording_started_at TIMESTAMPTZ NULL,
    recording_ended_at  TIMESTAMPTZ NULL,
    outcome             TEXT        NOT NULL DEFAULT '',        -- report_sent|action_taken|none|blocked
    n_actions           INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_manager_sessions_status_chk
        CHECK (status IN ('active','completed','failed','blocked'))
);
-- P1 idempotent ALTERs (these are the 8 cols verified live on an existing table)
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS recording_status     TEXT        NOT NULL DEFAULT 'none';
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS recording_key        TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS recording_url        TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS recording_provider   TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS recording_started_at TIMESTAMPTZ NULL;
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS recording_ended_at   TIMESTAMPTZ NULL;
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS outcome              TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS n_actions            INTEGER     NOT NULL DEFAULT 0;
-- base-col ALTERs (converge a pre-§8 table)
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS provider_call_id     TEXT        NULL;
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS transcript_text      TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS metadata             JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_sessions ADD COLUMN IF NOT EXISTS created_at           TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_sessions_vendor_idx ON ai_manager_sessions (vendor_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ai_manager_sessions_status_idx ON ai_manager_sessions (vendor_id, status);
CREATE INDEX IF NOT EXISTS ai_manager_sessions_chan_idx   ON ai_manager_sessions (vendor_id, channel);

-- ====================================================================== --
-- 4) ai_manager_session_turns : P1 NEW — one row per say/hear turn (seq monotonic)
--    state_machine._persist_turn() appends on every _say/_hear; _flatten_transcript on end.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_session_turns (
    id          TEXT        PRIMARY KEY,
    vendor_id   TEXT        NOT NULL,
    session_id  TEXT        NOT NULL,
    seq         INTEGER     NOT NULL DEFAULT 0,     -- monotonic per session
    role        TEXT        NOT NULL DEFAULT 'agent', -- agent|user|system
    text        TEXT        NOT NULL DEFAULT '',
    metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_manager_turns_seq_uq UNIQUE (vendor_id, session_id, seq)
);
ALTER TABLE ai_manager_session_turns ADD COLUMN IF NOT EXISTS seq        INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ai_manager_session_turns ADD COLUMN IF NOT EXISTS role       TEXT        NOT NULL DEFAULT 'agent';
ALTER TABLE ai_manager_session_turns ADD COLUMN IF NOT EXISTS text       TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_session_turns ADD COLUMN IF NOT EXISTS metadata   JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_session_turns ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_turns_session_idx ON ai_manager_session_turns (vendor_id, session_id, seq);

-- ====================================================================== --
-- 5) ai_manager_commands : every parsed instruction + its firewall lifecycle
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_commands (
    id                    TEXT        PRIMARY KEY,
    session_id            TEXT        NULL,
    vendor_id             TEXT        NOT NULL,
    user_id               TEXT        NULL,
    raw_text              TEXT        NOT NULL DEFAULT '',
    normalized_text       TEXT        NOT NULL DEFAULT '',
    detected_intent       TEXT        NOT NULL DEFAULT '',
    action_type           TEXT        NOT NULL DEFAULT '',     -- read|write|money|comms|...
    action_payload        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    risk_level            INTEGER     NOT NULL DEFAULT 0,      -- 0..4
    status                TEXT        NOT NULL DEFAULT 'pending',
    confirmation_required BOOLEAN     NOT NULL DEFAULT FALSE,
    confirmation_status   TEXT        NOT NULL DEFAULT '',     -- ''|pending|confirmed|cancelled
    pin_required          BOOLEAN     NOT NULL DEFAULT FALSE,
    pin_verified          BOOLEAN     NOT NULL DEFAULT FALSE,
    permission_result     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    cost_estimate         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    execution_result      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error_message         TEXT        NOT NULL DEFAULT '',
    idempotency_key       TEXT        NOT NULL DEFAULT '',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_manager_commands_status_chk
        CHECK (status IN ('pending','needs_confirmation','needs_pin','executing',
                          'succeeded','failed','denied','cancelled'))
);
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS session_id            TEXT        NULL;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS user_id               TEXT        NULL;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS raw_text              TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS normalized_text       TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS detected_intent       TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS action_type           TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS action_payload        JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS risk_level            INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS confirmation_required BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS confirmation_status   TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS pin_required          BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS pin_verified          BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS permission_result     JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS cost_estimate         JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS execution_result      JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS error_message         TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS idempotency_key       TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS created_at            TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE ai_manager_commands ADD COLUMN IF NOT EXISTS updated_at            TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_commands_vendor_idx  ON ai_manager_commands (vendor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_manager_commands_session_idx ON ai_manager_commands (vendor_id, session_id);
CREATE INDEX IF NOT EXISTS ai_manager_commands_status_idx  ON ai_manager_commands (vendor_id, status);
-- per-tenant idempotency: a non-empty key is unique within a vendor (partial index)
CREATE UNIQUE INDEX IF NOT EXISTS ai_manager_commands_idem_uq
    ON ai_manager_commands (vendor_id, idempotency_key) WHERE idempotency_key <> '';

-- ====================================================================== --
-- 6) ai_manager_audit_logs (IMMUTABLE) : append-only event trail
--    INSERT + SELECT only. NO UPDATE / DELETE grant; a trigger hard-blocks both.
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_audit_logs (
    id          TEXT        PRIMARY KEY,
    vendor_id   TEXT        NOT NULL,
    user_id     TEXT        NULL,
    session_id  TEXT        NULL,
    command_id  TEXT        NULL,
    event_type  TEXT        NOT NULL DEFAULT '',   -- command_received|risk_blocked|pin_failed|executed|...
    severity    TEXT        NOT NULL DEFAULT 'info', -- debug|info|warn|error|critical
    message     TEXT        NOT NULL DEFAULT '',
    metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS user_id    TEXT        NULL;
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS session_id TEXT        NULL;
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS command_id TEXT        NULL;
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS event_type TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS severity   TEXT        NOT NULL DEFAULT 'info';
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS message    TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS metadata   JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_audit_vendor_idx  ON ai_manager_audit_logs (vendor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_manager_audit_command_idx ON ai_manager_audit_logs (vendor_id, command_id);
CREATE INDEX IF NOT EXISTS ai_manager_audit_session_idx ON ai_manager_audit_logs (vendor_id, session_id);

-- immutability trigger (defence in depth even if a grant slips): block UPDATE/DELETE
CREATE OR REPLACE FUNCTION ai_manager_audit_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ai_manager_audit_logs is append-only (% blocked)', TG_OP;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ai_manager_audit_no_update ON ai_manager_audit_logs;
CREATE TRIGGER ai_manager_audit_no_update
    BEFORE UPDATE OR DELETE ON ai_manager_audit_logs
    FOR EACH ROW EXECUTE FUNCTION ai_manager_audit_block_mutation();

-- ====================================================================== --
-- 7) ai_manager_action_runs : async/durable execution records (queue → terminal)
-- ====================================================================== --
CREATE TABLE IF NOT EXISTS ai_manager_action_runs (
    id            TEXT        PRIMARY KEY,
    command_id    TEXT        NOT NULL,
    vendor_id     TEXT        NOT NULL,
    action_type   TEXT        NOT NULL DEFAULT '',
    target_module TEXT        NOT NULL DEFAULT '',   -- ads|leads|comms|wallet|...
    status        TEXT        NOT NULL DEFAULT 'queued',
    job_id        TEXT        NULL,                  -- Hatchet/queue id
    input         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    output        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    started_at    TIMESTAMPTZ NULL,
    completed_at  TIMESTAMPTZ NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_manager_action_runs_status_chk
        CHECK (status IN ('queued','running','succeeded','failed','retried','cancelled'))
);
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS action_type   TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS target_module TEXT        NOT NULL DEFAULT '';
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS job_id        TEXT        NULL;
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS input         JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS output        JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS error         JSONB       NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS started_at    TIMESTAMPTZ NULL;
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS completed_at  TIMESTAMPTZ NULL;
ALTER TABLE ai_manager_action_runs ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ai_manager_runs_command_idx ON ai_manager_action_runs (vendor_id, command_id);
CREATE INDEX IF NOT EXISTS ai_manager_runs_status_idx  ON ai_manager_action_runs (vendor_id, status);

-- ============================================================================
-- FORCE ROW LEVEL SECURITY (admin-GUC) on every ai_manager_* table.
-- App connects as famit_app (NOSUPERUSER, NOBYPASSRLS); db.engine.session sets
-- SET LOCAL app.tenant_id / app.is_admin in-txn. Drop-then-create = idempotent.
-- ============================================================================
DO $rls$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'ai_manager_profiles','ai_manager_authorized_users','ai_manager_sessions',
    'ai_manager_session_turns','ai_manager_commands','ai_manager_audit_logs',
    'ai_manager_action_runs'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS %1$s_isolation ON %1$I;', t);
    EXECUTE format($f$
      CREATE POLICY %1$s_isolation ON %1$I
      USING (
        current_setting('app.is_admin', true) = '1'
        OR vendor_id = current_setting('app.tenant_id', true)
      )
      WITH CHECK (
        current_setting('app.is_admin', true) = '1'
        OR vendor_id = current_setting('app.tenant_id', true)
      );
    $f$, t);
  END LOOP;
END $rls$;

-- ============ grants (famit_app owns these tables) ============
-- 6 mutable tables: SELECT/INSERT/UPDATE (no DELETE anywhere — runs/commands are append+patch).
GRANT SELECT, INSERT, UPDATE ON
    ai_manager_profiles, ai_manager_authorized_users, ai_manager_sessions,
    ai_manager_session_turns, ai_manager_commands, ai_manager_action_runs
    TO famit_app;
-- audit_logs: INSERT + SELECT ONLY. No UPDATE, no DELETE.
GRANT SELECT, INSERT ON ai_manager_audit_logs TO famit_app;
REVOKE UPDATE, DELETE ON ai_manager_audit_logs FROM famit_app;
