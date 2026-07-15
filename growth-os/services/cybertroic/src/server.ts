/**
 * Zero-dependency HTTP surface (node:http) for the Cybertroic guardian:
 *   GET  /v1/healthz
 *   GET  /v1/incidents?tenant=                       → the open incident book (panel)
 *   GET  /v1/posture?tenant=  (alias /v1/state)       → posture surfaces + threat level + watch tick
 *   POST /v1/triage    { tenant, snapshot }           → run the deterministic Sentry on a snapshot
 *   POST /v1/ingest/security-finding { tenant, finding } → ingest a famit-security vuln finding
 *   POST /v1/contain   { tenant, id, status }         → advance an incident's status (reversible-only)
 *   POST /v1/brief     { tenant }                     → (re)build + return the owner briefing
 *
 * The /triage endpoint is the pure brain made callable for ops + the panel's "explain this
 * classification" preview (no side effects beyond the in-memory book). The live loop runs via the
 * event backbone (consumer.ts). The store is the in-memory seam (swap for Postgres later).
 *
 * BOUNDARY: /contain only flips status on the in-memory book + (for reversible items) is the seam a
 * one-click pause would call. Destructive/irreversible containment is REFUSED here — it must route
 * through the AI Manager firewall step-up rail. We enforce that refusal in this surface.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { buildBriefing, sentryClassify, buildIncident, buildVulnIncident } from './consumer.js';
import type { CybertroicStore } from './store.js';
import { INCIDENT_STATUS_FLOW, type IncidentStatus, type SecurityFinding, type SentrySnapshot } from './types.js';

export interface CybertroicServerDeps {
  store: CybertroicStore;
  version?: string;
}

export function buildCybertroicServer(deps: CybertroicServerDeps): Server {
  return createServer((req, res) => {
    void route(req, res, deps).catch((err) =>
      json(res, 500, { error: { code: 'internal', message: (err as Error).message } }),
    );
  });
}

async function route(req: IncomingMessage, res: ServerResponse, deps: CybertroicServerDeps): Promise<void> {
  const method = req.method ?? 'GET';
  const u = new URL(req.url ?? '/', 'http://localhost');
  const path = u.pathname;
  const store = deps.store;

  if (method === 'GET' && (path === '/v1/healthz' || path === '/healthz')) {
    return json(res, 200, { status: 'ok', service: 'cybertroic', version: deps.version ?? '0.0.0' });
  }

  if (method === 'GET' && path === '/v1/incidents') {
    const tenant = u.searchParams.get('tenant');
    if (!tenant) return json(res, 400, { error: { code: 'validation_failed', message: 'tenant is required' } });
    return json(res, 200, { tenant, incidents: store.incidents(tenant) });
  }

  if (method === 'GET' && (path === '/v1/posture' || path === '/v1/state')) {
    // /v1/state is an alias of /v1/posture — the panel's getCybertroicState() reads "state".
    const tenant = u.searchParams.get('tenant');
    if (!tenant) return json(res, 400, { error: { code: 'validation_failed', message: 'tenant is required' } });
    return json(res, 200, store.state(tenant));
  }

  if (method === 'POST' && path === '/v1/triage') {
    const body = (await readJson(req)) as { tenant?: string; snapshot?: SentrySnapshot };
    if (!body.tenant || !body.snapshot?.eventType) {
      return json(res, 400, { error: { code: 'validation_failed', message: 'tenant + snapshot{eventType} required' } });
    }
    const verdict = sentryClassify(body.snapshot);
    // Side-effect-light: if it escalates, record it on the book so the panel sees it immediately.
    const incident = verdict.escalate ? buildIncident(body.snapshot, verdict) : null;
    if (incident) store.upsertIncident(body.tenant, incident);
    store.observe(body.tenant, verdict.escalate);
    return json(res, 200, { verdict, incident });
  }

  if (method === 'POST' && path === '/v1/ingest/security-finding') {
    // The vuln-detection feed from famit-security. Cybertroic builds the incident deterministically
    // (severity re-derived from the numeric CVSS) — the upstream engine only supplies facts.
    const body = (await readJson(req)) as { tenant?: string; finding?: SecurityFinding };
    if (!body.tenant || !body.finding?.cve_id) {
      return json(res, 400, { error: { code: 'validation_failed', message: 'tenant + finding{cve_id} required' } });
    }
    const incident = buildVulnIncident(body.finding);
    store.upsertIncident(body.tenant, incident);
    store.observe(body.tenant, true); // a triaged vuln finding is, by definition, a desk escalation
    return json(res, 200, { incident });
  }

  if (method === 'POST' && path === '/v1/contain') {
    const body = (await readJson(req)) as { tenant?: string; id?: string; status?: IncidentStatus };
    if (!body.tenant || !body.id || !body.status || !INCIDENT_STATUS_FLOW.includes(body.status)) {
      return json(res, 400, { error: { code: 'validation_failed', message: 'tenant + id + valid status required' } });
    }
    const current = store.incidents(body.tenant).find((i) => i.id === body.id);
    if (!current) return json(res, 404, { error: { code: 'not_found', message: 'unknown incident' } });
    // BOUNDARY: irreversible/destructive containment is NOT one-click here — refuse + point at the firewall.
    if (!current.reversible && (body.status === 'contained' || body.status === 'remediating')) {
      return json(res, 409, {
        error: {
          code: 'step_up_required',
          message: 'This containment is destructive/irreversible — route it through the AI Manager firewall step-up (PIN/OTP).',
        },
      });
    }
    const updated = store.setStatus(body.tenant, body.id, body.status);
    return json(res, 200, { incident: updated });
  }

  if (method === 'POST' && path === '/v1/brief') {
    const body = (await readJson(req)) as { tenant?: string };
    if (!body.tenant) return json(res, 400, { error: { code: 'validation_failed', message: 'tenant is required' } });
    const briefing = buildBriefing(body.tenant, store.incidents(body.tenant));
    store.setBriefing(body.tenant, briefing);
    return json(res, 200, { briefing });
  }

  json(res, 404, { error: { code: 'not_found', message: 'unknown route' } });
}

function readJson(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (c: Buffer) => chunks.push(c));
    req.on('end', () => {
      const s = Buffer.concat(chunks).toString('utf8');
      try {
        resolve(s ? JSON.parse(s) : {});
      } catch (err) {
        reject(err as Error);
      }
    });
    req.on('error', reject);
  });
}

function json(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(body));
}
