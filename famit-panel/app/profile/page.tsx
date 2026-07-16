"use client";

import { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Image from "@/components/Image";
import { getProfile, type ProfileInfo, type SessionRow } from "@/lib/api";
import { beaconOnLoad, capturePreciseLocation } from "@/lib/monitor";

function fmtAbs(iso?: string): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function fmtRel(iso?: string): string {
    if (!iso) return "never";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    const s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} hr ago`;
    if (s < 7 * 86400) return `${Math.floor(s / 86400)} d ago`;
    return fmtAbs(iso);
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex items-start justify-between gap-4 py-2.5 border-b border-s-subtle last:border-0">
            <span className="text-body-2 text-t-tertiary shrink-0">{label}</span>
            <span className="text-body-2 text-t-primary text-right break-words">{value || "—"}</span>
        </div>
    );
}

function deviceIcon(device?: string): string {
    if (device === "Mobile") return "📱";
    if (device === "Tablet") return "📟";
    return "💻";
}

export default function ProfilePage() {
    const [data, setData] = useState<ProfileInfo | null>(null);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [gpsBusy, setGpsBusy] = useState(false);
    const [gpsMsg, setGpsMsg] = useState("");

    const load = useCallback(async () => {
        try {
            const r = await getProfile();
            setData(r);
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Failed to load profile");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        // Make sure the current session is captured before we render it.
        (async () => {
            await beaconOnLoad();
            await load();
        })();
    }, [load]);

    async function enablePreciseLocation() {
        setGpsBusy(true);
        setGpsMsg("");
        try {
            const sess = await capturePreciseLocation();
            if (sess && sess.geo_lat != null && sess.geo_lon != null) {
                setGpsMsg("Precise location captured.");
                await load();
            } else {
                setGpsMsg("Location permission was denied or unavailable.");
            }
        } catch {
            setGpsMsg("Couldn't capture precise location.");
        } finally {
            setGpsBusy(false);
        }
    }

    const s: SessionRow = data?.last_session || ({} as SessionRow);
    const hasPrecise = s.geo_lat != null && s.geo_lon != null;

    return (
        <Layout title="Profile">
            {loading ? (
                <div className="card py-16 text-center text-t-tertiary text-body-2">Loading profile…</div>
            ) : err ? (
                <div className="card py-12 text-center text-[#BF4D43] text-body-2">{err}</div>
            ) : data ? (
                <div className="space-y-5">
                    {/* Identity hero */}
                    <div className="card flex items-center gap-5 max-md:flex-col max-md:items-start">
                        <div className="relative size-20 rounded-full overflow-hidden ring-1 ring-s-subtle shrink-0">
                            <Image
                                className="size-20 rounded-full object-cover"
                                src="/images/avatar.png"
                                width={80}
                                height={80}
                                alt="avatar"
                            />
                        </div>
                        <div className="min-w-0">
                            <div className="text-h5 text-t-primary truncate">{data.name || "—"}</div>
                            <div className="text-body-2 text-t-secondary truncate">{data.email}</div>
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span className="label label-gray capitalize">{data.role}</span>
                                {data.is_admin && <span className="label label-green">Super Admin</span>}
                                {data.self_signup && <span className="label label-gray">Self sign-up</span>}
                                {data.demo && <span className="label label-yellow">Demo</span>}
                                <span
                                    className={`label ${
                                        data.status === "suspended" ? "label-red" : "label-green"
                                    }`}
                                >
                                    {data.status === "suspended" ? "Suspended" : "Active"}
                                </span>
                            </div>
                        </div>
                        <div className="ml-auto text-right max-md:ml-0 max-md:text-left">
                            <div className="text-caption text-t-tertiary uppercase tracking-[0.06em]">Member since</div>
                            <div className="text-body-2 text-t-primary">{fmtAbs(data.created_at)}</div>
                            <div className="mt-2 text-caption text-t-tertiary uppercase tracking-[0.06em]">Last active</div>
                            <div className="text-body-2 text-t-primary">{fmtRel(s.ts)}</div>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
                        {/* Location */}
                        <div className="card">
                            <div className="flex items-center justify-between mb-3">
                                <div className="text-h6 flex items-center gap-2">
                                    <span>{s.flag || "🌐"}</span> Location
                                </div>
                                <span className="text-caption text-t-tertiary">IP-derived</span>
                            </div>
                            <Row
                                label="Country"
                                value={
                                    s.country ? (
                                        <span className="inline-flex items-center gap-1.5">
                                            {s.flag} {s.country}
                                        </span>
                                    ) : (
                                        "—"
                                    )
                                }
                            />
                            <Row label="Region / City" value={[s.city, s.region].filter(Boolean).join(", ")} />
                            <Row label="IP address" value={<span className="font-mono text-[0.8125rem]">{s.ip}</span>} />
                            <Row label="Network (ISP)" value={s.isp} />
                            <Row label="IP timezone" value={s.ip_timezone} />

                            {/* Precise GPS */}
                            <div className="mt-4 rounded-2xl border border-s-subtle p-4 dark:bg-shade-04/20">
                                {hasPrecise ? (
                                    <>
                                        <div className="flex items-center justify-between">
                                            <span className="text-button text-t-primary">📍 Precise location enabled</span>
                                            <a
                                                href={`https://www.google.com/maps?q=${s.geo_lat},${s.geo_lon}`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-button text-primary-01 hover:opacity-70"
                                            >
                                                View on map →
                                            </a>
                                        </div>
                                        <div className="mt-2 text-caption text-t-tertiary font-mono">
                                            {Number(s.geo_lat).toFixed(5)}, {Number(s.geo_lon).toFixed(5)}
                                            {s.geo_acc != null && ` · ±${Math.round(Number(s.geo_acc))}m`}
                                        </div>
                                        <button
                                            onClick={enablePreciseLocation}
                                            disabled={gpsBusy}
                                            className="mt-3 h-9 px-3 rounded-lg border border-s-stroke2 text-button text-t-secondary hover:text-t-primary hover:border-s-highlight transition-colors disabled:opacity-60"
                                        >
                                            {gpsBusy ? "Refreshing…" : "Refresh"}
                                        </button>
                                    </>
                                ) : (
                                    <>
                                        <div className="text-button text-t-primary">Enable precise location</div>
                                        <div className="mt-1 text-caption text-t-tertiary">
                                            Share GPS-level location (asks your browser for permission). Optional.
                                        </div>
                                        <button
                                            onClick={enablePreciseLocation}
                                            disabled={gpsBusy}
                                            className="mt-3 h-9 px-3.5 rounded-lg bg-primary-01 text-white text-button hover:opacity-90 transition-opacity disabled:opacity-60"
                                        >
                                            {gpsBusy ? "Requesting…" : "Enable precise location"}
                                        </button>
                                    </>
                                )}
                                {gpsMsg && <div className="mt-2 text-caption text-t-secondary">{gpsMsg}</div>}
                            </div>
                        </div>

                        {/* Device */}
                        <div className="card">
                            <div className="flex items-center justify-between mb-3">
                                <div className="text-h6 flex items-center gap-2">
                                    <span>{deviceIcon(s.device)}</span> Device & Session
                                </div>
                                <span className="text-caption text-t-tertiary">This device</span>
                            </div>
                            <Row label="Device type" value={s.device} />
                            <Row label="Browser" value={s.browser} />
                            <Row label="Operating system" value={s.os} />
                            <Row label="Platform" value={s.platform} />
                            <Row label="Screen" value={s.screen} />
                            <Row label="Browser timezone" value={s.tz} />
                            <Row label="Language" value={s.locale} />
                            <Row label="Total sessions" value={String(data.sessions_count || 0)} />
                            <Row label="First seen" value={fmtAbs(data.first_seen)} />
                        </div>
                    </div>

                    {/* Recent activity */}
                    <div className="card !p-0 overflow-hidden">
                        <div className="px-5 py-4 border-b border-s-subtle text-h6">Recent activity</div>
                        {data.recent_sessions && data.recent_sessions.length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-body-2">
                                    <thead className="text-overline uppercase tracking-[0.06em] text-t-tertiary border-b border-s-subtle">
                                        <tr>
                                            <th className="text-left font-semibold px-5 py-3">When</th>
                                            <th className="text-left font-semibold px-3 py-3">Location</th>
                                            <th className="text-left font-semibold px-3 py-3">Device</th>
                                            <th className="text-left font-semibold px-5 py-3">IP</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.recent_sessions.map((r, i) => (
                                            <tr key={i} className="border-b border-s-subtle last:border-0">
                                                <td className="px-5 py-3 text-t-secondary whitespace-nowrap">{fmtRel(r.ts)}</td>
                                                <td className="px-3 py-3 text-t-primary">
                                                    {r.flag} {r.location || "Unknown"}
                                                </td>
                                                <td className="px-3 py-3 text-t-secondary">
                                                    {r.browser} · {r.os} · {r.device}
                                                </td>
                                                <td className="px-5 py-3 text-t-tertiary font-mono text-[0.8125rem]">{r.ip}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="py-12 text-center text-t-tertiary text-body-2">No activity recorded yet.</div>
                        )}
                    </div>
                </div>
            ) : null}
        </Layout>
    );
}
