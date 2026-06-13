"use client";

/**
 * VirtualRows — table-row virtualization (PERF UNIT-4).
 *
 * Renders ONLY the rows currently in (or near) the viewport, so a list of
 * thousands of rows mounts ~30 DOM rows instead of all of them. The page stays
 * the EXISTING Core_2 `<table>` (real `<thead>`/`<tbody>`/`<tr>`/`<td>`, cell
 * styling untouched) — we just feed `<tbody>` a windowed slice of `<tr>`s plus a
 * top/bottom spacer `<tr>` whose height reserves the off-screen rows. Because the
 * visible rows are still genuine table rows, column widths and borders stay
 * pixel-identical to the un-virtualized table (no flex/absolute hacks that break
 * `table-layout`).
 *
 * Built on @tanstack/react-virtual's headless `useVirtualizer` (same family as the
 * react-query cache we already use). Dynamic measurement (via `data-index`) handles
 * variable row heights (e.g. a "2h ago" sub-line) without a fixed-height guess.
 *
 * It also drives INFINITE-SCROLL: when the rendered window nears the end it calls
 * `onEndReached`, so the page fetches the NEXT cursor page lazily. react-query's
 * useInfiniteQuery guards duplicate concurrent fetches, so an extra call is a no-op.
 *
 * It does NOT own the scroll container — it virtualizes against the scrollable
 * ancestor passed via `scrollRef` (the card's overflow box), preserving the page's
 * existing layout/scroll chrome.
 *
 * CONTRACT: `renderRow` MUST return a single native `<tr>` element. We clone it to
 * attach the measurement `ref` + `data-index` (a native `<tr>` accepts a ref;
 * non-forwarding wrapper components do not — so render a plain `<tr>` with the
 * Core_2 row classes at the call site, not the <TableRow> component).
 */

import React, { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

type VirtualRowsProps<T> = {
    items: T[];
    rowKey: (item: T, index: number) => string | number;
    /** MUST return a single native `<tr>`. */
    renderRow: (item: T, index: number) => React.ReactElement;
    scrollRef: React.RefObject<HTMLElement | null>;
    /** Column count — spans the spacer rows so table layout stays valid. */
    colSpan: number;
    estimateRowH?: number;
    overscan?: number;
    onEndReached?: () => void;
    endReachedThreshold?: number;
};

export default function VirtualRows<T>({
    items,
    rowKey,
    renderRow,
    scrollRef,
    colSpan,
    estimateRowH = 64,
    overscan = 8,
    onEndReached,
    endReachedThreshold = 600,
}: VirtualRowsProps<T>) {
    const virtualizer = useVirtualizer({
        count: items.length,
        getScrollElement: () => scrollRef.current,
        estimateSize: () => estimateRowH,
        overscan,
        getItemKey: (index) => rowKey(items[index], index),
    });

    const virtualItems = virtualizer.getVirtualItems();
    const totalH = virtualizer.getTotalSize();

    const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0;
    const paddingBottom =
        virtualItems.length > 0
            ? totalH - virtualItems[virtualItems.length - 1].end
            : 0;

    // Infinite-scroll trigger.
    const lastEnd =
        virtualItems.length > 0 ? virtualItems[virtualItems.length - 1].end : 0;
    const firedAtRef = useRef(0);
    useEffect(() => {
        if (!onEndReached || items.length === 0) return;
        if (totalH - lastEnd < endReachedThreshold) {
            // Fire once per total-height growth (a new page lands → totalH grows →
            // allowed to fire again), so we never spam fetchNextPage at the bottom.
            if (firedAtRef.current !== totalH) {
                firedAtRef.current = totalH;
                onEndReached();
            }
        }
    }, [lastEnd, totalH, items.length, onEndReached, endReachedThreshold]);

    return (
        <>
            {paddingTop > 0 && (
                <tr aria-hidden="true">
                    <td colSpan={colSpan} style={{ height: paddingTop, padding: 0, border: 0 }} />
                </tr>
            )}
            {virtualItems.map((vi) => (
                <MeasuredRow
                    key={vi.key as React.Key}
                    index={vi.index}
                    measureElement={virtualizer.measureElement}
                >
                    {renderRow(items[vi.index], vi.index)}
                </MeasuredRow>
            ))}
            {paddingBottom > 0 && (
                <tr aria-hidden="true">
                    <td colSpan={colSpan} style={{ height: paddingBottom, padding: 0, border: 0 }} />
                </tr>
            )}
        </>
    );
}

/** Clones the call-site's native `<tr>` to attach the virtualizer ref + index. */
function MeasuredRow({
    index,
    measureElement,
    children,
}: {
    index: number;
    measureElement: (el: Element | null) => void;
    children: React.ReactElement;
}) {
    const ref = useRef<HTMLTableRowElement | null>(null);
    useEffect(() => {
        measureElement(ref.current);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [index]);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return React.cloneElement(children as React.ReactElement<any>, {
        ref,
        "data-index": index,
    });
}
