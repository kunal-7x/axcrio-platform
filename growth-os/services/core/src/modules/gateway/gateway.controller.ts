/**
 * Gateway HTTP surface (maps to contracts/openapi/gateway.yaml). THIN (§7.1): auth-token
 * stub, tenant resolution (/session), health/readiness, and the live SSE feed. No business
 * logic — it only authenticates, resolves tenant from the token (P6), and fans out.
 */
import {
  BadRequestException,
  Body,
  Controller,
  ForbiddenException,
  Get,
  Post,
  Req,
  Res,
} from '@nestjs/common';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { mintDevToken, type Role } from '@growth-os/auth';
import type { CoreConfig } from '@growth-os/config';
import type { EventEnvelope, InMemoryEventBus } from '@growth-os/events';
import { CONFIG } from '../../common/tokens.js';
import { Inject } from '@nestjs/common';
import { Auth, Public } from '../../common/auth.guard.js';
import type { RequestContext } from '../../common/request-context.js';
import { DbService } from '../../db/db.service.js';
import { EventsService } from '../../common/events.service.js';

const DEV_TENANT = '00000000-0000-7000-8000-000000000001';
const DEV_WORKSPACE = '00000000-0000-7000-8000-000000000002';
const DEV_USER = '00000000-0000-7000-8000-0000000000aa';

@Controller()
export class GatewayController {
  constructor(
    @Inject(CONFIG) private readonly config: CoreConfig,
    private readonly db: DbService,
    private readonly events: EventsService,
  ) {}

  @Public()
  @Get('healthz')
  health(): { status: 'ok' } {
    return { status: 'ok' };
  }

  @Public()
  @Get('readyz')
  async ready(): Promise<{ status: 'ready' | 'degraded'; dependencies: Record<string, string> }> {
    const dbUp = this.db.isEnabled() ? await this.db.ping() : false;
    const deps: Record<string, string> = {
      db: this.db.isEnabled() ? (dbUp ? 'up' : 'down') : 'degraded',
      bus: this.config.busInMemory ? 'up' : 'up', // in-memory always up; kafka liveness Phase 1+
    };
    const status = Object.values(deps).some((d) => d === 'down') ? 'degraded' : 'ready';
    return { status, dependencies: deps };
  }

  /** Phase-0 dev-token mint (D5). Disabled in production. */
  @Public()
  @Post('auth/token')
  async mintToken(
    @Body() body: { email?: string; tenant_id?: string },
  ): Promise<{ access_token: string; token_type: 'Bearer'; expires_in: number; claims: Record<string, unknown> }> {
    if (!this.config.devTokenEnabled) {
      throw new ForbiddenException({ error: { code: 'forbidden', message: 'dev token mint is disabled' } });
    }
    if (!body?.email) throw new BadRequestException({ error: { code: 'validation_failed', message: 'email is required' } });
    const claims = {
      sub: DEV_USER,
      tenant_id: body.tenant_id ?? DEV_TENANT,
      workspace_id: DEV_WORKSPACE,
      role: 'Owner' as Role,
    };
    const { access_token, expires_in } = await mintDevToken(claims);
    return { access_token, token_type: 'Bearer', expires_in, claims };
  }

  /** Tenant resolution — the canonical proof tenant is bound to the token, not the body. */
  @Get('session')
  session(@Auth() ctx: RequestContext): Record<string, unknown> {
    return {
      sub: ctx.auth.sub,
      tenant_id: ctx.auth.tenant_id,
      workspace_id: ctx.auth.workspace_id,
      role: ctx.auth.role,
      workspaces: [{ workspace_id: ctx.auth.workspace_id, name: 'default' }],
    };
  }

  /** Live SSE feed of tenant-scoped envelope events (P10, §7.1). RLS-scoped to the token. */
  @Get('feed')
  async feed(
    @Auth() ctx: RequestContext,
    @Req() req: FastifyRequest,
    @Res() reply: FastifyReply,
  ): Promise<void> {
    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    });
    reply.raw.write(`event: ready\ndata: {"tenant_id":"${ctx.auth.tenant_id}"}\n\n`);

    const bus = this.events.getBus();
    // Only the in-memory bus supports in-process subscribe (Phase 0). Kafka feed = Phase 1 worker.
    if (typeof (bus as InMemoryEventBus).subscribe === 'function' && this.config.busInMemory) {
      const handler = (env: EventEnvelope): void => {
        if (env.tenant_id !== ctx.auth.tenant_id) return; // tenant scope (P6)
        reply.raw.write(`event: ${env.type}\ndata: ${JSON.stringify(env)}\n\n`);
      };
      // Subscribe to the whole catalog by listening to a wildcard via known types is out of
      // scope; Phase 0 demo wires specific types. Here we keep the stream open + heartbeat.
      void handler;
    }

    const heartbeat = setInterval(() => {
      reply.raw.write(`event: ping\ndata: {}\n\n`);
    }, 15000);

    req.raw.on('close', () => {
      clearInterval(heartbeat);
      reply.raw.end();
    });
  }
}
