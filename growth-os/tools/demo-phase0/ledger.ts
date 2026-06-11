/**
 * Minimal hash-chained Action Ledger for the Phase-0 demo (BUILD-SPEC §7.4, §5.5).
 *
 * The real Ledger is a Postgres table inside services/core with append-only, hash-chained,
 * tamper-evident entries (`prev_hash -> hash`, mirroring `action_plan.schema.json` `ledger`).
 * This in-memory version reproduces the EXACT chaining algorithm so the demo proves the
 * property on the laptop (no DB): each entry's `hash = sha256(prev_hash + canonical(entry))`,
 * so any tampering with an earlier entry breaks every subsequent hash (verifiable offline).
 *
 * This is also the Phase-0 stand-in the demo's consumer writes to when it sees an event — the
 * acceptance line "a consumer handles it → a Ledger entry is written (hash-chained)".
 */

import { createHash } from 'node:crypto';

export interface LedgerEntryInput {
  /** What happened (e.g. 'campaign.requested.observed'). */
  action_type: string;
  tenant_id: string;
  correlation_id: string;
  /** The §P5 Explanation (no silent actions) — kept compact for the demo. */
  explanation: { summary_en: string; evidence?: Array<{ metric: string; value: unknown }> };
  /** Free-form reference to the causing event (event_id). */
  causation_event_id?: string;
}

export interface LedgerEntry extends LedgerEntryInput {
  sequence: number;
  recorded_at: string;
  prev_hash: string;
  hash: string;
}

const GENESIS = '0'.repeat(64);

/** Canonical bytes of an entry MINUS the chain fields (those are derived from these bytes). */
function canonicalBody(entry: Omit<LedgerEntry, 'hash'>): string {
  // stable key order; the hash covers everything except `hash` itself (incl prev_hash + seq).
  return JSON.stringify({
    sequence: entry.sequence,
    recorded_at: entry.recorded_at,
    action_type: entry.action_type,
    tenant_id: entry.tenant_id,
    correlation_id: entry.correlation_id,
    explanation: entry.explanation,
    causation_event_id: entry.causation_event_id ?? null,
    prev_hash: entry.prev_hash,
  });
}

export class HashChainedLedger {
  private readonly entries: LedgerEntry[] = [];

  /** Append an entry, chaining it to the previous head. Returns the written entry. */
  append(input: LedgerEntryInput, now = new Date()): LedgerEntry {
    const prev_hash = this.entries.length ? this.entries[this.entries.length - 1]!.hash : GENESIS;
    const base: Omit<LedgerEntry, 'hash'> = {
      ...input,
      sequence: this.entries.length,
      recorded_at: now.toISOString(),
      prev_hash,
    };
    const hash = createHash('sha256').update(canonicalBody(base), 'utf8').digest('hex');
    const entry: LedgerEntry = { ...base, hash };
    this.entries.push(entry);
    return entry;
  }

  all(): readonly LedgerEntry[] {
    return this.entries;
  }

  /** Re-derive every hash and confirm the chain is intact (tamper-evidence check, §5.5). */
  verify(): { ok: boolean; brokenAt?: number } {
    let prev = GENESIS;
    for (const e of this.entries) {
      if (e.prev_hash !== prev) return { ok: false, brokenAt: e.sequence };
      const { hash: _omit, ...body } = e;
      const recomputed = createHash('sha256').update(canonicalBody(body), 'utf8').digest('hex');
      if (recomputed !== e.hash) return { ok: false, brokenAt: e.sequence };
      prev = e.hash;
    }
    return { ok: true };
  }
}
