/**
 * Outbound ports Cybertroic uses to triage + brief. Mirrors the optimizer's port pattern:
 * an INTERFACE plus an HTTP impl for the box and an in-memory FAKE for offline tests/typecheck.
 *
 * P8 (LLM via gateway): the model client routes through the gateway by TIER (sentry/investigator/
 * specialist) — never a raw vendor SDK. P5 (no silent actions): the OwnerNotifier is how the
 * guardian tells the human, in plain ₹-grounded language.
 *
 * The deterministic Sentry (consumer.ts) decides escalation WITHOUT a model call — the model
 * client only adds triage colour / a specialist read AFTER the arithmetic has spoken. So the
 * service is fully functional with the fakes (no key, no network).
 */
import type {
  GuardianBriefing,
  SecurityIncident,
  SentrySnapshot,
  SpecialistRead,
  TriageVerdict,
} from './types.js';

// ---- SecurityModelClient — the tier-routed brain (optional colour over the rules) ----

export interface SecurityModelClient {
  /** Tier-routed cheap classify of a snapshot (Sentry/Investigator). May refine but never
   *  overrides the deterministic verdict's severity/at-risk numbers. */
  triage(snapshot: SentrySnapshot, base: TriageVerdict): Promise<TriageVerdict>;
  /** Specialist read of an already-escalated incident (forensic narrative + recommendation). */
  analyze(incident: SecurityIncident): Promise<SpecialistRead>;
}

/** Tier → model id, supplied by env (the ladder). */
export interface ModelTierIds {
  sentry: string;
  investigator: string;
  specialist: string;
}

/**
 * BOX impl: posts to the OpenAI-compatible LLM gateway, routing by tier. Falls back to the
 * deterministic base verdict / a templated read on ANY error — the guardian must never go dark
 * because a model call failed (degrade gracefully, P7).
 */
export class HttpSecurityModelClient implements SecurityModelClient {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
    private readonly tiers: ModelTierIds,
    private readonly doFetch: typeof fetch = fetch,
  ) {}

  async triage(snapshot: SentrySnapshot, base: TriageVerdict): Promise<TriageVerdict> {
    if (!this.apiKey) return base; // no key ⇒ deterministic-only (correct Phase-0 path)
    try {
      const model = base.tier === 'investigator' ? this.tiers.investigator : this.tiers.sentry;
      const colour = await this.chat(model, [
        { role: 'system', content: 'You are a security sentry. Confirm or soften the given triage. Reply with one short sentence; never change the severity.' },
        { role: 'user', content: `event=${snapshot.eventType} reason=${base.reason}` },
      ]);
      // The model may only refine the human-readable reason — numbers/severity are sacred.
      return colour ? { ...base, reason: `${base.reason} · ${colour}` } : base;
    } catch {
      return base;
    }
  }

  async analyze(incident: SecurityIncident): Promise<SpecialistRead> {
    const templated: SpecialistRead = {
      narrative: incident.detail,
      recommendation: incident.reversible
        ? 'Low-risk reversible containment available — operator can one-click.'
        : 'Route remediation through the AI Manager firewall step-up (PIN/OTP) — destructive/irreversible.',
      confidence: incident.confidence,
    };
    if (!this.apiKey) return templated;
    try {
      const narrative = await this.chat(this.tiers.specialist, [
        { role: 'system', content: 'You are the incident specialist. Write a 2-sentence forensic read. Do not invent numbers; use only the evidence given.' },
        { role: 'user', content: `${incident.title} :: ${incident.detail} :: evidence=${incident.evidence ?? 'n/a'}` },
      ]);
      return narrative ? { ...templated, narrative } : templated;
    } catch {
      return templated;
    }
  }

  private async chat(model: string, messages: { role: string; content: string }[]): Promise<string> {
    const res = await this.doFetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${this.apiKey}` },
      body: JSON.stringify({ model, messages, max_tokens: 120, temperature: 0 }),
    });
    if (!res.ok) throw new Error(`gateway ${res.status}`);
    const body = (await res.json()) as { choices?: { message?: { content?: string } }[] };
    return body.choices?.[0]?.message?.content?.trim() ?? '';
  }
}

/**
 * Offline FAKE: the deterministic verdict is the answer (no network). This is what runs under
 * `vitest`/typecheck and on any box without OPENROUTER_API_KEY — and it proves the rules stand
 * alone (the model is colour, not the brain).
 */
export class InMemorySecurityModelClient implements SecurityModelClient {
  async triage(_snapshot: SentrySnapshot, base: TriageVerdict): Promise<TriageVerdict> {
    return base;
  }
  async analyze(incident: SecurityIncident): Promise<SpecialistRead> {
    return {
      narrative: incident.detail,
      recommendation: incident.reversible
        ? 'Reversible containment — one-click.'
        : 'Firewall step-up required (destructive/irreversible).',
      confidence: incident.confidence,
    };
  }
}

// ---- OwnerNotifier — how the guardian tells the human (P5: no silent actions) ----

export interface OwnerNotifier {
  /** Deliver a briefing to the business owner for a tenant. Resilient (never throws). */
  brief(tenant: string, briefing: GuardianBriefing): Promise<void>;
}

/** BOX impl: POSTs the briefing to a relay (Slack/WhatsApp/webhook). Swallows transport errors. */
export class HttpOwnerNotifier implements OwnerNotifier {
  constructor(
    private readonly webhookUrl: string,
    private readonly doFetch: typeof fetch = fetch,
  ) {}
  async brief(tenant: string, briefing: GuardianBriefing): Promise<void> {
    if (!this.webhookUrl) {
      console.log(`[cybertroic] (no OWNER_WEBHOOK_URL) brief tenant=${tenant}: ${briefing.headline}`);
      return;
    }
    try {
      await this.doFetch(this.webhookUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ tenant, briefing }),
      });
    } catch (err) {
      // Never let a dead webhook wedge the consume loop — log + move on (P7).
      console.warn(`[cybertroic] owner brief failed for tenant=${tenant}:`, (err as Error).message);
    }
  }
}

/** Offline FAKE: records briefs in memory so tests can assert the guardian spoke. */
export class InMemoryOwnerNotifier implements OwnerNotifier {
  readonly sent: { tenant: string; briefing: GuardianBriefing }[] = [];
  async brief(tenant: string, briefing: GuardianBriefing): Promise<void> {
    this.sent.push({ tenant, briefing });
  }
}
