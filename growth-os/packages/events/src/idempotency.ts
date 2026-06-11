/**
 * Idempotency helpers (BUILD-SPEC P3: idempotency everywhere; §6.1 idempotency_key).
 *
 * Every external mutation + every event carries an idempotency key so the effect is
 * exactly-once and consumers are replay-safe. Two shapes are needed:
 *
 *  - SOURCE-DERIVED: when an event originates from an external system (Famit via the
 *    Origin Connector), the key IS that system's own event id — passed straight through.
 *    Do NOT synthesize a key in that case; use the source id so re-delivery dedups.
 *
 *  - DETERMINISTIC: when WE mint the fact (e.g. a signal.dispatched), the key is a stable
 *    hash of the journey-defining inputs, so re-emitting the same logical fact produces the
 *    SAME key. The flagship signal loop relies on this: §11.3 invariant
 *    `event_id = hash(journey_id + ladder_step)` => idempotent re-sends, dedup >= 90%.
 *
 * Uses Node's built-in crypto (no dependency); SHA-256 hex, matching the live platform's
 * hashing discipline (the live signals layer keys CAPI events the same way).
 */

import { createHash } from 'node:crypto';

/**
 * Deterministic idempotency key from ordered parts.
 * SHA-256 over the parts joined by a separator that cannot appear inside a normalized part.
 * Parts are normalized (trimmed, lowercased) so trivial formatting differences don't split
 * a logical event into two keys.
 *
 * @example
 *   // §11.3: same journey + same ladder step => same key => Meta dedups the CAPI send
 *   idempotencyKey('signal', journeyId, 'QualifiedLead')
 */
export function idempotencyKey(...parts: Array<string | number>): string {
  const normalized = parts.map((p) => String(p).trim().toLowerCase());
  const joined = normalized.join(''); // SOH — never present in a normalized token
  return createHash('sha256').update(joined, 'utf8').digest('hex');
}

/**
 * The flagship signal-ladder event id (§11.3 invariant): `hash(journey_id + ladder_step)`.
 * Returned as a hex digest; used both as the CAPI `event_id` AND the envelope
 * `idempotency_key` for signal events so a re-send is a guaranteed no-op platform-side.
 */
export function signalEventId(journeyId: string, ladderStep: string): string {
  return idempotencyKey('ladder', journeyId, ladderStep);
}

/**
 * Pass-through for externally-sourced facts (Origin Connector): the key IS the source id.
 * Kept as a named function so call sites are explicit that they are NOT minting a new key —
 * they are honoring the source system's exactly-once contract (§3.1 Idempotency-Key).
 */
export function sourceIdempotencyKey(sourceEventId: string): string {
  const trimmed = sourceEventId.trim();
  if (!trimmed) {
    throw new Error('sourceIdempotencyKey: empty source event id (P3 requires a stable key)');
  }
  return trimmed;
}

/**
 * In-memory dedup set for a single consumer process (best-effort replay safety at the app
 * layer; the durable dedup lives in each service's own write model keyed on
 * (tenant_id, type, idempotency_key)). Bounded LRU so a long-running consumer doesn't leak.
 */
export class IdempotencyGuard {
  private readonly seen = new Map<string, number>();
  private readonly max: number;

  constructor(max = 100_000) {
    this.max = max;
  }

  /** Returns true the FIRST time a (tenant,type,key) tuple is seen, false on replays. */
  firstSeen(tenantId: string, type: string, key: string): boolean {
    const composite = `${tenantId}${type}${key}`;
    if (this.seen.has(composite)) return false;
    this.seen.set(composite, Date.now());
    if (this.seen.size > this.max) {
      // drop oldest insertion (Map preserves insertion order)
      const oldest = this.seen.keys().next().value;
      if (oldest !== undefined) this.seen.delete(oldest);
    }
    return true;
  }

  get size(): number {
    return this.seen.size;
  }
}
