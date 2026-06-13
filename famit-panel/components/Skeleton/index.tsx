"use client";

/**
 * Skeleton — the shared "loading shape" primitives (PERF UNIT-3).
 *
 * A page must NEVER paint a frozen blank while its data loads. These render the
 * dimension-matched grey shimmer the real content will occupy, so first paint is
 * immediate and the layout doesn't jump when data lands.
 *
 * CSS-only — reuses the `.skeleton` shimmer already defined in globals.css (W1),
 * so there's no new dependency and it's dark-mode + prefers-reduced-motion safe.
 * Presentational only, zero network I/O.
 */

import React from "react";

/** A single shimmer bar. Size it with Tailwind via `className` (h-/w-/rounded-). */
export function SkeletonBar({ className = "" }: { className?: string }) {
    return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/**
 * SkeletonTableRows — N placeholder rows for a <Table>, one cell per column.
 * Drop straight into the table body where the real <TableRow>s will go.
 * `widths` lets you taper cell widths to look like real data (optional).
 */
export function SkeletonTableRows({
    rows = 6,
    cols = 5,
    widths,
}: {
    rows?: number;
    cols?: number;
    widths?: string[];
}) {
    return (
        <>
            {Array.from({ length: rows }).map((_, r) => (
                <tr key={r} className="border-b border-s-subtle/60 last:border-0">
                    {Array.from({ length: cols }).map((__, c) => (
                        <td key={c} className="py-3 px-4">
                            <SkeletonBar
                                className={`h-4 ${widths?.[c] ?? (c === 0 ? "w-32" : "w-20")}`}
                            />
                        </td>
                    ))}
                </tr>
            ))}
        </>
    );
}

/**
 * SkeletonCards — a grid of N card-shaped placeholders (library/gallery/list views).
 */
export function SkeletonCards({
    count = 6,
    className = "",
    cardClassName = "h-40",
}: {
    count?: number;
    className?: string;
    cardClassName?: string;
}) {
    return (
        <div
            className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 ${className}`}
            role="status"
            aria-busy="true"
            aria-label="Loading"
        >
            {Array.from({ length: count }).map((_, i) => (
                <SkeletonBar key={i} className={`rounded-3xl ${cardClassName}`} />
            ))}
        </div>
    );
}

/**
 * SkeletonStats — a row of stat-tile placeholders (dashboard headers).
 */
export function SkeletonStats({ count = 4 }: { count?: number }) {
    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="card p-5 space-y-3">
                    <SkeletonBar className="h-3 w-24" />
                    <SkeletonBar className="h-7 w-20" />
                </div>
            ))}
        </div>
    );
}

/**
 * SkeletonLines — stacked text-line placeholders (panels, detail bodies).
 */
export function SkeletonLines({
    lines = 3,
    className = "",
}: {
    lines?: number;
    className?: string;
}) {
    return (
        <div className={`space-y-2 ${className}`} aria-hidden="true">
            {Array.from({ length: lines }).map((_, i) => (
                <SkeletonBar
                    key={i}
                    className={`h-4 ${i === lines - 1 ? "w-2/5" : i % 2 ? "w-4/5" : "w-3/5"}`}
                />
            ))}
        </div>
    );
}

const Skeleton = {
    Bar: SkeletonBar,
    TableRows: SkeletonTableRows,
    Cards: SkeletonCards,
    Stats: SkeletonStats,
    Lines: SkeletonLines,
};

export default Skeleton;
