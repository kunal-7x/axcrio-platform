/**
 * Event bus port (BUILD-SPEC §6, P2 event-sourced nervous system).
 *
 * Services depend on the EventBus INTERFACE, never on Kafka/Redpanda directly. Two impls:
 *  - InMemoryEventBus: Phase-0 dev / tests / typecheck-only laptop (no broker needed).
 *  - KafkaEventBus: real Redpanda producer (kafkajs) — only constructed when a broker URL
 *    is present (box/CI). Kept import-light so the in-memory path needs no broker deps at runtime.
 *
 * Every publish validates the envelope against the committed schemas (P1) before it goes on
 * the wire — a malformed event never enters the bus. Topic is derived from the event type.
 */
import type { EventEnvelope } from './envelope.js';
import { isKnownEventType, topicForType, type EventType } from './topics.js';
import { getEventValidator, type EventValidator } from './validator.js';

/** A consumer handler. Return/throw semantics: throw => redelivery (at-least-once). */
export type EventHandler = (envelope: EventEnvelope) => void | Promise<void>;

export interface EventBus {
  /** Validate + publish an envelope to its derived topic. Rejects malformed events (P1). */
  publish(envelope: EventEnvelope): Promise<void>;
  /** Subscribe a handler to one or more event types (dev/in-memory wiring + tests). */
  subscribe(types: string[], handler: EventHandler): void;
  /** Flush + close any underlying producer. */
  close(): Promise<void>;
}

/** Resolve the topic for an envelope (known type => mapped topic; else the dotted type). */
export function topicFor(envelope: EventEnvelope): string {
  return isKnownEventType(envelope.type) ? topicForType(envelope.type as EventType) : envelope.type;
}

/**
 * In-memory bus: synchronous fan-out to subscribers. Validates every publish. Perfect for
 * Phase-0 (no broker on the laptop), unit tests, and the publish->consume->ledger demo.
 */
export class InMemoryEventBus implements EventBus {
  private readonly handlers = new Map<string, EventHandler[]>();
  /** Append-only log of everything published — handy for tests + the demo trace. */
  readonly published: EventEnvelope[] = [];

  constructor(private readonly validator: EventValidator = getEventValidator()) {}

  async publish(envelope: EventEnvelope): Promise<void> {
    const result = this.validator.validateEnvelope(envelope);
    if (!result.ok) {
      throw new Error(
        `InMemoryEventBus.publish: invalid envelope (${result.where}): ${result.errors.join('; ')}`,
      );
    }
    this.published.push(envelope);
    const handlers = this.handlers.get(envelope.type) ?? [];
    for (const h of handlers) {
      await h(envelope);
    }
  }

  subscribe(types: string[], handler: EventHandler): void {
    for (const t of types) {
      const list = this.handlers.get(t) ?? [];
      list.push(handler);
      this.handlers.set(t, list);
    }
  }

  async close(): Promise<void> {
    this.handlers.clear();
  }
}

/**
 * Kafka/Redpanda-backed bus (box/CI only). Lazily imports kafkajs so the in-memory path
 * never needs a broker. Validation still runs before every send (P1).
 */
export class KafkaEventBus implements EventBus {
  private producer: { send: (r: unknown) => Promise<unknown>; connect: () => Promise<void>; disconnect: () => Promise<void> } | null =
    null;
  private connected = false;

  constructor(
    private readonly brokers: string[],
    private readonly clientId = 'growth-os-core',
    private readonly validator: EventValidator = getEventValidator(),
  ) {}

  private async ensureProducer(): Promise<NonNullable<KafkaEventBus['producer']>> {
    if (this.producer && this.connected) return this.producer;
    // Dynamic import: kafkajs is only a hard dependency on the box.
    const { Kafka } = (await import('kafkajs')) as typeof import('kafkajs');
    const kafka = new Kafka({ clientId: this.clientId, brokers: this.brokers });
    const producer = kafka.producer({ idempotent: true });
    await producer.connect();
    this.producer = producer as unknown as NonNullable<KafkaEventBus['producer']>;
    this.connected = true;
    return this.producer;
  }

  async publish(envelope: EventEnvelope): Promise<void> {
    const result = this.validator.validateEnvelope(envelope);
    if (!result.ok) {
      throw new Error(
        `KafkaEventBus.publish: invalid envelope (${result.where}): ${result.errors.join('; ')}`,
      );
    }
    const producer = await this.ensureProducer();
    await producer.send({
      topic: topicFor(envelope),
      messages: [
        {
          // Partition by tenant so a tenant's journey stays ordered (P6 + §6.3).
          key: envelope.tenant_id,
          value: JSON.stringify(envelope),
          headers: {
            'event-type': envelope.type,
            'event-version': envelope.version,
            'idempotency-key': envelope.idempotency_key,
            ...(envelope.trace?.traceparent ? { traceparent: envelope.trace.traceparent } : {}),
          },
        },
      ],
    });
  }

  subscribe(): void {
    throw new Error('KafkaEventBus is producer-only here; consumers live in each service worker.');
  }

  async close(): Promise<void> {
    if (this.producer && this.connected) {
      await this.producer.disconnect();
      this.connected = false;
    }
  }
}

/**
 * Factory: pick the bus by env. KAFKA_BROKERS present => real producer; else in-memory.
 * Phase 0 on the laptop always lands on in-memory (no broker), which is correct (D8).
 */
export function createEventBus(): EventBus {
  const brokers = process.env.KAFKA_BROKERS ?? process.env.REDPANDA_BROKERS;
  if (brokers && process.env.GROWTH_OS_BUS !== 'memory') {
    return new KafkaEventBus(brokers.split(',').map((b) => b.trim()).filter(Boolean));
  }
  return new InMemoryEventBus();
}
