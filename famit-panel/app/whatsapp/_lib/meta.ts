// Client-side Meta (WhatsApp Business) template compliance pre-check.
//
// This is NOT Meta's own approval gate (that stays in ApprovalStep, shown live,
// never faked). It's a LOCAL, deterministic lint so the founder SEES — before
// submitting — whether a hand-written template is likely to pass Meta review.
// Pure functions, no backend, no invented verdict: every rule maps to a public
// Meta WhatsApp template policy / format constraint.

import { type TemplateDraft } from "./types";

export type ComplianceLevel = "pass" | "warn" | "fail";

export type ComplianceRule = {
    id: string;
    label: string;
    level: ComplianceLevel; // result for THIS draft
    detail: string; // founder-readable note (why / how to fix)
};

export type ComplianceReport = {
    overall: ComplianceLevel; // worst of all rules (fail > warn > pass)
    rules: ComplianceRule[];
    passCount: number;
    failCount: number;
    warnCount: number;
};

// Meta hard limits (public template format constraints).
const BODY_MAX = 1024; // body text char cap
const FOOTER_MAX = 60; // footer char cap
const CTA_LABEL_MAX = 25; // button label char cap

// Count {{1}} {{2}} … merge tokens, and verify they're sequential from 1.
function tokenAnalysis(body: string): { count: number; sequential: boolean; nums: number[] } {
    const found = [...body.matchAll(/\{\{\s*(\d+)\s*\}\}/g)].map((m) => Number(m[1]));
    const uniq = [...new Set(found)].sort((a, b) => a - b);
    const sequential = uniq.every((n, i) => n === i + 1);
    return { count: found.length, sequential, nums: uniq };
}

function worst(a: ComplianceLevel, b: ComplianceLevel): ComplianceLevel {
    const rank = { pass: 0, warn: 1, fail: 2 } as const;
    return rank[a] >= rank[b] ? a : b;
}

// Run the lint over a draft template and return a per-rule report.
export function checkMetaCompliance(draft: TemplateDraft): ComplianceReport {
    const body = (draft.body || "").trim();
    const footer = (draft.footer || "").trim();
    const cta = (draft.cta || "").trim();
    const ctaUrl = (draft.cta_url || "").trim();
    const rules: ComplianceRule[] = [];

    // 1 — body present
    rules.push(
        body
            ? { id: "body", label: "Message body", level: "pass", detail: "Body text present." }
            : { id: "body", label: "Message body", level: "fail", detail: "Add message body text — Meta rejects empty templates." }
    );

    // 2 — body length
    rules.push(
        body.length <= BODY_MAX
            ? { id: "body_len", label: "Body length", level: "pass", detail: `${body.length}/${BODY_MAX} characters.` }
            : { id: "body_len", label: "Body length", level: "fail", detail: `Body is ${body.length} characters — Meta's limit is ${BODY_MAX}.` }
    );

    // 3 — personalization tokens sequential ({{1}},{{2}},…)
    const tok = tokenAnalysis(body);
    if (tok.count === 0) {
        rules.push({ id: "tokens", label: "Personalization", level: "warn", detail: "No {{1}} merge fields — the message is the same for every lead. Add {{1}} to personalize." });
    } else if (!tok.sequential) {
        rules.push({ id: "tokens", label: "Personalization", level: "fail", detail: `Merge fields must be numbered sequentially from {{1}}. Found: ${tok.nums.map((n) => `{{${n}}}`).join(", ")}.` });
    } else {
        rules.push({ id: "tokens", label: "Personalization", level: "pass", detail: `${tok.nums.length} merge field(s), numbered correctly.` });
    }

    // 4 — no leading/trailing token & no consecutive tokens (Meta rejects)
    const consec = /\}\}\s*\{\{/.test(body);
    const edge = /^\s*\{\{|\}\}\s*$/.test(body);
    rules.push(
        !consec && !edge
            ? { id: "token_pos", label: "Merge-field placement", level: "pass", detail: "Tokens are embedded in copy, not back-to-back or at the edges." }
            : { id: "token_pos", label: "Merge-field placement", level: "fail", detail: "Meta rejects templates that start/end with a merge field or place two next to each other. Wrap them in words." }
    );

    // 5 — CTA pairing (label needs a URL, URL needs a label)
    if (cta || ctaUrl) {
        if (cta && !ctaUrl) {
            rules.push({ id: "cta", label: "Call-to-action", level: "warn", detail: "CTA label set but no URL — add a destination link so the button works." });
        } else if (!cta && ctaUrl) {
            rules.push({ id: "cta", label: "Call-to-action", level: "warn", detail: "CTA URL set but no button label — add a short label (e.g. “Book now”)." });
        } else if (cta.length > CTA_LABEL_MAX) {
            rules.push({ id: "cta", label: "Call-to-action", level: "fail", detail: `CTA label is ${cta.length} characters — Meta's button limit is ${CTA_LABEL_MAX}.` });
        } else if (ctaUrl && !/^https?:\/\//i.test(ctaUrl)) {
            rules.push({ id: "cta", label: "Call-to-action", level: "fail", detail: "CTA URL must start with http:// or https://." });
        } else {
            rules.push({ id: "cta", label: "Call-to-action", level: "pass", detail: "Button label and URL are valid." });
        }
    }

    // 6 — footer length
    if (footer) {
        rules.push(
            footer.length <= FOOTER_MAX
                ? { id: "footer", label: "Footer", level: "pass", detail: `${footer.length}/${FOOTER_MAX} characters.` }
                : { id: "footer", label: "Footer", level: "fail", detail: `Footer is ${footer.length} characters — Meta's limit is ${FOOTER_MAX}.` }
        );
    }

    // 7 — no newline runs / formatting Meta strips (3+ blank lines)
    rules.push(
        !/\n{3,}/.test(draft.body || "")
            ? { id: "format", label: "Formatting", level: "pass", detail: "No excessive blank lines." }
            : { id: "format", label: "Formatting", level: "warn", detail: "Several blank lines in a row — Meta collapses these; tighten the copy." }
    );

    const overall = rules.reduce<ComplianceLevel>((acc, r) => worst(acc, r.level), "pass");
    return {
        overall,
        rules,
        passCount: rules.filter((r) => r.level === "pass").length,
        warnCount: rules.filter((r) => r.level === "warn").length,
        failCount: rules.filter((r) => r.level === "fail").length,
    };
}
