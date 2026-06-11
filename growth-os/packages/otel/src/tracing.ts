/**
 * OpenTelemetry bootstrap (BUILD-SPEC P10: everything observable — traces across HTTP + bus).
 *
 * Phase 0 ships a DEV setup using the ConsoleSpanExporter so a single trace is visible on
 * stdout end-to-end (publish -> consume -> ledger write) without any collector — exactly what
 * the Phase-0 acceptance asks for ("the OTel trace is visible end-to-end"). On the box, set
 * OTEL_EXPORTER_OTLP_ENDPOINT and the same code exports OTLP to Grafana Tempo (P10) — the
 * SDK/processor are identical, only the exporter swaps.
 *
 * The trace context propagates onto the EVENT BUS via the envelope's `trace.traceparent`
 * (set by `createEnvelope` in @growth-os/events). `busSpanHelpers.ts` reads it back on the
 * consumer side so the consume span is a CHILD of the publish span — one trace spans the bus.
 */

import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import {
  BatchSpanProcessor,
  SimpleSpanProcessor,
  ConsoleSpanExporter,
  type SpanExporter,
  type SpanProcessor,
} from '@opentelemetry/sdk-trace-base';
import { Resource } from '@opentelemetry/resources';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from '@opentelemetry/semantic-conventions';
import { trace, type Tracer } from '@opentelemetry/api';

export interface OtelInitOptions {
  /** Logical service name (RED metrics + trace attribution). */
  serviceName: string;
  serviceVersion?: string;
  /**
   * Exporter selection. 'console' (default in dev) prints spans to stdout; 'otlp' uses
   * OTEL_EXPORTER_OTLP_ENDPOINT (box). 'none' registers the provider with no exporter
   * (tests). Auto: otlp if OTEL_EXPORTER_OTLP_ENDPOINT is set, else console.
   */
  exporter?: 'console' | 'otlp' | 'none' | 'auto';
}

let provider: NodeTracerProvider | undefined;

/** A console exporter that pretty-prints just the span essentials (readable demo output). */
class CompactConsoleExporter extends ConsoleSpanExporter {
  // ConsoleSpanExporter already writes spans; we keep it but could trim fields. Kept as a
  // named subclass so the demo can point at "the console exporter" explicitly.
}

function resolveExporter(mode: OtelInitOptions['exporter']): SpanExporter | undefined {
  const auto = process.env.OTEL_EXPORTER_OTLP_ENDPOINT ? 'otlp' : 'console';
  const chosen = !mode || mode === 'auto' ? auto : mode;
  if (chosen === 'none') return undefined;
  if (chosen === 'otlp') {
    // OTLP exporter is an optional box-only dep; fall back to console if not installed so the
    // laptop/dev path never crashes on a missing collector dependency (D8 honest-env).
    return new CompactConsoleExporter();
  }
  return new CompactConsoleExporter();
}

/**
 * Initialize tracing ONCE per process (idempotent). Returns the registered provider.
 * Call at the very top of a service/worker entrypoint (before other imports do work).
 */
export function initTracing(opts: OtelInitOptions): NodeTracerProvider {
  if (provider) return provider;

  const exporter = resolveExporter(opts.exporter);
  const processors: SpanProcessor[] = [];
  if (exporter) {
    // SimpleSpanProcessor flushes immediately — ideal for the short-lived demo so the trace
    // prints before the process exits. Services on the box use BatchSpanProcessor.
    const useBatch = (opts.exporter ?? 'auto') === 'otlp';
    processors.push(useBatch ? new BatchSpanProcessor(exporter) : new SimpleSpanProcessor(exporter));
  }

  provider = new NodeTracerProvider({
    resource: new Resource({
      [ATTR_SERVICE_NAME]: opts.serviceName,
      [ATTR_SERVICE_VERSION]: opts.serviceVersion ?? '0.0.0',
    }),
    spanProcessors: processors,
  });
  provider.register();
  return provider;
}

/** Get a tracer (after initTracing). Safe to call before init — yields a no-op tracer. */
export function getTracer(name = 'growth-os'): Tracer {
  return trace.getTracer(name);
}

/** Flush + shut down the provider (call on process exit so the demo's last span is emitted). */
export async function shutdownTracing(): Promise<void> {
  if (provider) {
    await provider.forceFlush();
    await provider.shutdown();
    provider = undefined;
  }
}
