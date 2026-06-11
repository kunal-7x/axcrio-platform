/**
 * @growth-os/auth — auth interface + Phase-0 dev JWT stub (BUILD-SPEC D5, §7.1, P6).
 *
 * The whole platform resolves identity through ONE interface (TokenVerifier -> AuthContext).
 * Phase 0 = a symmetric (HS256) dev JWT minted + verified locally so the contract surface is
 * exercisable before OIDC. Phase 3 swaps the issuer to Logto OIDC behind the SAME interface
 * (asymmetric verify via JWKS) — no service code changes.
 *
 * THE LOAD-BEARING RULE (P6): tenant_id + workspace_id come from the verified TOKEN claims,
 * never from a request body. Services read AuthContext, not the raw request.
 */
import { SignJWT, jwtVerify, type JWTPayload } from 'jose';

export type Role = 'Owner' | 'Admin' | 'Marketer' | 'Analyst' | 'Approver';

/** The resolved identity context every request carries (OIDC-shaped). */
export interface AuthContext {
  /** Subject — the user id (uuid). */
  sub: string;
  /** Owning tenant (org) — from the token, never the body (P6). */
  tenant_id: string;
  /** Active workspace (vendor/brand) within the tenant. */
  workspace_id: string;
  /** The caller's role in the active workspace. */
  role: Role;
  /** Token issuer (dev-stub or, later, the OIDC issuer URL). */
  iss: string;
  /** Expiry (epoch seconds). */
  exp?: number;
}

/** Claims we mint/expect. Mirrors gateway.yaml /auth/token response `claims`. */
export interface DevTokenClaims {
  sub: string;
  tenant_id: string;
  workspace_id: string;
  role: Role;
}

/** The interface services depend on (OIDC impl slots in here in Phase 3). */
export interface TokenVerifier {
  /** Verify a bearer token, returning the AuthContext or throwing AuthError. */
  verify(token: string): Promise<AuthContext>;
}

export class AuthError extends Error {
  readonly code = 'unauthorized';
  constructor(message: string) {
    super(message);
    this.name = 'AuthError';
  }
}

const DEV_ISSUER = 'growth-os-dev';
const DEV_AUDIENCE = 'growth-os';

function devSecret(): Uint8Array {
  // Phase-0 ONLY: a fixed dev secret (overridable). NEVER used in prod — Phase 3 is asymmetric OIDC.
  const secret = process.env.AUTH_DEV_SECRET ?? 'growth-os-phase0-dev-secret-not-for-prod';
  return new TextEncoder().encode(secret);
}

/**
 * Phase-0 dev token verifier (HS256). Implements TokenVerifier so the rest of the platform
 * is issuer-agnostic. The presence of this stub is gated to non-prod by the gateway.
 */
export class DevJwtVerifier implements TokenVerifier {
  async verify(token: string): Promise<AuthContext> {
    let payload: JWTPayload;
    try {
      const res = await jwtVerify(token, devSecret(), {
        issuer: DEV_ISSUER,
        audience: DEV_AUDIENCE,
      });
      payload = res.payload;
    } catch (err) {
      throw new AuthError(`invalid dev token: ${(err as Error).message}`);
    }
    const tenant_id = asString(payload.tenant_id, 'tenant_id');
    const workspace_id = asString(payload.workspace_id, 'workspace_id');
    const sub = asString(payload.sub, 'sub');
    const role = asRole(payload.role);
    return {
      sub,
      tenant_id,
      workspace_id,
      role,
      iss: DEV_ISSUER,
      ...(typeof payload.exp === 'number' ? { exp: payload.exp } : {}),
    };
  }
}

/** Mint a Phase-0 dev JWT (used by the gateway /auth/token stub). */
export async function mintDevToken(
  claims: DevTokenClaims,
  ttlSeconds = 3600,
): Promise<{ access_token: string; expires_in: number }> {
  const now = Math.floor(Date.now() / 1000);
  const access_token = await new SignJWT({
    tenant_id: claims.tenant_id,
    workspace_id: claims.workspace_id,
    role: claims.role,
  })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(claims.sub)
    .setIssuer(DEV_ISSUER)
    .setAudience(DEV_AUDIENCE)
    .setIssuedAt(now)
    .setExpirationTime(now + ttlSeconds)
    .sign(devSecret());
  return { access_token, expires_in: ttlSeconds };
}

function asString(v: unknown, field: string): string {
  if (typeof v !== 'string' || v.length === 0) {
    throw new AuthError(`token missing claim: ${field}`);
  }
  return v;
}

const ROLES: ReadonlySet<string> = new Set<Role>(['Owner', 'Admin', 'Marketer', 'Analyst', 'Approver']);
function asRole(v: unknown): Role {
  if (typeof v !== 'string' || !ROLES.has(v)) {
    throw new AuthError(`token has invalid role: ${String(v)}`);
  }
  return v as Role;
}

export const DEV_TOKEN_ISSUER = DEV_ISSUER;
