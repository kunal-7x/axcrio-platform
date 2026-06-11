import { describe, it, expect } from 'vitest';
import { trace, context } from '@opentelemetry/api';
import { initTracing, shutdownTracing } from './tracing.js';
import { withSpan, injectTraceContext, extractTraceContext, continueFromEnvelope } from './spans.js';

describe('@growth-os/otel', () => {
  it('initTracing is idempotent and yields a working tracer', async () => {
    const p1 = initTracing({ serviceName: 'test', exporter: 'none' });
    const p2 = initTracing({ serviceName: 'test', exporter: 'none' });
    expect(p1).toBe(p2); // same provider (idempotent)
    await shutdownTracing();
  });

  it('withSpan runs the fn inside an active span and propagates context to the bus carrier', async () => {
    initTracing({ serviceName: 'test', exporter: 'none' });
    let carrier: { traceparent?: string } = {};
    let traceIdInside = '';
    await withSpan('publish', async () => {
      traceIdInside = trace.getSpan(context.active())?.spanContext().traceId ?? '';
      carrier = injectTraceContext({});
    });
    // a traceparent was injected and embeds the same trace id (W3C: 00-<traceId>-<spanId>-<flags>)
    expect(carrier.traceparent).toBeDefined();
    expect(carrier.traceparent).toContain(traceIdInside);
    await shutdownTracing();
  });

  it('continueFromEnvelope makes the consume span a child of the publish span (one trace over the bus)', async () => {
    initTracing({ serviceName: 'test', exporter: 'none' });
    let publishTraceId = '';
    let consumeTraceId = '';
    const carrier: { traceparent?: string } = {};

    await withSpan('publish', async () => {
      publishTraceId = trace.getSpan(context.active())!.spanContext().traceId;
      injectTraceContext(carrier);
    });

    const envelope = {
      type: 'campaign.requested',
      tenant_id: 't',
      correlation_id: 'c',
      trace: carrier,
    };
    await continueFromEnvelope(envelope, 'consume', () => {
      consumeTraceId = trace.getSpan(context.active())!.spanContext().traceId;
    });

    expect(publishTraceId).toHaveLength(32);
    expect(consumeTraceId).toBe(publishTraceId); // same trace spans the bus hop (P10)
    await shutdownTracing();
  });

  it('extractTraceContext on an empty carrier returns the active context (no crash)', () => {
    expect(() => extractTraceContext(undefined)).not.toThrow();
  });
});
