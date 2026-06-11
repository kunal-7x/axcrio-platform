/**
 * Notify service (BUILD-SPEC §7.6) — Phase-0 CONSOLE driver.
 *
 * channels/templates/send/preferences. Phase 0 sink = console (a NotifyDriver impl); the
 * contract is stable so email/WA drivers slot in later (§16.1 WA via the live adapter).
 * Every send persists a notification row (the in-app feed + audit) and is idempotent on
 * Idempotency-Key (P3). RLS-scoped (P6).
 */
import { Injectable, Logger } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { AuthContext } from '@growth-os/auth';
import { DbService } from '../../db/db.service.js';
import { roleHasPermission } from '../../common/rbac.js';

export class NotifyError extends Error {
  constructor(
    message: string,
    readonly code: 'forbidden' | 'not_found' | 'conflict' | 'db_unavailable' | 'validation_failed' | 'blocked',
  ) {
    super(message);
    this.name = 'NotifyError';
  }
}

/** Pluggable delivery driver. Phase 0 = console; email/WA implement this later. */
export interface NotifyDriver {
  readonly channel: 'in_app' | 'email' | 'whatsapp';
  deliver(msg: { to: string; templateKey: string; body: string; variables: Record<string, string> }): Promise<void>;
}

/** Phase-0 console driver — logs the rendered message; no external calls. */
export class ConsoleNotifyDriver implements NotifyDriver {
  readonly channel = 'in_app' as const;
  private readonly logger = new Logger('NotifyConsole');
  async deliver(msg: { to: string; templateKey: string; body: string; variables: Record<string, string> }): Promise<void> {
    this.logger.log(`[notify -> ${msg.to}] (${msg.templateKey}) ${render(msg.body, msg.variables)}`);
  }
}

@Injectable()
export class NotifyService {
  private readonly console = new ConsoleNotifyDriver();

  constructor(private readonly db: DbService) {}

  async listChannels(auth: AuthContext): Promise<{ channels: Record<string, unknown>[] }> {
    return this.scoped(auth, async (client) => {
      const res = await client.query(
        'SELECT channel, enabled, status, config_summary FROM core.notify_channels WHERE tenant_id = $1',
        [auth.tenant_id],
      );
      // Phase 0: in_app is always ready via the console driver even with no rows.
      const rows = res.rows.length
        ? res.rows
        : [{ channel: 'in_app', enabled: true, status: 'ready', config_summary: {} }];
      return { channels: rows };
    });
  }

  async listTemplates(auth: AuthContext, filters: { channel?: string; locale?: string; limit: number }): Promise<Record<string, unknown>[]> {
    return this.scoped(auth, async (client) => {
      const where: string[] = ['tenant_id = $1'];
      const params: unknown[] = [auth.tenant_id];
      if (filters.channel) {
        params.push(filters.channel);
        where.push(`channel = $${params.length}`);
      }
      if (filters.locale) {
        params.push(filters.locale);
        where.push(`locale = $${params.length}`);
      }
      params.push(filters.limit);
      const res = await client.query(
        `SELECT template_id, key, channel, locale, category, body, variables, wa_status
           FROM core.notify_templates WHERE ${where.join(' AND ')} ORDER BY created_at ASC LIMIT $${params.length}`,
        params,
      );
      return res.rows;
    });
  }

  async createTemplate(
    auth: AuthContext,
    input: { key: string; channel: string; locale?: string; category?: string; body: string; variables?: string[] },
  ): Promise<Record<string, unknown>> {
    return this.scoped(auth, async (client) => {
      const id = randomUUID();
      const res = await client.query(
        `INSERT INTO core.notify_templates (template_id, tenant_id, key, channel, locale, category, body, variables)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
         RETURNING template_id, key, channel, locale, category, body, variables, wa_status`,
        [
          id,
          auth.tenant_id,
          input.key,
          input.channel,
          input.locale ?? 'en-IN',
          input.category ?? 'utility',
          input.body,
          JSON.stringify(input.variables ?? []),
        ],
      );
      return res.rows[0]!;
    });
  }

  /** Send through a channel (console in Phase 0). Idempotent on idempotencyKey (P3). */
  async send(
    auth: AuthContext,
    idempotencyKey: string,
    input: { channel: string; to: string; template_key: string; locale?: string; variables?: Record<string, string>; priority?: string; action_ref?: string | null },
  ): Promise<Record<string, unknown>> {
    if (!roleHasPermission(auth.role, 'notify:send')) throw new NotifyError('missing notify:send permission', 'forbidden');
    return this.scoped(auth, async (client) => {
      const existing = await client.query<{ notification_id: string; channel: string; recipient: string; template_key: string; status: string; action_ref: string | null; created_at: string }>(
        'SELECT notification_id, channel, recipient, template_key, status, action_ref, created_at FROM core.notifications WHERE tenant_id = $1 AND idempotency_key = $2',
        [auth.tenant_id, idempotencyKey],
      );
      if (existing.rowCount > 0) {
        const r = existing.rows[0]!;
        return toNotification(r);
      }

      // Resolve template body (best-effort; Phase 0 falls back to a generic body).
      const tpl = await client.query<{ body: string }>(
        'SELECT body FROM core.notify_templates WHERE tenant_id = $1 AND key = $2 AND channel = $3 ORDER BY (locale = $4) DESC LIMIT 1',
        [auth.tenant_id, input.template_key, input.channel, input.locale ?? 'en-IN'],
      );
      const body = tpl.rowCount > 0 ? tpl.rows[0]!.body : `[${input.template_key}]`;

      const id = randomUUID();
      const res = await client.query<{ notification_id: string; channel: string; recipient: string; template_key: string; status: string; action_ref: string | null; created_at: string }>(
        `INSERT INTO core.notifications (notification_id, tenant_id, channel, recipient, template_key, status, action_ref, idempotency_key, payload)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
         RETURNING notification_id, channel, recipient, template_key, status, action_ref, created_at`,
        [
          id,
          auth.tenant_id,
          input.channel,
          input.to,
          input.template_key,
          'sent',
          input.action_ref ?? null,
          idempotencyKey,
          JSON.stringify({ variables: input.variables ?? {}, priority: input.priority ?? 'normal' }),
        ],
      );

      // Phase 0: deliver via the console driver (the only wired channel).
      await this.console.deliver({
        to: input.to,
        templateKey: input.template_key,
        body,
        variables: input.variables ?? {},
      });

      return toNotification(res.rows[0]!);
    });
  }

  async listNotifications(auth: AuthContext, status: string | undefined, limit: number): Promise<Record<string, unknown>[]> {
    return this.scoped(auth, async (client) => {
      const where: string[] = ['tenant_id = $1'];
      const params: unknown[] = [auth.tenant_id];
      if (status) {
        params.push(status);
        where.push(`status = $${params.length}`);
      }
      params.push(limit);
      const res = await client.query<{ notification_id: string; channel: string; recipient: string; template_key: string; status: string; action_ref: string | null; created_at: string }>(
        `SELECT notification_id, channel, recipient, template_key, status, action_ref, created_at
           FROM core.notifications WHERE ${where.join(' AND ')} ORDER BY created_at DESC LIMIT $${params.length}`,
        params,
      );
      return res.rows.map(toNotification);
    });
  }

  async getPreferences(auth: AuthContext): Promise<Record<string, unknown>> {
    return this.scoped(auth, async (client) => {
      const res = await client.query<{ quiet_hours: Record<string, unknown>; channel_prefs: Record<string, unknown>; locale: string }>(
        'SELECT quiet_hours, channel_prefs, locale FROM core.notify_preferences WHERE tenant_id = $1',
        [auth.tenant_id],
      );
      if (res.rowCount === 0) {
        return { quiet_hours: { enabled: false, timezone: 'Asia/Kolkata' }, channel_prefs: {}, locale: 'en-IN' };
      }
      return res.rows[0]!;
    });
  }

  async updatePreferences(auth: AuthContext, prefs: { quiet_hours: Record<string, unknown>; channel_prefs: Record<string, unknown>; locale?: string }): Promise<Record<string, unknown>> {
    return this.scoped(auth, async (client) => {
      await client.query(
        `INSERT INTO core.notify_preferences (tenant_id, quiet_hours, channel_prefs, locale)
         VALUES ($1,$2,$3,$4)
         ON CONFLICT (tenant_id) DO UPDATE SET quiet_hours = EXCLUDED.quiet_hours, channel_prefs = EXCLUDED.channel_prefs, locale = EXCLUDED.locale, updated_at = now()`,
        [auth.tenant_id, JSON.stringify(prefs.quiet_hours), JSON.stringify(prefs.channel_prefs), prefs.locale ?? 'en-IN'],
      );
      return { quiet_hours: prefs.quiet_hours, channel_prefs: prefs.channel_prefs, locale: prefs.locale ?? 'en-IN' };
    });
  }

  private async scoped<T>(auth: AuthContext, fn: Parameters<DbService['withTenant']>[1]): Promise<T> {
    if (!this.db.isEnabled()) throw new NotifyError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, fn) as Promise<T>;
  }
}

function toNotification(r: { notification_id: string; channel: string; recipient: string; template_key: string; status: string; action_ref: string | null; created_at: string }): Record<string, unknown> {
  return {
    notification_id: r.notification_id,
    channel: r.channel,
    to: r.recipient,
    template_key: r.template_key,
    status: r.status,
    action_ref: r.action_ref,
    created_at: r.created_at,
  };
}

function render(body: string, vars: Record<string, string>): string {
  return body.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => vars[k] ?? `{{${k}}}`);
}
