/**
 * GROWTH OS envelope + payload validator (P1 contracts-first, P2 event-sourced).
 *
 * The committed JSON Schemas under `contracts/schemas/` are the SOURCE OF TRUTH.
 * This validator loads them into a single ajv (2020-12) instance and validates every
 * envelope at emit/consume time, so a drift between code and contract is caught at
 * runtime (not just in CI). The envelope schema validates the outer shape; the
 * `<type>.schema.json` keyed off `type` validates the `payload`.
 *
 * LEARNING (carried from the contracts work): ajv rejects compiling the same `$id`
 * twice — register each schema ONCE via addSchema, then resolve with getSchema($id).
 * Use strict:false + allowUnionTypes for the 2020-12 docs that carry `x-` keywords.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
// ajv ships a CJS module with an ESM-default-export shim. Under NodeNext + esModuleInterop the
// default import resolves to a namespace, not the callable constructor — so we import the NAMED
// `Ajv2020` export (typed as the class: usable as both a type and a value) and normalize the
// addFormats default to its callable form (interop-safe across bundlers).
import { Ajv2020, type ValidateFunction } from 'ajv/dist/2020.js';
import addFormatsImport, { type FormatsPlugin } from 'ajv-formats';

type Ajv2020Instance = InstanceType<typeof Ajv2020>;
const addFormats = ((addFormatsImport as unknown as { default?: unknown }).default ??
  addFormatsImport) as FormatsPlugin;

const ENVELOPE_ID = 'https://contracts.growth-os.dev/schemas/event-envelope.schema.json';

/** Locate the repo's contracts/schemas dir. Overridable via GROWTH_OS_CONTRACTS_DIR (CI/box). */
function resolveSchemasDir(): string {
  const fromEnv = process.env.GROWTH_OS_CONTRACTS_DIR;
  if (fromEnv) return resolve(fromEnv);
  // packages/events/src/validator.ts -> repo root is three levels up.
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, '..', '..', '..', 'contracts', 'schemas');
}

export interface EnvelopeValidationError {
  ok: false;
  /** 'envelope' if the outer shape failed, otherwise the event type whose payload failed. */
  where: 'envelope' | string;
  errors: string[];
}
export interface EnvelopeValidationOk {
  ok: true;
}
export type EnvelopeValidationResult = EnvelopeValidationOk | EnvelopeValidationError;

export class EventValidator {
  private readonly ajv: Ajv2020Instance;
  private readonly schemasDir: string;
  /** type -> compiled payload validator (lazy). */
  private readonly payloadCache = new Map<string, ValidateFunction | null>();
  private envelopeValidate: ValidateFunction | null = null;

  constructor(schemasDir = resolveSchemasDir()) {
    this.schemasDir = schemasDir;
    this.ajv = new Ajv2020({
      strict: false,
      allowUnionTypes: true,
      allErrors: true,
      // We register every schema up-front so cross-$ref ($ref to explanation.schema.json
      // etc.) resolves without network loads.
      loadSchema: undefined,
    });
    addFormats(this.ajv);
    this.loadAllSchemas();
  }

  /** Register every *.schema.json once (by its $id) so $refs resolve in-memory. */
  private loadAllSchemas(): void {
    let files: string[];
    try {
      files = readdirSync(this.schemasDir).filter((f) => f.endsWith('.schema.json'));
    } catch (err) {
      throw new Error(
        `EventValidator: cannot read contracts schemas dir '${this.schemasDir}': ${(err as Error).message}. ` +
          `Set GROWTH_OS_CONTRACTS_DIR to the repo's contracts/schemas path.`,
      );
    }
    for (const file of files) {
      const raw = readFileSync(join(this.schemasDir, file), 'utf8');
      const schema = JSON.parse(raw) as { $id?: string };
      if (!schema.$id) continue;
      if (this.ajv.getSchema(schema.$id)) continue; // already registered (idempotent)
      this.ajv.addSchema(schema, schema.$id);
    }
  }

  private getEnvelopeValidator(): ValidateFunction {
    if (this.envelopeValidate) return this.envelopeValidate;
    const v = this.ajv.getSchema(ENVELOPE_ID);
    if (!v) throw new Error(`EventValidator: envelope schema not registered (${ENVELOPE_ID})`);
    this.envelopeValidate = v as ValidateFunction;
    return this.envelopeValidate;
  }

  /** Resolve the payload validator for an event type, or null if no schema is committed. */
  private getPayloadValidator(type: string): ValidateFunction | null {
    if (this.payloadCache.has(type)) return this.payloadCache.get(type) ?? null;
    const id = `https://contracts.growth-os.dev/schemas/${type}.schema.json`;
    const v = (this.ajv.getSchema(id) as ValidateFunction | undefined) ?? null;
    this.payloadCache.set(type, v);
    return v;
  }

  /**
   * Validate a full envelope (outer shape) AND its payload against the committed schemas.
   * Returns a structured result rather than throwing, so callers decide how to react
   * (drop vs DLQ vs error response). Unknown types: the envelope still validates; the
   * payload is left unvalidated (forward-compat) but flagged in `where`.
   */
  validateEnvelope(envelope: unknown): EnvelopeValidationResult {
    const env = this.getEnvelopeValidator();
    if (!env(envelope)) {
      return { ok: false, where: 'envelope', errors: formatErrors(env) };
    }
    const type = (envelope as { type: string }).type;
    const payload = (envelope as { payload: unknown }).payload;
    const payloadValidator = this.getPayloadValidator(type);
    if (!payloadValidator) {
      // No committed payload schema (e.g. a not-yet-frozen type). Outer shape is valid.
      return { ok: true };
    }
    if (!payloadValidator(payload)) {
      return { ok: false, where: type, errors: formatErrors(payloadValidator) };
    }
    return { ok: true };
  }

  /** Validate just a payload for a given type (used by services constructing events). */
  validatePayload(type: string, payload: unknown): EnvelopeValidationResult {
    const v = this.getPayloadValidator(type);
    if (!v) return { ok: true };
    if (!v(payload)) return { ok: false, where: type, errors: formatErrors(v) };
    return { ok: true };
  }
}

function formatErrors(v: ValidateFunction): string[] {
  return (v.errors ?? []).map((e) => `${e.instancePath || '/'} ${e.message ?? 'invalid'}`);
}

/** Lazily-built process-wide singleton (cheap to share; schemas are immutable). */
let singleton: EventValidator | null = null;
export function getEventValidator(): EventValidator {
  if (!singleton) singleton = new EventValidator();
  return singleton;
}

/**
 * Thrown at the bus publish/consume boundary when an event is off-contract (P2: nothing
 * off-contract on the bus). Carries the structured ajv errors for DLQ/logging.
 */
export class OffContractEventError extends Error {
  constructor(
    message: string,
    public readonly where: string,
    public readonly errors: string[],
    public readonly eventType?: string,
  ) {
    super(message);
    this.name = 'OffContractEventError';
  }
}

/**
 * STRICT boundary check used by the typed producer/consumer (`bus.ts`).
 *
 * Unlike `validateEnvelope` (which is lenient on a not-yet-frozen type for forward-compat),
 * this REJECTS an unknown event type when `knownTypes` is supplied — the producer always
 * passes the frozen catalog, so a typo'd or off-contract `type` cannot reach the bus. This
 * is the "rejects off-contract events" rail the spec calls for.
 *
 * @param knownTypes the frozen event catalog (EVENT_CATALOG keys); when provided, a `type`
 *                   outside it is rejected as `unknown_type`.
 */
export function assertOnContract(
  envelope: unknown,
  opts: { validator?: EventValidator; knownTypes?: readonly string[] } = {},
): void {
  const validator = opts.validator ?? getEventValidator();
  const type = (envelope as { type?: unknown })?.type;
  if (opts.knownTypes && (typeof type !== 'string' || !opts.knownTypes.includes(type))) {
    throw new OffContractEventError(
      `unknown / off-contract event type '${String(type)}'`,
      'unknown_type',
      [`type '${String(type)}' is not in the frozen catalog`],
      typeof type === 'string' ? type : undefined,
    );
  }
  const result = validator.validateEnvelope(envelope);
  if (!result.ok) {
    throw new OffContractEventError(
      `event failed ${result.where} validation`,
      result.where,
      result.errors,
      typeof type === 'string' ? type : undefined,
    );
  }
}
