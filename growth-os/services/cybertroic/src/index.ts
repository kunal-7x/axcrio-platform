/**
 * Cybertroic entrypoint.  pnpm --filter @growth-os/cybertroic serve
 *
 * Boots the guardian HTTP surface (/v1) AND wires the always-on consumer onto the money/control
 * event backbone. In-memory bus on the laptop (no broker, no key) ⇒ the deterministic Sentry +
 * fakes run end-to-end. On a Kafka box the consumer joins its own group and the model client +
 * owner notifier light up from env.
 */
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { initTracing } from '@growth-os/otel';
import { createEventBus } from '@growth-os/events';
import { CybertroicConsumer, WATCHED_EVENTS } from './consumer.js';
import { CybertroicStore } from './store.js';
import { buildCybertroicServer } from './server.js';
import {
  HttpOwnerNotifier,
  HttpSecurityModelClient,
  InMemoryOwnerNotifier,
  InMemorySecurityModelClient,
  type OwnerNotifier,
  type SecurityModelClient,
} from './ports.js';
import { CYBERTROIC_ENV } from './shared.js';

// Public surface for embedders/tests.
export { CybertroicConsumer, WATCHED_EVENTS, sentryClassify, toSnapshot, buildIncident, buildBriefing, buildVulnIncident, vulnSeverity } from './consumer.js';
export { CybertroicStore, threatLevel } from './store.js';
export { buildCybertroicServer } from './server.js';
export {
  HttpSecurityModelClient,
  InMemorySecurityModelClient,
  HttpOwnerNotifier,
  InMemoryOwnerNotifier,
} from './ports.js';
export type {
  SecurityIncident,
  ThreatClass,
  IncidentStatus,
  ModelTier,
  PostureSurface,
  Severity,
  TriageVerdict,
  SentrySnapshot,
  GuardianBriefing,
  CybertroicState,
} from './types.js';

async function main(): Promise<void> {
  initTracing({ serviceName: 'growth-os-cybertroic' });
  const bus = createEventBus();
  const store = new CybertroicStore();

  // Tier-routed model client + owner notifier: HTTP on the box (key/webhook present), fakes else.
  const model: SecurityModelClient = CYBERTROIC_ENV.openRouterApiKey
    ? new HttpSecurityModelClient(CYBERTROIC_ENV.modelBaseUrl, CYBERTROIC_ENV.openRouterApiKey, {
        sentry: CYBERTROIC_ENV.sentryModel,
        investigator: CYBERTROIC_ENV.investigatorModel,
        specialist: CYBERTROIC_ENV.specialistModel,
      })
    : new InMemorySecurityModelClient();
  const notifier: OwnerNotifier = CYBERTROIC_ENV.ownerWebhookUrl
    ? new HttpOwnerNotifier(CYBERTROIC_ENV.ownerWebhookUrl)
    : new InMemoryOwnerNotifier();

  const consumer = new CybertroicConsumer({ bus, store, model, notifier });
  consumer.start();
  // Kafka: connect the consumer group + run the loop (watches the money/control topics). In-memory: no-op.
  await bus.start?.();

  const server = buildCybertroicServer({ store });
  server.listen(CYBERTROIC_ENV.port, '0.0.0.0', () => {
    console.log(
      `[cybertroic] guardian up on :${CYBERTROIC_ENV.port}/v1 — watching ${WATCHED_EVENTS.length} money/control event types ` +
        `(model=${CYBERTROIC_ENV.openRouterApiKey ? 'http' : 'fake'}, notifier=${CYBERTROIC_ENV.ownerWebhookUrl ? 'http' : 'fake'})`,
    );
  });
}

// Robust entrypoint check: resolve both sides to an absolute path so it fires whether run as
// `node dist/index.js`, `node --import tsx src/index.ts`, or with a relative arg.
const isEntrypoint = process.argv[1] !== undefined && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isEntrypoint) {
  main().catch((err) => {
    console.error('[cybertroic] failed to start:', err);
    process.exit(1);
  });
}
