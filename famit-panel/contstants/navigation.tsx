// `roles` (optional) gates an item by the current user's role.
//   "admin"   -> only admins see it
//   "manager" -> managers + admins see it (hidden for read-only agents)
// Items with no `roles` are visible to everyone (read-only views).
export const navigation = [
    {
        title: "Dashboard",
        icon: "dashboard",
        href: "/",
    },
    {
        title: "Campaigns",
        icon: "promote",
        href: "/campaigns",
    },
    {
        title: "Leads",
        icon: "profile",
        href: "/leads",
    },
    {
        title: "Run",
        icon: "send",
        href: "/run",
    },
    {
        title: "Call Logs",
        icon: "chart",
        href: "/calls",
    },
    {
        title: "Do-Not-Call",
        icon: "profile",
        href: "/suppression",
    },
    {
        title: "Callbacks",
        icon: "send",
        href: "/callbacks",
    },
    {
        title: "Analytics",
        icon: "chart",
        href: "/analytics",
    },
    {
        title: "Webhooks",
        icon: "link",
        href: "/webhooks",
        roles: "manager",
    },
    {
        title: "WhatsApp",
        icon: "chat",
        href: "/whatsapp",
        roles: "manager",
    },
    {
        // Collapsible parent (no `href`) — Sidebar renders this via the
        // Sidebar/Dropdown expandable group (same mechanism as the core-2
        // "Income → …" group). Each child is its own route under /billing/.
        title: "Billing",
        icon: "wallet",
        list: [
            {
                title: "Overview",
                href: "/billing/overview",
            },
            {
                title: "Vendors",
                href: "/billing/vendors",
            },
            {
                title: "Cost Explorer",
                href: "/billing/explorer",
            },
            {
                title: "Audit",
                href: "/billing/audit",
            },
            {
                title: "Plan & Ledger",
                href: "/billing/plan",
            },
        ],
    },
    {
        title: "Vendors",
        icon: "profile",
        href: "/vendors",
        roles: "admin",
    },
];

export const navigationUser = [
    {
        title: "Settings",
        icon: "edit-profile",
        href: "/settings",
    },
];
