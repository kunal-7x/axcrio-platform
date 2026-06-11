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
import { StatusBadge, ScoreBadge } from "@/lib/badges";
import {
    getCampaigns,
    getLeads,
    getLeadBatches,
    addLeads,
    run,
    getStatus,
    RunError,
    type Campaign,
    type Lead,
    type UploadBatch,
    type StatusLead,
    type RunResult,
} from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";
import { type SelectOption } from "@/types/select";
import { type TabsOption } from "@/types/tabs";
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

    // Manual-picker view (filtered + search) — rows the vendor hand-picks from.
    const pickerRows = useMemo(
        () => applyQuery(filtered, query),
        [filtered, query]
    );

    const audience = useMemo(
        () => resolveAudience(filtered, manualSelected),
        [filtered, manualSelected]
    );

    const breakdown = useMemo(() => breakdownOf(audience), [audience]);

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
            return;
        }
        if (audience.length === 0 && sourceTab.id !== SOURCE_ID.all) {
            setToastType("error");
            setToast("No leads match the current audience — adjust your filters.");
            return;
        }
        setStarting(true);
        setToast("");
        setQueuedResult(null);
        setInsufficient(false);
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

    return (
        <Layout title="Run">
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

            <div className="flex gap-6 max-lg:flex-col">
                {/* ── LEFT: scrollable audience-builder rail ── */}
                <div className="w-[26rem] max-lg:w-full shrink-0 flex flex-col gap-4 max-h-[calc(100vh-12rem)] max-lg:max-h-none overflow-y-auto max-lg:overflow-visible pr-1 -mr-1 pb-2 scrollbar scrollbar-thumb-t-tertiary/40 scrollbar-track-transparent">
                    {/* 1 ── Campaign ── */}
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
                            <div className="mt-3 flex items-center gap-2 text-caption text-t-tertiary">
                                <Icon
                                    name="clock"
                                    className="size-4 fill-t-tertiary shrink-0"
                                />
                                Calls outside the calling window are queued and
                                dialed automatically.
                            </div>
                        </div>
                    </Card>

                    {/* 2 ── Audience source tabs ── */}
                    <Card title="Audience source">
                        <div className="px-5 pb-5 max-lg:px-3">
                            <Tabs
                                items={SOURCE_TABS}
                                value={sourceTab}
                                setValue={setSourceTab}
                                className="flex-wrap"
                                classButton="!h-10 !px-4 text-button"
                            />
                            <p className="mt-3 text-caption text-t-tertiary">
                                Filters compose — pick a temperature and/or a
                                file, then hand-pick if you want. The preview
                                always reflects exactly who will be dialed.
                            </p>
                        </div>
                    </Card>

                    {/* 3 ── Upload + batch list (source = By upload) ── */}
                    {showUpload && (
                        <Card title="Upload leads (CSV / Excel)">
                            <div className="px-5 pb-5 max-lg:px-3 space-y-4">
                                <FieldFiles
                                    onChange={(f) => setUploadFile(f)}
                                />
                                {/* widen accept to xlsx via the hidden input that
                                    FieldFiles renders — handled by the file picker;
                                    server routes by extension. */}
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
                                            No uploaded files yet. Drop a CSV or
                                            Excel file above — each import
                                            becomes a selectable batch.
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
                                                            key={b.batch_id}
                                                            selectedRows={on}
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
                                                                {b.count}
                                                            </td>
                                                        </TableRow>
                                                    );
                                                })}
                                            </Table>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </Card>
                    )}

                    {/* 4 ── Temperature filter (source = By temperature) ── */}
                    {showTemperature && (
                        <Card title="Temperature">
                            <div className="px-5 pb-5 max-lg:px-3 space-y-4">
                                <div className="flex flex-wrap gap-2">
                                    {TEMP_DEFS.map((t) => {
                                        const on = temps.has(t.key);
                                        return (
                                            <button
                                                key={t.key}
                                                onClick={() => toggleTemp(t.key)}
                                                className={`group flex items-center gap-2 h-10 px-4 rounded-full border text-button transition-colors ${
                                                    on
                                                        ? "border-s-stroke2 text-t-primary bg-b-surface1 dark:bg-shade-04/50"
                                                        : "border-transparent text-t-secondary hover:text-t-primary bg-b-surface1/60 dark:bg-shade-04/30"
                                                }`}
                                            >
                                                <span
                                                    className={`size-2 rounded-full ${
                                                        t.key === "hot"
                                                            ? "bg-primary-02"
                                                            : t.key === "warm"
                                                            ? "bg-primary-05"
                                                            : "bg-t-tertiary"
                                                    }`}
                                                />
                                                {t.label}
                                                <Badge
                                                    variant={
                                                        on ? "info" : "neutral"
                                                    }
                                                >
                                                    {tempCounts[t.key]}
                                                </Badge>
                                            </button>
                                        );
                                    })}
                                </div>
                                <p className="text-caption text-t-tertiary">
                                    Hot 70+ · Warm 40–69 · Cold under 40 /
                                    unscored. Pick one or more.
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
                                                setManualSelected(new Set());
                                                setUseBand(e.target.checked);
                                            }}
                                        />
                                    </label>
                                    {useBand && (
                                        <Range
                                            values={band}
                                            setValues={(v) => {
                                                setManualSelected(new Set());
                                                setBand([v[0], v[1]]);
                                            }}
                                            min={0}
                                            max={100}
                                            step={1}
                                        />
                                    )}
                                </div>
                            </div>
                        </Card>
                    )}

                    {/* 5 ── Manual lead picker (source = Pick manually) ── */}
                    {showManual && (
                        <Card
                            title="Pick leads"
                            headContent={
                                <Search
                                    className="w-44 max-md:w-32"
                                    classInput="!h-9"
                                    isGray
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    placeholder="Search"
                                />
                            }
                        >
                            <div className="px-2 pb-4 max-lg:px-1">
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
                                            selectAll={allPickerSelected}
                                            onSelectAll={
                                                toggleSelectAllPicker
                                            }
                                            cellsThead={
                                                <>
                                                    <th>Lead</th>
                                                    <th className="text-right">
                                                        Score
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
                                                    onRowSelect={(on) =>
                                                        toggleRow(l.id, on)
                                                    }
                                                >
                                                    <td>
                                                        <div className="flex items-center gap-2.5">
                                                            <span
                                                                className={`grid place-items-center size-8 shrink-0 rounded-full text-caption font-semibold ${
                                                                    (l.score ??
                                                                        0) >= 70
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
                                                                    {l.name}
                                                                </div>
                                                                <div className="text-caption text-t-tertiary td-num truncate max-w-36">
                                                                    {l.phone}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="text-right">
                                                        <ScoreBadge
                                                            score={l.score}
                                                        />
                                                    </td>
                                                </TableRow>
                                            ))}
                                        </Table>
                                    </div>
                                )}
                                <p className="px-3 pt-3 text-caption text-t-tertiary">
                                    {manualSelected.size > 0
                                        ? `${manualSelected.size} hand-picked — these exact leads will be dialed.`
                                        : "Tick rows to dial an exact subset, or leave empty to call everything that passed the filters."}
                                </p>
                            </div>
                        </Card>
                    )}

                    {/* 6 ── Pacing & caps ── */}
                    <Card title="Pacing & caps">
                        <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-3 gap-3">
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
                                    setHourlyCap(parseInt(e.target.value) || 0)
                                }
                            />
                            <Field
                                label="Daily cap"
                                type="number"
                                min={0}
                                value={dailyCap || ""}
                                onChange={(e) =>
                                    setDailyCap(parseInt(e.target.value) || 0)
                                }
                            />
                        </div>
                    </Card>
                </div>

                {/* ── RIGHT: preview bar + live status ── */}
                <div className="flex-1 min-w-0 flex flex-col gap-4">
                    {/* Sticky preview / launch bar */}
                    <div className="sticky top-2 z-10 card p-5 max-lg:p-4 flex items-center gap-5 max-md:flex-col max-md:items-stretch">
                        <div className="shrink-0">
                            <div className="eyebrow mb-1">Audience preview</div>
                            <div className="flex items-baseline gap-2">
                                <span className="text-h3 text-t-primary tabular-nums">
                                    {sourceTab.id === SOURCE_ID.all &&
                                    audience.length === 0
                                        ? loadingLeads
                                            ? "…"
                                            : storedLeads.length
                                        : breakdown.total}
                                </span>
                                <span className="text-body-2 text-t-secondary">
                                    leads will be called
                                </span>
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 grow">
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
                        <Button
                            isBlack
                            className="shrink-0 max-md:w-full max-md:justify-center"
                            icon="send"
                            onClick={handleStart}
                            disabled={starting || !writable || !campaignId}
                        >
                            {starting
                                ? "Starting…"
                                : !writable
                                ? "Read-only"
                                : "Start Calling"}
                        </Button>
                    </div>

                    {/* Live status */}
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
                                        Build your audience on the left and each
                                        lead&apos;s live status appears here.
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
                                        The dialer is spinning up — statuses
                                        refresh every few seconds.
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
            </div>
        </Layout>
    );
}
