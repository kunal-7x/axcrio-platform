/**
 * @growth-os/metering — per-tenant usage cost meters (P10 observable; §7.5 billing; §10).
 *
 * Phase-0 skeleton: the meter vocabulary + a recorder PORT. The concrete recorder (emit
 * `credit.consumed` onto the bus / write to ClickHouse cost meters) lands with billing + the
 * LLM gateway in later phases. Every metered unit is tenant-scoped (P6) and priced in INR paise
 * (mirrors the live wallet — integer paise, never floats).
 */

/** The billable resource classes (§7.5). */
export type MeterKind =
  | 'llm_tokens'
  | 'image_generations'
  | 'video_seconds'
  | 'wa_messages' // category in `dimensions.category`: marketing | utility | authentication
  | 'voice_minutes'
  | 'managed_ad_spend';

export interface MeterEvent {
  readonly tenantId: string;
  readonly workspaceId: string;
  readonly kind: MeterKind;
  /** Raw quantity in the meter's natural unit (tokens, count, seconds, minutes, paise). */
  readonly quantity: number;
  /** Cost attributed to this usage, in INR paise (integer). */
  readonly costMinor: number;
  /** Free-form dimensions for rollups (model, category, provider, correlation_id). */
  readonly dimensions?: Readonly<Record<string, string | number>>;
  /** Exactly-once key (P3) — dedup repeated meter writes. */
  readonly idempotencyKey: string;
  readonly occurredAt: string; // RFC3339
}

/** A sink for meter events. Phase-0 default = console; prod = bus -> billing. */
export interface MeterRecorder {
  record(event: MeterEvent): Promise<void>;
}

/** No-op/console recorder for dev + tests. Never throws. */
export class ConsoleMeterRecorder implements MeterRecorder {
  async record(event: MeterEvent): Promise<void> {
    console.debug('[meter]', event.kind, event.quantity, `${event.costMinor}p`, event.tenantId);
  }
}

/** Helper to assert a value is a non-negative integer paise amount (money is sacred, P4). */
export function assertPaise(value: number, label = 'amount'): number {
  if (!Number.isInteger(value) || value < 0) {
    throw new RangeError(`${label} must be a non-negative integer paise value, got ${value}`);
  }
  return value;
}
