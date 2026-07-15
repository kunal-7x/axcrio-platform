/**
 * Work programs — what makes a workforce hire ACTUALLY do its job, not write essays.
 *
 * Each wf-* role gets a program: a job-specific system prompt that demands ONE structured JSON
 * ACTION (a concrete deliverable — a WhatsApp message to a real lead, a dunning sequence step, a
 * reconciliation verdict, a budget shift), plus a deterministic fallback that still produces a
 * valid action when no model is reachable (the shift never stalls, and we never fake reasoning).
 *
 * The action contract every program returns:
 *   { kind, customerMessage?, params, note }
 * The dispatcher (agent-actions.ts) then executes it: internal records are written for real,
 * external sends deliver for real only when provider creds exist (else honestly 'prepared'),
 * and money actions PARK for human approval.
 */

export interface WorkAction {
  kind: string;
  customerMessage?: string;
  params: Record<string, unknown>;
  note: string;
}

export interface WorkProgram {
  /** The primary action kind this role produces (also the outcome it is paid for). */
  actionKind: string;
  /** Money/irreversible: the action parks for approval instead of dispatching. */
  money?: boolean;
  system(role: string, industry: string): string;
  fallback(taskBody: string): WorkAction;
}

const CONTRACT =
  'Respond with ONLY one JSON object, no prose, no code fences: ' +
  '{"kind": "<action>", "customer_message": "<the exact message to send, or null>", ' +
  '"params": {...}, "note": "<one line: what you did and why>"}. ' +
  'Never invent customer PII — use only names/numbers present in the task.';

/** Best-effort name extraction so deterministic fallbacks stay personal without inventing PII. */
function nameFrom(task: string): string {
  const m = /(?:lead|customer|client|from|for|invoice)\s+([A-Z][a-z]{2,15})/i.exec(task);
  return m?.[1] ?? 'there';
}

export const WORK_PROGRAMS: Record<string, WorkProgram> = {
  'wf-sdr': {
    actionKind: 'send_whatsapp',
    system: (role, industry) =>
      `You are an ${role} (${industry}) — an AI SDR working WhatsApp leads for a business on Famit. ` +
      `Given the lead in the task: draft the actual WhatsApp message (warm, short, Indian-business tone, one clear CTA), ` +
      `qualify what you can from the text, and schedule the next follow-up. ` +
      `kind MUST be "send_whatsapp"; params MUST include {"to": "<lead name/number from the task>", ` +
      `"qualification": {"intent": "hot|warm|cold", "budget": "<known or unknown>", "timeline": "<known or unknown>"}, ` +
      `"followup_in_hours": <number>}. ${CONTRACT}`,
    fallback: (task) => {
      const to = nameFrom(task);
      return {
        kind: 'send_whatsapp',
        customerMessage: `Hi ${to}! Thanks for reaching out — I’d love to help you take the next step. When would be a good time for a quick call today or tomorrow?`,
        params: { to, qualification: { intent: 'warm', budget: 'unknown', timeline: 'unknown' }, followup_in_hours: 24 },
        note: 'deterministic first-touch + 24h follow-up (no model available)',
      };
    },
  },
  'wf-collections': {
    actionKind: 'send_whatsapp',
    system: (role, industry) =>
      `You are a ${role} (${industry}) — an AI collections agent chasing overdue invoices for a business on Famit. ` +
      `Given the overdue invoice in the task: draft the actual dunning message (polite, firm, references the invoice + amount, offers a payment link placeholder {PAY_LINK}), ` +
      `and propose the escalation step. kind MUST be "send_whatsapp"; params MUST include ` +
      `{"to": "<debtor from the task>", "invoice": "<id/ref from the task>", "amount_inr": <number or null>, ` +
      `"stage": "reminder|firm|final", "promise_to_pay_days": <number or null>}. ${CONTRACT}`,
    fallback: (task) => {
      const to = nameFrom(task);
      return {
        kind: 'send_whatsapp',
        customerMessage: `Hi ${to}, a gentle reminder that your invoice is past due. You can settle it here: {PAY_LINK}. If you’ve already paid, please ignore this — otherwise could you share when we can expect payment?`,
        params: { to, invoice: 'from-task', amount_inr: null, stage: 'reminder', promise_to_pay_days: 3 },
        note: 'deterministic stage-1 reminder (no model available)',
      };
    },
  },
  'wf-support': {
    actionKind: 'send_reply',
    system: (role, industry) =>
      `You are a ${role} (${industry}) — an AI Tier-1 support rep for a business on Famit. ` +
      `Given the customer question in the task: draft the actual reply (answer directly from facts IN the task; if the task lacks the answer, say what you'll check — never invent), ` +
      `and decide the resolution. kind MUST be "send_reply"; params MUST include ` +
      `{"channel": "whatsapp|email", "to": "<customer from the task>", "resolution": "resolved|escalate", "summary": "<one line for the ticket log>"}. ${CONTRACT}`,
    fallback: (task) => {
      const to = nameFrom(task);
      return {
        kind: 'send_reply',
        customerMessage: `Hi ${to}, thanks for writing in — I’m on this now and will get back to you with a full answer shortly. If it’s urgent, reply URGENT and a teammate will jump in.`,
        params: { channel: 'whatsapp', to, resolution: 'escalate', summary: 'acknowledged; escalated to a human (deterministic mode)' },
        note: 'deterministic acknowledge + escalate (no model available)',
      };
    },
  },
  'wf-ads': {
    actionKind: 'budget_shift',
    money: true, // moving ad spend is MONEY — it always parks for founder approval
    system: (role, industry) =>
      `You are a ${role} (${industry}) — an AI ads optimizer for a business on Famit. ` +
      `Given the campaign performance in the task: propose ONE concrete budget shift from the worst performer to the best ` +
      `(use only campaigns/numbers present in the task). kind MUST be "budget_shift"; customer_message MUST be null; params MUST include ` +
      `{"from_campaign": "<name>", "to_campaign": "<name>", "amount_inr_per_day": <number>, "expected_effect": "<one line>"}. ${CONTRACT}`,
    fallback: (task) => ({
      kind: 'budget_shift',
      params: {
        from_campaign: 'lowest-CTR campaign in the task',
        to_campaign: 'highest-CTR campaign in the task',
        amount_inr_per_day: 500,
        expected_effect: 'shift ₹500/day from the weakest to the strongest ad set (deterministic heuristic)',
      },
      note: 'deterministic budget-shift proposal (no model available) — parks for approval',
    }),
  },
  'wf-bookkeeper': {
    actionKind: 'ledger_entry',
    system: (role, industry) =>
      `You are a ${role} (${industry}) — an AI bookkeeper for a business on Famit. ` +
      `Given the day's transactions/settlements in the task: reconcile them (match settlements to invoices present in the task), ` +
      `and record the verdict. kind MUST be "ledger_entry"; customer_message MUST be null; params MUST include ` +
      `{"entries_posted": <number>, "matched": <number>, "mismatches": [{"ref": "<id>", "issue": "<what>"}], "books_current": true|false}. ${CONTRACT}`,
    fallback: () => ({
      kind: 'ledger_entry',
      params: { entries_posted: 0, matched: 0, mismatches: [], books_current: false, needs_review: 'no parseable transactions in the task' },
      note: 'deterministic: nothing reconcilable found in the task — flagged for review',
    }),
  },
  'wf-caller': {
    actionKind: 'place_call',
    system: (role, industry) =>
      `You are an ${role} (${industry}) — an AI appointment setter for a business on Famit. ` +
      `Given the call list / lead in the task: prepare the actual call — a natural 20-second opening script + 2 concrete slot offers. ` +
      `kind MUST be "place_call"; customer_message is the OPENING SCRIPT; params MUST include ` +
      `{"to": "<person from the task>", "purpose": "confirm|rebook|reactivate", "slots": ["<slot 1>", "<slot 2>"]}. ${CONTRACT}`,
    fallback: (task) => {
      const to = nameFrom(task);
      return {
        kind: 'place_call',
        customerMessage: `Hi ${to}, this is the assistant calling from the office — just confirming your appointment. Does the scheduled time still work, or shall I move it to a better slot?`,
        params: { to, purpose: 'confirm', slots: ['tomorrow 11:00', 'tomorrow 16:30'] },
        note: 'deterministic confirm-call prep (no model available)',
      };
    },
  },
};

export function programFor(agentId: string): WorkProgram | undefined {
  return WORK_PROGRAMS[agentId];
}

/** Parse the model's action reply: strip fences/prose, take the first {...}, validate the shape.
 *  Returns null on any mismatch so the caller falls back to the deterministic action. */
export function parseAction(text: string): WorkAction | null {
  let s = text.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  const a = s.indexOf('{');
  const b = s.lastIndexOf('}');
  if (a < 0 || b <= a) return null;
  s = s.slice(a, b + 1);
  try {
    const o = JSON.parse(s) as Record<string, unknown>;
    if (typeof o.kind !== 'string' || !o.kind) return null;
    const msg = o.customer_message ?? o.customerMessage;
    return {
      kind: o.kind,
      customerMessage: typeof msg === 'string' && msg ? msg : undefined,
      params: (o.params && typeof o.params === 'object' ? o.params : {}) as Record<string, unknown>,
      note: typeof o.note === 'string' ? o.note : '',
    };
  } catch {
    return null;
  }
}
