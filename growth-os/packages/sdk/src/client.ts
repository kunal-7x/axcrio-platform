/**
 * GROWTH OS SDK — minimal typed fetch client.
 *
 * Phase-0 stub: a thin wrapper that carries the bearer/service token + base URL and exposes a
 * typed `request`. Per-surface typed methods are layered on top of the generated `paths` types
 * (packages/sdk/src/generated, produced by `pnpm codegen:sdk` from contracts/openapi/*).
 *
 * Auth (D5, §5.2): Phase-0 dev JWT for user calls; `serviceToken` (Bearer) for the Origin
 * Connector + service-to-service. Tenant is resolved server-side from the token, never sent in
 * the body (P6). This client therefore never accepts a tenant_id argument.
 */

export interface SdkOptions {
  /** Base URL of the API gateway / surface, e.g. http://localhost:8080 */
  baseUrl: string;
  /** Bearer token (dev JWT or service token). */
  token?: string;
  /** Optional fetch override (tests / non-browser runtimes). */
  fetch?: typeof fetch;
  /** Default request headers merged into every call. */
  headers?: Record<string, string>;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  /** Exactly-once key for mutations (P3). Sent as Idempotency-Key. */
  idempotencyKey?: string;
  headers?: Record<string, string>;
}

export class GrowthOsError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'GrowthOsError';
  }
}

export class GrowthOsClient {
  private readonly opts: Required<Pick<SdkOptions, 'baseUrl'>> & SdkOptions;
  private readonly doFetch: typeof fetch;

  constructor(opts: SdkOptions) {
    this.opts = opts;
    this.doFetch = opts.fetch ?? globalThis.fetch;
    if (!this.doFetch) {
      throw new Error('No fetch available; pass opts.fetch on this runtime.');
    }
  }

  async request<T = unknown>(req: RequestOptions): Promise<T> {
    const url = new URL(req.path.replace(/^\//, ''), this.opts.baseUrl.replace(/\/?$/, '/'));
    for (const [k, v] of Object.entries(req.query ?? {})) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }

    const headers: Record<string, string> = {
      accept: 'application/json',
      ...this.opts.headers,
      ...req.headers,
    };
    if (this.opts.token) headers.authorization = `Bearer ${this.opts.token}`;
    if (req.idempotencyKey) headers['idempotency-key'] = req.idempotencyKey;
    if (req.body !== undefined) headers['content-type'] = 'application/json';

    const res = await this.doFetch(url.toString(), {
      method: req.method ?? 'GET',
      headers,
      body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
    });

    const text = await res.text();
    const data = text ? safeJson(text) : undefined;

    if (!res.ok) {
      const err = (data as { error?: { code?: string; message?: string } } | undefined)?.error;
      throw new GrowthOsError(
        res.status,
        err?.code ?? 'http_error',
        err?.message ?? `HTTP ${res.status}`,
        data,
      );
    }
    return data as T;
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
