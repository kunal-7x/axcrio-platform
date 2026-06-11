/**
 * GROWTH OS core — Phase-0 bootstrap (NestJS on Fastify, D1).
 *
 * One process, one base path (/v1 to match the OpenAPI servers). The global AuthGuard
 * (AppModule) authenticates + resolves tenant from the token (P6); @Public() routes opt out.
 * On the laptop (D8) the DB + bus are degraded/in-memory; the HTTP/contract surface still
 * boots so the contracts can be exercised. Real Postgres/Redpanda are box/CI.
 */
import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { Logger, ValidationPipe } from '@nestjs/common';
import cors from '@fastify/cors';
import { AppModule, coreConfig } from './app.module.js';

const API_PREFIX = 'v1';

async function bootstrap(): Promise<void> {
  const logger = new Logger('bootstrap');
  const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter({ trustProxy: true }), {
    logger: logLevels(coreConfig.LOG_LEVEL),
  });

  app.setGlobalPrefix(API_PREFIX);
  app.useGlobalPipes(new ValidationPipe({ transform: true, whitelist: true }));
  await app.register(cors, { origin: true });

  await app.listen({ port: coreConfig.PORT, host: '0.0.0.0' });
  logger.log(
    `core up on :${coreConfig.PORT}/${API_PREFIX} ` +
      `[env=${coreConfig.NODE_ENV} db=${coreConfig.dbEnabled ? 'on' : 'off'} ` +
      `bus=${coreConfig.busInMemory ? 'in-memory' : 'kafka'} devToken=${coreConfig.devTokenEnabled}]`,
  );
}

function logLevels(level: string): ('error' | 'warn' | 'log' | 'debug' | 'verbose')[] {
  const order: Array<['error' | 'warn' | 'log' | 'debug' | 'verbose', string[]]> = [
    ['error', ['fatal', 'error', 'warn', 'info', 'debug', 'trace']],
    ['warn', ['warn', 'info', 'debug', 'trace']],
    ['log', ['info', 'debug', 'trace']],
    ['debug', ['debug', 'trace']],
    ['verbose', ['trace']],
  ];
  return order.filter(([, levels]) => levels.includes(level)).map(([l]) => l);
}

bootstrap().catch((err) => {
  console.error('core failed to start:', err);
  process.exit(1);
});
