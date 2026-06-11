/**
 * Billing STUB (BUILD-SPEC §7.5, D6 — money structurally impossible in Phase 0).
 *
 * Phase 0 only records credit.consumed meter rows (the sink the metering helper writes to).
 * NO wallets, invoices, or money movement — those land in Phase 3 (mirroring the live
 * wallet.py ACID ledger). This exists so the consumption-meter contract is exercisable and
 * the per-tenant cost feed (P10) has somewhere to go.
 */
import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { AuthContext } from '@growth-os/auth';
import { DbService } from '../../db/db.service.js';

export class BillingError extends Error {
  constructor(message: string, readonly code: 'db_unavailable') {
    super(message);
    this.name = 'BillingError';
  }
}

@Injectable()
export class BillingService {
  constructor(private readonly db: DbService) {}

  /** Record a credit.consumed meter event (the only Phase-0 billing write). */
  async recordConsumption(
    auth: AuthContext,
    input: { meter: string; amount: number; unit: string; reference?: string },
  ): Promise<{ id: string }> {
    if (!this.db.isEnabled()) throw new BillingError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, async (client) => {
      const id = randomUUID();
      await client.query(
        `INSERT INTO core.credit_consumption (id, tenant_id, workspace_id, meter, amount, unit, reference)
         VALUES ($1,$2,$3,$4,$5,$6,$7)`,
        [id, auth.tenant_id, auth.workspace_id, input.meter, input.amount, input.unit, input.reference ?? null],
      );
      return { id };
    });
  }

  /** Sum consumption by meter (the per-tenant cost feed). */
  async summary(auth: AuthContext): Promise<Record<string, unknown>[]> {
    if (!this.db.isEnabled()) throw new BillingError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, async (client) => {
      const res = await client.query(
        'SELECT meter, unit, SUM(amount) AS total FROM core.credit_consumption WHERE tenant_id = $1 GROUP BY meter, unit',
        [auth.tenant_id],
      );
      return res.rows;
    });
  }
}
