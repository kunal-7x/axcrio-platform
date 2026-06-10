"use client";

import { useEffect, useState, useRef } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import { StatusBadge } from "@/lib/badges";
import { getCampaigns, run, getStatus, RunError, type Campaign, type StatusLead, type RunResult } from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";

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
            <PageHeader
                eyebrow="Outreach"
                title="Run a Call Run"
                subtitle="Pick a campaign, drop in your leads, set concurrency and caps, then dial — live status streams in on the right."
            />
            {toast && (
                <div
                    className={`toast items-start ${
                        toastType === "success" ? "toast-success"
                        : toastType === "warning" ? "border border-[#EF9D0E]/20 bg-[#EF9D0E]/8 text-[#C77E08] dark:text-[#EF9D0E]"
                        : "toast-error"
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
                <div className="toast toast-error">
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        Insufficient balance — top up to continue placing calls.
                    </span>
                    <a href="/billing" className="shrink-0 px-3 h-7 inline-flex items-center border border-current/30 rounded-full text-caption font-medium transition-colors hover:bg-current/10">Go to Billing</a>
                </div>
            )}

            {!writable && me && (
                <div className="mb-4 p-3.5 rounded-2xl surface text-t-secondary text-body-2">
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
                                    className="input-base w-full h-12 px-4 rounded-2xl text-body-2"
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
                                    className="input-base w-full h-28 px-4 py-3 rounded-2xl text-body-2 resize-none"
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
                                        className="input-base w-full h-10 px-3 rounded-xl text-body-2"
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
                                        className="input-base w-full h-10 px-3 rounded-xl text-body-2"
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
                                        className="input-base w-full h-10 px-3 rounded-xl text-body-2"
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
                            <table className="data-table">
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
                                            <td colSpan={3}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon name="send" className="fill-inherit" />
                                                    </span>
                                                    <div className="state-title">No active run</div>
                                                    <div className="state-sub">
                                                        Start a call run on the left and each lead&apos;s live status appears here.
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : liveLeads.length === 0 ? (
                                        <tr>
                                            <td colSpan={3}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon name="clock" className="fill-inherit" />
                                                    </span>
                                                    <div className="state-title">Waiting for updates…</div>
                                                    <div className="state-sub">
                                                        The dialer is spinning up — statuses refresh every few seconds.
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        liveLeads.map((l, i) => (
                                            <tr key={i}>
                                                <td className="font-medium text-t-primary">{l.name}</td>
                                                <td className="text-t-secondary td-num">
                                                    {l.num}
                                                </td>
                                                <td>
                                                    <StatusBadge status={l.status} />
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
