import { describe, it, expect } from 'vitest';
import { createEnvelope } from './create-envelope.js';
import { getEventValidator } from './validator.js';
import { InMemoryEventBus } from './bus.js';
import { topicForType } from './topics.js';

const TENANT = '00000000-0000-7000-8000-000000000001';
const WORKSPACE = '00000000-0000-7000-8000-000000000002';
const JOURNEY = '00000000-0000-7000-8000-000000000003';

function campaignRequestedPayload() {
  // Minimal shape that satisfies campaign.requested.schema.json required fields.
  return {
    campaign_request_id: '11111111-1111-7111-8111-111111111111',
    objective: 'leads',
    requested_by: 'user-1',
  };
}

describe('createEnvelope', () => {
  it('mints a uuidv7 event_id and pins version from the registry', () => {
    const env = createEnvelope({
      type: 'campaign.requested',
      tenant_id: TENANT,
      workspace_id: WORKSPACE,
      correlation_id: JOURNEY,
      idempotency_key: 'idem-1',
      actor: { kind: 'user', id: 'user-1' },
      payload: campaignRequestedPayload(),
    });
    expect(env.event_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(env.version).toBe('1.0.0');
    expect(env.causation_id).toBeNull();
    expect(env.occurred_at).toMatch(/T/);
  });
});

describe('EventValidator', () => {
  const v = getEventValidator();

  it('accepts a well-formed envelope', () => {
    const env = createEnvelope({
      type: 'campaign.requested',
      tenant_id: TENANT,
      workspace_id: WORKSPACE,
      correlation_id: JOURNEY,
      idempotency_key: 'idem-2',
      actor: { kind: 'user', id: 'user-1' },
      payload: campaignRequestedPayload(),
    });
    expect(v.validateEnvelope(env).ok).toBe(true);
  });

  it('rejects a missing tenant_id (P6)', () => {
    const env = createEnvelope({
      type: 'campaign.requested',
      tenant_id: TENANT,
      workspace_id: WORKSPACE,
      correlation_id: JOURNEY,
      idempotency_key: 'idem-3',
      actor: { kind: 'user', id: 'user-1' },
      payload: campaignRequestedPayload(),
    }) as Record<string, unknown>;
    delete env.tenant_id;
    const res = v.validateEnvelope(env);
    expect(res.ok).toBe(false);
  });

  it('rejects a non-uuidv7 event_id', () => {
    const env = createEnvelope({
      type: 'campaign.requested',
      tenant_id: TENANT,
      workspace_id: WORKSPACE,
      correlation_id: JOURNEY,
      idempotency_key: 'idem-4',
      actor: { kind: 'user', id: 'user-1' },
      payload: campaignRequestedPayload(),
    });
    env.event_id = 'not-a-uuid';
    expect(v.validateEnvelope(env).ok).toBe(false);
  });
});

describe('InMemoryEventBus', () => {
  it('validates, publishes to subscribers, and derives the topic', async () => {
    const bus = new InMemoryEventBus();
    const seen: string[] = [];
    bus.subscribe(['campaign.requested'], (e) => {
      seen.push(e.type);
    });
    const env = createEnvelope({
      type: 'campaign.requested',
      tenant_id: TENANT,
      workspace_id: WORKSPACE,
      correlation_id: JOURNEY,
      idempotency_key: 'idem-5',
      actor: { kind: 'user', id: 'user-1' },
      payload: campaignRequestedPayload(),
    });
    await bus.publish(env);
    expect(seen).toEqual(['campaign.requested']);
    expect(bus.published).toHaveLength(1);
    expect(topicForType('campaign.requested')).toBe('campaign.lifecycle.requested');
  });

  it('throws when publishing a malformed envelope', async () => {
    const bus = new InMemoryEventBus();
    await expect(bus.publish({ type: 'campaign.requested' } as never)).rejects.toThrow(/invalid envelope/);
  });
});
