/**
 * AgentRuntime — turns a "deployed agent" from a placeholder sleep-loop into a REAL autonomous
 * worker that keeps working overnight, even after the operator closes the panel.
 *
 * Each tick an agent instance:
 *   1. READS its task inbox from the Cloud Drive (`/agents/<id>/inbox`).
 *   2. REASONS one step — via OpenRouter (when OPENROUTER_API_KEY is set; same pattern as fs-ai.ts)
 *      or a deterministic role-grounded fallback offline.
 *   3. WRITES the result to `/agents/<id>/outbox` and appends a line to `/agents/<id>/journal.md`.
 *   4. EMITS FEEDBACK — an RL experience (reward = did it move work forward) and, on failure, a
 *      Cybertroic security snapshot.
 *
 * 24/7: instances persist in the cloud's durable snapshot and are rehydrated + re-scheduled on boot
 * (same mechanism as workloads + connectors) — so the agent fleet survives a restart and runs round
 * the clock. The in-process scheduler means "even after the system is closed" = the box keeps the
 * control plane up; the operator's browser is irrelevant.
 */
import { randomUUID } from 'node:crypto';
import { CloudError } from './cloud.js';
import type { FeedbackHub, RlDomain, SentrySnapshot } from './feedback.js';
import type { Billing } from './metering.js';

/** Slice of the Cloud Drive the runtime reads/writes (FileSystem satisfies it). */
export interface AgentFs {
  read(tenant: string, path: string): Promise<{ content: string; encoding?: string }>;
  write(tenant: string, path: string, content: string, encoding?: 'utf8' | 'base64'): Promise<unknown>;
  list(tenant: string, path: string): Promise<{ items: Array<{ name: string; path: string; kind: string }> }>;
  mkdir(tenant: string, path: string): Promise<unknown>;
  remove?(tenant: string, path: string): Promise<unknown>;
}

export interface AgentInstance {
  id: string;
  tenantId: string;
  /** Catalog template id (e.g. 'real-estate-sdr'). */
  agentId: string;
  name: string;
  role: string;
  industry: string;
  domain: RlDomain;
  everyMs: number;
  ticks: number;
  tasksDone: number;
  status: 'idle' | 'working' | 'error';
  /** False once a model call fails (bad key / model down) — surfaced honestly instead of silently
   *  serving the deterministic fallback as if it were reasoning. */
  modelHealthy?: boolean;
  lastTickAt?: string;
  lastOutput?: string;
  lastError?: string;
  createdAt: string;
  updatedAt: string;
}

export interface AgentTickResult {
  id: string;
  ok: boolean;
  taskTitle: string;
  output: string;
  usedLlm: boolean;
  error?: string;
}

export interface AgentRuntimeOptions {
  iso?: () => string;
  newId?: () => string;
  fetchImpl?: typeof fetch;
  /** OpenRouter key — when present, agents reason via a real model (else deterministic). */
  apiKey?: string;
  model?: string;
  timeoutMs?: number;
  /** Paise per 1k tokens for the agent-tick spend estimate. */
  paisePer1kTokens?: number;
  /** Max journal lines retained per agent (older are trimmed — bounds 24/7 Drive growth). */
  journalMaxLines?: number;
}

export interface AgentRuntimeDeps {
  feedback: FeedbackHub;
  fs: AgentFs;
  /** Money meter — each tick's LLM spend is metered + attributed to the tenant (P4). */
  billing?: Billing;
}

// P8 (LLM via gateway): route through the OPENROUTER_BASE_URL seam (the Famit Cloud LiteLLM
// proxy in prod), falling back to OpenRouter direct. Same env fs-ai.ts already honours.
const OPENROUTER_URL =
  (process.env.OPENROUTER_BASE_URL ?? 'https://openrouter.ai/api/v1').replace(/\/+$/, '') +
  '/chat/completions';

export class AgentRuntime {
  private readonly store = new Map<string, AgentInstance>();
  private readonly timers = new Map<string, ReturnType<typeof setInterval>>();
  private readonly iso: () => string;
  private readonly newId: () => string;
  private readonly fetchImpl: typeof fetch;
  private readonly apiKey?: string;
  private readonly model: string;
  private readonly timeoutMs: number;
  private readonly paisePer1kTokens: number;
  private readonly journalMaxLines: number;

  constructor(private readonly deps: AgentRuntimeDeps, opts: AgentRuntimeOptions = {}) {
    this.iso = opts.iso ?? ((): string => new Date().toISOString());
    this.newId = opts.newId ?? ((): string => randomUUID());
    this.fetchImpl = opts.fetchImpl ?? ((globalThis as { fetch: typeof fetch }).fetch);
    this.apiKey = opts.apiKey ?? process.env.OPENROUTER_API_KEY;
    this.model = opts.model ?? process.env.FS_AI_MODEL ?? 'openai/gpt-4o-mini';
    this.timeoutMs = opts.timeoutMs ?? 25_000;
    this.paisePer1kTokens = opts.paisePer1kTokens ?? Number(process.env.CLOUD_LLM_PAISE_PER_1K ?? 12);
    this.journalMaxLines = opts.journalMaxLines ?? 500;
  }

  enabled(): boolean {
    return Boolean(this.apiKey);
  }

  // ── lifecycle ────────────────────────────────────────────────────────────────────────────────

  async register(spec: { id?: string; tenantId: string; agentId: string; name: string; role: string; industry: string; domain: RlDomain; everyMs?: number }): Promise<AgentInstance> {
    if (!spec.tenantId) throw new CloudError('tenantId is required');
    const now = this.iso();
    const inst: AgentInstance = {
      id: spec.id ?? this.newId(),
      tenantId: spec.tenantId,
      agentId: spec.agentId,
      name: spec.name,
      role: spec.role,
      industry: spec.industry,
      domain: spec.domain,
      everyMs: clampEvery(spec.everyMs ?? 5 * 60_000),
      ticks: 0,
      tasksDone: 0,
      status: 'idle',
      createdAt: now,
      updatedAt: now,
    };
    this.store.set(inst.id, inst);
    // Seed the agent's workspace so the inbox/outbox exist + leave a first-shift note.
    await this.deps.fs.mkdir(inst.tenantId, `/agents/${inst.id}/inbox`).catch(() => null);
    await this.deps.fs.mkdir(inst.tenantId, `/agents/${inst.id}/outbox`).catch(() => null);
    await this.deps.fs
      .write(inst.tenantId, `/agents/${inst.id}/journal.md`, `# ${inst.name}\nRole: ${inst.role} · ${inst.industry}\nDeployed ${now}\n\n`, 'utf8')
      .catch(() => null);
    this.schedule(inst); // start ticking immediately (idempotent — no external re-scan needed)
    return inst;
  }

  list(tenantId?: string): AgentInstance[] {
    const all = [...this.store.values()];
    return (tenantId ? all.filter((a) => a.tenantId === tenantId) : all).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
  get(id: string, tenantId?: string): AgentInstance | undefined {
    const a = this.store.get(id);
    if (!a || (tenantId && a.tenantId !== tenantId)) return undefined;
    return a;
  }
  remove(id: string): void {
    this.unschedule(id);
    this.store.delete(id);
  }

  snapshot(): AgentInstance[] {
    return [...this.store.values()];
  }
  hydrate(items: AgentInstance[]): void {
    // Reset transient runtime fields (mirrors workloads/connectors): a snapshot taken mid-tick must
    // not restore a stale 'working'/'error' status or a dangling lastError after a restart.
    for (const a of items) this.store.set(a.id, { ...a, status: 'idle', lastError: undefined });
  }

  // ── 24/7 scheduler ───────────────────────────────────────────────────────────────────────────

  startScheduler(): void {
    for (const a of this.store.values()) this.schedule(a);
  }
  stopScheduler(): void {
    for (const id of [...this.timers.keys()]) this.unschedule(id);
  }
  private schedule(a: AgentInstance): void {
    if (this.timers.has(a.id)) return;
    const t = setInterval(() => {
      void this.tick(a.id).catch(() => null);
    }, a.everyMs);
    if (typeof t.unref === 'function') t.unref();
    this.timers.set(a.id, t);
  }
  private unschedule(id: string): void {
    const t = this.timers.get(id);
    if (t) {
      clearInterval(t);
      this.timers.delete(id);
    }
  }

  // ── the tick (read → reason → write → feedback) ──────────────────────────────────────────────

  async tick(id: string, tenantId?: string): Promise<AgentTickResult> {
    const a = this.store.get(id);
    if (!a || (tenantId && a.tenantId !== tenantId)) throw new CloudError(`agent '${id}' not found`, 'not_found');

    // Re-entrancy guard: the scheduler timer AND the manual /tick route can both fire for one agent.
    // A second concurrent tick would race the journal read-modify-write + double-count. Skip it.
    if (a.status === 'working') {
      return { id, ok: false, taskTitle: '', output: '', usedLlm: false, error: 'tick already in progress' };
    }

    a.status = 'working';
    a.ticks++;
    const stamp = this.iso();
    let result: AgentTickResult = { id, ok: false, taskTitle: '', output: '', usedLlm: false };

    try {
      const task = await this.nextTask(a);
      const reasoned = await this.reason(a, task.body);
      result = { id, ok: true, taskTitle: task.title, output: reasoned.text, usedLlm: reasoned.usedLlm };

      // Meter the agent's LLM spend (P4) — tokens × rate, attributed to the tenant.
      if (this.deps.billing && reasoned.usedLlm && reasoned.tokens > 0) {
        this.deps.billing.meter(a.tenantId, 'agent', reasoned.tokens, Math.round((reasoned.tokens / 1000) * this.paisePer1kTokens), {
          model: this.model,
          agent: a.agentId,
        });
      }

      const outPath = `/agents/${a.id}/outbox/${stamp.replace(/[:.]/g, '-')}.md`;
      await this.deps.fs.write(a.tenantId, outPath, `# ${task.title}\n_${stamp}_\n\n${reasoned.text}\n`, 'utf8').catch(() => null);
      await this.appendJournal(a, `- ${stamp} · ${task.title} → ${reasoned.text.slice(0, 80).replace(/\n/g, ' ')}…`);
      if (task.fromInbox) await this.deps.fs.remove?.(a.tenantId, task.path!).catch(() => null);

      a.tasksDone += task.fromInbox ? 1 : 0;
      a.status = 'idle';
      a.lastOutput = reasoned.text.slice(0, 280);
      a.lastError = undefined;
      a.lastTickAt = stamp;
      a.updatedAt = stamp;

      // RL feedback — moving an inbox task forward is worth more than a standing watch note.
      await this.deps.feedback
        .reportExperience(a.tenantId, a.domain, {
          context: { domain: a.domain, features: { from_inbox: task.fromInbox ? 1 : 0, used_llm: reasoned.usedLlm ? 1 : 0 }, actions: [{ id: `agent:${a.agentId}`, label: a.role }] },
          actionId: `agent:${a.agentId}`,
          reward: task.fromInbox ? 0.7 : 0.3,
          behaviorProb: 1,
        })
        .catch(() => null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      a.status = 'error';
      a.lastError = msg;
      a.lastTickAt = stamp;
      a.updatedAt = stamp;
      result = { id, ok: false, taskTitle: '', output: '', usedLlm: false, error: msg };
      await this.deps.feedback.reportSecurity(this.securitySnapshot(a, msg)).catch(() => null);
    }
    return result;
  }

  // ── task source ────────────────────────────────────────────────────────────────────────────

  private async nextTask(a: AgentInstance): Promise<{ title: string; body: string; fromInbox: boolean; path?: string }> {
    let files: Array<{ name: string; path: string; kind: string }> = [];
    try {
      const { items } = await this.deps.fs.list(a.tenantId, `/agents/${a.id}/inbox`);
      files = items.filter((i) => i.kind === 'file').sort((x, y) => x.name.localeCompare(y.name));
    } catch (err) {
      // A MISSING inbox dir is normal → fall through to the standing duty. Any OTHER I/O error is a
      // real fault and must surface (not be silently downgraded to busywork that reports success).
      if (!isNotFound(err)) throw err;
    }
    const first = files[0];
    if (first) {
      // Do NOT swallow a read failure here: if a selected inbox file can't be read, let it propagate
      // so tick() records an error + a security snapshot, rather than abandoning the task as "done".
      const content = await this.deps.fs.read(a.tenantId, first.path);
      const body = content.encoding === 'base64' ? Buffer.from(content.content, 'base64').toString('utf8') : content.content;
      return { title: `Inbox · ${first.name}`, body, fromInbox: true, path: first.path };
    }
    // Standing duty — an autonomous worker always has something useful to do for its book.
    return { title: `Shift note · ${a.role}`, body: standingDuty(a), fromInbox: false };
  }

  // ── reasoning ────────────────────────────────────────────────────────────────────────────────

  private async reason(a: AgentInstance, task: string): Promise<{ text: string; usedLlm: boolean; tokens: number }> {
    if (!this.apiKey) return { text: deterministicWork(a, task), usedLlm: false, tokens: 0 };
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
      const res = await this.fetchImpl(OPENROUTER_URL, {
        method: 'POST',
        headers: { authorization: `Bearer ${this.apiKey}`, 'content-type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          max_tokens: 700,
          messages: [
            { role: 'system', content: `You are a ${a.role} agent for the ${a.industry} sector working inside Famit's 24/7 AI revenue workforce. Be concise, action-oriented, and produce concrete next steps. Never invent customer PII.` },
            { role: 'user', content: task },
          ],
        }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (!res.ok) throw new Error(`model responded ${res.status}`);
      const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }>; usage?: { total_tokens?: number } };
      const text = data.choices?.[0]?.message?.content?.trim();
      if (!text) throw new Error('empty model response');
      a.modelHealthy = true; // a good completion clears any prior model-health flag
      return { text, usedLlm: true, tokens: data.usage?.total_tokens ?? 0 };
    } catch (err) {
      // Model down / bad key → flip the honesty flag (once) so we don't silently serve the fallback
      // as if it were real reasoning, then still do useful deterministic work (never stall the shift).
      if (a.modelHealthy !== false) {
        a.modelHealthy = false;
        await this.deps.feedback
          .reportSecurity(this.securitySnapshot(a, `model unhealthy: ${err instanceof Error ? err.message : String(err)}`))
          .catch(() => null);
      }
      return { text: deterministicWork(a, task), usedLlm: false, tokens: 0 };
    }
  }

  private async appendJournal(a: AgentInstance, line: string): Promise<void> {
    const path = `/agents/${a.id}/journal.md`;
    let prior = '';
    try {
      const c = await this.deps.fs.read(a.tenantId, path);
      prior = c.encoding === 'base64' ? Buffer.from(c.content, 'base64').toString('utf8') : c.content;
    } catch {
      prior = `# ${a.name}\n\n`;
    }
    // Bound 24/7 growth: keep the header + the most recent journalMaxLines lines.
    let next = `${prior}${line}\n`;
    const lines = next.split('\n');
    if (lines.length > this.journalMaxLines + 50) {
      const header = lines.slice(0, 2); // "# name" + blank
      next = [...header, ...lines.slice(-this.journalMaxLines)].join('\n');
    }
    await this.deps.fs.write(a.tenantId, path, next, 'utf8').catch(() => null);
  }

  private securitySnapshot(a: AgentInstance, error: string): SentrySnapshot {
    return {
      eventType: 'cloud.agent.tick_failed',
      tenantId: a.tenantId,
      workspaceId: a.tenantId,
      correlationId: a.id,
      causationId: a.id,
      occurredAt: this.iso(),
      source: 'famit-cloud',
      facts: { agent: a.agentId, role: a.role, ticks: a.ticks, error: error.slice(0, 200), threat_hint: 'availability' },
    };
  }
}

// ── deterministic offline work + standing duties ────────────────────────────────────────────────

function standingDuty(a: AgentInstance): string {
  const duties: Record<string, string> = {
    crm: `Review the latest leads for ${a.industry}. Prioritise the hottest by intent, draft a first-touch message, and propose the next call window.`,
    calls: `Plan the overnight call queue for ${a.industry}: who to call, in what order, and the opening line for each.`,
    whatsapp: `Draft WhatsApp follow-ups for warm ${a.industry} leads who didn't pick up, respecting quiet hours.`,
    campaigns: `Summarise yesterday's ${a.industry} campaign performance and propose one budget reallocation.`,
    funnels: `Inspect the ${a.industry} funnel for the biggest drop-off and propose one fix.`,
    payments: `List ${a.industry} customers with pending dues and draft a polite collection nudge.`,
  };
  return duties[a.domain] ?? `Advance the ${a.role} workstream for ${a.industry}: identify the single highest-leverage action and outline it.`;
}

function deterministicWork(a: AgentInstance, task: string): string {
  const head = task.split('\n')[0]?.slice(0, 120) ?? task.slice(0, 120);
  return [
    `**${a.role} (${a.industry}) — autonomous step**`,
    ``,
    `Task: ${head}`,
    ``,
    `1. Assessed the item against the ${a.domain} playbook.`,
    `2. Next action: prepare the outreach and stage it for the firewall-gated executor.`,
    `3. Confidence: medium (offline reasoning — set OPENROUTER_API_KEY for full model reasoning).`,
    ``,
    `_Produced by Famit Cloud AgentRuntime tick #${a.ticks}._`,
  ].join('\n');
}

function clampEvery(ms: number): number {
  return Math.max(30_000, Math.min(24 * 60 * 60_000, Math.round(ms)));
}

/** A missing inbox directory (normal) vs a real I/O fault. CloudError carries code 'not_found'. */
function isNotFound(err: unknown): boolean {
  const code = (err as { code?: string } | undefined)?.code;
  if (code === 'not_found' || code === 'ENOENT') return true;
  const msg = err instanceof Error ? err.message.toLowerCase() : '';
  return /no such (file|directory)|not found|enoent/.test(msg);
}
