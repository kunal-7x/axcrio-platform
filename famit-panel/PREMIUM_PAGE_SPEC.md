# PREMIUM PAGE RESTYLE SPEC — apply this ONE pattern, mechanically

You are restyling pages of the Famit panel to ONE cohesive premium language
("Signal"). The shell, login, and the REFERENCE page (`app/campaigns/page.tsx`)
are already done — COPY their patterns exactly. Do NOT invent new styling.

## ABSOLUTE RULES (violating any = failure)
1. RESTYLE ONLY. Do NOT change: any `lib/api.ts` call, any state variable, any
   event handler, any `useEffect`, any data shape, any route, any component PROP
   signature. Only change JSX className/markup and presentational wrapper markup.
2. TOKENS ONLY. After editing each file, it MUST contain ZERO of these (grep it):
   `bg-white` `text-black` `bg-green-`/`red-`/`yellow-`/`blue-`/`amber-`/`purple-`/
   `gray-`/`orange-` `[0-9]` color utilities, and `text-...-[0-9]` / `border-...-[0-9]`
   raw color utilities. Replace them with the token classes below.
3. Dark-mode must stay correct → never raw hex except the 4 semantic accents that
   the design system already uses (#00A656 success, #FF6A55 danger, #EF9D0E warning,
   #2A85FF/primary-01 info). Prefer the utility classes that already encode them.
4. Keep the build green. `next.config.ts` ignores TS/lint during build, but do not
   introduce undefined identifiers. Import what you use (`Icon`, `PageHeader`,
   `StatusBadge`, etc.).

## THE PATTERN (from app/campaigns/page.tsx — open it and mirror it)

### a) Page masthead — add right after `<Layout title="...">`
```tsx
import PageHeader from "@/components/PageHeader";
...
<PageHeader
    eyebrow="<Section>"     // Outreach | Activity | Integrations | Billing | Admin — match the sidebar section
    title="<Page Title>"     // same as Layout title
    subtitle="<one calm sentence describing the page>"
/>
```
Eyebrow by page: Run→"Outreach", Callbacks/Suppression→"Activity",
Analytics→"Activity", Webhooks/WhatsApp→"Integrations", Vendors→"Admin",
Settings→"Account", Billing/*→"Billing".

### b) Status / outcome badges — DELETE any local `statusBadge`/`outcomeBadge`
function that returns raw `bg-green-100…` and use the shared language:
```tsx
import { StatusBadge, OutcomeBadge, ScoreBadge } from "@/lib/badges";
<StatusBadge status={x.status} />     // call/lead/job status
<OutcomeBadge outcome={x.outcome} />  // call outcome
<ScoreBadge score={x.score} />        // numeric lead score
```
If a value isn't in the badge map it falls back to neutral — that's fine.

### c) Toasts / alert banners — replace raw bg-green-50/bg-red-50/bg-amber-50:
```tsx
<div className="toast toast-success"> ...success... </div>
<div className="toast toast-error"> ...error... </div>
// warning: <div className="toast" style-equivalent> use pill-warning colors:
<div className="toast border border-[#EF9D0E]/20 bg-[#EF9D0E]/8 text-[#C77E08] dark:text-[#EF9D0E]"> ... </div>
```
Lead each toast message with `<span className="size-1.5 rounded-full bg-current" />`.
Inline action buttons inside a toast → use `className="action"` or a small
`<Button isStroke>`.

### d) Tables — replace `<table className="w-full text-body-2 [&_th]:h-13 …">`
with the dense premium table:
```tsx
<div className="overflow-x-auto">
  <table className="data-table">      {/* add `is-clickable` only if rows are clickable */}
    <thead><tr><th>…</th><th className="text-right">…</th></tr></thead>
    <tbody>
      {rows.map(r => (
        <tr key={r.id}>
          <td className="font-medium text-t-primary">{r.name}</td>
          <td className="text-t-secondary td-num">{r.number}</td>   {/* td-num for numeric/phone */}
          <td><StatusBadge status={r.status} /></td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```
Do NOT add manual `border-t border-s-subtle` to `<tr>` — `.data-table` handles row
hairlines.

### e) Empty + loading states inside a table → `.state-block` (see campaigns):
```tsx
<tr><td colSpan={N}>
  <div className="state-block">
    <span className="state-glyph"><Icon name="<icon>" className="fill-inherit" /></span>
    <div className="state-title">No <things> yet</div>
    <div className="state-sub"><one sentence what shows up here></div>
  </div>
</td></tr>
```
Loading rows → skeleton rows: `<td><div className="skeleton h-4 w-20" /></td>`.
Replace inline `<svg className="animate-spin">` spinners inside tables with skeletons;
spinners INSIDE a `<Button>` label may stay.

### f) Form inputs — bare `<input>/<textarea>/<select>` that use
`border border-s-stroke2 … bg-transparent hover:border-s-highlight focus:border-s-highlight`
are token-OK already; UPGRADE them to the shared field shell for the brand focus ring:
add `input-base` and drop the duplicated border/hover/focus classes, keep sizing:
```tsx
className="input-base w-full h-12 px-4 rounded-2xl text-body-2"
```
Checkboxes: keep as-is (they're fine). Primary actions stay `<Button isBlack>`.

### g) Section cards stay `<Card title="…">`. For non-Card panels/modals use `.surface`.
Modal backdrops: `fixed inset-0 z-50 bg-shade-01/60 backdrop-blur-sm` (NOT `bg-black/50`).

## PER-PAGE CHECKLIST (do these files, build after each 2-3, COMMIT NOTHING — no git)
- app/run/page.tsx          (statusBadge raw → StatusBadge; 3 toast/alert banners → .toast*; live-status table → data-table + state-block; select/inputs → input-base)
- app/callbacks/page.tsx
- app/suppression/page.tsx
- app/webhooks/page.tsx
- app/whatsapp/page.tsx
- app/vendors/page.tsx
- app/analytics/page.tsx    (mostly add PageHeader + fix the 1 raw color; keep recharts colors using CSS vars as-is)
- app/settings/page.tsx     (add PageHeader eyebrow "Account"; fix 2 raw colors)

## VERIFY (must pass before you report done)
1. For EACH edited file: `grep -nE "bg-white|text-black|bg-(green|red|yellow|blue|amber|purple|gray|orange)-[0-9]|text-(green|red|yellow|blue|amber|purple|gray|orange)-[0-9]|border-(green|red|yellow|blue|amber)-[0-9]" <file>` → MUST be empty.
2. `npx next build` → MUST exit 0.
3. Report: which files changed, confirm grep-clean + build exit 0. Return conclusions only, no file dumps.
