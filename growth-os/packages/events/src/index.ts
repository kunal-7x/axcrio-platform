/**
 * @growth-os/events — the typed event backbone (BUILD-SPEC §6, P1/P2/P3).
 *
 * Public surface: the canonical envelope type, the createEnvelope builder, the
 * event-type/topic registry, the schema validator, and the EventBus port (in-memory
 * for Phase-0 dev + Kafka for the box). Services import ONLY from here.
 */
export type {
  ActorKind,
  Actor,
  TraceContext,
  EventEnvelope,
  EnvelopeInput,
} from './envelope.js';

export { createEnvelope } from './create-envelope.js';

export {
  idempotencyKey,
  signalEventId,
  sourceIdempotencyKey,
  IdempotencyGuard,
} from './idempotency.js';

export {
  EVENT_TYPES,
  topicForType,
  versionForType,
  isKnownEventType,
} from './topics.js';
export type { EventType, EventTypeDef } from './topics.js';

// Generated typed-payload layer (codegen from contracts/schemas — P1). Complements topics.ts:
// topics.ts is the runtime topic/version registry; catalog.ts adds payload TYPES per event so
// producers/consumers get end-to-end type safety (TypedEnvelope<'lead.scored'> etc.).
export { EVENT_CATALOG, ALL_EVENT_TYPES } from './generated/catalog.js';
export type {
  EventMeta,
  PayloadByType,
  TypedEnvelope,
  AnyEvent,
} from './generated/catalog.js';
export type * from './generated/payloads.js';

export {
  EventValidator,
  getEventValidator,
  OffContractEventError,
  assertOnContract,
} from './validator.js';
export type {
  EnvelopeValidationResult,
  EnvelopeValidationOk,
  EnvelopeValidationError,
} from './validator.js';

export {
  InMemoryEventBus,
  KafkaEventBus,
  createEventBus,
  topicFor,
} from './bus.js';
export type { EventBus, EventHandler } from './bus.js';
