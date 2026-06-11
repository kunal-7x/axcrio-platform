/**
 * @growth-os/temporal-worker — Phase-0 Temporal proof (HelloSaga) + the worker/client wiring
 * later phases extend with CampaignLifecycle / LaunchSaga / OptimizationTick (§7.8).
 */
export { HelloSaga } from './workflows.js';
export type { HelloSagaInput, HelloSagaResult } from './workflows.js';
export * as activities from './activities.js';
export { TASK_QUEUE, HELLO_SAGA_NAMESPACE, TEMPORAL_ADDRESS } from './shared.js';
