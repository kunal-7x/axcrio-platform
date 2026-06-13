"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Tabs from "@/components/Tabs";
import {
    getContact,
    getContactTimeline,
    getContactRecordings,
    CrmDormantError,
    CrmNotFoundError,
    type ContactDetailResponse,
    type TimelineRow,
    type Recording,
} from "../client";
import {
    StageBadge,
    initials,
    fmtDate,
    fmtDateTime,
    fmtRelative,
    kindMeta,
    nbaMeta,
} from "../_ui";

// Timeline kind filter tabs (each maps to the ?kinds= query param).
const KIND_FILTERS = [
    { id: 1, name: "All", key: "all" },
    { id: 2, name: "Calls", key: "call" },
    { id: 3, name: "WhatsApp", key: "whatsapp" },
    { id: 4, name: "Purchases", key: "purchase" },
    { id: 5, name: "Notes", key: "note" },
];

export default function ContactProfilePage() {
    const params = useParams();
    const id = String(params?.id || "");

    const [detail, setDetail] = useState<ContactDetailResponse | null>(null);
    const [timeline, setTimeline] = useState<TimelineRow[]>([]);
    const [recordings, setRecordings] = useState<Recording[]>([]);
    const [recLoading, setRecLoading] = useState(true);
    const [loading, setLoading] = useState(true);
    const [tlLoading, setTlLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [notFound, setNotFound] = useState(false);
    const [error, setError] = useState("");
    const [kindTab, setKindTab] = useState(KIND_FILTERS[0]);
    const kind = kindTab.key;

    // Load the contact (+ embedded timeline + nba). Dormant (module/PG down) ->
    // "coming soon"; not-found (bad id) -> "not found"; else error.
    useEffect(() => {
        if (!id) return;
        setLoading(true);
        setError("");
        setNotFound(false);
        getContact(id)
            .then((r) => {
                // 200 with a null contact == module/PG dormant.
                if (!r.contact) {
                    setDormant(true);
                    return;
                }
                setDetail(r);
                setDormant(false);
            })
            .catch((e: unknown) => {
                if (e instanceof CrmDormantError) setDormant(true);
                else if (e instanceof CrmNotFoundError) setNotFound(true);
                else setError(e instanceof Error ? e.message : "Failed to load contact");
            })
            .finally(() => setLoading(false));
    }, [id]);

    // Load the timeline. The detail endpoint already embeds the unfiltered
    // first page, so the "all" view seeds from `detail.timeline` (no redundant
    // round-trip); a kind filter triggers a scoped fetch.
    useEffect(() => {
        if (!id) return;
        if (kind === "all" && detail?.timeline) {
            setTimeline(detail.timeline);
            setTlLoading(false);
            return;
        }
        setTlLoading(true);
        getContactTimeline(id, {
            kinds: kind !== "all" ? kind : undefined,
            limit: 100,
        })
            .then((r) => setTimeline(r.timeline || []))
            .catch(() => setTimeline([]))
            .finally(() => setTlLoading(false));
    }, [id, kind, detail]);

    // Load the lead's call recordings (inbound + outbound), keyed by phone. The
    // backend joins by phone/call_id/room and mints presigned URLs per-read.
    // Dormant-safe: the client resolves any failure to [] -> calm empty state.
    useEffect(() => {
        const c = detail?.contact;
        if (!c) return;
        const phone = c.phone_key || c.phone_display || id;
        if (!phone) {
            setRecLoading(false);
            return;
        }
        setRecLoading(true);
        getContactRecordings(phone)
            .then((r) => setRecordings(r.recordings || []))
            .catch(() => setRecordings([]))
            .finally(() => setRecLoading(false));
    }, [detail, id]);

    const contact = detail?.contact;
    // Live API projects lead truth INTO `contact` (no separate top-level lead);
    // keep `lead` as a forward-compat fallback only.
    const lead = detail?.lead ?? null;
    const nba = detail?.nba;
    const isHot = !!(contact?.hot || (contact?.score ?? 0) >= 70);

    // Lead status: prefer the projected stage/status; the contact's lifecycle
    // already mirrors lead.status, so fall back gracefully.
    const leadStatus = lead?.status ?? "";
    const addedAt = lead?.added_at ?? contact?.created_at ?? "";

    const consentClean =
        contact?.consent_call !== false && contact?.consent_wa !== false;

    // Tags from the contact's data.jsonb catch-all (industry-pack / custom).
    const tags = useMemo(() => {
        const raw = contact?.data?.tags;
        if (Array.isArray(raw)) return raw.filter((t) => typeof t === "string") as string[];
        if (typeof raw === "string") return raw.split(",").map((s) => s.trim()).filter(Boolean);
        return [];
    }, [contact]);

    return (
        <Layout title="Contact">
            {/* Back link + breadcrumb */}
            <div className="mb-4 flex items-center gap-3">
                <Button as="link" href="/crm" isStroke isCircle icon="arrow" className="rotate-180" />
                <Link
                    href="/crm"
                    className="text-caption text-t-tertiary hover:text-t-secondary transition-colors"
                >
                    CRM Workspace
                </Link>
                <Icon name="arrow" className="size-3 fill-t-tertiary" />
                <span className="text-caption text-t-secondary truncate max-w-40">
                    {contact?.name || (loading ? "Loading…" : "Contact")}
                </span>
            </div>

            {dormant ? (
                <Card title="Contact">
                    <FullState
                        icon="profile"
                        title="Contact profiles are coming soon"
                        sub="The Customer 360 contact spine isn’t enabled for your workspace yet. Once it is, each person gets a unified profile — timeline, lead stage, and next-best action — right here."
                    />
                </Card>
            ) : notFound ? (
                <Card title="Contact">
                    <FullState
                        icon="search"
                        title="Contact not found"
                        sub="This contact doesn’t exist or is outside your workspace. It may have been merged or removed."
                    />
                </Card>
            ) : error ? (
                <Card title="Contact">
                    <FullState
                        icon="info"
                        title="Couldn’t load this contact"
                        sub={error}
                    />
                </Card>
            ) : (
                <div className="flex gap-3 max-lg:flex-col">
                    {/* ── Left rail: identity + lead + consent ─────────── */}
                    <div className="w-96 max-lg:w-full shrink-0 space-y-3">
                        {/* Identity header card */}
                        <Card title="Profile">
                            <div className="px-5 pb-5 max-lg:px-3">
                                {loading ? (
                                    <div className="flex items-center gap-4">
                                        <div className="skeleton size-16 rounded-full" />
                                        <div className="flex-1 space-y-2">
                                            <div className="skeleton h-5 w-32" />
                                            <div className="skeleton h-4 w-24" />
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        <div className="flex items-center gap-4">
                                            <span
                                                className={`grid place-items-center size-16 shrink-0 rounded-full text-h6 font-semibold ${
                                                    isHot
                                                        ? "bg-primary-02/12 text-primary-02"
                                                        : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                }`}
                                            >
                                                {initials(contact?.name)}
                                            </span>
                                            <div className="min-w-0">
                                                <div className="text-h6 text-t-primary truncate">
                                                    {contact?.name || "Unknown contact"}
                                                </div>
                                                <div className="text-body-2 text-t-secondary td-num truncate">
                                                    {contact?.phone_display || "—"}
                                                </div>
                                            </div>
                                        </div>

                                        <div className="mt-4 flex flex-wrap items-center gap-2">
                                            <StageBadge stage={contact?.stage} />
                                            {isHot && (
                                                <span className="inline-flex items-center gap-1.5 px-2.5 h-6 rounded-full text-caption font-semibold bg-primary-02/12 text-primary-02">
                                                    <Icon name="star-fill" className="size-3 fill-primary-02" />
                                                    Hot · {contact?.score ?? 0}
                                                </span>
                                            )}
                                            {!isHot && (contact?.score ?? 0) > 0 && (
                                                <span className="inline-flex items-center px-2.5 h-6 rounded-full text-caption font-semibold bg-b-surface1 text-t-secondary dark:bg-shade-04/60 td-num">
                                                    Score {contact?.score}
                                                </span>
                                            )}
                                        </div>

                                        {contact?.email && (
                                            <div className="mt-4 flex items-center gap-2 text-body-2 text-t-secondary">
                                                <Icon name="envelope" className="size-4 fill-t-tertiary shrink-0" />
                                                <span className="truncate">{contact.email}</span>
                                            </div>
                                        )}

                                        {tags.length > 0 && (
                                            <div className="mt-4 flex flex-wrap gap-1.5">
                                                {tags.map((t) => (
                                                    <span
                                                        key={t}
                                                        className="px-2.5 h-6 inline-flex items-center rounded-full text-caption bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                    >
                                                        {t}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        </Card>

                        {/* Next-Best-Action card */}
                        {!loading && nba && <NbaCard nba={nba} />}

                        {/* Lead + consent summary */}
                        {!loading && (
                            <Card title="Lead & Consent">
                                <div className="px-5 pb-5 max-lg:px-3 space-y-3.5">
                                    <Row
                                        label="Lead status"
                                        value={
                                            leadStatus
                                                ? leadStatus.replace(/_/g, " ")
                                                : contact?.stage
                                                ? contact.stage.replace(/_/g, " ")
                                                : "—"
                                        }
                                        cap
                                    />
                                    <Row
                                        label="Last outcome"
                                        value={
                                            contact?.last_outcome
                                                ? contact.last_outcome.replace(/_/g, " ")
                                                : "—"
                                        }
                                        cap
                                    />
                                    <Row
                                        label="Last activity"
                                        value={fmtRelative(contact?.last_activity_at)}
                                    />
                                    {addedAt && (
                                        <Row label="Added" value={fmtDate(addedAt)} />
                                    )}
                                    {contact?.lifecycle_state && (
                                        <Row
                                            label="Lifecycle"
                                            value={contact.lifecycle_state.replace(/_/g, " ")}
                                            cap
                                        />
                                    )}

                                    <div className="h-px bg-s-subtle my-1" />

                                    {/* Consent compliance read (§3.1) */}
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-caption text-t-tertiary">
                                            Consent
                                        </span>
                                        <div className="flex items-center gap-1.5">
                                            <ConsentPill
                                                ok={contact?.consent_call !== false}
                                                label="Call"
                                            />
                                            <ConsentPill
                                                ok={contact?.consent_wa !== false}
                                                label="WhatsApp"
                                            />
                                        </div>
                                    </div>
                                    {!consentClean && (
                                        <div className="flex items-start gap-2 p-2.5 rounded-xl bg-primary-03/8 text-caption text-primary-03">
                                            <Icon name="block" className="size-3.5 fill-primary-03 shrink-0 mt-0.5" />
                                            <span>
                                                Consent withdrawn on a channel — outreach is
                                                suppressed for this contact.
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </Card>
                        )}

                        {/* Recordings — call audio for this lead (inbound + outbound) */}
                        {!loading && (
                            <RecordingsCard loading={recLoading} recordings={recordings} />
                        )}
                    </div>

                    {/* ── Right: unified timeline feed ─────────────────── */}
                    <div className="flex-1 min-w-0">
                        <Card
                            title="Timeline"
                            headContent={
                                <Tabs
                                    className="overflow-x-auto scrollbar-none"
                                    items={KIND_FILTERS}
                                    value={kindTab}
                                    setValue={(v) =>
                                        setKindTab(
                                            v as (typeof KIND_FILTERS)[number]
                                        )
                                    }
                                />
                            }
                        >
                            <div className="px-5 pb-5 max-lg:px-3">
                                {tlLoading ? (
                                    <div className="space-y-5 pt-2">
                                        {[...Array(5)].map((_, i) => (
                                            <div key={i} className="flex gap-4">
                                                <div className="skeleton size-9 rounded-full shrink-0" />
                                                <div className="flex-1 space-y-2">
                                                    <div className="skeleton h-4 w-1/3" />
                                                    <div className="skeleton h-3.5 w-2/3" />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : timeline.length === 0 ? (
                                    <div className="py-12 text-center">
                                        <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                                            <Icon name="clock" className="fill-t-tertiary" />
                                        </span>
                                        <div className="text-h6 mb-1">
                                            {kind === "all"
                                                ? "No activity yet"
                                                : `No ${kindTab.name.toLowerCase()} yet`}
                                        </div>
                                        <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                                            Every call, message, and event for this person will
                                            appear here, newest first.
                                        </div>
                                    </div>
                                ) : (
                                    <ol className="relative pt-2">
                                        {/* the connecting spine */}
                                        <span
                                            className="absolute left-[1.0625rem] top-4 bottom-4 w-px bg-s-subtle"
                                            aria-hidden
                                        />
                                        {timeline.map((row, i) => (
                                            <TimelineItem key={`${row.at}-${i}`} row={row} index={i} />
                                        ))}
                                    </ol>
                                )}
                            </div>
                        </Card>
                    </div>
                </div>
            )}
        </Layout>
    );
}

// ── Next-Best-Action card ────────────────────────────────────────────────────
function NbaCard({ nba }: { nba: ContactDetailResponse["nba"] }) {
    const meta = nbaMeta(nba.action);
    const isNone = nba.action === "none";
    return (
        <Card title="Next Best Action">
            <div className="px-5 pb-5 max-lg:px-3">
                <div className="flex items-start gap-3">
                    <span
                        className={`grid place-items-center size-10 shrink-0 rounded-full ${meta.bg}`}
                    >
                        <Icon name={meta.icon} className={`size-5 ${meta.fill}`} />
                    </span>
                    <div className="min-w-0">
                        <div className="text-body-1-str text-t-primary font-semibold">
                            {meta.label}
                        </div>
                        {nba.reason && (
                            <div className="text-caption text-t-secondary mt-0.5">
                                {nba.reason}
                            </div>
                        )}
                    </div>
                </div>

                {/* Confidence meter when provided */}
                {nba.confidence != null && nba.confidence > 0 && (
                    <div className="mt-4">
                        <div className="flex items-center justify-between text-caption text-t-tertiary mb-1.5">
                            <span>Confidence</span>
                            <span className="td-num">
                                {Math.round(nba.confidence * 100)}%
                            </span>
                        </div>
                        <div className="meter">
                            <div
                                className="meter-fill bg-primary-01"
                                style={{
                                    width: `${Math.max(2, Math.min(100, nba.confidence * 100))}%`,
                                }}
                            />
                        </div>
                    </div>
                )}

                {/* Actuation: gated behind the firewall step-up (F4). The PIN
                    verifier may be absent, so this stays a clearly-gated, not-yet
                    -live affordance rather than a misleading live button. */}
                {!isNone && (
                    <div className="mt-4">
                        {nba.requires_pin ? (
                            <div className="flex items-start gap-2 p-3 rounded-xl bg-b-surface1 dark:bg-shade-04/40 text-caption text-t-secondary">
                                <Icon name="lock" className="size-4 fill-primary-05 shrink-0 mt-0.5" />
                                <span>
                                    This action moves spend or sends a message, so it needs a
                                    PIN approval. Approve & run from the AI&nbsp;Manager when it
                                    goes live.
                                </span>
                            </div>
                        ) : (
                            <Button isStroke disabled className="w-full justify-center">
                                Run action · coming soon
                            </Button>
                        )}
                    </div>
                )}
            </div>
        </Card>
    );
}

// ── Recordings card ──────────────────────────────────────────────────────────
//
// Mirrors the proven AI-Manager session player (app/ai-manager/sessions/[id]):
// a native <audio controls preload="none"> (so the OGG only fetches on play +
// supports seeking via HTTP range) plus a Download link per row. The bucket is
// private, so each row's `url` is a freshly-minted presigned URL from the backend;
// a row that hasn't finished uploading shows a calm "preparing" line, never a
// broken player. Dormant-safe: no recordings -> a quiet empty state.

function fmtClock(sec?: number | null): string {
    if (sec == null || !Number.isFinite(sec) || sec <= 0) return "";
    const s = Math.round(sec);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function RecordingsCard({
    loading,
    recordings,
}: {
    loading: boolean;
    recordings: Recording[];
}) {
    return (
        <Card
            title="Recordings"
            headContent={
                !loading && recordings.length > 0 ? (
                    <span className="ml-auto text-caption text-t-tertiary td-num">
                        {recordings.length}
                    </span>
                ) : undefined
            }
        >
            <div className="px-5 pb-5 max-lg:px-3">
                {loading ? (
                    <div className="space-y-2.5 pt-1">
                        {[...Array(2)].map((_, i) => (
                            <div key={i} className="skeleton h-14 w-full rounded-2xl" />
                        ))}
                    </div>
                ) : recordings.length === 0 ? (
                    <div className="py-8 text-center">
                        <span className="inline-grid place-items-center size-12 mb-3 rounded-full bg-b-surface1 dark:bg-shade-04/60">
                            <Icon name="camera-video" className="fill-t-tertiary" />
                        </span>
                        <div className="text-body-2 font-medium text-t-primary mb-0.5">
                            No recordings yet
                        </div>
                        <div className="max-w-xs mx-auto text-caption text-t-secondary">
                            Every call with this person is recorded — inbound and outbound.
                            The audio appears here the moment a call ends and uploads.
                        </div>
                    </div>
                ) : (
                    <div className="space-y-2.5 pt-1">
                        {recordings.map((r) => (
                            <RecordingRow key={r.call_id} r={r} />
                        ))}
                    </div>
                )}
            </div>
        </Card>
    );
}

function RecordingRow({ r }: { r: Recording }) {
    const inbound = r.direction === "inbound";
    const clock = fmtClock(r.duration_s);
    const preparing = !r.url && /recording|pending|uploading/.test(r.status);
    return (
        <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
                <span className="inline-flex items-center gap-1.5 text-caption text-t-secondary">
                    <Icon
                        name="camera-video"
                        className="size-3.5 fill-primary-01 shrink-0"
                    />
                    {r.direction ? (inbound ? "Inbound call" : "Outbound call") : "Call"}
                    {clock && (
                        <span className="text-t-tertiary tabular-nums">· {clock}</span>
                    )}
                </span>
                {r.started_at && (
                    <span
                        className="shrink-0 text-caption text-t-tertiary td-num whitespace-nowrap"
                        title={fmtDateTime(r.started_at)}
                    >
                        {fmtRelative(r.started_at)}
                    </span>
                )}
            </div>

            {r.url ? (
                <div className="flex items-center gap-2 max-sm:flex-col max-sm:items-stretch">
                    <audio
                        controls
                        preload="none"
                        src={r.url}
                        className="h-9 w-full min-w-0"
                    >
                        Your browser does not support the audio element.
                    </audio>
                    <a
                        href={r.url}
                        download
                        className="shrink-0 inline-flex items-center justify-center gap-1.5 h-9 px-3 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary"
                    >
                        <Icon name="download" className="size-3.5 fill-current" />
                        <span className="max-sm:hidden">Download</span>
                    </a>
                </div>
            ) : (
                <div className="flex items-center gap-2 text-caption text-t-tertiary">
                    <Icon name="clock" className="size-3.5 fill-t-tertiary shrink-0" />
                    {preparing
                        ? "Recording in progress — the audio appears once the call ends and uploads."
                        : "This call was recorded — the playback link is being prepared."}
                </div>
            )}
        </div>
    );
}

// ── One timeline event ───────────────────────────────────────────────────────
function TimelineItem({ row, index }: { row: TimelineRow; index: number }) {
    const meta = kindMeta(row.kind);
    const inbound = row.direction === "inbound";
    const hasAmount = row.amount != null && row.amount !== 0;
    return (
        <li
            className="relative flex gap-4 pb-6 last:pb-1 rise-in"
            style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}
        >
            <span
                className="relative z-1 grid place-items-center size-9 shrink-0 rounded-full bg-b-surface2 ring-1 ring-s-subtle dark:bg-shade-04/80"
                title={meta.label}
            >
                <Icon name={meta.icon} className={`size-4 ${meta.fill}`} />
            </span>
            <div className="min-w-0 flex-1 pt-1">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <span className="text-body-2 font-medium text-t-primary">
                            {row.title || meta.label}
                        </span>
                        {row.direction && (
                            <span className="ml-2 text-caption text-t-tertiary">
                                {inbound ? "↓ inbound" : "↑ outbound"}
                            </span>
                        )}
                    </div>
                    <span
                        className="shrink-0 text-caption text-t-tertiary td-num whitespace-nowrap"
                        title={fmtDateTime(row.at)}
                    >
                        {fmtRelative(row.at)}
                    </span>
                </div>
                {row.body && (
                    <p className="mt-1 text-body-2 text-t-secondary line-clamp-3">
                        {row.body}
                    </p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    {row.outcome && (
                        <span className="inline-flex items-center px-2 h-5 rounded-md text-caption capitalize bg-b-surface1 text-t-secondary dark:bg-shade-04/60">
                            {row.outcome.replace(/_/g, " ")}
                        </span>
                    )}
                    {hasAmount && (
                        <span className="inline-flex items-center px-2 h-5 rounded-md text-caption font-semibold bg-primary-02/12 text-primary-02 td-num">
                            {row.currency ? `${row.currency} ` : ""}
                            {Number(row.amount).toLocaleString()}
                        </span>
                    )}
                </div>
            </div>
        </li>
    );
}

// ── Small layout atoms ───────────────────────────────────────────────────────
function Row({ label, value, cap }: { label: string; value: string; cap?: boolean }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <span className="text-caption text-t-tertiary shrink-0">{label}</span>
            <span
                className={`text-body-2 text-t-primary text-right truncate ${
                    cap ? "capitalize" : ""
                }`}
            >
                {value}
            </span>
        </div>
    );
}

function FullState({
    icon,
    title,
    sub,
}: {
    icon: string;
    title: string;
    sub: string;
}) {
    return (
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon name={icon} className="fill-t-tertiary" />
            </span>
            <div className="text-h6 mb-1">{title}</div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                {sub}
            </div>
            <Button as="link" href="/crm" isStroke className="mt-5">
                Back to CRM
            </Button>
        </div>
    );
}

function ConsentPill({ ok, label }: { ok: boolean; label: string }) {
    return (
        <span
            className={`inline-flex items-center gap-1 px-2 h-6 rounded-full text-caption font-medium ${
                ok
                    ? "bg-primary-02/12 text-primary-02"
                    : "bg-primary-03/12 text-primary-03"
            }`}
        >
            <Icon
                name={ok ? "check-circle" : "block"}
                className={`size-3 ${ok ? "fill-primary-02" : "fill-primary-03"}`}
            />
            {label}
        </span>
    );
}
