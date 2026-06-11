/**
 * Flags / policy-config HTTP surface (maps to contracts/openapi/flags.yaml).
 *   GET/PUT /policy-config ; GET /policy-config/history
 *   GET /flags ; PUT /flags/{key}
 */
import {
  BadRequestException,
  Body,
  Controller,
  ForbiddenException,
  Get,
  Param,
  Put,
  Query,
} from '@nestjs/common';
import { Auth } from '../../common/auth.guard.js';
import type { RequestContext } from '../../common/request-context.js';
import { FlagsError, FlagsService } from './flags.service.js';

@Controller()
export class FlagsController {
  constructor(private readonly flags: FlagsService) {}

  @Get('policy-config')
  async getPolicyConfig(
    @Auth() ctx: RequestContext,
    @Query('workspace_id') workspaceId?: string,
    @Query('version') version?: string,
  ) {
    return wrap(() =>
      this.flags.getPolicyConfig(ctx.auth, workspaceId, version ? Number.parseInt(version, 10) : undefined),
    );
  }

  @Put('policy-config')
  async updatePolicyConfig(
    @Auth() ctx: RequestContext,
    @Body() body: Record<string, unknown>,
    @Query('workspace_id') workspaceId?: string,
  ) {
    return wrap(() => this.flags.updatePolicyConfig(ctx.auth, body ?? {}, workspaceId));
  }

  @Get('policy-config/history')
  async listVersions(
    @Auth() ctx: RequestContext,
    @Query('workspace_id') workspaceId?: string,
    @Query('limit') limit?: string,
  ) {
    const items = await wrap(() => this.flags.listVersions(ctx.auth, workspaceId, clampLimit(limit)));
    return { items, next_cursor: null };
  }

  @Get('flags')
  async listFlags(@Auth() ctx: RequestContext, @Query('workspace_id') workspaceId?: string) {
    return wrap(() => this.flags.listFlags(ctx.auth, workspaceId));
  }

  @Put('flags/:key')
  async setFlag(
    @Auth() ctx: RequestContext,
    @Param('key') key: string,
    @Body() body: { value?: boolean | string | number },
    @Query('workspace_id') workspaceId?: string,
  ) {
    if (body?.value === undefined) throw new BadRequestException(err('validation_failed', 'value is required'));
    return wrap(() => this.flags.setFlag(ctx.auth, key, body.value!, workspaceId));
  }
}

function clampLimit(raw: string | undefined): number {
  const n = raw ? Number.parseInt(raw, 10) : 50;
  if (Number.isNaN(n)) return 50;
  return Math.min(200, Math.max(1, n));
}

function err(code: string, message: string) {
  return { error: { code, message } };
}

async function wrap<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (e instanceof FlagsError) {
      if (e.code === 'forbidden') throw new ForbiddenException(err('forbidden', e.message));
      throw new BadRequestException(err(e.code, e.message));
    }
    throw e;
  }
}
