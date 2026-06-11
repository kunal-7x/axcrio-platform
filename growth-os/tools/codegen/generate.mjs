#!/usr/bin/env node
/**
 * Umbrella codegen (BUILD-SPEC P1) — `pnpm codegen`.
 * Runs, in order:
 *   1. generate-types.mjs  (JSON Schemas -> @growth-os/events typed surface)
 *   2. generate-sdk.mjs    (OpenAPI 3.1 -> @growth-os/sdk typed paths/components)
 * then prints a reminder to re-snapshot the registry IF a schema legitimately changed.
 *
 * Each step is a child process so a failure surfaces a clean non-zero exit (CI-friendly).
 */

import { spawnSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

function step(script) {
  const res = spawnSync(process.execPath, [join(HERE, script)], { stdio: 'inherit' });
  if (res.status !== 0) {
    console.error(`[codegen] ✗ ${script} failed (exit ${res.status}).`);
    process.exit(res.status ?? 1);
  }
}

step('generate-types.mjs');
step('generate-sdk.mjs');

console.log(
  '\n[codegen] ✓ types + SDK regenerated.\n' +
    '          If you intentionally changed a frozen schema, bump its version (§6.2) and run\n' +
    '          `pnpm contracts:snapshot` to re-freeze the drift snapshot. Otherwise `pnpm contracts:drift`\n' +
    '          will (correctly) fail in CI.',
);
