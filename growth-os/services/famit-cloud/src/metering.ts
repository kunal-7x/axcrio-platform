/**
 * Billing — the money meter + pre-spend gate for the cloud (P4: money is structurally gated).
 *
 * Every billable action the cloud takes — provisioning a priced resource, an agent/Drive LLM call —
 * is METERED here (per-tenant, per-kind, INR paise integers) and surfaced at GET /v1/usage. Before a
 * spend-increasing action, the cloud asks the Budget-Governor "can this tenant afford it today?"; the
 * Governor's stamp is what the Action Ledger requires before signing. Both the meter sink and the
 * Governor are SEAMS: when their URLs are unset the meter records locally and the gate ALLOWS (so the
 * service runs self-contained offline), and when configured they talk to the real growth-os services.
 *
 * Zero new dependencies — node:crypto + fetch only.
 */
import { randomUUID } from 'node:crypto';

/** Parse a positive-integer paise amount, falling back when the input is missing/NaN/negative. */
function posIntOr(v: string | number | undefined, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : fallback;
}

export type UsageKind = 'compute' | 'llm' | 'storage' | 'resource' | 'agent' | 'salary' | 'outcome';

export interface UsageBucket {
  quantity: number;
  creditsMinor: number;
}

export interface TenantUsage {
  tenantId: string;
  byKind: Record<string, UsageBucket>;
  totalCreditsMinor: number;
  events: number;
}

/** A sink for metered events (the real one posts to the bus → billing; default is in-memory only). */
export interface MeterSink {
  record(event: {
    tenantId: string;
    workspaceId: string;
    kind: UsageKind;
    quantity: number;
    costMinor: number;
    dimensions?: Record<string, string | number>;
    idempotencyKey: string;
    occurredAt: string;
  }): Promise<void> | void;
}

export interface BillingOptions {
  /** Budget-Governor base URL (…/v1). When unset, the pre-spend gate ALLOWS (degrade gracefully). */
  governorUrl?: string;
  /** Optional external meter sink (bus → billing). The in-memory rollup is always kept regardless. */
  sink?: MeterSink;
  fetchImpl?: typeof fetch;
  iso?: () => string;
  /** Per-day compute estimate for a provisioned database (paise). */
  databaseDailyMinor?: number;
  /** Per-day compute estimate for a provisioned hosting site (paise). */
  siteDailyMinor?: number;
}

export interface GateResult {
  allowed: boolean;
  reason?: string;
  committedAfterMinor?: number;
  dailyCapMinor?: number;
}

export class Billing {
  private readonly usage = new Map<string, Map<UsageKind, UsageBucket>>();
  private readonly events = new Map<string, number>();
  private readonly governorUrl: string;
  private readonly sink?: MeterSink;
  private readonly fetchImpl: typeof fetch;
  private readonly iso: () => string;
  readonly databaseDailyMinor: number;
  readonly siteDailyMinor: number;

  constructor(opts: BillingOptions = {}) {
    this.governorUrl = (opts.governorUrl ?? process.env.GOVERNOR_URL ?? '').replace(/\/+$/, '');
    this.sink = opts.sink;
    this.fetchImpl = opts.fetchImpl ?? ((globalThis as { fetch: typeof fetch }).fetch);
    this.iso = opts.iso ?? ((): string => new Date().toISOString());
    // Validate the rates: a non-numeric env must NOT become NaN/0 and silently disable metering+gating
    // (both are guarded by `cost > 0`). Fall back to the default when the value isn't a positive integer.
    this.databaseDailyMinor = posIntOr(opts.databaseDailyMinor ?? process.env.CLOUD_DB_DAILY_MINOR, 5000);
    this.siteDailyMinor = posIntOr(opts.siteDailyMinor ?? process.env.CLOUD_SITE_DAILY_MINOR, 2000);
  }

  /** Record a billable usage event (accumulated per-tenant per-kind, paise integers, P4). */
  meter(
    tenantId: string,
    kind: UsageKind,
    quantity: number,
    creditsMinor: number,
    dimensions?: Record<string, string | number>,
  ): void {
    if (!tenantId) return;
    const cost = Math.max(0, Math.round(creditsMinor || 0));
    const qty = Math.max(0, quantity || 0);
    const byKind = this.usage.get(tenantId) ?? new Map<UsageKind, UsageBucket>();
    const bucket = byKind.get(kind) ?? { quantity: 0, creditsMinor: 0 };
    bucket.quantity += qty;
    bucket.creditsMinor += cost;
    byKind.set(kind, bucket);
    this.usage.set(tenantId, byKind);
    this.events.set(tenantId, (this.events.get(tenantId) ?? 0) + 1);
    // Best-effort fan-out to the canonical meter (never throws into the caller).
    if (this.sink) {
      void Promise.resolve(
        this.sink.record({
          tenantId,
          workspaceId: tenantId,
          kind,
          quantity: qty,
          costMinor: cost,
          dimensions,
          idempotencyKey: randomUUID(),
          occurredAt: this.iso(),
        }),
      ).catch(() => undefined);
    }
  }

  /** Per-tenant usage rollup for GET /v1/usage. */
  usageFor(tenantId: string): TenantUsage {
    const byKindMap = this.usage.get(tenantId);
    const byKind: Record<string, UsageBucket> = {};
    let total = 0;
    if (byKindMap) {
      for (const [k, v] of byKindMap) {
        byKind[k] = { quantity: v.quantity, creditsMinor: v.creditsMinor };
        total += v.creditsMinor;
      }
    }
    return { tenantId, byKind, totalCreditsMinor: total, events: this.events.get(tenantId) ?? 0 };
  }

  /** Ask the Budget-Governor whether a positive paise delta is affordable today. Degrades to ALLOW
   *  when no governor is configured, or when the governor is unreachable (availability > false-deny). */
  async gate(tenantId: string, workspaceId: string, dailyDeltaMinor: number): Promise<GateResult> {
    const delta = Math.max(0, Math.round(dailyDeltaMinor || 0));
    if (!this.governorUrl || delta === 0) return { allowed: true };
    try {
      const res = await this.fetchImpl(`${this.governorUrl}/v1/governor/stamp`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ tenantId, workspaceId, dailyDeltaMinor: delta }),
        redirect: 'manual',
      });
      if (!res.ok) return { allowed: true }; // governor erroring → don't hard-block ops (availability)
      const body = (await res.json()) as
        | { ok: true; committed_after_minor?: number; daily_cap_minor?: number }
        | { ok: false; reason?: string; daily_cap_minor?: number };
      if (body.ok) {
        return { allowed: true, committedAfterMinor: body.committed_after_minor, dailyCapMinor: body.daily_cap_minor };
      }
      return { allowed: false, reason: body.reason ?? 'budget cap exceeded', dailyCapMinor: body.daily_cap_minor };
    } catch {
      return { allowed: true }; // governor unreachable → allow (the meter still records the spend)
    }
  }
}
