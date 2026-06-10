// Colocated API client for the Forms & Surveys workspace.
//
// WHY here (not lib/api.ts): this build is scoped to app/forms own files, and
// the forms-surveys router is DEFINED-NOT-MOUNTED on the live API today (it sits
// in the deferred mount checklist — REMAINING_MODULES_BUILD_STATE.md §B row 4).
// So every /forms* call 404s until the orchestrator wires build_router(...). We
// translate 404/501/503/network into a FormsDormantError sentinel the UI renders
// as a premium "not configured / coming soon" state, while a real 401 bounces to
// /login exactly like lib/api.ts. The page lights up the moment the router mounts
// — every field name below is byte-exact to forms-surveys/endpoints.py + core.py.
//
// TWO CONTRACT GOTCHAS encoded here (don't refactor away):
//   1. create_form (POST /forms) + update_form (PUT /forms/{id}) read a JSON BODY
//      (request.json()), NOT FormData. So mutations send Content-Type:
//      application/json + JSON.stringify. (lib/api.ts uses FormData — different.)
//   2. Mutations return a {status, error?} ENVELOPE: HTTP 200 with status:"ok",
//      or HTTP 400 with status:"error", error:"bad_field_type:..". We surface the
//      `error` string. Reads (/forms, /submissions, /insights) return their data
//      shape directly. See core.create_form / validate_fields for the error codes.

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

// Raised when the forms backend is not reachable as a *feature* (router not
// mounted / not implemented / unreachable). Distinct from a hard error so the
// page degrades to "coming soon" instead of an error wall.
export class FormsDormantError extends Error {
    status: number;
    constructor(status: number, message = "Forms module is not configured yet") {
        super(message);
        this.name = "FormsDormantError";
        this.status = status;
    }
}

// Raised by mutations when the {status:'error', error} envelope comes back (or a
// real HTTP error). Carries the raw backend `error` code so the form can map it
// (e.g. "bad_field_type:foo" -> a friendly message).
export class FormsActionError extends Error {
    code: string;
    constructor(message: string, code = "") {
        super(message);
        this.name = "FormsActionError";
        this.code = code;
    }
}

function bounce401(res: Response) {
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

// GET wrapper: 401 -> logout; 404/501/503 -> dormant; network -> dormant;
// other non-OK -> generic Error. Returns the parsed JSON body.
async function getJson<T>(path: string): Promise<T> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    } catch {
        throw new FormsDormantError(0, "Forms module is unreachable");
    }
    bounce401(res);
    if (res.status === 501 || res.status === 503) {
        throw new FormsDormantError(res.status);
    }
    if (res.status === 404) {
        // Discriminate: a genuine missing-form 404 from get_form carries
        // {"error":"not_found"} (endpoints.py) -> a real "not found" action error
        // the detail page renders distinctly. An UNMOUNTED-route 404 is FastAPI's
        // {"detail":"Not Found"} (or non-JSON) -> dormant "coming soon". list_forms
        // has no not-found path, so the list page only ever sees the dormant shape.
        let body: Record<string, unknown> = {};
        try {
            body = await res.json();
        } catch {
            /* non-JSON — treat as dormant below */
        }
        if (body.error === "not_found") {
            throw new FormsActionError(friendlyError("not_found"), "not_found");
        }
        throw new FormsDormantError(404);
    }
    if (!res.ok) {
        let body: Record<string, unknown> = {};
        try {
            body = await res.json();
        } catch {
            /* non-JSON */
        }
        const err = typeof body.error === "string" ? body.error : "";
        throw new Error(err || `Request failed (${res.status})`);
    }
    return res.json() as Promise<T>;
}

// Mutation wrapper (POST/PUT JSON body). Honours the {status, error} envelope:
// a 200 with status:"error" still throws a FormsActionError carrying the code.
async function sendJson<T extends { status?: string; error?: string }>(
    path: string,
    method: "POST" | "PUT",
    body: Record<string, unknown>
): Promise<T> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, {
            method,
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    } catch {
        throw new FormsDormantError(0, "Forms module is unreachable");
    }
    bounce401(res);
    if (res.status === 404 || res.status === 501) {
        throw new FormsDormantError(res.status);
    }
    let parsed: T;
    try {
        parsed = (await res.json()) as T;
    } catch {
        parsed = {} as T;
    }
    // not_configured (PG down) reads as dormant so the UI stays calm.
    if (parsed.status === "not_configured") {
        throw new FormsDormantError(503, "Forms storage is not configured yet");
    }
    if (res.status === 403) {
        throw new FormsActionError(
            "You don't have permission to do that.",
            "permission"
        );
    }
    if (!res.ok || parsed.status === "error" || parsed.status === "not_found") {
        const code = parsed.error || `request_failed_${res.status}`;
        throw new FormsActionError(friendlyError(code), code);
    }
    return parsed;
}

// Map a backend allow-list error code to a human sentence. The codes come from
// core.validate_fields / validate_submission (e.g. "bad_field_type:rating2",
// "duplicate_field_key:name", "too_many_fields", "missing_required:phone").
export function friendlyError(code: string): string {
    if (!code) return "Something went wrong. Please try again.";
    const [head, detail] = code.split(":");
    switch (head) {
        case "fields_must_be_list":
            return "The form fields are malformed.";
        case "too_many_fields":
            return "This form has too many fields. Remove a few and try again.";
        case "field_must_be_object":
            return "One of the fields is malformed.";
        case "bad_field_key":
            return `Field key "${detail}" is invalid — use lowercase letters, numbers and underscores only.`;
        case "duplicate_field_key":
            return `Duplicate field key "${detail}". Each field needs a unique key.`;
        case "bad_field_type":
            return `Unsupported field type "${detail}".`;
        case "not_found":
            return "This form no longer exists.";
        case "request_failed_403":
        case "permission":
            return "You don't have permission to do that.";
        default:
            return code.replace(/_/g, " ");
    }
}

// ── Types (byte-exact to forms-surveys/core.py rows) ─────────────────────────

export type FormKind = "form" | "survey";
export type FormStatus = "draft" | "published" | "closed";

// The 13 field types the builder allow-list accepts (core._FIELD_TYPES).
export const FIELD_TYPES = [
    "text",
    "textarea",
    "email",
    "phone",
    "number",
    "select",
    "multiselect",
    "checkbox",
    "date",
    "rating",
    "nps",
    "csat",
    "hidden",
] as const;
export type FieldType = (typeof FIELD_TYPES)[number];

// A single field definition (normalized by core.validate_fields).
export type FormField = {
    key: string;
    label: string;
    type: FieldType;
    required: boolean;
    options: string[];
};

// contact_map: which field key feeds the CRM person spine (phone/name/email).
export type ContactMap = {
    phone?: string;
    name?: string;
    email?: string;
};

// Full form row (core._row_to_dict over the `forms` table).
export type Form = {
    id: string;
    org_id?: string;
    kind: FormKind;
    title: string;
    description: string;
    public_token: string;
    status: FormStatus;
    fields: FormField[];
    settings: Record<string, unknown>;
    contact_map: ContactMap;
    data: Record<string, unknown>;
    submit_count: number;
    created_at: string | null;
    updated_at: string | null;
};

export type FormsListResponse = {
    forms: Form[];
    total: number;
    note?: string;
};

// A stored submission row (core.list_submissions).
export type Submission = {
    id: string;
    org_id?: string;
    form_id: string;
    contact_id: string;
    answers: Record<string, unknown>;
    score: number | null;
    sentiment: string;
    source_ip_hash?: string;
    lead_emitted?: boolean;
    workflow_emitted?: boolean;
    data: Record<string, unknown>;
    created_at: string | null;
};

export type SubmissionsResponse = {
    submissions: Submission[];
    total: number;
    note?: string;
};

// Per-question rollup (core.survey_insights).
export type QuestionInsight = {
    label: string;
    type: string;
    answered: number;
    counts?: Record<string, number>;
    avg?: number | null;
    count?: number;
};

export type Insights = {
    status: string;
    form_id: string;
    kind: FormKind;
    responses: number;
    nps: number | null;
    csat_avg: number | null;
    sentiment: { promoter: number; passive: number; detractor: number };
    questions: Record<string, QuestionInsight>;
    llm_summary: string | null;
    llm_enabled: boolean;
};

// /forms/status — module health (core.status()).
export type FormsStatus = {
    forms_count: number | null;
    lead_hook_wired: boolean;
    workflow_hook_wired: boolean;
    audit_wired: boolean;
    captcha_verifier_wired: boolean;
    mode: string;
    [k: string]: unknown;
};

// ── Reads ────────────────────────────────────────────────────────────────────

export async function listForms(opts?: {
    kind?: FormKind | "";
    status?: FormStatus | "";
}): Promise<FormsListResponse> {
    const params = new URLSearchParams();
    if (opts?.kind) params.set("kind", opts.kind);
    if (opts?.status) params.set("status", opts.status);
    const qs = params.toString();
    return getJson<FormsListResponse>(`/forms${qs ? `?${qs}` : ""}`);
}

export async function getForm(id: string): Promise<Form> {
    const r = await getJson<{ form: Form }>(`/forms/${encodeURIComponent(id)}`);
    return r.form;
}

export async function getSubmissions(id: string): Promise<SubmissionsResponse> {
    return getJson<SubmissionsResponse>(
        `/forms/${encodeURIComponent(id)}/submissions`
    );
}

export async function getInsights(id: string): Promise<Insights> {
    return getJson<Insights>(`/forms/${encodeURIComponent(id)}/insights`);
}

export async function getFormsStatus(): Promise<FormsStatus> {
    return getJson<FormsStatus>(`/forms/status`);
}

// ── Mutations (JSON body + envelope-aware) ───────────────────────────────────

export type CreateFormInput = {
    kind: FormKind;
    title: string;
    description?: string;
    fields?: FormField[];
    settings?: Record<string, unknown>;
    contact_map?: ContactMap;
    status?: FormStatus;
};

export async function createForm(input: CreateFormInput): Promise<Form> {
    const r = await sendJson<{ status: string; form: Form; error?: string }>(
        `/forms`,
        "POST",
        {
            kind: input.kind,
            title: input.title,
            description: input.description ?? "",
            fields: input.fields ?? [],
            settings: input.settings ?? {},
            contact_map: input.contact_map ?? {},
            status: input.status ?? "draft",
        }
    );
    return r.form;
}

export type UpdateFormInput = Partial<{
    title: string;
    description: string;
    fields: FormField[];
    settings: Record<string, unknown>;
    contact_map: ContactMap;
    status: FormStatus;
}>;

export async function updateForm(
    id: string,
    patch: UpdateFormInput
): Promise<Form> {
    const r = await sendJson<{ status: string; form: Form; error?: string }>(
        `/forms/${encodeURIComponent(id)}`,
        "PUT",
        patch as Record<string, unknown>
    );
    return r.form;
}

export async function rotateToken(id: string): Promise<string> {
    const r = await sendJson<{ status: string; public_token: string }>(
        `/forms/${encodeURIComponent(id)}/rotate-token`,
        "POST",
        {}
    );
    return r.public_token;
}
