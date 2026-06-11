/**
 * Notify HTTP surface (maps to contracts/openapi/notify.yaml).
 *   GET /notify/channels ; PUT /notify/channels/{channel}
 *   GET/POST /notify/templates
 *   POST /notify/send
 *   GET /notify/notifications
 *   GET/PUT /notify/preferences
 */
import {
  BadRequestException,
  Body,
  Controller,
  ForbiddenException,
  Get,
  Headers,
  HttpCode,
  Post,
  Put,
  Query,
} from '@nestjs/common';
import { Auth } from '../../common/auth.guard.js';
import type { RequestContext } from '../../common/request-context.js';
import { NotifyError, NotifyService } from './notify.service.js';

@Controller()
export class NotifyController {
  constructor(private readonly notify: NotifyService) {}

  @Get('notify/channels')
  listChannels(@Auth() ctx: RequestContext) {
    return wrap(() => this.notify.listChannels(ctx.auth));
  }

  @Get('notify/templates')
  async listTemplates(
    @Auth() ctx: RequestContext,
    @Query('channel') channel?: string,
    @Query('locale') locale?: string,
    @Query('limit') limit?: string,
  ) {
    const items = await wrap(() =>
      this.notify.listTemplates(ctx.auth, {
        ...(channel ? { channel } : {}),
        ...(locale ? { locale } : {}),
        limit: clampLimit(limit),
      }),
    );
    return { items, next_cursor: null };
  }

  @Post('notify/templates')
  @HttpCode(201)
  async createTemplate(
    @Auth() ctx: RequestContext,
    @Body() body: { key?: string; channel?: string; locale?: string; category?: string; body?: string; variables?: string[] },
  ) {
    if (!body?.key || !body?.channel || !body?.body) {
      throw new BadRequestException(err('validation_failed', 'key, channel and body are required'));
    }
    return wrap(() =>
      this.notify.createTemplate(ctx.auth, {
        key: body.key!,
        channel: body.channel!,
        body: body.body!,
        ...(body.locale ? { locale: body.locale } : {}),
        ...(body.category ? { category: body.category } : {}),
        ...(body.variables ? { variables: body.variables } : {}),
      }),
    );
  }

  @Post('notify/send')
  @HttpCode(202)
  async send(
    @Auth() ctx: RequestContext,
    @Headers('idempotency-key') idemKey: string | undefined,
    @Body() body: { channel?: string; to?: string; template_key?: string; locale?: string; variables?: Record<string, string>; priority?: string; action_ref?: string | null },
  ) {
    if (!idemKey) throw new BadRequestException(err('validation_failed', 'Idempotency-Key header is required'));
    if (!body?.channel || !body?.to || !body?.template_key) {
      throw new BadRequestException(err('validation_failed', 'channel, to and template_key are required'));
    }
    return wrap(() =>
      this.notify.send(ctx.auth, idemKey, {
        channel: body.channel!,
        to: body.to!,
        template_key: body.template_key!,
        ...(body.locale ? { locale: body.locale } : {}),
        ...(body.variables ? { variables: body.variables } : {}),
        ...(body.priority ? { priority: body.priority } : {}),
        action_ref: body.action_ref ?? null,
      }),
    );
  }

  @Get('notify/notifications')
  async listNotifications(@Auth() ctx: RequestContext, @Query('status') status?: string, @Query('limit') limit?: string) {
    const items = await wrap(() => this.notify.listNotifications(ctx.auth, status, clampLimit(limit)));
    return { items, next_cursor: null };
  }

  @Get('notify/preferences')
  getPreferences(@Auth() ctx: RequestContext) {
    return wrap(() => this.notify.getPreferences(ctx.auth));
  }

  @Put('notify/preferences')
  async updatePreferences(
    @Auth() ctx: RequestContext,
    @Body() body: { quiet_hours?: Record<string, unknown>; channel_prefs?: Record<string, unknown>; locale?: string },
  ) {
    if (!body?.quiet_hours || !body?.channel_prefs) {
      throw new BadRequestException(err('validation_failed', 'quiet_hours and channel_prefs are required'));
    }
    return wrap(() =>
      this.notify.updatePreferences(ctx.auth, {
        quiet_hours: body.quiet_hours!,
        channel_prefs: body.channel_prefs!,
        ...(body.locale ? { locale: body.locale } : {}),
      }),
    );
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
    if (e instanceof NotifyError) {
      if (e.code === 'forbidden') throw new ForbiddenException(err('forbidden', e.message));
      throw new BadRequestException(err(e.code, e.message));
    }
    throw e;
  }
}
