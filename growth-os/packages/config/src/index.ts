/**
 * @growth-os/config — typed, zod-validated runtime config (BUILD-SPEC §20 packages/config).
 *
 * One source of truth for env. Services call loadCoreConfig() once at boot and pass the
 * frozen object around — no scattered process.env reads. Invalid/missing required env fails
 * fast with a precise message (fail-closed). Phase 0 has sane localhost defaults so the app
 * boots on the laptop; the bus/db only connect when their URLs are present (D8).
 */
import { z } from 'zod';

const Boolish = z
  .union([z.boolean(), z.string()])
  .transform((v) => (typeof v === 'boolean' ? v : ['1', 'true', 'yes', 'on'].includes(v.toLowerCase())));

const CoreConfigSchema = z.object({
  /** Runtime environment. Prod gates off the dev-token stub (D5). */
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  /** HTTP port for the core app (Fastify). */
  PORT: z.coerce.number().int().positive().default(3000),
  /** Log level. */
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace', 'silent']).default('info'),

  /** Postgres connection. Absent on the laptop => the app boots in degraded/no-db mode for typecheck/dev. */
  DATABASE_URL: z.string().url().optional(),
  /** Force-disable DB even if a URL is present (tests / offline). */
  DB_DISABLED: Boolish.default(false),

  /** Kafka/Redpanda brokers (comma-separated). Absent => in-memory bus (D8 laptop path). */
  KAFKA_BROKERS: z.string().optional(),
  /** Force the in-memory bus regardless of brokers. */
  BUS_MEMORY: Boolish.default(false),

  /** Phase-0 dev-token signing secret (HS256). NEVER used in prod (Phase 3 = OIDC). */
  AUTH_DEV_SECRET: z.string().min(8).default('growth-os-phase0-dev-secret-not-for-prod'),
  /** Enable the dev-token mint endpoint. Auto-off in production. */
  DEV_TOKEN_ENABLED: Boolish.optional(),

  /** Ledger signing key id (the signer identity stamped on signatures[]). */
  LEDGER_SIGNER_KEY_ID: z.string().default('ledger-dev-key-1'),
  /** Ledger signing secret (HS256 over canonical plan bytes). Phase 0 symmetric; ed25519 later. */
  LEDGER_SIGNING_SECRET: z.string().min(8).default('growth-os-phase0-ledger-secret-not-for-prod'),

  /** Origin Connector per-connection service token (mirrors live AIASSET_SERVICE_TOKEN). */
  ORIGIN_SERVICE_TOKEN: z.string().optional(),

  /** OTel collector endpoint (P10). Absent => traces stay in-process. */
  OTEL_EXPORTER_OTLP_ENDPOINT: z.string().url().optional(),
  OTEL_SERVICE_NAME: z.string().default('growth-os-core'),
});

export type CoreConfig = Readonly<z.infer<typeof CoreConfigSchema>> & {
  /** Derived: is this a production runtime? */
  readonly isProd: boolean;
  /** Derived: should the dev-token stub be available? (never in prod) */
  readonly devTokenEnabled: boolean;
  /** Derived: is a real DB configured + enabled? */
  readonly dbEnabled: boolean;
  /** Derived: use the in-memory bus? */
  readonly busInMemory: boolean;
};

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigError';
  }
}

/** Load + validate config from an env-like record (defaults to process.env). */
export function loadCoreConfig(env: NodeJS.ProcessEnv = process.env): CoreConfig {
  const parsed = CoreConfigSchema.safeParse(env);
  if (!parsed.success) {
    const issues = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
    throw new ConfigError(`invalid configuration: ${issues}`);
  }
  const c = parsed.data;
  const isProd = c.NODE_ENV === 'production';
  const config: CoreConfig = Object.freeze({
    ...c,
    isProd,
    devTokenEnabled: isProd ? false : (c.DEV_TOKEN_ENABLED ?? true),
    dbEnabled: Boolean(c.DATABASE_URL) && !c.DB_DISABLED,
    busInMemory: c.BUS_MEMORY || !c.KAFKA_BROKERS,
  });
  return config;
}
