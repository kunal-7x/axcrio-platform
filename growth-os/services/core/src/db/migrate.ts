/**
 * Minimal forward-only migration runner (Phase 0). Applies every
 * src/db/migrations/*.sql in lexical order inside a transaction, tracking applied
 * files in core.schema_migrations. Idempotent: already-applied files are skipped.
 *
 * Runs as a PRIVILEGED role (the migration connection) so DDL + RLS setup succeed;
 * the app then connects as a less-privileged role that RLS constrains. Box/CI only —
 * needs a real Postgres (DATABASE_URL).
 */
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from 'pg';

const MIGRATIONS_DIR = join(dirname(fileURLToPath(import.meta.url)), 'migrations');

async function main(): Promise<void> {
  const url = process.env.DATABASE_URL;
  if (!url) {
    console.error('migrate: DATABASE_URL is required (box/CI — no DB on the laptop).');
    process.exit(2);
  }
  const client = new Client({ connectionString: url });
  await client.connect();
  try {
    await client.query('CREATE SCHEMA IF NOT EXISTS core');
    await client.query(`
      CREATE TABLE IF NOT EXISTS core.schema_migrations (
        filename text PRIMARY KEY,
        applied_at timestamptz NOT NULL DEFAULT now()
      )`);

    const files = readdirSync(MIGRATIONS_DIR)
      .filter((f) => f.endsWith('.sql'))
      .sort();

    for (const file of files) {
      const { rowCount } = await client.query('SELECT 1 FROM core.schema_migrations WHERE filename = $1', [file]);
      if (rowCount && rowCount > 0) {
        console.log(`migrate: skip ${file} (already applied)`);
        continue;
      }
      const sql = readFileSync(join(MIGRATIONS_DIR, file), 'utf8');
      console.log(`migrate: applying ${file} ...`);
      await client.query('BEGIN');
      try {
        await client.query(sql);
        await client.query('INSERT INTO core.schema_migrations (filename) VALUES ($1)', [file]);
        await client.query('COMMIT');
        console.log(`migrate: applied ${file}`);
      } catch (err) {
        await client.query('ROLLBACK');
        throw new Error(`migration ${file} failed: ${(err as Error).message}`);
      }
    }
    console.log('migrate: done.');
  } finally {
    await client.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
