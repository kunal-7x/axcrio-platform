// Self-contained Booking API client.
//
// Lives under the Booking route's OWN folder (NOT shared lib/api.ts) so this
// page can ship without touching shared files. It mirrors lib/api.ts's BASE +
// auth-header + 401 conventions exactly, and every call is dormant-safe: when
// the backend module is unmounted (404 / network error) or Postgres is down
// (the engine returns {status:"not_configured"}), these helpers resolve to a
// typed "not_configured" shape instead of throwing — the page renders a
// graceful "coming soon / not configured" state rather than an error.
//
// Backend contract: droplet_work/booking/router.py (prefix /booking) +
// core.py response shapes. Endpoints:
//   GET  /booking/status
//   POST /booking/resources
//   GET  /booking/availability?resource_id=&day=
//   POST /booking/book
//   GET  /booking/bookings?contact_id=&status=&limit=
//   GET  /booking/bookings/{id}
//   POST /booking/bookings/{id}/{reschedule,cancel,complete}
//   POST /booking/tick?dry_run=

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

// ---------------------------------------------------------------------------
// Types — match core.py response shapes verbatim.
// ---------------------------------------------------------------------------
export type ModuleStatus = "ok" | "not_configured" | "error" | "noop" | "conflict";

export type BookingConfig = {
    configured: boolean; // calendar integration ready
    pg_available: boolean; // core booking ready (no creds needed)
    reminders_enabled: boolean;
    calendar_sync_enabled: boolean;
    calendar_configured: boolean;
    google_client_present: boolean;
    google_token_present: boolean;
    default_slot_minutes: number;
    default_timezone: string;
    no_show_grace_minutes: number;
    var_root: string;
};

export type CalendarStatus = {
    configured?: boolean;
    status?: string;
    [k: string]: unknown;
};

export type BookingStatusResponse = {
    booking: BookingConfig;
    calendar: CalendarStatus;
};

export type Resource = {
    id: string;
    org_id?: string;
    name: string;
    kind: string;
    timezone: string;
    slot_minutes: number;
    capacity: number;
    windows?: AvailabilityWindow[];
};

export type AvailabilityWindow = {
    dow: number; // 0=Mon ... 6=Sun
    start: string; // "HH:MM"
    end: string; // "HH:MM"
};

export type FreeSlot = {
    slot_start: string; // ISO
    slot_end: string; // ISO
    remaining: number;
};

export type Availability = {
    status: ModuleStatus;
    resource_id?: string;
    day?: string;
    slot_minutes?: number;
    free?: FreeSlot[];
    reason?: string;
};

// Bookings come in two shapes: the list row (lean) and the detail row.
export type BookingRow = {
    id: string;
    resource_id: string;
    contact_id: string;
    phone_display: string;
    name: string;
    status: string; // booked | rescheduled | cancelled | completed | no_show
    slot_start: string; // ISO (slot_start_raw)
    slot_end: string;
    title: string;
    source?: string;
    campaign_id?: string;
};

export type BookingsList = {
    status: ModuleStatus;
    bookings?: BookingRow[];
    count?: number;
    reason?: string;
};

export type BookResult = {
    ok?: boolean;
    status: ModuleStatus;
    booking?: Partial<BookingRow> & { id?: string };
    reason?: string;
    detail?: string;
};

export type MutationResult = {
    ok?: boolean;
    status: ModuleStatus;
    booking_id?: string;
    new_status?: string;
    booking?: Partial<BookingRow>;
    reason?: string;
    detail?: string;
};

export type TickCandidate = {
    reminder_id: string;
    org_id: string;
    booking_id: string;
    kind: string;
    channel: string;
    template: string;
    skip?: string;
    job_id?: string;
    hold_id?: number | null;
};

export type TickResult = {
    status: ModuleStatus;
    fired: TickCandidate[];
    skipped: TickCandidate[];
    no_shows: { booking_id: string; org_id: string }[];
    enqueued: number;
    dry_run: boolean;
    reason?: string;
};

// Sentinel returned when the module is unmounted / unreachable. Distinct from a
// genuine backend "not_configured" only in `reason`, so the UI treats both the
// same (dormant), never as a hard error.
export const DORMANT: { status: "not_configured"; reason: string } = {
    status: "not_configured",
    reason: "module_unreachable",
};

// Core GET helper that NEVER throws for dormant/unmounted backends. A 404
// (router not mounted) or a network error resolves to a dormant sentinel; only
// a genuinely malformed authed response surfaces as a thrown error to callers
// that opt in. Most callers swallow and branch on `status`.
async function safeGet<T>(path: string): Promise<T | typeof DORMANT> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    } catch {
        return DORMANT; // network / not deployed
    }
    await handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) return DORMANT;
    if (!res.ok) return DORMANT;
    try {
        return (await res.json()) as T;
    } catch {
        return DORMANT;
    }
}

async function safePost<T>(path: string, body?: BodyInit): Promise<T | typeof DORMANT> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, {
            method: "POST",
            headers: { ...authHeaders() },
            body,
        });
    } catch {
        return DORMANT;
    }
    await handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) return DORMANT;
    if (!res.ok) {
        // Try to surface a typed backend error body (forbidden / db_error) so the
        // page can toast it; fall back to dormant for anything unparseable.
        try {
            return (await res.json()) as T;
        } catch {
            return DORMANT;
        }
    }
    try {
        return (await res.json()) as T;
    } catch {
        return DORMANT;
    }
}

export function isDormant(r: unknown): r is typeof DORMANT {
    return (
        !!r &&
        typeof r === "object" &&
        (r as { status?: string }).status === "not_configured"
    );
}

// JSON-body POST. The booking router reads `payload: dict = Body(default={})`
// (a JSON object), unlike the legacy FormData endpoints — so we send JSON.
function jsonBody(obj: Record<string, unknown>): BodyInit {
    return JSON.stringify(obj);
}
function jsonHeaders(): HeadersInit {
    return { ...authHeaders(), "Content-Type": "application/json" };
}

async function safePostJson<T>(
    path: string,
    obj: Record<string, unknown>
): Promise<T | typeof DORMANT> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, {
            method: "POST",
            headers: jsonHeaders(),
            body: jsonBody(obj),
        });
    } catch {
        return DORMANT;
    }
    await handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) return DORMANT;
    if (!res.ok) {
        try {
            return (await res.json()) as T;
        } catch {
            return DORMANT;
        }
    }
    try {
        return (await res.json()) as T;
    } catch {
        return DORMANT;
    }
}

// ---------------------------------------------------------------------------
// Public API surface
// ---------------------------------------------------------------------------
export async function getBookingStatus(): Promise<BookingStatusResponse | typeof DORMANT> {
    return safeGet<BookingStatusResponse>("/booking/status");
}

export async function getAvailability(
    resourceId: string,
    day: string
): Promise<Availability | typeof DORMANT> {
    const qs = new URLSearchParams({ resource_id: resourceId, day }).toString();
    return safeGet<Availability>(`/booking/availability?${qs}`);
}

export async function listBookings(opts?: {
    contact_id?: string;
    status?: string;
    limit?: number;
}): Promise<BookingsList | typeof DORMANT> {
    const params = new URLSearchParams();
    if (opts?.contact_id) params.set("contact_id", opts.contact_id);
    if (opts?.status) params.set("status", opts.status);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return safeGet<BookingsList>(`/booking/bookings${qs ? `?${qs}` : ""}`);
}

export async function createResource(payload: {
    name: string;
    kind?: string;
    timezone?: string;
    slot_minutes?: number;
    capacity?: number;
    windows?: AvailabilityWindow[];
}): Promise<BookResult | typeof DORMANT> {
    return safePostJson<BookResult>("/booking/resources", payload as Record<string, unknown>);
}

export async function book(payload: {
    resource_id: string;
    phone: string;
    slot_start: string;
    slot_end?: string;
    name?: string;
    title?: string;
    notes?: string;
    source?: string;
    campaign_id?: string;
}): Promise<BookResult | typeof DORMANT> {
    return safePostJson<BookResult>("/booking/book", payload as Record<string, unknown>);
}

export async function rescheduleBooking(
    id: string,
    slot_start: string,
    slot_end?: string
): Promise<MutationResult | typeof DORMANT> {
    return safePostJson<MutationResult>(`/booking/bookings/${encodeURIComponent(id)}/reschedule`, {
        slot_start,
        ...(slot_end ? { slot_end } : {}),
    });
}

export async function cancelBooking(
    id: string,
    reason?: string
): Promise<MutationResult | typeof DORMANT> {
    return safePostJson<MutationResult>(`/booking/bookings/${encodeURIComponent(id)}/cancel`, {
        reason: reason || "",
    });
}

export async function completeBooking(
    id: string
): Promise<MutationResult | typeof DORMANT> {
    return safePost<MutationResult>(`/booking/bookings/${encodeURIComponent(id)}/complete`);
}

export async function tick(
    dryRun = true,
    pin = ""
): Promise<TickResult | typeof DORMANT> {
    return safePostJson<TickResult>(`/booking/tick?dry_run=${dryRun ? 1 : 0}`, { pin });
}
