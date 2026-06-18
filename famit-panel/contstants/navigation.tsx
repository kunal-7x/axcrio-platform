// Sidebar navigation (premium-ui "Signal").
//
// TWO kinds of entries:
//   • A LINK         -> `{ title, icon, href }`  (rendered by NavLink)
//   • A COLLAPSIBLE GROUP -> `{ title, icon, list:[...] }` (rendered by Sidebar/Dropdown).
//     Click the parent -> it EXPANDS to its children (same mechanism the Billing
//     group has always used). The whole rail now reads as organized sections.
//
// W15 INFORMATION ARCHITECTURE (design/W15-UI-IA-PLAN.md §2) — the SCATTER KILL.
// The same concern used to live in 2–4 places (calls in 4 surfaces, lead scores in
// 3, analytics in 2, money in 6, AI-Manager as 9 dead-redirect children). W15
// consolidates to ONE obvious home per concern and regroups the rail into plain
// task language:
//
//   WORK          — Dashboard, Leads & CRM, Call Logs (Callbacks=tab), Bookings, AI Manager
//   GROW          — Campaigns, Run, Creative Studio, Ad Automation, Funnels, Form Builder
//   MESSAGE       — WhatsApp (Communication folds in as channel tabs), Customer Support
//   INTELLIGENCE  — Reports (=/analytics, the deep drill-down), Knowledge Base
//   MONEY         — Billing (tabbed hub: Overview/Vendor Costs/Spending/Audit/Plan), Payments
//   BUILD         — Workflows, Webhooks, Integrations
//   SETTINGS      — (navigationUser footer) Settings + Do-Not-Call + Vendors(admin) as sections
//   SUPER ADMIN   — admin-only control plane (UNCHANGED, role-gated)
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
        // the bookings + the inbound brain. Everything you DO lives here so the
        // operator stops hopping between Command/Sell/Engage. The GROUP is UNKEYED so
        // the core Dashboard can never be hidden; per-child keys preserve the old
        // sell.* / engage.* / mod.ai_manager gates verbatim.
        title: "Work",
        icon: "grid",
        list: [
            // CORE — Dashboard (the consolidated Today-first cockpit). UNKEYED.
            { title: "Dashboard", href: "/" },
            // Leads & CRM — ONE people-surface. /leads folds in as a "Dialing queue"
            // tab inside /crm; the CRM link is the home. Keep BOTH keys live so an
            // entitlement that hides either page still resolves (the page self-gates).
            { title: "Leads & CRM", href: "/crm", feature_key: "sell.crm" },
            // Call Logs — ONE call surface. /callbacks folds in as a "Callbacks" tab.
            { title: "Call Logs", href: "/calls", feature_key: "engage.calls" },
            { title: "Bookings", href: "/booking", feature_key: "engage.booking" },
            // AI Manager — collapsed from 9 sidebar children to ONE link; the page
            // owns Overview/Live/Handoff/Try-it/Commands/Approvals/Capabilities/Setup/
            // Team as in-page tabs. Manager-gated; the group key rides the link so the
            // whole inbound-command surface hides/locks as one entitlement.
            { title: "AI Manager", href: "/ai-manager", roles: "manager", feature_key: "mod.ai_manager" },
        ],
    },
    {
        // GROW — acquisition: turn ad spend + audiences into dialled leads. Campaigns
        // and Run sit together (build the campaign, then run it), with the Creative
        // Studio design engine and the ad/funnel/form tools. Group UNKEYED (mixed core
        // + keyed children); each child keeps its grow.* / engage.run key verbatim.
        title: "Grow",
        icon: "promote",
        feature_key: "mod.grow",
        list: [
            { title: "Campaigns", href: "/campaigns", feature_key: "grow.campaigns" },
            // Run — the founder's named multi-card audience+config launcher. Lives in
            // GROW next to Campaigns (build → run) instead of buried in the old Engage.
            { title: "Run", href: "/run", feature_key: "engage.run" },
            // Creative Studio — the campaign-aware AI design engine. Promoted to a
            // single link; Studio/Video/Library/Brand are in-page tabs of /creative.
            // (Was its own 4-child group; the sub-pages remain real routes.)
            { title: "Creative Studio", href: "/creative" },
            { title: "Ad Automation", href: "/ads", roles: "manager", feature_key: "grow.ads" },
            { title: "Funnels", href: "/funnels", feature_key: "grow.funnels" },
            { title: "Form Builder", href: "/forms", feature_key: "grow.forms" },
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
            { title: "Customer Support", href: "/support", feature_key: "engage.support" },
        ],
    },
    {
        // INTELLIGENCE — where the data turns into decisions. Reports (=/analytics) is
        // now the DEEP drill-down the Dashboard links INTO (the Dashboard owns the
        // consolidated top-line analytics). Knowledge Base sits alongside. The old
        // standalone "Analytics" label becomes "Reports". Keys preserved verbatim.
        title: "Intelligence",
        icon: "chart",
        feature_key: "mod.intelligence",
        list: [
            { title: "Reports", href: "/analytics", feature_key: "intelligence.analytics" },
            { title: "Knowledge Base", href: "/knowledge", feature_key: "intelligence.knowledge" },
        ],
    },
    {
        // MONEY — the whole money story. Billing is the hub (Overview/Vendor Costs/
        // Spending/Audit/Plan as tabs); Payments is the collections page. The GROUP is
        // intentionally UNKEYED: Money contains the CORE Billing surface
        // (money.billing, is_core), so hiding the module must NEVER drop Billing. Only
        // the non-core Payments child carries a key. All /billing/* children map to the
        // single core money.billing page → left UNKEYED (never hidden).
        title: "Money",
        icon: "wallet",
        list: [
            { title: "Billing Overview", href: "/billing/overview" },
            { title: "Vendor Costs", href: "/billing/vendors" },
            { title: "Spending", href: "/billing/explorer" },
            { title: "Audit", href: "/billing/audit" },
            { title: "Plan", href: "/billing/plan" },
            { title: "Payments", href: "/payments", roles: "manager", feature_key: "money.payments" },
        ],
    },
    {
        // BUILD — automation + the connector substrate. Workflow orchestration,
        // outbound webhooks, and the universal provider/connector registry. Group
        // UNKEYED (mixed); per-child keys (automate.* / integrations.providers)
        // preserved verbatim. (Was the old "Automate" group + the loose Integrations.)
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
        ],
    },
    {
        // SUPER ADMIN — the Control Center (CL-F1, design/control-ui.md §1). The
        // founder/super-admin's tier-0 admin plane: fleet command, per-vendor
        // workspaces, entitlement flags, plans, fleet usage and the immutable
        // control-audit. The WHOLE group is `roles:"admin"` so resolveNav drops it for
        // every vendor (a vendor never receives this group in their nav tree). Each
        // child also carries `roles:"admin"` for defense-in-depth. COSMETIC ONLY — the
        // backend require_super_admin (which EXCLUDES the legacy static-password auth,
        // the #1 security finding) is the real boundary; HIDDEN=404 / LOCKED=402 /
        // unknown=DENY, fail-closed. UNCHANGED by W15 (out of consolidation scope).
        title: "Super Admin",
        icon: "lock",
        roles: "admin",
        list: [
            { title: "Control Overview", href: "/super-admin", roles: "admin" },
            { title: "Vendors", href: "/super-admin/vendors", roles: "admin" },
            { title: "Feature Flags", href: "/super-admin/flags", roles: "admin" },
            { title: "Plans", href: "/super-admin/plans", roles: "admin" },
            { title: "Usage Analytics", href: "/super-admin/usage", roles: "admin" },
            { title: "Audit Logs", href: "/super-admin/audit", roles: "admin" },
            { title: "Integrations", href: "/super-admin/integrations", roles: "admin" },
        ],
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
    { title: "Settings", icon: "edit-profile", href: "/settings" },
    { title: "Do-Not-Call", icon: "profile", href: "/suppression", feature_key: "foundation.suppression" },
    { title: "Vendors", icon: "wallet", href: "/vendors", roles: "admin" },
];
