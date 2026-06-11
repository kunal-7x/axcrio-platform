"use client";

// The single React-Flow custom node renderer ("wfNode"). Paints the SAME premium
// card the old SVG canvas's NodeCard painted (accent left-bar, icon chip in the
// type accent, group eyebrow + label, advisory money pill) but as a real RF node
// with connectable Handles. A condition node exposes TWO labelled source handles
// (true / false); every other node has one source on the right + one target left.
// A trigger has no target handle (nothing connects INTO it).
//
// Reuses our Icon component + Signal tokens only — no new shared components.

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import Icon from "@/components/Icon";
import { nodeMeta, type WfNodeData } from "../_lib";

// Shared handle look — small token-coloured dot, hit-area enlarged by RF.
const handleStyle: React.CSSProperties = {
    width: 11,
    height: 11,
    background: "var(--b-surface1, #fff)",
    border: "2px solid var(--primary-01)",
    borderRadius: 9999,
};

function WfNodeViewImpl({ data, selected }: NodeProps) {
    const d = data as WfNodeData;
    const meta = nodeMeta(d.wfType);
    const isCondition = d.wfType === "condition";
    const isTrigger = d.wfType === "trigger";

    return (
        <div
            className={`relative select-none rounded-2xl bg-b-surface2 ring-1 ring-inset transition-shadow ${
                selected ? "ring-2 ring-primary-01 shadow-widget" : "ring-s-subtle hover:shadow-widget"
            }`}
            style={{ width: 184 }}
        >
            {/* target handle (left) — trigger has none */}
            {!isTrigger && (
                <Handle
                    type="target"
                    position={Position.Left}
                    style={handleStyle}
                    isConnectable
                />
            )}

            {/* accent left bar */}
            <span
                aria-hidden
                className="absolute left-0 top-3 bottom-3 w-1 rounded-full"
                style={{ background: meta.accent }}
            />

            <div className="flex items-start gap-2.5 p-3 pl-4">
                <span
                    className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04"
                    style={{ fill: meta.accent }}
                >
                    <Icon name={meta.icon} className="size-4 fill-inherit" />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="text-caption text-t-tertiary uppercase tracking-[0.06em]">
                        {meta.label}
                    </div>
                    <div className="text-body-2 text-t-primary truncate leading-tight mt-0.5">
                        {d.label || d.wfType}
                    </div>
                </div>
                {d.money && (
                    <span
                        title="Advisory: this step can spend — gated server-side by Budget + Approval"
                        className="grid place-items-center size-4 shrink-0 rounded-full"
                        style={{ background: "var(--primary-02)" }}
                    >
                        <Icon name="wallet" className="size-2.5 fill-white" />
                    </span>
                )}
            </div>

            {/* source handles */}
            {isCondition ? (
                <>
                    <Handle
                        id="true"
                        type="source"
                        position={Position.Right}
                        style={{ ...handleStyle, top: "34%", borderColor: "var(--primary-02)" }}
                        isConnectable
                    />
                    <Handle
                        id="false"
                        type="source"
                        position={Position.Right}
                        style={{ ...handleStyle, top: "70%", borderColor: "var(--primary-05)" }}
                        isConnectable
                    />
                    <span
                        className="absolute -right-7 text-[9px] font-semibold leading-none"
                        style={{ top: "30%", color: "var(--primary-02)" }}
                    >
                        true
                    </span>
                    <span
                        className="absolute -right-8 text-[9px] font-semibold leading-none"
                        style={{ top: "66%", color: "var(--primary-05)" }}
                    >
                        false
                    </span>
                </>
            ) : d.wfType !== "error" ? (
                <Handle type="source" position={Position.Right} style={handleStyle} isConnectable />
            ) : null}
        </div>
    );
}

export default memo(WfNodeViewImpl);
