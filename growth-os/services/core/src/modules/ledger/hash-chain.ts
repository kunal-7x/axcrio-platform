/**
 * ★ Action Ledger hash-chain (BUILD-SPEC §7.4, §5.5 tamper-evident; P4/P5).
 *
 * The ledger is an append-only, PER-TENANT chain of ActionPlan entries. Each entry's `hash`
 * commits to BOTH its own canonical content AND the previous entry's hash, so any tampering
 * with a historical entry breaks every subsequent link (the chain no longer recomputes).
 *
 *   hash(entry_n) = sha256( prev_hash || canonical_bytes(plan_n) )
 *   prev_hash(entry_0) = GENESIS (64 hex zeros)
 *
 * CANONICALIZATION is the crux: two semantically-equal plans MUST produce identical bytes.
 * We serialize the plan with recursively-sorted object keys, EXCLUDING the fields that are
 * (a) themselves the chain linkage (`ledger`) or (b) appended AFTER hashing (`signatures`).
 * Everything else — including status — is committed, so the proposed->signed status flip is
 * NOT part of the hashed bytes (we hash the plan at proposal time and the hash is immutable).
 *
 * This module is PURE (no I/O) so it is trivially unit-testable and identically reproducible
 * by a verifier walking the chain.
 */
import { createHash } from 'node:crypto';

/** Genesis prev_hash for the first entry in a tenant's chain. */
export const GENESIS_HASH = '0'.repeat(64);

/** Fields excluded from the canonical bytes (linkage + post-hash additions). */
const EXCLUDED_KEYS = new Set(['ledger', 'signatures']);

/**
 * Deterministically serialize a value with recursively-sorted object keys.
 * Arrays preserve order (order is semantically meaningful, e.g. operations[]).
 * Excludes the top-level chain/signature fields so the hash is stable across the
 * proposed->signed transition and across signature appends.
 */
export function canonicalize(plan: Record<string, unknown>): string {
  return stableStringify(plan, true);
}

function stableStringify(value: unknown, topLevel = false): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) {
    return `[${value.map((v) => stableStringify(v)).join(',')}]`;
  }
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj)
      .filter((k) => !(topLevel && EXCLUDED_KEYS.has(k)))
      .filter((k) => obj[k] !== undefined)
      .sort();
    const entries = keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`);
    return `{${entries.join(',')}}`;
  }
  // string | number | boolean — JSON.stringify gives canonical forms.
  return JSON.stringify(value);
}

/** Compute the entry hash from the previous hash + the plan's canonical bytes. */
export function computeHash(prevHash: string, plan: Record<string, unknown>): string {
  return createHash('sha256').update(prevHash).update('\n').update(canonicalize(plan)).digest('hex');
}

/** One link in the chain as stored (the columns the verifier needs). */
export interface ChainLink {
  sequence: number;
  prev_hash: string;
  hash: string;
  /** The canonical plan content that was hashed (excludes ledger/signatures). */
  plan: Record<string, unknown>;
}

export interface ChainVerifyResult {
  ok: boolean;
  entries_checked: number;
  chain_head_hash: string | null;
  /** action_plan_id of the first broken link, if any. */
  first_broken_id: string | null;
}

/**
 * Walk an ORDERED (by sequence) list of links and verify the chain recomputes.
 * Checks: genesis prev_hash on entry 0, prev_hash continuity, and hash correctness.
 */
export function verifyChain(links: ReadonlyArray<ChainLink & { action_plan_id: string }>): ChainVerifyResult {
  let expectedPrev = GENESIS_HASH;
  let head: string | null = null;
  for (let i = 0; i < links.length; i++) {
    const link = links[i]!;
    if (link.prev_hash !== expectedPrev) {
      return { ok: false, entries_checked: i, chain_head_hash: head, first_broken_id: link.action_plan_id };
    }
    const recomputed = computeHash(link.prev_hash, link.plan);
    if (recomputed !== link.hash) {
      return { ok: false, entries_checked: i, chain_head_hash: head, first_broken_id: link.action_plan_id };
    }
    expectedPrev = link.hash;
    head = link.hash;
  }
  return { ok: true, entries_checked: links.length, chain_head_hash: head, first_broken_id: null };
}
