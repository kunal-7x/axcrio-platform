/**
 * Trigger a HelloSaga run (BUILD-SPEC §7.8). Box-required (needs Temporal + a running worker).
 *
 *   pnpm --filter @growth-os/temporal-worker trigger:hello
 *
 * Starts the workflow, waits for the result, prints it. Used to demonstrate "Temporal up with
 * HelloSaga" once the stack boots. Pass GROWTH_OS_SAGA_FAIL=1 to exercise the compensation path.
 */

import { randomUUID } from 'node:crypto';
import { Client, Connection } from '@temporalio/client';
import type { HelloSaga, HelloSagaResult } from './workflows.js';
import { TASK_QUEUE, HELLO_SAGA_NAMESPACE, TEMPORAL_ADDRESS } from './shared.js';

async function main(): Promise<void> {
  const connection = await Connection.connect({ address: TEMPORAL_ADDRESS });
  const client = new Client({ connection, namespace: HELLO_SAGA_NAMESPACE });

  const correlation_id = randomUUID();
  const handle = await client.workflow.start<typeof HelloSaga>('HelloSaga', {
    taskQueue: TASK_QUEUE,
    workflowId: `hellosaga-${correlation_id}`,
    args: [
      {
        tenant_id: '00000000-0000-7000-8000-000000000001',
        workspace_id: '00000000-0000-7000-8000-000000000002',
        correlation_id,
        name: 'phase0',
        failAfterEmit: process.env.GROWTH_OS_SAGA_FAIL === '1',
      },
    ],
  });

  console.log(`[trigger] started workflow ${handle.workflowId}`);
  try {
    const result: HelloSagaResult = await handle.result();
    console.log('[trigger] HelloSaga result:', JSON.stringify(result, null, 2));
  } catch (err) {
    console.log('[trigger] HelloSaga failed (compensation ran):', (err as Error).message);
  } finally {
    await connection.close();
  }
}

main().catch((err) => {
  console.error('[trigger] fatal:', err);
  process.exit(1);
});
