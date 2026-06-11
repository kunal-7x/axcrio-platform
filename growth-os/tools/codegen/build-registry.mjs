#!/usr/bin/env node
/**
 * Build / check the contract registry — the CONTRACT-DRIFT mechanism (Phase 0 acceptance).
 *
 *   node tools/codegen/build-registry.mjs --write   # regenerate index + drift-snapshot (after an intentional, versioned change)
 *   node tools/codegen/build-registry.mjs --check    # CI: recompute sha256 over schema bytes; fail on ANY drift
 *
 * The drift snapshot pins every FROZEN schema's sha256 (envelope + core events + the 3
 * frozen artifacts CIB/MediaPlan/ActionPlan + their sub-schemas). An UNINTENDED edit to any
 * one (or an added/removed schema) changes the recomputed hash / set and `--check` exits
 * non-zero. This is exactly the spec's "contract-drift test fails on an intentional schema
 * edit." A LEGITIMATE change is made deliberately + re-snapshotted with `--write` and (per
 * §6.2) carries a version bump — the human-gated, reviewable moment.
 *
 * Snapshot SHAPE is the established `{ schemas: { <name>: { version, sha256 } } }` map (the
 * format the contracts were first snapshotted in — kept stable so this is purely additive).
 */

import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildIndex, readJson, REGISTRY_DIR } from './lib.mjs';

const INDEX_PATH = join(REGISTRY_DIR, 'event-backbone.index.json');
const SNAPSHOT_PATH = join(REGISTRY_DIR, 'event-backbone.drift-snapshot.json');

/** The drift snapshot = name -> { version, sha256 } over EVERY frozen schema. */
function toSnapshot(index) {
  const schemas = {};
  for (const s of [...index.schemas].sort((a, b) => a.name.localeCompare(b.name))) {
    schemas[s.name] = { version: s.version, sha256: s.sha256 };
  }
  return {
    group: index.group,
    algo: 'sha256',
    note: 'CI fails when any sha256 changes without a version bump (Phase-0 acceptance §6). sha256 is over LF-normalized bytes (cross-OS stable).',
    count: Object.keys(schemas).length,
    schemas,
  };
}

function writeAll() {
  const index = buildIndex();
  writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2) + '\n', 'utf8');
  const snapshot = toSnapshot(index);
  writeFileSync(SNAPSHOT_PATH, JSON.stringify(snapshot, null, 2) + '\n', 'utf8');
  console.log(`[registry] wrote ${index.count} schemas`);
  console.log(`[registry] index    -> ${INDEX_PATH}`);
  console.log(`[registry] snapshot -> ${SNAPSHOT_PATH}`);
}

function check() {
  const index = buildIndex();
  const current = toSnapshot(index).schemas;
  let saved;
  try {
    saved = readJson(SNAPSHOT_PATH).schemas;
  } catch {
    console.error('[drift] FAIL: no drift-snapshot.json schemas map — run `--write` first.');
    process.exit(1);
  }

  const problems = [];
  for (const [name, cur] of Object.entries(current)) {
    const prev = saved[name];
    if (!prev) {
      problems.push(`ADDED schema not in snapshot: ${name} (re-snapshot with --write if intentional)`);
      continue;
    }
    if (prev.sha256 !== cur.sha256) {
      problems.push(
        `DRIFT in ${name}.schema.json\n      snapshot sha256=${prev.sha256}\n      current  sha256=${cur.sha256}` +
          (prev.version === cur.version
            ? `\n      (version unchanged at ${cur.version} — a FROZEN schema was edited WITHOUT a version bump, §6.2)`
            : `\n      (version ${prev.version} -> ${cur.version})`),
      );
    }
  }
  for (const name of Object.keys(saved)) {
    if (!current[name]) problems.push(`REMOVED schema present in snapshot: ${name}`);
  }

  if (problems.length > 0) {
    console.error('[drift] CONTRACT DRIFT DETECTED (' + problems.length + '):');
    for (const p of problems) console.error('  - ' + p);
    console.error(
      '\n[drift] If this change is intentional + reviewed, bump the schema version (§6.2 extend-never-mutate)\n' +
        '        and re-run `pnpm contracts:snapshot` to re-freeze. Otherwise revert the edit.',
    );
    process.exit(1);
  }

  console.log(`[drift] no drift — ${Object.keys(current).length} frozen schemas match the snapshot.`);
}

const mode = process.argv.includes('--write') ? 'write' : process.argv.includes('--check') ? 'check' : null;
if (mode === 'write') writeAll();
else if (mode === 'check') check();
else {
  console.error('usage: build-registry.mjs --write | --check');
  process.exit(2);
}
