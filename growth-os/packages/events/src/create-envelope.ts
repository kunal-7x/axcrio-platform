/**
 * createEnvelope — the ONE way to mint a canonical event envelope (BUILD-SPEC §6.1).
 *
 * Fills in the server-managed fields (event_id uuidv7, version from the type registry,
 * occurred_at, OTel trace context) and leaves the producer to supply the business fields.
 * The producer MUST supply idempotency_key consciously (P3 exactly-once is a decision).
 *
 * tenant_id / workspace_id are supplied by the caller but in services they come from the
 * AUTH CONTEXT, never a request body (P6) — this builder does not invent them.
 */
import { v7 as uuidv7 } from 'uuid';
import { context, trace } from '@opentelemetry/api';
import type { EventEnvelope, EnvelopeInput } from './envelope.js';
import { isKnownEventType, versionForType, type EventType } from './topics.js';

/** Build a fully-formed envelope from the producer-supplied input. */
export function createEnvelope<T = Record<string, unknown>>(input: EnvelopeInput<T>): EventEnvelope<T> {
  const version =
    input.version ?? (isKnownEventType(input.type) ? versionForType(input.type as EventType) : '1.0.0');

  const env: EventEnvelope<T> = {
    event_id: uuidv7(),
    type: input.type,
    version,
    occurred_at: input.occurred_at ?? new Date().toISOString(),
    tenant_id: input.tenant_id,
    workspace_id: input.workspace_id,
    correlation_id: input.correlation_id,
    causation_id: input.causation_id ?? null,
    actor: input.actor,
    idempotency_key: input.idempotency_key,
    payload: input.payload,
  };

  const traceparent = currentTraceparent();
  if (traceparent) env.trace = { traceparent };
  return env;
}

/** Best-effort W3C traceparent for the active span (P10 publish->consume continuity). */
function currentTraceparent(): string | undefined {
  const span = trace.getSpan(context.active());
  if (!span) return undefined;
  const sc = span.spanContext();
  if (!sc.traceId || !sc.spanId) return undefined;
  const flags = (sc.traceFlags & 0xff).toString(16).padStart(2, '0');
  return `00-${sc.traceId}-${sc.spanId}-${flags}`;
}
