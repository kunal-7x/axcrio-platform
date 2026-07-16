"use client";

// /knowledge — KB Management page (RAG W3 frontend)
//
// Three tabs:
//   1. Sources   — list of this tenant's KB sources + shared _global sources.
//                  Upload control: text area OR PDF file -> POST /kb/upload.
//   2. Test      — type a question (+ optional campaign tag) -> POST /kb/test-retrieve
//                  -> renders the chunks that fire (the "grounding" differentiator).
//   3. Gaps      — GET /kb/gaps: questions the AI couldn't answer (grounded=false).
//
// Design: Core_2 kit, Inter Display, token-based classes only (zero raw hex).
// Dormant-safe: every section has a calm empty state when the backend returns no data.

import { useCallback, useEffect, useRef, useState } from "react";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import Card from "@/components/Card";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Skeleton from "@/components/Skeleton";
import CampaignSelect from "@/components/CampaignSelect";
import type { TabsOption } from "@/types/tabs";
import {
    getKbSources,
    uploadKbText,
    uploadKbPdf,
    testRetrieve,
    getKbGaps,
    type KbSource,
    type KbChunk,
    type KbGap,
} from "./_lib";

// ---------- Tab definitions ----------

const TABS: (TabsOption & { key: string })[] = [
    { id: 1, name: "Sources", key: "sources" },
    { id: 2, name: "Test Answers", key: "test" },
    { id: 3, name: "Knowledge Gaps", key: "gaps" },
];

// ---------- Helpers ----------

function fmtDate(iso: string) {
    try {
        return new Intl.DateTimeFormat("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric",
        }).format(new Date(iso));
    } catch {
        return iso;
    }
}

function fmtRelative(iso: string) {
    try {
        const diff = Date.now() - new Date(iso).getTime();
        const mins = Math.floor(diff / 60_000);
        if (mins < 1) return "just now";
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        return `${Math.floor(hrs / 24)}d ago`;
    } catch {
        return iso;
    }
}

function scoreBar(score: number) {
    // score is a BM25 float — typically 0..0.05+ for FTS. We visualise it as a
    // proportional bar capped at 100% (anything ≥0.05 = full bar).
    const pct = Math.min(100, Math.round((score / 0.05) * 100));
    return pct;
}

// ---------- Sources tab ----------

type UploadMode = "text" | "pdf";

function SourcesTab() {
    const [sources, setSources] = useState<KbSource[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // Upload state
    const [mode, setMode] = useState<UploadMode>("text");
    const [text, setText] = useState("");
    const [title, setTitle] = useState("");
    const [pdfFile, setPdfFile] = useState<File | null>(null);
    const [campaignId, setCampaignId] = useState<string | undefined>();
    const [uploading, setUploading] = useState(false);
    const [uploadMsg, setUploadMsg] = useState("");
    const [uploadErr, setUploadErr] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getKbSources()
            .then((r) => setSources(r.sources))
            .catch(() => setError("Could not load sources. Try again."))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleUpload = async () => {
        setUploadErr("");
        setUploadMsg("");
        if (mode === "text" && !text.trim()) {
            setUploadErr("Paste some text first.");
            return;
        }
        if (mode === "pdf" && !pdfFile) {
            setUploadErr("Select a PDF file first.");
            return;
        }
        setUploading(true);
        try {
            let res;
            if (mode === "text") {
                res = await uploadKbText({ text, title: title || undefined, scopeCampaignId: campaignId });
            } else {
                res = await uploadKbPdf({ file: pdfFile!, scopeCampaignId: campaignId });
            }
            setUploadMsg(`Added "${res.title}" — ${res.chunks} chunk${res.chunks !== 1 ? "s" : ""} indexed.`);
            setText("");
            setTitle("");
            setPdfFile(null);
            if (fileRef.current) fileRef.current.value = "";
            load();
        } catch (e: unknown) {
            setUploadErr(e instanceof Error ? e.message : "Upload failed.");
        } finally {
            setUploading(false);
        }
    };

    const tenantSources = sources.filter((s) => !s.is_shared);
    const globalSources = sources.filter((s) => s.is_shared);

    return (
        <div className="space-y-5">
            {/* Upload card */}
            <Card title="Add Knowledge">
                <div className="px-5 pb-5 max-lg:px-3 space-y-4">
                    {/* Mode toggle */}
                    <div className="flex gap-2">
                        <button
                            onClick={() => setMode("text")}
                            className={`px-4 py-1.5 rounded-full text-body-2 font-medium transition-all border ${
                                mode === "text"
                                    ? "bg-b-primary text-t-light border-transparent"
                                    : "border-s-stroke2 text-t-secondary hover:text-t-primary"
                            }`}
                        >
                            Paste Text
                        </button>
                        <button
                            onClick={() => setMode("pdf")}
                            className={`px-4 py-1.5 rounded-full text-body-2 font-medium transition-all border ${
                                mode === "pdf"
                                    ? "bg-b-primary text-t-light border-transparent"
                                    : "border-s-stroke2 text-t-secondary hover:text-t-primary"
                            }`}
                        >
                            Upload PDF
                        </button>
                    </div>

                    {mode === "text" && (
                        <div className="space-y-3">
                            <input
                                className="w-full px-4 py-2.5 rounded-xl bg-b-surface2 border border-s-stroke2 text-body-2 text-t-primary placeholder:text-t-tertiary focus:outline-none focus:border-s-focus transition-colors"
                                placeholder="Source title (optional)"
                                value={title}
                                onChange={(e) => setTitle(e.target.value)}
                            />
                            <textarea
                                className="w-full h-32 px-4 py-3 rounded-xl bg-b-surface2 border border-s-stroke2 text-body-2 text-t-primary placeholder:text-t-tertiary focus:outline-none focus:border-s-focus transition-colors resize-none"
                                placeholder="Paste your FAQs, product info, scripts, pricing — anything you want the AI to know and cite…"
                                value={text}
                                onChange={(e) => setText(e.target.value)}
                            />
                        </div>
                    )}

                    {mode === "pdf" && (
                        <div
                            className="relative border-2 border-dashed border-s-stroke2 rounded-xl p-8 text-center cursor-pointer hover:border-s-focus transition-colors"
                            onClick={() => fileRef.current?.click()}
                        >
                            <input
                                ref={fileRef}
                                type="file"
                                accept=".pdf"
                                className="sr-only"
                                onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
                            />
                            <Icon className="fill-t-tertiary mx-auto mb-2" name="upload" />
                            {pdfFile ? (
                                <p className="text-body-2 text-t-primary font-medium">{pdfFile.name}</p>
                            ) : (
                                <p className="text-body-2 text-t-secondary">Click to choose a PDF</p>
                            )}
                        </div>
                    )}

                    {/* Optional campaign scope */}
                    <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-caption text-t-tertiary shrink-0">Scope to campaign (optional):</span>
                        <div className="w-52">
                            <CampaignSelect
                                value={campaignId}
                                placeholder="All campaigns"
                                label=""
                                onSelect={(c) => setCampaignId(c.id)}
                            />
                        </div>
                        {campaignId && (
                            <button
                                className="text-caption text-t-secondary hover:text-t-primary transition-colors"
                                onClick={() => setCampaignId(undefined)}
                            >
                                Clear
                            </button>
                        )}
                    </div>

                    <div className="flex items-center gap-3 flex-wrap">
                        <Button isBlack disabled={uploading} onClick={handleUpload}>
                            {uploading ? "Uploading…" : "Add to Knowledge Base"}
                        </Button>
                        {uploadMsg && (
                            <span className="text-body-2 text-primary-02">{uploadMsg}</span>
                        )}
                        {uploadErr && (
                            <span className="text-body-2 text-primary-03">{uploadErr}</span>
                        )}
                    </div>
                </div>
            </Card>

            {/* Your sources */}
            <Card title={`Your Sources${tenantSources.length ? ` (${tenantSources.length})` : ""}`}>
                {loading ? (
                    <div className="px-5 pb-5 max-lg:px-3 space-y-3">
                        {[1, 2, 3].map((i) => (
                            <div key={i} className="flex items-center gap-3">
                                <Skeleton.Bar className="h-10 flex-1 rounded-xl" />
                            </div>
                        ))}
                    </div>
                ) : error ? (
                    <div className="px-5 pb-5 max-lg:px-3">
                        <p className="text-body-2 text-primary-03">{error}</p>
                    </div>
                ) : tenantSources.length === 0 ? (
                    <div className="px-5 pb-8 max-lg:px-3 text-center">
                        <p className="text-body-2 text-t-tertiary mt-4">No sources yet. Add text or a PDF above to teach your AI something new.</p>
                    </div>
                ) : (
                    <div className="px-5 pb-5 max-lg:px-3 divide-y divide-s-subtle">
                        {tenantSources.map((s) => (
                            <SourceRow key={s.id} source={s} />
                        ))}
                    </div>
                )}
            </Card>

            {/* Global / shared sources */}
            {globalSources.length > 0 && (
                <Card title={`Haptica AI Knowledge Base (${globalSources.length})`}>
                    <div className="px-5 pb-5 max-lg:px-3 divide-y divide-s-subtle">
                        {globalSources.map((s) => (
                            <SourceRow key={s.id} source={s} shared />
                        ))}
                    </div>
                </Card>
            )}
        </div>
    );
}

function SourceRow({ source, shared }: { source: KbSource; shared?: boolean }) {
    return (
        <div className="py-3.5 flex items-start gap-4">
            <div className="w-9 h-9 shrink-0 rounded-xl bg-b-surface1 flex items-center justify-center">
                <Icon
                    className="fill-t-secondary"
                    name={source.kind === "pdf" ? "upload" : "edit"}
                />
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-body-2 font-medium text-t-primary truncate">{source.title}</span>
                    {shared && <Badge variant="info">Shared</Badge>}
                    <Badge variant={source.status === "active" ? "success" : "warning"}>
                        {source.status}
                    </Badge>
                </div>
                <div className="flex items-center gap-3 mt-1 flex-wrap">
                    <span className="text-caption text-t-tertiary">{source.chunks} chunk{source.chunks !== 1 ? "s" : ""}</span>
                    {source.scope && source.scope !== "null" && (
                        <span className="text-caption text-t-secondary">{source.scope}</span>
                    )}
                    <span className="text-caption text-t-tertiary">{fmtDate(source.created_at)}</span>
                </div>
            </div>
        </div>
    );
}

// ---------- Test Answers tab ----------

function TestTab() {
    const [query, setQuery] = useState("");
    const [campaignId, setCampaignId] = useState<string | undefined>();
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ grounded: boolean; chunks: KbChunk[]; query: string } | null>(null);
    const [error, setError] = useState("");

    const run = async () => {
        if (!query.trim()) return;
        setLoading(true);
        setError("");
        setResult(null);
        try {
            const r = await testRetrieve({ query, campaign: campaignId, top_k: 6 });
            setResult({ grounded: r.grounded, chunks: r.chunks, query: r.query });
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Request failed.");
        } finally {
            setLoading(false);
        }
    };

    const handleKey = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
    };

    return (
        <div className="space-y-5">
            <Card title="Test Answers">
                <div className="px-5 pb-5 max-lg:px-3 space-y-4">
                    <p className="text-body-2 text-t-secondary">
                        Type any question a lead might ask. See exactly which knowledge chunks your AI would cite — before a live call.
                    </p>
                    <textarea
                        className="w-full h-24 px-4 py-3 rounded-xl bg-b-surface2 border border-s-stroke2 text-body-2 text-t-primary placeholder:text-t-tertiary focus:outline-none focus:border-s-focus transition-colors resize-none"
                        placeholder="e.g. What is the registration charge? How many EMI options?"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={handleKey}
                    />
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="w-52">
                            <CampaignSelect
                                value={campaignId}
                                placeholder="All campaigns"
                                label=""
                                onSelect={(c) => setCampaignId(c.id)}
                            />
                        </div>
                        {campaignId && (
                            <button
                                className="text-caption text-t-secondary hover:text-t-primary transition-colors"
                                onClick={() => setCampaignId(undefined)}
                            >
                                Clear
                            </button>
                        )}
                        <Button isBlack disabled={loading || !query.trim()} onClick={run}>
                            {loading ? "Searching…" : "Test Answer"}
                        </Button>
                        <span className="text-caption text-t-tertiary hidden md:inline">⌘↵</span>
                    </div>
                    {error && <p className="text-body-2 text-primary-03">{error}</p>}
                </div>
            </Card>

            {/* Results */}
            {loading && (
                <Card title="Grounding…">
                    <div className="px-5 pb-5 max-lg:px-3 space-y-3">
                        {[1, 2, 3].map((i) => (
                            <Skeleton.Bar key={i} className="h-20 rounded-xl" />
                        ))}
                    </div>
                </Card>
            )}

            {result && !loading && (
                <Card
                    title={
                        result.grounded
                            ? `Grounded — ${result.chunks.length} chunk${result.chunks.length !== 1 ? "s" : ""} matched`
                            : "Not Grounded — no matching knowledge"
                    }
                >
                    <div className="px-5 pb-5 max-lg:px-3">
                        {/* Grounding verdict banner */}
                        <div
                            className={`flex items-center gap-2 px-4 py-3 rounded-xl mb-4 ${
                                result.grounded
                                    ? "bg-primary-02/10 border border-primary-02/20"
                                    : "bg-primary-03/10 border border-primary-03/20"
                            }`}
                        >
                            <span
                                className={`w-2 h-2 rounded-full shrink-0 ${
                                    result.grounded ? "bg-primary-02" : "bg-primary-03"
                                }`}
                            />
                            <span className="text-body-2 font-medium text-t-primary">
                                {result.grounded
                                    ? "AI would answer this from your knowledge base."
                                    : "AI has no knowledge for this question — add a source to teach it."}
                            </span>
                        </div>

                        {/* Chunk cards */}
                        {result.chunks.length > 0 && (
                            <div className="space-y-3">
                                {result.chunks.map((c, i) => (
                                    <ChunkCard key={c.id} chunk={c} rank={i + 1} />
                                ))}
                            </div>
                        )}

                        {result.chunks.length === 0 && (
                            <p className="text-body-2 text-t-tertiary text-center py-4">
                                No chunks fired for this query.
                            </p>
                        )}
                    </div>
                </Card>
            )}

            {/* Empty initial state */}
            {!result && !loading && (
                <div className="text-center py-12">
                    <div className="w-14 h-14 rounded-2xl bg-b-surface2 flex items-center justify-center mx-auto mb-4 shadow-widget">
                        <Icon className="fill-t-tertiary" name="search" />
                    </div>
                    <p className="text-body-2 text-t-secondary font-medium">Ask a question to see your AI's grounding</p>
                    <p className="text-caption text-t-tertiary mt-1">
                        This runs the exact same retrieval the live voice agent uses on every call.
                    </p>
                </div>
            )}
        </div>
    );
}

function ChunkCard({ chunk, rank }: { chunk: KbChunk; rank: number }) {
    const pct = scoreBar(chunk.score);
    return (
        <div className="rounded-xl bg-b-surface2 border border-s-subtle p-4 space-y-2.5">
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-b-primary flex items-center justify-center text-t-light text-caption font-semibold shrink-0">
                        {rank}
                    </span>
                    {chunk.section && (
                        <span className="text-caption text-t-secondary font-medium">{chunk.section}</span>
                    )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="neutral">{chunk.leg}</Badge>
                    <span className="text-caption text-t-tertiary font-mono">{chunk.score.toFixed(4)}</span>
                </div>
            </div>

            {/* Score bar */}
            <div className="h-1 rounded-full bg-b-surface1 overflow-hidden">
                <div
                    className="h-full rounded-full bg-b-primary transition-all"
                    style={{ width: `${pct}%` }}
                />
            </div>

            {/* Snippet */}
            <p className="text-body-2 text-t-primary leading-relaxed">{chunk.snippet}</p>
        </div>
    );
}

// ---------- Knowledge Gaps tab ----------

const GAP_WINDOWS = [
    { id: 1, name: "Last 7 days" },
    { id: 2, name: "Last 30 days" },
    { id: 3, name: "Last 90 days" },
];

function GapsTab() {
    const [window, setWindow] = useState(GAP_WINDOWS[0]);
    const [gaps, setGaps] = useState<KbGap[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [total, setTotal] = useState(0);

    const days = [7, 30, 90][window.id - 1];

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getKbGaps({ days, limit: 50 })
            .then((r) => {
                setGaps(r.gaps);
                setTotal(r.total);
            })
            .catch(() => setError("Could not load gaps."))
            .finally(() => setLoading(false));
    }, [days]);

    useEffect(() => { load(); }, [load]);

    return (
        <div className="space-y-5">
            <Card
                title={`Knowledge Gaps${total ? ` — ${total} unanswered question${total !== 1 ? "s" : ""}` : ""}`}
                selectOptions={GAP_WINDOWS}
                selectValue={window}
                selectOnChange={setWindow}
            >
                {loading ? (
                    <div className="px-5 pb-5 max-lg:px-3 space-y-3">
                        {[1, 2, 3, 4].map((i) => (
                            <Skeleton.Bar key={i} className="h-14 rounded-xl" />
                        ))}
                    </div>
                ) : error ? (
                    <div className="px-5 pb-5 max-lg:px-3">
                        <p className="text-body-2 text-primary-03">{error}</p>
                    </div>
                ) : gaps.length === 0 ? (
                    <div className="px-5 pb-10 max-lg:px-3 text-center">
                        <div className="w-12 h-12 rounded-2xl bg-b-surface1 flex items-center justify-center mx-auto mt-4 mb-3">
                            <Icon className="fill-primary-02" name="check" />
                        </div>
                        <p className="text-body-2 text-t-secondary font-medium">No gaps in the last {days} days</p>
                        <p className="text-caption text-t-tertiary mt-1">Your AI answered every question from the knowledge base.</p>
                    </div>
                ) : (
                    <div className="px-5 pb-5 max-lg:px-3">
                        <p className="text-body-2 text-t-secondary mb-4">
                            These are questions your AI couldn't ground in the last {days} days. Add sources above to fill them.
                        </p>
                        <div className="space-y-3">
                            {gaps.map((g, i) => (
                                <GapRow key={i} gap={g} />
                            ))}
                        </div>
                    </div>
                )}
            </Card>
        </div>
    );
}

function GapRow({ gap }: { gap: KbGap }) {
    return (
        <div className="flex items-start gap-4 px-4 py-3.5 rounded-xl bg-b-surface2 border border-s-subtle group hover:border-s-highlight transition-colors">
            {/* frequency badge */}
            <div className="shrink-0 text-center min-w-[2.5rem]">
                <span className="text-h6 text-primary-03 font-semibold">{gap.count}</span>
                <p className="text-caption text-t-tertiary leading-none">asks</p>
            </div>

            <div className="flex-1 min-w-0">
                <p className="text-body-2 text-t-primary font-medium truncate">{gap.query}</p>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <span className="text-caption text-t-tertiary">{fmtRelative(gap.last_seen)}</span>
                    {gap.channels.filter(Boolean).map((ch) => (
                        <Badge key={ch} variant="neutral">{ch}</Badge>
                    ))}
                </div>
            </div>

            {/* quick action: copy to clipboard to prep a new source */}
            <button
                className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Copy question to clipboard"
                onClick={() => navigator.clipboard?.writeText(gap.query)}
            >
                <Icon className="fill-t-tertiary hover:fill-t-primary transition-colors" name="dots" />
            </button>
        </div>
    );
}

// ---------- Page ----------

export default function KnowledgePage() {
    const [activeTab, setActiveTab] = useState(TABS[0]);

    const setTab = (opt: TabsOption) => {
        const t = TABS.find((x) => x.id === opt.id) || TABS[0];
        setActiveTab(t);
    };

    return (
        <Layout title="Knowledge Base">
            <Tabs className="mb-5" items={TABS} value={activeTab} setValue={setTab} />
            {activeTab.key === "sources" && <SourcesTab />}
            {activeTab.key === "test" && <TestTab />}
            {activeTab.key === "gaps" && <GapsTab />}
        </Layout>
    );
}
