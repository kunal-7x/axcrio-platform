/* AUTO-GENERATED from contracts/openapi/ledger.yaml — DO NOT EDIT. Run `pnpm codegen:sdk`. */

export interface paths {
    "/actions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List/replay ledger entries; filter by journey, status, or target (§7.4).
         * @description GET /actions?journey={correlation_id} returns the ordered, hash-chained decision trail for one person's journey (the replay asset, §14.3). Also filterable by status and target_ref.
         */
        get: operations["listActions"];
        put?: never;
        /**
         * Propose an action — append a `proposed` ledger entry with its Explanation (P5).
         * @description Records the intended action + its Explanation (§7.4 / Appendix A) BEFORE any execution (P5 — no silent actions). The entry is appended with prev_hash/hash; it is NOT executable until signed. Idempotent on Idempotency-Key.
         */
        post: operations["proposeAction"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/actions/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        /** Fetch one ledger entry (with full plan + Explanation + signatures). */
        get: operations["getAction"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/actions/{id}/sign": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sign a proposed action — the gate connectors verify before any mutation (P4).
         * @description Transitions proposed -> signed and appends a signature over the entry hash. ONLY a signed entry authorizes the Action Executor to call a connector mutation (P4). Requires sign permission (RBAC) and, for spend/destructive plans, a firewall step-up token (mirrors the live firewall.py PIN + HS256 step-up; §17.3). Money plans require a read-back confirmation flag. Signing an already-signed/executed entry => 422 (append-only invariant).
         */
        post: operations["signAction"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/actions/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Verify the tenant's hash-chain integrity (tamper-evidence check, §5.5).
         * @description Walks the append-only chain recomputing hashes; returns ok=false + the first broken link if any entry was tampered with. Cheap integrity audit for the panel.
         */
        get: operations["verifyChain"];
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
         * ActionPlan
         * @description The SIGNED plan executed by the Action Executor (GROWTH-OS-BUILD-SPEC §7.4, §10.2, P4/P5). The ONLY object a connector will mutate from — connectors verify status=signed + a valid signature before ANY platform mutation (P4: money is sacred; no side door). Carries the §P5 Explanation (no silent actions), lives in the hash-chained Action Ledger, and is executed via the Temporal LaunchSaga with compensation (§10.2). Frozen-after-merge; new fields ⇒ version bump.
         */
        "action_plan.schema": {
            /** Format: uuid */
            action_plan_id: string;
            /**
             * @description The class of action (drives policy gate + approval thresholds). Aligns with explanation.action.type and optimization.decision vocab.
             * @enum {string}
             */
            action_type: "launch_campaign" | "pause_ad" | "pause_ad_set" | "pause_campaign" | "resume" | "trash_ad" | "promote_ad" | "scale_budget" | "throttle_budget" | "reallocate_budget" | "rotate_creative" | "draft_creative" | "expand_audience" | "dispatch_signal" | "send_broadcast" | "submit_template" | "edit_targeting" | "quarantine_creative";
            /** @description Who proposed the plan (P5: agent | user | system | webhook). */
            actor: {
                id: string;
                /** @enum {string} */
                kind: "agent" | "user" | "system" | "webhook";
            };
            /** @description Approval state when the policy gate (§17) requires a human. Temporal signal on response; auto-escalate on timeout (§17.2). */
            approval?: {
                approver_id?: string;
                /** Format: date-time */
                decided_at?: string;
                /**
                 * Format: date-time
                 * @description When the approval window expires (auto-escalation deadline).
                 */
                expires_at?: string;
                required?: boolean;
                /** @enum {string} */
                state?: "not_required" | "pending" | "granted" | "denied" | "auto_escalated" | "timed_out";
            };
            /** @description The money delta this plan introduces. P4: any spend-changing plan needs a Budget Governor stamp to be signed (§13.1). All amounts INR paise (integer). */
            budget_impact?: {
                /** @constant */
                currency?: "INR";
                /** @description Net change to daily spend, INR paise (integer; may be negative). */
                daily_delta_minor?: number;
                /** @description The Budget Governor stamp proving sum(daily budgets) ≤ daily_cap holds (§13.1/§13.2). REQUIRED before a spend-changing plan can be signed. */
                governor_stamp?: {
                    daily_cap_minor?: number;
                    stamp_id: string;
                    /** Format: date-time */
                    stamped_at: string;
                };
                spend_changing: boolean;
            };
            /** @description The event/decision that caused this plan (e.g. an optimization.decision event_id). */
            causation_id?: string;
            /** @description Journey id this plan belongs to (§6.3), so the ledger is queryable by journey (GET /actions?journey=). */
            correlation_id?: string;
            /** Format: date-time */
            created_at?: string;
            /**
             * Format: date-time
             * @description When an unsigned/unapproved plan goes stale and must not execute.
             */
            expires_at?: string;
            /** @description The mandatory §P5 Explanation emitted BEFORE execution (no silent actions). */
            explanation: components["schemas"]["explanation.schema"];
            /** @description Hash-chain linkage written by the Action Ledger (§7.4, §5.5 tamper-evident). */
            ledger?: {
                hash?: string;
                prev_hash?: string;
                sequence?: number;
            };
            /** @description The ordered, typed connector operations the Executor performs (LaunchSaga steps, §10.2). Each is idempotent (P3) and reversible-or-compensated. Connectors accept these ONLY inside a signed plan (P4). */
            operations: {
                /** @description The inverse op to run if a later step fails (LaunchSaga rollback, §10.2: never leave half-live spend). */
                compensation?: {
                    op?: string;
                    params?: {
                        [key: string]: unknown;
                    };
                };
                /**
                 * @description Which connector executes this op.
                 * @enum {string}
                 */
                connector: "meta" | "google" | "whatsapp" | "signals" | "audiences" | "catalog";
                /** @description Exactly-once key for this external mutation (P3). Stable across retries. */
                idempotency_key: string;
                /** @description The connector verb (e.g. create_campaign, update_budget, pause_entity, create_ad, dispatch_capi). */
                op: string;
                /** @description Plan-local stable id for ordering + compensation pairing. */
                op_id: string;
                /** @description Op parameters (validated by the connector's own contract). Spend-changing amounts in INR paise (integer). */
                params?: {
                    [key: string]: unknown;
                };
            }[];
            /** @description Detached signatures over the plan's canonical bytes (§7.4 signatures[]). Connectors verify at least one valid signature whose signer is authorized to sign this action_type before mutating (P4). */
            signatures?: {
                /**
                 * @example ed25519
                 * @example HS256
                 */
                alg: string;
                /** @description Base64/hex signature over the canonical plan payload (everything except signatures + ledger hash fields). */
                signature: string;
                /** Format: date-time */
                signed_at: string;
                /** @description Key id / signer identity (e.g. ledger service key id). */
                signer: string;
            }[];
            /**
             * @description Ledger lifecycle (§7.4). Connectors mutate ONLY when status=signed (P4).
             * @enum {string}
             */
            status: "proposed" | "signed" | "executing" | "executed" | "failed" | "rolled_back" | "rejected" | "expired";
            /** @description Firewall step-up proof for sensitive intents (PIN/OTP + HS256 token, sub-bound, TTL, §17.3). Required for money/destructive actions initiated via AI Manager. */
            step_up?: {
                /** @enum {string} */
                scope?: "spend" | "bulk" | "destructive";
                token_ref?: string;
            };
            /** @description The primary platform entity this plan acts on (e.g. 'meta:ad:123', 'meta:adset:456', or a media_plan_id for a launch). §7.4 target_ref. */
            target_ref?: string;
            /** @description Owning tenant. Set from the actor's token context, never from a request body (the isolation rule, P6). */
            tenant_id: string;
            /**
             * @description Schema version of the ActionPlan shape (frozen-after-merge).
             * @constant
             */
            version: "1.0.0";
            workspace_id?: string;
        };
        /**
         * @description §7.4 lifecycle. Phase 0 reaches only proposed/signed (D6 — no executor yet).
         * @enum {string}
         */
        ActionStatus: "proposed" | "signed" | "executing" | "executed" | "failed" | "rolled_back" | "rejected" | "expired";
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
         * Explanation
         * @description The plain-language 'why' that EVERY autonomous action must emit BEFORE execution (GROWTH-OS-BUILD-SPEC §P5, §17.2, §I16). Normative shape: {action, evidence[], expected_effect, confidence, reversible, approval_required, undo_plan}. Written to the Action Ledger and surfaced in the Approval Inbox and the daily brief. No silent actions (P5). Frozen-after-merge.
         */
        "explanation.schema": {
            /** @description What is being done, as a stable machine token plus human renders. e.g. trash an ad, scale an ad set, launch a campaign, dispatch a CAPI signal, send a WA broadcast. */
            action: {
                /** @description One-line English summary of the action shown to the vendor. */
                summary_en: string;
                /** @description Hindi (or tenant-locale) render of the action summary. Vernacular is first-class (§I13). */
                summary_hi?: string;
                /** @description Optional tenant-locale render when locale is neither en nor hi. */
                summary_locale?: {
                    [key: string]: string;
                };
                /**
                 * @description Canonical action verb. Aligns with ledger action_type and optimization.decision.decision vocab.
                 * @enum {string}
                 */
                type: "launch_campaign" | "pause_ad" | "pause_ad_set" | "pause_campaign" | "resume" | "trash_ad" | "promote_ad" | "scale_budget" | "throttle_budget" | "reallocate_budget" | "rotate_creative" | "draft_creative" | "expand_audience" | "dispatch_signal" | "send_broadcast" | "submit_template" | "edit_targeting" | "quarantine_creative";
            };
            /** @description Whether a human must approve before execution, given the tenant's autopilot level (§17.1) and approval policy (§17). When true, the action queues in the Approval Inbox rather than executing. */
            approval_required: boolean;
            /**
             * @description How confident the brain is in this action. Honesty rule (§12.6): below War-Game min-detectable threshold, decisions are labelled low and 'winner' claims are refused.
             * @enum {string}
             */
            confidence: "high" | "medium" | "low";
            /** @description The grounded metrics/facts that justify the action. EVERY claim carries a value and source (§9.3 rule: evidence + confidence on every claim). */
            evidence: {
                /** @description Optional threshold/baseline the value is judged against (e.g. target_CPqL, 7d_norm). */
                comparator?: string;
                /** @description The metric or fact name, ideally from the semantic metrics layer (§8.5: CPqL, qual_rate, spend, q_leads, frequency_7d, junk_rate, EMQ, etc.). */
                metric: string;
                /**
                 * @description Provenance of the value: which layer/system reported it.
                 * @enum {string}
                 */
                source?: "metrics_layer" | "platform_reported" | "posterior" | "war_game" | "benchmark" | "memory" | "signal_health" | "rule" | "ledger";
                /** @description Unit of the value where applicable (e.g. INR_paise, count, ratio, seconds, score). */
                unit?: string;
                /** @description The observed value. Number for metrics, string for categorical facts. */
                value: number | string | boolean;
                /** @description Optional time window the value was measured over (e.g. 4h, today, 7d, lifetime). */
                window?: string;
            }[];
            /** @description Optional honesty note on data sufficiency (e.g. 'needs ₹X more / Y more days' per §12.6 / §13.4 margin-aware refusal). */
            evidence_window_note?: string;
            /** @description The predicted outcome of taking this action, in plain language and (where known) quantified. e.g. 'reallocate ₹620/day to better arms'. */
            expected_effect: {
                /**
                 * @description Direction of the expected change on the primary metric.
                 * @enum {string}
                 */
                direction?: "increase" | "decrease" | "hold" | "unknown";
                /** @description Optional point estimate of the change (sign per direction). Currency amounts in INR paise (integer) per the money model. */
                magnitude?: number;
                /** @description Unit of magnitude (e.g. INR_paise, ratio, count, percent). */
                magnitude_unit?: string;
                /** @description Optional primary metric the effect is expressed in (e.g. CPqL, daily_spend, qualified_leads). */
                metric?: string;
                /** @description Optional [low, high] uncertainty band on magnitude (from War-Game / posterior). */
                range?: number[];
                /** @description Plain-language expected effect. */
                summary: string;
            };
            /** @description Whether the action can be cleanly undone (drives approval policy and trust ladder). */
            reversible: boolean;
            /** @description Optional id of the deterministic rule that fired (e.g. G2 runaway-no-qual, §12.3 guardrails), for auditability. */
            rule_ref?: string;
            /** @description The concrete steps to reverse this action if it proves wrong. e.g. 'unpause ad 123'. Required even when reversible=false (then it states why it cannot be undone and the compensating mitigation). */
            undo_plan: string;
            /**
             * @description Schema version of this Explanation shape. Bump on any field change (frozen-after-merge).
             * @constant
             */
            version?: "1.0.0";
        };
        Page: {
            items: unknown[];
            /** @description Cursor for the next page; null when no more results. */
            next_cursor?: string | null;
            /** @description Best-effort total (may be null for large/streaming sets). */
            total_estimate?: number | null;
        };
        /** @description Propose body. `plan` is a draft ActionPlan (the frozen artifact); the ledger assigns/overrides server-managed fields (action_plan_id, status=proposed, signatures, ledger hash-chain, created_at) — clients SHOULD omit them. */
        ProposeActionRequest: {
            plan: components["schemas"]["action_plan.schema"];
        };
        SignActionRequest: {
            /**
             * @description Read-back confirmation flag; must be true to sign a spend-increasing plan (§17.3).
             * @default false
             */
            confirm_money: boolean;
            /** @description The ledger.hash the signer reviewed (optimistic concurrency / "sign exactly what I saw"). Mismatch => 422. */
            expected_hash: string;
            /** @description Optional approver note recorded with the signature. */
            note?: string | null;
            /** @description Firewall HS256 step-up token (sub-bound, TTL 300s) — REQUIRED for spend/bulk/destructive plans (mirrors live firewall.py; populates action_plan.step_up). Ignored for benign plans. */
            step_up_token?: string | null;
        };
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
        /** @description correlation_id (journey uuid, §6.3) to scope results to one person's journey. */
        JourneyQuery: string;
        /** @description Max items to return (1..200, default 50). */
        LimitQuery: number;
    };
    requestBodies: never;
    headers: {
        /** @description Per-request trace id echoed for OTel correlation (P10). */
        XRequestId: string;
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    listActions: {
        parameters: {
            query?: {
                action_type?: string;
                /** @description Opaque pagination cursor returned by the previous page (Page.next_cursor). */
                cursor?: components["parameters"]["CursorQuery"];
                /** @description correlation_id (journey uuid, §6.3) to scope results to one person's journey. */
                journey?: components["parameters"]["JourneyQuery"];
                /** @description Max items to return (1..200, default 50). */
                limit?: components["parameters"]["LimitQuery"];
                status?: components["schemas"]["ActionStatus"];
                /** @description Platform target ref, e.g. "meta:ad:123". */
                target_ref?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Ordered page of ledger entries (hash-chain order preserved). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page"] & {
                        /** @description The hash of the most recent entry in this tenant's chain (integrity anchor). */
                        chain_head_hash?: string;
                        items?: components["schemas"]["action_plan.schema"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
    proposeAction: {
        parameters: {
            query?: never;
            header: {
                /** @description Exactly-once proposal key (P3). */
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProposeActionRequest"];
            };
        };
        responses: {
            /** @description Proposed. Emits action.plan.created. */
            201: {
                headers: {
                    "X-Request-Id": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["action_plan.schema"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["UnprocessableEntity"];
        };
    };
    getAction: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The ledger entry. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["action_plan.schema"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
        };
    };
    signAction: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: components["schemas"]["Uuid"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignActionRequest"];
            };
        };
        responses: {
            /** @description Signed. Emits action.plan.signed. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["action_plan.schema"];
                };
            };
            401: components["responses"]["Unauthorized"];
            /** @description Missing sign permission OR missing/invalid step-up token for a spend/destructive plan. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            404: components["responses"]["NotFound"];
            /** @description Entry not in a signable state (already signed/executed/failed). */
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
    verifyChain: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Integrity result. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        chain_head_hash?: string;
                        entries_checked: number;
                        /** Format: uuid */
                        first_broken_id?: string | null;
                        ok: boolean;
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
        };
    };
}
