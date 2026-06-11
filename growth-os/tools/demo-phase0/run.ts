/**
 * GROWTH OS — Phase-0 DEMO (BUILD-SPEC §21 Phase-0 acceptance; architecture-phase0.md §6).
 *
 *   pnpm demo:phase0
 *
 * Proves the rails end-to-end ON THE LAPTOP (no Docker, in-memory bus — D8):
 *   1. init OpenTelemetry with the console exporter (P10);
 *   2. publish a canonical `campaign.requested` envelope onto the bus INSIDE a publish span —
 *      the envelope carries the W3C traceparent so the trace propagates over the bus (§6.1);
 *   3. a CONSUMER receives it, continues the SAME trace (consume span = child of publish), and
 *      writes a hash-chained Action Ledger entry (§7.4) — "consumed → ledger entry";
 *   4. publish a second event so the ledger chain has >1 link;
 *   5. print the OTel trace (console exporter already streamed the spans) + the ledger hash
 *      chain + verify the chain is intact (tamper-evidence, §5.5).
 *
 * Every event is validated against the frozen JSON Schemas before it reaches the bus (P1) — an
 * off-contract event cannot complete the demo. This is the literal Phase-0 acceptance:
 * "demo publishes campaign.requested → consumed → ledger entry → trace visible."
 */

import { randomUUID } from 'node:crypto';
import {
  createEnvelope,
  InMemoryEventBus,
  topicFor,
  type EventEnvelope,
} from '@growth-os/events';
import {
  initTracing,
  shutdownTracing,
  withSpan,
  injectTraceContext,
  continueFromEnvelope,
  SpanKind,
} from '@growth-os/otel';
import { HashChainedLedger } from './ledger.js';

// uuidv7-shaped helper for the demo's tenant/workspace/journey ids (envelope wants real uuids).
const TENANT = '0190b3a1-7c2d-7abc-89ef-000000000001';
const WORKSPACE = '0190b3a1-7c2d-7abc-89ef-000000000002';

function line(label: string): void {
  console.log(`\n${'─'.repeat(4)} ${label} ${'─'.repeat(Math.max(0, 56 - label.length))}`);
}

async function main(): Promise<void> {
  line('1. OpenTelemetry (console exporter)');
  initTracing({ serviceName: 'demo-phase0', exporter: 'console' });
  console.log('   tracing initialized — spans below are real OTel spans printed by the console exporter.');

  const bus = new InMemoryEventBus();
  const ledger = new HashChainedLedger();

  line('2. CONSUMER subscribes (writes a ledger entry per event)');
  // The consumer continues the trace from the envelope, then writes a hash-chained ledger entry.
  const onEvent = async (env: EventEnvelope): Promise<void> => {
    await continueFromEnvelope(env, `consume ${env.type}`, async () => {
      const entry = ledger.append({
        action_type: `${env.type}.observed`,
        tenant_id: env.tenant_id,
        correlation_id: env.correlation_id,
        causation_event_id: env.event_id,
        explanation: {
          summary_en: `Observed ${env.type} on topic ${topicFor(env)} and recorded it to the ledger.`,
          evidence: [{ metric: 'event_id', value: env.event_id }],
        },
      });
      console.log(`   [consumer] ledger seq=${entry.sequence} hash=${entry.hash.slice(0, 16)}… (from ${env.type})`);
    });
  };
  bus.subscribe(['campaign.requested'], onEvent);
  bus.subscribe(['lead.captured'], onEvent);
  console.log('   subscribed to: campaign.requested, lead.captured');

  line('3. PUBLISH campaign.requested (inside a publish span)');
  const journey = randomUUID();
  await withSpan(
    'publish campaign.requested',
    async () => {
      const env = createEnvelope({
        type: 'campaign.requested',
        tenant_id: TENANT,
        workspace_id: WORKSPACE,
        correlation_id: journey,
        idempotency_key: `demo:${journey}:campaign.requested`,
        actor: { kind: 'user', id: 'demo-founder' },
        payload: {
          campaign_request_id: journey,
          objective: 'leads',
          business: { name: 'Demo Salon', industry_pack: 'salon', locale: 'en-IN', geo: 'Ahmedabad' },
          channels_hint: ['meta', 'whatsapp'],
          requested_by: 'demo-founder',
        },
      });
      // propagate the active trace onto the envelope so the consumer joins this trace over the bus
      env.trace = injectTraceContext(env.trace ?? {});
      console.log(`   publishing event_id=${env.event_id} topic=${topicFor(env)} traceparent=${env.trace.traceparent?.slice(0, 32)}…`);
      await bus.publish(env);
    },
    { kind: SpanKind.PRODUCER, attributes: { 'event.type': 'campaign.requested' } },
  );

  line('4. PUBLISH lead.captured (second chain link, same journey)');
  await withSpan(
    'publish lead.captured',
    async () => {
      const env = createEnvelope({
        type: 'lead.captured',
        tenant_id: TENANT,
        workspace_id: WORKSPACE,
        correlation_id: journey,
        idempotency_key: `demo:${journey}:lead.captured`,
        actor: { kind: 'webhook', id: 'origin' },
        payload: {
          lead_id: randomUUID(),
          person_hint: { phone: '+919900000000', name: 'Demo Lead' },
          source: { platform: 'meta', ctwa_clid: 'CTWA_demo_123' },
          destination: 'ctwa',
        },
      });
      env.trace = injectTraceContext(env.trace ?? {});
      console.log(`   publishing event_id=${env.event_id} topic=${topicFor(env)}`);
      await bus.publish(env);
    },
    { kind: SpanKind.PRODUCER, attributes: { 'event.type': 'lead.captured' } },
  );

  line('5. LEDGER hash chain');
  for (const e of ledger.all()) {
    console.log(
      `   seq=${e.sequence}  ${e.action_type.padEnd(28)}  prev=${e.prev_hash.slice(0, 12)}…  hash=${e.hash.slice(0, 12)}…`,
    );
  }
  const verified = ledger.verify();
  console.log(`\n   chain integrity: ${verified.ok ? 'OK (tamper-evident, §5.5)' : `BROKEN at seq ${verified.brokenAt}`}`);

  // Negative control: tamper with an entry and prove verify() catches it (the test has teeth).
  line('6. tamper test (negative control)');
  const tampered = new HashChainedLedger();
  tampered.append({
    action_type: 'a',
    tenant_id: TENANT,
    correlation_id: journey,
    explanation: { summary_en: 'first' },
  });
  tampered.append({
    action_type: 'b',
    tenant_id: TENANT,
    correlation_id: journey,
    explanation: { summary_en: 'second' },
  });
  // mutate the first entry's explanation AFTER the fact
  (tampered.all()[0] as { explanation: { summary_en: string } }).explanation.summary_en = 'HACKED';
  const tamperedResult = tampered.verify();
  console.log(`   after tampering seq 0: verify -> ${tamperedResult.ok ? 'OK (BAD — no teeth!)' : `BROKEN at seq ${tamperedResult.brokenAt} ✓`}`);

  await shutdownTracing();

  line('PHASE-0 DEMO COMPLETE');
  const allGood = verified.ok && !tamperedResult.ok && ledger.all().length === 2;
  console.log(
    `   published 2 events → consumed → ${ledger.all().length} ledger entries (chained) → trace printed above.\n` +
      `   acceptance: ${allGood ? 'PASS ✓' : 'FAIL ✗'}`,
  );
  if (!allGood) process.exit(1);
}

main().catch((err) => {
  console.error('[demo] FAILED:', err);
  process.exit(1);
});
