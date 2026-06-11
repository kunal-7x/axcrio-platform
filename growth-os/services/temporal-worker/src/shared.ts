/** Shared Temporal constants (worker + client must agree on these). */
export const TASK_QUEUE = 'growth-os-phase0';
export const HELLO_SAGA_NAMESPACE = process.env.TEMPORAL_NAMESPACE ?? 'default';
export const TEMPORAL_ADDRESS = process.env.TEMPORAL_ADDRESS ?? 'localhost:7233';
