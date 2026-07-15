/**
 * Cybertroic-local types. These MIRROR the panel's app/cybertroic/_rules.ts shapes 1:1
 * (Severity, ThreatClass, IncidentStatus, ModelTier, the Incident/Surface/briefing fields)
 * so the service↔panel contract lines up — the panel's getCybertroicState() reads exactly
 * what /v1/* here returns. The classification + every number is computed deterministically
 * (see consumer.ts); an LLM may only narrate copy, never invent a severity or a ₹ figure.
 */

// ---- the panel-mirrored vocabulary ------------------------------------------

export type Severity = 'critical' | 'warning' | 'opportunity' | 'info';
export type Confidence = 'high' | 'medium' | 'low';

/** A threat's family — drives the specialist model + the remediation playbook. */
export type ThreatClass =
  | 'spend_anomaly' // money moving faster/oddly vs the norm
  | 'credential' // auth / secret / legacy-bearer-token risk
  | 'config_drift' // a control toggled into an unsafe state
  | 'vulnerability' // an exploitable weakness in a surface
  | 'compliance' // DND / consent / hours / step-up bypass
  | 'access' // tenant-isolation / RBAC / impersonation
  | 'data_exposure' // a leak path (PII, secret, cross-tenant)
  | 'availability'; // a surface saturating / float exhaustion / DoS pressure

export type IncidentStatus = 'triage' | 'analyzing' | 'remediating' | 'contained' | 'resolved';

/** The security model ladder — the escalation IS the product (cheap watcher → costly lead). */
export type ModelTier = 'sentry' | 'investigator' | 'specialist';

export type SurfaceStatus = 'guarded' | 'watch' | 'exposed' | 'unknown';

/** Severity sort weight (lower = more urgent → shown first). Mirrors _rules.ts. */
export const SEVERITY_ORDER: Record<Severity, number> = { critical: 0, warning: 1, opportunity: 2, info: 3 };

/** Canonical status flow (mirrors _rules.ts STATUS_ORDER). */
export const INCIDENT_STATUS_FLOW: IncidentStatus[] = [
  'triage',
  'analyzing',
  'remediating',
  'contained',
  'resolved',
];

// ---- the authoritative incident the engine emits ----------------------------

/**
 * SecurityIncident — the engine's authoritative incident. Field names are the
 * snake_case wire shape the panel's CybertroicState.incidents[] reads (id, severity,
 * threatClass, title, status, tier, opened_at, source) PLUS the engine-only forensic
 * fields the deterministic classifier fills (evidence, at_risk_inr, reversible, …).
 */
export interface SecurityIncident {
  /** Stable, deterministic per-signal id (drives ack/dismiss + idempotency). */
  id: string;
  severity: Severity;
  threatClass: ThreatClass;
  title: string;
  detail: string;
  status: IncidentStatus;
  /** Which model tier is (or would be) handling it — the deterministic escalation. */
  tier: ModelTier;
  confidence: Confidence;
  /** RFC3339 UTC of when the incident opened (the source fact's occurred_at). */
  opened_at: string;
  /** Originating module / event ('billing', 'firewall', 'treasury', 'activation'…). */
  source: string;
  /** The arithmetic / fact behind the classification (auditable — never invented). */
  evidence?: string;
  /** ₹ the incident puts at risk over the stated window (paise → rupees, integer). */
  at_risk_inr?: number;
  /** Containment is reversible (one-click) vs needs sign-off. */
  reversible: boolean;
  /** A money-touching containment needs a Budget-Governor stamp. */
  needs_stamp: boolean;
  /** The originating envelope's correlation id (journey trace). */
  correlation_id?: string;
}

/** A guarded surface's live posture (mirrors _rules.ts Surface). */
export interface PostureSurface {
  id: string;
  label: string;
  glyph: string;
  status: SurfaceStatus;
  /** 0..1 — how fully the surface is monitored. */
  coverage: number;
  note: string;
}

export type CyberThreatLevel = 'calm' | 'elevated' | 'active' | 'critical';

/** A cheap-watcher throughput tick (the "Sentry cleared N of M" story). */
export interface WatchTick {
  window_s: number;
  observed: number;
  cleared: number;
  escalated: number;
  handed_off: number;
}

/**
 * CybertroicState — the authoritative guardian snapshot the panel reads via
 * getCybertroicState(). Shape lines up with the panel's CybertroicState type.
 */
export interface CybertroicState {
  tenant: string;
  threatLevel: CyberThreatLevel;
  surfaces: PostureSurface[];
  incidents: SecurityIncident[];
  watch: WatchTick;
}

/** The owner briefing — plain-language, ₹-grounded (mirrors _rules.ts OwnerBriefing). */
export interface GuardianBriefing {
  headline: string;
  summary: string;
  lines: { glyph: string; text: string }[];
  generated_at: string;
}

// ---- the deterministic sentry I/O contracts ---------------------------------

/** The cheap snapshot the Sentry classifies — distilled from one consumed envelope. */
export interface SentrySnapshot {
  /** The dotted source event type (e.g. 'treasury.float.debited'). */
  eventType: string;
  tenantId: string;
  workspaceId: string;
  correlationId: string;
  causationId: string;
  /** The originating fact's occurred_at (RFC3339). */
  occurredAt: string;
  /** Originating plane/module ('billing', 'treasury', 'firewall', 'activation'). */
  source: string;
  /** Money moved by this fact in paise (signed; debit > 0), when applicable. */
  amountMinor?: number;
  /** Remaining float/balance after the fact, in paise, when applicable. */
  balanceMinor?: number;
  /** A coarse rolling baseline (paise) the classifier compares spend velocity against. */
  baselineMinor?: number;
  /** Free-form facts the deterministic rules read (idempotency_key, scope, flags…). */
  facts: Record<string, string | number | boolean>;
}

/**
 * The Sentry verdict — the deterministic triage. `escalate=false` ⇒ the 99% nominal path
 * (cleared at near-zero cost). `escalate=true` ⇒ build the SecurityIncident + climb the ladder.
 */
export interface TriageVerdict {
  escalate: boolean;
  severity: Severity;
  threatClass: ThreatClass;
  tier: ModelTier;
  confidence: Confidence;
  /** Short, auditable reason (the arithmetic) → becomes incident.evidence. */
  reason: string;
  /** ₹ at risk over the window (rupees, integer), when computable. */
  atRiskInr?: number;
  reversible: boolean;
  needsStamp: boolean;
}

/** A specialist's deeper read of an escalated incident (narration only — no number invention). */
export interface SpecialistRead {
  /** Human-readable forensic summary (the LLM may write this). */
  narrative: string;
  /** A recommended, firewall-routed remediation (never auto-executed here). */
  recommendation: string;
  confidence: Confidence;
}

/**
 * SecurityFinding — a triaged vulnerability finding pushed IN from famit-security (the CVE/vuln
 * detection+triage engine). Cybertroic OWNS the incident shape: it re-derives severity from the
 * numeric CVSS base_score with its OWN bands (never trusting an upstream label), so the
 * "numbers come from code, never a model" principle holds even for an ingested finding.
 */
export interface SecurityFinding {
  cve_id: string;
  title?: string;
  /** CVSS base score 0..10 — the authoritative number cybertroic maps to a Severity itself. */
  base_score?: number;
  /** true ⇒ base_score is AI-estimated (CTI-VSP) — surfaced honestly in evidence, never hidden. */
  ai_estimated?: boolean;
  /** In CISA KEV (actively exploited) — floors severity to critical. */
  kev?: boolean;
  cwe?: string[];
  summary?: string;
  /** The remediation strategy famit-security proposes (feeds the briefing / famit-remediation). */
  remediation?: string;
  /** Affected package / product / target string. */
  affected?: string;
  /** RFC3339 of the triage (defaults to now if absent). */
  occurred_at?: string;
  correlation_id?: string;
}
