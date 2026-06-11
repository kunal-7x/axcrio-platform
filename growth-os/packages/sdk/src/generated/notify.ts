/* AUTO-GENERATED from contracts/openapi/notify.yaml — DO NOT EDIT. Run `pnpm codegen:sdk`. */

export interface paths {
    "/notify/channels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List configured delivery channels for the tenant (§7.6). */
        get: operations["listChannels"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/notify/channels/{channel}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                channel: components["schemas"]["ChannelKind"];
            };
            cookie?: never;
        };
        get?: never;
        /** Configure a channel (e.g. email sender, WA template namespace). */
        put: operations["configureChannel"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/notify/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List sent/in-app notifications (the in-app inbox feed). */
        get: operations["listNotifications"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/notify/preferences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get quiet-hours + per-channel preferences (§7.6 quiet hours + locale). */
        get: operations["getPreferences"];
        /** Update quiet hours + channel preferences. */
        put: operations["updatePreferences"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/notify/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send a notification through a channel (approvals/alerts/briefs §7.6).
         * @description Other modules call this to deliver. Honors quiet hours + locale + (for WA) the messaging window + per-user caps (§16.1). Idempotent on Idempotency-Key (P3). Phase 0 sink = console; the contract is unchanged when real channels arrive.
         */
        post: operations["sendNotification"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/notify/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List notification templates (locale-aware) for the tenant. */
        get: operations["listTemplates"];
        put?: never;
        /** Create a notification template. */
        post: operations["createTemplate"];
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
        Channel: {
            channel: components["schemas"]["ChannelKind"];
            /** @description Non-secret summary (e.g. WA quality rating, sender address). */
            config_summary?: {
                [key: string]: unknown;
            };
            enabled: boolean;
            /** @enum {string} */
            status?: "ready" | "degraded" | "unconfigured";
        };
        /**
         * @description §7.6 channels. WhatsApp uses the live WABA adapter (§16.1).
         * @enum {string}
         */
        ChannelKind: "in_app" | "email" | "whatsapp";
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
        Notification: {
            action_ref?: string | null;
            channel: components["schemas"]["ChannelKind"];
            created_at: components["schemas"]["Timestamp"];
            notification_id: components["schemas"]["Uuid"];
            /** @enum {string} */
            status: "queued" | "sent" | "delivered" | "failed" | "read";
            template_key?: string;
            to?: string;
        };
        Page: {
            items: unknown[];
            /** @description Cursor for the next page; null when no more results. */
            next_cursor?: string | null;
            /** @description Best-effort total (may be null for large/streaming sets). */
            total_estimate?: number | null;
        };
        Preferences: {
            /** @description Per-channel opt-in map. */
            channel_prefs: {
                [key: string]: boolean;
            };
            /** @default en-IN */
            locale: string;
            quiet_hours: {
                enabled: boolean;
                /** @example 08:00 */
                end?: string;
                /**
                 * @description tenant-local HH:mm.
                 * @example 21:00
                 */
                start?: string;
                /** @default Asia/Kolkata */
                timezone: string;
            };
        };
        SendRequest: {
            /** @description Optional ledger action id for approval cards (§17.2) — links the WA buttons. */
            action_ref?: string | null;
            channel: components["schemas"]["ChannelKind"];
            locale?: string;
            /**
             * @description critical (e.g. budget anomaly §13.2) may bypass quiet hours.
             * @default normal
             * @enum {string}
             */
            priority: "low" | "normal" | "high" | "critical";
            template_key: string;
            /** @description Recipient — user_id (in_app), email, or E.164 phone (whatsapp). */
            to: string;
            variables?: {
                [key: string]: string;
            };
        };
        Template: {
            /** @description Template body with {{variables}}. */
            body: string;
            /**
             * @description WA category (cost meter §16.1). Approvals/alerts/briefs = utility.
             * @enum {string}
             */
            category?: "utility" | "marketing" | "authentication";
            channel: components["schemas"]["ChannelKind"];
            /** @description Stable logical name, e.g. approval_request, anomaly_alert, daily_brief. */
            key: string;
            /** @default en-IN */
            locale: string;
            template_id: components["schemas"]["Uuid"];
            variables?: string[];
            /**
             * @description WA template approval status when channel=whatsapp.
             * @enum {string|null}
             */
            wa_status?: "draft" | "submitted" | "approved" | "rejected" | null;
        };
        TemplateInput: {
            body: string;
            /**
             * @default utility
             * @enum {string}
             */
            category: "utility" | "marketing" | "authentication";
            channel: components["schemas"]["ChannelKind"];
            key: string;
            /** @default en-IN */
            locale: string;
            variables?: string[];
        };
        /**
         * Format: date-time
         * @description RFC3339 / ISO-8601 UTC instant.
         */
        Timestamp: string;
        /** Format: uuid */
        Uuid: string;
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
        /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
        CursorQuery: string;
        /** @description Max items to return (1..200, default 50). */
        LimitQuery: number;
    };
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    listChannels: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Channels + their status. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        channels: components["schemas"]["Channel"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    configureChannel: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                channel: components["schemas"]["ChannelKind"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** @description Channel-specific config (no secrets returned on read). */
                    config?: {
                        [key: string]: unknown;
                    };
                    enabled: boolean;
                };
            };
        };
        responses: {
            /** @description Channel configured. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Channel"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
        };
    };
    listNotifications: {
        parameters: {
            query?: {
                /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
                cursor?: components["parameters"]["CursorQuery"];
                /** @description Max items to return (1..200, default 50). */
                limit?: components["parameters"]["LimitQuery"];
                status?: "queued" | "sent" | "delivered" | "failed" | "read";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Page of notifications. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        items?: components["schemas"]["Notification"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    getPreferences: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Preferences. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Preferences"];
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    updatePreferences: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Preferences"];
            };
        };
        responses: {
            /** @description Preferences updated. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Preferences"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
        };
    };
    sendNotification: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SendRequest"];
            };
        };
        responses: {
            /** @description Accepted for delivery (or replayed if Idempotency-Key seen, P3). */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Notification"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            409: components["responses"]["Conflict"];
            /** @description Send blocked (e.g. WA window closed, quiet hours, consent missing §5.4). */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    listTemplates: {
        parameters: {
            query?: {
                channel?: components["schemas"]["ChannelKind"];
                locale?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Page of templates. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        items?: components["schemas"]["Template"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    createTemplate: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateInput"];
            };
        };
        responses: {
            /** @description Template created. */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Template"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            409: components["responses"]["Conflict"];
        };
    };
}
