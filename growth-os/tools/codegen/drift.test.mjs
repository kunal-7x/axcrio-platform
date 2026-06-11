/**
 * Contract-drift test (BUILD-SPEC §21 Phase-0 acceptance: "contract-drift test fails on an
 * intentional schema edit"; architecture-phase0.md §6).
 *
 * Three assertions:
 *   1. POSITIVE: with the repo as-is, the drift checker passes (every frozen schema matches
 *      the snapshot) — proves the snapshot is in sync.
 *   2. NEGATIVE (logic): an intentional edit to a schema's bytes changes its sha256, so the
 *      snapshot comparison reports DRIFT — proves the mechanism has teeth without mutating the
 *      real repo files (we diff a current index against a doctored snapshot).
 *   3. NEGATIVE (end-to-end CLI): copy the contracts into a temp dir, edit one schema on disk,
 *      and run `build-registry.mjs --check` against it — assert a NON-ZERO exit. This is the
 *      literal "intentional schema edit makes CI fail" guarantee.
 *
 * Run via vitest: `pnpm --filter @growth-os/codegen test` (or the root `turbo run test`).
 */

import { describe, it, expect } from 'vitest';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildIndex, REPO_ROOT, REGISTRY_DIR, hashBytes } from './lib.mjs';

const SNAPSHOT_PATH = join(REGISTRY_DIR, 'event-backbone.drift-snapshot.json');
const BUILD_REGISTRY = join(REPO_ROOT, 'tools', 'codegen', 'build-registry.mjs');

describe('contract-drift mechanism', () => {
  it('1. POSITIVE: the live repo matches the frozen snapshot (--check passes)', () => {
    const res = spawnSync(process.execPath, [BUILD_REGISTRY, '--check'], { encoding: 'utf8' });
    expect(res.status, res.stdout + res.stderr).toBe(0);
    expect(res.stdout).toMatch(/no drift/);
  });

  it('2. NEGATIVE (logic): editing a schema changes its sha256 vs the snapshot', () => {
    const snapshot = JSON.parse(readFileSync(SNAPSHOT_PATH, 'utf8')).schemas;
    const index = buildIndex();
    const envelope = index.schemas.find((s) => s.name === 'event-envelope');
    expect(envelope).toBeDefined();

    // current bytes match the snapshot
    expect(envelope.sha256).toBe(snapshot['event-envelope'].sha256);

    // simulate an intentional edit (add a field) and recompute the hash
    const raw = readFileSync(join(REPO_ROOT, 'contracts', 'schemas', 'event-envelope.schema.json'), 'utf8');
    const edited = raw.replace('"title": "EventEnvelope"', '"title": "EventEnvelope", "x-sneaky": true');
    expect(edited).not.toBe(raw);
    const editedHash = hashBytes(edited);

    // the edited hash must DIFFER from the frozen snapshot => drift detected
    expect(editedHash).not.toBe(snapshot['event-envelope'].sha256);
  });

  it('3. NEGATIVE (CLI end-to-end): an on-disk schema edit makes --check exit non-zero', () => {
    const tmp = mkdtempSync(join(tmpdir(), 'growthos-drift-'));
    try {
      // copy the contracts tree + ONLY the two .mjs the checker needs (build-registry depends
      // solely on lib.mjs + node builtins — no ajv). Copying the whole codegen dir would drag
      // in pnpm's symlinked node_modules (EPERM on Windows).
      cpSync(join(REPO_ROOT, 'contracts'), join(tmp, 'contracts'), { recursive: true });
      const codegenTmp = join(tmp, 'tools', 'codegen');
      mkdirSync(codegenTmp, { recursive: true });
      cpSync(join(REPO_ROOT, 'tools', 'codegen', 'lib.mjs'), join(codegenTmp, 'lib.mjs'), { recursive: false });
      cpSync(join(REPO_ROOT, 'tools', 'codegen', 'build-registry.mjs'), join(codegenTmp, 'build-registry.mjs'), {
        recursive: false,
      });

      // intentional edit: append a property to a frozen schema (the "off-contract" change)
      const target = join(tmp, 'contracts', 'schemas', 'lead.scored.schema.json');
      const original = readFileSync(target, 'utf8');
      const tampered = original.replace(
        '"additionalProperties": false',
        '"additionalProperties": false, "x-injected-by-test": "drift"',
      );
      expect(tampered).not.toBe(original);
      writeFileSync(target, tampered, 'utf8');

      const res = spawnSync(process.execPath, [join(tmp, 'tools', 'codegen', 'build-registry.mjs'), '--check'], {
        encoding: 'utf8',
      });
      expect(res.status, `expected non-zero exit; got ${res.status}\n${res.stdout}${res.stderr}`).not.toBe(0);
      expect(res.stderr + res.stdout).toMatch(/DRIFT in lead\.scored/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
