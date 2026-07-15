/**
 * In-memory state for the guardian (the persistence SEAM — swap for Postgres / the `memory`
 * service later without touching the classifier). Holds, per tenant: the open incident book
 * (deduped by deterministic id), the live posture surfaces, and the rolling Sentry watch tick
 * (the cheap-watcher throughput story). The consumer WRITES here; the HTTP surface READS here.
 *
 * Mirrors grow-connect's store.ts pattern: an ensure(tenant) seam + idempotent upserts.
 */
import {
  INCIDENT_STATUS_FLOW,
  SEVERITY_ORDER,
  type CyberThreatLevel,
  type CybertroicState,
  type GuardianBriefing,
  type PostureSurface,
  type SecurityIncident,
  type WatchTick,
} from './types.js';

interface TenantState {
  /** id → incident (idempotent: re-seeing a signal updates, never duplicates). */
  incidents: Map<string, SecurityIncident>;
  surfaces: PostureSurface[];
  watch: WatchTick;
  lastBriefing: GuardianBriefing | null;
}

const WATCH_WINDOW_S = 600;

function emptyTenant(): TenantState {
  return {
    incidents: new Map(),
    surfaces: [],
    watch: { window_s: WATCH_WINDOW_S, observed: 0, cleared: 0, escalated: 0, handed_off: 0 },
    lastBriefing: null,
  };
}

export class CybertroicStore {
  private tenants = new Map<string, TenantState>();

  private ensure(tenant: string): TenantState {
    let st = this.tenants.get(tenant);
    if (!st) {
      st = emptyTenant();
      this.tenants.set(tenant, st);
    }
    return st;
  }

  /** Record one observed event in the Sentry watch tick. `escalated` ⇒ it climbed the ladder. */
  observe(tenant: string, escalated: boolean): void {
    const w = this.ensure(tenant).watch;
    w.observed += 1;
    if (escalated) w.escalated += 1;
    else w.cleared += 1;
  }

  /** Idempotent upsert of an escalated incident (the deterministic id is the dedup key). */
  upsertIncident(tenant: string, incident: SecurityIncident): void {
    const st = this.ensure(tenant);
    const existing = st.incidents.get(incident.id);
    // Preserve human-driven status progression: never regress a remediating/contained incident
    // back to triage just because the same signal re-fired (idempotency over a live book).
    if (existing && INCIDENT_STATUS_FLOW.indexOf(existing.status) > INCIDENT_STATUS_FLOW.indexOf(incident.status)) {
      st.incidents.set(incident.id, { ...incident, status: existing.status });
    } else {
      st.incidents.set(incident.id, incident);
    }
    if (!existing) st.watch.handed_off += 1; // a genuinely NEW incident reached the desk
  }

  /** Advance an incident's status (server /v1/contain seam). Returns the updated incident or null. */
  setStatus(tenant: string, id: string, status: SecurityIncident['status']): SecurityIncident | null {
    const st = this.ensure(tenant);
    const inc = st.incidents.get(id);
    if (!inc) return null;
    const updated = { ...inc, status };
    st.incidents.set(id, updated);
    return updated;
  }

  setSurfaces(tenant: string, surfaces: PostureSurface[]): void {
    this.ensure(tenant).surfaces = surfaces;
  }

  setBriefing(tenant: string, briefing: GuardianBriefing): void {
    this.ensure(tenant).lastBriefing = briefing;
  }

  lastBriefing(tenant: string): GuardianBriefing | null {
    return this.ensure(tenant).lastBriefing;
  }

  incidents(tenant: string): SecurityIncident[] {
    return [...this.ensure(tenant).incidents.values()].sort((a, b) => {
      const s = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
      if (s !== 0) return s;
      return Date.parse(b.opened_at) - Date.parse(a.opened_at);
    });
  }

  surfaces(tenant: string): PostureSurface[] {
    return this.ensure(tenant).surfaces;
  }

  watch(tenant: string): WatchTick {
    return this.ensure(tenant).watch;
  }

  /** The authoritative guardian snapshot the panel reads (getCybertroicState()). */
  state(tenant: string): CybertroicState {
    const incidents = this.incidents(tenant);
    return {
      tenant,
      threatLevel: threatLevel(incidents),
      surfaces: this.surfaces(tenant),
      incidents,
      watch: this.watch(tenant),
    };
  }
}

/** Headline threat level from the open book (mirrors _rules.ts threatVerdict tiers). */
export function threatLevel(incidents: SecurityIncident[]): CyberThreatLevel {
  const open = incidents.filter((i) => i.status !== 'resolved' && i.status !== 'contained');
  const openCritical = open.filter((i) => i.severity === 'critical').length;
  const openWarning = open.filter((i) => i.severity === 'warning').length;
  if (openCritical > 0) return 'critical';
  if (openWarning >= 2) return 'active';
  if (openWarning === 1) return 'elevated';
  return 'calm';
}
