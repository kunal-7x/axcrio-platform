"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
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
            {toast && (
                <div
                    className={`mb-4 p-3 rounded-2xl text-body-2 flex items-center justify-between gap-3 ${
                        toast.type === "success"
                            ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                            : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                    }`}
                >
                    <span>{toast.msg}</span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: Vendors list */}
                <div className="flex-1 min-w-0">
                    <Card title="All Vendors">
                        {loadError && (
                            <div className="mx-5 mb-3 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
                                {loadError}
                            </div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
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
                                        <tr>
                                            <td colSpan={4} className="py-8 text-center text-t-secondary">
                                                <span className="inline-flex items-center gap-2">
                                                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                                    </svg>
                                                    Loading vendors…
                                                </span>
                                            </td>
                                        </tr>
                                    ) : tenants.length === 0 ? (
                                        <tr>
                                            <td colSpan={4} className="py-12 text-center text-t-secondary">
                                                <div className="flex flex-col items-center gap-2">
                                                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
                                                        <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
                                                        <circle cx="9" cy="7" r="4"/>
                                                        <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
                                                    </svg>
                                                    <span className="text-t-tertiary">No vendors yet — create one on the right</span>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        tenants.map((t) => (
                                            <tr key={t.tenant_id} className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors">
                                                <td className="font-medium">{t.name}</td>
                                                <td className="text-t-secondary">{t.email}</td>
                                                <td>
                                                    {(() => {
                                                        const r = t.role || (t.is_admin ? "admin" : "manager");
                                                        const cls = r === "admin"
                                                            ? "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400"
                                                            : r === "agent"
                                                            ? "bg-b-surface3 text-t-tertiary"
                                                            : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400";
                                                        return (
                                                            <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${cls}`}>{r}</span>
                                                        );
                                                    })()}
                                                </td>
                                                <td className="text-t-secondary">{fmtDate(t.created_at)}</td>
                                            </tr>
                                        ))
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
                                    className="w-full h-11 px-4 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
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
                                    className="w-full h-11 px-4 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
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
                                    className="w-full h-11 px-4 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
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
                                    className="w-full h-11 px-4 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight bg-transparent"
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
