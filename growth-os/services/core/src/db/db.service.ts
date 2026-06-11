/**
 * Database access with per-request tenant isolation (BUILD-SPEC §5.1, P6).
 *
 * EVERY tenant-scoped query runs inside withTenant(), which opens a transaction and sets
 * the GUC `app.current_tenant` to the TOKEN's tenant_id (set_config(..., true) = txn-local).
 * Postgres RLS policies (migration 0001) compare each row's tenant_id to this GUC, so the
 * database itself enforces isolation — even a buggy query can't read another tenant's rows.
 *
 * Tenant ALWAYS comes from the AuthContext (the verified token), never a request body.
 *
 * Phase-0 laptop note (D8): when DATABASE_URL is absent the app boots in a degraded
 * "no-db" mode (dbEnabled=false). The HTTP/contract surface still typechecks and runs;
 * DB-backed endpoints return 503-style errors. Real Postgres is box/CI-required.
 */
import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { Pool, type PoolClient } from 'pg';
import type { CoreConfig } from '@growth-os/config';

export class DbUnavailableError extends Error {
  readonly code = 'db_unavailable';
  constructor() {
    super('database is not configured (DATABASE_URL absent or DB disabled)');
    this.name = 'DbUnavailableError';
  }
}

/** A scoped client whose RLS tenant GUC is already pinned for the active transaction. */
export interface TenantClient {
  query<R extends Record<string, unknown> = Record<string, unknown>>(
    text: string,
    params?: readonly unknown[],
  ): Promise<{ rows: R[]; rowCount: number }>;
}

@Injectable()
export class DbService implements OnModuleDestroy {
  private pool: Pool | null = null;
  readonly enabled: boolean;

  constructor(private readonly config: CoreConfig) {
    this.enabled = config.dbEnabled;
    if (this.enabled && config.DATABASE_URL) {
      this.pool = new Pool({
        connectionString: config.DATABASE_URL,
        // search_path so unqualified table names resolve to the core schema.
        options: '-c search_path=core,public',
        max: 10,
      });
    }
  }

  /** True when a real Postgres pool is available. */
  isEnabled(): boolean {
    return this.enabled && this.pool !== null;
  }

  /**
   * Run `fn` inside a transaction with RLS pinned to `tenantId` (txn-local GUC, P6).
   * Commits on success, rolls back on throw. The tenant id MUST be the token's tenant.
   */
  async withTenant<T>(tenantId: string, fn: (client: TenantClient) => Promise<T>): Promise<T> {
    if (!this.pool) throw new DbUnavailableError();
    const client: PoolClient = await this.pool.connect();
    try {
      await client.query('BEGIN');
      // txn-local (third arg true) => never leaks to the next user of this pooled connection.
      await client.query('SELECT set_config($1, $2, true)', ['app.current_tenant', tenantId]);
      const scoped: TenantClient = {
        query: async (text, params) => {
          const res = await client.query(text, params as unknown[] | undefined);
          return { rows: res.rows as never[], rowCount: res.rowCount ?? 0 };
        },
      };
      const out = await fn(scoped);
      await client.query('COMMIT');
      return out;
    } catch (err) {
      try {
        await client.query('ROLLBACK');
      } catch {
        /* ignore rollback errors */
      }
      throw err;
    } finally {
      client.release();
    }
  }

  /**
   * Run a query OUTSIDE any tenant scope (admin/migration/health). RLS still applies to
   * tenant tables (no GUC => current_tenant() is NULL => no rows), so this is only for
   * non-tenant operations like `SELECT 1` readiness and migrations (which run before RLS bites
   * via a privileged role). Use sparingly.
   */
  async unscoped<R extends Record<string, unknown> = Record<string, unknown>>(
    text: string,
    params?: readonly unknown[],
  ): Promise<{ rows: R[]; rowCount: number }> {
    if (!this.pool) throw new DbUnavailableError();
    const res = await this.pool.query(text, params as unknown[] | undefined);
    return { rows: res.rows as R[], rowCount: res.rowCount ?? 0 };
  }

  /** Readiness probe helper: is the DB reachable? */
  async ping(): Promise<boolean> {
    if (!this.pool) return false;
    try {
      await this.pool.query('SELECT 1');
      return true;
    } catch {
      return false;
    }
  }

  async onModuleDestroy(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
    }
  }
}
