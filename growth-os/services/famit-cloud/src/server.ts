/**
 * Famit Cloud REST API (node:http, zero deps). The cloud surface:
 *   GET    /v1/healthz
 *   POST   /v1/workloads              {spec}          -> create
 *   GET    /v1/workloads?tenant=                      -> list
 *   GET    /v1/workloads/{id}                         -> get
 *   POST   /v1/workloads/{id}/start                   -> desired=running
 *   POST   /v1/workloads/{id}/stop                    -> desired=stopped
 *   POST   /v1/workloads/{id}/scale  {replicas}       -> scale a service
 *   GET    /v1/workloads/{id}/runs                    -> run history
 *   DELETE /v1/workloads/{id}                         -> remove
 * OpenAPI: contracts/openapi/famit-cloud.yaml.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { SpanKind, withSpan } from '@growth-os/otel';
import { CloudError, FamitCloud } from './cloud.js';
import { FAMIT_CLOUD_ENV, IS_PROD } from './shared.js';
import type { FileSystem } from './filesystem.js';
import type { FsAi, FsAiOp } from './fs-ai.js';
import type { Catalog } from './catalog.js';
import type { Resources, ResourceType } from './resources.js';
import type { Connectors } from './connectors.js';
import type { ConnectorCatalog } from './connector-catalog.js';
import type { AgentRuntime } from './agent-runtime.js';
import type { FeedbackHub } from './feedback.js';
import type { Billing } from './metering.js';
import type { WorkloadSpec } from './types.js';

export interface CloudServerDeps {
  cloud: FamitCloud;
  /** Optional filesystem plane (Drive). Routes 404 when absent. */
  fs?: FileSystem;
  fsAi?: FsAi;
  /** Optional marketplace: catalog of provisionable things + provisioned resources. */
  catalog?: Catalog;
  resources?: Resources;
  /** Optional EnterpriseConnect plane: external-system connectors + their catalog. */
  connectors?: Connectors;
  connectorCatalog?: ConnectorCatalog;
  /** Optional agentic runtime (real overnight agent loops). */
  agents?: AgentRuntime;
  /** Optional feedback fabric (cloud → optimizer / security / RL). */
  feedback?: FeedbackHub;
  /** Optional money meter + budget gate (P4). Powers GET /v1/usage. */
  billing?: Billing;
  /** Readiness predicate — /v1/readyz returns 200 only once the cloud has rehydrated + reconciled. */
  ready?: () => boolean;
  version?: string;
  /** Shared secret proving a request came through the trusted panel proxy. When set, every route
   *  except /healthz (and the vendor-authenticated connector webhook) must present a matching
   *  `x-famit-internal`. When empty, the gate is skipped in dev but fail-closed in prod. */
  internalToken?: string;
  /** Production posture (controls fail-closed-when-token-absent + dev tenant fallback). */
  prod?: boolean;
  /** Max JSON request body the control plane will buffer (bytes). */
  maxBodyBytes?: number;
}

/** An error carrying an explicit HTTP status (body cap, malformed JSON, auth, …). */
class RequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'RequestError';
  }
}

export function buildCloudServer(deps: CloudServerDeps): Server {
  const cfg: CloudServerDeps = {
    ...deps,
    internalToken: deps.internalToken ?? FAMIT_CLOUD_ENV.internalToken,
    prod: deps.prod ?? IS_PROD,
    maxBodyBytes: deps.maxBodyBytes ?? FAMIT_CLOUD_ENV.maxBodyBytes,
  };
  return createServer((req, res) => {
    const path = new URL(req.url ?? '/', 'http://localhost').pathname;
    void withSpan(
      'famit-cloud.http',
      () => route(req, res, cfg),
      { kind: SpanKind.SERVER, attributes: { 'http.method': req.method ?? 'GET', 'http.route': path } },
    ).catch((err) => sendError(res, err, cfg.prod));
  });
}

/** Does the request carry the trusted proxy's internal token? */
function internalAuthorized(req: IncomingMessage, deps: CloudServerDeps): boolean {
  const expected = deps.internalToken ?? '';
  if (!expected) return !deps.prod; // unconfigured → dev-allow, prod-deny (entrypoint also refuses boot)
  const got = req.headers['x-famit-internal'];
  if (typeof got !== 'string' || got.length === 0) return false;
  const a = Buffer.from(got);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

/** The tenant the request acts as — from the trusted `x-famit-tenant` header the proxy injects. In
 *  dev (non-prod), a `?tenant=` query is accepted as a fallback for direct curl testing. The caller's
 *  body is NEVER trusted for tenant (P6). */
function tenantOf(req: IncomingMessage, u: URL, deps: CloudServerDeps): string | null {
  const h = req.headers['x-famit-tenant'];
  if (typeof h === 'string' && h.trim()) return h.trim();
  if (!deps.prod) {
    const q = u.searchParams.get('tenant');
    if (q && q.trim()) return q.trim();
  }
  return null;
}

async function route(req: IncomingMessage, res: ServerResponse, deps: CloudServerDeps): Promise<void> {
  const method = req.method ?? 'GET';
  const u = new URL(req.url ?? '/', 'http://localhost');
  const path = u.pathname;
  const cloud = deps.cloud;

  // Readiness is unauthenticated (orchestrators gate traffic on it). 200 only after boot recovery +
  // the first reconcile pass — so a restarting cloud isn't sent work before it has rehydrated.
  if (method === 'GET' && (path === '/v1/readyz' || path === '/readyz')) {
    const ready = deps.ready ? deps.ready() : true;
    json(res, ready ? 200 : 503, { status: ready ? 'ready' : 'starting' });
    return;
  }

  // Liveness is unauthenticated (orchestrators probe it directly).
  if (method === 'GET' && (path === '/v1/healthz' || path === '/healthz')) {
    json(res, 200, {
      status: 'ok',
      service: 'famit-cloud',
      version: deps.version ?? '0.0.0',
      filesystem: Boolean(deps.fs),
      ai: Boolean(deps.fsAi?.enabled()),
      connectors: Boolean(deps.connectors),
      agents: deps.agents ? { enabled: true, reasoning: deps.agents.enabled() } : false,
      feedback: deps.feedback ? deps.feedback.status() : false,
    });
    return;
  }

  // The vendor-facing connector webhook authenticates with the connector's own signing secret (the
  // vendor cannot present the internal proxy token), so it is exempt from the proxy-auth + tenant gate.
  const isWebhook = method === 'POST' && /^\/v1\/connectors\/[^/]+\/webhook$/.test(path);

  if (!isWebhook && !internalAuthorized(req, deps)) {
    throw new RequestError(401, 'unauthorized', 'missing or invalid internal token');
  }

  // Operator-level observability — authenticated by the internal token but NOT tenant-scoped (these
  // are cloud-wide gauges scraped by infra, not tenant data).
  if (method === 'GET' && path === '/v1/metrics') {
    res.writeHead(200, { 'content-type': 'text/plain; version=0.0.4' });
    res.end(renderPrometheus(cloud.stats()));
    return;
  }

  // Server-derived tenant — the keystone of P6 isolation. Never read from the caller's body.
  const tenant = isWebhook ? '' : tenantOf(req, u, deps);
  if (!isWebhook && !tenant) {
    throw new RequestError(401, 'unauthorized', 'missing tenant (x-famit-tenant)');
  }

  if (method === 'GET' && path === '/v1/quota') {
    json(res, 200, cloud.quota(tenant!));
    return;
  }

  if (method === 'GET' && path === '/v1/usage') {
    json(res, 200, deps.billing ? deps.billing.usageFor(tenant!) : { tenantId: tenant!, byKind: {}, totalCreditsMinor: 0, events: 0 });
    return;
  }

  if (path.startsWith('/v1/fs/')) {
    await routeFs(method, path, u, req, res, deps, tenant!);
    return;
  }

  if (path.startsWith('/v1/catalog/') || path === '/v1/resources' || path.startsWith('/v1/resources/') || path === '/v1/domains/check') {
    await routeMarket(method, path, u, req, res, deps, tenant!);
    return;
  }

  if (path.startsWith('/v1/connectors')) {
    await routeConnectors(method, path, u, req, res, deps, tenant ?? '');
    return;
  }

  if (path.startsWith('/v1/agents')) {
    await routeAgents(method, path, u, req, res, deps, tenant!);
    return;
  }

  if (path.startsWith('/v1/feedback')) {
    await routeFeedback(method, path, u, res, deps, tenant!);
    return;
  }

  if (path === '/v1/workloads') {
    if (method === 'POST') {
      const body = (await readJson(req, deps.maxBodyBytes)) as { spec?: WorkloadSpec } & Partial<WorkloadSpec>;
      const raw = (body.spec ?? body) as WorkloadSpec;
      // Tenant comes from the session, not the caller's spec — overwrite any client-supplied tenantId.
      const spec = { ...raw, tenantId: tenant! };
      json(res, 201, cloud.createWorkload(spec));
      return;
    }
    if (method === 'GET') {
      json(res, 200, { items: cloud.list(tenant!) });
      return;
    }
  }

  const m = path.match(/^\/v1\/workloads\/([^/]+)(?:\/(start|stop|scale|runs|logs))?$/);
  if (m) {
    const id = decodeURIComponent(m[1]!);
    const action = m[2];
    if (method === 'GET' && !action) {
      const wl = cloud.get(id, tenant!);
      if (!wl) return notFound(res, id);
      json(res, 200, wl);
      return;
    }
    if (method === 'GET' && action === 'runs') {
      if (!cloud.get(id, tenant!)) return notFound(res, id);
      json(res, 200, { items: cloud.runs(id, tenant!) });
      return;
    }
    if (method === 'GET' && action === 'logs') {
      const lines = Math.min(2000, Math.max(1, Number(u.searchParams.get('lines')) || 200));
      json(res, 200, await cloud.logs(id, { runId: u.searchParams.get('run') ?? undefined, lines, tenantId: tenant! }));
      return;
    }
    if (method === 'POST' && action === 'start') {
      json(res, 200, cloud.start(id, tenant!));
      return;
    }
    if (method === 'POST' && action === 'stop') {
      json(res, 200, cloud.stop(id, tenant!));
      return;
    }
    if (method === 'POST' && action === 'scale') {
      const body = (await readJson(req, deps.maxBodyBytes)) as { replicas?: number };
      json(res, 200, cloud.scale(id, Number(body.replicas), tenant!));
      return;
    }
    if (method === 'DELETE' && !action) {
      cloud.delete(id, tenant!);
      res.writeHead(204);
      res.end();
      return;
    }
  }

  json(res, 404, { error: { code: 'not_found', message: 'unknown route' } });
}

/**
 * Filesystem plane (Drive). All mutations are POST + JSON (proxy-friendly, no multipart dep); reads
 * are GET with ?tenant=&path=. `download` streams raw bytes. 404s when no fs is wired.
 */
async function routeFs(
  method: string,
  path: string,
  u: URL,
  req: IncomingMessage,
  res: ServerResponse,
  deps: CloudServerDeps,
  tenant: string,
): Promise<void> {
  const fs = deps.fs;
  if (!fs) {
    json(res, 404, { error: { code: 'not_found', message: 'filesystem not enabled' } });
    return;
  }
  const op = path.slice('/v1/fs/'.length);
  const q = (k: string): string => u.searchParams.get(k) ?? '';

  if (method === 'GET' && op === 'list') {
    json(res, 200, await fs.list(tenant, q('path') || '/'));
    return;
  }
  if (method === 'GET' && op === 'read') {
    json(res, 200, await fs.read(tenant, q('path')));
    return;
  }
  if (method === 'GET' && op === 'stat') {
    json(res, 200, await fs.stat(tenant, q('path')));
    return;
  }
  if (method === 'GET' && op === 'download') {
    // Stream the file straight to the response — no whole-file buffering (OOM guard for big files).
    const { stream, mime, name, size } = await fs.openRead(tenant, q('path'));
    res.writeHead(200, {
      'content-type': mime,
      'content-disposition': `attachment; filename="${name.replace(/"/g, '')}"`,
      'content-length': String(size),
    });
    stream.on('error', () => res.destroy());
    stream.pipe(res);
    return;
  }

  if (method === 'POST') {
    const body = (await readJson(req, deps.maxBodyBytes)) as Record<string, string>;
    // Tenant is the server-derived one; the caller's body.tenant is ignored (P6).
    const t = tenant;
    switch (op) {
      case 'mkdir':
        json(res, 201, await fs.mkdir(t, body.path ?? ''));
        return;
      case 'write':
        json(res, 200, await fs.write(t, body.path ?? '', body.content ?? '', body.encoding === 'base64' ? 'base64' : 'utf8'));
        return;
      case 'upload':
        json(res, 201, await fs.upload(t, body.path ?? '', body.dataBase64 ?? '', body.mime));
        return;
      case 'move':
        json(res, 200, await fs.move(t, body.from ?? '', body.to ?? ''));
        return;
      case 'copy':
        json(res, 200, await fs.copy(t, body.from ?? '', body.to ?? ''));
        return;
      case 'convert':
        json(res, 201, await fs.convert(t, body.path ?? '', body.to ?? ''));
        return;
      case 'rm':
        await fs.remove(t, body.path ?? '');
        json(res, 200, { ok: true });
        return;
      case 'ai': {
        if (!deps.fsAi) {
          json(res, 404, { error: { code: 'not_found', message: 'ai not enabled' } });
          return;
        }
        json(res, 200, await deps.fsAi.run(t, body.path ?? '', (body.op ?? 'summarize') as FsAiOp, body.prompt));
        return;
      }
      default:
        break;
    }
  }

  json(res, 404, { error: { code: 'not_found', message: `unknown fs op '${op}'` } });
}

/**
 * Marketplace plane: GET /v1/catalog/{summary|agents|databases|domains|hosting},
 * GET /v1/domains/check?name=, GET /v1/resources?tenant=, POST /v1/resources/{provision|deprovision}.
 */
async function routeMarket(
  method: string,
  path: string,
  u: URL,
  req: IncomingMessage,
  res: ServerResponse,
  deps: CloudServerDeps,
  tenant: string,
): Promise<void> {
  const catalog = deps.catalog;
  const resources = deps.resources;
  if (!catalog || !resources) {
    json(res, 404, { error: { code: 'not_found', message: 'marketplace not enabled' } });
    return;
  }
  const q = (k: string): string => u.searchParams.get(k) ?? '';

  if (method === 'GET' && path === '/v1/catalog/summary') {
    json(res, 200, {
      agents: catalog.agentCount(),
      databases: catalog.databases().length,
      domainTlds: catalog.domainTlds().length,
      hostingPlans: catalog.hostingPlans().length,
    });
    return;
  }
  if (method === 'GET' && path === '/v1/catalog/agents') {
    json(res, 200, catalog.agents({ q: q('q'), category: q('category'), limit: Number(q('limit')) || undefined, offset: Number(q('offset')) || 0 }));
    return;
  }
  if (method === 'GET' && path === '/v1/catalog/databases') {
    json(res, 200, { items: catalog.databases() });
    return;
  }
  if (method === 'GET' && path === '/v1/catalog/domains') {
    json(res, 200, { items: catalog.domainTlds() });
    return;
  }
  if (method === 'GET' && path === '/v1/catalog/hosting') {
    json(res, 200, { items: catalog.hostingPlans() });
    return;
  }
  if (method === 'GET' && path === '/v1/catalog/workforce') {
    json(res, 200, { items: catalog.workforce() });
    return;
  }
  if (method === 'GET' && path === '/v1/domains/check') {
    json(res, 200, await resources.checkDomain(q('name')));
    return;
  }
  if (method === 'GET' && path === '/v1/resources') {
    json(res, 200, { items: resources.list(tenant) });
    return;
  }
  if (method === 'POST' && path === '/v1/resources/provision') {
    const body = (await readJson(req, deps.maxBodyBytes)) as { type?: string; spec?: Record<string, unknown> };
    const out = await resources.provision(tenant, (body.type ?? '') as ResourceType, body.spec ?? {});
    json(res, 201, out);
    return;
  }
  if (method === 'POST' && path === '/v1/resources/deprovision') {
    const body = (await readJson(req, deps.maxBodyBytes)) as { id?: string };
    json(res, 200, await resources.deprovision(String(body.id), tenant));
    return;
  }

  json(res, 404, { error: { code: 'not_found', message: 'unknown marketplace route' } });
}

/**
 * EnterpriseConnect plane:
 *   GET    /v1/connectors/catalog?q=&category=
 *   GET    /v1/connectors/catalog/{templateId}
 *   GET    /v1/connectors?tenant=
 *   POST   /v1/connectors                 {tenant, templateId, config, name?}  -> connect
 *   GET    /v1/connectors/{id}
 *   GET    /v1/connectors/{id}/runs
 *   POST   /v1/connectors/{id}/sync
 *   POST   /v1/connectors/{id}/test
 *   DELETE /v1/connectors/{id}            -> disconnect
 */
async function routeConnectors(
  method: string,
  path: string,
  u: URL,
  req: IncomingMessage,
  res: ServerResponse,
  deps: CloudServerDeps,
  callerTenant: string,
): Promise<void> {
  const connectors = deps.connectors;
  const catalog = deps.connectorCatalog;
  if (!connectors || !catalog) {
    json(res, 404, { error: { code: 'not_found', message: 'connectors not enabled' } });
    return;
  }
  const q = (k: string): string => u.searchParams.get(k) ?? '';

  if (method === 'GET' && path === '/v1/connectors/catalog') {
    json(res, 200, catalog.list({ q: q('q'), category: q('category') }));
    return;
  }
  const cm = path.match(/^\/v1\/connectors\/catalog\/([^/]+)$/);
  if (method === 'GET' && cm) {
    const tmpl = catalog.byId(decodeURIComponent(cm[1]!));
    if (!tmpl) return notFoundMsg(res, `connector template '${cm[1]}'`);
    json(res, 200, tmpl);
    return;
  }

  if (path === '/v1/connectors') {
    if (method === 'GET') {
      json(res, 200, { items: connectors.list(callerTenant) });
      return;
    }
    if (method === 'POST') {
      const body = (await readJson(req, deps.maxBodyBytes)) as { templateId?: string; config?: Record<string, string>; name?: string };
      // Tenant from the session, not the caller's body.
      json(res, 201, connectors.connect(callerTenant, String(body.templateId ?? ''), body.config ?? {}, body.name));
      return;
    }
  }

  const m = path.match(/^\/v1\/connectors\/([^/]+)(?:\/(runs|sync|test|webhook|reconnect))?$/);
  if (m && m[1] !== 'catalog') {
    const id = decodeURIComponent(m[1]!);
    const action = m[2];
    // Webhook is vendor-facing (no famit session/tenant); every other op is tenant-scoped — a foreign
    // id reads as not-found. `callerTenant` is '' only on the webhook path, which never uses it.
    const tenant = callerTenant || undefined;
    if (method === 'GET' && !action) {
      const c = connectors.get(id, tenant);
      if (!c) return notFoundMsg(res, `connector '${id}'`);
      json(res, 200, c);
      return;
    }
    if (method === 'GET' && action === 'runs') {
      json(res, 200, { items: connectors.runsFor(id, tenant) });
      return;
    }
    if (method === 'POST' && action === 'sync') {
      json(res, 200, await connectors.sync(id, tenant));
      return;
    }
    if (method === 'POST' && action === 'test') {
      json(res, 200, await connectors.test(id, tenant));
      return;
    }
    if (method === 'POST' && action === 'reconnect') {
      json(res, 200, connectors.reconnect(id, tenant));
      return;
    }
    if (method === 'POST' && action === 'webhook') {
      // Vendor-facing inbound — authenticated by the connector's HMAC signature over the RAW body (or
      // a shared secret), not a famit session. The raw bytes must be hashed exactly as received.
      const secret = (req.headers['x-connector-secret'] as string | undefined) ?? u.searchParams.get('secret') ?? undefined;
      const signature =
        (req.headers['x-connector-signature'] as string | undefined) ??
        (req.headers['x-hub-signature-256'] as string | undefined) ??
        undefined;
      const timestamp = (req.headers['x-connector-timestamp'] as string | undefined) ?? undefined;
      const { raw, body } = await readRawJson(req, deps.maxBodyBytes);
      json(res, 200, await connectors.ingest(id, body, { secret, signature, rawBody: raw, timestamp }));
      return;
    }
    if (method === 'DELETE' && !action) {
      json(res, 200, connectors.disconnect(id, tenant));
      return;
    }
  }

  json(res, 404, { error: { code: 'not_found', message: 'unknown connectors route' } });
}

/**
 * Agentic runtime plane:
 *   GET  /v1/agents?tenant=
 *   GET  /v1/agents/{id}
 *   POST /v1/agents/{id}/tick   -> run one reasoning step now
 */
async function routeAgents(
  method: string,
  path: string,
  _u: URL,
  _req: IncomingMessage,
  res: ServerResponse,
  deps: CloudServerDeps,
  tenant: string,
): Promise<void> {
  const agents = deps.agents;
  if (!agents) {
    json(res, 404, { error: { code: 'not_found', message: 'agent runtime not enabled' } });
    return;
  }
  if (method === 'GET' && path === '/v1/agents') {
    json(res, 200, { items: agents.list(tenant), reasoning: agents.enabled() });
    return;
  }
  const m = path.match(/^\/v1\/agents\/([^/]+)(?:\/(tick))?$/);
  if (m) {
    const id = decodeURIComponent(m[1]!);
    if (method === 'GET' && !m[2]) {
      const a = agents.get(id, tenant);
      if (!a) return notFoundMsg(res, `agent '${id}'`);
      json(res, 200, a);
      return;
    }
    if (method === 'POST' && m[2] === 'tick') {
      json(res, 200, await agents.tick(id, tenant));
      return;
    }
  }
  json(res, 404, { error: { code: 'not_found', message: 'unknown agents route' } });
}

/**
 * Feedback fabric (read-only observability of what the cloud reports to the brains):
 *   GET /v1/feedback/status   -> per-hub configured/reachable/sent/accepted
 *   GET /v1/feedback/recent?limit= -> rolling log of recent emissions
 *   POST /v1/feedback/probe   -> probe hub liveness now
 */
async function routeFeedback(method: string, path: string, u: URL, res: ServerResponse, deps: CloudServerDeps, tenant: string): Promise<void> {
  const feedback = deps.feedback;
  if (!feedback) {
    json(res, 404, { error: { code: 'not_found', message: 'feedback fabric not enabled' } });
    return;
  }
  if (method === 'GET' && path === '/v1/feedback/status') {
    json(res, 200, feedback.status());
    return;
  }
  if (method === 'GET' && path === '/v1/feedback/recent') {
    // Tenant-scoped: a per-user proxy caller only sees its own tenant's emissions.
    json(res, 200, { items: feedback.recent(Number(u.searchParams.get('limit')) || 50, tenant) });
    return;
  }
  if (method === 'POST' && path === '/v1/feedback/probe') {
    json(res, 200, await feedback.probe());
    return;
  }
  json(res, 404, { error: { code: 'not_found', message: 'unknown feedback route' } });
}

function notFoundMsg(res: ServerResponse, what: string): void {
  json(res, 404, { error: { code: 'not_found', message: `${what} not found` } });
}

/** Render cloud stats as Prometheus exposition text (scrape /v1/metrics). */
function renderPrometheus(s: ReturnType<FamitCloud['stats']>): string {
  const lines: string[] = [];
  lines.push('# HELP famit_cloud_workloads Total workloads under management.');
  lines.push('# TYPE famit_cloud_workloads gauge');
  lines.push(`famit_cloud_workloads ${s.workloads}`);
  lines.push('# HELP famit_cloud_workload_phase Workloads by phase.');
  lines.push('# TYPE famit_cloud_workload_phase gauge');
  for (const [phase, n] of Object.entries(s.phases)) {
    lines.push(`famit_cloud_workload_phase{phase="${phase}"} ${n}`);
  }
  lines.push('# HELP famit_cloud_runs Runs by status.');
  lines.push('# TYPE famit_cloud_runs gauge');
  lines.push(`famit_cloud_runs{status="running"} ${s.runs.running}`);
  lines.push(`famit_cloud_runs{status="exited"} ${s.runs.exited}`);
  lines.push(`famit_cloud_runs{status="failed"} ${s.runs.failed}`);
  lines.push('# HELP famit_cloud_restarts_total Cumulative restarts across workloads.');
  lines.push('# TYPE famit_cloud_restarts_total counter');
  lines.push(`famit_cloud_restarts_total ${s.restarts}`);
  lines.push('# HELP famit_cloud_crashloops Workloads currently in crashloop.');
  lines.push('# TYPE famit_cloud_crashloops gauge');
  lines.push(`famit_cloud_crashloops ${s.crashloops}`);
  lines.push('# HELP famit_cloud_reconcile_lag_ms Wall-clock of the last reconcile pass.');
  lines.push('# TYPE famit_cloud_reconcile_lag_ms gauge');
  lines.push(`famit_cloud_reconcile_lag_ms ${s.reconcile.lastLagMs}`);
  lines.push('# HELP famit_cloud_reconcile_total Reconcile passes since boot.');
  lines.push('# TYPE famit_cloud_reconcile_total counter');
  lines.push(`famit_cloud_reconcile_total ${s.reconcile.count}`);
  return lines.join('\n') + '\n';
}

function sendError(res: ServerResponse, err: unknown, prod = IS_PROD): void {
  if (res.headersSent) return;
  if (err instanceof RequestError) {
    json(res, err.status, { error: { code: err.code, message: err.message } });
    return;
  }
  if (err instanceof CloudError) {
    const status = err.code === 'not_found' ? 404 : err.code === 'unprocessable' ? 422 : 400;
    json(res, status, { error: { code: err.code, message: err.message } });
    return;
  }
  // Don't leak internal error text in production.
  const message = prod ? 'internal error' : (err as Error)?.message ?? 'internal error';
  json(res, 500, { error: { code: 'internal', message } });
}

function notFound(res: ServerResponse, id: string): void {
  json(res, 404, { error: { code: 'not_found', message: `workload '${id}' not found` } });
}

/** Read the raw request body as a string, bounded by `maxBytes` (413 on overflow). */
function readRawBody(req: IncomingMessage, maxBytes = FAMIT_CLOUD_ENV.maxBodyBytes): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let total = 0;
    let done = false;
    const fail = (err: Error): void => {
      if (done) return;
      done = true;
      reject(err);
    };
    req.on('data', (c: Buffer) => {
      if (done) return;
      total += c.length;
      if (total > maxBytes) {
        // Drain (discard) the rest so the client can finish sending and still read our 413 — destroying
        // the socket mid-upload would surface as a connection reset instead of a clean error.
        req.resume();
        fail(new RequestError(413, 'payload_too_large', `request body exceeds ${maxBytes} bytes`));
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      if (done) return;
      done = true;
      resolve(Buffer.concat(chunks).toString('utf8'));
    });
    req.on('error', (e) => fail(e as Error));
  });
}

function parseJsonBody(raw: string): Record<string, unknown> {
  try {
    return raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    throw new RequestError(400, 'bad_request', 'invalid JSON body');
  }
}

/** Read + parse a JSON body, bounded by `maxBytes` (413 on overflow, 400 on malformed JSON). */
async function readJson(req: IncomingMessage, maxBytes = FAMIT_CLOUD_ENV.maxBodyBytes): Promise<Record<string, unknown>> {
  return parseJsonBody(await readRawBody(req, maxBytes));
}

/** Like readJson but also returns the RAW bytes (needed for HMAC signature verification). */
async function readRawJson(req: IncomingMessage, maxBytes = FAMIT_CLOUD_ENV.maxBodyBytes): Promise<{ raw: string; body: Record<string, unknown> }> {
  const raw = await readRawBody(req, maxBytes);
  return { raw, body: parseJsonBody(raw) };
}

function json(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(body));
}
