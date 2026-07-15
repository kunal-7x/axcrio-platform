/**
 * CybertroicConsumer — the observe → classify → escalate loop (the always-on guardian).
 *
 * Subscribes to the money + control event backbone (wallet.*, treasury.float.debited/replenished,
 * treasury.vendor.low, credit.consumed, action.plan.created/signed, action.executed). For EVERY
 * fact it runs a deterministic, cheap "Sentry" classify (sentryClassify) — the 99% that are
 * nominal are CLEARED at near-zero cost. The few that are security-shaped (spend-velocity anomaly,
 * step-up reuse, float exhaustion, config drift) are ESCALATED: it builds a SecurityIncident,
 * emits a 'security.incident' (and, on a fresh escalation, a 'guardian.briefing') envelope via
 * createEnvelope + bus.publish, and calls the OwnerNotifier.
 *
 * BOUNDARY (design-of-record): Cybertroic DETECTS + TRIAGES + RECOMMENDS + BRIEFS. It never runs
 * destructive/irreversible containment here — that routes through the AI Manager firewall step-up.
 *
 * RESILIENCE (mirrors the optimizer consumer): the handler NEVER throws — a model/notifier/publish
 * failure is swallowed so it can't wedge a Kafka partition. NOTE: 'security.incident' /
 * 'guardian.briefing' are guardian-plane events NOT yet in the frozen registry, so bus.publish may
 * reject them under the validator; we treat a publish rejection as non-fatal (the incident is still
 * stored + the owner still briefed). Add the rows to topics.ts to put them on the wire for real.
 */
import { createEnvelope, type EventBus, type EventEnvelope } from '@growth-os/events';
import { withSpan, SpanKind } from '@growth-os/otel';
import type { OwnerNotifier, SecurityModelClient } from './ports.js';
import type { CybertroicStore } from './store.js';
import {
  SEVERITY_ORDER,
  type GuardianBriefing,
  type ModelTier,
  type SecurityFinding,
  type SecurityIncident,
  type SentrySnapshot,
  type Severity,
  type TriageVerdict,
} from './types.js';

/** The money/control topics the guardian watches. Dotted event TYPES (the bus maps to topics). */
export const WATCHED_EVENTS = [
  // money plane
  'wallet.topped_up',
  'wallet.reserved',
  'wallet.settled',
  'wallet.released',
  'credit.consumed',
  // treasury (vendor-credit float) plane
  'treasury.float.debited',
  'treasury.float.replenished',
  'treasury.vendor.low',
  // control / activation plane (action firewall + ledger)
  'action.plan.created',
  'action.plan.signed',
  'action.executed',
] as const;

/** Guardian-plane output types (NOT yet in the frozen registry — see file header). */
const SECURITY_INCIDENT_EVENT = 'security.incident';
const GUARDIAN_BRIEFING_EVENT = 'guardian.briefing';

/** Spend-velocity anomaly bar: a single debit ≥ this multiple of the rolling baseline escalates. */
const SPEND_BURST_MULTIPLE = 2.0;
/** Float-exhaustion bar: remaining vendor float ≤ this (paise) escalates as availability risk. */
const FLOAT_FLOOR_MINOR = 50_00; // ₹50 of headroom

const paiseToInr = (minor: number): number => Math.round(minor / 100);

export interface CybertroicConsumerDeps {
  bus: EventBus;
  store: CybertroicStore;
  model: SecurityModelClient;
  notifier: OwnerNotifier;
}

export class CybertroicConsumer {
  private readonly bus: EventBus;
  private readonly store: CybertroicStore;
  private readonly model: SecurityModelClient;
  private readonly notifier: OwnerNotifier;
  /** Bounded dedup on the deterministic incident id so we don't re-brief on every redelivery. */
  private readonly briefed = new Set<string>();

  constructor(deps: CybertroicConsumerDeps) {
    this.bus = deps.bus;
    this.store = deps.store;
    this.model = deps.model;
    this.notifier = deps.notifier;
  }

  start(): void {
    this.bus.subscribe([...WATCHED_EVENTS], async (env) => {
      await this.handle(env);
    });
  }

  /** Handle one money/control fact. Returns the incident it escalated (or null if cleared/failed). */
  async handle(env: EventEnvelope): Promise<SecurityIncident | null> {
    return withSpan(
      'cybertroic.consume',
      async () => {
        try {
          const snapshot = toSnapshot(env);
          const verdict = sentryClassify(snapshot);

          // Optional model colour — never overrides the deterministic numbers/severity.
          const refined = await safe(() => this.model.triage(snapshot, verdict), verdict);

          this.store.observe(env.tenant_id, refined.escalate);
          if (!refined.escalate) return null; // the 99% nominal path — cleared at near-zero cost.

          const incident = buildIncident(snapshot, refined);
          this.store.upsertIncident(env.tenant_id, incident);

          // P5: no silent actions. Emit the incident envelope (best-effort — see header).
          await this.tryEmit(env, SECURITY_INCIDENT_EVENT, incident as unknown as Record<string, unknown>, `cybertroic:incident:${incident.id}`);

          // First time THIS incident escalates → brief the owner (and emit the briefing).
          if (!this.briefed.has(incident.id)) {
            this.briefed.add(incident.id);
            if (this.briefed.size > 5000) this.briefed.delete(this.briefed.values().next().value as string);
            const briefing = buildBriefing(env.tenant_id, this.store.incidents(env.tenant_id));
            this.store.setBriefing(env.tenant_id, briefing);
            await safe(() => this.notifier.brief(env.tenant_id, briefing), undefined);
            await this.tryEmit(env, GUARDIAN_BRIEFING_EVENT, briefing as unknown as Record<string, unknown>, `cybertroic:briefing:${incident.id}`);
          }
          return incident;
        } catch {
          // Belt-and-braces: a guardian must NEVER throw out of the consume loop (P7).
          return null;
        }
      },
      { kind: SpanKind.CONSUMER, attributes: { 'event.type': env.type, tenant_id: env.tenant_id } },
    );
  }

  /** Emit a guardian-plane envelope; a validator rejection (event not yet registered) is non-fatal. */
  private async tryEmit(env: EventEnvelope, type: string, payload: Record<string, unknown>, idem: string): Promise<void> {
    try {
      const out = createEnvelope({
        type,
        tenant_id: env.tenant_id,
        workspace_id: env.workspace_id,
        correlation_id: env.correlation_id,
        causation_id: env.event_id,
        idempotency_key: idem,
        actor: { kind: 'system', id: 'growth-os:cybertroic' },
        payload,
      });
      await this.bus.publish(out);
    } catch {
      // security.incident / guardian.briefing aren't in the frozen registry yet → publish may
      // reject. The incident is already stored + the owner briefed, so this is observability-only.
    }
  }
}

/** Run `fn`, returning `fallback` on ANY rejection — keeps the loop resilient. */
async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

// ============================================================
// THE DETERMINISTIC SENTRY — cheap, auditable, no LLM. Every severity + ₹ figure is arithmetic
// over the consumed fact. This is the brain; the model is colour. Mirrors the panel _rules.ts
// principle (numbers always come from code, never from a model).
// ============================================================

/** Distil one envelope into the cheap snapshot the Sentry classifies. */
export function toSnapshot(env: EventEnvelope): SentrySnapshot {
  const p = (env.payload ?? {}) as Record<string, unknown>;
  const num = (k: string): number | undefined => (typeof p[k] === 'number' ? (p[k] as number) : undefined);

  return {
    eventType: env.type,
    tenantId: env.tenant_id,
    workspaceId: env.workspace_id,
    correlationId: env.correlation_id,
    causationId: env.causation_id ?? '',
    occurredAt: env.occurred_at,
    source: sourceFor(env.type),
    amountMinor: num('amount_minor') ?? num('cost_minor') ?? num('debited_minor') ?? num('delta_minor'),
    balanceMinor: num('balance_minor') ?? num('remaining_minor') ?? num('float_minor'),
    baselineMinor: num('baseline_minor') ?? num('hourly_norm_minor'),
    facts: {
      idempotency_key: env.idempotency_key,
      ...(typeof p.vendor === 'string' ? { vendor: p.vendor } : {}),
      ...(typeof p.scope === 'string' ? { scope: p.scope } : {}),
      ...(typeof p.step_up_token === 'string' ? { step_up_token_present: true } : {}),
      ...(typeof p.step_up_reused === 'boolean' ? { step_up_reused: p.step_up_reused } : {}),
      ...(typeof p.spend_changing === 'boolean' ? { spend_changing: p.spend_changing } : {}),
      ...(typeof p.governor_stamp === 'undefined' ? {} : { governor_stamped: true }),
    },
  };
}

function sourceFor(eventType: string): string {
  if (eventType.startsWith('treasury.')) return 'treasury';
  if (eventType.startsWith('wallet.') || eventType.startsWith('credit.')) return 'billing';
  if (eventType.startsWith('action.')) return 'activation';
  return 'engine';
}

/**
 * The deterministic triage. Returns escalate=false for the nominal majority. Escalation families:
 *  • spend_anomaly  — a debit/consume runs ≥ SPEND_BURST_MULTIPLE × the rolling baseline
 *  • availability   — a vendor float falls at/below the floor (exhaustion / single-point risk)
 *  • compliance     — a step-up token was reused (anti-replay), or a spend-changing plan signed sans stamp
 *  • config_drift   — a spend-changing action executed without a governor stamp / step-up
 */
export function sentryClassify(s: SentrySnapshot): TriageVerdict {
  const nominal: TriageVerdict = {
    escalate: false,
    severity: 'info',
    threatClass: 'availability',
    tier: 'sentry',
    confidence: 'high',
    reason: 'nominal — cleared by the Sentry',
    reversible: true,
    needsStamp: false,
  };

  // 1 · step-up token REUSE → compliance (anti-replay). Highest-signal control event.
  if (s.facts.step_up_reused === true) {
    return {
      escalate: true,
      severity: 'warning',
      threatClass: 'compliance',
      tier: 'investigator',
      confidence: 'high',
      reason: `step-up token presented more than once (anti-replay) on ${s.eventType}`,
      reversible: true,
      needsStamp: false,
    };
  }

  // 2 · spend-changing action executed/signed WITHOUT a governor stamp → config_drift / bypass.
  if (
    (s.eventType === 'action.executed' || s.eventType === 'action.plan.signed') &&
    s.facts.spend_changing === true &&
    s.facts.governor_stamped !== true
  ) {
    return {
      escalate: true,
      severity: 'critical',
      threatClass: 'config_drift',
      tier: 'specialist',
      confidence: 'high',
      reason: `spend-changing ${s.eventType} with no Budget-Governor stamp — money moved past the cap gate`,
      atRiskInr: s.amountMinor ? paiseToInr(Math.abs(s.amountMinor)) : undefined,
      reversible: false, // money already moved → needs sign-off, never one-click
      needsStamp: true,
    };
  }

  // 3 · vendor float exhaustion → availability (the fleet stalls if it empties).
  if (
    (s.eventType === 'treasury.float.debited' || s.eventType === 'treasury.vendor.low') &&
    typeof s.balanceMinor === 'number' &&
    s.balanceMinor <= FLOAT_FLOOR_MINOR
  ) {
    return {
      escalate: true,
      severity: s.balanceMinor <= 0 ? 'critical' : 'warning',
      threatClass: 'availability',
      tier: s.balanceMinor <= 0 ? 'specialist' : 'investigator',
      confidence: 'high',
      reason: `vendor float at ₹${paiseToInr(s.balanceMinor)} (≤ floor ₹${paiseToInr(FLOAT_FLOOR_MINOR)}) on ${String(s.facts.vendor ?? 'a vendor')}`,
      atRiskInr: paiseToInr(Math.max(0, FLOAT_FLOOR_MINOR - s.balanceMinor)),
      reversible: true, // reversible containment = pause that vendor's draws / replenish
      needsStamp: true, // replenishing spends money → needs a stamp
    };
  }

  // 4 · spend-velocity anomaly → spend_anomaly (a debit/consume that dwarfs the baseline).
  if (
    typeof s.amountMinor === 'number' &&
    s.amountMinor > 0 &&
    typeof s.baselineMinor === 'number' &&
    s.baselineMinor > 0 &&
    s.amountMinor >= s.baselineMinor * SPEND_BURST_MULTIPLE
  ) {
    const multiple = s.amountMinor / s.baselineMinor;
    return {
      escalate: true,
      severity: multiple >= SPEND_BURST_MULTIPLE * 2 ? 'critical' : 'warning',
      threatClass: 'spend_anomaly',
      tier: multiple >= SPEND_BURST_MULTIPLE * 2 ? 'specialist' : 'investigator',
      confidence: 'medium',
      reason: `spend ran ${multiple.toFixed(1)}× the rolling norm on ${s.eventType} (₹${paiseToInr(s.amountMinor)} vs ₹${paiseToInr(s.baselineMinor)})`,
      atRiskInr: paiseToInr(s.amountMinor - s.baselineMinor),
      reversible: true, // reversible containment = throttle/pause the spending surface
      needsStamp: false,
    };
  }

  return nominal;
}

/** Build the authoritative SecurityIncident from the snapshot + the deterministic verdict. */
export function buildIncident(s: SentrySnapshot, v: TriageVerdict): SecurityIncident {
  // Deterministic, stable id so redeliveries dedup and the panel's ack/dismiss persists.
  const id = `engine.${v.threatClass}.${s.source}.${stableKey(s)}`;
  return {
    id,
    severity: v.severity,
    threatClass: v.threatClass,
    title: titleFor(v),
    detail: v.reason,
    status: 'triage',
    tier: v.tier,
    confidence: v.confidence,
    opened_at: s.occurredAt,
    source: s.source,
    evidence: v.reason,
    ...(typeof v.atRiskInr === 'number' ? { at_risk_inr: v.atRiskInr } : {}),
    reversible: v.reversible,
    needs_stamp: v.needsStamp,
    correlation_id: s.correlationId,
  };
}

/** A short window key so repeated bursts in the same hour collapse to one incident. */
function stableKey(s: SentrySnapshot): string {
  const hour = s.occurredAt.slice(0, 13); // YYYY-MM-DDTHH
  const vendor = typeof s.facts.vendor === 'string' ? s.facts.vendor : s.eventType;
  return `${vendor}.${hour}`.replace(/[^a-zA-Z0-9._-]/g, '_');
}

function titleFor(v: TriageVerdict): string {
  switch (v.threatClass) {
    case 'spend_anomaly':
      return 'Spend velocity anomaly';
    case 'availability':
      return 'Vendor float exhaustion risk';
    case 'compliance':
      return 'Step-up token reuse';
    case 'config_drift':
      return 'Spend executed without a governor stamp';
    default:
      return 'Security signal';
  }
}

// ============================================================
// VULNERABILITY INGEST — the seam famit-security (the CVE/vuln engine) feeds. Cybertroic decides
// the incident: it re-derives severity from the numeric CVSS with its OWN bands (numbers-from-code),
// and fixes reversibility/tier itself — famit-security only supplies the facts. This populates the
// 'vulnerability' threatClass the desk already renders but nothing produced until now.
// ============================================================

/** CVSS base-score → cybertroic Severity (its own bands). KEV (actively exploited) floors to critical. */
export function vulnSeverity(baseScore: number | undefined, kev: boolean | undefined): Severity {
  if (kev) return 'critical';
  if (typeof baseScore !== 'number') return 'warning'; // unscored vuln is not "info" — watch it
  if (baseScore >= 9.0) return 'critical';
  if (baseScore >= 7.0) return 'warning';
  if (baseScore >= 4.0) return 'opportunity';
  return 'info';
}

/**
 * Build a deterministic 'vulnerability' SecurityIncident from a famit-security finding. A vuln
 * remediation is a code/patch change → reversible=false (needs sign-off, never one-click contain)
 * and needs_stamp=false (no money moves). Stable id per CVE so redeliveries dedup on the book.
 */
export function buildVulnIncident(f: SecurityFinding): SecurityIncident {
  const cve = (f.cve_id || '').trim().toUpperCase();
  const severity = vulnSeverity(f.base_score, f.kev);
  const tier: ModelTier = severity === 'critical' ? 'specialist' : severity === 'warning' ? 'investigator' : 'sentry';
  const cwe = (f.cwe ?? []).filter(Boolean).slice(0, 4);
  const scoreTxt =
    typeof f.base_score === 'number' ? `CVSS ${f.base_score}${f.ai_estimated ? ' (AI-estimated)' : ''}` : 'CVSS unscored';
  const evidence = [scoreTxt, cwe.length ? `CWE ${cwe.join(', ')}` : '', f.kev ? 'in CISA KEV (actively exploited)' : '']
    .filter(Boolean)
    .join(' · ');
  const title = (f.title || '').trim() || `${cve || 'Vulnerability'}: exploitable weakness`;
  return {
    id: `security.vulnerability.${cve || 'unknown'}`,
    severity,
    threatClass: 'vulnerability',
    title,
    detail: (f.summary || '').trim() || evidence,
    status: 'triage',
    tier,
    confidence: f.ai_estimated ? 'medium' : 'high',
    opened_at: f.occurred_at || new Date().toISOString(),
    source: 'famit-security',
    evidence,
    reversible: false, // a code/patch fix → routes through review/sign-off, never one-click
    needs_stamp: false, // no money moves
    ...(f.correlation_id ? { correlation_id: f.correlation_id } : {}),
  };
}

/** The owner briefing — plain-language, ₹-grounded. Mirrors _rules.ts ownerBriefing. */
export function buildBriefing(tenant: string, incidents: SecurityIncident[]): GuardianBriefing {
  const open = incidents.filter((i) => i.status !== 'resolved');
  const ranked = [...open].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  const top = ranked.slice(0, 3);
  const openCritical = open.filter((i) => i.severity === 'critical').length;

  const lines = top.map((i) => ({
    glyph: i.severity === 'critical' ? 'block' : i.severity === 'warning' ? 'info' : 'check-circle',
    text: `${i.title} — ${i.detail}${i.at_risk_inr ? ` (₹${i.at_risk_inr.toLocaleString('en-IN')} at risk)` : ''}.`,
  }));
  if (!lines.length) {
    lines.push({ glyph: 'check-circle', text: 'No open incidents. Every spend and transaction is being watched in real time.' });
  }

  const label = openCritical > 0 ? 'Critical exposure' : open.length ? 'Active watch' : 'Calm';
  return {
    headline: `${label}: ${open.length} open item${open.length === 1 ? '' : 's'} on the security desk`,
    summary:
      openCritical > 0
        ? 'We found a critical exposure and the top-tier model is on it. Here is what it is and what we are doing.'
        : open.length
        ? 'A few items are under investigation. None are urgent for you, but here is the honest picture.'
        : 'Your platform is calm. The guardian is watching everything; nothing needs your attention.',
    lines,
    generated_at: new Date().toISOString(),
  };
}
