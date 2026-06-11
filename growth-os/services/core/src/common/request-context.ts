/**
 * Per-request context derived from the verified token (P6). Attached to the Fastify
 * request by AuthGuard; read by controllers/services via the @Auth() param decorator.
 * Tenant + workspace come from the TOKEN, never the request body.
 */
import type { AuthContext } from '@growth-os/auth';

export interface RequestContext {
  auth: AuthContext;
  /** Per-request id for trace correlation (P10), echoed as X-Request-Id. */
  requestId: string;
}

/** The shape we attach to FastifyRequest. */
export interface AuthedRequest {
  growthos?: RequestContext;
  headers: Record<string, string | string[] | undefined>;
}
