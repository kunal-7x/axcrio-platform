// Sidebar navigation (premium-ui "Signal").
//
// TWO kinds of entries:
//   • A LINK         -> `{ title, icon, href }`  (rendered by NavLink)
//   • A COLLAPSIBLE GROUP -> `{ title, icon, list:[...] }` (rendered by Sidebar/Dropdown).
//     Click the parent -> it EXPANDS to its children (same mechanism the Billing
//     group has always used). The whole rail now reads as organized sections.
//
// INFORMATION ARCHITECTURE — the canonical 8-section IA from
// `MASTER_PLATFORM_ROADMAP.md §0a` (P5 = "the §7 sidebar regroup"). Every section
// is a collapsible parent (no `href` + a `list`). The regroup is NON-BREAKING by
// construction: every previously-live route is absorbed verbatim into a section —
// no live page is orphaned, no href is rewritten. The new module pages (built this
// wave: ai-manager, ads, funnels, forms, crm, support, booking, workflows,
// payments) slot into their roadmap section alongside the routes they extend.
//
//   A Command      — Dashboard, AI Manager
//   B Grow         — Campaigns, Ad Automation, Funnels, Form Builder
//   C Sell         — Leads, CRM
//   D Engage       — Run, Call Logs, Callbacks, WhatsApp, Customer Support, Booking
//   E Automate     — Workflows, Webhooks
//   F Money        — Payments, Billing (Overview/Vendor Costs/Spending/Audit/Plan)
//   G Intelligence — Analytics
//   H Foundation   — Do-Not-Call (Compliance), Vendors (Admin)
//
// W1 nav cleanup (design/ui-design-principles.md jargon glossary): plain-language
// labels (Test Console→Try it, Authorized Users→Team, Cost Explorer→Spending,
// Plan & Ledger→Plan, Run a Campaign→Run, billing Vendors→Vendor Costs to
// de-dupe vs the admin Vendors page) and the unbuilt "Create Studio" coming-soon
// stub group removed entirely.
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
// dimmed, non-clickable row with a "Soon" pill (NOT a <Link>, so it can never
// 404). Used for the "Create Studio" group — the pages are intentionally NOT built.
//
// CL-F0 — `feature_key` (CONTROL LAYER): every module GROUP carries its module
// registry key and every CHILD carries its page key (the SAME keys the backend
// /me/entitlements `modes` map uses, mirrored 1:1 from lib/api.ts FEATURE_REGISTRY
// — keep them in lockstep). `components/Sidebar/index.tsx resolveNav` reads these:
// a key resolving to HIDE drops the entry, LOCK dims it ("Locked" pill); a group
// whose module key is HIDE drops the whole section. Keys are AUTHORED here (not
// derived at runtime) so the static nav stays a plain data module. CORE surfaces
// stay UNKEYED so they can never be hidden: Command/Dashboard, the Billing
// children + Settings (core), and the whole admin-only "Super Admin" group
// (role-gated, never entitlement-gated). The vendor `/me/entitlements` map is the
// authoritative key list; this is the cosmetic mirror — the backend 404/402 is the
// real boundary.
export const navigation = [
    {
        // A — Command. The operator's command layer. Dashboard lives here (per
        // roadmap §0a) so the section is ALWAYS present — even for a read-only
        // agent who can't see the manager-gated AI Manager child. CORE module —
        // intentionally UNKEYED (command/dashboard can never be hidden).
        title: "Command",
        icon: "grid",
        list: [
            { title: "Dashboard", href: "/" },
        ],
    },
    {
        // A2 — AI Manager. Promoted from a single Command link to its own
        // collapsible section (master AI-Manager spec §1): the voice/chat command
        // center is now a multi-route surface, so each sub-page is a child here.
        // The whole group is manager-gated (read-only agents never see it); every
        // page additionally self-gates writes (canWrite) + is firewall-gated
        // server-side. Routes that 404 today degrade to a premium dormant view, so
        // no child can land on an error wall. Sub-pages owned across F-waves:
        // Overview / Test Console (F1), Command History / Approvals / Capabilities
        // (F3), Setup / Authorized Users (F2). NOTE: no `href` on the group — the
        // Sidebar renders an entry WITH an href as a flat NavLink (hiding the
        // children); a group needs `list` + NO `href` to collapse. /ai-manager
        // itself redirects to Overview, which is the first child here.
        title: "AI Manager",
        icon: "chat-think",
        roles: "manager",
        feature_key: "mod.ai_manager",
        list: [
            { title: "Overview", href: "/ai-manager/overview", feature_key: "ai_manager.overview" },
            { title: "Live Calls", href: "/ai-manager/live" },
            { title: "Handoff Team", href: "/ai-manager/handoff" },
            { title: "Try it", href: "/ai-manager/test", feature_key: "ai_manager.test" },
            { title: "Command History", href: "/ai-manager/commands", feature_key: "ai_manager.commands" },
            { title: "Pending Approvals", href: "/ai-manager/approvals", feature_key: "ai_manager.approvals" },
            { title: "Capabilities", href: "/ai-manager/capabilities", feature_key: "ai_manager.capabilities" },
            { title: "Setup", href: "/ai-manager/setup", feature_key: "ai_manager.setup" },
            { title: "Team", href: "/ai-manager/users", feature_key: "ai_manager.users" },
        ],
    },
    {
        // B — Grow (Marketing). Acquisition: campaigns, ads, funnels, forms.
        title: "Grow",
        icon: "promote",
        feature_key: "mod.grow",
        list: [
            { title: "Campaigns", href: "/campaigns", feature_key: "grow.campaigns" },
            { title: "Ad Automation", href: "/ads", roles: "manager", feature_key: "grow.ads" },
            { title: "Funnels", href: "/funnels", feature_key: "grow.funnels" },
            { title: "Form Builder", href: "/forms", feature_key: "grow.forms" },
        ],
    },
    {
        // B2 — Creative Studio. The campaign-aware AI design engine (AI designer +
        // copywriter + ad strategist): tell it what you need, watch angle-labelled
        // banners stream in, pick / edit / approve / reuse everywhere. Three plain-
        // noun children (cs-workspace §1): Studio (create), Library (the reusable
        // store), Brand Kit (the look the AI honours). The whole surface is dormant-
        // safe behind GET /api/assets/status — every page renders a calm coming-soon
        // card when AIASSET_ENABLED is off for the tenant, never an error wall.
        title: "Creative Studio",
        icon: "magic-pencil",
        list: [
            { title: "Studio", href: "/creative" },
            // Video Studio — the campaign-aware AI video engine (composite-cheap by
            // default + AI-motion tiers). Dormant-safe behind the studio probe; the
            // whole /creative/video surface 404s when FEATURE_VIDEO_STUDIO is OFF.
            { title: "Video Studio", href: "/creative/video" },
            { title: "Library", href: "/creative/library" },
            { title: "Brand Kit", href: "/creative/brand" },
        ],
    },
    {
        // C — Sell (Revenue). The system of record.
        title: "Sell",
        icon: "usd-circle",
        feature_key: "mod.sell",
        list: [
            { title: "Leads", href: "/leads", feature_key: "sell.leads" },
            { title: "CRM", href: "/crm", feature_key: "sell.crm" },
        ],
    },
    {
        // D — Engage (Conversations). Everything that talks to a customer.
        title: "Engage",
        icon: "chat",
        feature_key: "mod.engage",
        list: [
            { title: "Run", href: "/run", feature_key: "engage.run" },
            { title: "Call Logs", href: "/calls", feature_key: "engage.calls" },
            { title: "Callbacks", href: "/callbacks", feature_key: "engage.callbacks" },
            { title: "WhatsApp", href: "/whatsapp", roles: "manager", feature_key: "engage.whatsapp" },
            { title: "Customer Support", href: "/support", feature_key: "engage.support" },
            { title: "Booking", href: "/booking", feature_key: "engage.booking" },
        ],
    },
    {
        // E — Automate. Workflow orchestration + outbound integrations.
        title: "Automate",
        icon: "layers",
        feature_key: "mod.automate",
        list: [
            { title: "Workflows", href: "/workflows", feature_key: "automate.workflows" },
            { title: "Webhooks", href: "/webhooks", roles: "manager", feature_key: "automate.webhooks" },
            // Universal Provider / Connector registry — add any AI model + key,
            // self-host a model, or wire a tool, all from the UI. Video Studio is
            // its first consumer. Manager-gated (BYO-key is spend-sensitive).
            { title: "Integrations", href: "/integrations", roles: "manager", feature_key: "integrations.providers" },
        ],
    },
    {
        // F — Money. Collections + the vendor-cost billing surface. The GROUP is
        // intentionally UNKEYED: the Money module contains the CORE Billing surface
        // (money.billing, is_core), so hiding the module must NEVER drop Billing.
        // Only the non-core Payments child carries a key. All /billing/* children
        // map to the single core money.billing page → left UNKEYED (never hidden).
        title: "Money",
        icon: "wallet",
        list: [
            { title: "Payments", href: "/payments", roles: "manager", feature_key: "money.payments" },
            { title: "Billing Overview", href: "/billing/overview" },
            { title: "Vendor Costs", href: "/billing/vendors" },
            { title: "Spending", href: "/billing/explorer" },
            { title: "Audit", href: "/billing/audit" },
            { title: "Plan", href: "/billing/plan" },
        ],
    },
    {
        // G — Intelligence. Where the data turns into decisions.
        title: "Intelligence",
        icon: "chart",
        feature_key: "mod.intelligence",
        list: [
            { title: "Analytics", href: "/analytics", feature_key: "intelligence.analytics" },
            { title: "Knowledge Base", href: "/knowledge", feature_key: "intelligence.knowledge" },
        ],
    },
    {
        // H — Foundation. Operator-facing config of the foundational systems. The
        // GROUP is UNKEYED: foundation is a CORE module (foundation.settings core)
        // → never entitlement-hidden. Only the non-core Do-Not-Call child carries a
        // key; the admin "Vendors" page is role-gated (admin), not entitlement-gated.
        title: "Foundation",
        icon: "profile",
        list: [
            { title: "Do-Not-Call", href: "/suppression", feature_key: "foundation.suppression" },
            { title: "Vendors", href: "/vendors", roles: "admin" },
        ],
    },
    {
        // SUPER ADMIN — the Control Center (CL-F1, design/control-ui.md §1). The
        // founder/super-admin's tier-0 admin plane: fleet command, per-vendor
        // workspaces, entitlement flags, plans, fleet usage and the immutable
        // control-audit. The WHOLE group is `roles:"admin"` so resolveNav drops
        // it for every vendor (a vendor never receives this group in their nav
        // tree). Each child also carries `roles:"admin"` for defense-in-depth.
        // COSMETIC ONLY — the backend require_super_admin (which EXCLUDES the
        // legacy static-password auth, the #1 security finding) is the real
        // boundary; HIDDEN=404 / LOCKED=402 / unknown=DENY, fail-closed.
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

export const navigationUser = [
    {
        title: "Settings",
        icon: "edit-profile",
        href: "/settings",
    },
];
