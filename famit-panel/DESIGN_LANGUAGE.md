# Famit Premium Design Language (feat/premium-ui, base-uplift pass)

Source of truth for page agents. Apply these patterns; do NOT invent new tokens
or change component prop signatures. Everything below is already wired in
`app/globals.css` + the shared components — page agents just CONSUME it.

## What this pass changed (base/app-wide, so even un-restyled pages lift)
- `globals.css` `.card`: radius 2rem -> **rounded-3xl (1.5rem)** + light-mode
  hairline `ring-1 ring-s-subtle ring-inset` + `relative`. Now unified with
  `.surface` = ONE card language app-wide. Dark unchanged (inner top-light).
- `globals.css` `.surface`: same hairline ring added (matches `.card`).
- `globals.css` NEW utilities: `.focus-ring`, `.input-base`, `.lift`.
- `components/Field` (Input): brand **focus ring** on input + textarea
  (`focus:ring-2 focus:ring-primary-01/30 focus:border-primary-01/60`),
  smoother `transition-[color,border-color,box-shadow] duration-200`.
- `components/Select`: same focus ring via headless `data-[focus]`; ring cleared
  when open (`data-[open]:ring-0`).
- `components/Button`: `focus-visible` ring (offset, brand) + `active:scale-[0.98]`
  press + `disabled:opacity-50`. No prop change.
- `components/Table`: head -> **overline uppercase**, `tracking-[0.06em]`,
  `text-t-tertiary font-semibold`, head height 17->14, `thead` bottom hairline.
- Type scale, color tokens, and prior wave utilities (`.kpi`, `.pill`,
  `.data-table`, `.state-block`, `.skeleton`, `.meter`, `.rise-in`) UNCHANGED.

## Color
- Surfaces: `bg-b-surface2` (card), `bg-b-surface1` (page / inset chips).
- Text: `text-t-primary` (values/headings), `text-t-secondary` (body),
  `text-t-tertiary` (labels/overline). Never raw gray-* utilities.
- Brand/action: `primary-01` #2A85FF. Semantic: success `#00A656`,
  danger `#FF6A55`, warning `#EF9D0E`, info `primary-01`.
- Edges: light = `ring-s-subtle` hairline; dark = inner top-light. Never a hard
  1px black/gray border on cards.

## Type (DO NOT re-derive — use the named scale)
- Page/section titles: `text-h6` (card titles already do this via Card).
- Hero metric numbers: `text-h3` / `kpi-value` (tabular-nums, on by default).
- Body: `text-body-2`. Labels/eyebrows: `text-overline` (uppercase, tracked).
- Captions/footnotes: `text-caption`.

## Spacing & density
- Card padding: `p-3` shell + `pl-5` head (Card does this). Inside content,
  prefer multiples of `gap-2 / gap-3 / gap-5`.
- Card-to-card vertical rhythm: `mb-3` (Card built-in).
- Tables: row height ~`h-14`, cells `px-5 py-4`. Use `.data-table` for dense
  scannable lists (sticky overline head, hairline rows, `is-clickable` hover).

## Card style (THE signature)
- Default panel: `<Card title=...>` (rounded-3xl, hairline ring light / depth
  shadow dark). Modals / non-Card panels: `.surface`.
- Clickable card/row: add `.lift` (gentle -1px rise + warmer shadow on hover,
  settles on press). Use sparingly — only genuinely clickable elements.
- One radius family: cards `rounded-3xl`, pills/inputs `rounded-full`,
  chips/meters `rounded-md`/`rounded-lg`.

## Inputs / controls
- Text input = `<Field>`; Select = `<Select>`. Both now show the brand focus
  ring automatically. For a bespoke input, apply `.input-base` + `.focus-ring`.
- Buttons: `<Button>` variants `isBlack` (primary), `isStroke`/`isGray`/`isWhite`
  (secondary). Focus ring + press-scale are automatic.

## Motion (calm, not flashy)
- Entrance: `.rise-in` (6px up, 0.4s, ease-out-expo) on cards/rows.
- Hover lift: `.lift`. Transitions: 0.2s default. Honors
  `prefers-reduced-motion` (rise-in/skeleton disabled).

## Badges / status (ONE language)
- Use `<Badge variant="success|danger|warning|info|neutral" dot?>`; it renders
  the `.pill-*` utilities. Do NOT hand-roll `bg-green-100` pills.

## Hard rules for page agents
- No fabricated deltas ("+12%") — no prior-period data exists in the API.
  Use real signals only (series sparklines, cap ratios, answered/total).
- Never change a shared component's prop signature. Restyle via className/CSS.
- Dark mode must stay correct: rely on `b-*`/`t-*`/`s-*` tokens, never raw hex
  except the 4 semantic accents above.
