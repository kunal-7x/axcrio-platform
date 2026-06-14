"use client";

// ============================================================================
// _field-mapper — the visual JSONPath field-mapper (design crazy-ui-security §B,
// PROVIDER-FRAMEWORK-PLAN §7/§12.7). The ONE net-new component — the "connect ANY
// future tool from a form, no code deploy" lever.
//
// It builds two declarative maps WITHOUT hand-editing JSON:
//   • request_field_map : our envelope field  →  the provider's wire JSONPath
//   • response_field_map : our envelope field  ←  the provider's response JSONPath
// The emitted value is a flat { our_field: "$.their.path" } object the backend
// validates (JSONPath-only, depth ≤ 5, NO eval — adapter.validate_field_map). We
// validate client-side too so a bad path is caught before "Test connection".
//
// SECURITY: a field-map string is UNTRUSTED. This widget ONLY emits JSONPath-shaped
// strings and refuses anything with an expression/function/eval shape — the server
// is the real boundary, this is the friendly first gate. Zero hex, Core_2 tokens.
// ============================================================================

import { useMemo } from "react";
import Icon from "@/components/Icon";

// The internal envelope fields a consumer can map (PROVIDER-FRAMEWORK §7 envelope).
const REQUEST_FIELDS = ["prompt", "negative_prompt", "model", "max_tokens", "temperature", "duration_s", "aspect_ratio"];
const RESPONSE_FIELDS = ["text", "image_url", "video_url", "embedding", "external_id", "status"];

// Client-side JSONPath sanity: must start with `$`, only path chars, depth ≤ 5,
// and NONE of the expression/eval shapes the server rejects.
const PATH_OK = /^\$[A-Za-z0-9_.[\]*'"-]*$/;
const FORBIDDEN = /[()=;{}]|\beval\b|\bfunction\b|=>|\$\{/i;

export function validatePath(path: string): string {
    const p = (path || "").trim();
    if (!p) return ""; // empty = unmapped, allowed
    if (FORBIDDEN.test(p)) return "Expressions aren't allowed — JSONPath only.";
    if (!PATH_OK.test(p)) return "Must be a JSONPath like $.data.url";
    const depth = (p.match(/[.[]/g) || []).length;
    if (depth > 5) return "Too deep — max 5 levels.";
    return "";
}

export function validateMap(map: Record<string, string>): string {
    for (const [k, v] of Object.entries(map || {})) {
        const e = validatePath(v);
        if (e) return `${k}: ${e}`;
    }
    return "";
}

function MapRow({
    field,
    value,
    direction,
    onChange,
}: {
    field: string;
    value: string;
    direction: "request" | "response";
    onChange: (v: string) => void;
}) {
    const err = validatePath(value);
    return (
        <div className="flex items-center gap-2 py-2">
            <span className="font-mono text-caption text-t-primary w-28 shrink-0 truncate" title={field}>
                {field}
            </span>
            <Icon
                name={direction === "request" ? "arrow" : "chevron"}
                className={`size-3.5 shrink-0 ${direction === "response" ? "rotate-180 fill-t-tertiary" : "fill-t-tertiary"}`}
            />
            <input
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={direction === "request" ? "$.inputs.text" : "$.data[0].url"}
                spellCheck={false}
                className={`flex-1 h-8 px-3 rounded-xl bg-b-surface2 border text-caption font-mono text-t-primary focus:outline-none transition-colors ${
                    err ? "border-primary-03/50" : "border-s-subtle focus:border-s-highlight"
                }`}
            />
        </div>
    );
}

export default function FieldMapper({
    requestMap,
    responseMap,
    onChange,
}: {
    requestMap: Record<string, string>;
    responseMap: Record<string, string>;
    onChange: (req: Record<string, string>, res: Record<string, string>) => void;
}) {
    const reqErr = useMemo(() => validateMap(requestMap), [requestMap]);
    const resErr = useMemo(() => validateMap(responseMap), [responseMap]);

    const setReq = (field: string, v: string) => onChange({ ...requestMap, [field]: v }, responseMap);
    const setRes = (field: string, v: string) => onChange(requestMap, { ...responseMap, [field]: v });

    return (
        <div className="rounded-3xl border border-s-subtle p-4 bg-b-surface1">
            <div className="flex items-start gap-2 mb-3">
                <Icon name="chain" className="size-4 fill-t-secondary shrink-0 mt-0.5" />
                <p className="text-caption text-t-secondary">
                    Map our request fields to the provider&apos;s wire format, and read its response back —
                    using JSONPath only (e.g. <span className="font-mono text-t-primary">$.data[0].url</span>). Leave a
                    row blank to skip it. No code, no JSON editing.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
                <div>
                    <div className="text-caption text-t-tertiary uppercase tracking-wide mb-1 px-1">
                        Request — our field → their path
                    </div>
                    <div className="divide-y divide-s-subtle">
                        {REQUEST_FIELDS.map((f) => (
                            <MapRow
                                key={f}
                                field={f}
                                direction="request"
                                value={requestMap[f] || ""}
                                onChange={(v) => setReq(f, v)}
                            />
                        ))}
                    </div>
                </div>
                <div>
                    <div className="text-caption text-t-tertiary uppercase tracking-wide mb-1 px-1">
                        Response — our field ← their path
                    </div>
                    <div className="divide-y divide-s-subtle">
                        {RESPONSE_FIELDS.map((f) => (
                            <MapRow
                                key={f}
                                field={f}
                                direction="response"
                                value={responseMap[f] || ""}
                                onChange={(v) => setRes(f, v)}
                            />
                        ))}
                    </div>
                </div>
            </div>

            {(reqErr || resErr) && (
                <div className="mt-3 flex items-center gap-2 text-caption text-primary-03">
                    <Icon name="info" className="size-3.5 fill-primary-03 shrink-0" />
                    {reqErr || resErr}
                </div>
            )}
        </div>
    );
}
