/**
 * HelloSaga activities (BUILD-SPEC §7.8, §10.2 LaunchSaga pattern).
 *
 * Activities are where side effects happen (workflows must stay deterministic). The HelloSaga
 * activities are a tiny proof of the REAL pattern the Phase-1 LaunchSaga uses:
 *   - a forward step that produces an effect (here: emit a canonical event to the bus), and
 *   - a COMPENSATION step that undoes it if a later step fails (here: emit a compensating
 *     event). §10.2: "adset fails -> pause + tag orphan, never half-live spend."
 *
 * Activities run in the worker's Node context (NOT the workflow sandbox), so they can use the
 * event bus + OTel directly. This is also the seam where Temporal meets the event backbone:
 * a durable workflow drives the loop by emitting/consuming canonical envelopes (P2).
 */

import { createEnvelope, createEventBus, type EventBus } from '@growth-os/events';
import { withSpan, SpanKind } from '@growth-os/otel';

export interface GreetInput {
  tenant_id: string;
  workspace_id: string;
  correlation_id: string;
  name: string;
}

// One bus per worker process (in-memory on the laptop; Kafka on the box). Lazily created so
// importing the activity module for typecheck doesn't construct a producer.
let _bus: EventBus | undefined;
function bus(): EventBus {
  if (!_bus) _bus = createEventBus();
  return _bus;
}

/**
 * Forward step: emit a `campaign.requested` envelope (the journey root of the core loop, §3.1).
 * In Phase 0 this proves a durable workflow can drive the event backbone. Returns the event_id
 * so the workflow can pass it as the causation/compensation handle.
 */
export async function emitCampaignRequested(input: GreetInput): Promise<{ event_id: string }> {
  return withSpan(
    'activity.emitCampaignRequested',
    async () => {
      const env = createEnvelope({
        type: 'campaign.requested',
        tenant_id: input.tenant_id,
        workspace_id: input.workspace_id,
        correlation_id: input.correlation_id,
        idempotency_key: `hellosaga:${input.correlation_id}:campaign.requested`,
        actor: { kind: 'system', id: 'temporal:HelloSaga' },
        payload: {
          campaign_request_id: input.correlation_id,
          objective: 'leads',
          requested_by: input.name,
        },
      });
      await bus().publish(env);
      return { event_id: env.event_id };
    },
    { kind: SpanKind.PRODUCER, attributes: { 'event.type': 'campaign.requested' } },
  );
}

/**
 * Compensation step: emit a `campaign.paused`-shaped compensating fact. (Phase 0 reuses the
 * optimization.decision envelope to record "rolled back" without a dedicated schema — extend
 * never mutate §6.2; a real campaign.paused arrives Phase 1.) Demonstrates the saga rollback.
 */
export async function compensateCampaignRequested(input: GreetInput, causedBy: string): Promise<void> {
  await withSpan(
    'activity.compensateCampaignRequested',
    async () => {
      const env = createEnvelope({
        type: 'optimization.decision',
        tenant_id: input.tenant_id,
        workspace_id: input.workspace_id,
        correlation_id: input.correlation_id,
        causation_id: causedBy,
        idempotency_key: `hellosaga:${input.correlation_id}:compensate`,
        actor: { kind: 'system', id: 'temporal:HelloSaga' },
        payload: {
          scope: 'campaign',
          platform_ref: `growthos:campaign:${input.correlation_id}`,
          decision: 'trash',
          rule: 'saga_compensation',
          explanation: {
            summary_en: 'HelloSaga compensation: a later step failed, rolling back the request.',
            evidence: [],
            confidence: 'high',
            reversible: true,
            undo_plan: 'no-op (demo compensation)',
          },
        },
      });
      await bus().publish(env);
    },
    { kind: SpanKind.PRODUCER, attributes: { 'event.type': 'optimization.decision', saga: 'compensation' } },
  );
}

/** A trivial pure-ish activity: returns a greeting (the "hello" half of HelloSaga). */
export async function greet(input: GreetInput): Promise<string> {
  return `hello ${input.name} (journey ${input.correlation_id})`;
}
