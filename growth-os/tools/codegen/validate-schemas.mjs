#!/usr/bin/env node
/**
 * Validate ALL contract schemas against JSON Schema 2020-12 + cross-$ref resolution
 * (BUILD-SPEC P1; `pnpm contracts:validate`). Run in CI before the drift check.
 *
 * - Every *.schema.json must be a valid 2020-12 document.
 * - All $ref between schemas must resolve (no dangling references — e.g. action_plan ->
 *   explanation.schema.json).
 * - The envelope must compile and a known-good envelope instance must PASS while a set of
 *   deliberately-broken instances must FAIL (proves the validator has teeth, mirroring the
 *   live "negative control" discipline).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { listSchemaFiles, SCHEMAS_DIR } from './lib.mjs';

const AjvCtor = Ajv2020.default ?? Ajv2020;
const addFormatsFn = addFormats.default ?? addFormats;

function makeAjv() {
  const ajv = new AjvCtor({ strict: false, allowUnionTypes: true, allErrors: true });
  addFormatsFn(ajv);
  // tolerate the x- extension keywords used for the topic map / registry
  for (const kw of ['x-event-type', 'x-topic', 'x-contract-version']) ajv.addKeyword(kw);
  return ajv;
}

function loadAll(ajv) {
  const files = listSchemaFiles();
  const byId = new Map();
  for (const file of files) {
    const json = JSON.parse(readFileSync(join(SCHEMAS_DIR, file), 'utf8'));
    if (!json.$id) throw new Error(`${file}: missing $id`);
    if (byId.has(json.$id)) throw new Error(`duplicate $id ${json.$id} (in ${file} and ${byId.get(json.$id)})`);
    byId.set(json.$id, file);
    ajv.addSchema(json, json.$id); // add once; resolve later via getSchema (ajv rejects double compile)
  }
  return { files, byId };
}

function compileAll(ajv, byId) {
  const errors = [];
  for (const [id, file] of byId) {
    try {
      const v = ajv.getSchema(id);
      if (!v) ajv.compile({ $ref: id }); // force resolution of all $refs
    } catch (e) {
      errors.push(`${file}: ${e.message}`);
    }
  }
  return errors;
}

const ENVELOPE_ID = 'https://contracts.growth-os.dev/schemas/event-envelope.schema.json';

const GOOD_ENVELOPE = {
  event_id: '0190b3a1-7c2d-7abc-89ef-0123456789ab',
  type: 'campaign.requested',
  version: '1.0.0',
  occurred_at: '2026-06-11T08:15:02Z',
  tenant_id: '11111111-1111-4111-8111-111111111111',
  workspace_id: '22222222-2222-4222-8222-222222222222',
  correlation_id: '33333333-3333-4333-8333-333333333333',
  causation_id: null,
  actor: { kind: 'system', id: 'demo' },
  idempotency_key: 'demo-key-1',
  payload: {},
};

const BAD_ENVELOPES = [
  ['missing tenant_id', (e) => { delete e.tenant_id; }],
  ['non-uuidv7 event_id (v4)', (e) => { e.event_id = '11111111-1111-4111-8111-111111111111'; }],
  ['bad type pattern (UpperCase)', (e) => { e.type = 'Campaign.Requested'; }],
  ['extra top-level prop', (e) => { e.injected = true; }],
  ['bad actor.kind enum', (e) => { e.actor = { kind: 'martian', id: 'x' }; }],
  ['bad version pattern', (e) => { e.version = 'one.zero.zero'; }],
];

function run() {
  const ajv = makeAjv();
  const { files, byId } = loadAll(ajv);
  const compileErrors = compileAll(ajv, byId);
  if (compileErrors.length) {
    console.error('[validate] ❌ schema compile / $ref errors:');
    for (const e of compileErrors) console.error('  - ' + e);
    process.exit(1);
  }
  console.log(`[validate] ✓ ${files.length} schemas valid (2020-12) + all $refs resolve`);

  const validateEnvelope = ajv.getSchema(ENVELOPE_ID);
  if (!validateEnvelope) {
    console.error('[validate] ❌ envelope schema not found');
    process.exit(1);
  }

  if (!validateEnvelope(structuredClone(GOOD_ENVELOPE))) {
    console.error('[validate] ❌ known-good envelope REJECTED:', validateEnvelope.errors);
    process.exit(1);
  }
  console.log('[validate] ✓ known-good envelope accepted');

  let teeth = 0;
  for (const [label, mutate] of BAD_ENVELOPES) {
    const bad = structuredClone(GOOD_ENVELOPE);
    mutate(bad);
    if (validateEnvelope(bad)) {
      console.error(`[validate] ❌ broken envelope ACCEPTED (no teeth): ${label}`);
      process.exit(1);
    }
    teeth++;
  }
  console.log(`[validate] ✓ ${teeth}/${BAD_ENVELOPES.length} negative-control envelopes correctly rejected`);
  console.log('[validate] ALL CONTRACT SCHEMA CHECKS PASSED');
}

run();
