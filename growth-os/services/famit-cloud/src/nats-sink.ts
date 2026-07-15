// nats-sink — the MeterSink that publishes every metered event onto the canonical
// famit.usage.<kind>.v1 seam (NATS/JetStream), so cloud-plane's LLM/agent/resource spend
// meters into famit-billing exactly like the organs. Best-effort: connects lazily, never
// throws into the caller. Dormant when NATS_URL is unset (the in-memory rollup still holds).
import { connect, type NatsConnection } from 'nats';
import type { MeterSink } from './metering.js';

const USAGE_PREFIX = (process.env.NATS_USAGE_PREFIX ?? 'famit.usage').replace(/\.+$/, '');
const enc = new TextEncoder();

export function makeNatsSink(url = process.env.NATS_URL ?? ''): MeterSink | undefined {
  if (!url) return undefined;
  let nc: NatsConnection | null = null;
  let connecting: Promise<void> | null = null;

  const ensure = async (): Promise<void> => {
    if (nc) return;
    if (!connecting) {
      connecting = connect({ servers: url, name: 'cloud-plane-usage', maxReconnectAttempts: -1 })
        .then((c) => {
          nc = c;
        })
        .catch((e: unknown) => {
          console.warn('[usage-sink] NATS connect failed:', String(e));
          connecting = null;
        });
    }
    await connecting;
  };

  const sink: MeterSink = {
    async record(e): Promise<void> {
      try {
        await ensure();
        if (!nc) return;
        const envelope = {
          event_id: e.idempotencyKey, // UUID from Billing.meter() — the dedup key
          event_type: `usage.${e.kind}.v1`,
          schema_version: 1,
          occurred_at: e.occurredAt,
          tenant_id: e.tenantId,
          producer: 'cloud-plane',
          payload: { quantity: e.quantity, cost_minor: e.costMinor, ...(e.dimensions ?? {}) },
        };
        nc.publish(`${USAGE_PREFIX}.${e.kind}.v1`, enc.encode(JSON.stringify(envelope)));
      } catch (err: unknown) {
        console.warn('[usage-sink] publish failed:', String(err));
      }
    },
  };
  return sink;
}
