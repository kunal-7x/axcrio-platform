/**
 * Billing-stub HTTP surface (§7.5, D6). Phase 0: read the per-tenant consumption summary
 * only. No money endpoints exist (structurally impossible in Phase 0).
 */
import { Controller, Get } from '@nestjs/common';
import { Auth } from '../../common/auth.guard.js';
import type { RequestContext } from '../../common/request-context.js';
import { BillingService } from './billing.service.js';

@Controller()
export class BillingController {
  constructor(private readonly billing: BillingService) {}

  @Get('billing/consumption')
  async consumption(@Auth() ctx: RequestContext): Promise<{ items: Record<string, unknown>[] }> {
    const items = await this.billing.summary(ctx.auth);
    return { items };
  }
}
