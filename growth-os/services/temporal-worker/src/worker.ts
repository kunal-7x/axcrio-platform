/**
 * Temporal worker entrypoint (BUILD-SPEC §7.8, D2 — GROWTH OS owns its own Temporal).
 *
 *   pnpm --filter @growth-os/temporal-worker worker
 *
 * Connects to the Temporal server (infra/docker-compose.dev.yml → temporal:7233 on the box),
 * registers the HelloSaga workflow + its activities on the task queue, and runs until killed.
 * The activities emit canonical events onto the bus, so a durable workflow drives the event
 * backbone (the rails meeting Temporal). OTel is initialized first so worker spans are traced.
 *
 * BOX-REQUIRED: needs a running Temporal server. On the laptop without Docker this won't
 * connect — that's expected (D8 honest-env). The worker code + workflow are fully typechecked
 * + bundled here; the live run happens on a capable box / in CI's ephemeral Temporal.
 */

import { Worker, NativeConnection } from '@temporalio/worker';
import { initTracing } from '@growth-os/otel';
import * as activities from './activities.js';
import { TASK_QUEUE, HELLO_SAGA_NAMESPACE, TEMPORAL_ADDRESS } from './shared.js';

async function run(): Promise<void> {
  initTracing({ serviceName: 'temporal-worker' });

  const connection = await NativeConnection.connect({ address: TEMPORAL_ADDRESS });
  try {
    const worker = await Worker.create({
      connection,
      namespace: HELLO_SAGA_NAMESPACE,
      taskQueue: TASK_QUEUE,
      // Workflows are bundled from this path (sandboxed, deterministic).
      workflowsPath: new URL('./workflows.js', import.meta.url).pathname,
      activities,
    });
    console.log(`[temporal-worker] polling ${TASK_QUEUE} @ ${TEMPORAL_ADDRESS} (ns=${HELLO_SAGA_NAMESPACE})`);
    await worker.run();
  } finally {
    await connection.close();
  }
}

run().catch((err) => {
  console.error('[temporal-worker] fatal:', err);
  process.exit(1);
});
