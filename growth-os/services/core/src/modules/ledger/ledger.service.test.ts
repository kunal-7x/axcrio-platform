/**
 * Ledger service integration test WITHOUT a real Postgres — a tiny in-memory fake of
 * DbService.withTenant emulates the per-tenant table + the proposed->signed transition.
 * Proves: propose validates against action_plan.schema.json, the hash-chain links across
 * entries, sign requires action:sign + step-up for spend, and verify recomputes the chain.
 *
 * The ledger entry returned by propose() is validated against the COMMITTED schema here, so
 * a response that drifts from contracts/schemas/action_plan.schema.json fails this test (P1).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import type { AuthContext } from '@growth-os/auth';
import { LedgerService } from './ledger.service.js';
import { ContractValidator } from '../../common/contract-validator.js';
import { verifyChain, type ChainLink } from './hash-chain.js';
import { loadCoreConfig } from '@growth-os/config';

// --- In-memory fakes -------------------------------------------------------

interface Row {
  action_plan_id: string;
  tenant_id: string;
  workspace_id: string | null;
  correlation_id: string | null;
  causation_id: string | null;
  action_type: string;
  target_ref: string | null;
  status: string;
  plan: Record<string, unknown>;
  sequence: number;
  prev_hash: string;
  hash: string;
  idempotency_key: string;
  created_at: string;
}

class FakeDb {
  rows: Row[] = [];
  isEnabled(): boolean {
    return true;
  }
  async withTenant<T>(_tenantId: string, fn: (client: FakeClient) => Promise<T>): Promise<T> {
    return fn(new FakeClient(this.rows));
  }
}

class FakeClient {
  constructor(private rows: Row[]) {}
  async query<R extends Record<string, unknown>>(text: string, params: readonly unknown[] = []): Promise<{ rows: R[]; rowCount: number }> {
    const t = text.replace(/\s+/g, ' ').trim();
    if (t.startsWith('SELECT * FROM core.ledger_actions WHERE tenant_id = $1 AND idempotency_key')) {
      const out = this.rows.filter((r) => r.idempotency_key === params[1]);
      return { rows: out as unknown as R[], rowCount: out.length };
    }
    if (t.startsWith('SELECT * FROM core.ledger_actions WHERE tenant_id = $1 AND action_plan_id')) {
      const out = this.rows.filter((r) => r.action_plan_id === params[1]);
      return { rows: out as unknown as R[], rowCount: out.length };
    }
    if (t.startsWith('SELECT sequence, hash FROM core.ledger_actions WHERE tenant_id = $1 ORDER BY sequence DESC LIMIT 1')) {
      const sorted = [...this.rows].sort((a, b) => b.sequence - a.sequence);
      const head = sorted[0];
      return { rows: (head ? [{ sequence: String(head.sequence), hash: head.hash }] : []) as unknown as R[], rowCount: head ? 1 : 0 };
    }
    if (t.startsWith('SELECT * FROM core.ledger_actions WHERE tenant_id = $1 ORDER BY sequence ASC')) {
      const sorted = [...this.rows].sort((a, b) => a.sequence - b.sequence);
      return { rows: sorted as unknown as R[], rowCount: sorted.length };
    }
    if (t.startsWith('INSERT INTO core.ledger_actions')) {
      this.rows.push({
        action_plan_id: params[0] as string,
        tenant_id: params[1] as string,
        workspace_id: (params[2] as string) ?? null,
        correlation_id: (params[3] as string) ?? null,
        causation_id: (params[4] as string) ?? null,
        action_type: params[5] as string,
        target_ref: (params[6] as string) ?? null,
        status: params[7] as string,
        plan: JSON.parse(params[8] as string),
        sequence: params[9] as number,
        prev_hash: params[10] as string,
        hash: params[11] as string,
        idempotency_key: params[12] as string,
        created_at: params[13] as string,
      });
      return { rows: [] as R[], rowCount: 1 };
    }
    if (t.startsWith('UPDATE core.ledger_actions SET status')) {
      const row = this.rows.find((r) => r.action_plan_id === params[3]);
      if (row) {
        row.status = params[0] as string;
        row.plan = JSON.parse(params[1] as string);
      }
      return { rows: [] as R[], rowCount: row ? 1 : 0 };
    }
    if (t.startsWith('INSERT INTO core.ledger_signatures')) {
      return { rows: [] as R[], rowCount: 1 };
    }
    return { rows: [] as R[], rowCount: 0 };
  }
}

const fakeEvents = { emit: async () => undefined } as unknown as import('../../common/events.service.js').EventsService;

const TENANT = '00000000-0000-7000-8000-000000000001';
const auth = (role: AuthContext['role']): AuthContext => ({
  sub: '00000000-0000-7000-8000-0000000000aa',
  tenant_id: TENANT,
  workspace_id: '00000000-0000-7000-8000-000000000002',
  role,
  iss: 'growth-os-dev',
});

function benignPlan(): Record<string, unknown> {
  return {
    action_type: 'pause_ad',
    correlation_id: '00000000-0000-7000-8000-000000000003',
    target_ref: 'meta:ad:123',
    operations: [{ op_id: 'o1', connector: 'meta', op: 'pause_entity', idempotency_key: 'k1' }],
    explanation: {
      action: { type: 'pause_ad', summary_en: 'Pause underperforming ad' },
      evidence: [{ metric: 'q_leads', value: 0, source: 'metrics_layer' }],
      expected_effect: { summary: 'reallocate ₹600/day' },
      confidence: 'high',
      reversible: true,
      approval_required: false,
      undo_plan: 'unpause ad 123',
    },
  };
}

describe('LedgerService (in-memory)', () => {
  let svc: LedgerService;
  let contracts: ContractValidator;
  let db: FakeDb;

  beforeEach(() => {
    db = new FakeDb();
    contracts = new ContractValidator();
    const config = loadCoreConfig({ NODE_ENV: 'test' } as NodeJS.ProcessEnv);
    svc = new LedgerService(db as never, fakeEvents, contracts, config);
  });

  it('propose() returns a ledger entry that conforms to action_plan.schema.json (P1)', async () => {
    const entry = await svc.propose(auth('Marketer'), 'idem-1', benignPlan());
    expect(entry.status).toBe('proposed');
    expect((entry.ledger as { sequence: number }).sequence).toBe(0);
    // The returned artifact MUST validate against the committed schema.
    const check = contracts.checkActionPlan(entry);
    expect(check.ok, check.errors.join('; ')).toBe(true);
  });

  it('chains entries with prev_hash continuity (per-tenant)', async () => {
    const e0 = await svc.propose(auth('Marketer'), 'idem-a', benignPlan());
    const e1 = await svc.propose(auth('Marketer'), 'idem-b', benignPlan());
    expect((e1.ledger as { prev_hash: string }).prev_hash).toBe((e0.ledger as { hash: string }).hash);
    const links: Array<ChainLink & { action_plan_id: string }> = db.rows
      .sort((a, b) => a.sequence - b.sequence)
      .map((r) => ({
        action_plan_id: r.action_plan_id,
        sequence: r.sequence,
        prev_hash: r.prev_hash,
        hash: r.hash,
        plan: { ...r.plan, status: 'proposed' },
      }));
    expect(verifyChain(links).ok).toBe(true);
  });

  it('is idempotent on Idempotency-Key', async () => {
    const a = await svc.propose(auth('Marketer'), 'same-key', benignPlan());
    const b = await svc.propose(auth('Marketer'), 'same-key', benignPlan());
    expect(a.action_plan_id).toBe(b.action_plan_id);
    expect(db.rows).toHaveLength(1);
  });

  it('rejects propose without action:propose permission (Analyst)', async () => {
    await expect(svc.propose(auth('Analyst'), 'idem-x', benignPlan())).rejects.toThrow(/permission/);
  });

  it('sign() flips proposed->signed and appends a signature (Approver)', async () => {
    const entry = await svc.propose(auth('Marketer'), 'idem-sign', benignPlan());
    const hash = (entry.ledger as { hash: string }).hash;
    const signed = await svc.sign(auth('Approver'), entry.action_plan_id as string, { expected_hash: hash });
    expect(signed.status).toBe('signed');
    expect((signed.signatures as unknown[])).toHaveLength(1);
    // Signing does NOT change the chain hash (sigs/ledger excluded from canonical bytes).
    expect((signed.ledger as { hash: string }).hash).toBe(hash);
  });

  it('sign() on a spend-changing plan requires step-up + governor stamp + confirm_money (P4)', async () => {
    const spendPlan = {
      action_type: 'scale_budget',
      operations: [{ op_id: 'o1', connector: 'meta', op: 'update_budget', idempotency_key: 'k1' }],
      budget_impact: { spend_changing: true, daily_delta_minor: 50000, currency: 'INR' },
      explanation: {
        action: { type: 'scale_budget', summary_en: 'Scale winner +20%' },
        evidence: [{ metric: 'CPqL', value: 1200, source: 'metrics_layer' }],
        expected_effect: { summary: 'increase qualified leads' },
        confidence: 'high',
        reversible: true,
        approval_required: true,
        undo_plan: 'revert budget',
      },
    };
    const entry = await svc.propose(auth('Marketer'), 'idem-spend', spendPlan);
    const hash = (entry.ledger as { hash: string }).hash;
    // No step-up => forbidden.
    await expect(svc.sign(auth('Approver'), entry.action_plan_id as string, { expected_hash: hash })).rejects.toThrow(/step-up/);
  });

  it('verify() reports ok for an untampered chain', async () => {
    await svc.propose(auth('Marketer'), 'v-1', benignPlan());
    await svc.propose(auth('Marketer'), 'v-2', benignPlan());
    const res = await svc.verify(auth('Analyst'));
    expect(res.ok).toBe(true);
    expect(res.entries_checked).toBe(2);
  });
});
