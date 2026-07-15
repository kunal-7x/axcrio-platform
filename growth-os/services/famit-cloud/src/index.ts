/**
 * Famit Cloud entrypoint.  pnpm --filter @growth-os/famit-cloud serve
 * Wires the store + runtimes (process + container) + quota + supervisor + control-plane facade,
 * starts the 24/7 reconcile loop, and boots the cloud API.
 */
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { initTracing } from '@growth-os/otel';
import { WorkloadStore } from './store.js';
import { Supervisor } from './supervisor.js';
import { QuotaManager } from './quota.js';
import { FamitCloud } from './cloud.js';
import { ProcessRunner } from './process-runner.js';
import { DockerRunner } from './docker-runner.js';
import { FileSystem } from './filesystem.js';
import { FsAi } from './fs-ai.js';
import { Catalog } from './catalog.js';
import { Resources } from './resources.js';
import { FeedbackHub } from './feedback.js';
import { ConnectorCatalog } from './connector-catalog.js';
import { Connectors } from './connectors.js';
import { AgentRuntime } from './agent-runtime.js';
import { makeOriginPush } from './origin-push.js';
import { Secrets } from './secrets.js';
import { makeNatsSink } from './nats-sink.js';
import { Billing } from './metering.js';
import { FilePersistence } from './persistence.js';
import { buildCloudServer } from './server.js';
import { FAMIT_CLOUD_ENV, IS_PROD } from './shared.js';
import type { Phase, RuntimeKind, WorkloadSpec as WorkloadSpecType } from './types.js';
import type { WorkloadRunner } from './runner.js';

export type { WorkloadSpec, Workload, RunInfo, WorkloadKind, RuntimeKind, Phase } from './types.js';
export { FamitCloud, CloudError } from './cloud.js';
export { Supervisor } from './supervisor.js';
export { WorkloadStore } from './store.js';
export { QuotaManager } from './quota.js';
export { MockRunner } from './runner.js';
export type { WorkloadRunner, RunnerHandle, RunnerStatus } from './runner.js';
export { ProcessRunner } from './process-runner.js';
export { DockerRunner } from './docker-runner.js';
export { FileSystem } from './filesystem.js';
export { FsAi } from './fs-ai.js';
export { Catalog } from './catalog.js';
export { Resources } from './resources.js';
export { FeedbackHub } from './feedback.js';
export type { FeedbackRecord, FeedbackStatus, HubKind, RlDomain } from './feedback.js';
export { ConnectorCatalog } from './connector-catalog.js';
export type { ConnectorTemplate, ConnectorKind, ConnectorDirection } from './connector-catalog.js';
export { Connectors } from './connectors.js';
export type { ConnectorState, ConnectorRun, ConnectorMode, OriginEvent } from './connectors.js';
export { AgentRuntime } from './agent-runtime.js';
export type { AgentInstance, AgentTickResult } from './agent-runtime.js';
export { makeOriginPush } from './origin-push.js';
export { Secrets, isSealed, isVaultRef } from './secrets.js';
export { Billing } from './metering.js';
export type { UsageKind, TenantUsage, MeterSink, GateResult } from './metering.js';
export { FilePersistence, MemoryPersistence } from './persistence.js';
export type { Persistence, CloudState } from './persistence.js';
export type { AgentTemplate, DbEngine, DomainTld, HostingPlan } from './catalog.js';
export type { Resource, ResourceType } from './resources.js';
export type { FileEntry, FileContent, FileKind } from './types.js';
export { buildCloudServer } from './server.js';

async function main(): Promise<void> {
  // Fail-closed: the cloud trusts `x-famit-internal` as proof a request came through the panel proxy.
  // Booting in production without it would let the gate dev-allow every request.
  if (IS_PROD && !FAMIT_CLOUD_ENV.internalToken) {
    throw new Error('CLOUD_INTERNAL_TOKEN must be set in production (the proxy-auth shared secret)');
  }

  initTracing({ serviceName: 'growth-os-famit-cloud' });

  const store = new WorkloadStore({ runHistoryMax: FAMIT_CLOUD_ENV.runHistoryMax, runTtlMs: FAMIT_CLOUD_ENV.runTtlMs });
  const runners = new Map<RuntimeKind, WorkloadRunner>([
    ['process', new ProcessRunner({ stopGraceMs: FAMIT_CLOUD_ENV.processStopGraceMs })],
    ['container', new DockerRunner('docker', FAMIT_CLOUD_ENV.instanceId)],
  ]);
  const quota = new QuotaManager({ maxConcurrentPerTenant: FAMIT_CLOUD_ENV.maxConcurrentPerTenant });
  const supervisor = new Supervisor(store, runners, quota);
  // `persist` is assigned the real durable-save closure once persistence + all planes exist below;
  // wiring it via a thunk lets workload mutations persist immediately (ack'd state is durable).
  let persist: () => void = () => {};
  const cloud = new FamitCloud(store, supervisor, { onChange: () => persist() });
  const filesystem = new FileSystem({ root: FAMIT_CLOUD_ENV.fsRoot, maxFileBytes: FAMIT_CLOUD_ENV.maxFileBytes, maxTenantBytes: FAMIT_CLOUD_ENV.maxTenantBytes });
  const catalog = new Catalog();

  // Shared envelope-encryption for secret material at rest (connector keys + DB passwords).
  const secrets = new Secrets();
  // Money meter + pre-spend budget gate (P4). Drive AI + provisioning bill through this.
  // The NATS sink fans every metered event onto famit.usage.<kind>.v1 -> famit-billing.
  const billing = new Billing({ sink: makeNatsSink() });
  const fsAi = new FsAi(filesystem, { billing });

  // --- Feedback fabric + EnterpriseConnect + agentic runtime (the "powerful agentic cloud") ---
  const feedback = new FeedbackHub();
  const connectorCatalog = new ConnectorCatalog();
  const connectors = new Connectors(connectorCatalog, { feedback, originPush: makeOriginPush(), media: filesystem }, { secrets });
  const agents = new AgentRuntime({ feedback, fs: filesystem, billing });

  const resources = new Resources(
    catalog,
    {
      createWorkload: (spec) => cloud.createWorkload(spec),
      delete: (id) => cloud.delete(id),
      teardown: (id) => cloud.teardown(id),
      phaseOf: (id) => cloud.get(id)?.phase,
    },
    {
      secrets,
      billing,
      // Deprovisioning an agent stops its runtime loop — no orphaned ticks (or spend) after teardown.
      onAgentDeprovisioned: (id) => agents.remove(id),
      // Provisioning an agent in the Marketplace spins up a REAL autonomous loop (not a sleep stub).
      // register() self-schedules; a failure is reported to Security rather than silently swallowed.
      onAgentProvisioned: (spec) => {
        void agents.register(spec).catch((err) => {
          void feedback
            .reportSecurity({
              eventType: 'cloud.agent.register_failed',
              tenantId: spec.tenantId,
              workspaceId: spec.tenantId,
              correlationId: spec.id,
              causationId: spec.id,
              occurredAt: new Date().toISOString(),
              source: 'famit-cloud',
              facts: { agent: spec.agentId, error: String(err).slice(0, 200), threat_hint: 'availability' },
            })
            .catch(() => null);
        });
      },
    },
  );

  // --- Boot recovery: durable state survives restarts (the prerequisite for 24/7 autonomy) ---
  const persistence = new FilePersistence(FAMIT_CLOUD_ENV.stateFile);
  // Clear cloud-managed containers left over from a previous run so we don't orphan/port-collide.
  // (Named volumes are kept — database DATA survives; the supervisor re-attaches them on restart.)
  const pruned = await DockerRunner.pruneManaged('docker', FAMIT_CLOUD_ENV.instanceId);
  const saved = persistence.load();
  if (saved) {
    // Rehydrate DESIRED state; reset transient fields so the supervisor starts fresh runs cleanly.
    const now = new Date().toISOString();
    store.hydrate(
      saved.workloads.map((w) => ({ ...w, phase: 'pending' as Phase, restarts: 0, lastExitAtMs: undefined, updatedAt: now })),
    );
    resources.hydrate(saved.resources);
    if (saved.connectors) connectors.hydrate(saved.connectors);
    if (saved.agents) agents.hydrate(saved.agents);
  } else {
    // FIRST boot (no durable state): reconcile the declarative standing fleet into existence so a
    // fresh box comes up running its baseline workloads unattended.
    const fleetCount = bootstrapFleet(cloud);
    if (fleetCount > 0) console.log(`[famit-cloud] standing fleet: created ${fleetCount} workloads from manifest`);
  }

  supervisor.start(FAMIT_CLOUD_ENV.reconcileEveryMs);
  // Readiness flips true after the first reconcile pass — orchestrators gate traffic on /v1/readyz
  // so a restarting cloud isn't handed work before it has rehydrated + converged once.
  let ready = false;
  void supervisor
    .reconcile()
    .catch(() => undefined)
    .finally(() => {
      ready = true;
    });
  // The EnterpriseConnect + agentic loops run on their own in-process schedulers — rehydrated above,
  // they resume 24/7 after a restart (the same durability story as workloads).
  connectors.startScheduler();
  agents.startScheduler();
  void feedback.probe();

  // Coalesced durable snapshot — only writes when state actually changed. Called both on a timer
  // (catches resource/connector/agent drift) and synchronously on each workload mutation (onChange).
  let lastSnap = '';
  const saveNow = (): void => {
    const snapshot = { workloads: store.all(), resources: resources.snapshot(), connectors: connectors.snapshot(), agents: agents.snapshot() };
    const json = JSON.stringify(snapshot);
    if (json !== lastSnap) {
      try {
        persistence.save(snapshot);
        lastSnap = json;
      } catch {
        /* a transient FS error must not stall the control plane */
      }
    }
  };
  persist = saveNow; // from here, cloud mutations persist immediately
  const snapTimer = setInterval(saveNow, FAMIT_CLOUD_ENV.snapshotEveryMs);
  if (typeof snapTimer.unref === 'function') snapTimer.unref();

  const server = buildCloudServer({ cloud, fs: filesystem, fsAi, catalog, resources, connectors, connectorCatalog, agents, feedback, billing, ready: () => ready });

  // Graceful 24/7 shutdown: stop the loops, flush a final snapshot (no lost create/scale), close the
  // server. A bounded fallback guarantees the process exits even if a handle hangs.
  let shuttingDown = false;
  const shutdown = (signal: string): void => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`[famit-cloud] ${signal} received — draining + flushing state`);
    clearInterval(snapTimer);
    supervisor.stop();
    connectors.stopScheduler();
    agents.stopScheduler();
    try {
      saveNow();
    } catch {
      /* best-effort final flush */
    }
    server.close(() => process.exit(0));
    const t = setTimeout(() => process.exit(0), 5000);
    if (typeof t.unref === 'function') t.unref();
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  server.listen(FAMIT_CLOUD_ENV.port, FAMIT_CLOUD_ENV.bind, () => {
    const fb = feedback.status();
    console.log(
      `[famit-cloud] up on :${FAMIT_CLOUD_ENV.port}/v1 (reconcile ${FAMIT_CLOUD_ENV.reconcileEveryMs}ms; runtimes: process, container; max ${FAMIT_CLOUD_ENV.maxConcurrentPerTenant}/tenant; fs ${FAMIT_CLOUD_ENV.fsRoot}; ai ${fsAi.enabled() ? 'live' : 'offline'}; catalog ${catalog.agentCount()} agents + ${connectorCatalog.count()} connectors; agents ${agents.enabled() ? 'reasoning' : 'deterministic'}; feedback→[security ${fb.security.configured ? 'cfg' : 'default'}, rl ${fb.rl.configured ? 'cfg' : 'default'}, optimizer ${fb.optimizer.configured ? 'cfg' : 'default'}]; durable ${FAMIT_CLOUD_ENV.stateFile} — recovered ${saved?.workloads.length ?? 0} workloads + ${saved?.resources.length ?? 0} resources + ${saved?.connectors?.length ?? 0} connectors + ${saved?.agents?.length ?? 0} agents, pruned ${pruned} stale containers)`,
    );
  });
}

/** Reconcile the declarative standing-fleet manifest into the store on first boot. The manifest is a
 *  JSON array of WorkloadSpec, provided inline (FAMIT_CLOUD_FLEET='[…]') or as a file path. Malformed
 *  or invalid specs are skipped (logged) rather than crashing boot. Returns the count created. */
function bootstrapFleet(cloud: FamitCloud): number {
  const src = FAMIT_CLOUD_ENV.fleet.trim();
  if (!src) return 0;
  let raw = src;
  try {
    if (!src.startsWith('[') && existsSync(src)) raw = readFileSync(src, 'utf8');
    const specs = JSON.parse(raw) as unknown;
    if (!Array.isArray(specs)) return 0;
    let n = 0;
    for (const spec of specs) {
      try {
        cloud.createWorkload(spec as WorkloadSpecType);
        n++;
      } catch (err) {
        console.warn('[famit-cloud] fleet: skipped an invalid workload spec:', (err as Error).message);
      }
    }
    return n;
  } catch (err) {
    console.warn('[famit-cloud] fleet: could not parse FAMIT_CLOUD_FLEET:', (err as Error).message);
    return 0;
  }
}

/** Robust "is this file the entrypoint?" — handles a relative argv (node src/index.ts) + symlinks
 *  (e.g. macOS /tmp) by comparing real, absolute paths. The naive `file://${argv[1]}` check fails
 *  when argv[1] is relative (which `pnpm serve` produces). */
function isEntrypoint(): boolean {
  const arg = process.argv[1];
  if (!arg) return false;
  try {
    return realpathSync(arg) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}
if (isEntrypoint()) {
  main().catch((err) => {
    console.error('[famit-cloud] failed to start:', err);
    process.exit(1);
  });
}
