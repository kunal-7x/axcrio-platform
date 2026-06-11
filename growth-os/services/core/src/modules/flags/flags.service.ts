/**
 * Flags / policy-config service (BUILD-SPEC §7.7). Per-tenant autopilot/thresholds/budget/
 * kill-rules + boolean feature flags. Every write is VERSIONED and emits config.changed (P2).
 * Drives the Approval Policy (§17) + Budget Governor stamps (§13) downstream. RLS-scoped (P6).
 */
import { Injectable } from '@nestjs/common';
import type { AuthContext } from '@growth-os/auth';
import { DbService } from '../../db/db.service.js';
import { EventsService } from '../../common/events.service.js';
import { roleHasPermission } from '../../common/rbac.js';

export class FlagsError extends Error {
  constructor(
    message: string,
    readonly code: 'forbidden' | 'not_found' | 'conflict' | 'db_unavailable' | 'validation_failed',
  ) {
    super(message);
    this.name = 'FlagsError';
  }
}

const NIL_WS = '00000000-0000-0000-0000-000000000000';

const DEFAULT_CONFIG = {
  autopilot: { research: 'L1', creative: 'L1', launch: 'L0', budget_change: 'L0', optimization: 'L1' },
  thresholds: { auto_test_daily_cap_minor: 50000, require_approval_above_minor: 100000 },
  budget: { workspace_monthly_cap_minor: 0, daily_cap_minor: 0 },
  kill_rules: {
    runaway_multiplier: 3.0,
    zero_q_multiplier: 2.5,
    set_fail_multiplier: 4.0,
    junk_rate_threshold: 0.6,
    fatigue_frequency_7d: 2.5,
  },
  locale: 'en-IN',
  locales_enabled: [] as string[],
};

@Injectable()
export class FlagsService {
  constructor(
    private readonly db: DbService,
    private readonly events: EventsService,
  ) {}

  async getPolicyConfig(auth: AuthContext, workspaceId?: string, version?: number): Promise<Record<string, unknown>> {
    return this.scoped(auth, async (client) => {
      const ws = workspaceId ?? auth.workspace_id;
      const params: unknown[] = [auth.tenant_id, ws];
      let sql =
        'SELECT version, config, created_at FROM core.policy_config WHERE tenant_id = $1 AND COALESCE(workspace_id, $2) = $2';
      if (version) {
        params.push(version);
        sql += ` AND version = $${params.length}`;
      } else {
        sql += ' ORDER BY version DESC LIMIT 1';
      }
      const res = await client.query<{ version: number; config: Record<string, unknown>; created_at: string }>(sql, params);
      if (res.rowCount === 0) {
        return {
          tenant_id: auth.tenant_id,
          workspace_id: ws,
          version: 0,
          updated_at: new Date().toISOString(),
          ...DEFAULT_CONFIG,
        };
      }
      const row = res.rows[0]!;
      return {
        tenant_id: auth.tenant_id,
        workspace_id: ws,
        version: row.version,
        updated_at: row.created_at,
        ...row.config,
      };
    });
  }

  async updatePolicyConfig(
    auth: AuthContext,
    input: Record<string, unknown>,
    workspaceId?: string,
  ): Promise<Record<string, unknown>> {
    this.require(auth, 'policy:update');
    return this.scoped(auth, async (client) => {
      const ws = workspaceId ?? auth.workspace_id;
      const head = await client.query<{ version: number; config: Record<string, unknown> }>(
        'SELECT version, config FROM core.policy_config WHERE tenant_id = $1 AND COALESCE(workspace_id, $2) = $2 ORDER BY version DESC LIMIT 1',
        [auth.tenant_id, ws],
      );
      const prevVersion = head.rowCount > 0 ? head.rows[0]!.version : 0;
      const prevConfig = head.rowCount > 0 ? head.rows[0]!.config : DEFAULT_CONFIG;
      const nextVersion = prevVersion + 1;
      // Full replace of the editable block (the contract semantics).
      const merged = { ...DEFAULT_CONFIG, ...input };
      const diff = computeDiff(prevConfig as Record<string, unknown>, merged);

      await client.query(
        `INSERT INTO core.policy_config (tenant_id, workspace_id, version, config, actor_kind, actor_id, diff)
         VALUES ($1,$2,$3,$4,$5,$6,$7)`,
        [auth.tenant_id, ws === NIL_WS ? null : ws, nextVersion, JSON.stringify(merged), 'user', auth.sub, JSON.stringify(diff)],
      );

      await this.emitConfigChanged(auth, ws, { version: nextVersion, diff });

      return {
        tenant_id: auth.tenant_id,
        workspace_id: ws,
        version: nextVersion,
        updated_at: new Date().toISOString(),
        ...merged,
      };
    });
  }

  async listVersions(auth: AuthContext, workspaceId: string | undefined, limit: number): Promise<Record<string, unknown>[]> {
    return this.scoped(auth, async (client) => {
      const ws = workspaceId ?? auth.workspace_id;
      const res = await client.query<{ version: number; actor_kind: string; actor_id: string; created_at: string; diff: Record<string, unknown> }>(
        'SELECT version, actor_kind, actor_id, created_at, diff FROM core.policy_config WHERE tenant_id = $1 AND COALESCE(workspace_id, $2) = $2 ORDER BY version DESC LIMIT $3',
        [auth.tenant_id, ws, limit],
      );
      return res.rows.map((r) => ({
        version: r.version,
        actor: { kind: r.actor_kind, id: r.actor_id },
        changed_at: r.created_at,
        diff: r.diff,
      }));
    });
  }

  async listFlags(auth: AuthContext, workspaceId?: string): Promise<{ flags: Record<string, unknown> }> {
    return this.scoped(auth, async (client) => {
      const ws = workspaceId ?? auth.workspace_id;
      const res = await client.query<{ key: string; value: unknown }>(
        'SELECT key, value FROM core.feature_flags WHERE tenant_id = $1 AND COALESCE(workspace_id, $2) = $2',
        [auth.tenant_id, ws],
      );
      const flags: Record<string, unknown> = {};
      for (const r of res.rows) flags[r.key] = r.value;
      return { flags };
    });
  }

  async setFlag(
    auth: AuthContext,
    key: string,
    value: boolean | string | number,
    workspaceId?: string,
  ): Promise<{ key: string; value: unknown }> {
    this.require(auth, 'flag:update');
    return this.scoped(auth, async (client) => {
      const ws = workspaceId ?? auth.workspace_id;
      await client.query(
        `INSERT INTO core.feature_flags (tenant_id, workspace_id, key, value)
         VALUES ($1,$2,$3,$4)
         ON CONFLICT (tenant_id, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid), key)
         DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
        [auth.tenant_id, ws === NIL_WS ? null : ws, key, JSON.stringify(value)],
      );
      await this.emitConfigChanged(auth, ws, { flag: key });
      return { key, value };
    });
  }

  // --- helpers ---

  private require(auth: AuthContext, perm: Parameters<typeof roleHasPermission>[1]): void {
    if (!roleHasPermission(auth.role, perm)) throw new FlagsError(`missing ${perm} permission`, 'forbidden');
  }

  private async scoped<T>(auth: AuthContext, fn: Parameters<DbService['withTenant']>[1]): Promise<T> {
    if (!this.db.isEnabled()) throw new FlagsError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, fn) as Promise<T>;
  }

  private async emitConfigChanged(auth: AuthContext, ws: string, payload: Record<string, unknown>): Promise<void> {
    await this.events.emit({
      type: 'config.changed',
      tenant_id: auth.tenant_id,
      workspace_id: ws,
      correlation_id: ws,
      idempotency_key: `config.changed:${ws}:${Date.now()}`,
      actor: { kind: 'user', id: auth.sub },
      payload,
    });
  }
}

function computeDiff(prev: Record<string, unknown>, next: Record<string, unknown>): Record<string, unknown> {
  const diff: Record<string, unknown> = {};
  for (const k of new Set([...Object.keys(prev), ...Object.keys(next)])) {
    if (JSON.stringify(prev[k]) !== JSON.stringify(next[k])) {
      diff[k] = { from: prev[k] ?? null, to: next[k] ?? null };
    }
  }
  return diff;
}
