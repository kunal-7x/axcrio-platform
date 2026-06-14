"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Tabs from "@/components/Tabs";
import Modal from "@/components/Modal";
import Spinner from "@/components/Spinner";
import {
    getContact,
    getContactTimeline,
    getContactRecordings,
    getCallTranscript,
    getLeadMemory,
    getLeadEpisodes,
    CrmDormantError,
    CrmNotFoundError,
    type ContactDetailResponse,
    type TimelineRow,
    type Recording,
    type CallTranscript,
    type LeadMemory,
    type LeadEpisode,
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

// Main right-column tabs: Timeline feed vs. Relationship Memory.
const MAIN_TABS = [
    { id: 1, name: "Timeline" },
    { id: 2, name: "Memory" },
];

export default function ContactProfilePage() {
    const params = useParams();
    const id = String(params?.id || "");

    const [detail, setDetail] = useState<ContactDetailResponse | null>(null);
    const [timeline, setTimeline] = useState<TimelineRow[]>([]);
    const [recordings, setRecordings] = useState<Recording[]>([]);
    const [recLoading, setRecLoading] = useState(true);

    // VOICE-BRAIN W4: durable cross-channel relationship memory (lead_memory
    // profile + lead_episodes history), keyed by phone. Dormant-safe: the client
    // resolves any degraded state to memory:null / episodes:[] -> calm empty UI.
    const [memory, setMemory] = useState<LeadMemory | null>(null);
    const [episodes, setEpisodes] = useState<LeadEpisode[]>([]);
    const [memLoading, setMemLoading] = useState(true);
    const [loading, setLoading] = useState(true);
    const [tlLoading, setTlLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [notFound, setNotFound] = useState(false);
    const [error, setError] = useState("");
    const [kindTab, setKindTab] = useState(KIND_FILTERS[0]);
    const kind = kindTab.key;

    // Main right-column tab: "Timeline" | "Memory"
    const [mainTab, setMainTab] = useState(MAIN_TABS[0]);

    // Call transcript chat-view: clicking a "call" timeline row opens the full
    // ordered transcript in a right slide-over (customer RIGHT, AI LEFT).
    const [transcriptCall, setTranscriptCall] = useState<{
        callId: string;
        title: string;
        at: string;
    } | null>(null);
    const [transcript, setTranscript] = useState<CallTranscript | null>(null);
    const [transcriptLoading, setTranscriptLoading] = useState(false);

    const openTranscript = (row: TimelineRow) => {
        // Timeline "call" rows carry source_id = call.id || room — exactly what
        // GET /calls/{call_id}/transcript accepts. Bail if there's no id to query.
        const callId = (row.source_id || "").trim();
        if (!callId) return;
        setTranscriptCall({ callId, title: row.title || "Call", at: row.at });
        setTranscript(null);
        setTranscriptLoading(true);
        getCallTranscript(callId)
            .then((t) => setTranscript(t))
            .catch(() => setTranscript(null))
            .finally(() => setTranscriptLoading(false));
    };
    const closeTranscript = () => {
        setTranscriptCall(null);
        setTranscript(null);
        setTranscriptLoading(false);
    };

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

    // Load the lead's durable memory + episode history (W4). Same phone key as
    // recordings. Both client calls never throw -> the section degrades calmly.
    useEffect(() => {
        const c = detail?.contact;
        if (!c) return;
        const phone = c.phone_key || c.phone_display || id;
        if (!phone) {
            setMemLoading(false);
            return;
        }
        setMemLoading(true);
        Promise.all([
            getLeadMemory(phone).then((r) => setMemory(r.memory)).catch(() => setMemory(null)),
            getLeadEpisodes(phone, { limit: 50 })
                .then((r) => setEpisodes(r.episodes || []))
                .catch(() => setEpisodes([])),
        ]).finally(() => setMemLoading(false));
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
                        sub="The Customer 360 contact spine isn't enabled for your workspace yet. Once it is, each person gets a unified profile — timeline, lead stage, and next-best action — right here."
                    />
                </Card>
            ) : notFound ? (
                <Card title="Contact">
                    <FullState
                        icon="search"
                        title="Contact not found"
                        sub="This contact doesn't exist or is outside your workspace. It may have been merged or removed."
                    />
                </Card>
            ) : error ? (
                <Card title="Contact">
                    <FullState
                        icon="info"
                        title="Couldn't load this contact"
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

                    {/* ── Right: main tab switcher (Timeline | Memory) ──── */}
                    <div className="flex-1 min-w-0 space-y-3">
                        {/* Top-level tab bar for the right column */}
                        {!loading && (
                            <div className="flex items-center gap-1 border-b border-s-subtle pb-0">
                                {MAIN_TABS.map((tab) => (
                                    <button
                                        key={tab.id}
                                        type="button"
                                        onClick={() => setMainTab(tab)}
                                        className={`flex items-center gap-2 h-11 px-4 text-button border-b-2 -mb-px transition-colors ${
                                            mainTab.id === tab.id
                                                ? "border-primary-01 text-t-primary"
                                                : "border-transparent text-t-secondary hover:text-t-primary"
                                        }`}
                                    >
                                        {tab.id === 2 && (
                                            <Icon
                                                name="profile"
                                                className={`size-4 ${
                                                    mainTab.id === 2
                                                        ? "fill-primary-01"
                                                        : "fill-t-tertiary"
                                                }`}
                                            />
                                        )}
                                        {tab.name}
                                        {/* badge: episode count on the Memory tab */}
                                        {tab.id === 2 && !memLoading && episodes.length > 0 && (
                                            <span className="inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full text-caption font-semibold bg-primary-01/12 text-primary-01 td-num">
                                                {episodes.length}
                                            </span>
                                        )}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ── Timeline tab ──────────────────────────────── */}
                        {(loading || mainTab.id === 1) && (
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
                                                <TimelineItem
                                                    key={`${row.at}-${i}`}
                                                    row={row}
                                                    index={i}
                                                    onOpenTranscript={openTranscript}
                                                />
                                            ))}
                                        </ol>
                                    )}
                                </div>
                            </Card>
                        )}

                        {/* ── Memory tab ────────────────────────────────── */}
                        {!loading && mainTab.id === 2 && (
                            <MemoryPanel
                                loading={memLoading}
                                memory={memory}
                                episodes={episodes}
                            />
                        )}
                    </div>
                </div>
            )}

            {/* Call transcript chat-view (right slide-over) */}
            <CallTranscriptModal
                open={!!transcriptCall}
                onClose={closeTranscript}
                title={transcriptCall?.title || "Call"}
                at={transcriptCall?.at || ""}
                loading={transcriptLoading}
                transcript={transcript}
            />
        </Layout>
    );
}

// ── Memory tab panel ─────────────────────────────────────────────────────────
// Full-width panel shown when the "Memory" tab is active. Two logical sections:
// (1) the durable profile card (what we know, preferences, next-best-action),
// (2) the episode timeline (call + WhatsApp conversation summaries, newest-first).
// Both sections degrade calmly when memory/episodes are empty (flag off / new lead).
function MemoryPanel({
    loading,
    memory,
    episodes,
}: {
    loading: boolean;
    memory: LeadMemory | null;
    episodes: LeadEpisode[];
}) {
    return (
        <div className="space-y-3">
            {/* ── Profile / durable facts card ── */}
            <MemoryProfileCard loading={loading} memory={memory} />

            {/* ── Episode history timeline ── */}
            <EpisodeTimelineCard loading={loading} episodes={episodes} />
        </div>
    );
}

// ── Durable profile card (full-width Memory tab version) ─────────────────────
// Shows the profile facts, preferences, last outcome, and next-best-action from
// the lead_memory row. Dormant-safe: no row -> a calm empty state.
function MemoryProfileCard({
    loading,
    memory,
}: {
    loading: boolean;
    memory: LeadMemory | null;
}) {
    const facts = factEntries(memory?.durable_facts);
    const prefs = factEntries(memory?.preferences);
    const lastOutcome = memory?.last_outcome as Record<string, unknown> | undefined;
    const nba = memory?.next_best_action as Record<string, unknown> | undefined;
    const nbaAction = nba && typeof nba.action === "string" ? nba.action : "";
    const nbaReason = nba && typeof nba.reason === "string" ? nba.reason : "";
    const hasContent = facts.length > 0 || prefs.length > 0 || !!nbaAction || !!lastOutcome;

    return (
        <Card
            title="Relationship Memory"
            headContent={
                memory && !loading ? (
                    <div className="flex items-center gap-3 ml-auto pr-5">
                        {memory.last_channel && (
                            <span className="inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                <Icon
                                    name={memory.last_channel === "whatsapp" ? "send" : "chat"}
                                    className="size-3.5 fill-t-tertiary"
                                />
                                Last via {memory.last_channel}
                            </span>
                        )}
                        <span className="text-caption text-t-tertiary td-num">
                            {memory.episode_count} episode{memory.episode_count === 1 ? "" : "s"}
                        </span>
                    </div>
                ) : undefined
            }
        >
            <div className="px-5 pb-5 max-lg:px-3">
                {loading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
                        {[...Array(3)].map((_, i) => (
                            <div key={i} className="space-y-2">
                                <div className="skeleton h-3.5 w-20" />
                                <div className="skeleton h-4 w-full" />
                                <div className="skeleton h-4 w-3/4" />
                            </div>
                        ))}
                    </div>
                ) : !memory || !hasContent ? (
                    <MemoryEmptyState
                        icon="profile"
                        title="No memory yet"
                        sub="Durable facts, preferences, and conversation insights will appear here after this person's first call or WhatsApp exchange."
                    />
                ) : (
                    <div className="space-y-5">
                        {/* Three-column facts grid */}
                        {(facts.length > 0 || prefs.length > 0) && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-4">
                                {facts.length > 0 && (
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-2">
                                            <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0" />
                                            <span className="text-caption text-t-tertiary uppercase tracking-wide">
                                                What we know
                                            </span>
                                        </div>
                                        <div className="space-y-2.5">
                                            {facts.map(([k, v]) => (
                                                <FactRow key={k} label={k} value={v} />
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {prefs.length > 0 && (
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-2">
                                            <Icon name="heart" className="size-3.5 fill-t-tertiary shrink-0" />
                                            <span className="text-caption text-t-tertiary uppercase tracking-wide">
                                                Preferences
                                            </span>
                                        </div>
                                        <div className="space-y-2.5">
                                            {prefs.map(([k, v]) => (
                                                <FactRow key={k} label={k} value={v} />
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {lastOutcome && Object.keys(lastOutcome).length > 0 && (
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-2">
                                            <Icon name="check-circle" className="size-3.5 fill-t-tertiary shrink-0" />
                                            <span className="text-caption text-t-tertiary uppercase tracking-wide">
                                                Last outcome
                                            </span>
                                        </div>
                                        <div className="space-y-2.5">
                                            {factEntries(lastOutcome).map(([k, v]) => (
                                                <FactRow key={k} label={k} value={v} />
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Divider before NBA */}
                        {nbaAction && (facts.length > 0 || prefs.length > 0) && (
                            <div className="h-px bg-s-subtle" />
                        )}

                        {/* Next-best-action block */}
                        {nbaAction && (
                            <div className="flex items-start gap-3 p-4 rounded-2xl bg-primary-01/6 ring-1 ring-primary-01/16 ring-inset">
                                <span className="grid place-items-center size-9 shrink-0 rounded-full bg-primary-01/12">
                                    <Icon name="magic-pencil" className="size-4.5 fill-primary-01" />
                                </span>
                                <div className="min-w-0">
                                    <div className="text-caption text-primary-01 uppercase tracking-wide mb-0.5">
                                        Next best action
                                    </div>
                                    <div className="text-body-1-str text-t-primary capitalize font-semibold">
                                        {nbaAction.replace(/_/g, " ")}
                                    </div>
                                    {nbaReason && (
                                        <div className="text-body-2 text-t-secondary mt-0.5">
                                            {nbaReason}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Footer: last-seen timestamp */}
                        {memory.last_seen_at && (
                            <div className="text-caption text-t-tertiary">
                                Last seen {fmtRelative(memory.last_seen_at)}
                                {memory.last_channel ? ` · via ${memory.last_channel}` : ""}
                                {memory.updated_at ? ` · updated ${fmtRelative(memory.updated_at)}` : ""}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </Card>
    );
}

// ── Episode timeline card (full-width Memory tab version) ─────────────────────
// Chronological list of every call + WhatsApp conversation, summarised. Each
// episode has a channel icon, date, summary, sentiment pill, outcome chip, and
// any objections raised. Dormant-safe: no episodes -> calm empty state.
function EpisodeTimelineCard({
    loading,
    episodes,
}: {
    loading: boolean;
    episodes: LeadEpisode[];
}) {
    return (
        <Card
            title="Conversation History"
            headContent={
                !loading && episodes.length > 0 ? (
                    <span className="text-caption text-t-tertiary pr-5 ml-auto td-num">
                        {episodes.length} conversation{episodes.length === 1 ? "" : "s"}
                    </span>
                ) : undefined
            }
        >
            <div className="px-5 pb-5 max-lg:px-3">
                {loading ? (
                    <div className="space-y-3 pt-1">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="skeleton h-24 w-full rounded-2xl" />
                        ))}
                    </div>
                ) : episodes.length === 0 ? (
                    <MemoryEmptyState
                        icon="clock"
                        title="No conversations yet"
                        sub="Every call and WhatsApp exchange will be summarised here — channel, outcome, sentiment, and any objections raised — so you always know exactly where this person is in the journey."
                    />
                ) : (
                    <ol className="relative space-y-0 pt-2">
                        {/* connecting spine */}
                        <span
                            className="absolute left-[1.3125rem] top-6 bottom-6 w-px bg-s-subtle"
                            aria-hidden
                        />
                        {episodes.map((ep, idx) => (
                            <EpisodeRow key={ep.id} ep={ep} index={idx} />
                        ))}
                    </ol>
                )}
            </div>
        </Card>
    );
}

// One episode row in the timeline.
function EpisodeRow({ ep, index }: { ep: LeadEpisode; index: number }) {
    const m = kindMeta(ep.channel);
    const sentClass = sentimentPill(ep.sentiment);

    return (
        <li
            className="relative flex gap-4 pb-5 last:pb-1 rise-in"
            style={{ animationDelay: `${Math.min(index * 40, 400)}ms` }}
        >
            {/* channel icon node */}
            <span
                className="relative z-1 grid place-items-center size-[1.625rem] shrink-0 mt-0.5 rounded-full bg-b-surface2 ring-1 ring-s-subtle dark:bg-shade-04/80"
                title={m.label}
            >
                <Icon name={m.icon} className={`size-3.5 ${m.fill}`} />
            </span>

            {/* episode body */}
            <div className="flex-1 min-w-0">
                {/* header row: channel label, outcome, sentiment, date */}
                <div className="flex items-start gap-2 flex-wrap mb-1.5">
                    <span className="text-body-2 font-medium text-t-primary">
                        {m.label}
                    </span>
                    {ep.outcome && (
                        <span className="inline-flex items-center px-2 h-5 rounded-md text-caption capitalize bg-b-surface1 text-t-secondary dark:bg-shade-04/60">
                            {outcomeLabel(ep.outcome)}
                        </span>
                    )}
                    {ep.sentiment && (
                        <span
                            className={`inline-flex items-center px-2 h-5 rounded-full text-caption font-medium capitalize ${sentClass}`}
                        >
                            {ep.sentiment}
                        </span>
                    )}
                    {ep.created_at && (
                        <span className="ml-auto shrink-0 text-caption text-t-tertiary td-num whitespace-nowrap">
                            {fmtRelative(ep.created_at)}
                        </span>
                    )}
                </div>

                {/* summary text */}
                {ep.summary && (
                    <p className="text-body-2 text-t-secondary leading-relaxed">
                        {ep.summary}
                    </p>
                )}

                {/* objection chips */}
                {ep.objections.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                        <span className="text-caption text-t-tertiary self-center">
                            Objections:
                        </span>
                        {ep.objections.map((o, i) => (
                            <span
                                key={i}
                                className="inline-flex items-center px-2 h-5 rounded-full bg-primary-03/10 text-caption text-primary-03"
                            >
                                {o}
                            </span>
                        ))}
                    </div>
                )}
            </div>
        </li>
    );
}

// Shared empty-state atom used inside the memory tab cards.
function MemoryEmptyState({
    icon,
    title,
    sub,
}: {
    icon: string;
    title: string;
    sub: string;
}) {
    return (
        <div className="py-10 text-center">
            <span className="inline-grid place-items-center size-12 mb-3 rounded-full bg-b-surface1 dark:bg-shade-04/60">
                <Icon name={icon} className="fill-t-tertiary size-5" />
            </span>
            <div className="text-body-2-str text-t-primary mb-0.5">{title}</div>
            <div className="max-w-sm mx-auto text-caption text-t-secondary">{sub}</div>
        </div>
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

// ── Call transcript chat-view (right slide-over) ─────────────────────────────
//
// The full ordered transcript for ONE call, rendered as a chat: the CUSTOMER's
// turns are bubbles on the RIGHT (primary tint), the AI's turns on the LEFT
// (neutral surface) — exactly the messaging-app convention the founder asked for.
// The backend already normalizes each turn's `role` to "customer"/"ai", so we
// only switch the side + skin here. Dormant-safe: a call with no stored turns
// shows a calm note rather than an empty void.

function CallTranscriptModal({
    open,
    onClose,
    title,
    at,
    loading,
    transcript,
}: {
    open: boolean;
    onClose: () => void;
    title: string;
    at: string;
    loading: boolean;
    transcript: CallTranscript | null;
}) {
    const turns = transcript?.turns ?? [];
    const dir = transcript?.direction || "";
    return (
        <Modal open={open} onClose={onClose} isSlidePanel>
            <div className="flex flex-col h-svh">
                {/* header */}
                <div className="shrink-0 px-6 pt-6 pb-4 border-b border-s-subtle max-md:px-4">
                    <div className="flex items-center gap-2.5">
                        <span className="grid place-items-center size-9 shrink-0 rounded-full bg-primary-01/12">
                            <Icon name="chat-think" className="size-4.5 fill-primary-01" />
                        </span>
                        <div className="min-w-0">
                            <div className="text-sub-title-1 text-t-primary truncate">
                                {title || "Call transcript"}
                            </div>
                            <div className="flex items-center gap-2 text-caption text-t-tertiary">
                                {dir && (
                                    <span className="capitalize">
                                        {dir === "inbound" ? "Inbound call" : "Outbound call"}
                                    </span>
                                )}
                                {at && (
                                    <span className="td-num" title={fmtDateTime(at)}>
                                        {dir ? "· " : ""}
                                        {fmtRelative(at)}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* chat body */}
                <div className="grow overflow-y-auto px-5 py-5 scrollbar-none max-md:px-4">
                    {loading ? (
                        <div className="grid place-items-center h-full">
                            <Spinner className="!size-10" />
                        </div>
                    ) : turns.length === 0 ? (
                        <div className="grid place-items-center h-full text-center px-4">
                            <div>
                                <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1 dark:bg-shade-04/60">
                                    <Icon name="chat" className="fill-t-tertiary" />
                                </span>
                                <div className="text-body-1-str font-semibold text-t-primary mb-1">
                                    No transcript for this call
                                </div>
                                <div className="max-w-xs mx-auto text-body-2 text-t-secondary">
                                    This call has no saved conversation yet. Transcripts appear here
                                    once a call is answered and the conversation is captured.
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {turns.map((turn) => (
                                <ChatBubble key={turn.seq} turn={turn} />
                            ))}
                        </div>
                    )}
                </div>

                {/* footer legend */}
                {!loading && turns.length > 0 && (
                    <div className="shrink-0 flex items-center justify-center gap-5 px-6 py-3 border-t border-s-subtle text-caption text-t-tertiary max-md:px-4">
                        <span className="inline-flex items-center gap-1.5">
                            <span className="size-2.5 rounded-full bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04/80" />
                            AI agent
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <span className="size-2.5 rounded-full bg-primary-01" />
                            Customer
                        </span>
                    </div>
                )}
            </div>
        </Modal>
    );
}

function ChatBubble({ turn }: { turn: CallTranscript["turns"][number] }) {
    const isCustomer = turn.role === "customer";
    return (
        <div className={`flex ${isCustomer ? "justify-end" : "justify-start"}`}>
            <div className="max-w-[82%]">
                <div className={`mb-1 px-1 text-caption text-t-tertiary ${isCustomer ? "text-right" : ""}`}>
                    {isCustomer ? "Customer" : "AI agent"}
                </div>
                <div
                    className={`px-3.5 py-2.5 text-body-2 text-t-primary whitespace-pre-wrap break-words ${
                        isCustomer
                            ? "bg-primary-01/12 rounded-3xl rounded-br-lg"
                            : "bg-b-surface2 ring-1 ring-s-subtle ring-inset rounded-3xl rounded-bl-lg dark:bg-shade-04/60"
                    }`}
                >
                    {turn.text}
                </div>
            </div>
        </div>
    );
}

// ── One timeline event ───────────────────────────────────────────────────────
function TimelineItem({
    row,
    index,
    onOpenTranscript,
}: {
    row: TimelineRow;
    index: number;
    onOpenTranscript: (row: TimelineRow) => void;
}) {
    const meta = kindMeta(row.kind);
    const inbound = row.direction === "inbound";
    const hasAmount = row.amount != null && row.amount !== 0;
    // A "call" row with a backing id (source_id = call.id || room) opens its full
    // transcript as a chat-view. Other kinds (and id-less call rows) stay static.
    const isCall = (row.kind || "").toLowerCase() === "call";
    const callId = (row.source_id || "").trim();
    const clickable = isCall && !!callId;

    const inner = (
        <>
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
                    {clickable && (
                        <span className="inline-flex items-center gap-1 text-caption text-primary-01 transition-opacity opacity-0 group-hover/tl:opacity-100">
                            <Icon name="chat-think" className="size-3.5 fill-primary-01" />
                            View transcript
                        </span>
                    )}
                </div>
            </div>
        </>
    );

    return (
        <li
            className="relative flex gap-4 pb-6 last:pb-1 rise-in"
            style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}
        >
            {clickable ? (
                <button
                    type="button"
                    onClick={() => onOpenTranscript(row)}
                    className="group/tl flex gap-4 w-full text-left -mx-2 px-2 py-1 -my-1 rounded-2xl transition-colors hover:bg-b-surface1 dark:hover:bg-shade-04/40 cursor-pointer"
                    title="Open full transcript"
                >
                    {inner}
                </button>
            ) : (
                <div className="flex gap-4 w-full">{inner}</div>
            )}
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

// Compact fact row for the memory profile grid.
function FactRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="space-y-0.5">
            <div className="text-caption text-t-tertiary capitalize">{label}</div>
            <div className="text-body-2 text-t-primary capitalize">{value}</div>
        </div>
    );
}

// ── Relationship-memory presentational helpers (W4) ──────────────────────────
// Sentiment -> a full static pill class (Tailwind JIT can't see interpolated tones).
const SENTIMENT_PILL: Record<string, string> = {
    positive: "bg-primary-04/12 text-primary-04",
    negative: "bg-primary-03/12 text-primary-03",
    mixed: "bg-primary-05/12 text-primary-05",
    neutral: "bg-b-surface1 dark:bg-shade-04/60 text-t-secondary",
};
function sentimentPill(s?: string): string {
    return SENTIMENT_PILL[(s || "").toLowerCase()] ?? SENTIMENT_PILL.neutral;
}
// Outcome -> human label (the writer's enum). Falls back to a humanised string.
const OUTCOME_LABEL: Record<string, string> = {
    booked: "Booked",
    interested: "Interested",
    callback: "Callback",
    not_interested: "Not interested",
    wrong_number: "Wrong number",
    no_answer: "No answer",
    info_only: "Info only",
    other: "Other",
};
function outcomeLabel(o?: string): string {
    const k = (o || "").toLowerCase();
    return OUTCOME_LABEL[k] ?? (o ? o.replace(/_/g, " ") : "—");
}
// Render a flat facts/preferences map as label·value rows (skip empty/nested junk).
function factEntries(obj?: Record<string, unknown>): [string, string][] {
    if (!obj || typeof obj !== "object") return [];
    const out: [string, string][] = [];
    for (const [k, v] of Object.entries(obj)) {
        if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
        let val: string;
        if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
            val = String(v);
        } else if (Array.isArray(v)) {
            val = v.map((x) => String(x)).join(", ");
        } else {
            // a nested object — flatten one level to a compact string
            try {
                val = Object.entries(v as Record<string, unknown>)
                    .filter(([, x]) => x != null && x !== "")
                    .map(([kk, x]) => `${kk}: ${String(x)}`)
                    .join(", ");
            } catch {
                continue;
            }
        }
        if (val.trim()) out.push([k.replace(/_/g, " "), val]);
    }
    return out;
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
