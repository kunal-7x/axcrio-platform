"use client";

import { useEffect, useState, useRef, useMemo, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import Tabs from "@/components/Tabs";
import FieldFiles from "@/components/FieldFiles";
import Field from "@/components/Field";
import Range from "@/components/Range";
import Search from "@/components/Search";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Badge from "@/components/Badge";
import { StatusBadge, LeadBadge } from "@/lib/badges";
import {
    getCampaigns,
    getLeads,
    getLeadBatches,
    addLeads,
    run,
    getStatus,
    getCalledLeadKeys,
    RunError,
    type Campaign,
    type Lead,
    type UploadBatch,
    type StatusLead,
    type RunResult,
} from "@/lib/api";
import {
    planFromTier,
    suggestPacing,
    pacingLabel,
    pacingReason,
    type Pacing,
} from "./_pacing-defaults";
import { useMe, canWrite } from "@/lib/auth";
import { type SelectOption } from "@/types/select";
import { type TabsOption } from "@/types/tabs";
import HandoffTeam from "@/app/ai-manager/_handoff";
import VoiceProviders from "./_voice-providers";
import Stepper, { type Step } from "./_stepper";
import { SOURCE_TABS, SOURCE_ID, TEMP_DEFS, type Temp } from "./_lib/types";
import {
    type AudienceFilter,
    applyTempFilter,
    applyQuery,
    resolveAudience,
    breakdownOf,
    dedupeById,
} from "./_lib/audience";

function fmtDate(d?: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
}

function initials(name?: string): string {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// Manual-pick sort options. Client-side over the already-loaded picker rows,
// mirroring the Leads page sort so the manual list can be ordered the same way.
const PICK_SORTS: (SelectOption & { sort: string })[] = [
    { id: 1, name: "Newest first", sort: "recent" },
    { id: 2, name: "Oldest first", sort: "oldest" },
    { id: 3, name: "Name (A–Z)", sort: "name" },
    { id: 4, name: "Status", sort: "status" },
    { id: 5, name: "Score (high→low)", sort: "score" },
];

function sortLeads(rows: Lead[], key: string): Lead[] {
    const out = [...rows];
    switch (key) {
        case "oldest":
            return out.sort((a, b) => (a.added_at || "").localeCompare(b.added_at || ""));
        case "name":
            return out.sort((a, b) =>
                (a.name || "").toLowerCase().localeCompare((b.name || "").toLowerCase())
            );
        case "status":
            return out.sort(
                (a, b) =>
                    (a.status || "").toLowerCase().localeCompare((b.status || "").toLowerCase()) ||
                    (b.added_at || "").localeCompare(a.added_at || "")
            );
        case "score":
            return out.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
        default: // "recent" / newest-first
            return out.sort((a, b) => (b.added_at || "").localeCompare(a.added_at || ""));
    }
}

// The four steps of the Run flow. Pure labels — the stepper is presentational.
const STEPS: Step[] = [
    { label: "Campaign & Audience", hint: "Who gets called" },
    { label: "Voice & Providers", hint: "Quality & cost" },
    { label: "Pacing & Handoff", hint: "Speed & escalation" },
    { label: "Review & Launch", hint: "Confirm & dial" },
];

export default function RunPage() {
    // ── Campaign ──
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [campaign, setCampaign] = useState<SelectOption | null>(null);

    // ── Source mode (composable layers — see _lib/audience.ts) ──
    const [sourceTab, setSourceTab] = useState<TabsOption>(SOURCE_TABS[0]);

    // ── Stored + batch pools ──
    const [storedLeads, setStoredLeads] = useState<Lead[]>([]);
    const [loadingLeads, setLoadingLeads] = useState(true);
    const [batches, setBatches] = useState<UploadBatch[]>([]);
    const [selectedBatchIds, setSelectedBatchIds] = useState<Set<string>>(new Set());
    const [batchLeads, setBatchLeads] = useState<Record<string, Lead[]>>({});

    // ── Filters ──
    const [temps, setTemps] = useState<Set<Temp>>(new Set());
    const [useBand, setUseBand] = useState(false);
    const [band, setBand] = useState<[number, number]>([0, 100]);
    const [query, setQuery] = useState("");

    // ── Manual override (empty ⇒ all-filtered) ──
    const [manualSelected, setManualSelected] = useState<Set<string>>(new Set());
    // ── Manual-pick sort (client-side over the loaded picker rows) ──
    const [pickSort, setPickSort] = useState<SelectOption>(PICK_SORTS[0]);

    // ── WAVE C: exclude leads already called in THIS campaign ──
    const [excludeCalled, setExcludeCalled] = useState(false);
    const [calledKeys, setCalledKeys] = useState<Set<string>>(new Set());

    // ── Upload ──
    const [uploadFile, setUploadFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);

    // ── Pacing & caps ──
    const [concurrency, setConcurrency] = useState(1);
    const [hourlyCap, setHourlyCap] = useState(0);
    const [dailyCap, setDailyCap] = useState(0);

    // ── Run / live status ──
    const [starting, setStarting] = useState(false);
    const [jobId, setJobId] = useState<string | null>(null);
    const [liveLeads, setLiveLeads] = useState<StatusLead[]>([]);
    const [jobState, setJobState] = useState("");
    const [toast, setToast] = useState("");
    const [toastType, setToastType] = useState<"success" | "warning" | "error">("success");
    const [queuedResult, setQueuedResult] = useState<RunResult | null>(null);
    const [insufficient, setInsufficient] = useState(false);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // ── Stepper position (pure layout state — single source of truth stays this component) ──
    const [step, setStep] = useState(0);

    const { me } = useMe();
    const writable = canWrite(me);

    // ── Initial loads ──
    useEffect(() => {
        getCampaigns()
            .then((r) => {
                setCampaigns(r.campaigns);
                if (r.campaigns.length > 0)
                    setCampaign({ id: 0, name: r.campaigns[0].name });
            })
            .catch(() => {});
    }, []);

    const loadLeads = useCallback(() => {
        setLoadingLeads(true);
        getLeads()
            .then((r) => setStoredLeads(r.leads))
            .catch(() => {})
            .finally(() => setLoadingLeads(false));
    }, []);

    const loadBatches = useCallback(() => {
        getLeadBatches()
            .then((r) => setBatches(r.batches))
            .catch(() => setBatches([]));
    }, []);

    useEffect(() => {
        loadLeads();
        loadBatches();
    }, [loadLeads, loadBatches]);

    // Lazy-load leads for a selected batch (graceful: if the backend lacks the
    // batch filter, no rows come back and the batch simply contributes nothing).
    const ensureBatchLeads = useCallback(
        (batchId: string) => {
            if (batchLeads[batchId]) return;
            getLeads({ batch: batchId })
                .then((r) =>
                    setBatchLeads((prev) => ({ ...prev, [batchId]: r.leads }))
                )
                .catch(() =>
                    setBatchLeads((prev) => ({ ...prev, [batchId]: [] }))
                );
        },
        [batchLeads]
    );

    // ── Poll job status ──
    useEffect(() => {
        if (!jobId) return;
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(async () => {
            try {
                const s = await getStatus(jobId);
                setLiveLeads(s.leads);
                setJobState(s.state);
                if (s.state === "done" || s.state === "failed") {
                    if (pollRef.current) clearInterval(pollRef.current);
                }
            } catch {
                /* silently retry */
            }
        }, 3000);
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [jobId]);

    // ── Resolve the audience (client-side, truthful preview) ──
    const campaignId = useMemo(() => {
        if (!campaign) return "";
        const c = campaigns.find((c) => c.name === campaign.name);
        return c?.id ?? "";
    }, [campaign, campaigns]);

    // ── WAVE C: load the set of lead keys already called in this campaign ──
    // (dormant-safe: 404/empty → exclude nothing; the toggle simply does nothing).
    useEffect(() => {
        if (!campaignId) {
            setCalledKeys(new Set());
            return;
        }
        let cancelled = false;
        getCalledLeadKeys(campaignId)
            .then((s) => !cancelled && setCalledKeys(s))
            .catch(() => !cancelled && setCalledKeys(new Set()));
        return () => {
            cancelled = true;
        };
    }, [campaignId]);

    // Base pool depends on the source tab. "All stored" / "By temperature" /
    // "Pick manually" all draw from stored leads; "By upload" merges in the
    // selected batches' leads (stored is still included so filters compose).
    const basePool = useMemo(() => {
        const pool: Lead[] = [...storedLeads];
        for (const id of selectedBatchIds) {
            const bl = batchLeads[id];
            if (bl) pool.push(...bl);
        }
        return dedupeById(pool);
    }, [storedLeads, selectedBatchIds, batchLeads]);

    const filter: AudienceFilter = useMemo(
        () => ({ temps, useBand, band, query }),
        [temps, useBand, band, query]
    );

    const filtered = useMemo(
        () => applyTempFilter(basePool, filter),
        [basePool, filter]
    );

    // Manual-picker view (filtered + search + sort) — rows the vendor hand-picks from.
    const pickSortKey = (PICK_SORTS.find((s) => s.id === pickSort.id) ?? PICK_SORTS[0]).sort;
    const pickerRows = useMemo(
        () => sortLeads(applyQuery(filtered, query), pickSortKey),
        [filtered, query, pickSortKey]
    );

    const audience = useMemo(() => {
        const resolved = resolveAudience(filtered, manualSelected);
        if (!excludeCalled || calledKeys.size === 0) return resolved;
        // Drop leads already dialed in this campaign (match on id OR phone).
        return resolved.filter(
            (l) => !calledKeys.has(l.id) && !(l.phone && calledKeys.has(l.phone))
        );
    }, [filtered, manualSelected, excludeCalled, calledKeys]);

    // How many of the current filtered pool would be removed by the toggle —
    // shown on the toggle so the founder sees its effect before flipping it.
    const alreadyCalledInPool = useMemo(() => {
        if (calledKeys.size === 0) return 0;
        const resolved = resolveAudience(filtered, manualSelected);
        return resolved.filter(
            (l) => calledKeys.has(l.id) || (l.phone && calledKeys.has(l.phone))
        ).length;
    }, [filtered, manualSelected, calledKeys]);

    const breakdown = useMemo(() => breakdownOf(audience), [audience]);

    // ── WAVE C: DID-protective pacing suggestion (audience-aware, override-able) ──
    // Plan is inferred conservatively (Starter floor) since this page has no hard
    // plan field; the Voice & Providers tier refines cost, not the DID-protective caps.
    const suggestedPacing: Pacing = useMemo(
        () => suggestPacing(planFromTier(), audience.length),
        [audience.length]
    );
    const pacingMatchesSuggestion =
        (concurrency || 1) === suggestedPacing.concurrency &&
        hourlyCap === suggestedPacing.hourlyCap &&
        dailyCap === suggestedPacing.dailyCap;
    const applySuggestedPacing = () => {
        setConcurrency(suggestedPacing.concurrency);
        setHourlyCap(suggestedPacing.hourlyCap);
        setDailyCap(suggestedPacing.dailyCap);
    };

    // Live temperature counts over the base pool (for the chip badges).
    const tempCounts = useMemo(() => {
        const c: Record<Temp, number> = { hot: 0, warm: 0, cold: 0 };
        for (const l of basePool) {
            const s = l.score ?? 0;
            if (s >= 70) c.hot++;
            else if (s >= 40) c.warm++;
            else c.cold++;
        }
        return c;
    }, [basePool]);

    // ── Handlers ──
    function toggleTemp(t: Temp) {
        setManualSelected(new Set()); // changing the pool clears manual picks
        setTemps((prev) => {
            const next = new Set(prev);
            if (next.has(t)) next.delete(t);
            else next.add(t);
            return next;
        });
    }

    function toggleBatch(batchId: string) {
        setManualSelected(new Set());
        setSelectedBatchIds((prev) => {
            const next = new Set(prev);
            if (next.has(batchId)) next.delete(batchId);
            else {
                next.add(batchId);
                ensureBatchLeads(batchId);
            }
            return next;
        });
    }

    const allPickerSelected =
        pickerRows.length > 0 &&
        pickerRows.every((l) => manualSelected.has(l.id));

    function toggleSelectAllPicker(on: boolean) {
        setManualSelected((prev) => {
            const next = new Set(prev);
            for (const l of pickerRows) {
                if (on) next.add(l.id);
                else next.delete(l.id);
            }
            return next;
        });
    }

    function toggleRow(id: string, on: boolean) {
        setManualSelected((prev) => {
            const next = new Set(prev);
            if (on) next.add(id);
            else next.delete(id);
            return next;
        });
    }

    async function handleUpload() {
        if (!uploadFile) return;
        setUploading(true);
        setToast("");
        try {
            const r = await addLeads("", uploadFile);
            setToastType("success");
            setToast(
                `Imported ${r.added} leads from ${
                    r.source_file || uploadFile.name
                }.`
            );
            setUploadFile(null);
            loadLeads();
            loadBatches();
            // If the new batch id came back, pre-select it for convenience.
            if (r.batch_id) {
                setSelectedBatchIds((prev) => new Set(prev).add(r.batch_id!));
                ensureBatchLeads(r.batch_id);
            }
        } catch (e: unknown) {
            setToastType("error");
            setToast(e instanceof Error ? e.message : "Failed to import file");
        } finally {
            setUploading(false);
        }
    }

    function buildRunPayload(force?: boolean) {
        const ids = audience.map((l) => l.id).filter(Boolean);
        return {
            campaign_id: campaignId,
            // Primary path: explicit resolved audience. Fallback: if no ids
            // resolved (e.g. backend has no leads yet) and the user picked
            // "All stored", let the server use stored leads.
            lead_ids: ids.length > 0 ? ids : undefined,
            use_stored:
                ids.length === 0 && sourceTab.id === SOURCE_ID.all
                    ? true
                    : false,
            leads: "",
            concurrency: concurrency || undefined,
            hourly_cap: hourlyCap || undefined,
            daily_cap: dailyCap || undefined,
            force,
        };
    }

    async function handleStart() {
        if (!campaignId) {
            setToastType("error");
            setToast("Please select a campaign");
            setStep(0);
            return;
        }
        if (audience.length === 0 && sourceTab.id !== SOURCE_ID.all) {
            setToastType("error");
            setToast("No leads match the current audience — adjust your filters.");
            setStep(0);
            return;
        }
        setStarting(true);
        setToast("");
        setQueuedResult(null);
        setInsufficient(false);
        // Launching always lands on Review & Launch so live status is in view.
        setStep(3);
        try {
            const result = await run(buildRunPayload());
            setJobId(result.job_id);
            setLiveLeads([]);
            if (result.queued_out_of_window) {
                setQueuedResult(result);
                setToastType("warning");
                const suppNote = result.suppressed_count
                    ? ` (${result.suppressed_count} excluded — DND)`
                    : "";
                setToast(
                    `Outside calling window (${result.window}) — ${result.count} leads queued${suppNote}, dialing will start automatically.`
                );
                setJobState("queued");
            } else {
                setJobState("running");
                const suppNote = result.suppressed_count
                    ? ` — ${result.suppressed_count} excluded (DND)`
                    : "";
                setToastType("success");
                setToast(
                    `Started! Job ${result.job_id} — ${result.count} leads${suppNote}`
                );
            }
        } catch (e: unknown) {
            setToastType("error");
            if (e instanceof RunError && e.code === "insufficient_balance") {
                setInsufficient(true);
                setToast(
                    "Insufficient balance — top up to continue. Visit Billing to add funds."
                );
            } else {
                setToast(e instanceof Error ? e.message : "Failed to start");
            }
        } finally {
            setStarting(false);
        }
    }

    const campaignOptions: SelectOption[] = useMemo(
        () => campaigns.map((c, i) => ({ id: i, name: c.name })),
        [campaigns]
    );

    const showUpload = sourceTab.id === SOURCE_ID.upload;
    const showTemperature = sourceTab.id === SOURCE_ID.temperature;
    const showManual = sourceTab.id === SOURCE_ID.manual;

    // The single truth for the headline audience count, shared by the summary
    // rail, the cost meter and the run payload (so the estimate matches dialed).
    const audienceCount =
        sourceTab.id === SOURCE_ID.all && audience.length === 0
            ? storedLeads.length
            : breakdown.total;

    // ── Stepper gating ──
    // Step 0 is valid once a campaign is chosen (and, for non-"all" modes, the
    // audience is non-empty). Steps 1–2 are always passable. Step 3 is launch.
    const step0Valid =
        !!campaignId &&
        (sourceTab.id === SOURCE_ID.all || audienceCount > 0);
    // Furthest step the user may jump forward to. Lock step ≥1 until step 0 is
    // valid; otherwise every step is reachable.
    const maxReachable = step0Valid ? STEPS.length - 1 : 0;

    const goNext = () => setStep((s) => Math.min(STEPS.length - 1, s + 1));
    const goBack = () => setStep((s) => Math.max(0, s - 1));
    const onStep = (i: number) => {
        if (i <= maxReachable) setStep(i);
    };

    // Audience-count chip shown in the step-1 header.
    const audienceChip = (
        <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-b-surface1 border border-s-subtle text-caption text-t-secondary dark:bg-shade-04/40">
            <span className="size-1.5 rounded-full bg-primary-02" />
            <span className="tabular-nums text-t-primary font-medium">
                {loadingLeads &&
                sourceTab.id === SOURCE_ID.all &&
                audience.length === 0
                    ? "…"
                    : audienceCount}
            </span>
            in audience
        </span>
    );

    return (
        <Layout title="Run">
            {/* ── Banners (verbatim behaviour) ── */}
            {toast && (
                <div
                    className={`mb-3 flex items-start justify-between gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toastType === "success"
                            ? "bg-primary-02/8 text-primary-02"
                            : toastType === "warning"
                            ? "bg-primary-05/10 text-primary-05"
                            : "bg-primary-03/8 text-primary-03"
                    }`}
                >
                    <span className="flex items-start gap-2">
                        <span className="size-1.5 rounded-full bg-current mt-1.5 shrink-0" />
                        {toast}
                    </span>
                    {queuedResult && (
                        <button
                            className="shrink-0 px-3 h-7 inline-flex items-center border border-current/30 rounded-full text-caption font-medium transition-colors hover:bg-current/10"
                            onClick={async () => {
                                setStarting(true);
                                try {
                                    const r = await run(buildRunPayload(true));
                                    setJobId(r.job_id);
                                    setJobState("running");
                                    setToastType("success");
                                    setToast(
                                        `Started anyway! Job ${r.job_id} — ${r.count} leads`
                                    );
                                    setQueuedResult(null);
                                } catch {
                                    /* ignore */
                                } finally {
                                    setStarting(false);
                                }
                            }}
                        >
                            Start anyway
                        </button>
                    )}
                </div>
            )}

            {insufficient && (
                <div className="mb-3 flex items-center justify-between gap-2 p-3.5 rounded-3xl bg-primary-03/8 text-primary-03 text-body-2">
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        Insufficient balance — top up to continue placing calls.
                    </span>
                    <a
                        href="/billing"
                        className="shrink-0 px-3 h-7 inline-flex items-center border border-current/30 rounded-full text-caption font-medium transition-colors hover:bg-current/10"
                    >
                        Go to Billing
                    </a>
                </div>
            )}

            {!writable && me && (
                <div className="mb-3 p-3.5 rounded-3xl surface text-t-secondary text-body-2">
                    Your role is read-only — you can view campaigns and live
                    status, but cannot start call runs.
                </div>
            )}

            {/* ── Sticky stepper spine ── */}
            <div className="sticky top-2 z-20 mb-4">
                <Stepper
                    steps={STEPS}
                    step={step}
                    maxReachable={maxReachable}
                    onStep={onStep}
                />
            </div>

            <div className="flex gap-6 max-lg:flex-col">
                {/* ── LEFT: ONE focused step panel at a time ── */}
                <div className="flex-1 min-w-0">
                    {/* ① Campaign & Audience ─────────────────────────────── */}
                    {step === 0 && (
                        <div key="step-0" className="step-reveal flex flex-col gap-4">
                            <Card title="Campaign">
                                <div className="px-5 pb-5 max-lg:px-3">
                                    <Select
                                        label="Choose campaign"
                                        value={campaign}
                                        onChange={setCampaign}
                                        options={campaignOptions}
                                        placeholder={
                                            campaigns.length === 0
                                                ? "No campaigns available"
                                                : "Select a campaign"
                                        }
                                    />
                                    <div className="mt-3 flex items-center gap-2 text-body-2 text-t-secondary">
                                        <Icon
                                            name="clock"
                                            className="size-4 fill-t-tertiary shrink-0"
                                        />
                                        Calls outside the calling window are
                                        queued and dialed automatically.
                                    </div>
                                </div>
                            </Card>

                            <Card
                                title="Audience"
                                headContent={
                                    <div className="mr-1">{audienceChip}</div>
                                }
                            >
                                <div className="px-5 pb-5 max-lg:px-3">
                                    <Tabs
                                        items={SOURCE_TABS}
                                        value={sourceTab}
                                        setValue={setSourceTab}
                                        className="flex-wrap"
                                        classButton="!h-10 !px-4 text-button"
                                    />
                                    <p className="mt-3 text-body-2 text-t-secondary">
                                        Filters compose — pick a temperature
                                        and/or a file, then hand-pick if you
                                        want. The preview always reflects exactly
                                        who will be dialed.
                                    </p>

                                    {/* WAVE C: exclude leads already called in this campaign */}
                                    {campaignId && calledKeys.size > 0 && (
                                        <button
                                            type="button"
                                            onClick={() =>
                                                setExcludeCalled((v) => !v)
                                            }
                                            className={`mt-3 flex items-center gap-3 w-full p-3 rounded-2xl border text-left transition-colors ${
                                                excludeCalled
                                                    ? "border-primary-01/40 bg-primary-01/8"
                                                    : "border-s-subtle bg-b-surface1 hover:border-s-stroke2 dark:bg-shade-04/30"
                                            }`}
                                        >
                                            <span
                                                className={`relative shrink-0 w-9 h-5 rounded-full transition-colors ${
                                                    excludeCalled
                                                        ? "bg-primary-01"
                                                        : "bg-s-stroke2"
                                                }`}
                                            >
                                                <span
                                                    className={`absolute top-0.5 size-4 rounded-full bg-b-surface2 transition-transform ${
                                                        excludeCalled
                                                            ? "translate-x-4"
                                                            : "translate-x-0.5"
                                                    }`}
                                                />
                                            </span>
                                            <span className="min-w-0">
                                                <span className="block text-button text-t-primary">
                                                    Skip already-called leads
                                                </span>
                                                <span className="block text-caption text-t-tertiary">
                                                    {alreadyCalledInPool > 0
                                                        ? `${alreadyCalledInPool} in this audience were already dialed in this campaign`
                                                        : "No overlap with previously dialed leads"}
                                                </span>
                                            </span>
                                        </button>
                                    )}

                                    {/* Progressive disclosure: only the active
                                        source mode's controls render. */}
                                    {showUpload && (
                                        <div className="mt-5 space-y-4">
                                            <FieldFiles
                                                onChange={(f) =>
                                                    setUploadFile(f)
                                                }
                                            />
                                            {uploadFile && writable && (
                                                <Button
                                                    isBlack
                                                    className="w-full justify-center"
                                                    onClick={handleUpload}
                                                    disabled={uploading}
                                                >
                                                    {uploading
                                                        ? "Importing…"
                                                        : `Import ${uploadFile.name}`}
                                                </Button>
                                            )}

                                            <div className="pt-1">
                                                <div className="text-button mb-2.5">
                                                    Uploaded batches
                                                </div>
                                                {batches.length === 0 ? (
                                                    <div className="p-4 rounded-2xl bg-b-surface1 border border-s-subtle text-caption text-t-tertiary dark:bg-shade-04/30">
                                                        No uploaded files yet.
                                                        Drop a CSV or Excel file
                                                        above — each import
                                                        becomes a selectable
                                                        batch.
                                                    </div>
                                                ) : (
                                                    <div className="overflow-hidden rounded-2xl border border-s-subtle">
                                                        <Table
                                                            cellsThead={
                                                                <>
                                                                    <th>File</th>
                                                                    <th className="text-right">
                                                                        Leads
                                                                    </th>
                                                                </>
                                                            }
                                                        >
                                                            {batches.map((b) => {
                                                                const on =
                                                                    selectedBatchIds.has(
                                                                        b.batch_id
                                                                    );
                                                                return (
                                                                    <TableRow
                                                                        key={
                                                                            b.batch_id
                                                                        }
                                                                        selectedRows={
                                                                            on
                                                                        }
                                                                        onRowSelect={() =>
                                                                            toggleBatch(
                                                                                b.batch_id
                                                                            )
                                                                        }
                                                                    >
                                                                        <td>
                                                                            <div className="font-medium text-t-primary truncate max-w-40">
                                                                                {
                                                                                    b.source_file
                                                                                }
                                                                            </div>
                                                                            <div className="text-caption text-t-tertiary">
                                                                                {fmtDate(
                                                                                    b.added_at
                                                                                )}
                                                                            </div>
                                                                        </td>
                                                                        <td className="text-right td-num text-t-secondary">
                                                                            {
                                                                                b.count
                                                                            }
                                                                        </td>
                                                                    </TableRow>
                                                                );
                                                            })}
                                                        </Table>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {showTemperature && (
                                        <div className="mt-5 space-y-4">
                                            <div className="flex flex-wrap gap-2">
                                                {TEMP_DEFS.map((t) => {
                                                    const on = temps.has(t.key);
                                                    return (
                                                        <button
                                                            key={t.key}
                                                            onClick={() =>
                                                                toggleTemp(
                                                                    t.key
                                                                )
                                                            }
                                                            className={`group flex items-center gap-2 h-10 px-4 rounded-full border text-button transition-colors ${
                                                                on
                                                                    ? "border-s-stroke2 text-t-primary bg-b-surface1 dark:bg-shade-04/50"
                                                                    : "border-transparent text-t-secondary hover:text-t-primary bg-b-surface1/60 dark:bg-shade-04/30"
                                                            }`}
                                                        >
                                                            <span
                                                                className={`size-2 rounded-full ${
                                                                    t.key ===
                                                                    "hot"
                                                                        ? "bg-primary-02"
                                                                        : t.key ===
                                                                          "warm"
                                                                        ? "bg-primary-05"
                                                                        : "bg-t-tertiary"
                                                                }`}
                                                            />
                                                            {t.label}
                                                            <Badge
                                                                variant={
                                                                    on
                                                                        ? "info"
                                                                        : "neutral"
                                                                }
                                                            >
                                                                {
                                                                    tempCounts[
                                                                        t.key
                                                                    ]
                                                                }
                                                            </Badge>
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                            <p className="text-body-2 text-t-secondary">
                                                Hot 70+ · Warm 40–69 · Cold under
                                                40 / unscored. Pick one or more.
                                            </p>

                                            <div className="pt-2 border-t border-s-subtle">
                                                <label className="flex items-center justify-between cursor-pointer mb-3">
                                                    <span className="text-button">
                                                        Custom score band
                                                    </span>
                                                    <input
                                                        type="checkbox"
                                                        className="size-4 rounded"
                                                        checked={useBand}
                                                        onChange={(e) => {
                                                            setManualSelected(
                                                                new Set()
                                                            );
                                                            setUseBand(
                                                                e.target.checked
                                                            );
                                                        }}
                                                    />
                                                </label>
                                                {useBand && (
                                                    <Range
                                                        values={band}
                                                        setValues={(v) => {
                                                            setManualSelected(
                                                                new Set()
                                                            );
                                                            setBand([
                                                                v[0],
                                                                v[1],
                                                            ]);
                                                        }}
                                                        min={0}
                                                        max={100}
                                                        step={1}
                                                    />
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {showManual && (
                                        <div className="mt-5">
                                            <div className="flex items-center justify-between gap-2 mb-3 max-md:flex-wrap">
                                                <span className="text-button shrink-0">
                                                    Pick leads
                                                </span>
                                                <div className="flex items-center gap-2 max-md:w-full">
                                                    <Select
                                                        className="w-40 max-md:flex-1"
                                                        classButton="!h-9"
                                                        value={pickSort}
                                                        onChange={setPickSort}
                                                        options={PICK_SORTS}
                                                    />
                                                    <Search
                                                        className="w-36 max-md:flex-1"
                                                        classInput="!h-9"
                                                        isGray
                                                        value={query}
                                                        onChange={(e) =>
                                                            setQuery(e.target.value)
                                                        }
                                                        placeholder="Search"
                                                    />
                                                </div>
                                            </div>
                                            {loadingLeads ? (
                                                <div className="px-3 py-8 text-center text-caption text-t-tertiary">
                                                    Loading leads…
                                                </div>
                                            ) : pickerRows.length === 0 ? (
                                                <div className="px-3 py-8 text-center text-caption text-t-tertiary">
                                                    {query
                                                        ? `Nothing matches “${query}”.`
                                                        : "No leads in the current pool."}
                                                </div>
                                            ) : (
                                                <div className="max-h-80 overflow-y-auto scrollbar scrollbar-thumb-t-tertiary/40 scrollbar-track-transparent">
                                                    <Table
                                                        selectAll={
                                                            allPickerSelected
                                                        }
                                                        onSelectAll={
                                                            toggleSelectAllPicker
                                                        }
                                                        cellsThead={
                                                            <>
                                                                <th>Lead</th>
                                                                <th className="text-right">
                                                                    Status
                                                                </th>
                                                            </>
                                                        }
                                                    >
                                                        {pickerRows.map((l) => (
                                                            <TableRow
                                                                key={l.id}
                                                                selectedRows={manualSelected.has(
                                                                    l.id
                                                                )}
                                                                onRowSelect={(
                                                                    on
                                                                ) =>
                                                                    toggleRow(
                                                                        l.id,
                                                                        on
                                                                    )
                                                                }
                                                            >
                                                                <td>
                                                                    <div className="flex items-center gap-2.5">
                                                                        <span
                                                                            className={`grid place-items-center size-8 shrink-0 rounded-full text-caption font-semibold ${
                                                                                (l.score ??
                                                                                    0) >=
                                                                                70
                                                                                    ? "bg-primary-02/12 text-primary-02"
                                                                                    : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                                            }`}
                                                                        >
                                                                            {initials(
                                                                                l.name
                                                                            )}
                                                                        </span>
                                                                        <div className="min-w-0">
                                                                            <div className="font-medium text-t-primary truncate max-w-36">
                                                                                {
                                                                                    l.name
                                                                                }
                                                                            </div>
                                                                            <div className="text-caption text-t-tertiary td-num truncate max-w-36">
                                                                                {
                                                                                    l.phone
                                                                                }
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </td>
                                                                <td className="text-right">
                                                                    <LeadBadge
                                                                        lead={l}
                                                                    />
                                                                </td>
                                                            </TableRow>
                                                        ))}
                                                    </Table>
                                                </div>
                                            )}
                                            <p className="pt-3 text-body-2 text-t-secondary">
                                                {manualSelected.size > 0
                                                    ? `${manualSelected.size} hand-picked — these exact leads will be dialed.`
                                                    : "Tick rows to dial an exact subset, or leave empty to call everything that passed the filters."}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </Card>
                        </div>
                    )}

                    {/* ② Voice & Providers ───────────────────────────────── */}
                    {step === 1 && (
                        <div key="step-1" className="step-reveal">
                            <VoiceProviders
                                campaignId={campaignId}
                                audienceCount={audienceCount}
                                writable={writable}
                            />
                        </div>
                    )}

                    {/* ③ Pacing & Handoff ────────────────────────────────── */}
                    {step === 2 && (
                        <div key="step-2" className="step-reveal flex flex-col gap-4">
                            <Card title="Pacing & caps">
                                <div className="px-5 pb-5 max-lg:px-3">
                                    {/* WAVE C: smart pacing-defaults chip (one-click, DID-protective, override-able) */}
                                    <div
                                        className={`mb-4 flex items-center gap-3 p-3 rounded-2xl border ${
                                            pacingMatchesSuggestion
                                                ? "border-primary-02/30 bg-primary-02/8"
                                                : "border-s-subtle bg-b-surface1 dark:bg-shade-04/30"
                                        }`}
                                    >
                                        <span className="grid place-items-center size-8 shrink-0 rounded-full bg-b-surface2 text-t-secondary">
                                            <Icon
                                                name={
                                                    pacingMatchesSuggestion
                                                        ? "check-circle-fill"
                                                        : "clock"
                                                }
                                                className={`size-4 ${
                                                    pacingMatchesSuggestion
                                                        ? "fill-primary-02"
                                                        : "fill-t-secondary"
                                                }`}
                                            />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <div className="text-button text-t-primary">
                                                Smart pacing ·{" "}
                                                {pacingLabel(suggestedPacing)}
                                            </div>
                                            <div className="text-caption text-t-tertiary truncate">
                                                {pacingReason(audience.length)}
                                            </div>
                                        </div>
                                        {pacingMatchesSuggestion ? (
                                            <span className="shrink-0 text-caption text-primary-02 font-medium">
                                                Applied
                                            </span>
                                        ) : (
                                            <button
                                                type="button"
                                                onClick={applySuggestedPacing}
                                                disabled={!writable}
                                                className="shrink-0 px-3 h-8 inline-flex items-center rounded-full bg-b-surface2 border border-s-stroke2 text-caption font-medium text-t-primary transition-colors hover:border-s-highlight disabled:opacity-40 disabled:pointer-events-none"
                                            >
                                                Apply
                                            </button>
                                        )}
                                    </div>
                                    <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
                                        <Field
                                            label="Concurrency"
                                            type="number"
                                            min={1}
                                            value={concurrency || ""}
                                            onChange={(e) =>
                                                setConcurrency(
                                                    parseInt(e.target.value) || 0
                                                )
                                            }
                                        />
                                        <Field
                                            label="Hourly cap"
                                            type="number"
                                            min={0}
                                            value={hourlyCap || ""}
                                            onChange={(e) =>
                                                setHourlyCap(
                                                    parseInt(e.target.value) || 0
                                                )
                                            }
                                        />
                                        <Field
                                            label="Daily cap"
                                            type="number"
                                            min={0}
                                            value={dailyCap || ""}
                                            onChange={(e) =>
                                                setDailyCap(
                                                    parseInt(e.target.value) || 0
                                                )
                                            }
                                        />
                                    </div>
                                    <p className="mt-3 text-body-2 text-t-secondary">
                                        Concurrency caps simultaneous calls;
                                        hourly / daily caps throttle volume. Leave
                                        a cap at 0 for no limit.
                                    </p>
                                </div>
                            </Card>

                            {/* Reuses the SAME manager + /brain/handoff* calls as
                                the dedicated Handoff Team view, so what's set here
                                is what the AI dials when a caller asks for a human
                                or a lead goes hot during this run. */}
                            <HandoffTeam compact />
                        </div>
                    )}

                    {/* ④ Review & Launch ─────────────────────────────────── */}
                    {step === 3 && (
                        <div key="step-3" className="step-reveal flex flex-col gap-4">
                            <Card title="Review">
                                <div className="px-5 pb-5 max-lg:px-3">
                                    <div className="grid grid-cols-2 gap-px rounded-2xl overflow-hidden border border-s-subtle bg-s-subtle max-md:grid-cols-1">
                                        <ReviewCell
                                            label="Campaign"
                                            value={
                                                campaign?.name ||
                                                "No campaign selected"
                                            }
                                        />
                                        <ReviewCell
                                            label="Audience"
                                            value={`${audienceCount} leads`}
                                            sub={[
                                                breakdown.hot > 0
                                                    ? `${breakdown.hot} hot`
                                                    : "",
                                                breakdown.warm > 0
                                                    ? `${breakdown.warm} warm`
                                                    : "",
                                                breakdown.cold > 0
                                                    ? `${breakdown.cold} cold`
                                                    : "",
                                            ]
                                                .filter(Boolean)
                                                .join(" · ")}
                                        />
                                        <ReviewCell
                                            label="Source"
                                            value={sourceTab.name}
                                            sub={
                                                manualSelected.size > 0
                                                    ? `${manualSelected.size} hand-picked`
                                                    : undefined
                                            }
                                        />
                                        <ReviewCell
                                            label="Pacing"
                                            value={`${
                                                concurrency || 1
                                            } concurrent`}
                                            sub={[
                                                hourlyCap
                                                    ? `${hourlyCap}/hr`
                                                    : "",
                                                dailyCap
                                                    ? `${dailyCap}/day`
                                                    : "",
                                            ]
                                                .filter(Boolean)
                                                .join(" · ") || "no caps"}
                                        />
                                    </div>

                                    {queuedResult && (
                                        <div className="mt-4 flex items-start gap-2 p-3 rounded-2xl bg-primary-05/8 text-body-2">
                                            <Icon
                                                name="clock"
                                                className="size-4 fill-primary-05 shrink-0 mt-0.5"
                                            />
                                            <span className="text-caption text-t-secondary">
                                                Outside the calling window — leads
                                                are queued and will dial
                                                automatically when the window
                                                opens. Use{" "}
                                                <span className="text-t-primary">
                                                    Start anyway
                                                </span>{" "}
                                                in the banner to override.
                                            </span>
                                        </div>
                                    )}

                                    <div className="mt-5 flex items-center gap-3 max-md:flex-col max-md:items-stretch">
                                        <Button
                                            isBlack
                                            className="max-md:w-full max-md:justify-center"
                                            icon="send"
                                            onClick={handleStart}
                                            disabled={
                                                starting ||
                                                !writable ||
                                                !campaignId
                                            }
                                        >
                                            {starting
                                                ? "Starting…"
                                                : !writable
                                                ? "Read-only"
                                                : "Launch — call now"}
                                        </Button>
                                        {queuedResult && (
                                            <button
                                                className="inline-flex items-center justify-center h-12 px-5 rounded-3xl border border-s-stroke2 text-button text-t-secondary transition-colors hover:text-t-primary hover:border-s-highlight max-md:w-full"
                                                onClick={async () => {
                                                    setStarting(true);
                                                    try {
                                                        const r = await run(
                                                            buildRunPayload(true)
                                                        );
                                                        setJobId(r.job_id);
                                                        setJobState("running");
                                                        setToastType("success");
                                                        setToast(
                                                            `Started anyway! Job ${r.job_id} — ${r.count} leads`
                                                        );
                                                        setQueuedResult(null);
                                                    } catch {
                                                        /* ignore */
                                                    } finally {
                                                        setStarting(false);
                                                    }
                                                }}
                                            >
                                                Start anyway
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </Card>

                            {/* Live status (renders once a run has been launched) */}
                            <Card
                                title={
                                    jobId
                                        ? `Live Status — Job ${jobId} (${jobState})`
                                        : "Live Status"
                                }
                            >
                                <div className="px-2 max-lg:px-1">
                                    {!jobId ? (
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon
                                                    name="send"
                                                    className="fill-inherit"
                                                />
                                            </span>
                                            <div className="state-title">
                                                No active run
                                            </div>
                                            <div className="state-sub">
                                                Press Launch above and each
                                                lead&apos;s live status appears
                                                here.
                                            </div>
                                        </div>
                                    ) : liveLeads.length === 0 ? (
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon
                                                    name="clock"
                                                    className="fill-inherit"
                                                />
                                            </span>
                                            <div className="state-title">
                                                Waiting for updates…
                                            </div>
                                            <div className="state-sub">
                                                The dialer is spinning up —
                                                statuses refresh every few
                                                seconds.
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <Table
                                                cellsThead={
                                                    <>
                                                        <th>Name</th>
                                                        <th>Number</th>
                                                        <th className="text-right">
                                                            Status
                                                        </th>
                                                    </>
                                                }
                                            >
                                                {liveLeads.map((l, i) => (
                                                    <TableRow key={i}>
                                                        <td className="font-medium text-t-primary">
                                                            {l.name}
                                                        </td>
                                                        <td className="text-t-secondary td-num">
                                                            {l.num}
                                                        </td>
                                                        <td className="text-right">
                                                            <StatusBadge
                                                                status={l.status}
                                                            />
                                                        </td>
                                                    </TableRow>
                                                ))}
                                            </Table>
                                        </div>
                                    )}
                                </div>
                            </Card>
                        </div>
                    )}

                    {/* ── Step nav (Back / Next) — hidden on the launch step ── */}
                    {step < 3 && (
                        <div className="mt-4 flex items-center justify-between gap-3 max-lg:hidden">
                            <button
                                type="button"
                                onClick={goBack}
                                disabled={step === 0}
                                className="inline-flex items-center gap-1.5 h-11 px-5 rounded-3xl border border-s-stroke2 text-button text-t-secondary transition-colors hover:text-t-primary hover:border-s-highlight disabled:opacity-40 disabled:pointer-events-none"
                            >
                                <Icon
                                    name="arrow"
                                    className="size-4 fill-inherit rotate-180"
                                />
                                Back
                            </button>
                            <Button
                                isBlack
                                icon="arrow"
                                onClick={goNext}
                                disabled={step === 0 && !step0Valid}
                            >
                                {step === 2 ? "Review" : "Continue"}
                            </Button>
                        </div>
                    )}
                </div>

                {/* ── RIGHT: sticky Launch-summary rail (always visible) ── */}
                <aside className="w-[20rem] max-lg:w-full shrink-0">
                    <div className="sticky top-24 max-lg:static flex flex-col gap-4">
                        <div className="surface p-5 max-lg:p-4">
                            <div className="eyebrow mb-1">Launch summary</div>
                            <div className="flex items-baseline gap-2 mb-4">
                                <span className="text-h3 text-t-primary tabular-nums">
                                    {loadingLeads &&
                                    sourceTab.id === SOURCE_ID.all &&
                                    audience.length === 0
                                        ? "…"
                                        : audienceCount}
                                </span>
                                <span className="text-body-2 text-t-secondary">
                                    leads to call
                                </span>
                            </div>

                            {/* breakdown badges */}
                            <div className="flex flex-wrap items-center gap-2 mb-4">
                                {breakdown.hot > 0 && (
                                    <Badge variant="success" dot>
                                        {breakdown.hot} hot
                                    </Badge>
                                )}
                                {breakdown.warm > 0 && (
                                    <Badge variant="warning">
                                        {breakdown.warm} warm
                                    </Badge>
                                )}
                                {breakdown.cold > 0 && (
                                    <Badge variant="neutral">
                                        {breakdown.cold} cold
                                    </Badge>
                                )}
                                {manualSelected.size > 0 && (
                                    <Badge variant="info">hand-picked</Badge>
                                )}
                            </div>

                            {/* compact spec list */}
                            <dl className="space-y-2.5 pt-4 border-t border-s-subtle">
                                <SummaryRow
                                    label="Campaign"
                                    value={campaign?.name || "—"}
                                />
                                <SummaryRow
                                    label="Source"
                                    value={sourceTab.name}
                                />
                                <SummaryRow
                                    label="Pacing"
                                    value={`${concurrency || 1} concurrent`}
                                />
                                <SummaryRow
                                    label="Caps"
                                    value={
                                        [
                                            hourlyCap ? `${hourlyCap}/hr` : "",
                                            dailyCap ? `${dailyCap}/day` : "",
                                        ]
                                            .filter(Boolean)
                                            .join(" · ") || "none"
                                    }
                                />
                            </dl>

                            <Button
                                isBlack
                                className="w-full justify-center mt-5"
                                icon="send"
                                onClick={handleStart}
                                disabled={starting || !writable || !campaignId}
                            >
                                {starting
                                    ? "Starting…"
                                    : !writable
                                    ? "Read-only"
                                    : "Launch"}
                            </Button>
                            {!campaignId && (
                                <p className="mt-2 text-caption text-t-tertiary text-center">
                                    Choose a campaign to enable launch.
                                </p>
                            )}
                        </div>
                    </div>
                </aside>
            </div>

            {/* ── MOBILE sticky bottom launch bar ── */}
            <div className="lg:hidden fixed inset-x-0 bottom-0 z-30 p-3 bg-b-surface1/90 backdrop-blur border-t border-s-subtle">
                <div className="flex items-center gap-3">
                    <div className="min-w-0">
                        <div className="text-caption text-t-tertiary leading-tight">
                            {sourceTab.name}
                        </div>
                        <div className="text-button text-t-primary leading-tight tabular-nums">
                            {audienceCount} leads
                        </div>
                    </div>
                    <Button
                        isBlack
                        className="ml-auto shrink-0"
                        icon="send"
                        onClick={handleStart}
                        disabled={starting || !writable || !campaignId}
                    >
                        {starting ? "Starting…" : "Launch"}
                    </Button>
                </div>
            </div>
            {/* spacer so the mobile bottom bar never covers content */}
            <div className="lg:hidden h-20" aria-hidden />
        </Layout>
    );
}

// ── small summary-rail row ──
function SummaryRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <dt className="text-caption text-t-tertiary shrink-0">{label}</dt>
            <dd className="text-caption text-t-primary font-medium truncate text-right">
                {value}
            </dd>
        </div>
    );
}

// ── review-grid cell ──
function ReviewCell({
    label,
    value,
    sub,
}: {
    label: string;
    value: string;
    sub?: string;
}) {
    return (
        <div className="bg-b-surface2 p-4">
            <div className="eyebrow mb-1">{label}</div>
            <div className="text-body-1 text-t-primary truncate">{value}</div>
            {sub && (
                <div className="mt-0.5 text-caption text-t-tertiary truncate">
                    {sub}
                </div>
            )}
        </div>
    );
}
