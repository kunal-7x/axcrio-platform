/**
 * @growth-os/otel — OpenTelemetry bootstrap + span helpers (BUILD-SPEC P10).
 *
 * Services/workers call `initTracing({serviceName})` once at startup, then wrap HTTP handlers,
 * bus publish/consume, and ledger writes in `withSpan` / `continueFromEnvelope`. Dev uses the
 * console exporter (trace visible on stdout — Phase-0 acceptance); the box swaps to OTLP.
 */
export { initTracing, getTracer, shutdownTracing } from './tracing.js';
export type { OtelInitOptions } from './tracing.js';

export {
  withSpan,
  injectTraceContext,
  extractTraceContext,
  continueFromEnvelope,
} from './spans.js';
export type { TraceCarrier } from './spans.js';

export { SpanKind, SpanStatusCode } from '@opentelemetry/api';
export type { Span } from '@opentelemetry/api';
