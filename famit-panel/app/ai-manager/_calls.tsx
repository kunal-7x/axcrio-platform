"use client";

// AI MANAGER — CALL HISTORY tab (the inbound-call ledger).
//
// Every inbound AI-Manager call/chat session for the authenticated tenant, newest
// first: caller, when, duration, outcome, how many commands it executed, and whether
// it has a recording. Click a row -> the existing Session Detail (sessions/[id]) with
// the full turn-by-turn transcript, the executed commands + results, the PIN/risk
// badges, and an audio player for the recording.
//
// Reads GET /ai-manager/sessions (PG-first, RLS, tenant-scoped). Filters by channel
// and status are applied server-side. Backend DEFINED-NOT-MOUNTED / no-sessions-yet
// both degrade to a premium dormant panel — never an error wall. Presentation only;
// all wiring lives in _lib.ts. Built on the in-app Signal language (Card / Badge /
// Icon) + the shared helpers. Touches no app-wide component, no globals.css.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Select from "@/components/Select";
import { DormantPanel, ErrorBanner, fmt, statusVariant } from "./_shared";
import {
    getAimSessions,
    sessionId,
    sessionCaller,
    channelGlyph,
    AIM_CHANNELS,
    type AimSession,
    type ReadResult,
} from "./_lib";

/* ----------------------------------------------------------------- helpers */

function durationOf(a?: string | null, b?: string | null): string {
    if (!a || !b) return "—";
    try {
        const ms = new Date(b).getTime() - new Date(a).getTime();
        if (!Number.isFinite(ms) || ms < 0) return "—";
        const s = Math.round(ms / 1000);
        if (s < 60) return `${s}s`;
        return `${Math.floor(s / 60)}m ${s % 60}s`;
    } catch {
        return "—";
    }
}

// Recording presence -> a small badge. "done" plays; pending/recording = in flight;
// failed = errored; otherwise none. Mirrors the recording_status the backend persists.
function recordingBadge(s: AimSession): React.ReactNode {
    const has = !!s.has_recording;
    const st = (s.recording_status || "").toLowerCase();
    if (st === "failed") return <Badge variant="danger">rec failed</Badge>;
    if (has || st === "done")
        return (
            <Badge variant="info">
                <Icon name="camera-video" className="size-3 fill-current mr-1" />
                recording
            </Badge>
        );
    if (st === "pending" || st === "recording")
        return <Badge variant="warning">recording…</Badge>;
    return <span className="text-caption text-t-tertiary">—</span>;
}

const STATUS_FILTERS: { value: string; label: string }[] = [
    { value: "", label: "All" },
    { value: "completed", label: "Completed" },
    { value: "active", label: "Active" },
    { value: "failed", label: "Failed" },
    { value: "blocked", label: "Blocked" },
];

// One "Show more" pulls this many more sessions (Lane C SPEED — was a single
// limit:100 load-all).
const AIM_PAGE = 50;

// Sortable columns → the backend sort_by column. Sorting asks the server to
// order ALL records; the client sort below is the graceful fallback.
type AimSortKey = "caller" | "when" | "duration" | "commands" | "outcome";
const AIM_SORT_COLUMN: Record<AimSortKey, string> = {
    caller: "caller",
    when: "started_at",
    duration: "started_at", // duration derives from started/ended; proxy on start
    commands: "n_actions",
    outcome: "outcome",
};
function aimSortValue(s: AimSession, key: AimSortKey): number | string {
    switch (key) {
        case "caller":
            return (sessionCaller(s) || "").toLowerCase();
        case "when":
            return s.started_at ? new Date(s.started_at).getTime() : 0;
        case "duration": {
            if (!s.started_at || !s.ended_at) return -1;
            return new Date(s.ended_at).getTime() - new Date(s.started_at).getTime();
        }
        case "commands":
            return typeof s.n_actions === "number" ? s.n_actions : 0;
        case "outcome":
            return (s.outcome || s.status || "").toLowerCase();
    }
}

/* ============================================================== the tab */

export default function CallsTab() {
    const router = useRouter();

    const [res, setRes] = useState<ReadResult<{ sessions: AimSession[]; source?: string; total?: number; next?: number | null }> | null>(null);
    const [pages, setPages] = useState<AimSession[]>([]);
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(false);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [channel, setChannel] = useState("");
    const [status, setStatus] = useState("");
    // Click-header sort (Lane C). Backend sort_by/order span ALL records; the
    // client sort below is the fallback if the backend ignores them.
    const [sortKey, setSortKey] = useState<AimSortKey>("when");
    const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

    // Page 0 — replaces the list whenever filters/sort change.
    const load = useCallback(() => {
        setLoading(true);
        getAimSessions({
            limit: AIM_PAGE,
            offset: 0,
            channel: channel || undefined,
            status: status || undefined,
            sort_by: AIM_SORT_COLUMN[sortKey],
            order: sortDir,
        })
            .then((r) => {
                setRes(r);
                if (r.kind === "ok") {
                    const got = r.data.sessions || [];
                    setPages(got);
                    setOffset(got.length);
                    setHasMore(
                        r.data.next != null
                            ? true
                            : got.length >= AIM_PAGE &&
                                  (r.data.total == null || got.length < r.data.total)
                    );
                } else {
                    setPages([]);
                    setOffset(0);
                    setHasMore(false);
                }
            })
            .finally(() => setLoading(false));
    }, [channel, status, sortKey, sortDir]);

    const loadMore = useCallback(() => {
        setLoadingMore(true);
        getAimSessions({
            limit: AIM_PAGE,
            offset,
            channel: channel || undefined,
            status: status || undefined,
            sort_by: AIM_SORT_COLUMN[sortKey],
            order: sortDir,
        })
            .then((r) => {
                if (r.kind === "ok") {
                    const got = r.data.sessions || [];
                    setPages((prev) => [...prev, ...got]);
                    setOffset((o) => o + got.length);
                    setHasMore(
                        r.data.next != null ? true : got.length >= AIM_PAGE
                    );
                }
            })
            .finally(() => setLoadingMore(false));
    }, [offset, channel, status, sortKey, sortDir]);

    useEffect(() => {
        load();
    }, [load]);

    const onSort = (k: AimSortKey) => {
        if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        else {
            setSortKey(k);
            setSortDir(k === "caller" || k === "outcome" ? "asc" : "desc");
        }
    };

    // Client-side sort fallback over the loaded pages (keeps the header instant +
    // correct even if the backend ignored sort_by).
    const rows = useMemo(() => {
        const sorted = [...pages].sort((a, b) => {
            const av = aimSortValue(a, sortKey);
            const bv = aimSortValue(b, sortKey);
            const r =
                typeof av === "number" && typeof bv === "number"
                    ? av - bv
                    : String(av).localeCompare(String(bv));
            return sortDir === "asc" ? r : -r;
        });
        return sorted;
    }, [pages, sortKey, sortDir]);
    const dormant = res?.kind === "dormant";
    const err = res?.kind === "error" ? res.message : "";

    const open = (s: AimSession) => {
        const id = sessionId(s);
        if (id) router.push(`/ai-manager/sessions/${encodeURIComponent(id)}`);
    };

    return (
        <>
            <ErrorBanner msg={err} />

            <Card
                title="Call history"
                headContent={
                    <div className="ml-auto flex items-center gap-2 max-sm:hidden">
                        {/* Channel filter */}
                        <FilterPill
                            value={channel}
                            onChange={setChannel}
                            options={[{ value: "", label: "All channels" }, ...AIM_CHANNELS.map((c) => ({ value: c.value, label: c.label }))]}
                        />
                        {/* Status filter */}
                        <FilterPill value={status} onChange={setStatus} options={STATUS_FILTERS} />
                        <button
                            onClick={load}
                            disabled={loading}
                            className="inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                            aria-label="Refresh"
                        >
                            <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                            Refresh
                        </button>
                    </div>
                }
            >
                {/* mobile filter row */}
                <div className="hidden max-sm:flex items-center gap-2 px-3 pb-3 flex-wrap">
                    <FilterPill
                        value={channel}
                        onChange={setChannel}
                        options={[{ value: "", label: "All channels" }, ...AIM_CHANNELS.map((c) => ({ value: c.value, label: c.label }))]}
                    />
                    <FilterPill value={status} onChange={setStatus} options={STATUS_FILTERS} />
                </div>

                {loading && !res ? (
                    <div className="px-5 max-lg:px-3 pb-5 space-y-2">
                        {[...Array(6)].map((_, i) => (
                            <div key={i} className="skeleton h-16 w-full rounded-2xl" />
                        ))}
                    </div>
                ) : dormant || rows.length === 0 ? (
                    <div className="px-5 max-lg:px-3 pb-6">
                        <DormantPanel
                            icon="mobile"
                            title={
                                dormant
                                    ? "Call history lights up once the line is live"
                                    : channel || status
                                    ? "No calls match these filters"
                                    : "No calls yet"
                            }
                            sub={
                                dormant
                                    ? "When managers call the AI Manager number, each call is recorded here — the full transcript, the commands it ran, and an audio player for the recording."
                                    : channel || status
                                    ? "Try clearing the channel or status filter."
                                    : "Every inbound call will appear here with its caller, duration, outcome and the commands it executed."
                            }
                        />
                    </div>
                ) : (
                    <>
                        {/* desktop table */}
                        <div className="px-2 pb-3 max-md:hidden">
                            <table className="w-full">
                                <thead>
                                    <tr className="text-left text-caption text-t-tertiary">
                                        <AimSortTh label="Caller" k="caller" active={sortKey} dir={sortDir} onSort={onSort} />
                                        <AimSortTh label="When" k="when" active={sortKey} dir={sortDir} onSort={onSort} />
                                        <AimSortTh label="Duration" k="duration" active={sortKey} dir={sortDir} onSort={onSort} />
                                        <AimSortTh label="Commands" k="commands" active={sortKey} dir={sortDir} onSort={onSort} />
                                        <th className="font-normal px-3 py-2">Recording</th>
                                        <AimSortTh label="Outcome" k="outcome" active={sortKey} dir={sortDir} onSort={onSort} />
                                        <th className="px-3 py-2" />
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map((s) => (
                                        <tr
                                            key={sessionId(s)}
                                            onClick={() => open(s)}
                                            className="group cursor-pointer border-t border-s-subtle transition-colors hover:bg-b-surface2/60"
                                        >
                                            <td className="px-3 py-3">
                                                <div className="flex items-center gap-2.5">
                                                    <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                                                        <Icon name={channelGlyph(s.channel)} className="size-4 fill-inherit" />
                                                    </span>
                                                    <div className="min-w-0">
                                                        <div className="text-body-2 text-t-primary font-mono td-num truncate">
                                                            {sessionCaller(s) || "Unknown"}
                                                        </div>
                                                        <div className="text-caption text-t-tertiary capitalize">
                                                            {(s.channel || "—").toString().replace("_", " ")}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-3 py-3 text-body-2 text-t-secondary whitespace-nowrap">
                                                {fmt(s.started_at)}
                                            </td>
                                            <td className="px-3 py-3 text-body-2 text-t-secondary tabular-nums whitespace-nowrap">
                                                {durationOf(s.started_at, s.ended_at)}
                                            </td>
                                            <td className="px-3 py-3">
                                                <span className="inline-flex items-center gap-1.5 text-body-2 text-t-secondary tabular-nums">
                                                    <Icon name="layers" className="size-3.5 fill-t-tertiary" />
                                                    {typeof s.n_actions === "number" ? s.n_actions : 0}
                                                </span>
                                            </td>
                                            <td className="px-3 py-3">{recordingBadge(s)}</td>
                                            <td className="px-3 py-3">
                                                <Badge variant={statusVariant(s.outcome || s.status)}>
                                                    {(s.outcome || s.status || "—").replace(/_/g, " ")}
                                                </Badge>
                                            </td>
                                            <td className="px-3 py-3 text-right">
                                                <Icon
                                                    name="arrow"
                                                    className="size-4 fill-t-tertiary opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0"
                                                />
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* mobile cards */}
                        <div className="hidden max-md:block px-3 pb-4 space-y-2">
                            {rows.map((s) => (
                                <button
                                    key={sessionId(s)}
                                    onClick={() => open(s)}
                                    className="w-full text-left rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3 transition-colors hover:ring-s-highlight"
                                >
                                    <div className="flex items-center gap-2.5">
                                        <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-t-secondary">
                                            <Icon name={channelGlyph(s.channel)} className="size-4 fill-inherit" />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <div className="text-body-2 text-t-primary font-mono td-num truncate">
                                                {sessionCaller(s) || "Unknown"}
                                            </div>
                                            <div className="text-caption text-t-tertiary">{fmt(s.started_at)}</div>
                                        </div>
                                        <Badge variant={statusVariant(s.outcome || s.status)}>
                                            {(s.outcome || s.status || "—").replace(/_/g, " ")}
                                        </Badge>
                                    </div>
                                    <div className="mt-2 flex items-center gap-x-4 gap-y-1 flex-wrap text-caption text-t-tertiary">
                                        <span className="inline-flex items-center gap-1">
                                            <Icon name="clock" className="size-3.5 fill-t-tertiary" />
                                            {durationOf(s.started_at, s.ended_at)}
                                        </span>
                                        <span className="inline-flex items-center gap-1">
                                            <Icon name="layers" className="size-3.5 fill-t-tertiary" />
                                            {typeof s.n_actions === "number" ? s.n_actions : 0} commands
                                        </span>
                                        {recordingBadge(s)}
                                    </div>
                                </button>
                            ))}
                        </div>

                        {hasMore && (
                            <div className="flex justify-center px-3 pb-4">
                                <button
                                    onClick={loadMore}
                                    disabled={loadingMore}
                                    className="inline-flex items-center justify-center gap-2 h-9 px-4 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary active:scale-[0.98] disabled:opacity-50"
                                >
                                    {loadingMore ? (
                                        <>
                                            <Icon name="clock" className="size-4 fill-current animate-spin" />
                                            Loading…
                                        </>
                                    ) : (
                                        "Show more"
                                    )}
                                </button>
                            </div>
                        )}

                        {res?.kind === "ok" && res.data.source === "jsonl" && (
                            <div className="px-5 max-lg:px-3 pb-4 text-caption text-t-tertiary">
                                Showing a mirrored copy — live records resume once the database reconnects.
                            </div>
                        )}
                    </>
                )}
            </Card>
        </>
    );
}

/* ----------------------------------------------------------- sub-components */

// Sortable <th> — click to sort, click again to flip direction.
function AimSortTh({
    label,
    k,
    active,
    dir,
    onSort,
}: {
    label: string;
    k: AimSortKey;
    active: AimSortKey;
    dir: "asc" | "desc";
    onSort: (k: AimSortKey) => void;
}) {
    const isActive = active === k;
    return (
        <th className="font-normal px-3 py-2">
            <button
                type="button"
                onClick={() => onSort(k)}
                className={`inline-flex items-center gap-1 select-none transition-colors hover:text-t-primary ${
                    isActive ? "text-t-secondary" : ""
                }`}
            >
                {label}
                <span className="text-caption">
                    {isActive ? (dir === "asc" ? "↑" : "↓") : ""}
                </span>
            </button>
        </th>
    );
}

function FilterPill({
    value,
    onChange,
    options,
}: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
}) {
    const opts = options.map((o, i) => ({ id: i, name: o.label, value: o.value }));
    return (
        <Select
            classButton="!h-9 !rounded-full !pl-3.5 !pr-3 !border-s-subtle !bg-b-surface2 !text-button !text-t-secondary"
            value={opts.find((o) => o.value === value) ?? null}
            options={opts}
            onChange={(o) => onChange(opts[o.id].value)}
        />
    );
}
