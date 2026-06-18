"use client";

// Famit Studio — the integrated developer console inside the dashboard.
//
// Two surfaces, one page:
//   Deploy  — Coolify PaaS (self-hosted): list apps, trigger deploys, view logs.
//             Config: COOLIFY_URL + COOLIFY_API_KEY in the server env.
//   Editor  — OpenVSCode Server (self-hosted): full VS Code in an iframe.
//             Config: NEXT_PUBLIC_OPENVSCODE_URL in the panel env.
//
// Both are dormant-safe: a missing config renders a step-by-step setup card,
// never an error wall. Built entirely on Signal design tokens — no raw hex.

import { useCallback, useEffect, useRef, useState } from "react";
import Layout from "@/components/Layout";
import Button from "@/components/Button";
import KpiCard from "@/components/KpiCard";
import Spinner from "@/components/Spinner";
import Icon from "@/components/Icon";
import Tabs from "@/components/Tabs";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Modal from "@/components/Modal";
import type { TabsOption } from "@/types/tabs";
import { useMe, canWrite } from "@/lib/auth";
import {
    listApplications,
    listDeployments,
    listServers,
    triggerDeploy,
    StudioError,
    isNotConfigured,
    APP_STATUS_LABEL,
    DEPLOY_STATUS_LABEL,
    relTime,
    type CoolifyApp,
    type CoolifyDeployment,
    type CoolifyServer,
    type AppStatus,
    type DeployStatus,
} from "./_lib";

// ---- Tabs -------------------------------------------------------------------
const TAB_DEPLOY = 1;
const TAB_EDITOR = 2;
const TABS: TabsOption[] = [
    { id: TAB_DEPLOY, name: "Deploy" },
    { id: TAB_EDITOR, name: "Editor" },
];

// Read at module-load time so Next.js can tree-shake the env var server-side.
const EDITOR_URL = process.env.NEXT_PUBLIC_OPENVSCODE_URL ?? "";

// ---- Badge helpers ----------------------------------------------------------
function appBadge(status: AppStatus): BadgeVariant {
    if (status === "running") return "success";
    if (status === "restarting") return "warning";
    if (status === "stopped" || status === "exited") return "danger";
    return "neutral";
}

function deployBadge(status: DeployStatus): BadgeVariant {
    if (status === "finished") return "success";
    if (status === "in_progress" || status === "queued") return "warning";
    if (status === "failed") return "danger";
    return "neutral";
}

// ---- Setup card -------------------------------------------------------------
function SetupCard({ title, steps }: { title: string; steps: string[] }) {
    return (
        <div className="rise-in" style={{ maxWidth: 680, margin: "0 auto", paddingTop: "2rem" }}>
            <div className="card" style={{ padding: "2.5rem 2rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem" }}>
                    <Icon name="desktop" className="icon-lg fill-t-secondary" />
                    <span className="pill pill-warning" style={{ fontSize: "0.7rem", fontWeight: 700 }}>
                        Setup required
                    </span>
                </div>
                <p style={{ color: "var(--color-shade-07)", lineHeight: 1.65, marginBottom: "1.5rem", fontSize: "0.9rem" }}>
                    {title}
                </p>
                <ol style={{ paddingLeft: "1.4rem", display: "flex", flexDirection: "column", gap: "0.6rem", margin: 0 }}>
                    {steps.map((step, i) => (
                        <li key={i} style={{ color: "var(--color-shade-06)", fontSize: "0.85rem", lineHeight: 1.7 }}>
                            {step}
                        </li>
                    ))}
                </ol>
            </div>
        </div>
    );
}

// ---- Log modal --------------------------------------------------------------
function LogModal({
    open,
    app,
    deployments,
    loading,
    onClose,
}: {
    open: boolean;
    app: CoolifyApp | null;
    deployments: CoolifyDeployment[];
    loading: boolean;
    onClose: () => void;
}) {
    return (
        <Modal open={open} onClose={onClose}>
            <div style={{ width: "min(92vw, 740px)", padding: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
                    <h3 className="text-h4" style={{ margin: 0 }}>
                        {app?.name ?? ""} — Deployments
                    </h3>
                </div>
                {loading ? (
                    <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
                        <Spinner />
                    </div>
                ) : deployments.length === 0 ? (
                    <p style={{ color: "var(--color-shade-05)", fontSize: "0.875rem" }}>No deployments yet.</p>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", maxHeight: "70vh", overflowY: "auto" }}>
                        {deployments.slice(0, 10).map((d) => (
                            <div key={d.id} className="card" style={{ padding: "0.85rem 1rem" }}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem" }}>
                                    <Badge variant={deployBadge(d.status)}>
                                        {DEPLOY_STATUS_LABEL[d.status] ?? d.status}
                                    </Badge>
                                    <span style={{ fontSize: "0.75rem", color: "var(--color-shade-05)" }}>
                                        {relTime(d.created_at)}
                                    </span>
                                </div>
                                {d.commit && (
                                    <p style={{ fontSize: "0.72rem", fontFamily: "monospace", color: "var(--color-shade-05)", margin: "0.25rem 0 0" }}>
                                        commit {d.commit.slice(0, 10)}
                                    </p>
                                )}
                                {d.logs && (
                                    <pre
                                        style={{
                                            marginTop: "0.6rem",
                                            padding: "0.75rem",
                                            background: "var(--color-b-dark1)",
                                            borderRadius: 6,
                                            fontSize: "0.68rem",
                                            color: "var(--color-shade-08)",
                                            maxHeight: 220,
                                            overflow: "auto",
                                            fontFamily: "monospace",
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-all",
                                            lineHeight: 1.55,
                                        }}
                                    >
                                        {d.logs}
                                    </pre>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Modal>
    );
}

// ---- Main page --------------------------------------------------------------
export default function StudioPage() {
    const { me } = useMe();
    const writable = canWrite(me);
    const [tab, setTab] = useState<TabsOption>(TABS[0]);

    // Deploy state
    const [apps, setApps] = useState<CoolifyApp[]>([]);
    const [servers, setServers] = useState<CoolifyServer[]>([]);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [deploying, setDeploying] = useState<string | null>(null);

    // Log modal
    const [logApp, setLogApp] = useState<CoolifyApp | null>(null);
    const [logModalOpen, setLogModalOpen] = useState(false);
    const [deployments, setDeployments] = useState<CoolifyDeployment[]>([]);
    const [logsLoading, setLogsLoading] = useState(false);

    // Toast
    const [toast, setToast] = useState<{ kind: "success" | "error"; msg: string } | null>(null);
    const toastRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const flash = useCallback((kind: "success" | "error", msg: string) => {
        setToast({ kind, msg });
        if (toastRef.current) clearTimeout(toastRef.current);
        toastRef.current = setTimeout(() => setToast(null), 3200);
    }, []);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const [a, s] = await Promise.all([listApplications(), listServers()]);
            setApps(a);
            setServers(s);
            setDormant(false);
        } catch (e) {
            if (isNotConfigured(e) || e instanceof StudioError) setDormant(true);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void refresh(); }, [refresh]);

    const openLogs = useCallback(async (app: CoolifyApp) => {
        setLogApp(app);
        setDeployments([]);
        setLogsLoading(true);
        setLogModalOpen(true);
        try {
            setDeployments(await listDeployments(app.uuid));
        } catch {
            setDeployments([]);
        } finally {
            setLogsLoading(false);
        }
    }, []);

    const deploy = useCallback(async (app: CoolifyApp) => {
        if (!writable) return;
        setDeploying(app.uuid);
        try {
            const r = await triggerDeploy(app.uuid);
            flash("success", r.message || `Deployment queued for ${app.name}`);
            setTimeout(() => { void refresh(); }, 2000);
        } catch (e) {
            flash("error", e instanceof StudioError ? e.message : "Failed to trigger deployment.");
        } finally {
            setDeploying(null);
        }
    }, [writable, flash, refresh]);

    // KPI figures
    const running = apps.filter((a) => a.status === "running").length;
    const offline = apps.filter((a) => a.status === "stopped" || a.status === "exited").length;
    const reachable = servers.filter((s) => s.status === "reachable").length;

    return (
        <Layout>
            <div className="page-content rise-in">
                {/* Header */}
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
                    <div>
                        <h1 className="text-h3" style={{ margin: 0 }}>Studio</h1>
                        <p style={{ color: "var(--color-shade-05)", fontSize: "0.85rem", marginTop: "0.3rem" }}>
                            Deploy with Coolify · Edit with OpenVSCode Server
                        </p>
                    </div>
                    {tab.id === TAB_DEPLOY && !dormant && !loading && (
                        <Button isGray onClick={() => { void refresh(); }} icon="arrow">
                            Refresh
                        </Button>
                    )}
                </div>

                <Tabs items={TABS} value={tab} setValue={setTab} />

                <div style={{ marginTop: "1.5rem" }}>

                    {/* ── Deploy tab ─────────────────────────────────────────── */}
                    {tab.id === TAB_DEPLOY && (
                        <>
                            {loading ? (
                                <div style={{ display: "flex", justifyContent: "center", padding: "5rem" }}>
                                    <Spinner />
                                </div>
                            ) : dormant ? (
                                <SetupCard
                                    title="Coolify is not connected. Self-host it on your server to get a full PaaS deployment plane inside Famit — deploy Next.js apps, React frontends, Python backends, Node services, and databases without leaving the dashboard."
                                    steps={[
                                        "SSH into your server and run:  curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash",
                                        "Open Coolify at http://<your-server-ip>:8000 and complete onboarding",
                                        "Go to Keys & Tokens → API Tokens → New Token → copy it",
                                        "Add to your Famit panel server env:  COOLIFY_URL=http://<your-server-ip>:8000",
                                        "Add to your Famit panel server env:  COOLIFY_API_KEY=<your-token>",
                                        "Restart the panel (pnpm build && pnpm start) — apps appear here",
                                    ]}
                                />
                            ) : (
                                <>
                                    {/* KPI row */}
                                    <div
                                        style={{
                                            display: "grid",
                                            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                                            gap: "1rem",
                                            marginBottom: "1.5rem",
                                        }}
                                    >
                                        <KpiCard label="Total Apps" value={apps.length} icon="cube" />
                                        <KpiCard label="Running" value={running} icon="check-circle" tone="success" />
                                        <KpiCard label="Offline" value={offline} icon="close" tone={offline > 0 ? "danger" : "neutral"} />
                                        <KpiCard label="Servers" value={reachable} icon="layers" tone="info" />
                                    </div>

                                    {/* Apps table */}
                                    {apps.length === 0 ? (
                                        <div
                                            className="card"
                                            style={{ padding: "4rem 2rem", textAlign: "center", color: "var(--color-shade-05)" }}
                                        >
                                            No applications found in Coolify. Create your first app there, then refresh.
                                        </div>
                                    ) : (
                                        <div className="card rise-in" style={{ overflow: "hidden" }}>
                                            <table
                                                style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}
                                            >
                                                <thead>
                                                    <tr style={{ borderBottom: "1px solid var(--color-shade-02)" }}>
                                                        {["Application", "Status", "Branch", "URL", "Updated", ""].map((h) => (
                                                            <th
                                                                key={h}
                                                                style={{
                                                                    padding: "0.85rem 1rem",
                                                                    textAlign: "left",
                                                                    fontSize: "0.72rem",
                                                                    fontWeight: 700,
                                                                    letterSpacing: "0.06em",
                                                                    textTransform: "uppercase",
                                                                    color: "var(--color-shade-05)",
                                                                }}
                                                            >
                                                                {h}
                                                            </th>
                                                        ))}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {apps.map((app) => (
                                                        <tr
                                                            key={app.uuid}
                                                            style={{ borderBottom: "1px solid var(--color-shade-01)" }}
                                                        >
                                                            <td style={{ padding: "0.9rem 1rem" }}>
                                                                <div style={{ fontWeight: 500 }}>{app.name}</div>
                                                                {app.build_pack && (
                                                                    <div style={{ fontSize: "0.72rem", color: "var(--color-shade-04)", marginTop: "0.15rem" }}>
                                                                        {app.build_pack}
                                                                    </div>
                                                                )}
                                                            </td>
                                                            <td style={{ padding: "0.9rem 1rem" }}>
                                                                <Badge variant={appBadge(app.status)}>
                                                                    {APP_STATUS_LABEL[app.status] ?? app.status}
                                                                </Badge>
                                                            </td>
                                                            <td style={{ padding: "0.9rem 1rem", fontFamily: "monospace", fontSize: "0.8rem", color: "var(--color-shade-06)" }}>
                                                                {app.git_branch ?? "—"}
                                                            </td>
                                                            <td style={{ padding: "0.9rem 1rem" }}>
                                                                {app.fqdn ? (
                                                                    <a
                                                                        href={app.fqdn.startsWith("http") ? app.fqdn : `https://${app.fqdn}`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        style={{ color: "var(--color-primary-03)", fontSize: "0.8rem", textDecoration: "none" }}
                                                                    >
                                                                        {app.fqdn}
                                                                    </a>
                                                                ) : (
                                                                    <span style={{ color: "var(--color-shade-03)", fontSize: "0.8rem" }}>—</span>
                                                                )}
                                                            </td>
                                                            <td style={{ padding: "0.9rem 1rem", fontSize: "0.8rem", color: "var(--color-shade-05)" }}>
                                                                {relTime(app.updated_at)}
                                                            </td>
                                                            <td style={{ padding: "0.9rem 1rem" }}>
                                                                <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                                                                    <Button
                                                                        isGray
                                                                        onClick={() => void openLogs(app)}
                                                                    >
                                                                        Logs
                                                                    </Button>
                                                                    {writable && (
                                                                        <Button
                                                                            isBlack
                                                                            onClick={() => void deploy(app)}
                                                                            disabled={deploying === app.uuid}
                                                                        >
                                                                            {deploying === app.uuid && (
                                                                                <span style={{ display: "inline-flex", marginRight: "0.3rem" }}>
                                                                                    <Spinner />
                                                                                </span>
                                                                            )}
                                                                            Deploy
                                                                        </Button>
                                                                    )}
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </>
                            )}
                        </>
                    )}

                    {/* ── Editor tab ─────────────────────────────────────────── */}
                    {tab.id === TAB_EDITOR && (
                        EDITOR_URL ? (
                            <div
                                className="card rise-in"
                                style={{
                                    height: "calc(100vh - 220px)",
                                    minHeight: 480,
                                    padding: 0,
                                    overflow: "hidden",
                                    borderRadius: 12,
                                }}
                            >
                                <iframe
                                    src={EDITOR_URL}
                                    style={{ width: "100%", height: "100%", border: "none", display: "block" }}
                                    title="OpenVSCode Server"
                                    allow="clipboard-read; clipboard-write"
                                />
                            </div>
                        ) : (
                            <SetupCard
                                title="OpenVSCode Server is not configured. Self-host it on your server for a full VS Code editor embedded directly in Famit — edit React frontends, Python backends, configs, databases — everything from one place."
                                steps={[
                                    "On your server, run:  docker run -it --init -p 3000:3000 -v \"$(pwd)/workspace:/home/workspace:cached\" ghcr.io/gitpod-io/openvscode-server:latest",
                                    "Or use Docker Compose with a named volume and --restart=unless-stopped for persistence",
                                    "Optional — add a connection token for security:  --connection-token=<secret>",
                                    "Add to your panel env (.env.local):  NEXT_PUBLIC_OPENVSCODE_URL=http://<your-server-ip>:3000",
                                    "Restart the panel — the editor loads here in an iframe",
                                    "Tip: you can deploy OpenVSCode Server itself through the Deploy tab using Coolify",
                                ]}
                            />
                        )
                    )}
                </div>
            </div>

            {/* Log modal */}
            <LogModal
                open={logModalOpen}
                app={logApp}
                deployments={deployments}
                loading={logsLoading}
                onClose={() => { setLogModalOpen(false); setLogApp(null); setDeployments([]); }}
            />

            {/* Toast */}
            {toast && (
                <div
                    className="rise-in"
                    style={{
                        position: "fixed",
                        bottom: "1.5rem",
                        right: "1.5rem",
                        zIndex: 9999,
                        padding: "0.75rem 1.25rem",
                        borderRadius: 8,
                        fontSize: "0.875rem",
                        boxShadow: "0 4px 20px rgba(0,0,0,0.18)",
                        background: toast.kind === "success"
                            ? "var(--color-b-primary)"
                            : "var(--color-secondary-04)",
                        color: "#fff",
                        maxWidth: 360,
                    }}
                >
                    {toast.msg}
                </div>
            )}
        </Layout>
    );
}
