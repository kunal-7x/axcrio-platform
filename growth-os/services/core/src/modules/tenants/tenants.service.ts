/**
 * Tenants service (BUILD-SPEC §7.2): orgs/workspaces/members/roles/invites/entitlements.
 * GET /me/permissions resolves role -> permission set (RBAC). All writes emit tenant.*.
 * Tenant scope always from the token (P6); every query runs under RLS (DbService.withTenant).
 */
import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { AuthContext, Role } from '@growth-os/auth';
import { DbService } from '../../db/db.service.js';
import { EventsService } from '../../common/events.service.js';
import {
  autopilotCeilingForRole,
  permissionsForRole,
  roleHasPermission,
} from '../../common/rbac.js';

export class TenantsError extends Error {
  constructor(
    message: string,
    readonly code: 'forbidden' | 'not_found' | 'conflict' | 'db_unavailable' | 'validation_failed',
  ) {
    super(message);
    this.name = 'TenantsError';
  }
}

@Injectable()
export class TenantsService {
  constructor(
    private readonly db: DbService,
    private readonly events: EventsService,
  ) {}

  /** GET /me/permissions — role -> flat permission strings + autopilot ceiling. */
  getMyPermissions(auth: AuthContext, workspaceId?: string): {
    tenant_id: string;
    workspace_id: string;
    role: Role;
    permissions: string[];
    autopilot_ceiling: string;
  } {
    return {
      tenant_id: auth.tenant_id,
      workspace_id: workspaceId ?? auth.workspace_id,
      role: auth.role,
      permissions: permissionsForRole(auth.role),
      autopilot_ceiling: autopilotCeilingForRole(auth.role),
    };
  }

  async listWorkspaces(auth: AuthContext, limit: number): Promise<Record<string, unknown>[]> {
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        'SELECT workspace_id, tenant_id, name, industry_pack_id, locale, data_residency, created_at FROM core.workspaces WHERE tenant_id = $1 ORDER BY created_at ASC LIMIT $2',
        [auth.tenant_id, limit],
      );
      return res.rows;
    });
  }

  async createWorkspace(
    auth: AuthContext,
    input: { name: string; industry_pack_id?: string; locale?: string },
  ): Promise<Record<string, unknown>> {
    this.requirePermission(auth, 'workspace:create');
    return this.scoped(auth, async (client) => {
      const id = randomUUID();
      const res = await client.query(
        `INSERT INTO core.workspaces (workspace_id, tenant_id, name, industry_pack_id, locale)
         VALUES ($1,$2,$3,$4,$5)
         RETURNING workspace_id, tenant_id, name, industry_pack_id, locale, data_residency, created_at`,
        [id, auth.tenant_id, input.name, input.industry_pack_id ?? null, input.locale ?? 'en-IN'],
      );
      const ws = res.rows[0]!;
      await this.emitTenantEvent(auth, 'tenant.workspace.created', id, { workspace_id: id, name: input.name });
      return ws;
    });
  }

  async getWorkspace(auth: AuthContext, workspaceId: string): Promise<Record<string, unknown> | null> {
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        'SELECT workspace_id, tenant_id, name, industry_pack_id, locale, data_residency, created_at FROM core.workspaces WHERE tenant_id = $1 AND workspace_id = $2',
        [auth.tenant_id, workspaceId],
      );
      return res.rowCount > 0 ? res.rows[0]! : null;
    });
  }

  async updateWorkspace(
    auth: AuthContext,
    workspaceId: string,
    patch: { name?: string; industry_pack_id?: string; locale?: string },
  ): Promise<Record<string, unknown>> {
    this.requirePermission(auth, 'workspace:update');
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        `UPDATE core.workspaces
            SET name = COALESCE($3, name),
                industry_pack_id = COALESCE($4, industry_pack_id),
                locale = COALESCE($5, locale)
          WHERE tenant_id = $1 AND workspace_id = $2
          RETURNING workspace_id, tenant_id, name, industry_pack_id, locale, data_residency, created_at`,
        [auth.tenant_id, workspaceId, patch.name ?? null, patch.industry_pack_id ?? null, patch.locale ?? null],
      );
      if (res.rowCount === 0) throw new TenantsError('workspace not found', 'not_found');
      await this.emitTenantEvent(auth, 'tenant.workspace.updated', workspaceId, { workspace_id: workspaceId });
      return res.rows[0]!;
    });
  }

  async listMembers(auth: AuthContext, workspaceId: string, limit: number): Promise<Record<string, unknown>[]> {
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        'SELECT member_id, user_id, email, role, status FROM core.members WHERE tenant_id = $1 AND workspace_id = $2 ORDER BY created_at ASC LIMIT $3',
        [auth.tenant_id, workspaceId, limit],
      );
      return res.rows;
    });
  }

  async updateMemberRole(
    auth: AuthContext,
    workspaceId: string,
    memberId: string,
    role: Role,
  ): Promise<Record<string, unknown>> {
    this.requirePermission(auth, 'member:manage');
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        `UPDATE core.members SET role = $4
          WHERE tenant_id = $1 AND workspace_id = $2 AND member_id = $3
          RETURNING member_id, user_id, email, role, status`,
        [auth.tenant_id, workspaceId, memberId, role],
      );
      if (res.rowCount === 0) throw new TenantsError('member not found', 'not_found');
      await this.emitTenantEvent(auth, 'tenant.member.role_changed', workspaceId, { member_id: memberId, role });
      return res.rows[0]!;
    });
  }

  async removeMember(auth: AuthContext, workspaceId: string, memberId: string): Promise<void> {
    this.requirePermission(auth, 'member:manage');
    await this.scoped(auth, async (client) => {
      const res = await client.query(
        'DELETE FROM core.members WHERE tenant_id = $1 AND workspace_id = $2 AND member_id = $3',
        [auth.tenant_id, workspaceId, memberId],
      );
      if (res.rowCount === 0) throw new TenantsError('member not found', 'not_found');
      return null;
    });
    await this.emitTenantEvent(auth, 'tenant.member.removed', workspaceId, { member_id: memberId });
  }

  async createInvite(
    auth: AuthContext,
    workspaceId: string,
    input: { email: string; role: Role },
  ): Promise<Record<string, unknown>> {
    this.requirePermission(auth, 'invite:create');
    return this.scoped(auth, async (client) => {
      const id = randomUUID();
      const token = randomUUID().replace(/-/g, '');
      const expires = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();
      const res = await client.query(
        `INSERT INTO core.invites (invite_id, tenant_id, workspace_id, email, role, token, expires_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7)
         RETURNING invite_id, email, role, status, expires_at, created_at`,
        [id, auth.tenant_id, workspaceId, input.email, input.role, token, expires],
      );
      await this.emitTenantEvent(auth, 'tenant.invite.created', workspaceId, { invite_id: id, email: input.email });
      return res.rows[0]!;
    });
  }

  async getEntitlements(auth: AuthContext): Promise<Record<string, unknown>> {
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        `SELECT tenant_id, plan, autopilot_ceiling, max_workspaces, max_members,
                monthly_managed_spend_cap_minor, features
           FROM core.entitlements WHERE tenant_id = $1`,
        [auth.tenant_id],
      );
      if (res.rowCount === 0) {
        // Sensible default envelope (a tenant row should be seeded; never 500 here).
        return {
          tenant_id: auth.tenant_id,
          plan: 'trial',
          autopilot_ceiling: 'L2',
          limits: { max_workspaces: 3, max_members: 10, monthly_managed_spend_cap_minor: null },
          features: {},
        };
      }
      const e = res.rows[0]! as Record<string, unknown>;
      return {
        tenant_id: e.tenant_id,
        plan: e.plan,
        autopilot_ceiling: e.autopilot_ceiling,
        limits: {
          max_workspaces: e.max_workspaces,
          max_members: e.max_members,
          monthly_managed_spend_cap_minor: e.monthly_managed_spend_cap_minor,
        },
        features: e.features ?? {},
      };
    });
  }

  // --- helpers ---

  private requirePermission(auth: AuthContext, perm: Parameters<typeof roleHasPermission>[1]): void {
    if (!roleHasPermission(auth.role, perm)) {
      throw new TenantsError(`missing ${perm} permission`, 'forbidden');
    }
  }

  private async scoped<T>(auth: AuthContext, fn: Parameters<DbService['withTenant']>[1]): Promise<T> {
    if (!this.db.isEnabled()) throw new TenantsError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, fn) as Promise<T>;
  }

  private async emitTenantEvent(
    auth: AuthContext,
    type: string,
    correlation: string,
    payload: Record<string, unknown>,
  ): Promise<void> {
    // tenant.* events use a non-frozen type (no payload schema yet); the envelope still validates.
    await this.events.emit({
      type,
      tenant_id: auth.tenant_id,
      workspace_id: auth.workspace_id,
      correlation_id: correlation,
      idempotency_key: `${type}:${correlation}:${Date.now()}`,
      actor: { kind: 'user', id: auth.sub },
      payload,
    });
  }
}
