/**
 * Span helpers for HTTP + bus instrumentation (BUILD-SPEC P10).
 *
 * The event bus carries the W3C `traceparent` inside the envelope (set by createEnvelope on
 * publish). On the consumer side, `continueFromEnvelope` re-establishes that context so the
 * consume span is a CHILD of the publish span — a single trace stitches across the async bus
 * hop (publish HTTP request -> bus -> consumer -> ledger write all in ONE trace).
 */

import {
  context,
  propagation,
  trace,
  SpanKind,
  SpanStatusCode,
  type Span,
  type Context,
  type Tracer,
} from '@opentelemetry/api';
import { getTracer } from './tracing.js';

/** A minimal carrier just holding a W3C traceparent (matches the envelope `trace` shape). */
export interface TraceCarrier {
  traceparent?: string;
  tracestate?: string;
}

/**
 * Run `fn` inside a new span, recording exceptions + setting status. The span ends when `fn`
 * settles. Returns whatever `fn` returns. This is the one wrapper used across HTTP handlers,
 * bus publish, bus consume, and the ledger write so RED metrics + traces are uniform.
 */
export async function withSpan<T>(
  name: string,
  fn: (span: Span) => Promise<T> | T,
  opts: { kind?: SpanKind; attributes?: Record<string, string | number | boolean>; tracer?: Tracer; parent?: Context } = {},
): Promise<T> {
  const tracer = opts.tracer ?? getTracer();
  const parent = opts.parent ?? context.active();
  const span = tracer.startSpan(name, { kind: opts.kind ?? SpanKind.INTERNAL, attributes: opts.attributes }, parent);
  const spanCtx = trace.setSpan(parent, span);
  try {
    const result = await context.with(spanCtx, () => fn(span));
    span.setStatus({ code: SpanStatusCode.OK });
    return result;
  } catch (err) {
    span.recordException(err as Error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
    throw err;
  } finally {
    span.end();
  }
}

/** Inject the active trace context INTO a carrier (e.g. envelope.trace) before publishing. */
export function injectTraceContext(carrier: TraceCarrier = {}): TraceCarrier {
  propagation.inject(context.active(), carrier, {
    set: (c, k, v) => {
      (c as Record<string, string>)[k] = v;
    },
  });
  return carrier;
}

/** Extract a Context from a carrier (e.g. envelope.trace) — the parent for the consume span. */
export function extractTraceContext(carrier: TraceCarrier | undefined): Context {
  if (!carrier) return context.active();
  return propagation.extract(context.active(), carrier, {
    keys: (c) => Object.keys(c as Record<string, string>),
    get: (c, k) => (c as Record<string, string>)[k],
  });
}

/**
 * Consumer-side: run a handler span as a child of the publishing span carried on the
 * envelope's `trace.traceparent`. This is what makes ONE trace span the bus hop.
 */
export async function continueFromEnvelope<T>(
  envelope: { type: string; trace?: TraceCarrier; tenant_id: string; correlation_id: string },
  name: string,
  fn: (span: Span) => Promise<T> | T,
): Promise<T> {
  const parent = extractTraceContext(envelope.trace);
  return withSpan(
    name,
    fn,
    {
      kind: SpanKind.CONSUMER,
      parent,
      attributes: {
        'messaging.system': 'kafka',
        'messaging.operation': 'process',
        'event.type': envelope.type,
        'growthos.tenant_id': envelope.tenant_id,
        'growthos.correlation_id': envelope.correlation_id,
      },
    },
  );
}
