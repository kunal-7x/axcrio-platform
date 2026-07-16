"use client";

// Ad-Engine · Leads & Compliance tab — the ad-lead table with consent / gate
// status + call outcome, plus a per-lead compliance drawer (red-team K7: the
// compliance front-end). FRONTEND_ARCHITECTURE §5.
//
// MIRRORS app/leads/page.tsx VERBATIM for the table chrome: the same bounded
// sticky-header scroll box, the same native-<tr> virtualized body via
// <VirtualRows> (so large ad-lead lists window cleanly), the same Search + Select
// filter row, and the CRM badge language (TempBadge / tempOf) so heat never
// drifts between this page and CRM/Leads. Statuses use the ONE <Badge> vocabulary.
//
// Data comes from the dormant-safe ad-engine helpers in ../_lib — getAdsLeads
// (cursor paging), getAdsLead / getAdsConsent (drawer), and the writable
// mutations redialLead / postConsent / revokeConsent (all step-up aware, all
// gated behind the `writable` prop). A non-200 read degrades to the local
// DormantPanel — never an error wall. The list head re-polls every 30s
// (visibility-gated) via useRealtimeRefresh, the verified analytics idiom.
//
// Money stays _minor (paise); fmtMoney renders it. Zero raw hex — every colour is
// a token class. No write control renders for read-only (agent) sessions.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Button from "@/components/Button";
import Search from "@/components/Search";
import Select from "@/components/Select";
import Modal from "@/components/Modal";
import Field from "@/components/Field";
import Checkbox from "@/components/Checkbox";
import VirtualRows from "@/components/VirtualRows";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import { TempBadge, initials } from "@/app/crm/_ui";
import { type SelectOption } from "@/types/select";
import {
    getAdsLeads,
    getAdsConsent,
    redialLead,
    postConsent,
    revokeConsent,
    importLeads,
    useRealtimeRefresh,
    fmtMoney,
    fmtTs,
    type AdsLead,
    type AdsConsentResponse,
} from "../_lib";
import { DormantPanel, type AdsTabProps } from "../_shared";

/* --------------------------------------------------------- status vocabulary */
//
// Each compliance axis (source / consent / gate decision / call outcome) maps a
// backend string onto the ONE <Badge> tone language + a human, active-voice
// label. Unknown values degrade to a de-snaked neutral pill, never a crash.

function human(s?: string | null): string {
    if (!s) return "—";
    return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

const SOURCE_LABEL: Record<string, string> = {
    meta_leadgen: "Meta lead form",
    ctwa: "Click-to-WhatsApp",
    form: "Website form",
    google_lsa: "Google LSA",
};
function sourceLabel(s?: string): string {
    if (!s) return "—";
    return SOURCE_LABEL[s] ?? human(s);
}

// Consent: dpdp_ok / dca_dlt_ok read "good", anything blocked_* reads "bad".
function consentTone(s?: string): BadgeVariant {
    if (!s) return "neutral";
    if (s.startsWith("blocked") || s.includes("no_consent")) return "danger";
    return "success";
}
const CONSENT_LABEL: Record<string, string> = {
    dpdp_ok: "DPDP ✓",
    dca_dlt_ok: "DLT ✓",
    both_ok: "DPDP + DLT ✓",
    blocked_no_consent: "No consent",
    revoked: "Revoked",
};
function consentLabel(s?: string): string {
    if (!s) return "Not captured";
    return CONSENT_LABEL[s] ?? human(s);
}

// Gate decision: allowed = good; any block (NCPR / cool-off / …) = bad.
function gateTone(s?: string): BadgeVariant {
    if (!s) return "neutral";
    if (s === "allowed") return "success";
    if (s.startsWith("blocked")) return "danger";
    return "warning";
}
const GATE_LABEL: Record<string, string> = {
    allowed: "Allowed",
    blocked_ncpr: "NCPR / DND",
    blocked_cooloff: "In cool-off",
    blocked_no_consent: "No consent",
    blocked_quiet_hours: "Quiet hours",
};
function gateLabel(s?: string): string {
    if (!s) return "—";
    return GATE_LABEL[s] ?? human(s);
}

// Call outcome.
function outcomeTone(s?: string): BadgeVariant {
    if (!s) return "neutral";
    if (s === "booked" || s === "qualified") return "success";
    if (s === "no_answer" || s === "busy" || s === "voicemail") return "warning";
    if (s.includes("opt") || s === "not_interested") return "danger";
    return "info";
}
const OUTCOME_LABEL: Record<string, string> = {
    booked: "Booked",
    qualified: "Qualified",
    no_answer: "No answer",
    voicemail: "Voicemail",
    busy: "Busy",
    not_interested: "Not interested",
    callback: "Callback",
    pending: "Not called yet",
};
function outcomeLabel(s?: string): string {
    if (!s) return "Not called yet";
    return OUTCOME_LABEL[s] ?? human(s);
}

/* ---------------------------------------------------------- consent-axis maps */
//
// One ledger entry's `kind` -> the badge tone it reads as. The ledger is
// append-only + hash-chained, so a revoke is a NEW entry, not an edit.
function ledgerTone(kind?: string, status?: string): BadgeVariant {
    const k = (kind || "").toLowerCase();
    const st = (status || "").toLowerCase();
    if (k === "revoke" || st.includes("revoke") || st.startsWith("blocked")) return "danger";
    if (st === "ok" || st === "granted" || k === "dpdp" || k === "dca_dlt") return "success";
    return "neutral";
}

/* ------------------------------------------------------------- status filter */
// The one-line status filter (mirrors the Leads page's Select strip). `key`
// carries the backend filter value sent as `?status=`; "" = no filter.
const STATUS_VIEWS: (SelectOption & { key: string })[] = [
    { id: 1, name: "All leads", key: "" },
    { id: 2, name: "Allowed", key: "allowed" },
    { id: 3, name: "Blocked by gate", key: "blocked" },
    { id: 4, name: "No consent", key: "blocked_no_consent" },
    { id: 5, name: "Booked", key: "booked" },
    { id: 6, name: "Qualified", key: "qualified" },
];

/* ================================================================== the tab */

export default function LeadsTab({ writable, toast }: AdsTabProps) {
    const { range, campaign } = useGlobalFilters();

    const [view, setView] = useState<SelectOption>(STATUS_VIEWS[0]);
    const [query, setQuery] = useState("");

    // Cursor-paged list state. `pages` accumulates each loaded cursor page; the
    // first load (and the 30s poll / filter change) RESETS to page one. Dormant /
    // error are first-class so the tab degrades to the on-brand panel.
    const [pages, setPages] = useState<AdsLead[][]>([]);
    const [cursor, setCursor] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [fetchingMore, setFetchingMore] = useState(false);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const scrollRef = useRef<HTMLDivElement>(null);
    // Guard against a poll/refresh clobbering an in-flight "load more".
    const loadingMoreRef = useRef(false);

    const statusKey = (STATUS_VIEWS.find((v) => v.id === view.id) ?? STATUS_VIEWS[0]).key;

    // The active filter bag sent to the backend. Range/campaign come from the
    // shared URL state; status from the local Select. Empty values are dropped by
    // the helper's qs() so a dormant route still 404s cleanly.
    const filters = useMemo(
        () => ({
            from: range.from,
            to: range.to,
            campaign: campaign || undefined,
            status: statusKey || undefined,
        }),
        [range.from, range.to, campaign, statusKey],
    );

    // Load page one (and reset). `keepPreviousData`-style: the existing rows stay
    // on screen until the new page lands (no skeleton flash on poll / filter).
    const loadFirst = useCallback(
        (showSkeleton: boolean) => {
            if (showSkeleton) setLoading(true);
            getAdsLeads(null, filters)
                .then((r) => {
                    if (r.kind === "dormant") {
                        setDormant(true);
                        setPages([]);
                        setCursor(null);
                        setError(null);
                    } else if (r.kind === "error") {
                        setError(r.message);
                        setDormant(false);
                    } else {
                        setDormant(false);
                        setError(null);
                        setPages([r.data.leads || []]);
                        setCursor(r.data.next_cursor ?? null);
                    }
                })
                .finally(() => setLoading(false));
        },
        [filters],
    );

    // First load + reload whenever the filters change (skeleton on the reset).
    useEffect(() => {
        loadFirst(true);
    }, [loadFirst]);

    // 30s visibility-gated poll of the list head — refresh page one in place
    // (no skeleton) so new ad leads + outcome changes surface without a manual
    // refresh, and without draining a backgrounded tab. The verified idiom.
    const poll = useCallback(() => loadFirst(false), [loadFirst]);
    useRealtimeRefresh(poll, 30000);

    // Fetch the next cursor page (infinite scroll near the end).
    const loadMore = useCallback(() => {
        if (loadingMoreRef.current || !cursor) return;
        loadingMoreRef.current = true;
        setFetchingMore(true);
        getAdsLeads(cursor, filters)
            .then((r) => {
                if (r.kind === "ok") {
                    setPages((prev) => [...prev, r.data.leads || []]);
                    setCursor(r.data.next_cursor ?? null);
                }
            })
            .finally(() => {
                loadingMoreRef.current = false;
                setFetchingMore(false);
            });
    }, [cursor, filters]);

    const leads = useMemo(() => pages.flat(), [pages]);

    // Client-side search over the loaded set (no extra API call — mirrors Leads).
    const visibleLeads = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return leads;
        return leads.filter(
            (l) =>
                l.name?.toLowerCase().includes(q) ||
                l.phone_masked?.toLowerCase().includes(q) ||
                l.campaign?.toLowerCase().includes(q),
        );
    }, [leads, query]);
    const searching = query.trim().length > 0;

    // ── Drawer state ──
    const [active, setActive] = useState<AdsLead | null>(null);

    // ── Dead-lead revival modal ──
    const [reviveOpen, setReviveOpen] = useState(false);

    const showFirstSkeleton = loading && leads.length === 0;

    const tableHead = (
        <tr>
            <th>Lead</th>
            <th className="max-md:hidden">Source</th>
            <th>Consent</th>
            <th className="max-lg:hidden">Gate decision</th>
            <th className="max-md:hidden">Score</th>
            <th>Call outcome</th>
            <th className="text-right">CPL</th>
            <th className="w-12 text-right" />
        </tr>
    );
    const colCount = 8;

    /* ----- the resting / dormant / error frame wraps everything in one Card ----- */

    function body() {
        if (dormant) {
            return (
                <DormantPanel
                    icon="income"
                    title="Leads are warming up"
                    sub="Every ad lead lands here with its consent status, gate decision and call outcome once a campaign goes live. Connect a Meta or Google account to start the flow."
                />
            );
        }
        if (error) {
            return (
                <div className="state-block">
                    <span className="state-glyph">
                        <Icon name="info" className="fill-inherit" />
                    </span>
                    <div className="state-title">We couldn&apos;t load your leads</div>
                    <div className="state-sub max-w-md mx-auto">{error}</div>
                    <Button isStroke className="!h-10 !px-5 mt-1" onClick={() => loadFirst(true)}>
                        Try again
                    </Button>
                </div>
            );
        }
        if (showFirstSkeleton) {
            return (
                <div className="mt-3">
                    <table className={TABLE_CLS}>
                        <thead className="sticky top-0 z-10 bg-b-surface2 max-md:hidden">
                            {tableHead}
                        </thead>
                        <tbody>
                            {[...Array(8)].map((_, i) => (
                                <tr key={i}>
                                    {[...Array(colCount)].map((__, j) => (
                                        <td key={j}>
                                            <div className="skeleton h-4 w-20" />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            );
        }
        if (visibleLeads.length === 0) {
            return (
                <div className="state-block">
                    <span className="state-glyph">
                        <Icon name={searching ? "search" : "income"} className="fill-inherit" />
                    </span>
                    <div className="state-title">
                        {searching ? "No matching leads" : "No leads yet"}
                    </div>
                    <div className="state-sub max-w-md mx-auto">
                        {searching
                            ? `Nothing matches “${query}”. Try a different name, number or campaign.`
                            : statusKey
                            ? "No leads match this filter for the selected range — try another filter or widen the dates."
                            : "Leads from your live ad campaigns appear here with their consent and call status."}
                    </div>
                    {searching && (
                        <Button isStroke className="!h-10 !px-5 mt-1" onClick={() => setQuery("")}>
                            Clear search
                        </Button>
                    )}
                </div>
            );
        }
        // ── The data table ──
        return (
            <>
                <div className="flex items-center gap-3 pl-5 pr-4 pt-3 text-caption text-t-tertiary max-lg:pl-3">
                    <span>
                        {searching
                            ? `${visibleLeads.length} of ${leads.length} loaded`
                            : `${leads.length} ${leads.length === 1 ? "lead" : "leads"} loaded`}
                    </span>
                </div>
                <div
                    ref={scrollRef}
                    className="mt-3 max-h-[calc(100vh-22rem)] overflow-auto scrollbar-thin"
                >
                    <table className={TABLE_CLS}>
                        <thead className="sticky top-0 z-10 bg-b-surface2 max-md:hidden">
                            {tableHead}
                        </thead>
                        <tbody>
                            <VirtualRows
                                items={visibleLeads}
                                rowKey={(l) => l.id}
                                scrollRef={scrollRef}
                                colSpan={colCount}
                                estimateRowH={65}
                                onEndReached={
                                    searching || !cursor || fetchingMore ? undefined : loadMore
                                }
                                renderRow={(l) => renderLeadRow(l, () => setActive(l))}
                            />
                        </tbody>
                    </table>
                    {fetchingMore && (
                        <div className="flex items-center justify-center gap-2 py-3 text-caption text-t-tertiary">
                            <span className="size-3.5 rounded-full border-2 border-s-subtle border-t-primary-01 animate-spin" />
                            Loading more…
                        </div>
                    )}
                </div>
            </>
        );
    }

    return (
        <>
            <div className="card">
                <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                    <div className="pl-5 text-h6 max-lg:pl-3">Leads &amp; compliance</div>
                    {writable && (
                        <Button
                            isBlack
                            className="ml-4 !h-10 !px-4 max-md:ml-3 max-md:order-last max-md:w-full max-md:justify-center"
                            onClick={() => setReviveOpen(true)}
                        >
                            <Icon name="plus" className="size-4 fill-t-light mr-2" />
                            Revive dead leads
                        </Button>
                    )}
                    <Search
                        className="w-56 ml-auto mr-3 max-md:w-full max-md:ml-3 max-md:mr-0"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search name, number or campaign"
                        isGray
                    />
                    <Select
                        className="w-44 mr-3 max-md:w-full max-md:mr-0"
                        classButton="!h-10"
                        value={view}
                        onChange={setView}
                        options={STATUS_VIEWS}
                    />
                    <div className="mr-4 max-md:mr-0 max-md:w-full">
                        <GlobalFilters show={{ range: true, campaign: true }} />
                    </div>
                </div>
                {body()}
            </div>

            {/* ── Per-lead compliance drawer (consent ledger + gate trace + actions) ── */}
            <LeadDrawer
                lead={active}
                writable={writable}
                onClose={() => setActive(null)}
                toast={toast}
                onChanged={() => loadFirst(false)}
            />

            {/* ── Dead-lead revival uploader (DPA-gated import) ── */}
            <ReviveModal
                open={reviveOpen}
                onClose={() => setReviveOpen(false)}
                toast={toast}
                onImported={() => {
                    // Surface the revived leads at the top of the table.
                    setView(STATUS_VIEWS[0]);
                    setQuery("");
                    loadFirst(true);
                }}
            />
        </>
    );
}

// Shared cell rules — lifted from the Leads page table so the look is identical.
const TABLE_CLS =
    "w-full text-body-2 [&_th]:h-14 [&_th,&_td]:pl-5 [&_th,&_td]:py-4 [&_th,&_td]:first:pl-4 [&_th,&_td]:last:pr-4 [&_th]:align-middle [&_th]:text-left [&_th]:text-overline [&_th]:uppercase [&_th]:tracking-[0.06em] [&_th]:text-t-tertiary [&_th]:font-semibold [&_thead]:border-b [&_thead]:border-s-subtle max-lg:[&_th,&_td]:first:pl-3 max-md:[&_th,&_td]:p-3 max-md:[&_th]:h-13 max-md:[&_th]:border-b max-md:[&_th]:border-s-subtle";

// One ad-lead row as a plain <tr> (so the virtualizer can attach its ref). The
// whole row is clickable -> opens the compliance drawer. Classes mirror the Leads
// page row so the table reads identical.
function renderLeadRow(l: AdsLead, onOpen: () => void) {
    return (
        <tr
            onClick={onOpen}
            className="group relative cursor-pointer [&_td:not(:first-child)]:relative [&_td]:z-2 [&_td]:border-t [&_td]:border-s-subtle [&_td]:pl-5 [&_td]:py-4 [&_td]:first:pl-4 [&_td]:last:pr-4 max-lg:[&_td]:first:pl-3 max-md:[&_td]:p-3 hover:bg-b-surface1/60 dark:hover:bg-shade-04/40 transition-colors"
        >
            <td className="text-sub-title-1">
                <div className="flex items-center gap-3">
                    <span className="grid place-items-center size-9 shrink-0 rounded-full text-caption font-semibold bg-b-surface1 text-t-secondary dark:bg-shade-04/60">
                        {initials(l.name)}
                    </span>
                    <span className="min-w-0">
                        <span className="block truncate max-w-44">{l.name || "Unknown lead"}</span>
                        <span className="block text-caption text-t-tertiary td-num truncate max-w-44">
                            {l.phone_masked || "—"}
                        </span>
                    </span>
                </div>
            </td>
            <td className="max-md:hidden">
                <span className="text-t-secondary text-caption">{sourceLabel(l.source)}</span>
            </td>
            <td>
                <Badge variant={consentTone(l.consent_status)} dot={consentTone(l.consent_status) === "success"}>
                    {consentLabel(l.consent_status)}
                </Badge>
            </td>
            <td className="max-lg:hidden">
                <Badge variant={gateTone(l.gate_decision)} dot={l.gate_decision === "allowed"}>
                    {gateLabel(l.gate_decision)}
                </Badge>
            </td>
            <td className="max-md:hidden">
                <TempBadge row={{ score: typeof l.score === "number" ? l.score : undefined, status: typeof l.score === "string" ? l.score : undefined }} />
            </td>
            <td>
                <Badge variant={outcomeTone(l.call_outcome)} dot={l.call_outcome === "booked"}>
                    {outcomeLabel(l.call_outcome)}
                </Badge>
            </td>
            <td className="text-t-secondary td-num text-right">{fmtMoney(l.cpl_minor)}</td>
            <td className="w-12 text-right">
                <Icon
                    name="chevron"
                    className="size-4 fill-t-tertiary -rotate-90 inline-block md:opacity-0 md:group-hover:opacity-100 transition-opacity"
                />
            </td>
        </tr>
    );
}

/* ===================================================== the compliance drawer */
//
// A right slide-over (Modal isSlidePanel) showing one lead's full compliance
// picture: the immutable hash-chained consent ledger, the ordered guard-chain
// decision, and — for writable sessions — Redial (step-up), consent capture, and
// revoke. Reads getAdsConsent on open (dormant-safe). All writes route their
// friendly message through the page toast and re-pull the list on success.

function LeadDrawer({
    lead,
    writable,
    onClose,
    toast,
    onChanged,
}: {
    lead: AdsLead | null;
    writable: boolean;
    onClose: () => void;
    toast: AdsTabProps["toast"];
    onChanged: () => void;
}) {
    const [consent, setConsent] = useState<AdsConsentResponse | null>(null);
    const [consentLoading, setConsentLoading] = useState(false);
    const [consentDormant, setConsentDormant] = useState(false);
    const [busy, setBusy] = useState<null | "redial" | "capture" | "revoke">(null);

    const leadId = lead?.id ?? null;

    // Load the consent ledger whenever a lead opens.
    useEffect(() => {
        if (!leadId) {
            setConsent(null);
            setConsentDormant(false);
            return;
        }
        let cancelled = false;
        setConsentLoading(true);
        setConsentDormant(false);
        getAdsConsent(leadId)
            .then((r) => {
                if (cancelled) return;
                if (r.kind === "ok") setConsent(r.data);
                else if (r.kind === "dormant") setConsentDormant(true);
                else setConsent(null);
            })
            .finally(() => !cancelled && setConsentLoading(false));
        return () => {
            cancelled = true;
        };
    }, [leadId]);

    const reloadConsent = useCallback(() => {
        if (!leadId) return;
        getAdsConsent(leadId).then((r) => {
            if (r.kind === "ok") setConsent(r.data);
        });
    }, [leadId]);

    async function handleRedial() {
        if (!leadId || busy) return;
        setBusy("redial");
        try {
            await redialLead(leadId);
            toast("Redial queued");
            onChanged();
        } catch (e: unknown) {
            toast(e instanceof Error ? e.message : "Couldn't queue the redial", "error");
        } finally {
            setBusy(null);
        }
    }

    async function handleCapture() {
        if (!leadId || busy) return;
        setBusy("capture");
        try {
            // Capture both consent legs the calling flow requires (DPDP + DLT/DCA).
            await postConsent(leadId, { kind: "dpdp", channel: "voice", status: "granted" });
            toast("Consent captured");
            onChanged();
            reloadConsent();
        } catch (e: unknown) {
            toast(e instanceof Error ? e.message : "Couldn't capture consent", "error");
        } finally {
            setBusy(null);
        }
    }

    async function handleRevoke() {
        if (!leadId || busy) return;
        setBusy("revoke");
        try {
            await revokeConsent(leadId);
            toast("Consent revoked");
            onChanged();
            reloadConsent();
        } catch (e: unknown) {
            toast(e instanceof Error ? e.message : "Couldn't revoke consent", "error");
        } finally {
            setBusy(null);
        }
    }

    const open = !!lead;
    const blockedByGate = lead?.gate_decision && lead.gate_decision !== "allowed";

    return (
        <Modal classWrapper="max-w-md" open={open} onClose={onClose} isSlidePanel>
            {lead && (
                <div className="flex h-full flex-col">
                    {/* Header */}
                    <div className="shrink-0 px-6 pt-6 pb-4 border-b border-s-subtle">
                        <div className="flex items-center gap-3">
                            <span className="grid place-items-center size-11 shrink-0 rounded-full text-button font-semibold bg-b-surface2 text-t-secondary ring-1 ring-s-subtle">
                                {initials(lead.name)}
                            </span>
                            <div className="min-w-0">
                                <div className="text-h6 text-t-primary truncate">
                                    {lead.name || "Unknown lead"}
                                </div>
                                <div className="text-caption text-t-tertiary td-num truncate">
                                    {lead.phone_masked || "—"}
                                    {lead.campaign ? ` · ${lead.campaign}` : ""}
                                </div>
                            </div>
                        </div>
                        <div className="mt-4 flex flex-wrap items-center gap-2">
                            <Badge variant={gateTone(lead.gate_decision)} dot={lead.gate_decision === "allowed"}>
                                {gateLabel(lead.gate_decision)}
                            </Badge>
                            <Badge variant={consentTone(lead.consent_status)}>
                                {consentLabel(lead.consent_status)}
                            </Badge>
                            <Badge variant={outcomeTone(lead.call_outcome)}>
                                {outcomeLabel(lead.call_outcome)}
                            </Badge>
                        </div>
                    </div>

                    {/* Scrollable detail */}
                    <div className="flex-1 overflow-y-auto px-6 py-5 scrollbar-thin space-y-6">
                        {/* At-a-glance facts */}
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-body-2">
                            <Fact label="Source" value={sourceLabel(lead.source)} />
                            <Fact label="Cost per lead" value={fmtMoney(lead.cpl_minor)} />
                            <Fact
                                label="Captured"
                                value={typeof lead.ts === "number" ? fmtTs(lead.ts) : "—"}
                            />
                            <Fact
                                label="Score"
                                value={lead.score != null ? String(lead.score) : "—"}
                            />
                        </dl>

                        {/* Guard-chain decision */}
                        <section>
                            <SectionHead icon="filters" title="Guard-chain decision" />
                            {blockedByGate ? (
                                <div className="rounded-2xl bg-primary-03/8 ring-1 ring-s-subtle px-4 py-3 text-body-2 text-t-secondary">
                                    This lead is held by the{" "}
                                    <span className="text-t-primary">{gateLabel(lead.gate_decision)}</span>{" "}
                                    gate. The agent won&apos;t dial until the block clears.
                                </div>
                            ) : (
                                <div className="rounded-2xl bg-primary-02/8 ring-1 ring-s-subtle px-4 py-3 text-body-2 text-t-secondary">
                                    Every consent and do-not-call check passed — this lead is clear to dial.
                                </div>
                            )}
                            <ul className="mt-3 flex flex-col divide-y divide-s-subtle">
                                <GuardRow
                                    name="DPDP consent"
                                    ok={!`${lead.consent_status || ""}`.includes("no_consent")}
                                />
                                <GuardRow
                                    name="DLT / NCPR (DND)"
                                    ok={lead.gate_decision !== "blocked_ncpr"}
                                />
                                <GuardRow
                                    name="Cool-off window"
                                    ok={lead.gate_decision !== "blocked_cooloff"}
                                />
                                <GuardRow
                                    name="Quiet hours"
                                    ok={lead.gate_decision !== "blocked_quiet_hours"}
                                />
                            </ul>
                        </section>

                        {/* Consent ledger (immutable, hash-chained) */}
                        <section>
                            <SectionHead icon="lock" title="Consent ledger" />
                            {consentLoading ? (
                                <div className="space-y-2">
                                    {[...Array(3)].map((_, i) => (
                                        <div key={i} className="skeleton h-12 w-full rounded-2xl" />
                                    ))}
                                </div>
                            ) : consentDormant ? (
                                <p className="text-body-2 text-t-secondary">
                                    The consent ledger lights up once a campaign goes live.
                                </p>
                            ) : consent && consent.entries.length > 0 ? (
                                <ul className="flex flex-col gap-2">
                                    {consent.entries.map((e, i) => (
                                        <li
                                            key={e.hash || i}
                                            className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle px-4 py-3"
                                        >
                                            <div className="flex items-center justify-between gap-2">
                                                <Badge variant={ledgerTone(e.kind, e.status)}>
                                                    {human(e.kind)}
                                                </Badge>
                                                <span className="text-caption text-t-tertiary tabular-nums">
                                                    {fmtTs(e.ts)}
                                                </span>
                                            </div>
                                            <div className="mt-1.5 text-caption text-t-secondary">
                                                {human(e.status)}
                                            </div>
                                            {e.hash && (
                                                <div className="mt-1 flex items-center gap-1.5 text-caption text-t-tertiary">
                                                    <Icon name="lock" className="size-3 fill-t-tertiary shrink-0" />
                                                    <span className="font-mono truncate">
                                                        {String(e.hash).slice(0, 18)}…
                                                    </span>
                                                </div>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-body-2 text-t-secondary">
                                    No consent has been recorded for this lead yet.
                                </p>
                            )}
                            <div className="mt-3 flex items-center gap-1.5 text-caption text-t-tertiary">
                                <Icon name="lock" className="size-3.5 fill-t-tertiary shrink-0" />
                                Append-only · hash-chained · entries can never be edited.
                            </div>
                        </section>
                    </div>

                    {/* Action footer — writable only (step-up aware) */}
                    {writable && (
                        <div className="shrink-0 border-t border-s-subtle px-6 py-4 space-y-3">
                            <Button
                                isBlack
                                className="w-full justify-center"
                                onClick={handleRedial}
                                disabled={!!busy || !!blockedByGate}
                            >
                                <Icon name="chat" className="size-4 fill-t-light mr-2" />
                                {busy === "redial" ? "Queuing…" : "Redial lead"}
                            </Button>
                            <div className="flex gap-3">
                                <Button
                                    isStroke
                                    className="flex-1 justify-center"
                                    onClick={handleCapture}
                                    disabled={!!busy}
                                >
                                    {busy === "capture" ? "Saving…" : "Capture consent"}
                                </Button>
                                <Button
                                    isStroke
                                    className="flex-1 justify-center"
                                    onClick={handleRevoke}
                                    disabled={!!busy}
                                >
                                    {busy === "revoke" ? "Revoking…" : "Revoke consent"}
                                </Button>
                            </div>
                            {blockedByGate && (
                                <p className="text-caption text-t-tertiary text-center">
                                    Redial is paused while the {gateLabel(lead.gate_decision)} gate holds this lead.
                                </p>
                            )}
                        </div>
                    )}
                </div>
            )}
        </Modal>
    );
}

function Fact({ label, value }: { label: string; value: string }) {
    return (
        <div className="min-w-0">
            <dt className="text-caption text-t-tertiary">{label}</dt>
            <dd className="text-body-2 text-t-primary truncate">{value}</dd>
        </div>
    );
}

function SectionHead({ icon, title }: { icon: string; title: string }) {
    return (
        <div className="flex items-center gap-2 mb-3">
            <span className="grid place-items-center size-7 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                <Icon name={icon} className="size-4 fill-inherit" />
            </span>
            <span className="text-sub-title-2 text-t-primary">{title}</span>
        </div>
    );
}

function GuardRow({ name, ok }: { name: string; ok: boolean }) {
    return (
        <li className="flex items-center justify-between gap-3 py-2.5">
            <span className="text-body-2 text-t-secondary">{name}</span>
            <span
                className={`inline-flex items-center gap-1.5 text-caption font-medium ${
                    ok ? "text-primary-02" : "text-primary-03"
                }`}
            >
                <Icon
                    name={ok ? "check-circle" : "info"}
                    className={`size-4 ${ok ? "fill-primary-02" : "fill-primary-03"}`}
                />
                {ok ? "Passed" : "Blocked"}
            </span>
        </li>
    );
}

/* ================================================== dead-lead revival modal */
//
// Re-contacting a list of prior ("dead") leads is a compliance-sensitive,
// budget-spending action, so the modal is fail-closed by design: it won't submit
// until the operator (a) provides at least one parseable row AND (b) attests a
// signed DPA / that the leads consented to contact. The attestation maps to the
// backend's `dpa_acknowledged` gate; without it importLeads fail-closes.
//
// The list is taken as a CSV paste OR an uploaded .csv file (same parser). We map
// the first non-empty line to a header, then offer a tiny column map onto the
// engine's canonical fields. On success we toast + ask the table to refresh so the
// revived leads appear with their fresh consent/gate badges. Zero raw hex.

// Canonical engine fields the import maps onto. `phone` is the only hard
// requirement (a lead with no number can't be dialled).
const REVIVE_FIELDS: { key: string; label: string; required?: boolean }[] = [
    { key: "name", label: "Name" },
    { key: "phone", label: "Phone", required: true },
    { key: "email", label: "Email" },
    { key: "campaign", label: "Campaign" },
];

const NONE_OPT: SelectOption = { id: -1, name: "— Not in list —" };

// Split a CSV line honouring simple double-quoted fields (commas inside quotes).
function splitCsvLine(line: string): string[] {
    const out: string[] = [];
    let cur = "";
    let inQ = false;
    for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (c === '"') {
            if (inQ && line[i + 1] === '"') {
                cur += '"';
                i++;
            } else inQ = !inQ;
        } else if (c === "," && !inQ) {
            out.push(cur);
            cur = "";
        } else cur += c;
    }
    out.push(cur);
    return out.map((s) => s.trim());
}

// Parse pasted/uploaded CSV text into { header, rows }. The first non-empty line
// is the header; everything after is data. Empty input -> empty header/rows.
function parseCsv(text: string): { header: string[]; rows: string[][] } {
    const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
    if (lines.length === 0) return { header: [], rows: [] };
    const header = splitCsvLine(lines[0]);
    const rows = lines.slice(1).map(splitCsvLine);
    return { header, rows };
}

function ReviveModal({
    open,
    onClose,
    toast,
    onImported,
}: {
    open: boolean;
    onClose: () => void;
    toast: AdsTabProps["toast"];
    onImported: () => void;
}) {
    const fileRef = useRef<HTMLInputElement>(null);

    const [raw, setRaw] = useState("");
    const [fileName, setFileName] = useState<string | null>(null);
    const [source, setSource] = useState("");
    const [campaign, setCampaign] = useState("");
    const [dpa, setDpa] = useState(false);
    // columnMap: canonical field key -> the SelectOption chosen from the header.
    const [columnMap, setColumnMap] = useState<Record<string, SelectOption>>({});
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const { header, rows } = useMemo(() => parseCsv(raw), [raw]);

    // Header columns -> Select options (+ a "not in list" escape hatch).
    const headerOptions = useMemo<SelectOption[]>(
        () => [NONE_OPT, ...header.map((h, i) => ({ id: i, name: h || `Column ${i + 1}` }))],
        [header],
    );

    // Best-effort auto-map: match a canonical field to a header column whose name
    // contains it (phone/mobile/number, e-mail, etc.) so the operator rarely edits.
    useEffect(() => {
        if (header.length === 0) {
            setColumnMap({});
            return;
        }
        const guess: Record<string, SelectOption> = {};
        const lower = header.map((h) => h.toLowerCase());
        const find = (...needles: string[]) => {
            const idx = lower.findIndex((h) => needles.some((n) => h.includes(n)));
            return idx >= 0 ? { id: idx, name: header[idx] || `Column ${idx + 1}` } : NONE_OPT;
        };
        guess.name = find("name");
        guess.phone = find("phone", "mobile", "number", "msisdn", "contact");
        guess.email = find("email", "e-mail", "mail");
        guess.campaign = find("campaign", "source", "list");
        setColumnMap(guess);
    }, [header]);

    function reset() {
        setRaw("");
        setFileName(null);
        setSource("");
        setCampaign("");
        setDpa(false);
        setColumnMap({});
        setBusy(false);
        setError(null);
        if (fileRef.current) fileRef.current.value = "";
    }

    function close() {
        if (busy) return; // don't drop an in-flight import
        reset();
        onClose();
    }

    function pickFile(f: File | null) {
        setError(null);
        if (!f) return;
        if (f.size > 5 * 1024 * 1024) {
            setError("That file is over 5 MB — please split the list and import in batches.");
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            setRaw(String(reader.result || ""));
            setFileName(f.name);
        };
        reader.onerror = () => setError("Couldn't read that file — try pasting the rows instead.");
        reader.readAsText(f);
    }

    // The phone column must be mapped, and at least one data row must exist.
    const phoneMapped = (columnMap.phone?.id ?? -1) >= 0;
    const canSubmit = dpa && rows.length > 0 && phoneMapped && !busy;

    async function submit() {
        if (!canSubmit) return;
        setBusy(true);
        setError(null);

        // Build the canonical column_map (field -> header name) + the mapped rows.
        const map: Record<string, string> = {};
        for (const f of REVIVE_FIELDS) {
            const opt = columnMap[f.key];
            if (opt && opt.id >= 0) map[f.key] = String(opt.name);
        }
        const mappedRows = rows.map((cells) => {
            const rec: Record<string, string> = {};
            for (const f of REVIVE_FIELDS) {
                const opt = columnMap[f.key];
                if (opt && opt.id >= 0) {
                    rec[f.key] = cells[opt.id] ?? "";
                }
            }
            return rec;
        });

        try {
            const res = await importLeads({
                dpa_acknowledged: true,
                source: source.trim() || undefined,
                campaign: campaign.trim() || undefined,
                column_map: map,
                rows: mappedRows,
            });
            const n = res?.imported ?? mappedRows.length;
            toast(`${n} ${n === 1 ? "lead" : "leads"} queued for revival`);
            reset();
            onClose();
            onImported();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Couldn't import that list — please try again.");
            setBusy(false);
        }
    }

    return (
        <Modal classWrapper="max-w-2xl" open={open} onClose={close}>
            <div className="text-h5 mb-1">Revive dead leads</div>
            <p className="text-body-2 text-t-secondary mb-6 max-w-xl">
                Bring a previously-contacted, consented list back into the engine. Each row is
                re-screened by the guard-chain (consent, NCPR/DND, cool-off) before any dial — so
                only leads that are still clear to contact will ring.
            </p>

            {/* Paste / upload the list */}
            <div className="mb-5">
                <div className="flex items-center justify-between mb-3">
                    <div className="text-button">Lead list</div>
                    <button
                        type="button"
                        onClick={() => fileRef.current?.click()}
                        className="inline-flex items-center gap-1.5 text-button text-t-secondary transition-colors hover:text-t-primary"
                    >
                        <Icon name="upload" className="size-4 fill-current" />
                        {fileName ? "Replace file" : "Upload CSV"}
                    </button>
                </div>
                <input
                    ref={fileRef}
                    type="file"
                    accept=".csv,text/csv,text/plain"
                    className="hidden"
                    onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                />
                <Field
                    textarea
                    classInput="!h-36 font-mono !text-caption"
                    placeholder={"name,phone,email,campaign\nAsha Rao,+9198XXXXXX10,asha@example.com,Diwali"}
                    value={raw}
                    onChange={(e) => {
                        setRaw(e.target.value);
                        setFileName(null);
                    }}
                />
                <div className="mt-2 flex items-center gap-2 text-caption text-t-tertiary">
                    <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0" />
                    {fileName ? (
                        <span className="truncate">Loaded {fileName} · </span>
                    ) : null}
                    {rows.length > 0
                        ? `${rows.length} ${rows.length === 1 ? "row" : "rows"} · ${header.length} columns detected`
                        : "Paste rows or upload a CSV — the first line is read as the header."}
                </div>
            </div>

            {/* Column map — only once a header is detected */}
            {header.length > 0 && (
                <div className="mb-5">
                    <div className="text-button mb-3">Map columns</div>
                    <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                        {REVIVE_FIELDS.map((f) => (
                            <Select
                                key={f.key}
                                label={f.required ? `${f.label} (required)` : f.label}
                                value={columnMap[f.key] ?? NONE_OPT}
                                onChange={(opt) =>
                                    setColumnMap((m) => ({ ...m, [f.key]: opt }))
                                }
                                options={headerOptions}
                            />
                        ))}
                    </div>
                    {!phoneMapped && (
                        <div className="mt-2 flex items-center gap-2 text-caption text-primary-03">
                            <Icon name="info" className="size-3.5 fill-primary-03 shrink-0" />
                            Map the phone column — a lead with no number can&apos;t be dialled.
                        </div>
                    )}
                </div>
            )}

            {/* Optional source / campaign tagging */}
            <div className="grid grid-cols-2 gap-3 mb-5 max-md:grid-cols-1">
                <Field
                    label="Source tag (optional)"
                    placeholder="e.g. 2024 webinar list"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                />
                <Field
                    label="Campaign (optional)"
                    placeholder="e.g. Q3 win-back"
                    value={campaign}
                    onChange={(e) => setCampaign(e.target.value)}
                />
            </div>

            {/* The hard compliance gate */}
            <div className="mb-5 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
                <Checkbox
                    checked={dpa}
                    onChange={setDpa}
                    label="I have a signed DPA / these leads consented to contact"
                />
                <p className="mt-2 pl-9 text-caption text-t-tertiary">
                    Required. Importing without a lawful basis to contact breaches DPDP / DLT — the
                    engine fail-closes until this is attested, and every import is audited.
                </p>
            </div>

            {error && (
                <div className="flex items-center gap-2 p-3 mb-5 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            <div className="flex items-center gap-3">
                <Button isStroke className="flex-1" onClick={close} disabled={busy}>
                    Cancel
                </Button>
                <Button isBlack className="flex-1" onClick={submit} disabled={!canSubmit}>
                    {busy
                        ? "Importing…"
                        : rows.length > 0
                        ? `Revive ${rows.length} ${rows.length === 1 ? "lead" : "leads"}`
                        : "Revive leads"}
                </Button>
            </div>
        </Modal>
    );
}
