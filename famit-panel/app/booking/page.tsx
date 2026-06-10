"use client";

// Booking — Appointments / Site-Visit scheduling.
//
// Premium console for the Postgres-native Booking engine (droplet_work/booking).
// Composes the panel's shared premium primitives (Layout, PageHeader, Card,
// KpiCard, data-table, surface modal, pills, state-block) — NOT generic.
//
// DORMANT-SAFE BY DESIGN: the backend module is built but not yet mounted/
// deployed. Every call routes through ./api which resolves unmounted/unreachable
// endpoints (and the engine's own {status:"not_configured"} when Postgres is
// down) to a typed dormant sentinel. When dormant, the page renders a calm
// "coming soon / not configured" activation panel instead of erroring. The
// moment the orchestrator mounts the router, live data flows with no FE change.
//
// This file + ./api.ts are the ONLY files this page owns. No shared files
// (globals.css, navigation, lib/api) are touched.

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import KpiCard from "@/components/KpiCard";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { useMe, canWrite } from "@/lib/auth";
import {
    getBookingStatus,
    listBookings,
    getAvailability,
    book,
    cancelBooking,
    completeBooking,
    rescheduleBooking,
    tick,
    isDormant,
    type BookingConfig,
    type BookingRow,
    type FreeSlot,
    type TickResult,
} from "./api";

// ---------------------------------------------------------------------------
// small formatting helpers
// ---------------------------------------------------------------------------
function fmtDateTime(iso?: string) {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleString(undefined, {
            day: "2-digit",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}
function fmtTime(iso?: string) {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}
function todayISO() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate()
    ).padStart(2, "0")}`;
}

const STATUS_TONE: Record<string, string> = {
    booked: "pill-info",
    rescheduled: "pill-warning",
    completed: "pill-success",
    cancelled: "pill-neutral",
    no_show: "pill-danger",
};
function StatusPill({ status }: { status: string }) {
    const tone = STATUS_TONE[status] || "pill-neutral";
    const label = (status || "—").replace(/_/g, " ");
    return (
        <span className={`pill ${tone}`}>
            <span className="pill-dot" />
            {label}
        </span>
    );
}

type Toast = { msg: string; type: "success" | "error" };

// ===========================================================================
// Page
// ===========================================================================
export default function BookingPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    // module status / dormancy
    const [cfg, setCfg] = useState<BookingConfig | null>(null);
    const [dormant, setDormant] = useState(false);
    const [statusLoaded, setStatusLoaded] = useState(false);

    // bookings
    const [bookings, setBookings] = useState<BookingRow[]>([]);
    const [bookingsLoading, setBookingsLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState("");

    // reminder/no-show preview (tick dry-run)
    const [preview, setPreview] = useState<TickResult | null>(null);
    const [previewLoading, setPreviewLoading] = useState(false);

    // book modal
    const [bookOpen, setBookOpen] = useState(false);

    // reschedule modal
    const [reschedTarget, setReschedTarget] = useState<BookingRow | null>(null);

    const [toast, setToast] = useState<Toast | null>(null);
    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    // ---- loaders --------------------------------------------------------
    const loadStatus = useCallback(async () => {
        const r = await getBookingStatus();
        if (isDormant(r)) {
            setDormant(true);
            setStatusLoaded(true);
            return;
        }
        setCfg(r.booking);
        // The engine reports pg_available=false when Postgres is down — treat
        // that as dormant for the data surfaces, but still show the status card.
        setDormant(!r.booking?.pg_available);
        setStatusLoaded(true);
    }, []);

    const loadBookings = useCallback(async () => {
        setBookingsLoading(true);
        const r = await listBookings({ status: statusFilter, limit: 200 });
        if (isDormant(r)) {
            setBookings([]);
            setBookingsLoading(false);
            return;
        }
        setBookings(r.bookings || []);
        setBookingsLoading(false);
    }, [statusFilter]);

    const loadPreview = useCallback(async () => {
        setPreviewLoading(true);
        const r = await tick(true); // dry-run: previews due reminders + no-shows, enqueues nothing
        if (isDormant(r)) {
            setPreview(null);
            setPreviewLoading(false);
            return;
        }
        setPreview(r);
        setPreviewLoading(false);
    }, []);

    useEffect(() => {
        loadStatus();
    }, [loadStatus]);

    useEffect(() => {
        if (!statusLoaded) return;
        loadBookings();
        if (!dormant) loadPreview();
    }, [statusLoaded, dormant, loadBookings, loadPreview]);

    // ---- derived KPIs ---------------------------------------------------
    const kpis = useMemo(() => {
        const now = Date.now();
        const upcoming = bookings.filter(
            (b) =>
                (b.status === "booked" || b.status === "rescheduled") &&
                new Date(b.slot_start).getTime() >= now
        ).length;
        const completed = bookings.filter((b) => b.status === "completed").length;
        const noShow = bookings.filter((b) => b.status === "no_show").length;
        const active = bookings.filter(
            (b) => b.status === "booked" || b.status === "rescheduled"
        ).length;
        const total = bookings.length;
        const showRate =
            completed + noShow > 0
                ? Math.round((completed / (completed + noShow)) * 100)
                : null;
        return { upcoming, completed, noShow, active, total, showRate };
    }, [bookings]);

    // ---- actions --------------------------------------------------------
    async function handleCancel(b: BookingRow) {
        if (!confirm(`Cancel the appointment for ${b.name || b.phone_display || "this contact"}?`))
            return;
        const r = await cancelBooking(b.id);
        if (isDormant(r)) return showToast("Booking engine not available", "error");
        if (r.status === "ok" || r.status === "noop") {
            showToast(r.status === "noop" ? "Already inactive" : "Appointment cancelled");
            loadBookings();
        } else {
            showToast(r.reason || "Could not cancel", "error");
        }
    }

    async function handleComplete(b: BookingRow) {
        const r = await completeBooking(b.id);
        if (isDormant(r)) return showToast("Booking engine not available", "error");
        if (r.ok || r.status === "ok") {
            showToast("Marked completed");
            loadBookings();
        } else if (r.status === "noop") {
            showToast("Already inactive", "error");
        } else {
            showToast(r.reason || "Could not update", "error");
        }
    }

    // ===================================================================
    // Render
    // ===================================================================
    return (
        <Layout title="Booking">
            <PageHeader
                eyebrow="Engage"
                title="Booking"
                subtitle="Appointments, site visits and demos — atomic slot booking on the CRM contact spine, with reminders and no-show follow-up."
                actions={
                    writable && !dormant ? (
                        <Button isBlack onClick={() => setBookOpen(true)}>
                            <Icon name="plus" className="fill-inherit" />
                            New appointment
                        </Button>
                    ) : undefined
                }
            />

            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button
                        onClick={() => setToast(null)}
                        className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* KPI strip */}
            <div className="grid grid-cols-4 gap-6 max-2xl:grid-cols-2 max-md:grid-cols-1 mb-6">
                <KpiCard
                    label="Upcoming"
                    value={dormant ? "—" : kpis.upcoming}
                    icon="calendar"
                    tone="info"
                    sub={`${kpis.active} active`}
                />
                <KpiCard
                    label="Completed"
                    value={dormant ? "—" : kpis.completed}
                    icon="check"
                    tone="success"
                    sub={kpis.showRate != null ? `${kpis.showRate}% show rate` : "no outcomes yet"}
                    meter={kpis.showRate != null ? kpis.showRate / 100 : null}
                />
                <KpiCard
                    label="No-shows"
                    value={dormant ? "—" : kpis.noShow}
                    icon="warning"
                    tone="danger"
                    sub="missed appointments"
                />
                <KpiCard
                    label="Due reminders"
                    value={dormant ? "—" : preview ? preview.fired.length : previewLoading ? "…" : 0}
                    icon="bell"
                    tone="warning"
                    sub={
                        preview && preview.no_shows.length > 0
                            ? `${preview.no_shows.length} no-show to sweep`
                            : "scheduled nudges"
                    }
                />
            </div>

            {dormant ? (
                <DormantPanel cfg={cfg} loaded={statusLoaded} />
            ) : (
                <div className="flex gap-6 max-xl:flex-col">
                    {/* Left: bookings table */}
                    <div className="flex-1 min-w-0">
                        <Card
                            title="Appointments"
                            headContent={
                                <div className="flex items-center gap-1 mr-3">
                                    {["", "booked", "completed", "no_show", "cancelled"].map((s) => (
                                        <button
                                            key={s || "all"}
                                            onClick={() => setStatusFilter(s)}
                                            className={`px-3 h-8 rounded-full text-button transition-colors ${
                                                statusFilter === s
                                                    ? "bg-b-surface1 text-t-primary"
                                                    : "text-t-secondary hover:text-t-primary"
                                            }`}
                                        >
                                            {s ? s.replace(/_/g, " ") : "All"}
                                        </button>
                                    ))}
                                </div>
                            }
                        >
                            <div className="overflow-x-auto">
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th>Contact</th>
                                            <th>When</th>
                                            <th>Title</th>
                                            <th>Status</th>
                                            <th className="text-right">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {bookingsLoading ? (
                                            [...Array(5)].map((_, i) => (
                                                <tr key={i}>
                                                    {[...Array(5)].map((__, j) => (
                                                        <td key={j}>
                                                            <div className="skeleton h-4 w-24" />
                                                        </td>
                                                    ))}
                                                </tr>
                                            ))
                                        ) : bookings.length === 0 ? (
                                            <tr>
                                                <td colSpan={5}>
                                                    <div className="state-block">
                                                        <span className="state-glyph">
                                                            <Icon name="calendar" className="fill-inherit" />
                                                        </span>
                                                        <div className="state-title">No appointments yet</div>
                                                        <div className="state-sub">
                                                            {writable
                                                                ? "Book your first appointment — pick a free slot and a contact."
                                                                : "Appointments booked by your team will appear here."}
                                                        </div>
                                                        {writable && (
                                                            <Button
                                                                className="mt-4"
                                                                isStroke
                                                                onClick={() => setBookOpen(true)}
                                                            >
                                                                <Icon name="plus" className="fill-inherit" />
                                                                New appointment
                                                            </Button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ) : (
                                            bookings.map((b) => {
                                                const active =
                                                    b.status === "booked" || b.status === "rescheduled";
                                                return (
                                                    <tr key={b.id}>
                                                        <td>
                                                            <div className="font-medium text-t-primary">
                                                                {b.name || "—"}
                                                            </div>
                                                            <div className="text-caption text-t-secondary">
                                                                {b.phone_display || b.contact_id}
                                                            </div>
                                                        </td>
                                                        <td className="text-t-secondary whitespace-nowrap">
                                                            {fmtDateTime(b.slot_start)}
                                                        </td>
                                                        <td className="text-t-secondary">
                                                            {b.title || "Appointment"}
                                                        </td>
                                                        <td>
                                                            <StatusPill status={b.status} />
                                                        </td>
                                                        <td>
                                                            <div className="flex items-center gap-2 justify-end">
                                                                {writable && active && (
                                                                    <>
                                                                        <button
                                                                            onClick={() => handleComplete(b)}
                                                                            className="action"
                                                                            title="Mark completed"
                                                                        >
                                                                            Complete
                                                                        </button>
                                                                        <button
                                                                            onClick={() => setReschedTarget(b)}
                                                                            className="action"
                                                                            title="Reschedule"
                                                                        >
                                                                            Reschedule
                                                                        </button>
                                                                        <button
                                                                            onClick={() => handleCancel(b)}
                                                                            className="action hover:!text-primary-03 hover:!border-primary-03/30"
                                                                            title="Cancel"
                                                                        >
                                                                            Cancel
                                                                        </button>
                                                                    </>
                                                                )}
                                                                {!active && (
                                                                    <span className="text-caption text-t-tertiary">
                                                                        —
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                );
                                            })
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </Card>
                    </div>

                    {/* Right: operations rail */}
                    <div className="w-96 max-xl:w-full shrink-0 space-y-6">
                        <OperationsCard
                            preview={preview}
                            loading={previewLoading}
                            cfg={cfg}
                            onRefresh={loadPreview}
                        />
                        <IntegrationsCard cfg={cfg} />
                    </div>
                </div>
            )}

            {bookOpen && (
                <BookModal
                    defaultTz={cfg?.default_timezone || "Asia/Kolkata"}
                    defaultSlotMinutes={cfg?.default_slot_minutes || 30}
                    onClose={() => setBookOpen(false)}
                    onBooked={() => {
                        setBookOpen(false);
                        showToast("Appointment booked");
                        loadBookings();
                    }}
                    onError={(m) => showToast(m, "error")}
                />
            )}

            {reschedTarget && (
                <RescheduleModal
                    booking={reschedTarget}
                    onClose={() => setReschedTarget(null)}
                    onDone={(ok, msg) => {
                        setReschedTarget(null);
                        showToast(msg, ok ? "success" : "error");
                        if (ok) loadBookings();
                    }}
                />
            )}
        </Layout>
    );
}

// ===========================================================================
// Dormant activation panel — calm, premium "not configured / coming soon".
// ===========================================================================
function DormantPanel({
    cfg,
    loaded,
}: {
    cfg: BookingConfig | null;
    loaded: boolean;
}) {
    const checklist = [
        {
            label: "Postgres spine (core booking)",
            ok: !!cfg?.pg_available,
            note: cfg?.pg_available
                ? "Connected"
                : "Required for availability + atomic slot booking",
        },
        {
            label: "Reminders & no-show follow-up",
            ok: !!cfg?.reminders_enabled,
            note: cfg?.reminders_enabled ? "Enabled" : "BOOKING_REMINDERS_ENABLED off",
        },
        {
            label: "Google Calendar two-way sync",
            ok: !!cfg?.calendar_configured,
            note: cfg?.calendar_configured
                ? "Connected"
                : "Awaiting Google OAuth credentials",
        },
    ];
    return (
        <div className="surface p-8 rise-in">
            <div className="flex items-start gap-5 max-md:flex-col">
                <span className="flex items-center justify-center size-14 rounded-2xl bg-b-surface1 fill-t-secondary shrink-0">
                    <Icon name="calendar" className="fill-inherit !size-7" />
                </span>
                <div className="min-w-0 flex-1">
                    <h2 className="text-h5 text-t-primary mb-1">Booking is being activated</h2>
                    <p className="text-body-2 text-t-secondary max-w-xl">
                        The appointment engine — atomic slot booking, reminders, no-show
                        follow-up and Google Calendar sync — is built and ready. It will go
                        live for your workspace as soon as the data spine is connected. No
                        setup needed on your side.
                    </p>

                    <div className="mt-6 space-y-2 max-w-xl">
                        {checklist.map((c) => (
                            <div
                                key={c.label}
                                className="flex items-center gap-3 p-3 rounded-2xl bg-b-surface1"
                            >
                                <span
                                    className={`flex items-center justify-center size-6 rounded-full shrink-0 ${
                                        c.ok
                                            ? "bg-primary-02/15 fill-primary-02"
                                            : "bg-b-surface2 fill-t-tertiary"
                                    }`}
                                >
                                    <Icon
                                        name={c.ok ? "check" : "clock"}
                                        className="fill-inherit !size-3.5"
                                    />
                                </span>
                                <div className="min-w-0 flex-1">
                                    <div className="text-button text-t-primary">{c.label}</div>
                                    <div className="text-caption text-t-secondary">{c.note}</div>
                                </div>
                                <span className={`pill ${c.ok ? "pill-success" : "pill-neutral"}`}>
                                    <span className="pill-dot" />
                                    {c.ok ? "ready" : "pending"}
                                </span>
                            </div>
                        ))}
                    </div>

                    {!loaded && (
                        <div className="mt-4 text-caption text-t-tertiary">Checking status…</div>
                    )}
                    {loaded && !cfg && (
                        <div className="mt-4 text-caption text-t-tertiary">
                            The booking service isn’t reachable yet — this page will populate
                            automatically once it’s online.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ===========================================================================
// Operations card — reminder/no-show dry-run preview (enqueues NOTHING).
// ===========================================================================
function OperationsCard({
    preview,
    loading,
    cfg,
    onRefresh,
}: {
    preview: TickResult | null;
    loading: boolean;
    cfg: BookingConfig | null;
    onRefresh: () => void;
}) {
    const due = preview?.fired || [];
    const noShows = preview?.no_shows || [];
    const skipped = preview?.skipped || [];
    return (
        <Card
            title="Operations"
            headContent={
                <button
                    onClick={onRefresh}
                    className="action mr-3"
                    title="Re-run preview"
                    disabled={loading}
                >
                    {loading ? "…" : "Refresh"}
                </button>
            }
        >
            <div className="px-5 pb-5 space-y-4">
                <p className="text-caption text-t-secondary">
                    A safe, read-only preview of what the scheduler would do on the next
                    pass. Nothing is sent — reminders actuate only behind the PIN + wallet
                    gates.
                </p>

                <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-2xl bg-b-surface1">
                        <div className="text-caption text-t-secondary">Reminders due</div>
                        <div className="text-h5 text-t-primary tabular-nums">{due.length}</div>
                    </div>
                    <div className="p-3 rounded-2xl bg-b-surface1">
                        <div className="text-caption text-t-secondary">No-shows to sweep</div>
                        <div className="text-h5 text-t-primary tabular-nums">{noShows.length}</div>
                    </div>
                </div>

                {due.length > 0 && (
                    <div className="space-y-2">
                        <div className="text-caption text-t-secondary uppercase tracking-wide">
                            Next nudges
                        </div>
                        {due.slice(0, 4).map((c) => (
                            <div
                                key={c.reminder_id}
                                className="flex items-center gap-2 text-body-2 text-t-secondary"
                            >
                                <span className="flex items-center justify-center size-6 rounded-lg bg-b-surface1 fill-t-secondary">
                                    <Icon name="bell" className="fill-inherit !size-3.5" />
                                </span>
                                <span className="capitalize">{c.kind.replace(/_/g, " ")}</span>
                                <span className="text-t-tertiary">· {c.channel}</span>
                            </div>
                        ))}
                    </div>
                )}

                {skipped.length > 0 && (
                    <div className="text-caption text-t-tertiary">
                        {skipped.length} held back (PIN required / already fired).
                    </div>
                )}

                <div className="flex items-center gap-2 pt-1">
                    <span
                        className={`pill ${
                            cfg?.reminders_enabled ? "pill-success" : "pill-neutral"
                        }`}
                    >
                        <span className="pill-dot" />
                        {cfg?.reminders_enabled ? "Reminders on" : "Reminders off"}
                    </span>
                    <span className="text-caption text-t-tertiary">
                        grace {cfg?.no_show_grace_minutes ?? 15}m
                    </span>
                </div>
            </div>
        </Card>
    );
}

// ===========================================================================
// Integrations card — calendar sync status (dormant-aware, redacted booleans).
// ===========================================================================
function IntegrationsCard({ cfg }: { cfg: BookingConfig | null }) {
    const calOk = !!cfg?.calendar_configured;
    return (
        <Card title="Integrations">
            <div className="px-5 pb-5 space-y-3">
                <div className="flex items-center gap-3 p-3 rounded-2xl bg-b-surface1">
                    <span className="flex items-center justify-center size-9 rounded-xl bg-b-surface2 fill-t-secondary shrink-0">
                        <Icon name="calendar" className="fill-inherit" />
                    </span>
                    <div className="min-w-0 flex-1">
                        <div className="text-button text-t-primary">Google Calendar</div>
                        <div className="text-caption text-t-secondary">
                            {calOk
                                ? "Two-way sync active"
                                : cfg?.calendar_sync_enabled
                                ? "Enabled — awaiting credentials"
                                : "Two-way sync — coming soon"}
                        </div>
                    </div>
                    <span className={`pill ${calOk ? "pill-success" : "pill-neutral"}`}>
                        <span className="pill-dot" />
                        {calOk ? "connected" : "soon"}
                    </span>
                </div>
                <p className="text-caption text-t-tertiary">
                    Time zone {cfg?.default_timezone || "Asia/Kolkata"} · default slot{" "}
                    {cfg?.default_slot_minutes ?? 30}m
                </p>
            </div>
        </Card>
    );
}

// ===========================================================================
// Book modal — pick a resource + free slot (live availability) and a contact.
// ===========================================================================
function BookModal({
    defaultTz,
    defaultSlotMinutes,
    onClose,
    onBooked,
    onError,
}: {
    defaultTz: string;
    defaultSlotMinutes: number;
    onClose: () => void;
    onBooked: () => void;
    onError: (m: string) => void;
}) {
    const [resourceId, setResourceId] = useState("");
    const [day, setDay] = useState(todayISO());
    const [slots, setSlots] = useState<FreeSlot[]>([]);
    const [slotsLoading, setSlotsLoading] = useState(false);
    const [slotsTried, setSlotsTried] = useState(false);
    const [selected, setSelected] = useState<FreeSlot | null>(null);

    const [name, setName] = useState("");
    const [phone, setPhone] = useState("");
    const [title, setTitle] = useState("");
    const [notes, setNotes] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        const h = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", h);
        return () => document.removeEventListener("keydown", h);
    }, [onClose]);

    async function loadSlots() {
        if (!resourceId.trim()) return;
        setSlotsLoading(true);
        setSlotsTried(true);
        setSelected(null);
        const r = await getAvailability(resourceId.trim(), day);
        setSlotsLoading(false);
        if (isDormant(r)) {
            setSlots([]);
            return;
        }
        if (r.status === "ok") {
            setSlots(r.free || []);
        } else {
            setSlots([]);
            onError(r.reason ? r.reason.replace(/_/g, " ") : "Could not load availability");
        }
    }

    async function submit() {
        if (!resourceId.trim() || !phone.trim()) {
            onError("Resource and contact phone are required");
            return;
        }
        // slot_start: a chosen free slot, or a manual ISO fallback from day+now.
        const slot_start = selected?.slot_start;
        if (!slot_start) {
            onError("Pick a free slot first");
            return;
        }
        setSubmitting(true);
        const r = await book({
            resource_id: resourceId.trim(),
            phone: phone.trim(),
            slot_start,
            slot_end: selected?.slot_end,
            name: name.trim(),
            title: title.trim(),
            notes: notes.trim(),
            source: "panel",
        });
        setSubmitting(false);
        if (isDormant(r)) return onError("Booking engine not available");
        if (r.ok || r.status === "ok") {
            onBooked();
        } else if (r.status === "conflict") {
            onError("That slot was just taken — pick another");
            loadSlots();
        } else {
            onError(r.reason ? r.reason.replace(/_/g, " ") : "Could not book");
        }
    }

    return (
        <ModalShell title="New appointment" onClose={onClose}>
            <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
                <Field label="Resource ID">
                    <input
                        value={resourceId}
                        onChange={(e) => setResourceId(e.target.value)}
                        placeholder="res_…"
                        className={inputCls}
                    />
                </Field>
                <Field label="Day">
                    <input
                        type="date"
                        value={day}
                        onChange={(e) => setDay(e.target.value)}
                        className={inputCls}
                    />
                </Field>
            </div>

            <div className="mt-3">
                <Button isStroke className="w-full justify-center" onClick={loadSlots} disabled={slotsLoading || !resourceId.trim()}>
                    {slotsLoading ? "Loading slots…" : "Find free slots"}
                </Button>
            </div>

            {slotsTried && (
                <div className="mt-4">
                    <label className="block text-button mb-2 text-t-primary">
                        Free slots ({defaultSlotMinutes}m · {defaultTz})
                    </label>
                    {slotsLoading ? (
                        <div className="grid grid-cols-4 gap-2">
                            {[...Array(8)].map((_, i) => (
                                <div key={i} className="skeleton h-10 rounded-2xl" />
                            ))}
                        </div>
                    ) : slots.length === 0 ? (
                        <div className="text-caption text-t-secondary p-4 rounded-2xl bg-b-surface1">
                            No free slots for this day. Check the resource ID and availability
                            windows, or pick another day.
                        </div>
                    ) : (
                        <div className="grid grid-cols-4 gap-2 max-h-44 overflow-y-auto max-md:grid-cols-3">
                            {slots.map((s) => {
                                const on = selected?.slot_start === s.slot_start;
                                return (
                                    <button
                                        key={s.slot_start}
                                        onClick={() => setSelected(s)}
                                        className={`h-10 rounded-2xl text-body-2 border transition-colors ${
                                            on
                                                ? "border-s-highlight bg-b-surface1 text-t-primary"
                                                : "border-s-stroke2 text-t-secondary hover:border-s-highlight"
                                        }`}
                                    >
                                        {fmtTime(s.slot_start)}
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            <div className="mt-4 grid grid-cols-2 gap-4 max-md:grid-cols-1">
                <Field label="Contact name">
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Rohan Mehta" className={inputCls} />
                </Field>
                <Field label="Phone">
                    <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91…" className={inputCls} />
                </Field>
            </div>
            <div className="mt-3">
                <Field label="Title">
                    <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Site visit / demo" className={inputCls} />
                </Field>
            </div>
            <div className="mt-3">
                <Field label="Notes">
                    <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Anything the agent should know"
                        className={`${inputCls} h-20 py-2 resize-none`}
                    />
                </Field>
            </div>

            <div className="mt-5 flex items-center justify-end gap-3">
                <Button isStroke onClick={onClose}>
                    Cancel
                </Button>
                <Button isBlack onClick={submit} disabled={submitting || !selected}>
                    {submitting ? "Booking…" : "Book appointment"}
                </Button>
            </div>
        </ModalShell>
    );
}

// ===========================================================================
// Reschedule modal
// ===========================================================================
function RescheduleModal({
    booking,
    onClose,
    onDone,
}: {
    booking: BookingRow;
    onClose: () => void;
    onDone: (ok: boolean, msg: string) => void;
}) {
    const [value, setValue] = useState<string>(() => {
        try {
            const d = new Date(booking.slot_start);
            // datetime-local needs local time without seconds
            const off = d.getTimezoneOffset();
            const local = new Date(d.getTime() - off * 60000);
            return local.toISOString().slice(0, 16);
        } catch {
            return "";
        }
    });
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        const h = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", h);
        return () => document.removeEventListener("keydown", h);
    }, [onClose]);

    async function submit() {
        if (!value) return onDone(false, "Pick a new date and time");
        const iso = new Date(value).toISOString();
        setSubmitting(true);
        const r = await rescheduleBooking(booking.id, iso);
        setSubmitting(false);
        if (isDormant(r)) return onDone(false, "Booking engine not available");
        if (r.ok || r.status === "ok") return onDone(true, "Appointment rescheduled");
        if (r.status === "conflict") return onDone(false, "That new slot is already taken");
        return onDone(false, r.reason ? r.reason.replace(/_/g, " ") : "Could not reschedule");
    }

    return (
        <ModalShell title="Reschedule appointment" onClose={onClose}>
            <p className="text-body-2 text-t-secondary mb-4">
                Moving{" "}
                <span className="text-t-primary font-medium">
                    {booking.name || booking.phone_display || "appointment"}
                </span>{" "}
                from {fmtDateTime(booking.slot_start)}.
            </p>
            <Field label="New date & time">
                <input
                    type="datetime-local"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    className={inputCls}
                />
            </Field>
            <div className="mt-5 flex items-center justify-end gap-3">
                <Button isStroke onClick={onClose}>
                    Cancel
                </Button>
                <Button isBlack onClick={submit} disabled={submitting}>
                    {submitting ? "Rescheduling…" : "Confirm new time"}
                </Button>
            </div>
        </ModalShell>
    );
}

// ===========================================================================
// shared modal shell + field + input class (premium "surface" + backdrop blur)
// ===========================================================================
function ModalShell({
    title,
    onClose,
    children,
}: {
    title: string;
    onClose: () => void;
    children: React.ReactNode;
}) {
    function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
        if (e.target === e.currentTarget) onClose();
    }
    return (
        <div
            className="fixed inset-0 z-50 bg-shade-01/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={handleBackdrop}
        >
            <div className="surface w-full max-w-2xl max-h-[90vh] flex flex-col rise-in">
                <div className="flex items-center justify-between p-5 border-b border-s-subtle shrink-0">
                    <div className="flex items-center gap-2.5">
                        <span className="signal-glyph !h-3.5" aria-hidden>
                            <i />
                            <i />
                            <i />
                        </span>
                        <h2 className="text-h6 text-t-primary">{title}</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="flex items-center justify-center size-8 rounded-full text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04"
                    >
                        ×
                    </button>
                </div>
                <div className="overflow-y-auto p-5">{children}</div>
            </div>
        </div>
    );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-caption text-t-secondary mb-2">{label}</label>
            {children}
        </div>
    );
}

const inputCls =
    "w-full h-11 px-4 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none transition-colors bg-transparent hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50";
