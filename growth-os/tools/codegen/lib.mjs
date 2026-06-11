/**
 * Shared codegen/registry helpers (BUILD-SPEC P1; architecture-phase0.md §5.5).
 *
 * The registry (`contracts/registry/`) is the SINGLE SOURCE OF TRUTH for which schema files
 * exist, their type@version, their topic, and their sha256. The CI contract-drift mechanism
 * (§6 Phase 0 acceptance) recomputes the sha256 over the schema bytes and fails if any
 * differs from the snapshot. Everything is byte-exact and LF-normalized so the hash is
 * stable across OSes (this repo is built on Windows; CI runs on Linux).
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(HERE, '..', '..');
export const SCHEMAS_DIR = join(REPO_ROOT, 'contracts', 'schemas');
export const REGISTRY_DIR = join(REPO_ROOT, 'contracts', 'registry');

/** sha256 over LF-normalized UTF-8 bytes (cross-OS stable — matches the existing snapshot). */
export function hashBytes(text) {
  const lf = text.replace(/\r\n/g, '\n');
  return createHash('sha256').update(lf, 'utf8').digest('hex');
}

/** Read + parse a JSON file. */
export function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/** Read a file's raw text (for hashing). */
export function readText(path) {
  return readFileSync(path, 'utf8');
}

/** All *.schema.json files in contracts/schemas, sorted for determinism. */
export function listSchemaFiles() {
  return readdirSync(SCHEMAS_DIR)
    .filter((f) => f.endsWith('.schema.json'))
    .sort();
}

/**
 * Build the full registry index from the schema files themselves.
 * Each entry: { name, kind, event_type, topic, version, $id, file, sha256 }.
 * `event_type`/`topic` come from the schema's `x-event-type`/`x-topic` (the envelope schema
 * + the three frozen artifacts have neither => kind=envelope|artifact, event_type=null).
 */
export function buildIndex() {
  const files = listSchemaFiles();
  const schemas = files.map((file) => {
    const abs = join(SCHEMAS_DIR, file);
    const text = readText(abs);
    const json = JSON.parse(text);
    const eventType = json['x-event-type'] ?? null;
    const topic = json['x-topic'] ?? null;
    const isEnvelope = file === 'event-envelope.schema.json';
    const isArtifact = !eventType && !isEnvelope;
    return {
      name: file.replace(/\.schema\.json$/, ''),
      kind: isEnvelope ? 'envelope' : isArtifact ? 'artifact' : 'event',
      event_type: eventType,
      topic,
      version: json['x-contract-version'] ?? json.properties?.version?.const ?? '1.0.0',
      $id: json.$id ?? null,
      file: `contracts/schemas/${file}`,
      sha256: hashBytes(text),
    };
  });
  return {
    group: 'event-backbone',
    description:
      'Canonical event envelope + core event payload schemas + frozen artifacts. ' +
      'Frozen-after-merge, additive-only (P1/D7). CI diffs sha256 -> fails on drift.',
    generated_from: 'the schema files themselves (sha256 over LF-normalized bytes)',
    topic_map_doc: 'contracts/asyncapi/bus.yaml',
    count: schemas.length,
    schemas,
  };
}

/** Map of event_type -> registry entry (events only). */
export function eventTypeMap(index) {
  const map = new Map();
  for (const s of index.schemas) {
    if (s.kind === 'event' && s.event_type) map.set(s.event_type, s);
  }
  return map;
}
