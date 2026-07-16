// Sidebar navigation (premium-ui "Signal").
//
// TWO kinds of entries:
//   • A LINK         -> `{ title, icon, href }`  (rendered by NavLink)
//   • A COLLAPSIBLE GROUP -> `{ title, icon, list:[...] }` (rendered by Sidebar/Dropdown).
//     Click the parent -> it EXPANDS to its children (same mechanism the Billing
//     group has always used). The whole rail now reads as organized sections.
//
// ROUND-2 INFORMATION ARCHITECTURE — the founder's second-pass consolidation on top
// of W15. The rail collapses tab-owning hubs to SINGLE links (the page's own tabs own
// the sub-routes), promotes Creative Studio to its own section, retires the thin
// Intelligence section (its two pages rehome to Work + Build), and groups the ad
// tooling together inside Grow:
//
//   WORK          — Dashboard, Leads & CRM, Leads, Call Logs (Callbacks+DNC=tabs),
//                   Bookings, AI Manager (single link), Reports (=/analytics)
//   GROW          — Campaigns, Run Campaign, [Ad Tools cluster: Ad Automation,
//                   Funnels, Form Builder]
//   CREATIVE STUDIO — Image, Video, Library, Brand Kit (own top-level section)
//   MESSAGE       — WhatsApp (Communication folds in as channel tabs), Customer Support
//   MONEY         — single link → /billing/overview (the billing page is the tabbed
//                   hub: Overview/Vendors/Spending/Plan/Audit/Payments)
//   BUILD         — Workflows, Webhooks, Integrations, Knowledge Base
//   SETTINGS      — (navigationUser footer) Settings + Do-Not-Call + Vendors(admin)
//   SUPER ADMIN   — single link → /super-admin (AdminHeader tabs own the sub-routes)
//
// (Intelligence section REMOVED: Reports → Work, Knowledge Base → Build. Standalone
//  Callbacks rail child RETIRED: it is a calls-page tab. AI-Manager / Super-Admin /
//  Money collapse from multi-child groups to one link each.)
//
// NON-BREAKING by construction: every previously-live route still resolves. The
// folded routes (Callbacks, Communication, the AI-Manager sub-pages, the
// Do-Not-Call / admin-Vendors pages) survive as real routes reachable via an
// in-page tab or a grouped Settings/utility section — no live page is orphaned,
// no href is rewritten. We only change WHERE the rail points and the GROUPING.
//
// `roles` (optional) gates an entry by the current user's role:
//   "admin"   -> only admins see it
//   "manager" -> managers + admins see it (hidden for read-only agents)
//   (no roles -> everyone)
// `roles` works on TOP-LEVEL entries AND on individual `list` CHILDREN. The
// Sidebar filters children by role and HIDES a group that has no visible
// children left, so a read-only agent never sees a manager link and a vendor
// never sees the admin-only Vendors page — even inside a collapsible group.
// Module PAGES self-gate every write (canWrite = admin|manager), so READ access
// stays broad; only spend/command-sensitive entries carry a `manager` nav gate.
//
// `comingSoon: true` on a child marks a FUTURE feature: Dropdown renders it as a
// dimmed, non-clickable row with a "Soon" pill (NOT a <Link>, so it can never 404).
//
// CL-F0 — `feature_key` (CONTROL LAYER): every module GROUP carries its module
// registry key and every CHILD carries its page key (the SAME keys the backend
// /me/entitlements `modes` map uses, mirrored 1:1 from lib/api.ts FEATURE_REGISTRY
// — keep them in lockstep). `components/Sidebar/index.tsx resolveNav` reads these:
// a key resolving to HIDE drops the entry, LOCK dims it ("Locked" pill); a group
// whose module key is HIDE drops the whole section. Keys are AUTHORED here (not
// derived at runtime) so the static nav stays a plain data module. CORE surfaces
// stay UNKEYED so they can never be hidden: WORK/Dashboard, the Billing children +
// Settings (core), and the whole admin-only "Super Admin" group (role-gated, never
// entitlement-gated). The vendor `/me/entitlements` map is the authoritative key
// list; this is the cosmetic mirror — the backend 404/402 is the real boundary.
//
// W15 NOTE — keys are PRESERVED VERBATIM through the regroup: the module GROUP keys
// (mod.grow / mod.sell / mod.engage / mod.automate / mod.intelligence / mod.ai_manager)
// move WITH their children to the new task-group they live under. A child keeps the
// SAME feature_key it always had regardless of which visual section now hosts it
// (the key gates the PAGE, not the rail group). AI-Manager collapses from 9 children
// to a single link — its in-page tabs (Overview/Live/Handoff/Try-it/Commands/
// Approvals/Capabilities/Setup/Team) own the sub-routes now; the group key
// `mod.ai_manager` rides the single link so the whole surface still hides/locks as
// one entitlement.
export const navigation = [
    {
        // WORK — the daily operating surface: the cockpit + the people + the calls +
        // the bookings + the inbound brain + the deep Reports drill-down. Everything
        // you DO + measure lives here. The GROUP is UNKEYED so the core Dashboard can
        // never be hidden; per-child keys preserve the old sell.* / engage.* /
        // mod.ai_manager / intelligence.* gates verbatim.
        title: "Work",
        icon: "grid",
        list: [
            // CORE — Dashboard (the consolidated Today-first cockpit). UNKEYED.
            { title: "Dashboard", href: "/" },
            // Auto Lead — real-time multi-source lead ingestion (replaces the dormant
            // "Leads & CRM"/Customer-360 entry). Connect WhatsApp / email / Meta+Google
            // ads / website + custom webhooks / Apollo → auto-import + validate + route
            // every lead to calling. Reuses the sell.crm entitlement key so it shows.
            { title: "Auto Lead", href: "/auto-lead", feature_key: "sell.crm" },
            // Sales CRM — the Twenty-powered relational pipeline (Companies / People /
            // drag-and-drop Opportunities) rendered NATIVELY in Haptica (no iframe).
            // Sits beside Customer 360: that surface is the call-driven timeline, this
            // one is the deal pipeline. Shares the sell.crm entitlement key so both lock
            // together; the page self-gates writes + shows its own "Connect" state.
            { title: "Sales CRM", href: "/crm/sales", feature_key: "sell.crm" },
            // Leads — RESTORED standalone people page (was folded into a CRM tab; the
            // standalone route is real on disk).
            { title: "Leads", href: "/leads", feature_key: "sell.leads" },
            // Call Logs — ONE call surface. The calls page owns Callbacks + Do-Not-Call
            // as in-page tabs now, so the standalone Callbacks rail child is RETIRED
            // (the route still resolves; it is just not duplicated in the rail).
            { title: "Call Logs", href: "/calls", feature_key: "engage.calls" },
            { title: "Bookings", href: "/booking", feature_key: "engage.booking" },
            // AI Manager — ROUND-2: collapsed to a SINGLE LINK. The page's own tabs
            // (Overview/Live/Command-Center/Handoff/Try-it/History/Approvals/
            // Capabilities/Setup/Team) own the sub-routes, so the 10-child group is
            // killed. The mod.ai_manager key rides the link so the whole surface still
            // hides/locks as one entitlement — and because a top-level LINK that
            // resolves to LOCK is NOT dropped by resolveNav (only HIDE drops it), the
            // link always opens the REAL /ai-manager page (no dead "coming soon" /
            // "Locked" non-clickable row; the page itself shows any upsell state).
            { title: "AI Manager", icon: "ai", href: "/ai-manager", roles: "manager", feature_key: "mod.ai_manager" },
            // Reports — the deep analytics drill-down. MOVED IN from the retired
            // Intelligence section. Key preserved verbatim.
            { title: "Reports", href: "/analytics", feature_key: "intelligence.analytics" },
        ],
    },
    {
        // GROW — acquisition: turn ad spend + audiences into dialled leads. Campaigns
        // and Run-Campaign sit together (build the campaign, then run it). The ad
        // tooling moved OUT into its own "Revenue Tools" section (below) so a
        // super-admin can hide it per-vendor. Creative Studio is its OWN top-level
        // section (further below). Group UNKEYED (mixed core + keyed children); each
        // child keeps its grow.* / engage.run key verbatim.
        title: "Grow",
        icon: "promote",
        feature_key: "mod.grow",
        list: [
            { title: "Campaigns", href: "/campaigns", feature_key: "grow.campaigns" },
            // Run Campaign — the founder's named multi-card audience+config launcher.
            // Lives in GROW next to Campaigns (build → run). Relabelled "Run Campaign".
            { title: "Run Campaign", href: "/run", feature_key: "engage.run" },
        ],
    },
    {
        // REVENUE TOOLS — the ad-acquisition cluster (Ad Automation + Funnels + Form
        // Builder) promoted out of Grow into its OWN top-level section. The whole
        // group carries `feature_key:"mod.revenue_tools"` so a SUPER-ADMIN can
        // HIDE/LOCK it for a vendor that shouldn't see the ad tooling: when the
        // backend /me/entitlements resolves mod.revenue_tools → HIDE, resolveNav
        // drops the entire section (the same mechanism every keyed group uses).
        // Each child KEEPS its original page key (grow.ads / grow.funnels /
        // grow.forms) so per-page entitlements still gate individually. Ad
        // Automation stays `roles:"manager"` (spend-sensitive). BACKEND DEPENDENCY:
        // the module-level HIDE/LOCK needs the backend entitlement map to register
        // `mod.revenue_tools`; until then the group hides only when all three child
        // page-keys are hidden (which the backend already supports).
        title: "Revenue Tools",
        icon: "income",
        feature_key: "mod.revenue_tools",
        list: [
            { title: "Ad Automation", href: "/ads", roles: "manager", feature_key: "grow.ads" },
            { title: "Funnels", href: "/funnels", feature_key: "grow.funnels" },
            { title: "Form Builder", href: "/forms", feature_key: "grow.forms" },
        ],
    },
    {
        // CREATIVE STUDIO — ROUND-2: promoted to its OWN top-level section (was a
        // collapsible child of Grow). The campaign-aware AI design engine, exposing all
        // four REAL routes relabelled per spec: Image / Video / Library / Brand Kit.
        // UNKEYED group (no module gate authored for the suite) so it is always visible;
        // each page self-gates its writes.
        // ICON FIX — was `icon:"image"`, which is NOT a key in the Icon registry
        // (components/Icon) → `icons["image"]` is undefined → empty <path> → the
        // Creative Studio glyph rendered BLANK in the rail. `magic-pencil` (the AI
        // design wand) is a real registry key and reads as the AI creative engine.
        title: "Creative Studio",
        icon: "magic-pencil",
        list: [
            { title: "Image", href: "/creative" },
            { title: "Video", href: "/creative/video" },
            { title: "Library", href: "/creative/library" },
            { title: "Brand Kit", href: "/creative/brand" },
        ],
    },
    {
        // MESSAGE — every channel that talks to a customer outside the call. WhatsApp
        // is the home; Communication (Telegram/Email/SMS-soon) folds in as channel
        // tabs of /whatsapp. Customer Support shares the section. Group UNKEYED (mixed
        // core support + keyed channels); per-child keys preserved verbatim.
        title: "Message",
        icon: "chat",
        feature_key: "mod.engage",
        list: [
            { title: "WhatsApp", href: "/whatsapp", roles: "manager", feature_key: "engage.whatsapp" },
            // Communication — RESTORED standalone multi-channel page (W15 dropped it
            // with no replacement entry; the page is real on disk).
            { title: "Communication", href: "/communication", feature_key: "engage.communication" },
            { title: "Customer Support", href: "/support", feature_key: "engage.support" },
        ],
    },
    {
        // MONEY — ROUND-2: collapsed to a SINGLE LINK. The billing page is a tabbed hub
        // (Overview / Vendors / Spending / Plan / Audit / Payments — §1b adds Payments
        // to BILLING_TABS), so the rail no longer enumerates the children. The link
        // lands on /billing/overview. UNKEYED so the CORE billing surface can never be
        // hidden by an entitlement (Payments hides/locks at the in-page tab + the
        // backend 404/402, not the rail).
        title: "Money",
        icon: "wallet",
        href: "/billing/overview",
    },
    {
        // BUILD — automation + the connector substrate + the knowledge brain. Workflow
        // orchestration, outbound webhooks, the universal provider/connector registry,
        // and (ROUND-2: moved in from the retired Intelligence section) the Knowledge
        // Base. Group UNKEYED (mixed); per-child keys (automate.* / integrations.* /
        // intelligence.knowledge) preserved verbatim.
        title: "Build",
        icon: "layers",
        feature_key: "mod.automate",
        list: [
            { title: "Workflows", href: "/workflows", feature_key: "automate.workflows" },
            { title: "Webhooks", href: "/webhooks", roles: "manager", feature_key: "automate.webhooks" },
            // Universal Provider / Connector registry — add any AI model + key,
            // self-host a model, or wire a tool, all from the UI. Manager-gated
            // (BYO-key is spend-sensitive).
            { title: "Integrations", href: "/integrations", roles: "manager", feature_key: "integrations.providers" },
            // Knowledge Base — MOVED in from Intelligence (now retired). Key verbatim.
            { title: "Knowledge Base", href: "/knowledge", feature_key: "intelligence.knowledge" },
        ],
    },
    {
        // SUPER ADMIN — ROUND-2: collapsed to a SINGLE LINK. The control plane page
        // renders its own sub-nav via AdminHeader (Overview/Vendors/Flags/Plans/Usage/
        // Audit/API-Keys/Integrations as in-page tabs), so the 8-child rail group is
        // killed. The whole entry is `roles:"admin"` so resolveNav drops it for every
        // vendor (a vendor never receives it). COSMETIC ONLY — the backend
        // require_super_admin (which EXCLUDES the legacy static-password auth, the #1
        // security finding) is the real boundary; HIDDEN=404 / LOCKED=402 / unknown=DENY,
        // fail-closed. The link lands on /super-admin (Control Overview).
        title: "Super Admin",
        icon: "lock",
        href: "/super-admin",
        roles: "admin",
    },
];

// SETTINGS (footer, navigationUser — the avatar dropdown). FLAT links only:
// `components/Header/User` maps each as `{title, icon, href}`. W15 folds the thin
// "Foundation" group (Do-Not-Call + admin Vendors) IN HERE as additional footer
// links so those 1–2-item groups stop cluttering the main rail, while the routes
// stay reachable (no orphan). Keys/roles preserved verbatim: Do-Not-Call keeps
// `foundation.suppression`; admin Vendors keeps `roles:"admin"` (the User menu does
// not role-filter, but the page itself is admin-gated server-side + the rail-level
// gate is preserved for parity). Settings remains the home.
export const navigationUser = [
    { title: "Profile", icon: "profile", href: "/profile" },
    { title: "Settings", icon: "edit-profile", href: "/settings" },
    { title: "Do-Not-Call", icon: "profile", href: "/suppression", feature_key: "foundation.suppression" },
    { title: "Vendors", icon: "wallet", href: "/vendors", roles: "admin" },
];
