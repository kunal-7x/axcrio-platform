/**
 * GROWTH OS event-type <-> topic registry (BUILD-SPEC §6.2).
 *
 * Generated-by-hand-but-pinned-to-contracts: the values here MUST match
 * `contracts/registry/event-backbone.index.json` (the canonical topic map) and
 * `contracts/asyncapi/bus.yaml`. Each event type carries:
 *   - its dotted `type` (selects the payload schema by `<type>.schema.json`)
 *   - its bus `topic` (`plane.entity.verb`, §6.2)
 *   - its pinned payload schema `version`.
 *
 * Frozen-after-merge (D7): extend-never-mutate. Adding an event = append a row.
 */

export interface EventTypeDef {
  /** Canonical dotted event type (matches the payload schema $id stem). */
  readonly type: string;
  /** Kafka/Redpanda topic, `plane.entity.verb` (§6.2). */
  readonly topic: string;
  /** Pinned payload schema version (semver). */
  readonly version: string;
}

/**
 * The 15 core events + the 4 engagement-core events (Origin Connector domain).
 * Source of truth: contracts/registry/event-backbone.index.json.
 */
export const EVENT_TYPES = {
  'campaign.requested': { type: 'campaign.requested', topic: 'campaign.lifecycle.requested', version: '1.0.0' },
  'research.completed': { type: 'research.completed', topic: 'campaign.research.completed', version: '1.0.0' },
  'strategy.compiled': { type: 'strategy.compiled', topic: 'campaign.strategy.compiled', version: '1.0.0' },
  'campaign.compiled': { type: 'campaign.compiled', topic: 'campaign.lifecycle.compiled', version: '1.0.0' },
  'campaign.launched': { type: 'campaign.launched', topic: 'campaign.lifecycle.launched', version: '1.0.0' },
  'creative.generated': { type: 'creative.generated', topic: 'creative.creative.generated', version: '1.0.0' },
  'creative.qa.evaluated': { type: 'creative.qa.evaluated', topic: 'creative.qa.evaluated', version: '1.0.0' },
  'action.plan.created': { type: 'action.plan.created', topic: 'activation.action_plan.created', version: '1.0.0' },
  'action.plan.signed': { type: 'action.plan.signed', topic: 'activation.action_plan.signed', version: '1.0.0' },
  'action.executed': { type: 'action.executed', topic: 'activation.action_plan.executed', version: '1.0.0' },
  'ad.metrics.snapshot': { type: 'ad.metrics.snapshot', topic: 'metrics.ad.snapshot', version: '1.0.0' },
  'lead.captured': { type: 'lead.captured', topic: 'data.lead.captured', version: '1.0.0' },
  'lead.scored': { type: 'lead.scored', topic: 'data.lead.scored', version: '1.0.0' },
  'signal.dispatched': { type: 'signal.dispatched', topic: 'signals.signal.dispatched', version: '1.0.0' },
  'optimization.decision': { type: 'optimization.decision', topic: 'metrics.optimization.decision', version: '1.0.0' },
  'call.completed': { type: 'call.completed', topic: 'engagement.call.completed', version: '1.0.0' },
  'call.outcome': { type: 'call.outcome', topic: 'engagement.call.outcome', version: '1.0.0' },
  'wa.message.sent': { type: 'wa.message.sent', topic: 'engagement.wa.message.sent', version: '1.0.0' },
  'wa.message.received': { type: 'wa.message.received', topic: 'engagement.wa.message.received', version: '1.0.0' },
} as const satisfies Record<string, EventTypeDef>;

/** Union of all canonical event type strings. */
export type EventType = keyof typeof EVENT_TYPES;

/** Resolve the bus topic for a known event type (throws on unknown — fail-closed). */
export function topicForType(type: EventType): string {
  const def = EVENT_TYPES[type];
  if (!def) throw new Error(`unknown event type (no topic mapping): ${String(type)}`);
  return def.topic;
}

/** The pinned payload-schema version for a known event type. */
export function versionForType(type: EventType): string {
  const def = EVENT_TYPES[type];
  if (!def) throw new Error(`unknown event type (no version): ${String(type)}`);
  return def.version;
}

/** Type guard: is this string one of the canonical event types? */
export function isKnownEventType(type: string): type is EventType {
  return Object.prototype.hasOwnProperty.call(EVENT_TYPES, type);
}
