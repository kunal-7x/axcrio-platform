/**
 * Contract validator for the CORE app (P1 contracts-first).
 *
 * Validates request/response bodies against the COMMITTED JSON Schemas under
 * contracts/schemas (the source of truth). Used to:
 *   - validate an incoming ActionPlan on POST /actions (reject off-contract plans), and
 *   - assert the ledger entry we return conforms to action_plan.schema.json before responding.
 *
 * Loads every *.schema.json once into a single ajv 2020 instance (cross-$ref resolves
 * in-memory). Path is overridable via GROWTH_OS_CONTRACTS_DIR for box/CI.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Injectable } from '@nestjs/common';
// ajv ships CJS with an ESM-default shim; under NodeNext+esModuleInterop the default import
// resolves to a namespace (not callable). Import the NAMED class + normalize addFormats interop.
import { Ajv2020, type ValidateFunction } from 'ajv/dist/2020.js';
import addFormatsImport, { type FormatsPlugin } from 'ajv-formats';

type Ajv2020Instance = InstanceType<typeof Ajv2020>;
const addFormats = ((addFormatsImport as unknown as { default?: unknown }).default ??
  addFormatsImport) as FormatsPlugin;

function resolveSchemasDir(): string {
  const fromEnv = process.env.GROWTH_OS_CONTRACTS_DIR;
  if (fromEnv) return resolve(fromEnv);
  // services/core/src/common/contract-validator.ts -> repo root is four levels up.
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, '..', '..', '..', '..', 'contracts', 'schemas');
}

export interface ContractCheck {
  ok: boolean;
  errors: string[];
}

@Injectable()
export class ContractValidator {
  private readonly ajv: Ajv2020Instance;
  private readonly cache = new Map<string, ValidateFunction | null>();

  constructor(schemasDir = resolveSchemasDir()) {
    this.ajv = new Ajv2020({ strict: false, allowUnionTypes: true, allErrors: true });
    addFormats(this.ajv);
    for (const file of readdirSync(schemasDir).filter((f) => f.endsWith('.schema.json'))) {
      const schema = JSON.parse(readFileSync(join(schemasDir, file), 'utf8')) as { $id?: string };
      if (schema.$id && !this.ajv.getSchema(schema.$id)) this.ajv.addSchema(schema, schema.$id);
    }
  }

  private validator(schemaStem: string): ValidateFunction | null {
    if (this.cache.has(schemaStem)) return this.cache.get(schemaStem) ?? null;
    const id = `https://contracts.growth-os.dev/schemas/${schemaStem}.schema.json`;
    const v = (this.ajv.getSchema(id) as ValidateFunction | undefined) ?? null;
    this.cache.set(schemaStem, v);
    return v;
  }

  /** Validate `data` against contracts/schemas/<schemaStem>.schema.json. */
  check(schemaStem: string, data: unknown): ContractCheck {
    const v = this.validator(schemaStem);
    if (!v) return { ok: false, errors: [`no committed schema '${schemaStem}'`] };
    if (v(data)) return { ok: true, errors: [] };
    return {
      ok: false,
      errors: (v.errors ?? []).map((e) => `${e.instancePath || '/'} ${e.message ?? 'invalid'}`),
    };
  }

  /** Validate the ActionPlan artifact specifically (the ledger entry shape). */
  checkActionPlan(plan: unknown): ContractCheck {
    return this.check('action_plan', plan);
  }
}
