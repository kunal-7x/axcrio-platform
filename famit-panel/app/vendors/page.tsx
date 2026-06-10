"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { getTenants, createTenant, type Tenant, type Role } from "@/lib/api";

function fmtDate(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
}

type Toast = { msg: string; type: "success" | "error" };

export default function VendorsPage() {
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);

    // Create form
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [role, setRole] = useState<Role>("manager");
    const [creating, setCreating] = useState(false);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const loadTenants = useCallback(() => {
        setLoading(true);
        setLoadError("");
        getTenants()
            .then((r) => setTenants(r.tenants))
            .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load vendors"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        loadTenants();
    }, [loadTenants]);

    async function handleCreate(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim() || !email.trim() || !password.trim()) return;
        setCreating(true);
        try {
            await createTenant({ name, email, password, role });
            showToast(`Vendor "${name}" created successfully!`, "success");
            setName("");
            setEmail("");
            setPassword("");
            setRole("manager");
            loadTenants();
        } catch (err: unknown) {
            showToast(err instanceof Error ? err.message : "Failed to create vendor", "error");
        } finally {
            setCreating(false);
        }
    }

    return (
        <Layout title="Vendors">
            <PageHeader
                eyebrow="Admin"
                title="Vendors"
                subtitle="Create and manage the tenant accounts that share this platform. Each vendor sees only its own campaigns, leads and calls."
            />
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: Vendors list */}
                <div className="flex-1 min-w-0">
                    <Card title="All Vendors">
                        {loadError && (
                            <div className="mx-5 mb-3 toast toast-error"><span className="flex items-center gap-2"><span className="size-1.5 rounded-full bg-current" />{loadError}</span></div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Email</th>
                                        <th>Role</th>
                                        <th>Created</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(4)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(4)].map((__, j) => (
                                                    <td key={j}><div className="skeleton h-4 w-24" /></td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : tenants.length === 0 ? (
                                        <tr>
                                            <td colSpan={4}>
                                                <div className="state-block">
                                                    <span className="state-glyph"><Icon name="profile" className="fill-inherit" /></span>
                                                    <div className="state-title">No vendors yet</div>
                                                    <div className="state-sub">Create your first vendor account on the right to onboard a tenant.</div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        tenants.map((t) => {
                                            const r = t.role || (t.is_admin ? "admin" : "manager");
                                            const variant = r === "admin" ? "info" : r === "agent" ? "neutral" : "success";
                                            return (
                                                <tr key={t.tenant_id}>
                                                    <td className="font-medium text-t-primary">{t.name}</td>
                                                    <td className="text-t-secondary">{t.email}</td>
                                                    <td><Badge variant={variant}>{r}</Badge></td>
                                                    <td className="text-t-secondary whitespace-nowrap">{fmtDate(t.created_at)}</td>
                                                </tr>
                                            );
                                        })
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Right: Create vendor */}
                <div className="w-96 max-lg:w-full shrink-0">
                    <Card title="Add Vendor">
                        <form onSubmit={handleCreate} className="px-5 pb-5 space-y-4">
                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Company / Name
                                </label>
                                <input
                                    type="text"
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    className="input-base w-full h-11 px-4 rounded-2xl text-body-2"
                                    placeholder="Acme Corp"
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="input-base w-full h-11 px-4 rounded-2xl text-body-2"
                                    placeholder="vendor@company.com"
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Password
                                </label>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="input-base w-full h-11 px-4 rounded-2xl text-body-2"
                                    placeholder="Set a strong password"
                                    required
                                    minLength={6}
                                />
                            </div>

                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Role
                                </label>
                                <select
                                    value={role}
                                    onChange={(e) => setRole(e.target.value as Role)}
                                    className="input-base w-full h-11 px-4 rounded-2xl text-body-2"
                                >
                                    <option value="manager">manager (full tenant actions)</option>
                                    <option value="agent">agent (read-only)</option>
                                </select>
                            </div>

                            <Button
                                isBlack
                                className="w-full justify-center"
                                disabled={creating}
                            >
                                {creating ? (
                                    <span className="inline-flex items-center gap-2">
                                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                        </svg>
                                        Creating…
                                    </span>
                                ) : "Create Vendor"}
                            </Button>
                        </form>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}
