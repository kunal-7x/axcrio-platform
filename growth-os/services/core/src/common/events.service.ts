/**
 * EventsService — the core app's outbound event publisher (P2 event-sourced nervous system).
 *
 * Wraps @growth-os/events: builds a canonical envelope (createEnvelope) and publishes it on
 * the EventBus. Modules call emit() on every meaningful write (tenant.*, config.changed,
 * action.plan.created|signed, ...). The bus validates against the committed schemas before
 * anything goes on the wire. tenant_id/workspace_id come from the caller's AuthContext (P6).
 *
 * Phase-0 laptop: the bus is in-memory (D8) — no broker needed. The InMemoryEventBus keeps a
 * `published` log used by the demo + tests to prove the loop.
 */
import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import {
  createEnvelope,
  type Actor,
  type EventBus,
  type EventEnvelope,
} from '@growth-os/events';

export interface EmitInput {
  type: string;
  tenant_id: string;
  workspace_id: string;
  correlation_id: string;
  idempotency_key: string;
  actor: Actor;
  payload: Record<string, unknown>;
  causation_id?: string | null;
}

@Injectable()
export class EventsService implements OnModuleDestroy {
  constructor(private readonly bus: EventBus) {}

  /** Build + publish a canonical envelope. Returns the envelope (for the demo/SSE feed). */
  async emit(input: EmitInput): Promise<EventEnvelope> {
    const env = createEnvelope({
      type: input.type,
      tenant_id: input.tenant_id,
      workspace_id: input.workspace_id,
      correlation_id: input.correlation_id,
      idempotency_key: input.idempotency_key,
      actor: input.actor,
      payload: input.payload,
      causation_id: input.causation_id ?? null,
    });
    await this.bus.publish(env);
    return env;
  }

  /** Direct access to the bus (e.g. the gateway SSE feed subscribes to it). */
  getBus(): EventBus {
    return this.bus;
  }

  async onModuleDestroy(): Promise<void> {
    await this.bus.close();
  }
}
