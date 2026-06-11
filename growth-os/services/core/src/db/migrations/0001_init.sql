-- GROWTH OS core — Phase 0 initial schema.
-- BUILD-SPEC §5.1 (RLS ON day one), §7.2/7.4/7.6/7.7, P6 (tenant_id on every row).
--
-- TENANT ISOLATION (non-negotiable, mirrors the live platform):
--   * tenant_id on EVERY business row.
--   * Row-Level Security ENABLED + FORCED on every table (FORCE so even the table owner
--     is constrained — no accidental cross-tenant leak via the app's own role).
--   * Policies key off the GUC `app.current_tenant` set per-request by the app
--     (set_config('app.current_tenant', <token tenant>, true) inside the request txn).
--   * Tenant comes from the TOKEN, never a request body. The DB is the last line of defense.
--
-- All money is INTEGER paise INR (mirrors the live wallet). No FLOAT for money, ever.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- A dedicated schema keeps the core app's tables together (schema-per-service, §4).
CREATE SCHEMA IF NOT EXISTS core;
SET search_path TO core, public;

-- ---------------------------------------------------------------------------
-- Helper: the current request's tenant (from the GUC the app sets each request).
-- STABLE so the planner can use it in RLS policies efficiently. Returns NULL if unset,
-- and a NULL tenant matches NO rows (fail-closed) because policies compare equality.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION core.current_tenant() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting('app.current_tenant', true), '')::uuid $$;

-- ===========================================================================
-- TENANTS plane (§7.2): orgs -> workspaces -> members -> invites; entitlements.
-- ===========================================================================

CREATE TABLE core.tenants (
  tenant_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  plan          text NOT NULL DEFAULT 'trial',
  data_residency text NOT NULL DEFAULT 'ap-south-1',
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.workspaces (
  workspace_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  name             text NOT NULL,
  industry_pack_id text,
  locale           text NOT NULL DEFAULT 'en-IN',
  data_residency   text NOT NULL DEFAULT 'ap-south-1',
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX workspaces_tenant_idx ON core.workspaces (tenant_id);

CREATE TABLE core.users (
  user_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  email      text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);
CREATE INDEX users_tenant_idx ON core.users (tenant_id);

CREATE TABLE core.members (
  member_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL REFERENCES core.workspaces(workspace_id) ON DELETE CASCADE,
  user_id      uuid NOT NULL REFERENCES core.users(user_id) ON DELETE CASCADE,
  email        text NOT NULL,
  role         text NOT NULL CHECK (role IN ('Owner','Admin','Marketer','Analyst','Approver')),
  status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active','invited','suspended')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, user_id)
);
CREATE INDEX members_tenant_idx ON core.members (tenant_id);
CREATE INDEX members_workspace_idx ON core.members (workspace_id);

CREATE TABLE core.invites (
  invite_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL REFERENCES core.workspaces(workspace_id) ON DELETE CASCADE,
  email        text NOT NULL,
  role         text NOT NULL CHECK (role IN ('Owner','Admin','Marketer','Analyst','Approver')),
  token        text NOT NULL UNIQUE,
  status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','revoked','expired')),
  expires_at   timestamptz NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invites_tenant_idx ON core.invites (tenant_id);

CREATE TABLE core.entitlements (
  tenant_id                       uuid PRIMARY KEY REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  plan                            text NOT NULL DEFAULT 'trial',
  autopilot_ceiling               text NOT NULL DEFAULT 'L2' CHECK (autopilot_ceiling IN ('L0','L1','L2','L3','L4')),
  max_workspaces                  integer NOT NULL DEFAULT 3,
  max_members                     integer NOT NULL DEFAULT 10,
  monthly_managed_spend_cap_minor bigint,          -- INR paise; NULL = unlimited within plan
  features                        jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at                      timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- FLAGS / POLICY-CONFIG plane (§7.7): versioned per-tenant config + feature flags.
-- ===========================================================================

CREATE TABLE core.policy_config (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id uuid REFERENCES core.workspaces(workspace_id) ON DELETE CASCADE,
  version      integer NOT NULL,
  config       jsonb NOT NULL,         -- autopilot/thresholds/budget/kill_rules/locale/...
  actor_kind   text NOT NULL CHECK (actor_kind IN ('user','agent','system')),
  actor_id     text NOT NULL,
  diff         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);
-- One version per (tenant, workspace) — workspace_id NULL = tenant-level config. A bare inline
-- UNIQUE(...) cannot hold a COALESCE expression (Postgres allows only column names there), so the
-- nullable-workspace uniqueness is expressed as an expression UNIQUE INDEX (sentinel for NULL).
CREATE UNIQUE INDEX policy_config_version_uq ON core.policy_config
  (tenant_id, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid), version);
CREATE INDEX policy_config_tenant_idx ON core.policy_config (tenant_id, workspace_id, version DESC);

CREATE TABLE core.feature_flags (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id uuid REFERENCES core.workspaces(workspace_id) ON DELETE CASCADE,
  key          text NOT NULL,
  value        jsonb NOT NULL,
  updated_at   timestamptz NOT NULL DEFAULT now()
);
-- Same nullable-workspace uniqueness as policy_config: expression UNIQUE INDEX, not inline UNIQUE.
CREATE UNIQUE INDEX feature_flags_key_uq ON core.feature_flags
  (tenant_id, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid), key);
CREATE INDEX feature_flags_tenant_idx ON core.feature_flags (tenant_id, workspace_id);

-- ===========================================================================
-- ★ LEDGER plane (§7.4, §5.5, P4/P5): append-only, hash-chained Action Ledger.
--   Each entry stores the full ActionPlan (the frozen artifact) as `plan` jsonb,
--   plus the chain linkage columns prev_hash/hash/sequence. The chain is PER TENANT.
--   Append-only is enforced by an UPDATE/DELETE-blocking trigger (immutability).
-- ===========================================================================

CREATE TABLE core.ledger_actions (
  action_plan_id uuid PRIMARY KEY,
  tenant_id      uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id   uuid,
  correlation_id uuid,                 -- journey id (GET /actions?journey=)
  causation_id   text,
  action_type    text NOT NULL,
  target_ref     text,
  status         text NOT NULL CHECK (status IN
                   ('proposed','signed','executing','executed','failed','rolled_back','rejected','expired')),
  plan           jsonb NOT NULL,       -- the full action_plan.schema.json artifact
  -- hash-chain (§7.4): hash = sha256(prev_hash || canonical_plan_bytes). Per-tenant chain.
  sequence       bigint NOT NULL,
  prev_hash      text NOT NULL,        -- 64 hex zeros for the genesis entry
  hash           text NOT NULL,
  idempotency_key text NOT NULL,       -- exactly-once on (tenant_id, idempotency_key)
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, sequence),
  UNIQUE (tenant_id, hash),
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX ledger_actions_tenant_seq_idx ON core.ledger_actions (tenant_id, sequence);
CREATE INDEX ledger_actions_journey_idx   ON core.ledger_actions (tenant_id, correlation_id);
CREATE INDEX ledger_actions_target_idx    ON core.ledger_actions (tenant_id, target_ref);

-- A separate signature row keeps the append-only entry's identity stable while allowing the
-- ONE permitted state-machine transition (proposed -> signed) to be recorded out-of-band.
-- The status flip is the single allowed mutation (see the immutability trigger exception).
CREATE TABLE core.ledger_signatures (
  signature_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  action_plan_id uuid NOT NULL REFERENCES core.ledger_actions(action_plan_id) ON DELETE CASCADE,
  signer         text NOT NULL,
  alg            text NOT NULL,
  signature      text NOT NULL,
  signed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ledger_signatures_action_idx ON core.ledger_signatures (action_plan_id);

-- Immutability: block DELETE always; block UPDATE except the proposed->signed status flip
-- (which also stamps the plan jsonb's status + signatures + approval). This is the §7.4
-- "append-only" invariant with the one legal lifecycle transition Phase 0 reaches.
CREATE OR REPLACE FUNCTION core.ledger_actions_immutable() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'ledger_actions is append-only: DELETE is forbidden';
  END IF;
  -- UPDATE: only the single legal transition proposed -> signed is allowed, and the
  -- hash-chain columns + identity must NOT change (tamper-evidence).
  IF OLD.action_plan_id <> NEW.action_plan_id
     OR OLD.tenant_id    <> NEW.tenant_id
     OR OLD.sequence     <> NEW.sequence
     OR OLD.prev_hash    <> NEW.prev_hash
     OR OLD.hash         <> NEW.hash
     OR OLD.created_at   <> NEW.created_at THEN
    RAISE EXCEPTION 'ledger_actions is append-only: chain/identity columns are immutable';
  END IF;
  IF NOT (OLD.status = 'proposed' AND NEW.status = 'signed') THEN
    RAISE EXCEPTION 'ledger_actions: only the proposed->signed transition is permitted (was % -> %)',
      OLD.status, NEW.status;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER ledger_actions_immutable_trg
  BEFORE UPDATE OR DELETE ON core.ledger_actions
  FOR EACH ROW EXECUTE FUNCTION core.ledger_actions_immutable();

-- ===========================================================================
-- NOTIFY plane (§7.6): channels, templates, notifications, preferences.
--   Phase 0 sink = console; the rows still persist so the in-app feed + audit work.
-- ===========================================================================

CREATE TABLE core.notify_channels (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  channel        text NOT NULL CHECK (channel IN ('in_app','email','whatsapp')),
  enabled        boolean NOT NULL DEFAULT true,
  status         text NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','degraded','unconfigured')),
  config_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, channel)
);

CREATE TABLE core.notify_templates (
  template_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  key          text NOT NULL,
  channel      text NOT NULL CHECK (channel IN ('in_app','email','whatsapp')),
  locale       text NOT NULL DEFAULT 'en-IN',
  category     text NOT NULL DEFAULT 'utility' CHECK (category IN ('utility','marketing','authentication')),
  body         text NOT NULL,
  variables    jsonb NOT NULL DEFAULT '[]'::jsonb,
  wa_status    text CHECK (wa_status IN ('draft','submitted','approved','rejected')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, key, channel, locale)
);
CREATE INDEX notify_templates_tenant_idx ON core.notify_templates (tenant_id);

CREATE TABLE core.notifications (
  notification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  channel         text NOT NULL CHECK (channel IN ('in_app','email','whatsapp')),
  recipient       text NOT NULL,
  template_key    text NOT NULL,
  status          text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','delivered','failed','read')),
  action_ref      text,
  idempotency_key text NOT NULL,
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX notifications_tenant_idx ON core.notifications (tenant_id, created_at DESC);

CREATE TABLE core.notify_preferences (
  tenant_id     uuid PRIMARY KEY REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  quiet_hours   jsonb NOT NULL DEFAULT '{"enabled":false,"timezone":"Asia/Kolkata"}'::jsonb,
  channel_prefs jsonb NOT NULL DEFAULT '{}'::jsonb,
  locale        text NOT NULL DEFAULT 'en-IN',
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- INTEGRATION-HUB (§7.3): connections + the Origin Connector idempotency log.
--   Phase 0 = the contract + a seeded Tenant-Zero connection; no live wiring.
-- ===========================================================================

CREATE TABLE core.connections (
  connection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id  uuid REFERENCES core.workspaces(workspace_id) ON DELETE CASCADE,
  provider      text NOT NULL,        -- 'origin','meta','google','whatsapp',...
  scopes        jsonb NOT NULL DEFAULT '[]'::jsonb,
  vault_ref     text,                 -- envelope-encrypted token ref (stub Phase 0)
  health        text NOT NULL DEFAULT 'unknown' CHECK (health IN ('healthy','degraded','expired','unknown')),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX connections_tenant_idx ON core.connections (tenant_id);

-- Exactly-once log for inbound Origin Connector events (P3). The dedup key is the source
-- system's own id; a reused key with a different body is a 409 at the API edge.
CREATE TABLE core.origin_idempotency (
  tenant_id       uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  body_hash       text NOT NULL,
  event_id        uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, idempotency_key)
);

-- ===========================================================================
-- BILLING stub (§7.5, D6): credit.consumed sink only. NO money movement Phase 0.
-- ===========================================================================

CREATE TABLE core.credit_consumption (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES core.tenants(tenant_id) ON DELETE CASCADE,
  workspace_id  uuid,
  meter         text NOT NULL,        -- 'llm_tokens','images','wa_msgs',...
  amount        bigint NOT NULL,      -- meter-native units (paise for money meters)
  unit          text NOT NULL,
  reference     text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX credit_consumption_tenant_idx ON core.credit_consumption (tenant_id, created_at DESC);

-- ===========================================================================
-- ROW-LEVEL SECURITY — enable + FORCE on every business table, with a tenant policy.
-- The app sets app.current_tenant per request (from the TOKEN). NULL matches nothing.
-- ===========================================================================

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'tenants','workspaces','users','members','invites','entitlements',
    'policy_config','feature_flags',
    'ledger_actions','ledger_signatures',
    'notify_channels','notify_templates','notifications','notify_preferences',
    'connections','origin_idempotency','credit_consumption'
  ] LOOP
    EXECUTE format('ALTER TABLE core.%I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE core.%I FORCE ROW LEVEL SECURITY;', t);
    -- The tenants table keys on tenant_id itself; every other table has a tenant_id column.
    IF t = 'tenants' THEN
      EXECUTE format(
        'CREATE POLICY tenant_isolation ON core.%I USING (tenant_id = core.current_tenant()) WITH CHECK (tenant_id = core.current_tenant());',
        t);
    ELSE
      EXECUTE format(
        'CREATE POLICY tenant_isolation ON core.%I USING (tenant_id = core.current_tenant()) WITH CHECK (tenant_id = core.current_tenant());',
        t);
    END IF;
  END LOOP;
END $$;
