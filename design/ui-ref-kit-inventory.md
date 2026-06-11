# UI Reference Kit Inventory — `core-2-dashboard-builder-react`

READ-ONLY design wave. Source of truth for our UI port. Reference kit =
`C:\Users\kunal\Desktop\core-2-dashboard-builder-react` ("Core 2.0 – Dashboard
Builder", a UI8 commercial kit, shipped as real Next.js + React code). Our app to
port onto it = `C:\Users\kunal\Desktop\caps\famit-panel`.

**The rule (founder, repeated):** do NOT hand-build a lookalike. Where a reference
page matches one of ours, USE that page as-is and swap our data. Copy the actual
JSX/Tailwind/tokens below — do not re-derive.

---

## 0. TECH STACK (what to install)

- **Next.js 15.2** app-router, **React 19**, **TypeScript 5**.
- **Tailwind CSS v4** (`@import "tailwindcss"` in CSS, `@tailwindcss/postcss`
  plugin, **NO `tailwind.config.js`** — the whole theme lives in `globals.css`
  via `@theme {}`). Plugin: `tailwind-scrollbar`.
- **Headless UI** (`@headlessui/react` v2) for Select/Listbox, Modal/Dialog,
  Switch — every interactive primitive.
- **next-themes** for light/dark (`data-theme` attribute, `disableTransitionOnChange`).
- **framer-motion**, **recharts** (charts), **swiper** (sliders),
  **react-datepicker**, **react-slider** (Range), **@tiptap** (rich-text Editor),
  **react-number-format**, **react-scroll** (settings anchor nav), **millify**,
  **emoji-picker-react**, **react-tagsinput**, **react-textarea-autosize**,
  **react-tooltip**, **react-remove-scroll**, **react-animate-height**.
- **Icons = a custom inline-SVG set** baked into `components/Icon/index.tsx` (a
  `name -> SVG path string` dictionary, ~120 icons, all on a 24×24 viewBox). NOT
  an icon library. `<Icon name="dashboard" />` renders one `<path>`. To add an
  icon, paste its path into that dictionary. Color via `fill-*` utilities.

---

## 1. FONT (CRITICAL — fixes the "font didn't change" complaint)

- The kit's font is **Inter Display** (the "Display" optical cut of Inter), NOT
  Gilroy. Loaded via **`next/font/local`** from 5 local woff2 files in
  `public/fonts/`: `InterDisplay-Light(300) / Regular(400) / Medium(500) /
  SemiBold(600) / Bold(700)`.
- Loaded in `app/layout.tsx` as `localFont({...})` exposing CSS var
  `--font-inter-display`; `globals.css` maps `--font-inter: var(--font-inter-display)`
  and the Tailwind class is **`font-inter`**, applied once on `<body>`.
- **Recommendation for our app:** adopt **Inter Display** app-wide (copy the 5
  woff2 + the `localFont` block). This is why the founder's font never visibly
  changed — Gilroy free only ships 300/800, so 400/500/600 body text silently fell
  back to Inter. Inter Display has all 5 weights → the change will actually show,
  and it matches the reference exactly. (If Gilroy is a hard brand requirement,
  source a full-weight Gilroy; otherwise Inter Display is the correct, faithful
  choice.)

---

## 2. HEADING / TYPOGRAPHY SYSTEM

Type scale is defined as Tailwind v4 `--text-*` tokens in `globals.css @theme`
(each token bundles size + line-height + letter-spacing + weight). Use the class,
never raw px. Weights map to the 5 Inter Display cuts.

| class            | size            | weight | use |
|------------------|-----------------|--------|-----|
| `text-h1`        | 6rem            | 300    | hero numbers |
| `text-h2`        | 3.75rem         | 500    | big KPI values (e.g. "256k") |
| `text-h3`        | 3rem            | 500    | KPI mobile |
| `text-h4`        | 2rem            | 600    | **PAGE TITLE** (in Header) |
| `text-h5`        | 1.5rem          | 500    | page title @ mobile, section |
| `text-h6`        | 1.25rem         | 600    | **CARD TITLE** |
| `text-sub-title-1` | 1rem          | 600    | row name / emphasis |
| `text-sub-title-2` | 0.875rem      | 700    | small emphasis |
| `text-body-1`    | 1rem            | 400    | body (set on `<body>`) |
| `text-body-2`    | 0.875rem        | 400    | table cells, inputs, secondary |
| `text-button`    | 0.875rem        | 600    | buttons, nav links, tabs, labels |
| `text-caption`   | 0.75rem         | 400    | meta, captions, table TH |
| `text-overline`  | 0.625rem        | 500    | tiny uppercase |

### THE NO-SUBTITLE HEADING PATTERN (founder hard rule — verified)
**There is NO PageHeader-with-subtitle component anywhere in the kit.** The page
title is rendered ONLY as a plain string in the top Header bar:
`components/Header/index.tsx` → `<div className="mr-auto text-h4 max-lg:text-h5 max-md:hidden">{title}</div>`.
You pass it via `<Layout title="...">`. No description/subtitle line exists below
any heading. Inside content, sections are titled by **Card** `title` (`text-h6`),
again with no subtitle. → To match: strip every PageHeader subtitle in our app;
move the page name into the Header `title`; use `text-h6` card titles.

---

## 3. COLOR TOKENS / THEME (light + dark)

All in `app/globals.css`. Pattern: raw palette → semantic CSS vars (overridden
under `[data-theme="dark"]`) → exposed to Tailwind as `--color-*` in `@theme`.
**Never use raw hex in components — always the semantic Tailwind class.**

**Raw palette:** `--shade-01..10` (#141414 darkest → #fdfdfd lightest);
accents `--primary-01 #2a85ff` (blue), `-02 #00a656` (green), `-03 #ff381c` (red),
`-04 #7f5fff` (purple), `-05 #ff9d34` (orange); pastel `--secondary-01..05`;
`--accent #f52495` (pink).

**Semantic tokens → Tailwind class** (these are what you write in JSX):
- Backgrounds: `bg-b-surface1` (app bg), `bg-b-surface2` (card/surface),
  `bg-b-pop`, `bg-b-dark1/2`, `bg-b-primary`, `bg-b-highlight`, `bg-b-depth/2`.
- Text: `text-t-primary`, `text-t-secondary`, `text-t-tertiary`, `text-t-light`,
  `text-t-blue`.
- Strokes/borders: `border-s-stroke2`, `border-s-subtle`, `border-s-focus`,
  `border-s-highlight`; fills mirror via `fill-t-*`.
- Charts: `chart-green/purple/yellow`; status label helpers (see §4).
- **Default border width is 1.5px** (`--default-border-width: 1.5px`), `border-1`
  = 1px. Radii lean large: `rounded-3xl` (1.5rem) for buttons/inputs,
  `rounded-4xl` (2rem, custom) for cards, `rounded-full` for pills/avatars.

**Dark mode** flips every semantic var under `[data-theme="dark"]` (surfaces go
shade-02/03/04, text inverts, gradients/shadows swap). Components are written
once with semantic classes + occasional `dark:` overrides for gradient buttons.

**Shadows** are tokenized: `shadow-depth`, `shadow-widget`, `shadow-depth-toggle`,
`shadow-depth-menu`, `shadow-dropdown`, `shadow-input-typing`, etc. (multi-layer,
premium). Cards use `shadow-widget`; dropdowns/modals `shadow-depth`/`shadow-dropdown`.

**Breakpoints (custom, mobile-first max-width style):** sm 480, md 767, lg 1023,
xl 1259, 2xl 1419, 3xl 1719, 4xl 1899. Code uses `max-md:`, `max-lg:`, `max-xl:`
heavily. Root font-size is fluid: `text-[calc(0.7rem+0.4vw)]`.

**Reusable CSS component classes** (in `globals.css @layer components`, apply
directly): `.card`, `.label` + `.label-green/red/yellow/gray` (status pills),
`.action` (icon+text row action), `.gradient-menu`, `.gradient-card`,
`.box-hover`, `.chart-tooltip`, plus styled `.custom-datepicker`.

---

## 4. SHELL / LAYOUT STRUCTURE (the app frame)

`components/Layout/index.tsx` is the page shell. Usage:
`<Layout title="Dashboard" [hideSidebar] [newProduct]> ...page... </Layout>`.

- **Left fixed Sidebar** width 21.25rem (`pl-85`, responsive `max-4xl:pl-70
  max-3xl:pl-60`, collapses off-canvas `max-xl:pl-0` with overlay + hamburger).
- **Fixed top Header** (`h-22`) spanning to the right of the sidebar; holds the
  page `title` (text-h4, hidden on mobile), global search, a black "Create"
  button, Notifications, Messages, User menu, mobile hamburger + logo.
- **Content** under header (`pt-22 pb-5`) inside `.center-with-sidebar`.
- A floating **ThemeButton** bottom-left when sidebar hidden.

**Sidebar** (`components/Sidebar/index.tsx`): Logo (top), scrollable nav built
from `contstants/navigation.tsx`, ThemeButton pinned bottom. Two nav item shapes:
flat (`NavLink`) and grouped (`Sidebar/Dropdown`, animated expand via
`react-animate-height`). Active state = a `gradient-menu` rounded pill behind the
link + `text-t-primary` (see `NavLink`); group children render with a connector
line. Items support `icon`, `counter` badge.

`contstants/navigation.tsx` exports `navigation` (sidebar) and `navigationUser`
(user-menu) arrays of `{title, icon, href | list[]}`. → Swap our routes here.

---

## 5. REUSABLE COMPONENT INVENTORY (path · renders · key props)

All under `components/<Name>/index.tsx`. Import alias `@/components/...`.

**Core / shell**
- `Layout` — page frame (see §4). props: `title`, `children`, `hideSidebar`, `newProduct`.
- `Sidebar`, `Sidebar/Dropdown`, `NavLink` — nav (see §4).
- `Header` (+ `Header/SearchGlobal`, `Header/User`, `Header/Notifications`,
  `Header/Messages`) — top bar.
- `Logo` — links to `/`, renders `public/images/logo-light.png` 48×48 (separate
  light/dark `<Image>`; **here both point to logo-light — swap to our HD logo**).
- `ThemeButton` — pill light/dark toggle (next-themes).
- `Icon` — `<Icon name fill className />` inline-SVG from the path dictionary.
- `Image` — thin wrapper over next/image with sane defaults.

**Surfaces / containers**
- `Card` — the standard panel. props: `title` (text-h6), `children`, optional
  `selectOptions/selectValue/selectOnChange` (renders a header `Select`),
  `headContent`. Uses `.card` (rounded-4xl, bg-b-surface2, shadow-widget).
- `Modal` — Headless Dialog. props: `open`, `onClose`, `children`,
  `isSlidePanel` (right side-panel vs centered). Backdrop + close button included.

**Forms / inputs**
- `Field` — labeled text input OR `textarea`; rounded-full input, hover/focus
  border, optional `innerLabel`, `tooltip`, `validated` (check icon),
  `handleForgotPassword`. props pass through native input/textarea attrs.
- `Select` — Headless Listbox dropdown. props: `value`, `onChange`, `options:
  {id,name}[]`, `label`, `tooltip`, `placeholder`, `isBlack`. Animated panel,
  selected dot. (`types/select.ts` = `SelectOption`.)
- `Search` — search input with leading search icon + clear button. props:
  `value`, `onChange`, `placeholder`, `isGray`, `onClear`.
- `Checkbox`, `Switch` (Headless, pill toggle), `Range` (react-slider),
  `DateAndTime` (react-datepicker), `Editor` (tiptap rich text),
  `Emoji` (picker), `FieldFiles` / `FieldImage` (upload dropzones),
  `Tabs` (pill segmented control: `items`, `value`, `setValue`, `isOnlyIcon`),
  `Filters`, `Dropdown` (menu variant, distinct from Sidebar/Dropdown).
- `Button` — one button to rule all. variants via boolean props: `isWhite`
  (surface), `isBlack` (gradient primary CTA), `isGray`, `isStroke` (outline),
  `isCircle` (icon-only round). `icon` prop, `as: "button"|"a"|"link"` (+`href`).
  h-12, rounded-3xl, text-button.

**Data display**
- `Table` — semantic `<table>` wrapper. props: `cellsThead` (the `<th>`s),
  `children` (rows), optional `selectAll`/`onSelectAll` (adds a checkbox column).
  Styling (TH caption color, cell padding, responsive hide) is baked in via
  arbitrary `[&_th]` selectors.
- `TableRow` — `<tr>` with hover, optional row-select checkbox + `box-hover`
  glow. props: `selectedRows` (bool), `onRowSelect`, `onClick`, `children` (the `<td>`s).
- `TableProductCell` — product avatar+name cell.
- `Percentage` — green/red delta pill with arrow. props: `value` (number, sign →
  color/arrow), `large`.
- `CardChartPie` — donut/pie card (recharts). Charts elsewhere use recharts
  `<Area/Bar/Line>` with the `.chart-tooltip` class.
- `Tooltip` (react-tooltip, styled `.react-tooltip`), `Spinner`,
  `Compatibility`, `CountryItem`, `Follower`, `LikeButton`, `Message`,
  `NewCustomers`, `PopularProducts`, `Product`, `ProductView`, `GridProduct`,
  `RefundRequests`, `ShareProduct`, `ShopItem`, `ScheduleProduct` — domain
  widget cards (e-commerce flavored; reuse as card scaffolds, reskin data).
- `NoFound` — **empty-state** block (big text-h4 title + suggestion pills). props:
  `title`. `DeleteItems` / `UnpublishItems` — bulk-action confirm bars.
- `Login` (+ `Login/SignIn`, `Login/CreateAccount`, `Login/ResetPassword`) —
  centered auth card with Google button + email form, toggles between modes.

**Hooks / types / mocks**
- `hooks/useSelection.ts` — table multi-select (selectedRows, selectAll,
  handleRowSelect, handleSelectAll, handleDeselect). Use for our list pages.
- `types/*` — `customer, product, comment, refund, promote, select, tabs`.
- `mocks/*` — sample data per page (swap for our API data).

---

## 6. PAGE TEMPLATES (file · layout · how it looks)

Templates live in `templates/<Page>/index.tsx`, mounted by `app/<route>/page.tsx`
(one-liner that renders the template). All wrapped in `<Layout title=...>`.

1. **Dashboard / overview (2-column)** — `templates/HomePage/index.tsx`.
   `flex` → `.col-left` (main, ~70%) stacked Cards (Overview KPIs, charts,
   slider, CTA) + `.col-right` (~30%) stacked widget cards (PopularProducts,
   Comments, RefundRequests). Looks: airy stacked rounded-4xl cards, big h2 KPI
   numbers with green/red Percentage pills, a segmented toggle inside the
   Overview card, period `Select` in card headers. **Best match for our
   dashboards / AI Manager command-center.**

2. **List + filter + bulk-select table** —
   `templates/Customers/CustomerList/CustomerListPage/index.tsx` (+ `List/`).
   One big `.card`: header row = card title + `Search` + `Tabs` (Active/New);
   when rows selected the header swaps to "N selected" + Deselect + Delete bar.
   Body = `Table`/`TableRow` with avatar+name cell, row hover-actions
   (Message/Detail/Ban), `Percentage`, pagination arrows; `NoFound` on empty
   search. Uses `useSelection`. **Best match for Leads/CRM/contacts/any table.**

3. **List + detail split (master-detail)** —
   `templates/Customers/CustomerList/DetailsPage/index.tsx`. One card split:
   left = searchable scrollable list of `Customer` rows; right = scrollable
   `Details` pane (profile, contacts, purchase history). Mobile collapses to one
   pane with back arrow. **Best match for CRM contact detail, conversations,
   AI Manager approvals/threads.**

4. **Settings (anchor-scroll sections)** — `templates/SettingsPage/index.tsx`.
   Left sticky `Menu` of sections (icon + title + description + `react-scroll`
   anchor) → right column of stacked section Cards (ProfileInformation, YourShop,
   Password, Notifications, Payment). **Best match for our settings / config /
   capabilities pages.**

5. **Create / edit form (2-column)** — `templates/Products/NewProductPage/index.tsx`.
   `<Layout newProduct>` (header shows Save-draft + publish Select instead of
   page title). Left wide column = form Cards (details, images, category,
   discussion); right column = side Cards (cover, files, price, highlights, CTA).
   **Best match for create-campaign / new-workflow / new-form builders.**

6. **Auth** — `components/Login/*` rendered on a minimal page (no sidebar). Centered
   text-h4 title, Google button, email fields, mode toggle. **Match for our /login.**

7. **Tabbed analytics overview** — `templates/Customers/OverviewPage/index.tsx`,
   `templates/Products/OverviewPage/index.tsx`, `templates/Income/*`,
   `templates/PromotePage/*` — grids of stat Cards + recharts (area/bar/pie),
   country lists, traffic channels. **Match for analytics / billing / reports.**

8. **Grid of cards** — `templates/Products/DraftsPage/Grid/index.tsx`,
   `templates/ExploreCreatorsPage` — responsive card grids with image + meta +
   actions. **Match for Funnels / Forms gallery / template pickers.**

9. **Empty state** — `components/NoFound` (see §5). **Match for every "no data" view.**

---

## 7. PORTING NOTES FOR OUR APP

- Our `famit-panel` ALREADY uses this token vocabulary in `app/globals.css`
  (`b-surface*`, `t-primary`, `s-stroke2`, `text-h4`, etc.) and mirrored shell
  components (`components/Sidebar`, `NavLink`, `Sidebar/Dropdown`, `Logo`) — it
  was partly ported from the older `Core_2-Capsy-Dashboard`. Reconcile against
  THIS newer kit (authoritative for look).
- Action items implied: (1) swap font to Inter Display app-wide; (2) move page
  titles into `<Layout title>` / Header `text-h4` and DELETE all PageHeader
  subtitles; (3) replace bespoke/jargon pages with the matching template above
  (dashboard→#1, leads/CRM list→#2, CRM detail→#3, settings/capabilities→#4,
  create-campaign/workflow/forms→#5, login→#6, analytics/billing→#7); (4) point
  `Logo` light+dark at our real HD logo; (5) keep raw hex out — use semantic
  tokens; (6) simplify AI Manager into the 2-column dashboard + master-detail
  patterns instead of many dense pages.
