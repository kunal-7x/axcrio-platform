/**
 * Action dispatcher — where a workforce action stops being text and becomes WORK.
 *
 * Rules (the same money-law the whole cloud follows):
 *   • money actions (budget_shift, …) NEVER execute on their own — they park 'awaiting_approval'
 *     and a human approves them (the approve endpoint re-dispatches with approval).
 *   • external sends deliver FOR REAL only when the provider creds are present
 *     (WhatsApp Cloud API / Resend email); without creds they are honestly 'prepared' —
 *     the full deliverable is there, one env var away from sending. Never fake a send.
 *   • internal records (ledger entries, call prep, anything else) execute for real as
 *     structured records in the agent's Drive workspace.
 */

import type { WorkAction } from './work-programs.js';

export type ActionStatus = 'recorded' | 'prepared' | 'sent' | 'awaiting_approval' | 'failed';

export interface AgentAction extends WorkAction {
  at: string;
  instId: string;
  agentId: string;
  role: string;
  status: ActionStatus;
  statusNote: string;
  /** The action-log file name (set at write time; the approve endpoint addresses it by this). */
  name?: string;
}

export interface DispatchOpts {
  money?: boolean;
  approved?: boolean;
  fetchImpl?: typeof fetch;
  env?: NodeJS.ProcessEnv;
}

export async function dispatch(action: WorkAction, opts: DispatchOpts = {}): Promise<{ status: ActionStatus; statusNote: string }> {
  const env = opts.env ?? process.env;
  const doFetch = opts.fetchImpl ?? (globalThis as { fetch: typeof fetch }).fetch;

  // Money parks. Always. Approval re-enters here with approved=true.
  if (opts.money && !opts.approved) {
    return { status: 'awaiting_approval', statusNote: 'money action — parked for founder approval, never moves alone' };
  }

  switch (action.kind) {
    case 'send_whatsapp': {
      const token = env.WHATSAPP_TOKEN;
      const phoneId = env.WHATSAPP_PHONE_ID;
      const to = String((action.params.to as string) ?? '');
      // Real delivery needs the WhatsApp Cloud API creds AND a real phone number to send to.
      if (token && phoneId && /^\+?\d{10,15}$/.test(to.replace(/[\s-]/g, ''))) {
        try {
          const r = await doFetch(`https://graph.facebook.com/v20.0/${phoneId}/messages`, {
            method: 'POST',
            headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
            body: JSON.stringify({
              messaging_product: 'whatsapp',
              to: to.replace(/[\s-]/g, ''),
              type: 'text',
              text: { body: action.customerMessage ?? '' },
            }),
          });
          if (!r.ok) return { status: 'failed', statusNote: `WhatsApp API responded ${r.status}` };
          return { status: 'sent', statusNote: `delivered via WhatsApp Cloud API to ${to}` };
        } catch (err) {
          return { status: 'failed', statusNote: `WhatsApp send failed: ${err instanceof Error ? err.message : String(err)}` };
        }
      }
      return {
        status: 'prepared',
        statusNote:
          token && phoneId
            ? `message ready — '${to}' is not a sendable number (need +91… format from the task)`
            : 'message ready — set WHATSAPP_TOKEN + WHATSAPP_PHONE_ID to deliver for real',
      };
    }

    case 'send_reply':
    case 'send_email': {
      const channel = String((action.params.channel as string) ?? (action.kind === 'send_email' ? 'email' : 'whatsapp'));
      if (channel === 'email') {
        const key = env.RESEND_API_KEY;
        const to = String((action.params.to as string) ?? '');
        if (key && /.+@.+\..+/.test(to)) {
          try {
            const r = await doFetch('https://api.resend.com/emails', {
              method: 'POST',
              headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json' },
              body: JSON.stringify({
                from: env.WORKFORCE_FROM_EMAIL ?? 'workforce@famit.in',
                to: [to],
                subject: String((action.params.summary as string) ?? 'Re: your request'),
                text: action.customerMessage ?? '',
              }),
            });
            if (!r.ok) return { status: 'failed', statusNote: `email API responded ${r.status}` };
            return { status: 'sent', statusNote: `delivered via email to ${to}` };
          } catch (err) {
            return { status: 'failed', statusNote: `email send failed: ${err instanceof Error ? err.message : String(err)}` };
          }
        }
        return { status: 'prepared', statusNote: key ? `reply ready — '${to}' is not a sendable address` : 'reply ready — set RESEND_API_KEY to deliver for real' };
      }
      // whatsapp-channel replies reuse the WhatsApp door.
      return dispatch({ ...action, kind: 'send_whatsapp' }, { ...opts, money: false });
    }

    case 'place_call':
      // Voice dials from the India-side box (placement law) — the call pack is fully prepared.
      return { status: 'prepared', statusNote: 'call pack ready (script + slots) — voice dialing wires to the India voice box' };

    default:
      // ledger_entry, budget_shift-after-approval, and any structured record: real, durable work.
      return { status: 'recorded', statusNote: 'structured record written to the agent workspace' };
  }
}
