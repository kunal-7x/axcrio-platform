"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
    SuperAdminGuard,
    AdminHeader,
    ErrorBanner,
    fmtDate,
} from "@/app/super-admin/_shared";
import Button from "@/components/Button";
import Layout from "@/components/Layout";
import Select from "@/components/Select";
import {
    getClients,
    createClient,
    updateClient,
    setClientStatus,
    resetClientPassword,
    deleteClient,
    getSignupSettings,
    setSignupDefaultRole,
    getClientProfile,
    type ClientInfo,
    type ClientProfile,
    type SessionRow,
    type Role,
} from "@/lib/api";

// Sidebar sections a client can be restricted from (matches navigation titles).
const SECTIONS = [
    "Work",
    "Grow",
    "Revenue Tools",
    "Creative Studio",
    "Message",
    "Money",
    "Build",
];
const ROLES: { id: Role; name: string; hint: string }[] = [
    { id: "manager", name: "Manager", hint: "Run campaigns, manage leads & data" },
    { id: "agent", name: "Agent", hint: "Read-only access" },
];

// Design-system Select option lists (id === array index; `value` holds the real value).
const SIGNUP_ROLE_OPTS: { id: number; name: string; value: "agent" | "manager" }[] = [
    { id: 0, name: "Agent", value: "agent" },
    { id: 1, name: "Manager", value: "manager" },
];
const ROLE_OPTS: { id: number; name: string; value: Role }[] = ROLES.map((r, i) => ({
    id: i,
    name: `${r.name} — ${r.hint}`,
    value: r.id,
}));

function fmtClock(total: number): string {
    const s = Math.max(0, Math.floor(total));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

const inputCls =
    "w-full h-11 px-3.5 rounded-xl bg-b-surface1 border border-s-stroke2 text-body-2 text-t-primary placeholder:text-t-tertiary outline-none transition-colors focus:border-primary-01 dark:bg-shade-04/30";

type FormState = {
    name: string;
    email: string;
    password: string;
    role: Role;
    demo: boolean;
    demo_minutes: number;
    restricted: string[];
};

const EMPTY_FORM: FormState = {
    name: "",
    email: "",
    password: "",
    role: "manager",
    demo: false,
    demo_minutes: 10,
    restricted: [],
};

function ClientsInner() {
    const [clients, setClients] = useState<ClientInfo[]>([]);
    const [loadedAt, setLoadedAt] = useState<number>(() => 0);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [query, setQuery] = useState("");
    const [signupRole, setSignupRole] = useState("agent");
    const [, setTick] = useState(0);

    // modal
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState<ClientInfo | null>(null);
    const [form, setForm] = useState<FormState>(EMPTY_FORM);
    const [busy, setBusy] = useState(false);
    const [modalErr, setModalErr] = useState("");

    // monitoring profile modal
    const [profileOpen, setProfileOpen] = useState(false);
    const [profile, setProfile] = useState<ClientProfile | null>(null);
    const [profileLoading, setProfileLoading] = useState(false);
    const [profileErr, setProfileErr] = useState("");

    const openProfile = useCallback(async (c: ClientInfo) => {
        setProfileOpen(true);
        setProfile(null);
        setProfileErr("");
        setProfileLoading(true);
        try {
            const p = await getClientProfile(c.tenant_id);
            setProfile(p);
        } catch (e) {
            setProfileErr(e instanceof Error ? e.message : "Failed to load profile");
        } finally {
            setProfileLoading(false);
        }
    }, []);

    const load = useCallback(async () => {
        setErr("");
        try {
            const r = await getClients();
            setClients(r.clients);
            setLoadedAt(Date.now());
            try {
                const s = await getSignupSettings();
                setSignupRole(s.default_role || "agent");
            } catch {
                /* signup settings optional */
            }
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Failed to load clients");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // 1s ticker so demo countdowns update live
    useEffect(() => {
        const iv = setInterval(() => setTick((v) => v + 1), 1000);
        return () => clearInterval(iv);
    }, []);

    const liveRemaining = useCallback(
        (c: ClientInfo): number => {
            if (!c.demo) return 0;
            const elapsed = loadedAt ? Math.floor((Date.now() - loadedAt) / 1000) : 0;
            return Math.max(0, (c.demo_remaining_s ?? 0) - elapsed);
        },
        [loadedAt]
    );

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return clients;
        return clients.filter(
            (c) =>
                c.name.toLowerCase().includes(q) ||
                c.email.toLowerCase().includes(q)
        );
    }, [clients, query]);

    function openCreate() {
        setEditing(null);
        setForm(EMPTY_FORM);
        setModalErr("");
        setOpen(true);
    }
    function openEdit(c: ClientInfo) {
        setEditing(c);
        setForm({
            name: c.name,
            email: c.email,
            password: "",
            role: (c.role === "admin" ? "manager" : c.role) as Role,
            demo: c.demo,
            demo_minutes: c.demo_minutes ?? 10,
            restricted: c.restricted || [],
        });
        setModalErr("");
        setOpen(true);
    }

    function toggleRestrict(section: string) {
        setForm((f) => ({
            ...f,
            restricted: f.restricted.includes(section)
                ? f.restricted.filter((s) => s !== section)
                : [...f.restricted, section],
        }));
    }

    async function save() {
        setModalErr("");
        if (!form.email.trim()) {
            setModalErr("Email is required.");
            return;
        }
        if (!editing && form.password.length < 4) {
            setModalErr("Password must be at least 4 characters.");
            return;
        }
        setBusy(true);
        try {
            if (editing) {
                await updateClient(editing.tenant_id, {
                    name: form.name,
                    email: form.email,
                    role: form.role,
                    demo: form.demo,
                    demo_minutes: form.demo_minutes,
                    restricted: form.restricted,
                });
                if (form.password.trim()) {
                    await resetClientPassword(editing.tenant_id, form.password.trim());
                }
            } else {
                await createClient({
                    email: form.email.trim(),
                    password: form.password,
                    name: form.name,
                    role: form.role,
                    demo: form.demo,
                    demo_minutes: form.demo_minutes,
                    restricted: form.restricted,
                });
            }
            setOpen(false);
            await load();
        } catch (e) {
            setModalErr(e instanceof Error ? e.message : "Save failed");
        } finally {
            setBusy(false);
        }
    }

    async function toggleStatus(c: ClientInfo) {
        const next = c.status === "suspended" ? "active" : "suspended";
        try {
            await setClientStatus(c.tenant_id, next);
            await load();
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Failed to change status");
        }
    }

    async function remove(c: ClientInfo) {
        if (
            !window.confirm(
                `Delete client "${c.name || c.email}" and PERMANENTLY purge all their data (leads, calls, campaigns)? This cannot be undone.`
            )
        )
            return;
        try {
            await deleteClient(c.tenant_id);
            await load();
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Failed to delete client");
        }
    }

    return (
        <Layout title="Clients">
            <AdminHeader
                actions={
                    <Button isBlack icon="plus" onClick={openCreate}>
                        New client
                    </Button>
                }
            />

            <div className="mb-4 flex items-center gap-3 flex-wrap">
                <div className="label label-gray">{clients.length} total</div>
                <div className="flex items-center gap-2 text-body-2 text-t-secondary">
                    <span className="max-md:hidden">New signups default to</span>
                    <span className="md:hidden">Signup role</span>
                    <Select
                        classButton="!h-9 !rounded-lg"
                        value={
                            SIGNUP_ROLE_OPTS.find((o) => o.value === signupRole) ?? null
                        }
                        options={SIGNUP_ROLE_OPTS}
                        onChange={async (o) => {
                            const r = SIGNUP_ROLE_OPTS[o.id].value;
                            setSignupRole(r);
                            try {
                                await setSignupDefaultRole(r);
                            } catch {
                                /* */
                            }
                        }}
                    />
                </div>
                <input
                    className="ml-auto w-60 max-md:w-full h-10 px-3.5 rounded-xl bg-b-surface1 border border-s-stroke2 text-body-2 outline-none focus:border-primary-01 dark:bg-shade-04/30"
                    placeholder="Search name or email…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
            </div>

            {err && <ErrorBanner msg={err} />}

            <div className="card !p-0 overflow-hidden">
                {loading ? (
                    <div className="py-16 text-center text-t-tertiary text-body-2">
                        Loading clients…
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="py-16 text-center text-t-tertiary text-body-2">
                        {query ? "No clients match your search." : "No clients yet. Create the first one."}
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-body-2">
                            <thead className="text-overline uppercase tracking-[0.06em] text-t-tertiary border-b border-s-subtle">
                                <tr>
                                    <th className="text-left font-semibold px-5 py-4">Client</th>
                                    <th className="text-left font-semibold px-3 py-4">Role</th>
                                    <th className="text-left font-semibold px-3 py-4">Status</th>
                                    <th className="text-left font-semibold px-3 py-4">Demo</th>
                                    <th className="text-left font-semibold px-3 py-4">Restricted</th>
                                    <th className="text-left font-semibold px-3 py-4">Created</th>
                                    <th className="text-right font-semibold px-5 py-4">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((c) => {
                                    const rem = liveRemaining(c);
                                    const expired = c.demo && rem <= 0;
                                    return (
                                        <tr
                                            key={c.tenant_id}
                                            className="border-b border-s-subtle last:border-0 hover:bg-b-surface1/60 dark:hover:bg-shade-04/20"
                                        >
                                            <td className="px-5 py-4">
                                                <div className="font-medium text-t-primary">{c.name || "—"}</div>
                                                <div className="text-caption text-t-tertiary">{c.email}</div>
                                            </td>
                                            <td className="px-3 py-4 capitalize text-t-secondary">{c.role}</td>
                                            <td className="px-3 py-4">
                                                <span
                                                    className={`label ${
                                                        c.status === "suspended" ? "label-red" : "label-green"
                                                    }`}
                                                >
                                                    {c.status === "suspended" ? "Suspended" : "Active"}
                                                </span>
                                            </td>
                                            <td className="px-3 py-4">
                                                {c.demo ? (
                                                    <span
                                                        className={`label ${
                                                            expired ? "label-red" : rem <= 60 ? "label-yellow" : "label-gray"
                                                        } tabular-nums`}
                                                    >
                                                        {expired ? "Expired" : fmtClock(rem)}
                                                    </span>
                                                ) : (
                                                    <span className="text-t-tertiary">—</span>
                                                )}
                                            </td>
                                            <td className="px-3 py-4 text-t-secondary">
                                                {c.restricted && c.restricted.length > 0
                                                    ? `${c.restricted.length} hidden`
                                                    : "—"}
                                            </td>
                                            <td className="px-3 py-4 text-t-tertiary">{fmtDate(c.created_at)}</td>
                                            <td className="px-5 py-4">
                                                <div className="flex items-center justify-end gap-1.5">
                                                    <button
                                                        className="h-8 px-2.5 rounded-lg border border-s-stroke2 text-button text-t-secondary hover:text-t-primary hover:border-s-highlight transition-colors"
                                                        onClick={() => openProfile(c)}
                                                    >
                                                        Profile
                                                    </button>
                                                    <button
                                                        className="h-8 px-2.5 rounded-lg border border-s-stroke2 text-button text-t-secondary hover:text-t-primary hover:border-s-highlight transition-colors"
                                                        onClick={() => openEdit(c)}
                                                    >
                                                        Edit
                                                    </button>
                                                    <button
                                                        className="h-8 px-2.5 rounded-lg border border-s-stroke2 text-button text-t-secondary hover:text-t-primary hover:border-s-highlight transition-colors"
                                                        onClick={() => toggleStatus(c)}
                                                    >
                                                        {c.status === "suspended" ? "Activate" : "Deactivate"}
                                                    </button>
                                                    <button
                                                        className="h-8 px-2.5 rounded-lg border border-[#BF4D43]/30 text-button text-[#BF4D43] hover:bg-[#BF4D43]/10 transition-colors"
                                                        onClick={() => remove(c)}
                                                    >
                                                        Delete
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {open && (
                <div
                    className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 backdrop-blur-sm p-4 py-10"
                    onClick={() => !busy && setOpen(false)}
                >
                    <div
                        className="w-full max-w-lg rounded-3xl bg-b-surface2 ring-1 ring-s-subtle shadow-widget p-6 max-md:p-4"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-5">
                            <div className="text-h6">{editing ? "Edit client" : "New client"}</div>
                            <button
                                className="size-9 grid place-items-center rounded-full text-t-tertiary hover:text-t-primary"
                                onClick={() => !busy && setOpen(false)}
                            >
                                ✕
                            </button>
                        </div>

                        {modalErr && <ErrorBanner msg={modalErr} />}

                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                                <label className="block">
                                    <span className="block text-button mb-1.5">Name</span>
                                    <input
                                        className={inputCls}
                                        value={form.name}
                                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                                        placeholder="Acme Corp"
                                    />
                                </label>
                                <label className="block">
                                    <span className="block text-button mb-1.5">Email</span>
                                    <input
                                        className={inputCls}
                                        type="email"
                                        value={form.email}
                                        onChange={(e) => setForm({ ...form, email: e.target.value })}
                                        placeholder="client@company.com"
                                    />
                                </label>
                            </div>

                            <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                                <label className="block">
                                    <span className="block text-button mb-1.5">
                                        {editing ? "Set new password (optional)" : "Password"}
                                    </span>
                                    <input
                                        className={inputCls}
                                        type="text"
                                        value={form.password}
                                        onChange={(e) => setForm({ ...form, password: e.target.value })}
                                        placeholder={editing ? "leave blank to keep" : "min 4 characters"}
                                    />
                                </label>
                                <label className="block">
                                    <span className="block text-button mb-1.5">Role</span>
                                    <Select
                                        className="w-full"
                                        classButton="!h-11"
                                        value={ROLE_OPTS.find((o) => o.value === form.role) ?? null}
                                        options={ROLE_OPTS}
                                        onChange={(o) =>
                                            setForm({ ...form, role: ROLE_OPTS[o.id].value })
                                        }
                                    />
                                </label>
                            </div>

                            {/* Demo account */}
                            <div className="rounded-2xl border border-s-subtle p-4 dark:bg-shade-04/20">
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        className="size-4 accent-primary-01"
                                        checked={form.demo}
                                        onChange={(e) => setForm({ ...form, demo: e.target.checked })}
                                    />
                                    <span>
                                        <span className="block text-button text-t-primary">Demo account</span>
                                        <span className="block text-caption text-t-tertiary">
                                            Auto-deactivates after the time below; a live countdown shows in their header.
                                        </span>
                                    </span>
                                </label>
                                {form.demo && (
                                    <div className="mt-3 flex items-center gap-2">
                                        <span className="text-button text-t-secondary">Active for</span>
                                        <input
                                            type="number"
                                            min={1}
                                            className="w-24 h-10 px-3 rounded-xl bg-b-surface1 border border-s-stroke2 text-body-2 outline-none focus:border-primary-01 dark:bg-shade-04/30"
                                            value={form.demo_minutes}
                                            onChange={(e) =>
                                                setForm({ ...form, demo_minutes: Math.max(1, Number(e.target.value) || 1) })
                                            }
                                        />
                                        <span className="text-button text-t-secondary">minutes</span>
                                        {editing && (
                                            <span className="text-caption text-t-tertiary ml-auto">
                                                Saving resets the clock.
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Restrictions */}
                            <div>
                                <div className="text-button mb-2">Restrictions — hide these sections for this client</div>
                                <div className="grid grid-cols-2 gap-2 max-md:grid-cols-1">
                                    {SECTIONS.map((s) => {
                                        const on = form.restricted.includes(s);
                                        return (
                                            <button
                                                key={s}
                                                type="button"
                                                onClick={() => toggleRestrict(s)}
                                                className={`flex items-center justify-between gap-2 h-11 px-3.5 rounded-xl border text-button transition-colors ${
                                                    on
                                                        ? "border-[#BF4D43]/40 bg-[#BF4D43]/8 text-[#BF4D43]"
                                                        : "border-s-stroke2 text-t-secondary hover:border-s-highlight"
                                                }`}
                                            >
                                                <span>{s}</span>
                                                <span className="text-caption">{on ? "Hidden" : "Allowed"}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>

                        <div className="mt-6 flex items-center gap-3">
                            <Button isBlack className="flex-1 justify-center" onClick={save} disabled={busy}>
                                {busy ? "Saving…" : editing ? "Save changes" : "Create client"}
                            </Button>
                            <Button isStroke onClick={() => !busy && setOpen(false)} disabled={busy}>
                                Cancel
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {profileOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 backdrop-blur-sm p-4 py-10"
                    onClick={() => setProfileOpen(false)}
                >
                    <div
                        className="w-full max-w-2xl rounded-3xl bg-b-surface2 ring-1 ring-s-subtle shadow-widget p-6 max-md:p-4"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-5">
                            <div className="text-h6">Client profile & monitoring</div>
                            <button
                                className="size-9 grid place-items-center rounded-full text-t-tertiary hover:text-t-primary"
                                onClick={() => setProfileOpen(false)}
                            >
                                ✕
                            </button>
                        </div>

                        {profileLoading ? (
                            <div className="py-12 text-center text-t-tertiary text-body-2">Loading profile…</div>
                        ) : profileErr ? (
                            <ErrorBanner msg={profileErr} />
                        ) : profile ? (
                            <ClientProfileView p={profile} />
                        ) : null}
                    </div>
                </div>
            )}
        </Layout>
    );
}

// ---- Super-Admin client monitoring view (read-only) ----
function fmtRel(iso?: string): string {
    if (!iso) return "never";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    const s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} hr ago`;
    if (s < 7 * 86400) return `${Math.floor(s / 86400)} d ago`;
    return fmtDate(iso);
}

function PRow({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex items-start justify-between gap-4 py-2 border-b border-s-subtle last:border-0">
            <span className="text-body-2 text-t-tertiary shrink-0">{label}</span>
            <span className="text-body-2 text-t-primary text-right break-words">{value || "—"}</span>
        </div>
    );
}

function ClientProfileView({ p }: { p: ClientProfile }) {
    const s: SessionRow = p.last_session || ({} as SessionRow);
    const hasPrecise = s.geo_lat != null && s.geo_lon != null;
    return (
        <div className="space-y-5">
            {/* identity */}
            <div className="rounded-2xl border border-s-subtle p-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                        <div className="text-h6 text-t-primary">{p.name || "—"}</div>
                        <div className="text-body-2 text-t-secondary">{p.email}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="label label-gray capitalize">{p.role}</span>
                        {p.self_signup && <span className="label label-gray">Self sign-up</span>}
                        {p.demo && <span className="label label-yellow">Demo</span>}
                        <span className={`label ${p.status === "suspended" ? "label-red" : "label-green"}`}>
                            {p.status === "suspended" ? "Suspended" : "Active"}
                        </span>
                    </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-3 max-md:grid-cols-1">
                    <div>
                        <div className="text-caption text-t-tertiary uppercase tracking-[0.06em]">Created</div>
                        <div className="text-body-2 text-t-primary">{fmtDate(p.created_at)}</div>
                    </div>
                    <div>
                        <div className="text-caption text-t-tertiary uppercase tracking-[0.06em]">Last active</div>
                        <div className="text-body-2 text-t-primary">{fmtRel(s.ts)}</div>
                    </div>
                    <div>
                        <div className="text-caption text-t-tertiary uppercase tracking-[0.06em]">Sessions</div>
                        <div className="text-body-2 text-t-primary">{p.sessions_count || 0}</div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
                {/* location */}
                <div className="rounded-2xl border border-s-subtle p-4">
                    <div className="text-button text-t-primary mb-2 flex items-center gap-2">
                        <span>{s.flag || "🌐"}</span> Location
                    </div>
                    <PRow
                        label="Country"
                        value={s.country ? `${s.flag} ${s.country}` : "—"}
                    />
                    <PRow label="Region / City" value={[s.city, s.region].filter(Boolean).join(", ")} />
                    <PRow label="IP" value={<span className="font-mono text-[0.8125rem]">{s.ip}</span>} />
                    <PRow label="ISP" value={s.isp} />
                    <PRow label="IP timezone" value={s.ip_timezone} />
                    {hasPrecise && (
                        <PRow
                            label="Precise GPS"
                            value={
                                <a
                                    href={`https://www.google.com/maps?q=${s.geo_lat},${s.geo_lon}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-primary-01 hover:opacity-70 font-mono text-[0.8125rem]"
                                >
                                    {Number(s.geo_lat).toFixed(4)}, {Number(s.geo_lon).toFixed(4)} ↗
                                </a>
                            }
                        />
                    )}
                </div>

                {/* device */}
                <div className="rounded-2xl border border-s-subtle p-4">
                    <div className="text-button text-t-primary mb-2 flex items-center gap-2">
                        <span>💻</span> Device
                    </div>
                    <PRow label="Device type" value={s.device} />
                    <PRow label="Browser" value={s.browser} />
                    <PRow label="OS" value={s.os} />
                    <PRow label="Platform" value={s.platform} />
                    <PRow label="Screen" value={s.screen} />
                    <PRow label="Browser TZ" value={s.tz} />
                    <PRow label="Language" value={s.locale} />
                </div>
            </div>

            {/* session history */}
            <div>
                <div className="text-button text-t-secondary mb-2">Session history</div>
                {p.sessions && p.sessions.length > 0 ? (
                    <div className="rounded-2xl border border-s-subtle overflow-hidden">
                        <div className="overflow-x-auto max-h-72 overflow-y-auto">
                            <table className="w-full text-body-2">
                                <thead className="text-overline uppercase tracking-[0.06em] text-t-tertiary border-b border-s-subtle sticky top-0 bg-b-surface2">
                                    <tr>
                                        <th className="text-left font-semibold px-4 py-2.5">When</th>
                                        <th className="text-left font-semibold px-3 py-2.5">Location</th>
                                        <th className="text-left font-semibold px-3 py-2.5">Device</th>
                                        <th className="text-left font-semibold px-4 py-2.5">IP</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {p.sessions.map((r, i) => (
                                        <tr key={i} className="border-b border-s-subtle last:border-0">
                                            <td className="px-4 py-2.5 text-t-secondary whitespace-nowrap">{fmtRel(r.ts)}</td>
                                            <td className="px-3 py-2.5 text-t-primary">
                                                {r.flag} {r.location || "Unknown"}
                                            </td>
                                            <td className="px-3 py-2.5 text-t-secondary">
                                                {r.browser} · {r.os}
                                            </td>
                                            <td className="px-4 py-2.5 text-t-tertiary font-mono text-[0.8125rem]">{r.ip}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) : (
                    <div className="rounded-2xl border border-s-subtle py-8 text-center text-t-tertiary text-body-2">
                        No sessions recorded yet — they appear after the client next signs in.
                    </div>
                )}
            </div>
        </div>
    );
}

export default function ClientsPage() {
    return (
        <SuperAdminGuard>
            <ClientsInner />
        </SuperAdminGuard>
    );
}
