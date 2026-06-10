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
//   F Money        — Payments, Billing (Overview/Vendors/Cost Explorer/Audit/Plan)
//   G Intelligence — Analytics
//   H Foundation   — Do-Not-Call (Compliance), Vendors (Admin)
//   + Create Studio (coming-soon) is preserved as a dimmed roadmap group.
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
export const navigation = [
    {
        // A — Command. The operator's command layer. Dashboard lives here (per
        // roadmap §0a) so the section is ALWAYS present — even for a read-only
        // agent who can't see the manager-gated AI Manager child.
        title: "Command",
        icon: "grid",
        list: [
            { title: "Dashboard", href: "/" },
            { title: "AI Manager", href: "/ai-manager", roles: "manager" },
        ],
    },
    {
        // B — Grow (Marketing). Acquisition: campaigns, ads, funnels, forms.
        title: "Grow",
        icon: "promote",
        list: [
            { title: "Campaigns", href: "/campaigns" },
            { title: "Ad Automation", href: "/ads", roles: "manager" },
            { title: "Funnels", href: "/funnels" },
            { title: "Form Builder", href: "/forms" },
        ],
    },
    {
        // C — Sell (Revenue). The system of record.
        title: "Sell",
        icon: "usd-circle",
        list: [
            { title: "Leads", href: "/leads" },
            { title: "CRM", href: "/crm" },
        ],
    },
    {
        // D — Engage (Conversations). Everything that talks to a customer.
        title: "Engage",
        icon: "chat",
        list: [
            { title: "Run a Campaign", href: "/run" },
            { title: "Call Logs", href: "/calls" },
            { title: "Callbacks", href: "/callbacks" },
            { title: "WhatsApp", href: "/whatsapp", roles: "manager" },
            { title: "Customer Support", href: "/support" },
            { title: "Booking", href: "/booking" },
        ],
    },
    {
        // E — Automate. Workflow orchestration + outbound integrations.
        title: "Automate",
        icon: "layers",
        list: [
            { title: "Workflows", href: "/workflows" },
            { title: "Webhooks", href: "/webhooks", roles: "manager" },
        ],
    },
    {
        // F — Money. Collections + the vendor-cost billing surface.
        title: "Money",
        icon: "wallet",
        list: [
            { title: "Payments", href: "/payments", roles: "manager" },
            { title: "Billing Overview", href: "/billing/overview" },
            { title: "Vendors", href: "/billing/vendors" },
            { title: "Cost Explorer", href: "/billing/explorer" },
            { title: "Audit", href: "/billing/audit" },
            { title: "Plan & Ledger", href: "/billing/plan" },
        ],
    },
    {
        // G — Intelligence. Where the data turns into decisions.
        title: "Intelligence",
        icon: "chart",
        list: [{ title: "Analytics", href: "/analytics" }],
    },
    {
        // COMING SOON — a future "Create Studio" for designing campaigns,
        // scripts and voices in-app. Shown as a disabled group so the roadmap
        // is visible; the pages are intentionally NOT built (children render
        // dimmed with a "Soon" pill and are NOT links).
        title: "Create Studio",
        icon: "edit",
        list: [
            { title: "Script Builder", comingSoon: true },
            { title: "Voice Studio", comingSoon: true },
            { title: "Flow Designer", comingSoon: true },
            { title: "A/B Lab", comingSoon: true },
        ],
    },
    {
        // H — Foundation. Operator-facing config of the foundational systems.
        title: "Foundation",
        icon: "profile",
        list: [
            { title: "Do-Not-Call", href: "/suppression" },
            { title: "Vendors", href: "/vendors", roles: "admin" },
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
