/**
 * vuln-ingest tests — the famit-security → cybertroic feed. Proves the deterministic vuln→incident
 * mapping (severity re-derived from the numeric CVSS by cybertroic itself, KEV floors to critical,
 * AI-estimated surfaced honestly) and the HTTP ingest → /v1/posture path the panel reads.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { AddressInfo } from 'node:net';
import { buildCybertroicServer } from './server.js';
import { CybertroicStore } from './store.js';
import { buildVulnIncident, vulnSeverity } from './consumer.js';
import type { SecurityFinding } from './types.js';

describe('vulnSeverity — CVSS → cybertroic bands (numbers from code)', () => {
  it('maps score bands and floors KEV to critical', () => {
    expect(vulnSeverity(10.0, false)).toBe('critical');
    expect(vulnSeverity(9.0, false)).toBe('critical');
    expect(vulnSeverity(7.5, false)).toBe('warning');
    expect(vulnSeverity(5.0, false)).toBe('opportunity');
    expect(vulnSeverity(2.0, false)).toBe('info');
    expect(vulnSeverity(undefined, false)).toBe('warning'); // unscored ≠ info
    expect(vulnSeverity(3.0, true)).toBe('critical'); // KEV floors regardless of score
  });
});

describe('buildVulnIncident — deterministic vulnerability incident', () => {
  it('non-reversible, no stamp, stable id, KEV in evidence', () => {
    const f: SecurityFinding = {
      cve_id: 'cve-2021-44228',
      title: 'Log4Shell',
      base_score: 10.0,
      kev: true,
      cwe: ['CWE-502', 'CWE-917'],
      summary: 'JNDI RCE',
      occurred_at: '2021-12-10T00:00:00Z',
    };
    const inc = buildVulnIncident(f);
    expect(inc.threatClass).toBe('vulnerability');
    expect(inc.severity).toBe('critical');
    expect(inc.tier).toBe('specialist');
    expect(inc.reversible).toBe(false); // a code/patch fix routes through sign-off, never one-click
    expect(inc.needs_stamp).toBe(false); // no money moves
    expect(inc.id).toBe('security.vulnerability.CVE-2021-44228');
    expect(inc.evidence).toContain('CISA KEV');
    expect(inc.source).toBe('famit-security');
    expect(buildVulnIncident(f).id).toBe(inc.id); // idempotent key
  });

  it('labels AI-estimated CVSS honestly + lowers confidence', () => {
    const inc = buildVulnIncident({ cve_id: 'CVE-2026-90001', base_score: 9.8, ai_estimated: true });
    expect(inc.evidence).toContain('AI-estimated');
    expect(inc.confidence).toBe('medium');
    expect(inc.severity).toBe('critical');
  });
});

describe('POST /v1/ingest/security-finding → /v1/posture', () => {
  let server: ReturnType<typeof buildCybertroicServer>;
  let base: string;

  beforeAll(async () => {
    const store = new CybertroicStore();
    server = buildCybertroicServer({ store });
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', () => r()));
    base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  });
  afterAll(() => {
    server.close();
  });

  it('ingests a finding and surfaces it as a critical vulnerability incident', async () => {
    const res = await fetch(`${base}/v1/ingest/security-finding`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        tenant: 't_demo',
        finding: { cve_id: 'CVE-2022-22965', title: 'Spring4Shell', base_score: 9.8, kev: true, cwe: ['CWE-94'], summary: 'RCE via data binding' },
      }),
    });
    expect(res.status).toBe(200);
    const { incident } = (await res.json()) as { incident: { threatClass: string; severity: string } };
    expect(incident.threatClass).toBe('vulnerability');
    expect(incident.severity).toBe('critical');

    const posture = (await (await fetch(`${base}/v1/posture?tenant=t_demo`)).json()) as {
      threatLevel: string;
      incidents: { id: string }[];
      watch: { handed_off: number };
    };
    expect(posture.threatLevel).toBe('critical');
    expect(posture.incidents.some((i) => i.id === 'security.vulnerability.CVE-2022-22965')).toBe(true);
    expect(posture.watch.handed_off).toBeGreaterThanOrEqual(1);
  });

  it('rejects a finding without cve_id', async () => {
    const res = await fetch(`${base}/v1/ingest/security-finding`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ tenant: 't_demo', finding: {} }),
    });
    expect(res.status).toBe(400);
  });
});
