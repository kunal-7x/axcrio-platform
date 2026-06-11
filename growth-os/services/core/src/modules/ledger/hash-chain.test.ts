import { describe, it, expect } from 'vitest';
import {
  GENESIS_HASH,
  canonicalize,
  computeHash,
  verifyChain,
  type ChainLink,
} from './hash-chain.js';

function plan(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    action_plan_id: '11111111-1111-7111-8111-111111111111',
    version: '1.0.0',
    tenant_id: 't1',
    actor: { kind: 'system', id: 'optimizer' },
    action_type: 'pause_ad',
    status: 'proposed',
    operations: [{ op_id: 'o1', connector: 'meta', op: 'pause_entity', idempotency_key: 'k1' }],
    explanation: { action: { type: 'pause_ad', summary_en: 'pause' } },
    ...overrides,
  };
}

describe('canonicalize', () => {
  it('is stable under key reordering', () => {
    const a = canonicalize({ b: 1, a: 2, nested: { y: 1, x: 2 } });
    const b = canonicalize({ a: 2, nested: { x: 2, y: 1 }, b: 1 });
    expect(a).toBe(b);
  });

  it('preserves array order (operations are ordered)', () => {
    const a = canonicalize({ ops: [1, 2, 3] });
    const b = canonicalize({ ops: [3, 2, 1] });
    expect(a).not.toBe(b);
  });

  it('excludes ledger + signatures from the canonical bytes', () => {
    const base = plan();
    const withChainAndSigs = plan({
      ledger: { prev_hash: 'x', hash: 'y', sequence: 5 },
      signatures: [{ signer: 's', alg: 'HS256', signature: 'z', signed_at: '2026-01-01T00:00:00Z' }],
    });
    expect(canonicalize(base)).toBe(canonicalize(withChainAndSigs));
  });

  it('hash is invariant across the proposed->signed status flip is NOT assumed (status IS hashed)', () => {
    // status is part of the canonical bytes; changing it changes the hash. We rely on the
    // hash being computed ONCE at proposal time and frozen — verified separately below.
    expect(canonicalize(plan({ status: 'proposed' }))).not.toBe(canonicalize(plan({ status: 'signed' })));
  });
});

describe('computeHash + chain', () => {
  it('first entry chains off the genesis hash', () => {
    const p = plan();
    const h = computeHash(GENESIS_HASH, p);
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    const res = verifyChain([{ action_plan_id: 'a1', sequence: 0, prev_hash: GENESIS_HASH, hash: h, plan: p }]);
    expect(res.ok).toBe(true);
    expect(res.entries_checked).toBe(1);
    expect(res.chain_head_hash).toBe(h);
  });

  it('verifies a multi-entry chain', () => {
    const p0 = plan({ action_plan_id: 'a0' });
    const h0 = computeHash(GENESIS_HASH, p0);
    const p1 = plan({ action_plan_id: 'a1', action_type: 'promote_ad' });
    const h1 = computeHash(h0, p1);
    const links: Array<ChainLink & { action_plan_id: string }> = [
      { action_plan_id: 'a0', sequence: 0, prev_hash: GENESIS_HASH, hash: h0, plan: p0 },
      { action_plan_id: 'a1', sequence: 1, prev_hash: h0, hash: h1, plan: p1 },
    ];
    expect(verifyChain(links).ok).toBe(true);
  });

  it('DETECTS tampering: mutating a historical plan breaks the chain', () => {
    const p0 = plan({ action_plan_id: 'a0' });
    const h0 = computeHash(GENESIS_HASH, p0);
    const p1 = plan({ action_plan_id: 'a1' });
    const h1 = computeHash(h0, p1);
    // Tamper with entry 0's content AFTER the fact (its stored hash h0 no longer matches).
    const tampered = plan({ action_plan_id: 'a0', action_type: 'scale_budget' });
    const links: Array<ChainLink & { action_plan_id: string }> = [
      { action_plan_id: 'a0', sequence: 0, prev_hash: GENESIS_HASH, hash: h0, plan: tampered },
      { action_plan_id: 'a1', sequence: 1, prev_hash: h0, hash: h1, plan: p1 },
    ];
    const res = verifyChain(links);
    expect(res.ok).toBe(false);
    expect(res.first_broken_id).toBe('a0');
  });

  it('DETECTS a broken prev_hash link (reordering / deletion)', () => {
    const p0 = plan({ action_plan_id: 'a0' });
    const h0 = computeHash(GENESIS_HASH, p0);
    const p1 = plan({ action_plan_id: 'a1' });
    const h1 = computeHash(h0, p1);
    // Entry 1 claims a wrong prev_hash (e.g. someone deleted entry 0 and re-pointed).
    const links: Array<ChainLink & { action_plan_id: string }> = [
      { action_plan_id: 'a1', sequence: 0, prev_hash: 'deadbeef'.repeat(8), hash: h1, plan: p1 },
    ];
    const res = verifyChain(links);
    expect(res.ok).toBe(false);
    expect(res.first_broken_id).toBe('a1');
  });

  it('signatures/ledger appended after hashing do not invalidate the hash', () => {
    const p = plan();
    const h = computeHash(GENESIS_HASH, p);
    // Now the stored plan has signatures + ledger attached (as it would post-sign).
    const stored = {
      ...p,
      ledger: { prev_hash: GENESIS_HASH, hash: h, sequence: 0 },
      signatures: [{ signer: 'ledger-dev-key-1', alg: 'HS256', signature: 'sig', signed_at: '2026-01-01T00:00:00Z' }],
      status: 'signed',
    };
    // Re-derive from the ORIGINAL proposal content (status proposed, no sigs/ledger) — the
    // verifier recomputes from canonical bytes which exclude sigs/ledger; but status differs.
    // The ledger stores the canonical content it hashed; here we prove excluding sigs/ledger
    // yields the same hash when status is held at proposal value.
    const canonicalForHash = { ...stored, status: 'proposed' };
    expect(computeHash(GENESIS_HASH, canonicalForHash)).toBe(h);
  });
});
