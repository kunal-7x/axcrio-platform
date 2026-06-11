/**
 * AuthGuard + tenant-resolution (BUILD-SPEC §7.1, D5, P6).
 *
 * Verifies the Bearer token via the TokenVerifier (Phase-0 dev JWT stub; OIDC later),
 * builds the AuthContext, and pins it on the request as `growthos`. Downstream code reads
 * tenant_id/workspace_id from there — NEVER from the body. Routes opt out with @Public().
 */
import {
  CanActivate,
  ExecutionContext,
  Injectable,
  SetMetadata,
  UnauthorizedException,
  createParamDecorator,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { randomUUID } from 'node:crypto';
import { AuthError, type TokenVerifier } from '@growth-os/auth';
import type { AuthedRequest, RequestContext } from './request-context.js';

export const IS_PUBLIC_KEY = 'growthos:isPublic';
/** Mark a route handler/controller as not requiring auth (health, dev-token mint). */
export const Public = (): MethodDecorator & ClassDecorator => SetMetadata(IS_PUBLIC_KEY, true);

/** DI token for the verifier so the OIDC impl can swap in later (D5). */
export const TOKEN_VERIFIER = Symbol('TOKEN_VERIFIER');

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private readonly reflector: Reflector,
    private readonly verifier: TokenVerifier,
  ) {}

  async canActivate(ctx: ExecutionContext): Promise<boolean> {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      ctx.getHandler(),
      ctx.getClass(),
    ]);
    const req = ctx.switchToHttp().getRequest<AuthedRequest>();
    const requestId = headerValue(req.headers['x-request-id']) ?? randomUUID();

    if (isPublic) {
      // Public routes still get a requestId for tracing; no auth context.
      return true;
    }

    const token = extractBearer(req.headers['authorization']);
    if (!token) throw new UnauthorizedException({ error: { code: 'unauthorized', message: 'missing bearer token' } });

    try {
      const auth = await this.verifier.verify(token);
      const context: RequestContext = { auth, requestId };
      req.growthos = context;
      return true;
    } catch (err) {
      if (err instanceof AuthError) {
        throw new UnauthorizedException({ error: { code: 'unauthorized', message: err.message } });
      }
      throw new UnauthorizedException({ error: { code: 'unauthorized', message: 'token verification failed' } });
    }
  }
}

function extractBearer(header: string | string[] | undefined): string | null {
  const h = headerValue(header);
  if (!h) return null;
  const m = /^Bearer\s+(.+)$/i.exec(h);
  return m && m[1] ? m[1].trim() : null;
}

function headerValue(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v;
}

/** @Auth() — inject the resolved RequestContext into a controller method. */
export const Auth = createParamDecorator((_data: unknown, ctx: ExecutionContext): RequestContext => {
  const req = ctx.switchToHttp().getRequest<AuthedRequest>();
  if (!req.growthos) {
    throw new UnauthorizedException({ error: { code: 'unauthorized', message: 'no auth context' } });
  }
  return req.growthos;
});
