// Payments-page-owned API client.
//
// Self-contained on purpose: the shared `lib/api.ts` is a cross-page file and
// must not be touched by a single-page build. This mirrors `lib/api.ts`'s
// transport exactly (same BASE, same `X-Auth` token from localStorage, same
// 401 -> /login bounce) so the Payments page speaks to the backend identically
// to every other page — it just keeps its own typed surface for `/payments/*`.
//
// The Payments backend (`droplet_work/payments/`, router prefix `/payments`) is
// DORMANT-UNTIL-CREDS: with no Razorpay/Stripe keys every endpoint degrades to
// a `not_configured` shape and never errors. The UI reads that and shows a calm
// "gateway not connected" state instead of a failure.

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(): HeadersInit {
    const token = getToken();
    return token ? { "X-Auth": token } : {};
}

async function handle401(res: Response) {
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

// A module that hasn't been mounted on the backend yet answers 404 for the
// whole `/payments/*` tree. We treat that as "dormant" (same UX as
// not_configured) rather than a hard error, so the page renders its premium
// empty/idle state on a backend that simply hasn't enabled the feature flag.
export class PaymentsUnavailable extends Error {
    constructor(msg = "Payments module is not enabled yet") {
        super(msg);
        this.name = "PaymentsUnavailable";
    }
}

async function getJSON<T>(path: string): Promise<T> {
    const res = await fetch(`${BASE}/payments${path}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) throw new PaymentsUnavailable();
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return res.json();
}

async function postForm<T>(path: string, fields: Record<string, string>): Promise<T> {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) if (v != null && v !== "") fd.append(k, v);
    const res = await fetch(`${BASE}/payments${path}`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (res.status === 404) throw new PaymentsUnavailable();
    if (res.status === 403) {
        // firewall step-up challenge or read-only role
        let body: Record<string, unknown> = {};
        try { body = await res.json(); } catch { /* non-JSON */ }
        const err = typeof body.error === "string" ? body.error : "";
        throw new Error(err || "Step-up verification required (or read-only role).");
    }
    if (!res.ok) {
        let body: Record<string, unknown> = {};
        try { body = await res.json(); } catch { /* non-JSON */ }
        const err = typeof body.error === "string" ? body.error : "";
        throw new Error(err || `Request failed (${res.status})`);
    }
    return res.json();
}

// ---- Types (match the backend contract: integer minor units are converted to
//       major units server-side at the API boundary, so amounts here are major). ----

export type ProviderStatus = "configured" | "not_configured" | "error";

export type PaymentsHealth = {
    // The module reports overall + per-provider creds status. Field names are
    // tolerant: we read `status` (overall) and a `providers` map if present.
    status?: ProviderStatus;
    configured?: boolean;
    default_provider?: string;
    currency?: string;
    providers?: Record<string, { status: ProviderStatus; display_name?: string }>;
};

// Intent state machine: created -> issued -> paid | failed | expired | refunded | partially_refunded
export type IntentStatus =
    | "created"
    | "issued"
    | "paid"
    | "failed"
    | "expired"
    | "refunded"
    | "partially_refunded";

export type PaymentIntent = {
    id: string;
    org_id?: string;
    provider: string;
    status: IntentStatus;
    amount: number;          // major units
    amount_refunded?: number;
    currency: string;
    description?: string;
    customer?: string;       // name / phone / email
    customer_phone?: string;
    customer_name?: string;
    pay_url?: string;
    created_at?: string;
    updated_at?: string;
    paid_at?: string;
};

export type CreateLinkResult = {
    status: IntentStatus | "not_configured" | "exists" | "error";
    id?: string;
    pay_url?: string;
    provider?: string;
    amount?: number;
    currency?: string;
    message?: string;
};

export type PaymentEvent = {
    id: string;
    intent_id?: string;
    kind: string;            // e.g. created / issued / paid / refund / webhook
    at: string;
    note?: string;
};

export type Followup = {
    id: string;
    intent_id: string;
    status: string;          // pending / nudged / done / ...
    attempts: number;
    max_attempts: number;
    next_attempt_at?: string;
    channel?: string;        // 'dormant' until channels land
    amount?: number;
    currency?: string;
    customer?: string;
    created_at?: string;
};

// ---- Calls ----

export async function getPaymentsHealth(): Promise<PaymentsHealth> {
    return getJSON<PaymentsHealth>("/health");
}

export async function getPaymentLinks(opts?: { status?: string; limit?: number }): Promise<{
    intents?: PaymentIntent[];
    links?: PaymentIntent[];
    items?: PaymentIntent[];
    currency?: string;
}> {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", String(opts?.limit ?? 100));
    const qs = params.toString();
    return getJSON(`/links${qs ? `?${qs}` : ""}`);
}

export async function getFollowups(opts?: { status?: string; limit?: number }): Promise<{
    followups?: Followup[];
    items?: Followup[];
    currency?: string;
}> {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    params.set("limit", String(opts?.limit ?? 100));
    const qs = params.toString();
    return getJSON(`/followups${qs ? `?${qs}` : ""}`);
}

export type CreateLinkInput = {
    amount: string;          // major units, as typed
    currency?: string;
    description?: string;
    provider?: string;
    customer?: string;
    customer_phone?: string;
    idem_key?: string;
};

export async function createPaymentLink(input: CreateLinkInput): Promise<CreateLinkResult> {
    return postForm<CreateLinkResult>("/links", {
        amount: input.amount,
        currency: input.currency || "INR",
        description: input.description || "",
        provider: input.provider || "",
        customer: input.customer || "",
        customer_phone: input.customer_phone || "",
        idem_key: input.idem_key || "",
    });
}

export async function markPaid(id: string): Promise<CreateLinkResult> {
    return postForm<CreateLinkResult>(`/links/${encodeURIComponent(id)}/mark-paid`, {});
}

export async function refundLink(id: string): Promise<CreateLinkResult> {
    return postForm<CreateLinkResult>(`/links/${encodeURIComponent(id)}/refund`, {});
}

// Normalize the list response — the backend may key the array as
// intents/links/items depending on route version; accept any.
export function pickIntents(
    r: { intents?: PaymentIntent[]; links?: PaymentIntent[]; items?: PaymentIntent[] }
): PaymentIntent[] {
    return r.intents || r.links || r.items || [];
}

export function pickFollowups(r: { followups?: Followup[]; items?: Followup[] }): Followup[] {
    return r.followups || r.items || [];
}
