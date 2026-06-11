/**
 * Ledger HTTP surface (maps 1:1 to contracts/openapi/ledger.yaml).
 *   POST /actions            proposeAction
 *   POST /actions/{id}/sign  signAction
 *   GET  /actions            listActions (?journey=&status=&target_ref=&action_type=&limit=)
 *   GET  /actions/{id}       getAction
 *   GET  /actions/verify     verifyChain
 *
 * Errors map LedgerError.code -> the canonical Error envelope + HTTP status (common.yaml).
 */
import {
  BadRequestException,
  Body,
  Controller,
  ForbiddenException,
  Get,
  Headers,
  HttpCode,
  NotFoundException,
  Param,
  Post,
  Query,
  UnprocessableEntityException,
} from '@nestjs/common';
import { Auth } from '../../common/auth.guard.js';
import type { RequestContext } from '../../common/request-context.js';
import { LedgerError, LedgerService } from './ledger.service.js';

interface ProposeBody {
  plan?: Record<string, unknown>;
}
interface SignBody {
  expected_hash?: string;
  step_up_token?: string | null;
  confirm_money?: boolean;
  note?: string | null;
}

@Controller()
export class LedgerController {
  constructor(private readonly ledger: LedgerService) {}

  @Post('actions')
  @HttpCode(201)
  async propose(
    @Auth() ctx: RequestContext,
    @Headers('idempotency-key') idemKey: string | undefined,
    @Body() body: ProposeBody,
  ): Promise<Record<string, unknown>> {
    if (!idemKey) throw new BadRequestException(err('validation_failed', 'Idempotency-Key header is required'));
    if (!body?.plan || typeof body.plan !== 'object') {
      throw new BadRequestException(err('validation_failed', 'body.plan is required'));
    }
    try {
      return await this.ledger.propose(ctx.auth, idemKey, body.plan);
    } catch (e) {
      throw mapError(e);
    }
  }

  // NOTE: declared BEFORE :id so '/actions/verify' isn't captured by the :id param route.
  @Get('actions/verify')
  async verify(@Auth() ctx: RequestContext): Promise<{
    ok: boolean;
    entries_checked: number;
    chain_head_hash: string | null;
    first_broken_id: string | null;
  }> {
    try {
      return await this.ledger.verify(ctx.auth);
    } catch (e) {
      throw mapError(e);
    }
  }

  @Get('actions')
  async list(
    @Auth() ctx: RequestContext,
    @Query('journey') journey?: string,
    @Query('status') status?: string,
    @Query('target_ref') targetRef?: string,
    @Query('action_type') actionType?: string,
    @Query('limit') limit?: string,
  ): Promise<{ items: Record<string, unknown>[]; chain_head_hash: string | null; next_cursor: null }> {
    const lim = clampLimit(limit);
    try {
      const res = await this.ledger.list(ctx.auth, {
        ...(journey ? { journey } : {}),
        ...(status ? { status } : {}),
        ...(targetRef ? { target_ref: targetRef } : {}),
        ...(actionType ? { action_type: actionType } : {}),
        limit: lim,
      });
      return { items: res.items, chain_head_hash: res.chain_head_hash, next_cursor: null };
    } catch (e) {
      throw mapError(e);
    }
  }

  @Get('actions/:id')
  async get(@Auth() ctx: RequestContext, @Param('id') id: string): Promise<Record<string, unknown>> {
    try {
      const entry = await this.ledger.get(ctx.auth, id);
      if (!entry) throw new NotFoundException(err('not_found', 'action not found'));
      return entry;
    } catch (e) {
      throw mapError(e);
    }
  }

  @Post('actions/:id/sign')
  async sign(
    @Auth() ctx: RequestContext,
    @Param('id') id: string,
    @Body() body: SignBody,
  ): Promise<Record<string, unknown>> {
    if (!body?.expected_hash) throw new BadRequestException(err('validation_failed', 'expected_hash is required'));
    try {
      return await this.ledger.sign(ctx.auth, id, {
        expected_hash: body.expected_hash,
        step_up_token: body.step_up_token ?? null,
        confirm_money: body.confirm_money ?? false,
        note: body.note ?? null,
      });
    } catch (e) {
      throw mapError(e);
    }
  }
}

function clampLimit(raw: string | undefined): number {
  const n = raw ? Number.parseInt(raw, 10) : 50;
  if (Number.isNaN(n)) return 50;
  return Math.min(200, Math.max(1, n));
}

function err(code: string, message: string): { error: { code: string; message: string } } {
  return { error: { code, message } };
}

function mapError(e: unknown): Error {
  if (e instanceof LedgerError) {
    switch (e.code) {
      case 'validation_failed':
        return new BadRequestException(err('validation_failed', e.message));
      case 'forbidden':
        return new ForbiddenException(err('forbidden', e.message));
      case 'not_found':
        return new NotFoundException(err('not_found', e.message));
      case 'conflict':
        return new UnprocessableEntityException(err('conflict', e.message));
      case 'unprocessable':
        return new UnprocessableEntityException(err('validation_failed', e.message));
      case 'db_unavailable':
        return new UnprocessableEntityException(err('db_unavailable', e.message));
    }
  }
  if (e instanceof BadRequestException || e instanceof NotFoundException || e instanceof ForbiddenException) {
    return e;
  }
  return e as Error;
}
