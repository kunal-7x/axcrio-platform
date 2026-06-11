/**
 * Tenants HTTP surface (maps to contracts/openapi/tenants.yaml).
 *   GET  /me/permissions
 *   GET/POST /workspaces ; GET/PATCH /workspaces/{id}
 *   GET /workspaces/{id}/members ; PATCH/DELETE /workspaces/{id}/members/{memberId}
 *   POST /workspaces/{id}/invites
 *   GET /entitlements
 */
import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  ForbiddenException,
  Get,
  HttpCode,
  NotFoundException,
  Param,
  Patch,
  Post,
  Query,
} from '@nestjs/common';
import type { Role } from '@growth-os/auth';
import { Auth } from '../../common/auth.guard.js';
import type { RequestContext } from '../../common/request-context.js';
import { TenantsError, TenantsService } from './tenants.service.js';

const ROLES: Role[] = ['Owner', 'Admin', 'Marketer', 'Analyst', 'Approver'];

@Controller()
export class TenantsController {
  constructor(private readonly tenants: TenantsService) {}

  @Get('me/permissions')
  getMyPermissions(@Auth() ctx: RequestContext, @Query('workspace_id') workspaceId?: string) {
    return this.tenants.getMyPermissions(ctx.auth, workspaceId);
  }

  @Get('workspaces')
  async listWorkspaces(@Auth() ctx: RequestContext, @Query('limit') limit?: string) {
    const items = await wrap(() => this.tenants.listWorkspaces(ctx.auth, clampLimit(limit)));
    return { items, next_cursor: null };
  }

  @Post('workspaces')
  @HttpCode(201)
  async createWorkspace(
    @Auth() ctx: RequestContext,
    @Body() body: { name?: string; industry_pack_id?: string; locale?: string },
  ) {
    if (!body?.name) throw new BadRequestException(err('validation_failed', 'name is required'));
    return wrap(() =>
      this.tenants.createWorkspace(ctx.auth, {
        name: body.name!,
        ...(body.industry_pack_id ? { industry_pack_id: body.industry_pack_id } : {}),
        ...(body.locale ? { locale: body.locale } : {}),
      }),
    );
  }

  @Get('workspaces/:id')
  async getWorkspace(@Auth() ctx: RequestContext, @Param('id') id: string) {
    const ws = await wrap(() => this.tenants.getWorkspace(ctx.auth, id));
    if (!ws) throw new NotFoundException(err('not_found', 'workspace not found'));
    return ws;
  }

  @Patch('workspaces/:id')
  async updateWorkspace(
    @Auth() ctx: RequestContext,
    @Param('id') id: string,
    @Body() body: { name?: string; industry_pack_id?: string; locale?: string },
  ) {
    return wrap(() => this.tenants.updateWorkspace(ctx.auth, id, body ?? {}));
  }

  @Get('workspaces/:id/members')
  async listMembers(@Auth() ctx: RequestContext, @Param('id') id: string, @Query('limit') limit?: string) {
    const items = await wrap(() => this.tenants.listMembers(ctx.auth, id, clampLimit(limit)));
    return { items, next_cursor: null };
  }

  @Patch('workspaces/:id/members/:memberId')
  async updateMemberRole(
    @Auth() ctx: RequestContext,
    @Param('id') id: string,
    @Param('memberId') memberId: string,
    @Body() body: { role?: string },
  ) {
    if (!body?.role || !ROLES.includes(body.role as Role)) {
      throw new BadRequestException(err('validation_failed', 'valid role is required'));
    }
    return wrap(() => this.tenants.updateMemberRole(ctx.auth, id, memberId, body.role as Role));
  }

  @Delete('workspaces/:id/members/:memberId')
  @HttpCode(204)
  async removeMember(@Auth() ctx: RequestContext, @Param('id') id: string, @Param('memberId') memberId: string) {
    await wrap(() => this.tenants.removeMember(ctx.auth, id, memberId));
  }

  @Post('workspaces/:id/invites')
  @HttpCode(201)
  async createInvite(
    @Auth() ctx: RequestContext,
    @Param('id') id: string,
    @Body() body: { email?: string; role?: string },
  ) {
    if (!body?.email) throw new BadRequestException(err('validation_failed', 'email is required'));
    if (!body?.role || !ROLES.includes(body.role as Role)) {
      throw new BadRequestException(err('validation_failed', 'valid role is required'));
    }
    return wrap(() => this.tenants.createInvite(ctx.auth, id, { email: body.email!, role: body.role as Role }));
  }

  @Get('entitlements')
  async getEntitlements(@Auth() ctx: RequestContext) {
    return wrap(() => this.tenants.getEntitlements(ctx.auth));
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
    if (e instanceof TenantsError) {
      if (e.code === 'forbidden') throw new ForbiddenException(err('forbidden', e.message));
      if (e.code === 'not_found') throw new NotFoundException(err('not_found', e.message));
      if (e.code === 'validation_failed') throw new BadRequestException(err('validation_failed', e.message));
      throw new BadRequestException(err(e.code, e.message));
    }
    throw e;
  }
}
