/**
 * Famit Cloud Resources — provision + track the things the Catalog offers. A Resource is a managed
 * thing the cloud stood up for a tenant: a database, a deployed site, a running agent, or a domain.
 *
 * What's REAL vs sandbox (P7 honesty):
 *   • database — REAL: spins up the engine as a supervised container (DockerRunner) + a live
 *     connection string (a verified-free host port + generated password). Status reflects the
 *     backing workload's actual phase (provisioning → active / failed), never an optimistic guess.
 *   • site/agent — REAL container/process workload under the supervisor (agent = placeholder loop
 *     until the alpha runtime is wired; site exposure is local until a reverse proxy is attached).
 *   • domain — availability is REAL (live RDAP, no account); we only register when availability is
 *     CONFIRMED available (fail-closed). Registration is recorded in the sandbox registry unless a
 *     registrar provider is configured.
 */
import { createServer } from 'node:net';
import { randomBytes, randomUUID } from 'node:crypto';
import { Catalog } from './catalog.js';
import { CloudError } from './cloud.js';
import { Secrets } from './secrets.js';
import { Billing } from './metering.js';
import type { RlDomain } from './feedback.js';
import type { Phase, WorkloadSpec } from './types.js';

/** Spec handed to the agentic runtime when an agent resource is provisioned. */
export interface ProvisionedAgentSpec {
  id: string;
  tenantId: string;
  agentId: string;
  name: string;
  role: string;
  industry: string;
  domain: RlDomain;
  /** Workforce hires only: cadence + the salary/outcome metering overlay. */
  everyMs?: number;
  salaryInrMonth?: number;
  outcomeKind?: string;
}

export type ResourceType = 'database' | 'site' | 'agent' | 'domain';
export type ResourceStatus = 'provisioning' | 'active' | 'failed' | 'deprovisioned';

/** A registrable domain: 1–253 chars, valid labels (no leading/trailing hyphen, no empty labels),
 *  alphabetic TLD of 2+. Rejects double-dots, hyphen-edged labels, all-numeric TLDs. */
const DOMAIN_RE = /^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/;

const PORT_MIN = 26000;
const PORT_MAX = 30000;

export interface Resource {
  id: string;
  tenantId: string;
  type: ResourceType;
  name: string;
  status: ResourceStatus;
  spec: Record<string, unknown>;
  outputs: Record<string, string>;
  /** Backing workload id (database/site/agent), if any. */
  workloadId?: string;
  /** Allocated host port (database/site), freed on deprovision. */
  port?: number;
  createdAt: string;
  updatedAt: string;
}

/** The slice of the control-plane facade we need to stand up + observe backing workloads. */
export interface WorkloadDeployer {
  createWorkload(spec: WorkloadSpec): { id: string };
  delete(id: string): void;
  /** Graceful stop-then-remove (so the backing container is actually stopped, not orphaned). */
  teardown?(id: string): Promise<void>;
  /** Current phase of a workload, or undefined if it's gone. Lets resource status mirror reality. */
  phaseOf?(id: string): Phase | undefined;
}

export interface DomainAvailability {
  name: string;
  available: boolean | null; // null = unknown (RDAP unreachable / inconclusive)
  source: string;
}

export interface ResourcesOptions {
  iso?: () => string;
  newId?: () => string;
  rdapBase?: string;
  /** Envelope-encryption for credentials (DB passwords / connection strings) at rest. */
  secrets?: Secrets;
  /** Money meter + pre-spend budget gate (P4). When absent, provisioning is unmetered/ungated. */
  billing?: Billing;
  /** Hook fired when an agent is provisioned — wires it into the agentic runtime (real loops). */
  onAgentProvisioned?: (spec: ProvisionedAgentSpec) => void;
  /** Hook fired when an agent resource is deprovisioned — stops its runtime loop (no orphan ticks). */
  onAgentDeprovisioned?: (resourceId: string) => void;
}

/** Output keys that carry credentials — sealed in the durable snapshot, opened on load. */
const SECRET_OUTPUT_KEYS = ['password', 'connectionString'];

function statusFromPhase(phase: Phase | undefined): ResourceStatus {
  if (phase === 'running' || phase === 'succeeded') return 'active';
  if (phase === 'failed' || phase === 'crashloop') return 'failed';
  if (phase === 'stopped') return 'deprovisioned';
  return 'provisioning'; // pending / not-yet-started
}

/** Is a host TCP port free to bind right now? (catches ports held by other procs/containers.) */
function portFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const srv = createServer();
    srv.once('error', () => resolve(false));
    srv.once('listening', () => srv.close(() => resolve(true)));
    srv.listen(port, '127.0.0.1');
  });
}

export class Resources {
  private readonly store = new Map<string, Resource>();
  private readonly usedPorts = new Set<number>();
  private readonly iso: () => string;
  private readonly newId: () => string;
  private readonly rdapBase: string;
  private readonly secrets: Secrets;
  private readonly billing?: Billing;
  private readonly onAgentProvisioned?: (spec: ProvisionedAgentSpec) => void;
  private readonly onAgentDeprovisioned?: (resourceId: string) => void;

  constructor(
    private readonly catalog: Catalog,
    private readonly deployer: WorkloadDeployer,
    opts: ResourcesOptions = {},
  ) {
    this.iso = opts.iso ?? ((): string => new Date().toISOString());
    this.newId = opts.newId ?? ((): string => randomUUID());
    this.rdapBase = (opts.rdapBase ?? process.env.RDAP_BASE ?? 'https://rdap.org').replace(/\/$/, '');
    this.secrets = opts.secrets ?? new Secrets();
    this.billing = opts.billing;
    this.onAgentProvisioned = opts.onAgentProvisioned;
    this.onAgentDeprovisioned = opts.onAgentDeprovisioned;
  }

  /** Cheap, side-effect-free validation run BEFORE the money gate so an invalid spec never commits
   *  budget. The per-type provisioners re-check defensively. */
  private validateProvisionSpec(type: ResourceType, spec: Record<string, unknown>): void {
    switch (type) {
      case 'database':
        if (!this.catalog.databaseById(String(spec.engine ?? 'postgres'))) throw new CloudError(`unknown database engine '${String(spec.engine)}'`, 'validation_failed');
        return;
      case 'site':
        if (!this.catalog.hostingPlanById(String(spec.plan ?? 'container'))) throw new CloudError(`unknown hosting plan '${String(spec.plan)}'`, 'validation_failed');
        return;
      case 'domain':
        if (!DOMAIN_RE.test(String(spec.name ?? '').trim().toLowerCase())) throw new CloudError('enter a valid domain like name.com', 'validation_failed');
        return;
      case 'agent':
        if (!this.catalog.agentById(String(spec.agentId ?? ''))) throw new CloudError(`unknown agent '${String(spec.agentId)}'`, 'validation_failed');
        return;
      default:
        throw new CloudError(`unknown resource type '${String(type)}'`, 'validation_failed');
    }
  }

  /** Projected paise cost of standing up a resource — used by the pre-spend budget gate + the meter. */
  private projectedCostMinor(type: ResourceType, spec: Record<string, unknown>): number {
    if (!this.billing) return 0;
    if (type === 'database') return this.billing.databaseDailyMinor;
    if (type === 'site') return this.billing.siteDailyMinor;
    if (type === 'domain') {
      const name = String(spec.name ?? '').toLowerCase();
      const tld = name.slice(name.lastIndexOf('.') + 1);
      const inrYear = this.catalog.domainTlds().find((t) => t.tld === tld)?.priceInrYear ?? 999;
      return inrYear * 100; // INR → paise
    }
    if (type === 'agent') {
      // Workforce hires charge the first month's salary up front (through the budget gate);
      // plain catalog agents stay free at provision and bill per LLM tick.
      const wf = this.catalog.workforceById(String(spec.agentId ?? ''));
      return wf ? wf.salaryInrMonth * 100 : 0; // INR → paise
    }
    return 0;
  }

  list(tenantId?: string): Resource[] {
    const all = [...this.store.values()].map((r) => this.refresh(r));
    return (tenantId ? all.filter((r) => r.tenantId === tenantId) : all).sort((a, b) =>
      b.createdAt.localeCompare(a.createdAt),
    );
  }

  /** Resources for a durable snapshot, with credential outputs (DB password / connection string)
   *  SEALED so the snapshot file never holds cleartext. Deterministic → coalescing still holds. */
  snapshot(): Resource[] {
    return [...this.store.values()].map((r) => this.mapOutputs(r, (v) => this.secrets.seal(v)));
  }

  /** Restore resources from a durable snapshot (boot recovery), OPENING sealed credentials back to
   *  plaintext; re-claim their host ports. A pre-encryption (plaintext) snapshot loads as-is. */
  hydrate(items: Resource[]): void {
    for (const r of items) {
      const opened = this.mapOutputs(r, (v) => this.secrets.open(v));
      this.store.set(opened.id, opened);
      if (typeof opened.port === 'number') this.usedPorts.add(opened.port);
    }
  }

  /** Return a copy of `r` with its credential-bearing output keys transformed (seal/open). */
  private mapOutputs(r: Resource, fn: (v: string) => string): Resource {
    let touched = false;
    const outputs: Record<string, string> = { ...r.outputs };
    for (const k of SECRET_OUTPUT_KEYS) {
      if (outputs[k]) {
        outputs[k] = fn(outputs[k]);
        touched = true;
      }
    }
    return touched ? { ...r, outputs } : r;
  }
  /** Fetch a resource. Tenant-scoped when `tenantId` is given — a foreign id reads as missing (P6). */
  get(id: string, tenantId?: string): Resource | undefined {
    const r = this.store.get(id);
    if (!r) return undefined;
    if (tenantId && r.tenantId !== tenantId) return undefined; // foreign id = not-found
    return this.refresh(r);
  }

  /** Reconcile a resource's status from its backing workload's real phase (no-op for domains). */
  private refresh(r: Resource): Resource {
    if (!r.workloadId || r.status === 'deprovisioned' || !this.deployer.phaseOf) return r;
    const phase = this.deployer.phaseOf(r.workloadId);
    if (phase === undefined) return r; // workload not observable; leave last-known status
    const next = statusFromPhase(phase);
    if (next !== r.status) {
      r.status = next;
      r.updatedAt = this.iso();
    }
    return r;
  }

  /** Live domain availability via RDAP (404 = available, 200 = registered). Account-free + real. */
  async checkDomain(name: string): Promise<DomainAvailability> {
    const domain = String(name).trim().toLowerCase();
    if (!DOMAIN_RE.test(domain)) throw new CloudError('enter a valid domain like name.com', 'validation_failed');
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 6000);
      const res = await fetch(`${this.rdapBase}/domain/${encodeURIComponent(domain)}`, {
        signal: ctrl.signal,
        redirect: 'follow',
        headers: { accept: 'application/rdap+json' },
      });
      clearTimeout(t);
      if (res.status === 404) return { name: domain, available: true, source: 'rdap' };
      if (res.status === 200) return { name: domain, available: false, source: 'rdap' };
      return { name: domain, available: null, source: `rdap:${res.status}` };
    } catch {
      return { name: domain, available: null, source: 'rdap-unreachable' };
    }
  }

  async provision(tenantId: string, type: ResourceType, spec: Record<string, unknown>): Promise<Resource> {
    if (!tenantId) throw new CloudError('tenantId is required');

    // Validate the spec FIRST — otherwise an invalid request (unknown engine / bad domain) would
    // commit budget at the governor yet create + meter nothing (a wasted hold), and over-cap denials
    // would then block real provisions. Gate only well-formed requests.
    this.validateProvisionSpec(type, spec);

    // P4 money gate: ask the Budget-Governor BEFORE standing anything up. A refusal is a hard stop
    // (we never provision a priced resource the tenant can't afford today).
    const projectedMinor = this.projectedCostMinor(type, spec);
    if (projectedMinor > 0 && this.billing) {
      const gate = await this.billing.gate(tenantId, tenantId, projectedMinor);
      if (!gate.allowed) throw new CloudError(`cap_exceeded: ${gate.reason ?? 'daily budget cap reached'}`, 'unprocessable');
    }

    let resource: Resource;
    switch (type) {
      case 'database':
        resource = await this.provisionDatabase(tenantId, spec);
        break;
      case 'site':
        resource = await this.provisionSite(tenantId, spec);
        break;
      case 'agent':
        resource = this.provisionAgent(tenantId, spec);
        break;
      case 'domain':
        resource = await this.provisionDomain(tenantId, spec);
        break;
      default:
        throw new CloudError(`unknown resource type '${String(type)}'`, 'validation_failed');
    }

    // Meter the spend now that the resource actually exists (paise integers, attributed to the
    // tenant). A workforce hire is a SALARY (its own usage kind), not generic resource spend.
    if (projectedMinor > 0 && this.billing) {
      this.billing.meter(tenantId, type === 'agent' ? 'salary' : 'resource', 1, projectedMinor, { type, resourceId: resource.id });
    }
    return resource;
  }

  async deprovision(id: string, tenantId?: string): Promise<Resource> {
    const r = this.store.get(id);
    // Tenant-scope first: a foreign id is indistinguishable from missing (no cross-tenant teardown).
    if (!r || (tenantId && r.tenantId !== tenantId)) throw new CloudError(`resource '${id}' not found`, 'not_found');
    // Stop the agentic runtime loop FIRST so a deprovisioned agent can't keep ticking + spending.
    if (r.type === 'agent') this.onAgentDeprovisioned?.(r.id);
    if (r.workloadId) {
      try {
        if (this.deployer.teardown) await this.deployer.teardown(r.workloadId);
        else this.deployer.delete(r.workloadId);
      } catch {
        /* workload already gone — fine */
      }
    }
    if (typeof r.port === 'number') this.usedPorts.delete(r.port);
    r.status = 'deprovisioned';
    r.updatedAt = this.iso();
    return r;
  }

  // ---- helpers --------------------------------------------------------------------------------

  private async allocPort(): Promise<number> {
    for (let p = PORT_MIN; p < PORT_MAX; p++) {
      if (this.usedPorts.has(p)) continue;
      // Reserve SYNCHRONOUSLY (before the async probe) so two concurrent provisions cannot both pick
      // the same port across the `await` — the has-check + add is atomic w.r.t. the event loop.
      this.usedPorts.add(p);
      if (await portFree(p)) return p;
      this.usedPorts.delete(p);
    }
    throw new CloudError('no free host port available in range', 'unprocessable');
  }

  private save(r: Resource): Resource {
    this.store.set(r.id, r);
    return r;
  }

  private base(tenantId: string, type: ResourceType, name: string): Resource {
    const now = this.iso();
    return { id: this.newId(), tenantId, type, name, status: 'provisioning', spec: {}, outputs: {}, createdAt: now, updatedAt: now };
  }

  // ---- per-type provisioners ------------------------------------------------------------------

  private async provisionDatabase(tenantId: string, spec: Record<string, unknown>): Promise<Resource> {
    const engine = this.catalog.databaseById(String(spec.engine ?? 'postgres'));
    if (!engine) throw new CloudError(`unknown database engine '${String(spec.engine)}'`, 'validation_failed');
    const name = String(spec.name ?? `${engine.id}-${randomBytes(2).toString('hex')}`).replace(/[^a-zA-Z0-9-]/g, '-');
    const password = randomBytes(12).toString('base64url');
    const hostPort = await this.allocPort();
    const r = this.base(tenantId, 'database', name);

    const env: Record<string, string> = {};
    let user = 'root';
    if (engine.id === 'postgres') {
      env.POSTGRES_PASSWORD = password;
      user = 'postgres';
    } else if (engine.id === 'mysql') {
      env.MYSQL_ROOT_PASSWORD = password;
    } else if (engine.id === 'mariadb') {
      env.MARIADB_ROOT_PASSWORD = password;
    } else if (engine.id === 'mongo') {
      env.MONGO_INITDB_ROOT_USERNAME = 'root';
      env.MONGO_INITDB_ROOT_PASSWORD = password;
    }

    // A named volume keyed to the resource — DB data survives a control-plane restart (the supervisor
    // starts a fresh container that re-attaches the same volume).
    const volume = `famit-db-${r.id}`;
    let wl: { id: string };
    try {
      wl = this.deployer.createWorkload({
        name: `db-${name}`,
        tenantId,
        kind: 'service',
        runtime: 'container',
        image: engine.image,
        env,
        ports: [{ container: engine.port, host: hostPort }],
        volumes: [{ name: volume, mountPath: engine.dataDir }],
        restart: { mode: 'always', maxRetries: 5, backoffMs: 2000 },
      });
    } catch (err) {
      this.usedPorts.delete(hostPort); // don't leak the port if the workload couldn't be created
      throw err;
    }

    const auth = engine.id === 'redis' || engine.id === 'clickhouse' ? '' : `${user}:${password}@`;
    r.workloadId = wl.id;
    r.port = hostPort;
    r.spec = { engine: engine.id, image: engine.image, volume };
    r.outputs = {
      engine: engine.name,
      host: 'localhost',
      port: String(hostPort),
      username: engine.id === 'redis' || engine.id === 'clickhouse' ? '' : user,
      password,
      connectionString: `${engine.scheme}://${auth}localhost:${hostPort}`,
      volume,
    };
    r.updatedAt = this.iso();
    return this.save(this.refresh(r));
  }

  private async provisionSite(tenantId: string, spec: Record<string, unknown>): Promise<Resource> {
    const plan = this.catalog.hostingPlanById(String(spec.plan ?? 'container'));
    if (!plan) throw new CloudError(`unknown hosting plan '${String(spec.plan)}'`, 'validation_failed');
    const name = String(spec.name ?? `site-${randomBytes(2).toString('hex')}`).replace(/[^a-zA-Z0-9-]/g, '-');
    const image = String(spec.image ?? plan.defaultImage ?? 'nginx:alpine');
    const hostPort = await this.allocPort();
    const r = this.base(tenantId, 'site', name);

    let wl: { id: string };
    try {
      wl = this.deployer.createWorkload({
        name: `site-${name}`,
        tenantId,
        kind: 'service',
        runtime: 'container',
        image,
        ports: [{ container: plan.port, host: hostPort }],
        restart: { mode: 'always', maxRetries: 5, backoffMs: 2000 },
      });
    } catch (err) {
      this.usedPorts.delete(hostPort);
      throw err;
    }

    r.workloadId = wl.id;
    r.port = hostPort;
    r.spec = { plan: plan.id, runtime: plan.runtime, image };
    r.outputs = {
      url: `http://localhost:${hostPort}`,
      hostname: `${name}.famit.cloud`, // intended public name once a reverse proxy / domain is attached
      image,
    };
    r.updatedAt = this.iso();
    return this.save(this.refresh(r));
  }

  private provisionAgent(tenantId: string, spec: Record<string, unknown>): Resource {
    const tmpl = this.catalog.agentById(String(spec.agentId ?? ''));
    if (!tmpl) throw new CloudError(`unknown agent '${String(spec.agentId)}'`, 'validation_failed');
    const r = this.base(tenantId, 'agent', tmpl.name);

    // Placeholder long-running process representing the deployed agent instance (kept alive by the
    // supervisor). The real reasoning loop is the alpha runtime — wired separately.
    const wl = this.deployer.createWorkload({
      name: `agent-${tmpl.id}-${randomBytes(2).toString('hex')}`,
      tenantId,
      kind: 'service',
      runtime: 'process',
      command: ['sh', '-c', `echo "agent ${tmpl.role} · ${tmpl.industry} online"; while true; do sleep 3600; done`],
      restart: { mode: 'always', maxRetries: 3, backoffMs: 2000 },
    });

    r.workloadId = wl.id;
    r.spec = { agentId: tmpl.id, category: tmpl.category, role: tmpl.role, industry: tmpl.industry, tier: tmpl.tier };
    r.outputs = { tools: tmpl.tools.join(', '), tier: tmpl.tier };
    r.updatedAt = this.iso();
    const saved = this.save(this.refresh(r));

    // Wire the agent into the autonomous runtime so it actually WORKS its book 24/7 (reads its Drive
    // inbox → reasons → writes outbox → feeds the brains), not just an idle keep-alive loop.
    // A workforce hire also carries its salary/outcome overlay + cadence into the runtime.
    const wf = this.catalog.workforceById(tmpl.id);
    this.onAgentProvisioned?.({
      id: saved.id,
      tenantId,
      agentId: tmpl.id,
      name: tmpl.name,
      role: tmpl.role,
      industry: tmpl.industry,
      domain: wf?.domain ?? agentDomain(tmpl.tools),
      everyMs: wf?.everyMs,
      salaryInrMonth: wf?.salaryInrMonth,
      outcomeKind: wf?.outcomeKind,
    });
    return saved;
  }

  private async provisionDomain(tenantId: string, spec: Record<string, unknown>): Promise<Resource> {
    const name = String(spec.name ?? '').trim().toLowerCase();
    if (!DOMAIN_RE.test(name)) throw new CloudError('enter a valid domain like name.com', 'validation_failed');
    const avail = await this.checkDomain(name);
    // Fail-closed: only register when availability is CONFIRMED. Unknown (RDAP down/rate-limited) is
    // a hard stop, so we never register an already-registered name.
    if (avail.available === false) throw new CloudError(`${name} is already registered`, 'unprocessable');
    if (avail.available !== true) throw new CloudError(`could not verify availability for ${name} — try again`, 'unprocessable');

    const tld = name.slice(name.lastIndexOf('.') + 1);
    const price = this.catalog.domainTlds().find((t) => t.tld === tld)?.priceInrYear ?? 999;
    const registrarConfigured = Boolean(process.env.REGISTRAR_API_KEY);

    const r = this.base(tenantId, 'domain', name);
    const expires = new Date(new Date().getTime() + 365 * 24 * 3600 * 1000);
    r.status = 'active'; // a domain registration has no backing workload to wait on
    r.spec = { tld, priceInrYear: price };
    r.outputs = {
      registrar: registrarConfigured ? 'live' : 'sandbox',
      priceInr: String(price),
      registeredAt: this.iso(),
      expiresAt: expires.toISOString(),
      availability: avail.source,
    };
    r.updatedAt = this.iso();
    return this.save(r);
  }
}

/** Map an agent template's tools onto the Grow-Connect learning domain it should train. */
function agentDomain(tools: string[]): RlDomain {
  if (tools.includes('calls')) return 'calls';
  if (tools.includes('whatsapp')) return 'whatsapp';
  if (tools.includes('ads')) return 'campaigns';
  if (tools.includes('payments') || tools.includes('ledger')) return 'payments';
  return 'crm';
}
