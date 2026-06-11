/**
 * AppModule — wires the ONE modular core app (D1): gateway + tenants + flags + ledger +
 * notify + billing-stub as internal modules. Provides the shared singletons (config, DB,
 * event bus, events publisher, contract validator, token verifier) and the GLOBAL AuthGuard
 * so every route is authenticated + tenant-resolved by default (P6); @Public() opts out.
 */
import { Global, Module, type Provider } from '@nestjs/common';
import { APP_GUARD, Reflector } from '@nestjs/core';
import { loadCoreConfig, type CoreConfig } from '@growth-os/config';
import { createEventBus, type EventBus } from '@growth-os/events';
import { DevJwtVerifier, type TokenVerifier } from '@growth-os/auth';

import { CONFIG, EVENT_BUS } from './common/tokens.js';
import { AuthGuard, TOKEN_VERIFIER } from './common/auth.guard.js';
import { DbService } from './db/db.service.js';
import { EventsService } from './common/events.service.js';
import { ContractValidator } from './common/contract-validator.js';

import { GatewayModule } from './modules/gateway/gateway.module.js';
import { TenantsModule } from './modules/tenants/tenants.module.js';
import { FlagsModule } from './modules/flags/flags.module.js';
import { LedgerModule } from './modules/ledger/ledger.module.js';
import { NotifyModule } from './modules/notify/notify.module.js';
import { BillingModule } from './modules/billing/billing.module.js';

const config = loadCoreConfig();

/** Shared infra providers, made global so every feature module can inject them. */
const infraProviders: Provider[] = [
  { provide: CONFIG, useValue: config },
  // DbService + EventsService need the non-class CONFIG/BUS tokens, so build them explicitly.
  {
    provide: EVENT_BUS,
    useFactory: (): EventBus => createEventBus(),
  },
  {
    provide: DbService,
    useFactory: (cfg: CoreConfig): DbService => new DbService(cfg),
    inject: [CONFIG],
  },
  {
    provide: EventsService,
    useFactory: (bus: EventBus): EventsService => new EventsService(bus),
    inject: [EVENT_BUS],
  },
  ContractValidator,
  {
    provide: TOKEN_VERIFIER,
    useClass: DevJwtVerifier,
  },
  // AuthGuard needs the verifier under its symbol; build it explicitly so Nest can resolve it.
  {
    provide: AuthGuard,
    useFactory: (reflector: Reflector, verifier: TokenVerifier): AuthGuard => new AuthGuard(reflector, verifier),
    inject: [Reflector, TOKEN_VERIFIER],
  },
];

@Global()
@Module({
  providers: [...infraProviders, { provide: APP_GUARD, useExisting: AuthGuard }],
  exports: [CONFIG, EVENT_BUS, DbService, EventsService, ContractValidator],
})
class InfraModule {}

@Module({
  imports: [InfraModule, GatewayModule, TenantsModule, FlagsModule, LedgerModule, NotifyModule, BillingModule],
})
export class AppModule {}

/** Re-exported so main.ts can read the same validated config instance. */
export const coreConfig = config;
