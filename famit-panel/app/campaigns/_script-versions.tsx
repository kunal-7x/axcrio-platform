"use client";

// ─────────────────────────────────────────────────────────────────────────────
// P7.4 — Script Studio 2.0 VERSION CONTROL
// Every save snapshots the script into fields.script_versions (bounded, de-duped). This panel lists
// the history (newest first), marks the one matching the current live script as "Published", and
// lets the operator RESTORE a past version into the editor (review → save to make it live) or
// COMPARE it against the current editor content with a line-level diff. Pure presentation; restore
// bubbles up via onRestore. No backend change — script_versions rides on the existing campaign save.
// ─────────────────────────────────────────────────────────────────────────────

import { useMemo, useState } from "react";
import Icon from "@/components/Icon";
import type { ScriptBlock } from "./_block-builder";

export type ScriptVersion = {
    v: number;
    at: string;            // ISO timestamp
    by?: string;
    raw_script?: string;
    script_blocks?: ScriptBlock[];
    script_studio_v2?: boolean;
    script_variables?: Record<string, string>;
};
export type CurrentSnap = {
    raw_script: string;
    script_blocks: ScriptBlock[];
    script_studio_v2: boolean;
    script_variables: Record<string, string>;
};

// A readable text rendering of a version, covering BOTH free-script and block modes, used for the
// diff + the de-dup signature.
export function serializeBlocks(blocks: ScriptBlock[] | undefined): string {
    return (blocks || []).map((b) => {
        const lines = [`# ${b.type}${b.enabled === false ? " (off)" : ""}`];
        if (b.text) lines.push(b.text);
        (b.items || []).forEach((x) => x && lines.push(`- ${x}`));
        (b.qa || []).forEach((p) => { if (p.q) lines.push(`Q: ${p.q}`); if (p.a) lines.push(`A: ${p.a}`); });
        if (b.goal) lines.push(`Goal: ${b.goal}`);
        (b.options || []).forEach((x) => x && lines.push(`* ${x}`));
        return lines.join("\n");
    }).join("\n\n");
}
export function versionText(s: { raw_script?: string; script_blocks?: ScriptBlock[]; script_studio_v2?: boolean }): string {
    if (s.script_studio_v2 && (s.script_blocks || []).length) return serializeBlocks(s.script_blocks);
    return (s.raw_script || "").trim() || serializeBlocks(s.script_blocks);
}

// LCS line diff → [{type, line}]. type: same | add (only in B/current) | del (only in A/version).
function lineDiff(aText: string, bText: string): { type: "same" | "add" | "del"; line: string }[] {
    const a = aText.split("\n"), b = bText.split("\n");
    const m = a.length, n = b.length;
    const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
    for (let i = m - 1; i >= 0; i--)
        for (let j = n - 1; j >= 0; j--)
            dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const out: { type: "same" | "add" | "del"; line: string }[] = [];
    let i = 0, j = 0;
    while (i < m && j < n) {
        if (a[i] === b[j]) { out.push({ type: "same", line: a[i] }); i++; j++; }
        else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: "del", line: a[i] }); i++; }
        else { out.push({ type: "add", line: b[j] }); j++; }
    }
    while (i < m) out.push({ type: "del", line: a[i++] });
    while (j < n) out.push({ type: "add", line: b[j++] });
    return out;
}

function fmtTime(iso: string): string {
    try {
        return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    } catch {
        return iso;
    }
}

export default function ScriptVersions({ versions, current, writable, onRestore }: {
    versions: ScriptVersion[];
    current: CurrentSnap;
    writable: boolean;
    onRestore: (v: ScriptVersion) => void;
}) {
    const [compareV, setCompareV] = useState<number | null>(null);
    const curText = useMemo(() => versionText(current), [current]);
    const ordered = useMemo(() => [...versions].sort((a, b) => b.v - a.v), [versions]);
    const publishedV = useMemo(() => {
        // the version whose content matches the current live script (newest match wins)
        const hit = ordered.find((s) => versionText(s) === curText);
        return hit ? hit.v : null;
    }, [ordered, curText]);

    const selected = compareV != null ? ordered.find((s) => s.v === compareV) : null;
    const diff = useMemo(() => (selected ? lineDiff(versionText(selected), curText) : []), [selected, curText]);
    const added = diff.filter((d) => d.type === "add").length;
    const removed = diff.filter((d) => d.type === "del").length;

    if (ordered.length === 0) {
        return (
            <div className="rounded-2xl border border-dashed border-s-stroke2 px-4 py-10 text-center">
                <div className="text-sub-title-2 text-t-primary">No saved versions yet</div>
                <div className="mt-1 text-caption text-t-tertiary">Each time you save, a version is snapshotted here — so you can compare and roll back.</div>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
                <Icon name="clock" className="size-4 fill-t-secondary" />
                <span className="text-button text-t-primary">Version history</span>
                <span className="text-caption text-t-tertiary">({ordered.length})</span>
            </div>

            <div className="flex flex-col divide-y divide-s-subtle overflow-hidden rounded-2xl ring-1 ring-inset ring-s-subtle">
                {ordered.map((s) => {
                    const isPub = s.v === publishedV;
                    const isCmp = s.v === compareV;
                    return (
                        <div key={s.v} className={`flex items-center gap-3 px-3.5 py-2.5 ${isCmp ? "bg-primary-01/[0.06]" : ""}`}>
                            <span className="text-caption tabular-nums text-t-tertiary w-8">v{s.v}</span>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                    <span className="truncate text-body-2 text-t-primary">{fmtTime(s.at)}</span>
                                    {isPub && <span className="pill pill-success"><span className="pill-dot" />Published</span>}
                                    {s.script_studio_v2 && (s.script_blocks || []).length > 0 && <span className="pill pill-info">{(s.script_blocks || []).length} blocks</span>}
                                </div>
                                {s.by && <span className="text-caption text-t-tertiary">by {s.by}</span>}
                            </div>
                            <button type="button" onClick={() => setCompareV(isCmp ? null : s.v)}
                                className="text-caption text-t-secondary hover:text-t-primary">
                                {isCmp ? "Hide diff" : "Compare"}
                            </button>
                            <button type="button" disabled={!writable || isPub} onClick={() => onRestore(s)}
                                className="text-caption text-primary-01 hover:brightness-110 disabled:opacity-40">
                                Restore
                            </button>
                        </div>
                    );
                })}
            </div>

            {selected && (
                <div className="rounded-2xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-3.5">
                    <div className="mb-2 flex items-center gap-2 text-caption">
                        <span className="text-t-secondary">v{selected.v} → current</span>
                        <span className="text-primary-02">+{added}</span>
                        <span className="text-primary-03">−{removed}</span>
                        {added === 0 && removed === 0 && <span className="text-t-tertiary">identical</span>}
                    </div>
                    <pre className="max-h-72 overflow-auto rounded-xl bg-b-surface1 p-3 text-[12px] leading-relaxed dark:bg-shade-04/30">
                        {diff.map((d, i) => (
                            <div key={i} className={
                                d.type === "add" ? "bg-primary-02/10 text-primary-02"
                                    : d.type === "del" ? "bg-primary-03/10 text-primary-03"
                                        : "text-t-secondary"
                            }>
                                <span className="select-none opacity-60">{d.type === "add" ? "+ " : d.type === "del" ? "− " : "  "}</span>
                                {d.line || " "}
                            </div>
                        ))}
                    </pre>
                </div>
            )}
        </div>
    );
}
