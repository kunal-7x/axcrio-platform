/**
 * HelloSaga workflow (BUILD-SPEC §7.8 "Temporal up with HelloSaga"; §10.2 saga pattern).
 *
 * Phase-0 acceptance asks for "Temporal up with a HelloSaga." This workflow is the minimal but
 * REAL shape every Phase-1 workflow (CampaignLifecycle, LaunchSaga) will follow:
 *   1. run a forward activity that produces an effect (emit campaign.requested onto the bus),
 *   2. on failure of a later step, run its COMPENSATION (emit a rollback fact) — never leave a
 *      half-applied effect (§10.2: "never leave half-live spend").
 *
 * Workflows MUST be deterministic: this file only imports from `@temporalio/workflow` and the
 * activity *types*. All side effects (bus, OTel) live in activities.ts (the worker context).
 */

import { proxyActivities } from '@temporalio/workflow';
import type * as activities from './activities.js';

const { emitCampaignRequested, compensateCampaignRequested, greet } = proxyActivities<typeof activities>({
  startToCloseTimeout: '30 seconds',
  retry: { maximumAttempts: 3 },
});

export interface HelloSagaInput {
  tenant_id: string;
  workspace_id: string;
  correlation_id: string;
  name: string;
  /** Test hook: when true, the post-emit step throws to exercise the compensation path. */
  failAfterEmit?: boolean;
}

export interface HelloSagaResult {
  greeting: string;
  emitted_event_id: string;
  compensated: boolean;
}

/**
 * The durable HelloSaga. Returns the greeting + the emitted event id; if `failAfterEmit` is
 * set, the saga compensates the emit and rethrows (proving rollback runs durably).
 */
export async function HelloSaga(input: HelloSagaInput): Promise<HelloSagaResult> {
  const greeting = await greet(input);

  // Forward step (has a side effect on the bus).
  const { event_id } = await emitCampaignRequested(input);

  try {
    if (input.failAfterEmit) {
      // Simulate a later saga step failing (e.g. an ad set create fails in LaunchSaga).
      throw new Error('HelloSaga: simulated downstream failure after emit');
    }
    return { greeting, emitted_event_id: event_id, compensated: false };
  } catch (err) {
    // Compensate the forward effect, then rethrow so the workflow surfaces the failure.
    await compensateCampaignRequested(input, event_id);
    if (err instanceof Error) throw err;
    throw new Error('HelloSaga failed');
  }
}
