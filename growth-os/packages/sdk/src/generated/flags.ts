/* AUTO-GENERATED from contracts/openapi/flags.yaml — DO NOT EDIT. Run `pnpm codegen:sdk`. */

export interface paths {
    "/flags": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List boolean/string feature flags for the tenant/workspace. */
        get: operations["listFlags"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/flags/{key}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        get?: never;
        /** Set/override a single feature flag (emits config.changed). */
        put: operations["setFlag"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/policy-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current effective policy config for the tenant/workspace (§7.7). */
        get: operations["getPolicyConfig"];
        /**
         * Replace policy config (creates a new version; emits config.changed §7.7).
         * @description Full replace of the editable config block. Bumps the version monotonically and emits config.changed with a diff. Values are bounded server-side by the tenant's plan Entitlements (e.g. autopilot cannot exceed the plan ceiling).
         */
        put: operations["updatePolicyConfig"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/policy-config/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List config versions (who/when/diff) for audit (§14.3). */
        get: operations["listPolicyConfigVersions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * @description Action classes that carry independent autopilot levels (§17.1 per action-class).
         * @enum {string}
         */
        ActionClass: "research" | "creative" | "launch" | "budget_change" | "optimization" | "audience" | "messaging";
        /**
         * @description §17.1 autopilot ladder (L0 Observe .. L4 Autonomous).
         * @enum {string}
         */
        AutopilotLevel: "L0" | "L1" | "L2" | "L3" | "L4";
        Error: {
            error: {
                /**
                 * @description Stable machine-readable error code (snake_case).
                 * @example unauthorized
                 * @example forbidden
                 * @example not_found
                 * @example validation_failed
                 * @example conflict
                 * @example rate_limited
                 * @example internal
                 */
                code: string;
                /** @description Field-level validation problems, when applicable. */
                details?: {
                    issue: string;
                    /** @description JSON pointer / dotted path to the offending field. */
                    path: string;
                }[];
                /** @description Human-readable, non-PII summary. */
                message: string;
                /** @description Echoes X-Request-Id for support correlation. */
                request_id?: string;
                /** @description True if the caller may safely retry (e.g. 429/503). */
                retriable?: boolean;
            };
        };
        Page: {
            items: unknown[];
            /** @description Cursor for the next page; null when no more results. */
            next_cursor?: string | null;
            /** @description Best-effort total (may be null for large/streaming sets). */
            total_estimate?: number | null;
        };
        PolicyConfig: {
            /** @description Per action-class autopilot level (§17.1). */
            autopilot: {
                audience?: components["schemas"]["AutopilotLevel"];
                budget_change?: components["schemas"]["AutopilotLevel"];
                creative?: components["schemas"]["AutopilotLevel"];
                launch?: components["schemas"]["AutopilotLevel"];
                messaging?: components["schemas"]["AutopilotLevel"];
                optimization?: components["schemas"]["AutopilotLevel"];
                research?: components["schemas"]["AutopilotLevel"];
            };
            /** @description Budget caps the Governor enforces (§13.1 tree). */
            budget: {
                campaign_lifetime_cap_minor?: number | null;
                daily_cap_minor?: number;
                workspace_monthly_cap_minor?: number;
            };
            /** @description §18 selected pack (persona/offer/compliance/journey/KPI defaults). */
            industry_pack_id?: string | null;
            /** @description Kill-rule multipliers applied to the §12.3 guardrails (G1..G6). */
            kill_rules: {
                /**
                 * @description G5 frequency cap (cold).
                 * @default 2.5
                 */
                fatigue_frequency_7d: number;
                /**
                 * @description G4 junk-lead rate.
                 * @default 0.6
                 */
                junk_rate_threshold: number;
                /**
                 * @description G1 spend_today > N x daily cap share.
                 * @default 3
                 */
                runaway_multiplier: number;
                /**
                 * @description G3 ad-set fail threshold.
                 * @default 4
                 */
                set_fail_multiplier: number;
                /**
                 * @description G2 spend >= N x target CPqL with 0 q-leads.
                 * @default 2.5
                 */
                zero_q_multiplier: number;
            };
            /**
             * @description Tenant locale (§11 India-first; vernacular hi/gu/mr/ta/te/bn supported).
             * @default en-IN
             */
            locale: string;
            /** @description Additional languages enabled for transcreation (§I13). */
            locales_enabled?: string[];
            tenant_id: components["schemas"]["TenantId"];
            /** @description Approval thresholds (§17.2) — actions above these need human approval. */
            thresholds: {
                /** @description Max daily test spend auto-approvable at L2 (INR paise). */
                auto_test_daily_cap_minor?: number;
                /** @description Any spend-changing action above this needs approval (paise). */
                require_approval_above_minor?: number;
            };
            updated_at: components["schemas"]["Timestamp"];
            version: number;
            workspace_id?: components["schemas"]["WorkspaceId"];
        };
        /** @description Editable subset of PolicyConfig (version/updated_at/tenant_id are server-managed). */
        PolicyConfigInput: {
            /** @description Per action-class autopilot overrides; keys constrained to ActionClass. */
            autopilot?: {
                [key: string]: components["schemas"]["AutopilotLevel"];
            };
            budget?: {
                [key: string]: number | null;
            };
            industry_pack_id?: string | null;
            kill_rules?: {
                [key: string]: number;
            };
            locale?: string;
            locales_enabled?: string[];
            thresholds?: {
                [key: string]: number;
            };
        };
        PolicyConfigVersion: {
            actor: {
                id: string;
                /** @enum {string} */
                kind: "user" | "agent" | "system";
            };
            changed_at: components["schemas"]["Timestamp"];
            /** @description JSON-merge-patch style diff from the prior version. */
            diff?: {
                [key: string]: unknown;
            };
            version: number;
        };
        /**
         * Format: uuid
         * @description Tenant (org) id. Set from the token, NEVER accepted from the body (P6).
         */
        TenantId: string;
        /**
         * Format: date-time
         * @description RFC3339 / ISO-8601 UTC instant.
         */
        Timestamp: string;
        /** Format: uuid */
        WorkspaceId: string;
    };
    responses: {
        /** @description Malformed request / schema validation failed. */
        BadRequest: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description State/idempotency conflict (e.g. reused Idempotency-Key with a different body). */
        Conflict: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Authenticated but not permitted (RBAC / tenant scope). */
        Forbidden: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Resource not found within the token's tenant scope. */
        NotFound: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Missing or invalid credentials. */
        Unauthorized: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Semantically invalid (e.g. signing an already-executed action). */
        UnprocessableEntity: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
        CursorQuery: string;
        /** @description Max items to return (1..200, default 50). */
        LimitQuery: number;
        /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
        WorkspaceQuery: string;
    };
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    listFlags: {
        parameters: {
            query?: {
                /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
                workspace_id?: components["parameters"]["WorkspaceQuery"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Resolved flag map (defaults <- plan <- tenant override). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        flags: {
                            [key: string]: boolean | string | number;
                        };
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    setFlag: {
        parameters: {
            query?: {
                /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
                workspace_id?: components["parameters"]["WorkspaceQuery"];
            };
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    value: boolean | string | number;
                };
            };
        };
        responses: {
            /** @description Flag set. Emits config.changed. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        key: string;
                        value: boolean | string | number;
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
        };
    };
    getPolicyConfig: {
        parameters: {
            query?: {
                /** @description Fetch a specific historical version (audit/replay); omit for current. */
                version?: number;
                /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
                workspace_id?: components["parameters"]["WorkspaceQuery"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Effective policy config. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PolicyConfig"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    updatePolicyConfig: {
        parameters: {
            query?: {
                /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
                workspace_id?: components["parameters"]["WorkspaceQuery"];
            };
            header?: {
                /** @description Expected current version for optimistic concurrency; mismatch => 409. */
                "If-Match"?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PolicyConfigInput"];
            };
        };
        responses: {
            /** @description New version written. Emits config.changed. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PolicyConfig"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["UnprocessableEntity"];
        };
    };
    listPolicyConfigVersions: {
        parameters: {
            query?: {
                /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
                cursor?: components["parameters"]["CursorQuery"];
                /** @description Max items to return (1..200, default 50). */
                limit?: components["parameters"]["LimitQuery"];
                /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
                workspace_id?: components["parameters"]["WorkspaceQuery"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Page of version records. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        items?: components["schemas"]["PolicyConfigVersion"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
}
