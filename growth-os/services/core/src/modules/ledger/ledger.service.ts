/**
 * Ledger service — append-only, hash-chained Action Ledger (BUILD-SPEC §7.4, P4/P5).
 *
 * proposeAction: validate the plan against action_plan.schema.json, mint id, compute the
 *   per-tenant hash-chain link (prev_hash from the current chain head), persist atomically,
 *   emit action.plan.created. Idempotent on Idempotency-Key.
 * signAction: the ONLY legal mutation (proposed->signed). Verifies expected_hash, enforces
 *   step-up for spend/destructive plans, appends a signature, emits action.plan.signed.
 * verifyChain: recompute the whole tenant chain (tamper-evidence, §5.5).
 *
 * Phase 0 (D6): NO execution path exists — entries reach only proposed/signed.
 * Everything is tenant-scoped via DbService.withTenant (RLS GUC, P6).
 */
import { Injectable } from '@nestjs/common';
import { randomUUID, createHmac } from 'node:crypto';
import type { CoreConfig } from '@growth-os/config';
import type { AuthContext } from '@growth-os/auth';
import { DbService, type TenantClient } from '../../db/db.service.js';
import { EventsService } from '../../common/events.service.js';
import { ContractValidator } from '../../common/contract-validator.js';
import { roleHasPermission } from '../../common/rbac.js';
import {
  GENESIS_HASH,
  canonicalize,
  computeHash,
  verifyChain,
  type ChainLink,
} from './hash-chain.js';

export class LedgerError extends Error {
  constructor(
    message: string,
    readonly code:
      | 'validation_failed'
      | 'conflict'
      | 'forbidden'
      | 'not_found'
      | 'unprocessable'
      | 'db_unavailable',
  ) {
    super(message);
    this.name = 'LedgerError';
  }
}

type PlanRecord = Record<string, unknown>;

interface LedgerRow extends Record<string, unknown> {
  action_plan_id: string;
  tenant_id: string;
  workspace_id: string | null;
  correlation_id: string | null;
  causation_id: string | null;
  action_type: string;
  target_ref: string | null;
  status: string;
  plan: PlanRecord;
  sequence: string; // bigint comes back as string from pg
  prev_hash: string;
  hash: string;
  idempotency_key: string;
  created_at: string;
}

@Injectable()
export class LedgerService {
  constructor(
    private readonly db: DbService,
    private readonly events: EventsService,
    private readonly contracts: ContractValidator,
    private readonly config: CoreConfig,
  ) {}

  /** Propose an action: append a `proposed`, hash-chained entry + Explanation (P5). */
  async propose(auth: AuthContext, idempotencyKey: string, draft: PlanRecord): Promise<PlanRecord> {
    if (!roleHasPermission(auth.role, 'action:propose')) {
      throw new LedgerError('missing action:propose permission', 'forbidden');
    }
    if (!this.db.isEnabled()) throw new LedgerError('database unavailable', 'db_unavailable');

    return this.db.withTenant(auth.tenant_id, async (client) => {
      // Idempotency: a repeated key returns the original entry (P3).
      const existing = await client.query<LedgerRow>(
        'SELECT * FROM core.ledger_actions WHERE tenant_id = $1 AND idempotency_key = $2',
        [auth.tenant_id, idempotencyKey],
      );
      if (existing.rowCount > 0) {
        return this.toArtifact(existing.rows[0]!);
      }

      // Build the server-managed plan: tenant from TOKEN (P6), status=proposed, no sigs/ledger yet.
      const actionPlanId = randomUUID();
      const nowIso = new Date().toISOString();
      const plan: PlanRecord = {
        ...stripServerManaged(draft),
        action_plan_id: actionPlanId,
        version: '1.0.0',
        tenant_id: auth.tenant_id, // overrides any body-supplied tenant (P6)
        status: 'proposed',
        created_at: nowIso,
      };
      if (!plan.actor) plan.actor = { kind: actorKind(auth), id: auth.sub };
      if (auth.workspace_id && !plan.workspace_id) plan.workspace_id = auth.workspace_id;

      // Validate the FULL artifact against the committed schema (P1) before persisting.
      const check = this.contracts.checkActionPlan(plan);
      if (!check.ok) {
        throw new LedgerError(`plan failed action_plan schema: ${check.errors.join('; ')}`, 'validation_failed');
      }

      // Compute the chain link off the current head (per-tenant chain).
      const head = await client.query<{ sequence: string; hash: string }>(
        'SELECT sequence, hash FROM core.ledger_actions WHERE tenant_id = $1 ORDER BY sequence DESC LIMIT 1',
        [auth.tenant_id],
      );
      const prevHash = head.rowCount > 0 ? head.rows[0]!.hash : GENESIS_HASH;
      const sequence = head.rowCount > 0 ? Number(head.rows[0]!.sequence) + 1 : 0;
      const hash = computeHash(prevHash, plan);

      // Attach the ledger linkage to the stored artifact (excluded from the hash by design).
      plan.ledger = { prev_hash: prevHash, hash, sequence };

      await client.query(
        `INSERT INTO core.ledger_actions
           (action_plan_id, tenant_id, workspace_id, correlation_id, causation_id, action_type,
            target_ref, status, plan, sequence, prev_hash, hash, idempotency_key, created_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)`,
        [
          actionPlanId,
          auth.tenant_id,
          plan.workspace_id ?? null,
          plan.correlation_id ?? null,
          plan.causation_id ?? null,
          plan.action_type,
          plan.target_ref ?? null,
          'proposed',
          JSON.stringify(plan),
          sequence,
          prevHash,
          hash,
          idempotencyKey,
          nowIso,
        ],
      );

      await this.events.emit({
        type: 'action.plan.created',
        tenant_id: auth.tenant_id,
        workspace_id: auth.workspace_id,
        correlation_id: (plan.correlation_id as string) ?? actionPlanId,
        idempotency_key: `ledger:created:${actionPlanId}`,
        actor: { kind: actorKind(auth), id: auth.sub },
        payload: { action_plan_id: actionPlanId, action_type: plan.action_type, status: 'proposed', hash },
      });

      return plan;
    });
  }

  /** Sign a proposed action (the gate connectors check, P4). proposed->signed only. */
  async sign(
    auth: AuthContext,
    actionPlanId: string,
    body: { expected_hash: string; step_up_token?: string | null; confirm_money?: boolean; note?: string | null },
  ): Promise<PlanRecord> {
    if (!roleHasPermission(auth.role, 'action:sign')) {
      throw new LedgerError('missing action:sign permission', 'forbidden');
    }
    if (!this.db.isEnabled()) throw new LedgerError('database unavailable', 'db_unavailable');

    return this.db.withTenant(auth.tenant_id, async (client) => {
      const row = await this.loadRow(client, auth.tenant_id, actionPlanId);
      if (!row) throw new LedgerError('action not found', 'not_found');
      if (row.status !== 'proposed') {
        throw new LedgerError(`action is ${row.status}, not signable (append-only)`, 'unprocessable');
      }
      if (row.hash !== body.expected_hash) {
        throw new LedgerError('expected_hash mismatch (entry changed since review)', 'unprocessable');
      }

      const plan = row.plan;
      const spendChanging = isSpendChanging(plan);
      const destructive = isDestructiveAction(String(plan.action_type));

      // Step-up enforcement (mirrors live firewall.py; §17.3). Spend/destructive => token required.
      if ((spendChanging || destructive) && !body.step_up_token) {
        throw new LedgerError('step-up token required for spend/destructive plan', 'forbidden');
      }
      if (spendChanging && body.confirm_money !== true) {
        throw new LedgerError('confirm_money must be true to sign a spend-increasing plan', 'forbidden');
      }
      // Budget Governor stamp must exist on spend-changing plans before signing (P4, §13.1).
      if (spendChanging && !hasGovernorStamp(plan)) {
        throw new LedgerError('spend-changing plan needs a Budget Governor stamp to be signed', 'forbidden');
      }

      // Sign over the canonical bytes (HS256 Phase 0; ed25519 later). Detached signature.
      const signedAt = new Date().toISOString();
      const signatureValue = this.signCanonical(plan);
      const signature = {
        signer: this.config.LEDGER_SIGNER_KEY_ID,
        alg: 'HS256',
        signature: signatureValue,
        signed_at: signedAt,
      };

      const signedPlan: PlanRecord = {
        ...plan,
        status: 'signed',
        signatures: [...((plan.signatures as unknown[]) ?? []), signature],
        approval: {
          ...(plan.approval as Record<string, unknown> | undefined),
          required: false,
          state: 'not_required',
          approver_id: auth.sub,
          decided_at: signedAt,
        },
      };
      if (body.step_up_token) {
        signedPlan.step_up = {
          scope: destructive ? 'destructive' : spendChanging ? 'spend' : 'bulk',
          token_ref: hashToken(body.step_up_token),
        };
      }

      // The single legal mutation: status proposed->signed + stamp the plan jsonb.
      await client.query(
        'UPDATE core.ledger_actions SET status = $1, plan = $2 WHERE tenant_id = $3 AND action_plan_id = $4',
        ['signed', JSON.stringify(signedPlan), auth.tenant_id, actionPlanId],
      );
      await client.query(
        `INSERT INTO core.ledger_signatures (tenant_id, action_plan_id, signer, alg, signature, signed_at)
         VALUES ($1,$2,$3,$4,$5,$6)`,
        [auth.tenant_id, actionPlanId, signature.signer, signature.alg, signature.signature, signedAt],
      );

      await this.events.emit({
        type: 'action.plan.signed',
        tenant_id: auth.tenant_id,
        workspace_id: auth.workspace_id,
        correlation_id: (plan.correlation_id as string) ?? actionPlanId,
        idempotency_key: `ledger:signed:${actionPlanId}`,
        actor: { kind: actorKind(auth), id: auth.sub },
        payload: { action_plan_id: actionPlanId, action_type: plan.action_type, signer: signature.signer },
      });

      return signedPlan;
    });
  }

  async get(auth: AuthContext, actionPlanId: string): Promise<PlanRecord | null> {
    if (!this.db.isEnabled()) throw new LedgerError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, async (client) => {
      const row = await this.loadRow(client, auth.tenant_id, actionPlanId);
      return row ? this.toArtifact(row) : null;
    });
  }

  async list(
    auth: AuthContext,
    filters: { journey?: string; status?: string; target_ref?: string; action_type?: string; limit: number },
  ): Promise<{ items: PlanRecord[]; chain_head_hash: string | null }> {
    if (!this.db.isEnabled()) throw new LedgerError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, async (client) => {
      const where: string[] = ['tenant_id = $1'];
      const params: unknown[] = [auth.tenant_id];
      if (filters.journey) {
        params.push(filters.journey);
        where.push(`correlation_id = $${params.length}`);
      }
      if (filters.status) {
        params.push(filters.status);
        where.push(`status = $${params.length}`);
      }
      if (filters.target_ref) {
        params.push(filters.target_ref);
        where.push(`target_ref = $${params.length}`);
      }
      if (filters.action_type) {
        params.push(filters.action_type);
        where.push(`action_type = $${params.length}`);
      }
      params.push(filters.limit);
      const rows = await client.query<LedgerRow>(
        `SELECT * FROM core.ledger_actions WHERE ${where.join(' AND ')} ORDER BY sequence ASC LIMIT $${params.length}`,
        params,
      );
      const head = await client.query<{ hash: string }>(
        'SELECT hash FROM core.ledger_actions WHERE tenant_id = $1 ORDER BY sequence DESC LIMIT 1',
        [auth.tenant_id],
      );
      return {
        items: rows.rows.map((r) => this.toArtifact(r)),
        chain_head_hash: head.rowCount > 0 ? head.rows[0]!.hash : null,
      };
    });
  }

  /** Recompute the whole tenant chain — tamper-evidence audit (§5.5). */
  async verify(auth: AuthContext): Promise<{
    ok: boolean;
    entries_checked: number;
    chain_head_hash: string | null;
    first_broken_id: string | null;
  }> {
    if (!this.db.isEnabled()) throw new LedgerError('database unavailable', 'db_unavailable');
    return this.db.withTenant(auth.tenant_id, async (client) => {
      const rows = await client.query<LedgerRow>(
        'SELECT * FROM core.ledger_actions WHERE tenant_id = $1 ORDER BY sequence ASC',
        [auth.tenant_id],
      );
      const links: Array<ChainLink & { action_plan_id: string }> = rows.rows.map((r) => ({
        action_plan_id: r.action_plan_id,
        sequence: Number(r.sequence),
        prev_hash: r.prev_hash,
        hash: r.hash,
        // Recompute from the canonical content of the STORED plan (canonicalize excludes
        // ledger/signatures and we hold status at the proposal value for the recompute).
        plan: rehashView(r.plan),
      }));
      return verifyChain(links);
    });
  }

  // --- helpers ---

  private async loadRow(client: TenantClient, tenantId: string, id: string): Promise<LedgerRow | null> {
    const res = await client.query<LedgerRow>(
      'SELECT * FROM core.ledger_actions WHERE tenant_id = $1 AND action_plan_id = $2',
      [tenantId, id],
    );
    return res.rowCount > 0 ? res.rows[0]! : null;
  }

  private toArtifact(row: LedgerRow): PlanRecord {
    // The stored `plan` jsonb already IS the artifact (with ledger linkage). Return as-is.
    return row.plan;
  }

  private signCanonical(plan: PlanRecord): string {
    return createHmac('sha256', this.config.LEDGER_SIGNING_SECRET).update(canonicalize(plan)).digest('hex');
  }
}

/** The view used to RECOMPUTE an entry's hash: canonicalize excludes ledger/signatures, and
 * we pin status to the proposal value so the proposed->signed flip never invalidates the hash. */
function rehashView(plan: PlanRecord): PlanRecord {
  return { ...plan, status: 'proposed' };
}

function stripServerManaged(draft: PlanRecord): PlanRecord {
  const { action_plan_id, status, signatures, ledger, created_at, ...rest } = draft;
  void action_plan_id;
  void status;
  void signatures;
  void ledger;
  void created_at;
  return rest;
}

function actorKind(auth: AuthContext): 'agent' | 'user' | 'system' | 'webhook' {
  // Human-driven core requests are users; service tokens would map to system (Phase 1+).
  return 'user';
  void auth;
}

function isSpendChanging(plan: PlanRecord): boolean {
  const bi = plan.budget_impact as { spend_changing?: boolean } | undefined;
  return bi?.spend_changing === true;
}

function hasGovernorStamp(plan: PlanRecord): boolean {
  const bi = plan.budget_impact as { governor_stamp?: { stamp_id?: string } } | undefined;
  return Boolean(bi?.governor_stamp?.stamp_id);
}

const DESTRUCTIVE = new Set(['pause_campaign', 'pause_ad_set', 'trash_ad', 'quarantine_creative']);
function isDestructiveAction(actionType: string): boolean {
  return DESTRUCTIVE.has(actionType);
}

function hashToken(token: string): string {
  return createHmac('sha256', 'step-up-ref').update(token).digest('hex').slice(0, 32);
}
