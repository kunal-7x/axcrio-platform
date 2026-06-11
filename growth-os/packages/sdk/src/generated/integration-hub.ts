/* AUTO-GENERATED from contracts/openapi/integration-hub.yaml — DO NOT EDIT. Run `pnpm codegen:sdk`. */

export interface paths {
    "/connections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List the tenant's connected providers + health (§7.3). */
        get: operations["listConnections"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/connections/{connection_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                connection_id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        /** Fetch one connection (health, scopes, status — no secrets). */
        get: operations["getConnection"];
        put?: never;
        post?: never;
        /** Disconnect a provider (revokes + purges vault entry). */
        delete: operations["disconnect"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/connections/{connection_id}/test": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                connection_id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Test a connection's credentials + scopes (§7.3 test). */
        post: operations["testConnection"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/oauth/callback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** OAuth redirect target — exchanges code, vaults the token (§5.2). */
        get: operations["oauthCallback"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/oauth/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Begin an OAuth connect flow for a provider (§7.3 oauth-start).
         * @description Returns the provider authorize URL + a signed state. For provider=origin there is NO OAuth — a service token is issued out-of-band via tools/seed (Tenant-Zero), so origin is rejected here.
         */
        post: operations["oauthStart"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/origin/campaigns/{ref}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Famit's campaign ref (origin_ref) OR the GROWTH OS campaign id. */
                ref: string;
            };
            cookie?: never;
        };
        /** GROWTH OS campaign + media-plan + live status, RLS-scoped to the token (§3.3). */
        get: operations["originGetCampaign"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/origin/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * The ONE inbound door — Famit pushes canonical business facts (§3.2).
         * @description Batch-capable. The connector verifies the service token -> resolves the single connection -> pins tenant_id + workspace_id (P6) -> dedups on (connection_id, Idempotency-Key) for exactly-once (P3) -> normalizes each OriginEvent to the §6.1 envelope -> publishes to the bus (never inline, P2). All events in one request MUST belong to the token's connection/tenant.
         */
        post: operations["originPushEvents"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/origin/leads/{ref}/score": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Famit lead_id (origin_ref) for the lead. */
                ref: string;
            };
            cookie?: never;
        };
        /** lead.scored result so the panel can show lead quality (§3.3, §9.5). */
        get: operations["originGetLeadScore"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/origin/reports/daily": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Metrics-layer daily brief (CPL/CPqL/spend) for the panel (§3.3, §8.5). */
        get: operations["originGetDailyReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/origin/signals/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** The Signal Health card (EMQ/dedup/latency) for the panel (§3.3, §11). */
        get: operations["originGetSignalHealth"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/origin/webhook/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Provider-style webhook variant — Famit pushes raw, we normalize (§3.2).
         * @description For origins that prefer a webhook shape over the batch door. The connector maps the raw kind payload to one or more OriginEvents internally, then to envelopes.
         */
        post: operations["originPushWebhook"];
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
        Connection: {
            connection_id: components["schemas"]["Uuid"];
            created_at: components["schemas"]["Timestamp"];
            health: {
                last_checked_at?: components["schemas"]["Timestamp"];
                /** @enum {string} */
                state: "healthy" | "degraded" | "expired" | "scope_drift";
                /** Format: date-time */
                token_expires_at?: string | null;
            };
            provider: components["schemas"]["Provider"];
            scopes?: string[];
            /** @enum {string} */
            status: "active" | "degraded" | "disconnected" | "pending";
            /** @description Opaque pointer into the token vault. The token itself is NEVER returned (§5.2). */
            vault_ref?: string;
            workspace_id?: components["schemas"]["WorkspaceId"];
        };
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
        OriginAck: {
            /** @description Count of events accepted/queued to the bus. */
            accepted: number;
            /** @description Journey correlation_ids minted/resolved for the batch (§6.3). */
            correlation_ids?: string[];
            /** @description Count short-circuited by the idempotency cache (replayed, P3). */
            deduped?: number;
            idempotency_key: string;
        };
        OriginCampaignView: {
            campaign_id: string;
            /** @description Pointer to the CIB version (schemas/campaign_intelligence_brief.schema.json). */
            cib_ref?: string | null;
            /** @description Platform-reported live state (delivery, learning phase) when launched. */
            live_status?: {
                [key: string]: unknown;
            };
            /** @description Pointer to the MediaPlan (schemas/media_plan.schema.json). */
            media_plan_ref?: string | null;
            origin_ref?: string;
            /** @enum {string} */
            status: "requested" | "researching" | "compiled" | "awaiting_approval" | "launched" | "paused" | "completed";
        };
        OriginDailyReport: {
            /** @description CPL = spend/leads (paise). */
            cpl_minor?: number | null;
            /** @description CPqL = spend/qualified_leads (NORTH STAR, §8.5). */
            cpql_minor?: number | null;
            /** @constant */
            currency: "INR";
            /** Format: date */
            date: string;
            leads?: number;
            qualified_leads?: number;
            /**
             * @description Provenance label — numbers only from the metrics layer (P10, §8.6).
             * @constant
             */
            source?: "metrics_layer";
            /** @description INR paise. */
            spend_minor: number;
        };
        OriginEvent: {
            /** @description Hints the connector uses to mint/resolve correlation_id (§6.3 — E.164 phone is king in India, then ctwa_clid/fbclid). NOT authoritative tenant data. */
            correlation_hint?: {
                /** @description CTWA click id — the §11.2 loop. */
                ctwa_clid?: string;
                fbclid?: string;
                gclid?: string;
                lead_id?: string;
                /** @description E.164. */
                phone?: string;
                wamid?: string;
            };
            occurred_at: components["schemas"]["Timestamp"];
            /** @description Famit's own id (campaign_id:phone / wamid / lead_id / asset_id). */
            origin_ref: string;
            /**
             * @description The Famit-source fact type; mapped to a canonical event (§3.4).
             * @enum {string}
             */
            origin_type: "campaign.requested" | "call.completed" | "call.outcome" | "wa.message.sent" | "wa.message.received" | "wa.message.status" | "lead.captured" | "booking.created" | "booking.attended" | "sale.recorded" | "payment.received" | "creative.generated";
            /** @description Origin-native fields, normalized per the §3.4 map (e.g. duration, intents[], order_value paise). */
            payload?: {
                [key: string]: unknown;
            };
        };
        OriginLeadScore: {
            lead_ref: string;
            /** @example heuristic_v1 */
            model?: string;
            reasons?: string[];
            score: number;
            scored_at?: components["schemas"]["Timestamp"];
            /** @enum {string} */
            tier: "hot" | "warm" | "cold" | "junk";
        };
        OriginSignalHealth: {
            /** @description Fraction of journeys carrying a click-ID. */
            click_id_coverage?: number;
            /** @description Fraction of duplicate sends suppressed (target >=0.90, §8.4). */
            dedup_rate: number;
            /** @description Meta Event Match Quality on the optimization event (target >=8, §11.3). */
            emq: number | null;
            /** @description p95 source->dispatched latency (target <=900s / 15min, §11.3). */
            latency_p95_seconds: number;
            /**
             * @description Red downgrades optimizer autonomy (honesty gate, §11.3/§24).
             * @enum {string}
             */
            status: "green" | "amber" | "red";
        };
        Page: {
            items: unknown[];
            /** @description Cursor for the next page; null when no more results. */
            next_cursor?: string | null;
            /** @description Best-effort total (may be null for large/streaming sets). */
            total_estimate?: number | null;
        };
        /**
         * @description §7.3 provider catalog. `origin` = the Origin Platform Connector (Tenant Zero).
         * @enum {string}
         */
        Provider: "meta" | "google" | "waba" | "origin" | "hubspot" | "zoho" | "shopify" | "woocommerce" | "ga4";
        /**
         * Format: date-time
         * @description RFC3339 / ISO-8601 UTC instant.
         */
        Timestamp: string;
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
        /** @description State/idempotency conflict (e.g. reused Idempotency-Key with a different body). */
        Conflict: {
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
    listConnections: {
        parameters: {
            query?: {
                /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
                cursor?: components["parameters"]["CursorQuery"];
                /** @description Max items to return (1..200, default 50). */
                limit?: components["parameters"]["LimitQuery"];
                provider?: components["schemas"]["Provider"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Page of connections (NO secrets — vault refs only). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        items?: components["schemas"]["Connection"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    getConnection: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                connection_id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The connection. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Connection"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    disconnect: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                connection_id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Disconnected. Emits integration.disconnected. */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    testConnection: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                connection_id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Test result. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        checked_at: components["schemas"]["Timestamp"];
                        message?: string;
                        ok: boolean;
                        scopes_missing?: string[];
                        scopes_present?: string[];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    oauthCallback: {
        parameters: {
            query: {
                code: string;
                state: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Redirect back to the dashboard with connect result. */
            302: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["BadRequest"];
        };
    };
    oauthStart: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    provider: components["schemas"]["Provider"];
                    /** Format: uri */
                    redirect_uri?: string;
                    /** @description Requested scopes; defaults to the provider's minimal set (§5.2). */
                    scopes?: string[];
                    workspace_id?: components["schemas"]["WorkspaceId"];
                };
            };
        };
        responses: {
            /** @description Authorize URL + state to redirect the user to. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** Format: uri */
                        authorize_url: string;
                        state: string;
                    };
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
        };
    };
    originGetCampaign: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Famit's campaign ref (origin_ref) OR the GROWTH OS campaign id. */
                ref: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Campaign read projection. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OriginCampaignView"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    originPushEvents: {
        parameters: {
            query?: never;
            header: {
                /** @description Famit's source event id; exactly-once per (connection, key). */
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    events: components["schemas"]["OriginEvent"][];
                };
            };
        };
        responses: {
            /** @description Accepted + queued to the bus (or replayed from idempotency cache). */
            202: {
                headers: {
                    "X-Request-Id": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OriginAck"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            /** @description Idempotency-Key reused with a DIFFERENT body (the negative-control failure). */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            422: components["responses"]["UnprocessableEntity"];
            429: components["responses"]["RateLimited"];
        };
    };
    originGetLeadScore: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Famit lead_id (origin_ref) for the lead. */
                ref: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Lead score + tier + reasons. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OriginLeadScore"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    originGetDailyReport: {
        parameters: {
            query: {
                /** @description Report date (YYYY-MM-DD), tenant-local. */
                date: string;
                /** @description Optional workspace scope within the token's tenant (defaults to token workspace). */
                workspace_id?: components["parameters"]["WorkspaceQuery"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Daily metrics report (numbers only from the metrics layer, P10). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OriginDailyReport"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    originGetSignalHealth: {
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
            /** @description Signal health snapshot. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OriginSignalHealth"];
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    originPushWebhook: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                kind: "call" | "wa" | "lead" | "campaign";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Accepted + normalized + queued. */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OriginAck"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            409: components["responses"]["Conflict"];
            429: components["responses"]["RateLimited"];
        };
    };
}
