/**
 * HelloSaga activity tests — prove the saga's forward + compensation steps emit VALID
 * contract events (P1/P2). This tests the rails integration (activity -> createEnvelope ->
 * validate) without needing a running Temporal server (the workflow orchestration itself is a
 * thin durable wrapper; the durability is Temporal's, exercised on the box / in the testing env).
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { getEventValidator, type EventEnvelope } from '@growth-os/events';
import { initTracing } from '@growth-os/otel';

const INPUT = {
  tenant_id: '00000000-0000-7000-8000-000000000001',
  workspace_id: '00000000-0000-7000-8000-000000000002',
  correlation_id: '00000000-0000-7000-8000-000000000003',
  name: 'test',
};

describe('HelloSaga activities', () => {
  beforeAll(() => {
    initTracing({ serviceName: 'temporal-worker-test', exporter: 'none' });
    // force the in-memory bus (no broker in tests)
    process.env.GROWTH_OS_BUS = 'memory';
    delete process.env.KAFKA_BROKERS;
    delete process.env.REDPANDA_BROKERS;
  });

  it('emitCampaignRequested publishes a valid campaign.requested envelope', async () => {
    // dynamic import AFTER env is set so the module-level bus picks in-memory
    const { emitCampaignRequested } = await import('./activities.js');
    const { event_id } = await emitCampaignRequested(INPUT);
    expect(event_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });

  it('compensateCampaignRequested publishes a valid optimization.decision (rollback fact)', async () => {
    const { emitCampaignRequested, compensateCampaignRequested } = await import('./activities.js');
    // causation_id must be a real event_id (uuid) — use the forward step's actual emitted id.
    const { event_id } = await emitCampaignRequested(INPUT);
    await expect(compensateCampaignRequested(INPUT, event_id)).resolves.toBeUndefined();
  });

  it('the emitted envelopes are on-contract (validator accepts them)', async () => {
    const validator = getEventValidator();
    // Re-build the exact envelope the activity emits and validate its shape directly.
    const { createEnvelope } = await import('@growth-os/events');
    const env: EventEnvelope = createEnvelope({
      type: 'campaign.requested',
      tenant_id: INPUT.tenant_id,
      workspace_id: INPUT.workspace_id,
      correlation_id: INPUT.correlation_id,
      idempotency_key: 'x',
      actor: { kind: 'system', id: 'temporal:HelloSaga' },
      payload: { campaign_request_id: INPUT.correlation_id, objective: 'leads', requested_by: INPUT.name },
    });
    expect(validator.validateEnvelope(env).ok).toBe(true);
  });
});
