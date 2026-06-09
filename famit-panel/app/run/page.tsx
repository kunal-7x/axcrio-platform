"use client";

import { useEffect, useState, useRef } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import { getCampaigns, run, getStatus, RunError, type Campaign, type StatusLead, type RunResult } from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";

function statusBadge(status: string) {
    const map: Record<string, string> = {
        done: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        calling: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        queued: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    };
    return (
        <span
            className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[status] || "bg-b-surface3 text-t-secondary"}`}
        >
            {status}
        </span>
    );
}

export default function RunPage() {
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [campaignId, setCampaignId] = useState("");
    const [leadsText, setLeadsText] = useState("");
    const [useStored, setUseStored] = useState(false);
    const [concurrency, setConcurrency] = useState(1);
    const [hourlyCap, setHourlyCap] = useState(0);
    const [dailyCap, setDailyCap] = useState(0);
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

    useEffect(() => {
        getCampaigns()
            .then((r) => {
                setCampaigns(r.campaigns);
                if (r.campaigns.length > 0) setCampaignId(r.campaigns[0].id);
            })
            .catch(() => {});
    }, []);

    // Poll job status
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
                // silently retry
            }
        }, 3000);

        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [jobId]);

    async function handleStart() {
        if (!campaignId) {
            setToast("Please select a campaign");
            return;
        }
        setStarting(true);
        setToast("");
        setQueuedResult(null);
        setInsufficient(false);
        try {
            const result = await run({
                campaign_id: campaignId,
                leads: leadsText,
                use_stored: useStored,
                concurrency: concurrency || undefined,
                hourly_cap: hourlyCap || undefined,
                daily_cap: dailyCap || undefined,
            });
            setJobId(result.job_id);
            setLiveLeads([]);
            if (result.queued_out_of_window) {
                setQueuedResult(result);
                setToastType("warning");
                const suppNote = result.suppressed_count ? ` (${result.suppressed_count} excluded — DND)` : "";
                setToast(`Outside calling window (${result.window}) — ${result.count} leads queued${suppNote}, dialing will start automatically.`);
                setJobState("queued");
            } else {
                setJobState("running");
                const suppNote = result.suppressed_count ? ` — ${result.suppressed_count} excluded (DND)` : "";
                setToastType("success");
                setToast(`Started! Job ${result.job_id} — ${result.count} leads${suppNote}`);
            }
        } catch (e: unknown) {
            setToastType("error");
            if (e instanceof RunError && e.code === "insufficient_balance") {
                setInsufficient(true);
                setToast("Insufficient balance — top up to continue. Visit Billing to add funds.");
            } else {
                setToast(e instanceof Error ? e.message : "Failed to start");
            }
        } finally {
            setStarting(false);
        }
    }

    return (
        <Layout title="Run">
            {toast && (
                <div
                    className={`mb-4 p-3 rounded-2xl text-body-2 flex items-start justify-between gap-3 ${
                        toastType === "success" ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                        : toastType === "warning" ? "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
                        : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                    }`}
                >
                    <span>{toast}</span>
                    {queuedResult && (
                        <button
                            className="shrink-0 px-3 py-1 border border-amber-500 rounded-2xl text-caption font-medium hover:bg-amber-100 transition-colors"
                            onClick={async () => {
                                setStarting(true);
                                try {
                                    const r = await run({
                                        campaign_id: campaignId,
                                        leads: leadsText,
                                        use_stored: useStored,
                                        concurrency: concurrency || undefined,
                                        force: true,
                                    });
                                    setJobId(r.job_id);
                                    setJobState("running");
                                    setToastType("success");
                                    setToast(`Started anyway! Job ${r.job_id} — ${r.count} leads`);
                                    setQueuedResult(null);
                                } catch { /* ignore */ } finally { setStarting(false); }
                            }}
                        >
                            Start anyway
                        </button>
                    )}
                </div>
            )}

            {insufficient && (
                <div className="mb-4 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 flex items-center justify-between gap-3 dark:bg-red-900/20 dark:text-red-400">
                    <span>Insufficient balance — top up to continue placing calls.</span>
                    <a href="/billing" className="shrink-0 px-3 py-1 border border-red-400 rounded-2xl text-caption font-medium hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors">Go to Billing</a>
                </div>
            )}

            {!writable && me && (
                <div className="mb-4 p-3 rounded-2xl bg-b-surface2 text-t-secondary text-body-2">
                    Your role is read-only — you can view campaigns and live status, but cannot start call runs.
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Config panel */}
                <div className="w-96 max-lg:w-full shrink-0">
                    <Card title="Start a Call Run">
                        <div className="px-5 pb-5 space-y-4">
                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Campaign
                                </label>
                                <select
                                    className="w-full h-12 px-4 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight bg-transparent"
                                    value={campaignId}
                                    onChange={(e) =>
                                        setCampaignId(e.target.value)
                                    }
                                >
                                    {campaigns.length === 0 && (
                                        <option value="">
                                            No campaigns available
                                        </option>
                                    )}
                                    {campaigns.map((c) => (
                                        <option key={c.id} value={c.id}>
                                            {c.name}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Leads (Name, Phone per line)
                                </label>
                                <textarea
                                    className="w-full h-28 px-4 py-3 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors resize-none hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
                                    placeholder={"John Doe, +919876543210\nJane Smith, +918765432109"}
                                    value={leadsText}
                                    onChange={(e) =>
                                        setLeadsText(e.target.value)
                                    }
                                />
                            </div>

                            <label className="flex items-center gap-3 cursor-pointer">
                                <input
                                    type="checkbox"
                                    className="w-4 h-4 rounded"
                                    checked={useStored}
                                    onChange={(e) =>
                                        setUseStored(e.target.checked)
                                    }
                                />
                                <span className="text-body-2 text-t-primary">
                                    Use stored leads
                                </span>
                            </label>

                            <div className="grid grid-cols-3 gap-3">
                                <div>
                                    <label className="block text-caption text-t-secondary mb-2">
                                        Concurrency
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        className="w-full h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                        value={concurrency || ""}
                                        onChange={(e) =>
                                            setConcurrency(
                                                parseInt(e.target.value) || 0
                                            )
                                        }
                                    />
                                </div>
                                <div>
                                    <label className="block text-caption text-t-secondary mb-2">
                                        Hourly cap
                                    </label>
                                    <input
                                        type="number"
                                        min="0"
                                        className="w-full h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                        value={hourlyCap || ""}
                                        onChange={(e) =>
                                            setHourlyCap(
                                                parseInt(e.target.value) || 0
                                            )
                                        }
                                    />
                                </div>
                                <div>
                                    <label className="block text-caption text-t-secondary mb-2">
                                        Daily cap
                                    </label>
                                    <input
                                        type="number"
                                        min="0"
                                        className="w-full h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                        value={dailyCap || ""}
                                        onChange={(e) =>
                                            setDailyCap(
                                                parseInt(e.target.value) || 0
                                            )
                                        }
                                    />
                                </div>
                            </div>

                            <Button
                                isBlack
                                className="w-full justify-center"
                                onClick={handleStart}
                                disabled={starting || !writable}
                            >
                                {starting ? "Starting…" : !writable ? "Read-only" : "Start Calling"}
                            </Button>
                        </div>
                    </Card>
                </div>

                {/* Live status */}
                <div className="flex-1 min-w-0">
                    <Card
                        title={
                            jobId
                                ? `Live Status — Job ${jobId} (${jobState})`
                                : "Live Status"
                        }
                    >
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Number</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {!jobId ? (
                                        <tr>
                                            <td
                                                colSpan={3}
                                                className="py-8 text-center text-t-secondary"
                                            >
                                                Start a run to see live status
                                            </td>
                                        </tr>
                                    ) : liveLeads.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={3}
                                                className="py-8 text-center text-t-secondary"
                                            >
                                                Waiting for updates…
                                            </td>
                                        </tr>
                                    ) : (
                                        liveLeads.map((l, i) => (
                                            <tr
                                                key={i}
                                                className="border-t border-s-subtle"
                                            >
                                                <td>{l.name}</td>
                                                <td className="text-t-secondary">
                                                    {l.num}
                                                </td>
                                                <td>
                                                    {statusBadge(l.status)}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}
