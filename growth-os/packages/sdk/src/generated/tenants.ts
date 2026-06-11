/* AUTO-GENERATED from contracts/openapi/tenants.yaml — DO NOT EDIT. Run `pnpm codegen:sdk`. */

export interface paths {
    "/entitlements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Plan + entitlements for the caller's tenant (§7.2 plan entitlements).
         * @description What the tenant's plan permits — autopilot ceiling, caps, feature flags gated by plan. The flags/policy-config surface holds per-tenant overrides; this is the plan envelope they sit inside.
         */
        get: operations["getEntitlements"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/invites/{token}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Opaque invite token from the invite email/link. */
                token: string;
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept an invite (becomes a member). */
        post: operations["acceptInvite"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/me/permissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * The caller's effective permissions in the active tenant/workspace (§7.2).
         * @description Resolves role -> permission set so the dashboard/BFF can gate UI and the policy layer can pre-check. The single source of truth for "what can this user do".
         */
        get: operations["getMyPermissions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/workspaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List workspaces in the caller's tenant. */
        get: operations["listWorkspaces"];
        put?: never;
        /** Create a workspace (vendor/brand) within the tenant. */
        post: operations["createWorkspace"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/workspaces/{workspace_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        /** Fetch one workspace. */
        get: operations["getWorkspace"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update a workspace. */
        patch: operations["updateWorkspace"];
        trace?: never;
    };
    "/workspaces/{workspace_id}/invites": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Invite a user to a workspace with a role. */
        post: operations["createInvite"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/workspaces/{workspace_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        /** List members of a workspace. */
        get: operations["listMembers"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/workspaces/{workspace_id}/members/{member_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                member_id: components["schemas"]["Uuid"];
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove a member from the workspace. */
        delete: operations["removeMember"];
        options?: never;
        head?: never;
        /** Change a member's role. */
        patch: operations["updateMemberRole"];
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        Entitlements: {
            /** @enum {string} */
            autopilot_ceiling?: "L0" | "L1" | "L2" | "L3" | "L4";
            /** @description Plan-gated feature flags (per-tenant overrides live in flags surface). */
            features?: {
                [key: string]: boolean;
            };
            limits?: {
                max_members?: number;
                max_workspaces?: number;
                /** @description INR paise; null = unlimited within plan. */
                monthly_managed_spend_cap_minor?: number | null;
            };
            /**
             * @example trial
             * @example starter
             * @example growth
             * @example scale
             */
            plan: string;
            tenant_id: components["schemas"]["TenantId"];
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
        Invite: {
            created_at: components["schemas"]["Timestamp"];
            /** Format: email */
            email: string;
            expires_at?: components["schemas"]["Timestamp"];
            invite_id: components["schemas"]["Uuid"];
            role: components["schemas"]["Role"];
            /** @enum {string} */
            status: "pending" | "accepted" | "revoked" | "expired";
        };
        Member: {
            /** Format: email */
            email: string;
            member_id: components["schemas"]["Uuid"];
            role: components["schemas"]["Role"];
            /** @enum {string} */
            status: "active" | "invited" | "suspended";
            user_id: components["schemas"]["Uuid"];
        };
        Page: {
            items: unknown[];
            /** @description Cursor for the next page; null when no more results. */
            next_cursor?: string | null;
            /** @description Best-effort total (may be null for large/streaming sets). */
            total_estimate?: number | null;
        };
        Permissions: {
            /**
             * @description Max autopilot level this user/plan may operate at (§17.1).
             * @enum {string}
             */
            autopilot_ceiling?: "L0" | "L1" | "L2" | "L3" | "L4";
            /** @description Flat permission strings (resource:action), e.g. campaign:create, action:sign. */
            permissions: string[];
            role: components["schemas"]["Role"];
            tenant_id: components["schemas"]["TenantId"];
            workspace_id: components["schemas"]["WorkspaceId"];
        };
        /**
         * @description §7.2 role set.
         * @enum {string}
         */
        Role: "Owner" | "Admin" | "Marketer" | "Analyst" | "Approver";
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
        Uuid: string;
        Workspace: {
            created_at: components["schemas"]["Timestamp"];
            /**
             * @description §5.1 per-tenant data-residency tag (v1 Mumbai).
             * @default ap-south-1
             */
            data_residency: string;
            industry_pack_id?: string | null;
            /** @default en-IN */
            locale: string;
            name: string;
            tenant_id: components["schemas"]["TenantId"];
            workspace_id: components["schemas"]["WorkspaceId"];
        };
        WorkspaceCreate: {
            industry_pack_id?: string;
            /** @default en-IN */
            locale: string;
            name: string;
        };
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
    getEntitlements: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Plan + entitlement set. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Entitlements"];
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    acceptInvite: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Opaque invite token from the invite email/link. */
                token: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Invite accepted. Emits tenant.member.added. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Member"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
        };
    };
    getMyPermissions: {
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
            /** @description Effective permission set. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Permissions"];
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    listWorkspaces: {
        parameters: {
            query?: {
                /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
                cursor?: components["parameters"]["CursorQuery"];
                /** @description Max items to return (1..200, default 50). */
                limit?: components["parameters"]["LimitQuery"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Page of workspaces. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        items?: components["schemas"]["Workspace"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    createWorkspace: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceCreate"];
            };
        };
        responses: {
            /** @description Workspace created. Emits tenant.workspace.created. */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workspace"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            409: components["responses"]["Conflict"];
        };
    };
    getWorkspace: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The workspace. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workspace"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    updateWorkspace: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** @description §18 industry pack id (config selected at onboarding). */
                    industry_pack_id?: string;
                    /**
                     * @example en-IN
                     * @example hi-IN
                     * @example gu-IN
                     */
                    locale?: string;
                    name?: string;
                };
            };
        };
        responses: {
            /** @description Updated. Emits tenant.workspace.updated. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workspace"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
        };
    };
    createInvite: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Format: email */
                    email: string;
                    role: components["schemas"]["Role"];
                };
            };
        };
        responses: {
            /** @description Invite created. Emits tenant.invite.created. */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Invite"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            409: components["responses"]["Conflict"];
        };
    };
    listMembers: {
        parameters: {
            query?: {
                /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
                cursor?: components["parameters"]["CursorQuery"];
                /** @description Max items to return (1..200, default 50). */
                limit?: components["parameters"]["LimitQuery"];
            };
            header?: never;
            path: {
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Page of members. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        items?: components["schemas"]["Member"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    removeMember: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                member_id: components["schemas"]["Uuid"];
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Removed. Emits tenant.member.removed. */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
        };
    };
    updateMemberRole: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                member_id: components["schemas"]["Uuid"];
                workspace_id: components["schemas"]["WorkspaceId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    role: components["schemas"]["Role"];
                };
            };
        };
        responses: {
            /** @description Role updated. Emits tenant.member.role_changed. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Member"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
        };
    };
}
