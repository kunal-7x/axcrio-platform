/**
 * @growth-os/sdk — the typed client surface for GROWTH OS.
 *
 * - `GrowthOsClient` / `GrowthOsError`: the runtime typed fetch client.
 * - `./generated`: per-surface OpenAPI `paths`/`components` types (run `pnpm codegen:sdk`).
 * - Event payload types come from `@growth-os/events` (the event backbone is the SoT for those).
 */

export * from './client.js';

// Event payload types live in `@growth-os/events` (the event backbone is their single source of
// truth, P1). Import them directly from there — the SDK intentionally does NOT re-wrap them to
// avoid a build-order coupling and a second place that could drift.
