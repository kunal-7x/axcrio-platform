/**
 * GROWTH OS event envelope (BUILD-SPEC §6.1).
 *
 * EVERY business fact on the bus is wrapped in this envelope (P2 event-sourced
 * nervous system). The shape here mirrors `contracts/schemas/event-envelope.schema.json`
 * EXACTLY — that JSON Schema is the source of truth (P1 contracts-first); this is its
 * hand-maintained TS face kept in lockstep. The validator (`validator.ts`) checks every
 * envelope against the schema at runtime, so a drift between this type and the schema is
 * caught the moment an event is emitted or consumed.
 *
 * Frozen-after-merge (D7): a new envelope field => contract version bump.
 */

/** Who/what produced an event — provenance for the Action Ledger + audit (P5). */
export type ActorKind = 'agent' | 'user' | 'system' | 'webhook';

export interface Actor {
  /**
   * agent  = an LLM / typed agent activity
   * user   = a human
   * system = an internal scheduler/service
   * webhook= an inbound external source (incl the Origin Connector, §3)
   */
  kind: ActorKind;
  /** Stable id of the actor within its kind (user uuid, service name, 'origin', 'meta'). */
  id: string;
}

/** Optional W3C trace propagation so one trace spans publish -> consume (P10). */
export interface TraceContext {
  traceparent?: string;
  tracestate?: string;
}

/**
 * The canonical envelope. `T` is the typed payload for a given `type`.
 * The concrete payload union per `type` lives in the generated `events.generated.ts`.
 */
export interface EventEnvelope<T = Record<string, unknown>> {
  /** UUIDv7 for THIS envelope (time-ordered: natural bus + ClickHouse ordering). */
  event_id: string;
  /** Canonical event type, dotted (e.g. `campaign.requested`). Selects the payload schema. */
  type: string;
  /** Semantic version of the PAYLOAD schema for this `type` (additive within a major). */
  version: string;
  /** RFC3339 UTC of when the business fact OCCURRED (not when published). */
  occurred_at: string;
  /** Owning tenant (org). MANDATORY (P6). Derived from token context, never caller body. */
  tenant_id: string;
  /** Owning workspace (vendor/brand) inside the tenant. MANDATORY (P6). */
  workspace_id: string;
  /** Journey id (§6.3): minted once at first touch, propagated through the whole journey. */
  correlation_id: string;
  /** event_id of the event/source that directly caused this one. Null only for journey roots. */
  causation_id?: string | null;
  /** Provenance (P5). */
  actor: Actor;
  /** Exactly-once key (P3). For externally-sourced events = the source system's own id. */
  idempotency_key: string;
  /** The type-specific business payload (validated by `<type>.schema.json`). */
  payload: T;
  /** Optional OTel propagation (P10). */
  trace?: TraceContext;
}

/**
 * The fields a producer must supply; the rest (`event_id`, `version`, `occurred_at`,
 * `trace`) are filled in by `createEnvelope` from the type registry + clock + active
 * OTel context. `idempotency_key` is REQUIRED from the caller (P3): exactly-once is a
 * decision the producer must make consciously (the source id, a deterministic hash, etc).
 */
export type EnvelopeInput<T = Record<string, unknown>> = {
  type: string;
  tenant_id: string;
  workspace_id: string;
  correlation_id: string;
  idempotency_key: string;
  actor: Actor;
  payload: T;
  causation_id?: string | null;
  /** Override the schema version (defaults to the registry's pinned version for `type`). */
  version?: string;
  /** Override occurred_at (defaults to now). Use the SOURCE time for externally-sourced facts. */
  occurred_at?: string;
};
