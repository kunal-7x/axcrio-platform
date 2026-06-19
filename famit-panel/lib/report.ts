// W15 — the panel's reporting client (design/W14-REPORTING-AIM-SEAM.md §5/§7).
//
// The W14 wave built a real-time reporting read-model (`voice_ops/reporting`) with a
// query API (`/report?preset=…`, `/report/funnel`, `/report/hot-leads`, …). Those
// routes are NOT mounted on the live box yet (W14 is a SEAM NOTE — the wiring is a
// separate founder-signed wave). The LIVE routes today are `/stats`, `/analytics`,
// `/calls`, `/leads`, `/callbacks`.
//
// So this client is DORMANT-SAFE and FORWARD-COMPATIBLE in one shape:
//   1. It first TRIES the real `GET /report?preset=…` (and the sibling routes). If
//      the box has them mounted, the dashboard gets true range-aware, event-fed,
//      real-time numbers for free — no UI change needed.
//   2. If they 404 / error (today), it COMPOSES the same W14 §7 report shape from
//      the live `/stats` + `/analytics` + `/leads` endpoints, so the consolidated
//      dashboard renders REAL data now and seamlessly upgrades when the seam lands.
//
// The returned `Report` matches the W14 §7 UI contract the components bind to:
// `range`, `totals`, `funnel`, `timeline`, `by_status`, `hot_leads`. No backend or
// route signature is changed here (founder rule). Every fetch is tenant-token
// scoped via `authHeaders()` (mirrors lib/api.ts).

import {
    getStats,
    getAnalytics,
    getLeads,
    BASE,
    authHeaders,
    type Lead,
} from "@/lib/api";

// ── Range model (W14 §7 — default Today) ────────────────────────────────────
export type RangePreset =
    | "today"
    | "yesterday"
    | "7d"
    | "30d"
    | "this-month"
    | "prev-month"
    | "custom";

export type ResolvedRange = {
    preset: RangePreset;
    from: string; // YYYY-MM-DD (vendor-local, inclusive)
    to: string; // YYYY-MM-DD (inclusive)
    tz: string;
};

export const RANGE_PRESETS: { id: RangePreset; label: string }[] = [
    { id: "today", label: "Today" },
    { id: "yesterday", label: "Yesterday" },
    { id: "7d", label: "Last 7 days" },
    { id: "30d", label: "Last 30 days" },
    { id: "this-month", label: "This month" },
    { id: "prev-month", label: "Last month" },
    { id: "custom", label: "Custom" },
];

const TZ = "Asia/Kolkata";

// Vendor-local YYYY-MM-DD for a Date (the W14 "render in IST" rule, JS mirror of
// timeutil.to_vendor). Always operate on vendor-local day boundaries.
function ymd(d: Date): string {
    // en-CA gives ISO-ish YYYY-MM-DD; timeZone pins it to IST.
    return new Intl.DateTimeFormat("en-CA", {
        timeZone: TZ,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).format(d);
}

function addDays(ymdStr: string, days: number): string {
    const d = new Date(`${ymdStr}T00:00:00`);
    d.setDate(d.getDate() + days);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate()
    ).padStart(2, "0")}`;
}

// preset (+ optional custom from/to) -> resolved [from,to] inclusive, vendor-local.
export function resolveRange(
    preset: RangePreset,
    custom?: { from?: string; to?: string }
): ResolvedRange {
    const now = new Date();
    const today = ymd(now);
    let from = today;
    let to = today;
    switch (preset) {
        case "today":
            break;
        case "yesterday":
            from = addDays(today, -1);
            to = from;
            break;
        case "7d":
            from = addDays(today, -6);
            break;
        case "30d":
            from = addDays(today, -29);
            break;
        case "this-month": {
            const [y, m] = today.split("-");
            from = `${y}-${m}-01`;
            break;
        }
        case "prev-month": {
            const d = new Date(`${today}T00:00:00`);
            const first = new Date(d.getFullYear(), d.getMonth(), 1);
            const prevLast = new Date(first.getTime() - 86400000);
            const py = prevLast.getFullYear();
            const pm = String(prevLast.getMonth() + 1).padStart(2, "0");
            from = `${py}-${pm}-01`;
            to = `${py}-${pm}-${String(prevLast.getDate()).padStart(2, "0")}`;
            break;
        }
        case "custom":
            from = custom?.from || today;
            to = custom?.to || from;
            break;
    }
    return { preset, from, to, tz: TZ };
}

export function rangeLabel(preset: RangePreset): string {
    return RANGE_PRESETS.find((p) => p.id === preset)?.label ?? "Today";
}

// ── The W14 §7 report shape the UI binds to ─────────────────────────────────
export type ReportTotals = {
    calls: number;
    connected: number;
    connect_rate: number; // 0..100
    interested: number;
    booked: number;
    converted: number;
    hot: number;
    warm: number;
    cold: number;
    dead: number;
    callbacks: number;
    whatsapp_sent: number;
    handoff: number;
    avg_talk_time_s: number;
    conversion_rate: number; // 0..100
};

export type FunnelStage = {
    stage: string;
    count: number;
    pct_of_top: number; // 0..100
    step_conv: number; // 0..100 vs previous stage
};

export type TimelinePoint = {
    date: string; // YYYY-MM-DD vendor-local
    calls: number;
    connected: number;
    booked: number;
    converted: number;
};

export type HotLeadRow = {
    call_id: string;
    name: string;
    phone_masked: string;
    phone?: string; // raw phone — fallback when phone_masked is blank
    campaign_id?: string;
    source?: string;
    booked?: boolean;
    score?: number; // 0..100 flat score the backend may surface alongside the prob
    conversion_prob?: number; // 0..1 (NORMALIZED by normalizeHotLead — never >1)
    summary?: string;
    next_action?: string;
    ts_iso?: string;
};

// The live `/report` seam (caller.py _enrich_report_temperature) leaves each
// hot-lead's `conversion_prob` in WHATEVER scale the reporting store held — it may
// be a 0..1 fraction OR a 0..100 percentage (it only normalizes a sibling `score`).
// If the UI then does `prob * 100` it can render "8000%". So we normalize HERE to a
// guaranteed 0..1 once, for the whole panel: prefer the backend's flat `score`
// (0..100), else coerce a >1 prob down by /100, and clamp to [0,1]. Also surface a
// usable display phone (phone_masked → phone) so the report's phone cell is never
// blank when a raw number exists.
function normalizeHotLead(r: HotLeadRow): HotLeadRow {
    let prob = r.conversion_prob;
    if (typeof r.score === "number") prob = r.score / 100;
    else if (typeof prob === "number" && prob > 1) prob = prob / 100;
    if (typeof prob === "number") prob = Math.max(0, Math.min(1, prob));
    const phone_masked = r.phone_masked || r.phone || "";
    return { ...r, conversion_prob: prob, phone_masked };
}

// A richer temperature distribution the W14 seam may emit per range: each tier's
// count + its share of the total + a day-over-day delta. The dashboard's
// temperature display PREFERS this when the backend populates it, and falls back
// to the coarser `by_status` counts when it is absent (graceful, forward-compat).
export type TemperatureBucket = {
    tier: "hot" | "warm" | "cold" | "dead";
    count: number;
    pct: number; // 0..100 share of scored leads
    delta?: number; // signed change vs the previous comparable range, optional
};

export type Report = {
    range: ResolvedRange;
    totals: ReportTotals;
    funnel: FunnelStage[];
    timeline: TimelinePoint[];
    by_status: { hot: number; warm: number; cold: number; dead: number };
    // Forward-compatible: present only when the live /report seam emits it.
    temperature_distribution?: TemperatureBucket[];
    hot_leads: HotLeadRow[];
    // true when the numbers came from the real W14 /report seam; false = composed
    // from the live /stats+/analytics fallback (still REAL data, coarser range).
    live_seam: boolean;
};

export type ReportFilters = {
    campaign?: string;
    lead_status?: string;
    source?: string;
    agent?: string;
    call_status?: string;
    booking_status?: string;
};

function rangeQuery(range: ResolvedRange, filters?: ReportFilters): string {
    const p = new URLSearchParams();
    p.set("preset", range.preset);
    if (range.preset === "custom") {
        p.set("from", range.from);
        p.set("to", range.to);
    }
    if (filters?.campaign) p.set("campaign", filters.campaign);
    if (filters?.lead_status) p.set("lead_status", filters.lead_status);
    if (filters?.source) p.set("source", filters.source);
    if (filters?.agent) p.set("agent", filters.agent);
    if (filters?.call_status) p.set("call_status", filters.call_status);
    if (filters?.booking_status) p.set("booking_status", filters.booking_status);
    return p.toString();
}

// ── 1. Try the real W14 seam ────────────────────────────────────────────────
async function tryLiveReport(
    range: ResolvedRange,
    filters?: ReportFilters
): Promise<Report | null> {
    try {
        const res = await fetch(`${BASE}/report?${rangeQuery(range, filters)}`, {
            headers: authHeaders(),
        });
        if (!res.ok) return null; // 404 today -> fall back
        const data = (await res.json()) as Partial<Report> & {
            totals?: ReportTotals;
        };
        if (!data || !data.totals) return null;
        return {
            range: (data.range as ResolvedRange) ?? range,
            totals: data.totals,
            funnel: data.funnel ?? [],
            timeline: data.timeline ?? [],
            by_status:
                data.by_status ?? {
                    hot: data.totals.hot ?? 0,
                    warm: data.totals.warm ?? 0,
                    cold: data.totals.cold ?? 0,
                    dead: data.totals.dead ?? 0,
                },
            temperature_distribution: data.temperature_distribution,
            hot_leads: (data.hot_leads ?? []).map(normalizeHotLead),
            live_seam: true,
        };
    } catch {
        return null;
    }
}

// ── 2. Compose the same shape from the live endpoints (today's path) ────────
const FUNNEL_ORDER = [
    "uploaded",
    "dialed",
    "connected",
    "interested",
    "warm",
    "hot",
    "booked",
    "converted",
];

// W-FRONTEND-RECONCILE §3 Fix 2b — classify ONE lead into the GlobalFilters
// status vocabulary (hot/warm/cold/dead/booked/callback/interested), using the
// SAME precedence as the KPI classification loop below so the dropdown filter
// and the tile counts agree.
function leadTier(l: Lead): string {
    const st = (l.status ?? "").toLowerCase();
    const oc = (l.last_outcome ?? "").toLowerCase();
    const s = l.score;
    if (st.includes("opt_out") || st.includes("not_interested") || oc.includes("not_interested")) return "dead";
    if (st.includes("booked") || st.includes("won")) return "booked";
    if (st.includes("interested") || oc.includes("interested")) {
        return l.hot || (s ?? 0) >= 70 ? "hot" : "warm";
    }
    if (st.includes("callback") || oc.includes("callback")) return "callback";
    if (l.hot || (s ?? 0) >= 70) return "hot";
    if ((s ?? 0) >= 40) return "warm";
    return "cold";
}

// Guaranteed client-side post-filter (so dropdowns visibly narrow even when the
// box ignores the params). Date filter is inclusive on last_call_at ?? added_at
// (compared on the YYYY-MM-DD prefix, matching ResolvedRange's vendor-local
// dates). A missing date passes the date filter (don't drop activity-less rows
// for the all-time-ish default). "interested" matches the booked OR warm/hot
// interested tiers; the rest match the tier exactly.
function postFilterLeads(
    leads: Lead[],
    range: ResolvedRange,
    leadStatus?: string
): Lead[] {
    const from = range.from || "";
    const to = range.to || "";
    const wantStatus = (leadStatus || "").toLowerCase();
    return leads.filter((l) => {
        // date narrowing
        const raw = l.last_call_at ?? l.added_at ?? "";
        if (raw) {
            const day = raw.slice(0, 10); // YYYY-MM-DD
            if (from && day < from) return false;
            if (to && day > to) return false;
        }
        // status narrowing
        if (wantStatus) {
            const tier = leadTier(l);
            if (wantStatus === "interested") {
                const oc = (l.last_outcome ?? "").toLowerCase();
                const stt = (l.status ?? "").toLowerCase();
                if (!(stt.includes("interested") || oc.includes("interested"))) return false;
            } else if (tier !== wantStatus) {
                return false;
            }
        }
        return true;
    });
}

async function composeReport(
    range: ResolvedRange,
    filters?: ReportFilters
): Promise<Report> {
    // The live /stats + /analytics are NOT range-parameterised on the box yet, so
    // the composed report is whole-history coarse (honest: we mark live_seam=false
    // and the UI shows the active range chip + a "all-time" note where relevant).
    const [stats, analytics, leadsPage] = await Promise.all([
        getStats().catch(() => null),
        // W-FRONTEND-RECONCILE §3 Fix 1 — forward the active range (getAnalytics
        // already accepts from/to) so the funnel + connected/interested/booked
        // counts become date-range-aware, plus the campaign filter.
        getAnalytics({
            ...(filters?.campaign ? { campaign_id: filters.campaign } : {}),
            ...(range.from ? { from: range.from } : {}),
            ...(range.to ? { to: range.to } : {}),
        }).catch(() => null),
        // §3 Fix 2b — forward range/campaign/status to /leads (box narrows where
        // it supports them; the post-filter below guarantees the dropdowns work
        // even on an un-upgraded box).
        getLeads({
            limit: 500,
            ...(range.from ? { from: range.from } : {}),
            ...(range.to ? { to: range.to } : {}),
            ...(filters?.campaign ? { campaign_id: filters.campaign } : {}),
            ...(filters?.lead_status ? { status: filters.lead_status } : {}),
        }).catch(() => ({ leads: [] as Lead[] })),
    ]);

    // §3 Fix 2b — GUARANTEED client-side post-filter. Even if the live /leads
    // ignores the query params, narrow the in-memory set by date (on
    // last_call_at ?? added_at) and by the status-tier the dropdown picked, so
    // the KPIs + hot-leads visibly move with every filter change.
    const allLeads = leadsPage?.leads ?? [];
    const leads = postFilterLeads(allLeads, range, filters?.lead_status);
    // Classify leads into tiers using the SAME logic the badge uses (kept inline to
    // avoid a JSX import in this .ts module).
    let hot = 0,
        warm = 0,
        cold = 0,
        dead = 0,
        booked = 0,
        interested = 0,
        callbacks = 0;
    for (const l of leads) {
        const st = (l.status ?? "").toLowerCase();
        const oc = (l.last_outcome ?? "").toLowerCase();
        const s = l.score;
        if (
            st.includes("opt_out") ||
            st.includes("not_interested") ||
            oc.includes("not_interested")
        ) {
            dead++;
        } else if (st.includes("booked") || st.includes("won")) {
            booked++;
        } else if (st.includes("interested") || oc.includes("interested")) {
            interested++;
            if (l.hot || (s ?? 0) >= 70) hot++;
            else warm++;
        } else if (st.includes("callback") || oc.includes("callback")) {
            callbacks++;
            warm++;
        } else if (l.hot || (s ?? 0) >= 70) {
            hot++;
        } else if ((s ?? 0) >= 40) {
            warm++;
        } else {
            cold++;
        }
    }

    const total = stats?.total ?? 0;
    const connected = analytics?.connected ?? stats?.answered ?? 0;
    const a = analytics;
    const aInterested = a?.interested ?? interested;
    const connectRate = total > 0 ? Math.round((connected / total) * 100) : 0;

    const totals: ReportTotals = {
        calls: total,
        connected,
        connect_rate: connectRate,
        interested: aInterested,
        booked,
        converted: booked, // until a true conversion event exists (W14 §3)
        hot,
        warm,
        cold,
        dead,
        callbacks: a?.callback ?? callbacks,
        whatsapp_sent: 0,
        handoff: 0,
        avg_talk_time_s: 0,
        conversion_rate: total > 0 ? Math.round((booked / total) * 100) : 0,
    };

    // Funnel — prefer the live /analytics funnel; map onto the 8 canonical stages.
    const fSource: Record<string, number> = {
        uploaded: leads.length || total,
        dialed: a?.dialed ?? total,
        connected,
        interested: aInterested,
        warm,
        hot,
        booked,
        converted: booked,
    };
    const top = fSource.uploaded || 1;
    const funnel: FunnelStage[] = FUNNEL_ORDER.map((stage, i) => {
        const count = fSource[stage] ?? 0;
        const prev = i === 0 ? count : fSource[FUNNEL_ORDER[i - 1]] ?? 0;
        return {
            stage,
            count,
            pct_of_top: Math.round((count / top) * 100),
            step_conv: prev > 0 ? Math.round((count / prev) * 100) : 0,
        };
    });

    // Timeline — reuse the real /stats series (per-bucket call volume) as the
    // call-volume timeline. connected/booked/converted are not per-bucket in the
    // legacy endpoint, so they stay 0 until the W14 seam lands (honest).
    const timeline: TimelinePoint[] = (stats?.series ?? []).map((pt) => ({
        date: pt.name,
        calls: pt.amt,
        connected: 0,
        booked: 0,
        converted: 0,
    }));

    const hot_leads: HotLeadRow[] = leads
        .filter((l) => l.hot || (l.score ?? 0) >= 70)
        .slice(0, 10)
        .map((l) => ({
            call_id: l.id,
            name: l.name,
            phone_masked: l.phone,
            conversion_prob: l.score != null ? l.score / 100 : undefined,
            ts_iso: l.last_call_at ?? l.added_at,
        }));

    return {
        range,
        totals,
        funnel,
        timeline,
        by_status: { hot, warm, cold, dead },
        hot_leads,
        live_seam: false,
    };
}

// ── Public: the dashboard/reports binder ────────────────────────────────────
export async function getReport(
    range: ResolvedRange,
    filters?: ReportFilters
): Promise<Report> {
    const live = await tryLiveReport(range, filters);
    if (live) return live;
    return composeReport(range, filters);
}

// ── Report DOWNLOAD (CSV / Excel) ────────────────────────────────────────────
// Client-side blob export — no backend route (founder rule: no /report* signature
// change). Two artifacts: (1) the SUMMARY report (KPIs + funnel + temperature),
// (2) the LEADS list (the hot-leads table the report surfaces). The "Excel" path
// emits a UTF-8 CSV with a BOM so Excel opens it cleanly with the right encoding —
// no SheetJS dependency, no extra bundle weight.

// RFC-4180 cell escaping: wrap in quotes when the value holds a comma, quote, or
// newline; double any embedded quote.
function csvCell(v: unknown): string {
    const s = v == null ? "" : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(rows: (string | number | null | undefined)[][]): string {
    return rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
}

// Trigger a browser download of `content` as `filename`. `bom=true` prepends a
// UTF-8 BOM so Excel detects encoding (₹, Hindi names render correctly).
function downloadBlob(content: string, filename: string, mime: string, bom = false) {
    if (typeof window === "undefined") return;
    const parts = bom ? ["﻿", content] : [content];
    const blob = new Blob(parts, { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // Revoke on the next tick so the click has consumed the URL.
    setTimeout(() => URL.revokeObjectURL(url), 0);
}

function stamp(range: ResolvedRange): string {
    return range.from === range.to ? range.from : `${range.from}_to_${range.to}`;
}

// (1) The SUMMARY report: KPIs + funnel + temperature, one flat CSV with section
// headers. `excel=true` -> BOM (Excel-friendly encoding); otherwise a plain CSV.
export function exportReportSummary(report: Report, excel = false): void {
    const t = report.totals;
    const rows: (string | number)[][] = [
        ["Famit Report", `${report.range.from} to ${report.range.to} (${report.range.tz})`],
        [],
        ["Metric", "Value"],
        ["Total calls", t.calls],
        ["Connected", t.connected],
        ["Connect rate %", t.connect_rate],
        ["Interested", t.interested],
        ["Booked", t.booked],
        ["Converted", t.converted],
        ["Conversion rate %", t.conversion_rate],
        ["Callbacks", t.callbacks],
        ["Avg talk time (s)", t.avg_talk_time_s],
        [],
        ["Lead temperature", "Count"],
        ["Hot", report.by_status.hot],
        ["Warm", report.by_status.warm],
        ["Cold", report.by_status.cold],
        ["Dead", report.by_status.dead],
        [],
        ["Funnel stage", "Count", "% of top", "Step conv %"],
        ...report.funnel.map((f) => [f.stage, f.count, f.pct_of_top, f.step_conv]),
    ];
    downloadBlob(toCsv(rows), `famit-report-${stamp(report.range)}.csv`, "text/csv;charset=utf-8", excel);
}

// (2) The LEADS list the report surfaces (the hot-leads rows). One row per lead.
export function exportReportLeads(report: Report, excel = false): void {
    const rows: (string | number)[][] = [
        ["Name", "Phone", "Campaign", "Booked", "Conversion prob %", "Next action", "Timestamp"],
        ...report.hot_leads.map((l) => [
            l.name ?? "",
            l.phone_masked ?? "",
            l.campaign_id ?? "",
            l.booked ? "yes" : "no",
            l.conversion_prob != null ? Math.round(l.conversion_prob * 100) : "",
            l.next_action ?? "",
            l.ts_iso ?? "",
        ]),
    ];
    downloadBlob(toCsv(rows), `famit-leads-${stamp(report.range)}.csv`, "text/csv;charset=utf-8", excel);
}
