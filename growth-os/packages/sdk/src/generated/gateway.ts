/* AUTO-GENERATED from contracts/openapi/gateway.yaml — DO NOT EDIT. Run `pnpm codegen:sdk`. */

export interface paths {
    "/auth/token": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Phase-0 dev-stub token mint (D5).
         * @description Phase-0 ONLY. Mints a dev JWT for a known dev user + fixed tenant so the contract surface is exercisable before OIDC (Phase 3) is wired. The interface (packages/auth) is stable; only the issuer changes later.
         */
        post: operations["mintDevToken"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/feed": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Live SSE event feed for the dashboard (P10, §7.1 WS/SSE live feed).
         * @description Server-Sent-Events stream of tenant-scoped envelope events (the loop §3.1) for the live activity feed. RLS-scoped to the token's tenant. The data shape of each event is the canonical envelope (see schemas/event-envelope.schema.json).
         */
        get: operations["streamFeed"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Liveness probe. */
        get: operations["getHealth"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/readyz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness probe (bus + db + dependencies reachable). */
        get: operations["getReady"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Resolve the caller's tenant/workspace/role from the bearer token (P6).
         * @description The tenant-resolution endpoint. Returns the identity + tenant context the gateway derived from the token — the canonical proof that tenant is bound to the token, not the body. The dashboard calls this on load.
         */
        get: operations["getSession"];
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
        /**
         * Format: uuid
         * @description Tenant (org) id. Set from the token, NEVER accepted from the body (P6).
         */
        TenantId: string;
        /** Format: uuid */
        Uuid: string;
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
        /** @description Unexpected server error. */
        Internal: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Per-app / per-tenant rate limit exceeded (§5.3). */
        RateLimited: {
            headers: {
                "Retry-After": components["headers"]["RetryAfter"];
                "X-RateLimit-Remaining": components["headers"]["RateLimitRemaining"];
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
    };
    parameters: {
        /** @description correlation_id (journey uuid, §6.3) to scope results to one person's journey. */
        JourneyQuery: string;
    };
    requestBodies: never;
    headers: {
        /** @description Remaining requests in the current per-app/per-tenant token-bucket window (§5.3). */
        RateLimitRemaining: number;
        /** @description Seconds to wait before retrying (set on 429 / 503). */
        RetryAfter: number;
        /** @description Per-request trace id echoed for OTel correlation (P10). */
        XRequestId: string;
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    mintDevToken: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Format: email */
                    email: string;
                    /** @description Optional dev override; ignored in any non-dev environment. */
                    tenant_id?: components["schemas"]["Uuid"];
                };
            };
        };
        responses: {
            /** @description A dev JWT + its claims. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        access_token: string;
                        claims: {
                            /** @enum {string} */
                            role: "Owner" | "Admin" | "Marketer" | "Analyst" | "Approver";
                            sub: components["schemas"]["Uuid"];
                            tenant_id: components["schemas"]["TenantId"];
                            workspace_id: components["schemas"]["WorkspaceId"];
                        };
                        /** @description seconds */
                        expires_in: number;
                        /** @constant */
                        token_type: "Bearer";
                    };
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
        };
    };
    streamFeed: {
        parameters: {
            query?: {
                /** @description correlation_id (journey uuid, §6.3) to scope results to one person's journey. */
                journey?: components["parameters"]["JourneyQuery"];
                /** @description Comma-separated topic filter (e.g. campaign.requested,optimization.decision). */
                types?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description An SSE stream (text/event-stream); each `data:` line is one envelope. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
                };
            };
            401: components["responses"]["Unauthorized"];
            429: components["responses"]["RateLimited"];
        };
    };
    getHealth: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Process is alive. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @constant */
                        status: "ok";
                    };
                };
            };
        };
    };
    getReady: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Ready to serve traffic. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @description keyed by dependency name (db, bus, temporal, redis). */
                        dependencies: {
                            [key: string]: "up" | "down" | "degraded";
                        };
                        /** @enum {string} */
                        status: "ready" | "degraded";
                    };
                };
            };
            503: components["responses"]["Internal"];
        };
    };
    getSession: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Resolved session context. */
            200: {
                headers: {
                    "X-Request-Id": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @enum {string} */
                        role: "Owner" | "Admin" | "Marketer" | "Analyst" | "Approver";
                        sub: components["schemas"]["Uuid"];
                        tenant_id: components["schemas"]["TenantId"];
                        workspace_id: components["schemas"]["WorkspaceId"];
                        /** @description All workspaces the user may switch to within the tenant. */
                        workspaces?: {
                            name: string;
                            workspace_id: components["schemas"]["WorkspaceId"];
                        }[];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
}
