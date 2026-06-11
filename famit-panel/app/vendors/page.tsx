"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Search from "@/components/Search";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
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

const roleOptions = [
    { id: 1, name: "manager (full tenant actions)" },
    { id: 2, name: "agent (read-only)" },
];
const roleById: Record<number, Role> = { 1: "manager", 2: "agent" };

export default function VendorsPage() {
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);
    const [search, setSearch] = useState("");

    // Create form
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [role, setRole] = useState(roleOptions[0]);
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
            await createTenant({ name, email, password, role: roleById[role.id] });
            showToast(`Vendor "${name}" created successfully!`, "success");
            setName("");
            setEmail("");
            setPassword("");
            setRole(roleOptions[0]);
            loadTenants();
        } catch (err: unknown) {
            showToast(err instanceof Error ? err.message : "Failed to create vendor", "error");
        } finally {
            setCreating(false);
        }
    }

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return tenants;
        return tenants.filter(
            (t) =>
                (t.name || "").toLowerCase().includes(q) ||
                (t.email || "").toLowerCase().includes(q)
        );
    }, [tenants, search]);

    return (
        <Layout title="Vendors">
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="flex gap-3 max-lg:flex-col">
                {/* Left: Vendors list */}
                <div className="flex-1 min-w-0">
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="pl-5 text-h6 max-lg:pl-3 mr-auto">All vendors</div>
                            <Search
                                className="w-64 max-md:w-full max-md:order-3"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search by name or email"
                                isGray
                            />
                        </div>

                        {loadError ? (
                            <div className="mx-5 my-4 flex items-center gap-3 p-4 rounded-3xl bg-b-surface2 border border-primary-03/40 text-body-2 text-t-secondary max-lg:mx-3">
                                <Icon className="shrink-0 fill-primary-03" name="info" />
                                <span className="text-t-primary">{loadError}</span>
                            </div>
                        ) : loading ? (
                            <div className="py-16"><Spinner /></div>
                        ) : filtered.length === 0 ? (
                            <div className="flex flex-col items-center text-center py-16 px-5">
                                <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name="bag" />
                                </div>
                                <div className="text-sub-title-1 text-t-primary">
                                    {search ? "No vendors match your search" : "No vendors yet"}
                                </div>
                                <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                                    Create your first vendor account on the right to onboard a tenant.
                                </div>
                            </div>
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Name</th>
                                            <th>Email</th>
                                            <th>Role</th>
                                            <th>Created</th>
                                        </>
                                    }
                                >
                                    {filtered.map((t) => {
                                        const r = t.role || (t.is_admin ? "admin" : "manager");
                                        const variant = r === "admin" ? "info" : r === "agent" ? "neutral" : "success";
                                        return (
                                            <TableRow key={t.tenant_id}>
                                                <td className="font-medium text-t-primary">{t.name}</td>
                                                <td className="text-t-secondary">{t.email}</td>
                                                <td><Badge variant={variant}>{r}</Badge></td>
                                                <td className="text-t-secondary whitespace-nowrap">{fmtDate(t.created_at)}</td>
                                            </TableRow>
                                        );
                                    })}
                                </Table>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Create vendor */}
                <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0">
                    <Card title="Add vendor">
                        <form onSubmit={handleCreate} className="flex flex-col gap-6 p-5 pt-3 max-lg:px-3">
                            <Field
                                label="Company / Name"
                                placeholder="Acme Corp"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                            />
                            <Field
                                label="Email"
                                type="email"
                                placeholder="vendor@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                            <Field
                                label="Password"
                                type="password"
                                placeholder="Set a strong password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                minLength={6}
                            />
                            <Select
                                label="Role"
                                value={role}
                                onChange={setRole}
                                options={roleOptions}
                            />
                            <Button isBlack className="w-full" disabled={creating}>
                                {creating ? "Creating…" : "Create vendor"}
                            </Button>
                        </form>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}
