"use client";

// AI MANAGER — SETUP tab (Setup profile + Authorized users + What it can do).
//
// One settings surface with anchored sections (SettingsPage rhythm): the engine
// profile (enable, phone, language/voice, confirmation policy, spend caps, calling
// hours), the people allowed to command it, and a browseable catalog of what it
// can do — graded in plain language (Safe / Low / Medium / High / Blocked), never
// raw L-codes. No masthead: the title is the single `<Layout title>` in page.tsx.
//
// Data wiring stays in _lib.ts. Backend is DEFINED-NOT-MOUNTED today, so reads
// degrade to first-run defaults / a read-only banner rather than an error wall.

import { useCallback, useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import { useMe, canWrite, isAdmin } from "@/lib/auth";
import {
    ErrorBanner,
    FormRow,
    inputCls,
    selectCls,
    riskVariant,
    roleVariant,
    parseRiskVariant,
    parseRiskLabel,
    fmt,
} from "./_shared";
import {
    getAimProfile,
    putAimProfile,
    getAimUsers,
    createAimUser,
    patchAimUser,
    setAimUserPin,
    getAimNumbers,
    registerAimNumber,
    deleteAimNumber,
    changeFirewallPin,
    AIM_PROFILE_DEFAULTS,
    AIM_RISK_LEVELS,
    AIM_LANGUAGES,
    AIM_VOICE_PROVIDERS,
    AIM_TIMEZONES,
    AIM_ROLES,
    AIM_VERIFY_MODES,
    KNOWN_GRANTS,
    INTENT_CATALOG,
    BLOCKED_EXAMPLES,
    LIVE_MODULES,
    moduleGlyph,
    type AimProfile,
    type AimRiskLevel,
    type AimAuthUser,
    type AimRole,
    type AimNumber,
    type AimVerifyMode,
    type ReadResult,
} from "./_lib";

type Toast = { msg: string; type: "success" | "error" };

const SECTIONS = [
    { id: "general", label: "General", icon: "dashboard" },
    { id: "voice", label: "Voice & language", icon: "chat" },
    { id: "safety", label: "Confirmation & PIN", icon: "lock" },
    { id: "spend", label: "Spend limits", icon: "wallet" },
    { id: "hours", label: "Calling hours", icon: "clock" },
    { id: "numbers", label: "Phone numbers", icon: "mobile" },
    { id: "pin-change", label: "Change PIN", icon: "lock" },
    { id: "team", label: "Team", icon: "profile" },
    { id: "capabilities", label: "What it can do", icon: "grid" },
] as const;

function stripNulls(p: AimProfile): Partial<AimProfile> {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(p)) if (v !== null && v !== undefined) out[k] = v;
    return out as Partial<AimProfile>;
}
function numOrNull(s: string): number | null {
    if (s.trim() === "") return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
}
function isLocked(u: AimAuthUser): boolean {
    if (!u.locked_until) return false;
    const t = new Date(u.locked_until).getTime();
    return Number.isFinite(t) && t > Date.now();
}

export default function SetupTab() {
    const { me } = useMe();
    const writable = canWrite(me);
    const admin = isAdmin(me);

    const [toast, setToast] = useState<Toast | null>(null);
    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4200);
    };

    // ---- profile ----
    const [result, setResult] = useState<ReadResult<AimProfile> | null>(null);
    const [loading, setLoading] = useState(true);
    const [form, setForm] = useState<AimProfile>(AIM_PROFILE_DEFAULTS);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [saving, setSaving] = useState(false);

    // ---- users ----
    const [users, setUsers] = useState<ReadResult<{ users: AimAuthUser[] }> | null>(null);
    const [editOpen, setEditOpen] = useState(false);
    const [editing, setEditing] = useState<AimAuthUser | null>(null);
    const [pinFor, setPinFor] = useState<AimAuthUser | null>(null);

    // ---- numbers ----
    const [numbers, setNumbers] = useState<ReadResult<{ numbers: AimNumber[] }> | null>(null);
    const [numModalOpen, setNumModalOpen] = useState(false);

    const load = useCallback(() => {
        setLoading(true);
        Promise.all([
            getAimProfile().then((r) => {
                setResult(r);
                if (r.kind === "ok") setForm({ ...AIM_PROFILE_DEFAULTS, ...stripNulls(r.data) });
            }),
            getAimUsers().then(setUsers),
            getAimNumbers().then(setNumbers),
        ]).finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";
    const formDisabled = !writable || dormant;

    const userRows = useMemo(
        () => (users?.kind === "ok" ? users.data.users : []),
        [users]
    );

    function set<K extends keyof AimProfile>(key: K, value: AimProfile[K]) {
        setForm((f) => ({ ...f, [key]: value }));
    }

    async function doSave() {
        setSaving(true);
        try {
            await putAimProfile(form);
            showToast("AI Manager setup saved");
            setConfirmOpen(false);
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Save failed", "error");
        } finally {
            setSaving(false);
        }
    }

    async function toggleUser(u: AimAuthUser) {
        try {
            await patchAimUser(u.id, { is_active: !u.is_active });
            showToast(`${u.name} ${u.is_active ? "disabled" : "enabled"}`);
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Update failed", "error");
        }
    }

    return (
        <>
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">
                        ×
                    </button>
                </div>
            )}

            <ErrorBanner msg={error} />

            {dormant && (
                <div className="mb-4 flex items-start gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle">
                    <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-primary-01">
                        <Icon name="info" className="size-4.5 fill-inherit" />
                    </span>
                    <div className="min-w-0">
                        <div className="text-body-2 text-t-primary">Setup is read-only until the service is live</div>
                        <div className="text-caption text-t-tertiary mt-0.5">
                            These are the controls you&apos;ll tune once the AI Manager backend is provisioned. The
                            values below are the safe first-run defaults — saving is enabled the moment the service comes online.
                        </div>
                    </div>
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Sticky section menu */}
                <aside className="w-56 shrink-0 max-lg:w-full">
                    <div className="sticky top-22 max-lg:static">
                        <nav className="flex flex-col gap-1 max-lg:flex-row max-lg:flex-wrap max-lg:gap-2">
                            {SECTIONS.map((sct) => (
                                <a
                                    key={sct.id}
                                    href={`#${sct.id}`}
                                    className="inline-flex items-center gap-2.5 h-10 px-3 rounded-2xl text-button text-t-secondary fill-t-secondary transition-colors hover:bg-b-surface2 hover:text-t-primary hover:fill-t-primary"
                                >
                                    <Icon name={sct.icon} className="size-4.5 fill-inherit" />
                                    {sct.label}
                                </a>
                            ))}
                        </nav>
                        {writable && (
                            <div className="mt-4 max-lg:hidden">
                                <Button
                                    isBlack
                                    className="w-full justify-center"
                                    onClick={() => setConfirmOpen(true)}
                                    disabled={formDisabled || saving}
                                >
                                    Save changes
                                </Button>
                                {dormant && (
                                    <p className="text-caption text-t-tertiary mt-2 text-center">
                                        Saving unlocks when the service is live.
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                </aside>

                <div className="flex-1 min-w-0 space-y-3">
                    {loading && !result ? (
                        <SetupSkeleton />
                    ) : (
                        <>
                            {/* GENERAL */}
                            <section id="general" className="scroll-mt-24">
                                <Card title="General">
                                    <div className="px-5 pb-5 max-lg:px-3 space-y-5">
                                        <ToggleRow
                                            label="AI Manager enabled"
                                            hint="Master switch for the voice command engine on your account."
                                            on={form.enabled}
                                            disabled={formDisabled}
                                            onChange={(v) => set("enabled", v)}
                                        />
                                        <FormRow
                                            label="AI Manager phone number"
                                            hint="The number your managers call to issue commands. Provisioned with telephony."
                                        >
                                            <input
                                                type="text"
                                                value={form.ai_manager_phone_number ?? ""}
                                                onChange={(e) => set("ai_manager_phone_number", e.target.value || null)}
                                                placeholder="+91 80 4718 0000"
                                                className={inputCls}
                                                disabled={formDisabled}
                                            />
                                        </FormRow>
                                    </div>
                                </Card>
                            </section>

                            {/* VOICE & LANGUAGE */}
                            <section id="voice" className="scroll-mt-24">
                                <Card title="Voice & language">
                                    <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-2 gap-5 max-sm:grid-cols-1">
                                        <FormRow label="Language" hint="The language the AI speaks and understands by default.">
                                            <select
                                                value={form.language_preference ?? ""}
                                                onChange={(e) => set("language_preference", e.target.value)}
                                                className={selectCls}
                                                disabled={formDisabled}
                                            >
                                                {AIM_LANGUAGES.map((l) => (
                                                    <option key={l.value} value={l.value}>
                                                        {l.label}
                                                    </option>
                                                ))}
                                            </select>
                                        </FormRow>
                                        <FormRow label="Default voice provider" hint="Text-to-speech engine for the AI's spoken replies.">
                                            <select
                                                value={form.default_voice_provider ?? ""}
                                                onChange={(e) => set("default_voice_provider", e.target.value)}
                                                className={selectCls}
                                                disabled={formDisabled}
                                            >
                                                {AIM_VOICE_PROVIDERS.map((v) => (
                                                    <option key={v.value} value={v.value}>
                                                        {v.label}
                                                    </option>
                                                ))}
                                            </select>
                                        </FormRow>
                                    </div>
                                </Card>
                            </section>

                            {/* CONFIRMATION & PIN */}
                            <section id="safety" className="scroll-mt-24">
                                <Card
                                    title="Confirmation & PIN"
                                    headContent={
                                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                                            Default-deny · step-up by risk
                                        </span>
                                    }
                                >
                                    <div className="px-5 pb-5 max-lg:px-3 space-y-5">
                                        <FormRow
                                            label="Require a step-up PIN from this risk level up"
                                            hint="Any command at or above this risk demands a fresh, scoped PIN before it runs. Lower-risk reads run without one."
                                        >
                                            <div className="flex items-center gap-3 flex-wrap">
                                                <select
                                                    value={form.require_pin_for_level ?? "L3"}
                                                    onChange={(e) => set("require_pin_for_level", e.target.value as AimRiskLevel)}
                                                    className={`${selectCls} max-w-xs`}
                                                    disabled={formDisabled}
                                                >
                                                    {AIM_RISK_LEVELS.filter((r) => r.value !== "L4").map((r) => (
                                                        <option key={r.value} value={r.value}>
                                                            {plainRisk(r.value)} — {r.hint}
                                                        </option>
                                                    ))}
                                                </select>
                                                <Badge variant={riskVariant(form.require_pin_for_level)} dot>
                                                    {plainRisk(form.require_pin_for_level ?? "L3")} and above
                                                </Badge>
                                            </div>
                                        </FormRow>

                                        <FormRow
                                            label="Max bulk leads without a PIN"
                                            hint="Bulk actions touching more leads than this always demand a PIN, regardless of risk level."
                                        >
                                            <input
                                                type="number"
                                                min={0}
                                                value={form.max_bulk_leads_without_pin ?? 0}
                                                onChange={(e) => set("max_bulk_leads_without_pin", numOrNull(e.target.value))}
                                                className={`${inputCls} max-w-[12rem]`}
                                                disabled={formDisabled}
                                            />
                                        </FormRow>
                                    </div>
                                </Card>
                            </section>

                            {/* SPEND LIMITS */}
                            <section id="spend" className="scroll-mt-24">
                                <Card
                                    title="Spend limits"
                                    headContent={
                                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                            <Icon name="wallet" className="size-3.5 fill-t-tertiary" />
                                            Checked before every paid action
                                        </span>
                                    }
                                >
                                    <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-2 gap-5 max-sm:grid-cols-1">
                                        <FormRow label="Daily spend limit (₹)" hint="The AI can't authorise paid actions beyond this in one day.">
                                            <div className="relative">
                                                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-t-tertiary text-body-2">₹</span>
                                                <input
                                                    type="number"
                                                    min={0}
                                                    value={form.daily_spend_limit ?? 0}
                                                    onChange={(e) => set("daily_spend_limit", numOrNull(e.target.value))}
                                                    className={`${inputCls} pl-8`}
                                                    disabled={formDisabled}
                                                />
                                            </div>
                                        </FormRow>
                                        <FormRow label="Monthly spend limit (₹)" hint="A hard ceiling on total AI-authorised spend per month.">
                                            <div className="relative">
                                                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-t-tertiary text-body-2">₹</span>
                                                <input
                                                    type="number"
                                                    min={0}
                                                    value={form.monthly_spend_limit ?? 0}
                                                    onChange={(e) => set("monthly_spend_limit", numOrNull(e.target.value))}
                                                    className={`${inputCls} pl-8`}
                                                    disabled={formDisabled}
                                                />
                                            </div>
                                        </FormRow>
                                    </div>
                                </Card>
                            </section>

                            {/* CALLING HOURS */}
                            <section id="hours" className="scroll-mt-24">
                                <Card
                                    title="Calling hours"
                                    headContent={
                                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                            <Icon name="clock" className="size-3.5 fill-t-tertiary" />
                                            Outbound calls obey these + DND
                                        </span>
                                    }
                                >
                                    <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-3 gap-5 max-sm:grid-cols-1">
                                        <FormRow label="Start time" hint="Earliest the AI may place calls.">
                                            <input
                                                type="time"
                                                value={form.allowed_call_start_time ?? ""}
                                                onChange={(e) => set("allowed_call_start_time", e.target.value || null)}
                                                className={inputCls}
                                                disabled={formDisabled}
                                            />
                                        </FormRow>
                                        <FormRow label="End time" hint="Latest the AI may place calls.">
                                            <input
                                                type="time"
                                                value={form.allowed_call_end_time ?? ""}
                                                onChange={(e) => set("allowed_call_end_time", e.target.value || null)}
                                                className={inputCls}
                                                disabled={formDisabled}
                                            />
                                        </FormRow>
                                        <FormRow label="Timezone" hint="The window above is interpreted in this zone.">
                                            <select
                                                value={form.timezone ?? ""}
                                                onChange={(e) => set("timezone", e.target.value)}
                                                className={selectCls}
                                                disabled={formDisabled}
                                            >
                                                {AIM_TIMEZONES.map((tz) => (
                                                    <option key={tz} value={tz}>
                                                        {tz}
                                                    </option>
                                                ))}
                                            </select>
                                        </FormRow>
                                    </div>
                                </Card>
                            </section>

                            {/* PHONE NUMBERS */}
                            <section id="numbers" className="scroll-mt-24">
                                <NumbersCard
                                    numbers={numbers}
                                    writable={writable}
                                    dormant={dormant}
                                    numModalOpen={numModalOpen}
                                    onOpenAdd={() => setNumModalOpen(true)}
                                    onCloseAdd={() => setNumModalOpen(false)}
                                    onDeleted={(msg) => { showToast(msg); load(); }}
                                    onError={(m) => showToast(m, "error")}
                                    onAdded={(msg) => { showToast(msg); setNumModalOpen(false); load(); }}
                                />
                            </section>

                            {/* CHANGE PIN */}
                            <section id="pin-change" className="scroll-mt-24">
                                <ChangePinCard
                                    onSuccess={(msg) => showToast(msg)}
                                    onError={(m) => showToast(m, "error")}
                                />
                            </section>

                            {/* TEAM (authorized users) */}
                            <section id="team" className="scroll-mt-24">
                                <Card
                                    title="Team"
                                    headContent={
                                        <div className="ml-auto flex items-center gap-2">
                                            <Badge variant="neutral">{userRows.length} people</Badge>
                                            {writable && (
                                                <button
                                                    onClick={() => {
                                                        setEditing(null);
                                                        setEditOpen(true);
                                                    }}
                                                    disabled={dormant}
                                                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary fill-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary hover:fill-t-primary disabled:opacity-50"
                                                >
                                                    <Icon name="plus" className="size-3.5 fill-current" />
                                                    Add
                                                </button>
                                            )}
                                        </div>
                                    }
                                >
                                    <div className="overflow-x-auto">
                                        <table className="data-table">
                                            <thead>
                                                <tr>
                                                    <th>Person</th>
                                                    <th>Role</th>
                                                    <th>PIN</th>
                                                    <th>Last used</th>
                                                    <th>Status</th>
                                                    {writable && <th className="text-right pr-5">Actions</th>}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {dormant || userRows.length === 0 ? (
                                                    <tr>
                                                        <td colSpan={writable ? 6 : 5}>
                                                            <div className="state-block">
                                                                <span className="state-glyph">
                                                                    <Icon name="profile" className="fill-inherit" />
                                                                </span>
                                                                <div className="state-title">
                                                                    {dormant ? "Team appears once the service is live" : "No one added yet"}
                                                                </div>
                                                                <div className="state-sub max-w-md mx-auto">
                                                                    Add the people allowed to command the AI Manager — each with a role and a
                                                                    personal step-up PIN before any risky action can run.
                                                                </div>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    userRows.map((u) => {
                                                        const locked = isLocked(u);
                                                        return (
                                                            <tr key={u.id}>
                                                                <td>
                                                                    <div className="flex items-center gap-3 min-w-0">
                                                                        <span className="grid place-items-center size-9 shrink-0 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-button text-t-secondary uppercase">
                                                                            {u.name.slice(0, 2)}
                                                                        </span>
                                                                        <div className="min-w-0">
                                                                            <div className="text-body-2 text-t-primary truncate">{u.name}</div>
                                                                            <div className="font-mono text-caption text-t-tertiary truncate">{u.phone_number}</div>
                                                                        </div>
                                                                    </div>
                                                                </td>
                                                                <td><Badge variant={roleVariant(u.role)}>{u.role}</Badge></td>
                                                                <td>
                                                                    {u.pin_set_at ? (
                                                                        <Badge variant="success" dot>Set</Badge>
                                                                    ) : (
                                                                        <Badge variant="warning">Not set</Badge>
                                                                    )}
                                                                </td>
                                                                <td className="text-t-secondary whitespace-nowrap">{fmt(u.last_used_at)}</td>
                                                                <td>
                                                                    {locked ? (
                                                                        <Badge variant="danger" dot>Locked</Badge>
                                                                    ) : u.is_active ? (
                                                                        <Badge variant="success" dot>Active</Badge>
                                                                    ) : (
                                                                        <Badge variant="neutral">Disabled</Badge>
                                                                    )}
                                                                </td>
                                                                {writable && (
                                                                    <td className="text-right pr-5">
                                                                        <div className="inline-flex items-center gap-2">
                                                                            <RowBtn icon="edit" label="Edit" onClick={() => { setEditing(u); setEditOpen(true); }} />
                                                                            <RowBtn icon="lock" label={u.pin_set_at ? "Reset PIN" : "Set PIN"} onClick={() => setPinFor(u)} />
                                                                            <RowBtn
                                                                                icon={u.is_active ? "block" : "check"}
                                                                                label={u.is_active ? "Disable" : "Enable"}
                                                                                danger={u.is_active}
                                                                                onClick={() => toggleUser(u)}
                                                                            />
                                                                        </div>
                                                                    </td>
                                                                )}
                                                            </tr>
                                                        );
                                                    })
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </Card>
                            </section>

                            {/* WHAT IT CAN DO (capabilities) */}
                            <section id="capabilities" className="scroll-mt-24">
                                <CapabilitiesCard />
                            </section>

                            {/* Mobile save bar */}
                            {writable && (
                                <div className="lg:hidden flex items-center gap-3">
                                    <Button
                                        isBlack
                                        className="flex-1 justify-center"
                                        onClick={() => setConfirmOpen(true)}
                                        disabled={formDisabled || saving}
                                    >
                                        Save changes
                                    </Button>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>

            {confirmOpen && (
                <ConfirmModal
                    profile={form}
                    saving={saving}
                    onCancel={() => setConfirmOpen(false)}
                    onConfirm={doSave}
                />
            )}

            {editOpen && (
                <UserModal
                    user={editing}
                    onClose={() => setEditOpen(false)}
                    onSaved={(msg) => { showToast(msg); setEditOpen(false); load(); }}
                    onError={(m) => showToast(m, "error")}
                />
            )}

            {pinFor && (
                <SetPinModal
                    user={pinFor}
                    admin={admin}
                    onClose={() => setPinFor(null)}
                    onSaved={(msg) => { showToast(msg); setPinFor(null); load(); }}
                    onError={(m) => showToast(m, "error")}
                />
            )}
        </>
    );
}

/* ----------------------------------------------------------------- pieces */

// Map an L-code threshold to plain language for the badge.
function plainRisk(level: AimRiskLevel): string {
    const map: Record<AimRiskLevel, string> = {
        L0: "Safe reads",
        L1: "Low-risk",
        L2: "Medium",
        L3: "High-risk",
        L4: "Blocked",
    };
    return map[level] || level;
}

function ToggleRow({
    label,
    hint,
    on,
    disabled,
    onChange,
}: {
    label: string;
    hint: string;
    on: boolean;
    disabled?: boolean;
    onChange: (v: boolean) => void;
}) {
    return (
        <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
                <div className="text-body-2 text-t-primary">{label}</div>
                <div className="text-caption text-t-tertiary mt-0.5">{hint}</div>
            </div>
            <button
                type="button"
                role="switch"
                aria-checked={on}
                disabled={disabled}
                onClick={() => onChange(!on)}
                className={`relative shrink-0 h-6 w-11 rounded-full transition-colors disabled:opacity-50 ${
                    on ? "bg-primary-02" : "bg-s-stroke2"
                }`}
            >
                <span
                    className={`absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow-sm transition-transform ${
                        on ? "translate-x-5" : ""
                    }`}
                />
            </button>
        </div>
    );
}

function RowBtn({
    icon,
    label,
    onClick,
    danger,
}: {
    icon: string;
    label: string;
    onClick: () => void;
    danger?: boolean;
}) {
    return (
        <button
            onClick={onClick}
            title={label}
            className={`inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button transition-colors disabled:opacity-50 ${
                danger
                    ? "text-primary-03 fill-primary-03 hover:bg-primary-03/8 hover:border-primary-03/30"
                    : "text-t-secondary fill-t-secondary hover:border-s-highlight hover:text-t-primary hover:fill-t-primary"
            }`}
        >
            <Icon name={icon} className="size-3.5 fill-inherit" />
            <span className="max-md:hidden">{label}</span>
        </button>
    );
}

function ModalShell({
    title,
    icon,
    children,
    onClose,
    wide,
}: {
    title: string;
    icon: string;
    children: React.ReactNode;
    onClose: () => void;
    wide?: boolean;
}) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
            <div className={`relative w-full ${wide ? "max-w-lg" : "max-w-md"} card p-6 rise-in max-h-[90vh] overflow-y-auto`}>
                <div className="flex items-center gap-2 mb-4">
                    <span className="grid place-items-center size-9 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                        <Icon name={icon} className="size-4.5 fill-inherit" />
                    </span>
                    <h3 className="text-h6 text-t-primary">{title}</h3>
                    <button
                        onClick={onClose}
                        className="ml-auto grid place-items-center size-8 rounded-full text-t-tertiary hover:bg-b-surface2 hover:text-t-primary transition-colors"
                    >
                        <Icon name="close" className="size-4 fill-current" />
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
}

function ConfirmModal({
    profile,
    saving,
    onCancel,
    onConfirm,
}: {
    profile: AimProfile;
    saving: boolean;
    onCancel: () => void;
    onConfirm: () => void;
}) {
    return (
        <ModalShell title="Confirm setup changes" icon="lock" onClose={onCancel}>
            <p className="text-body-2 text-t-secondary mb-4">
                You&apos;re changing how the AI Manager spends money and when it asks for a PIN. Please confirm.
            </p>
            <dl className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset divide-y divide-s-subtle text-body-2">
                <KvRow k="Status" v={profile.enabled ? "Enabled" : "Disabled"} />
                <KvRow k="Require PIN from" v={`${plainRisk(profile.require_pin_for_level ?? "L3")} and above`} />
                <KvRow k="Daily limit" v={`₹${(profile.daily_spend_limit ?? 0).toLocaleString()}`} />
                <KvRow k="Monthly limit" v={`₹${(profile.monthly_spend_limit ?? 0).toLocaleString()}`} />
                <KvRow k="Calling hours" v={`${profile.allowed_call_start_time ?? "—"} – ${profile.allowed_call_end_time ?? "—"} (${profile.timezone ?? "—"})`} />
            </dl>
            <div className="flex items-center justify-end gap-3 mt-5">
                <Button isStroke onClick={onCancel} disabled={saving}>Cancel</Button>
                <Button isBlack onClick={onConfirm} disabled={saving}>
                    {saving ? "Saving…" : "Confirm & save"}
                </Button>
            </div>
        </ModalShell>
    );
}

function KvRow({ k, v }: { k: string; v: string }) {
    return (
        <div className="flex items-center justify-between gap-4 px-4 py-2.5">
            <dt className="text-t-tertiary">{k}</dt>
            <dd className="text-t-primary text-right">{v}</dd>
        </div>
    );
}

function validPin(p: string): boolean {
    return /^\d{4}$|^\d{6}$/.test(p);
}

function UserModal({
    user,
    onClose,
    onSaved,
    onError,
}: {
    user: AimAuthUser | null;
    onClose: () => void;
    onSaved: (msg: string) => void;
    onError: (m: string) => void;
}) {
    const editing = !!user;
    const [name, setName] = useState(user?.name ?? "");
    const [phone, setPhone] = useState(user?.phone_number ?? "");
    const [role, setRole] = useState<AimRole>(user?.role ?? "operator");
    const [perms, setPerms] = useState<string[]>(user?.permissions ?? ["analytics"]);
    const [active, setActive] = useState<boolean>(user?.is_active ?? true);
    const [saving, setSaving] = useState(false);

    function togglePerm(p: string) {
        setPerms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
    }

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim() || !phone.trim()) return;
        setSaving(true);
        try {
            if (editing && user) {
                await patchAimUser(user.id, { name: name.trim(), phone_number: phone.trim(), role, permissions: perms, is_active: active });
                onSaved(`${name.trim()} updated`);
            } else {
                await createAimUser({ name: name.trim(), phone_number: phone.trim(), role, permissions: perms, is_active: active });
                onSaved(`${name.trim()} added — set a PIN to enable risky commands`);
            }
        } catch (err) {
            onError(err instanceof Error ? err.message : "Save failed");
        } finally {
            setSaving(false);
        }
    }

    return (
        <ModalShell title={editing ? "Edit person" : "Add person"} icon={editing ? "edit" : "plus"} onClose={onClose} wide>
            <form onSubmit={submit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
                    <FormRow label="Name">
                        <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Rahul Mehta" className={inputCls} required />
                    </FormRow>
                    <FormRow label="Phone (caller-ID)">
                        <input type="text" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+919876543210" className={inputCls} required />
                    </FormRow>
                </div>
                <FormRow label="Role" hint="Effective permission = role allows AND a matching grant is checked below. Default-deny.">
                    <select value={role} onChange={(e) => setRole(e.target.value as AimRole)} className={selectCls}>
                        {AIM_ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                        ))}
                    </select>
                </FormRow>
                <FormRow label="What they can command">
                    <div className="flex flex-wrap gap-2">
                        {KNOWN_GRANTS.map((g) => {
                            const on = perms.includes(g);
                            return (
                                <button
                                    type="button"
                                    key={g}
                                    onClick={() => togglePerm(g)}
                                    className={`inline-flex items-center gap-1 h-8 px-3 rounded-full border text-button transition-colors ${
                                        on
                                            ? "border-transparent bg-primary-01/12 text-primary-01 fill-primary-01"
                                            : "border-s-subtle text-t-secondary hover:border-s-highlight hover:text-t-primary"
                                    }`}
                                >
                                    {on && <Icon name="check" className="size-3 fill-current" />}
                                    {g}
                                </button>
                            );
                        })}
                    </div>
                </FormRow>
                <label className="flex items-center justify-between gap-4 py-1">
                    <span className="text-body-2 text-t-primary">Active</span>
                    <button
                        type="button"
                        role="switch"
                        aria-checked={active}
                        onClick={() => setActive((v) => !v)}
                        className={`relative shrink-0 h-6 w-11 rounded-full transition-colors ${active ? "bg-primary-02" : "bg-s-stroke2"}`}
                    >
                        <span className={`absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow-sm transition-transform ${active ? "translate-x-5" : ""}`} />
                    </button>
                </label>
                <div className="flex items-center justify-end gap-3 pt-1">
                    <Button isStroke onClick={onClose} disabled={saving} type="button">Cancel</Button>
                    <Button isBlack disabled={saving} type="submit">
                        {saving ? "Saving…" : editing ? "Save changes" : "Add person"}
                    </Button>
                </div>
            </form>
        </ModalShell>
    );
}

function SetPinModal({
    user,
    admin,
    onClose,
    onSaved,
    onError,
}: {
    user: AimAuthUser;
    admin: boolean;
    onClose: () => void;
    onSaved: (msg: string) => void;
    onError: (m: string) => void;
}) {
    const [pin, setPin] = useState("");
    const [confirm, setConfirm] = useState("");
    const [saving, setSaving] = useState(false);
    const mismatch = confirm.length > 0 && pin !== confirm;
    const resetting = !!user.pin_set_at;

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!validPin(pin) || pin !== confirm) return;
        setSaving(true);
        try {
            // `admin` carries the required admin-on-behalf flag so the backend
            // accepts an admin reset of another user's PIN (otherwise 422).
            await setAimUserPin(user.id, pin, admin || resetting);
            onSaved(`PIN ${resetting ? "reset" : "set"} for ${user.name}`);
        } catch (err) {
            onError(err instanceof Error ? err.message : "Could not set PIN");
        } finally {
            setSaving(false);
        }
    }

    return (
        <ModalShell title={`${resetting ? "Reset" : "Set"} PIN — ${user.name}`} icon="lock" onClose={onClose}>
            {resetting && !admin && (
                <div className="mb-4 p-3 rounded-2xl bg-primary-05/10 border border-primary-05/20 text-caption text-t-secondary">
                    Resetting a PIN is admin-only and firewall-gated — you may be asked for a step-up PIN.
                </div>
            )}
            <p className="text-body-2 text-t-secondary mb-4">
                Choose a 4- or 6-digit PIN. It&apos;s hashed on the server — never stored or shown in plain text.
            </p>
            <form onSubmit={submit} className="space-y-4">
                <FormRow label="New PIN">
                    <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        value={pin}
                        onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
                        placeholder="••••"
                        className={`${inputCls} tracking-[0.4em] font-mono`}
                        required
                    />
                </FormRow>
                <FormRow label="Confirm PIN" hint={mismatch ? "PINs don't match." : "Re-enter the same PIN."}>
                    <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        value={confirm}
                        onChange={(e) => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 6))}
                        placeholder="••••"
                        className={`${inputCls} tracking-[0.4em] font-mono ${mismatch ? "!border-primary-03" : ""}`}
                        required
                    />
                </FormRow>
                <div className="flex items-center justify-end gap-3 pt-1">
                    <Button isStroke onClick={onClose} disabled={saving} type="button">Cancel</Button>
                    <Button isBlack disabled={saving || !validPin(pin) || pin !== confirm} type="submit">
                        {saving ? "Saving…" : resetting ? "Reset PIN" : "Set PIN"}
                    </Button>
                </div>
            </form>
        </ModalShell>
    );
}

/* ------------------------------------------------------- capability catalog */

const CAP_MODULES = [
    "all",
    "analytics",
    "campaign",
    "lead",
    "call",
    "whatsapp",
    "workflow",
    "billing",
    "booking",
    "creative",
] as const;

function moduleLabel(m: string): string {
    if (m === "all") return "All";
    return m.charAt(0).toUpperCase() + m.slice(1);
}

function CapabilitiesCard() {
    const [module, setModule] = useState<(typeof CAP_MODULES)[number]>("all");
    const filtered = useMemo(
        () => INTENT_CATALOG.filter((c) => module === "all" || c.module === module),
        [module]
    );

    return (
        <Card
            title="What it can do"
            headContent={
                <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="grid" className="size-3.5 fill-t-tertiary" />
                    {INTENT_CATALOG.length} actions · graded by risk
                </span>
            }
        >
            <div className="px-5 max-lg:px-3 pb-3">
                <div className="flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle w-fit max-w-full overflow-x-auto scrollbar-none">
                    {CAP_MODULES.map((m) => {
                        const active = module === m;
                        return (
                            <button
                                key={m}
                                onClick={() => setModule(m)}
                                className={`shrink-0 inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-button transition-colors ${
                                    active ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04" : "text-t-secondary hover:text-t-primary"
                                }`}
                            >
                                {m !== "all" && (
                                    <Icon name={moduleGlyph(m)} className={`size-3.5 ${active ? "fill-t-primary" : "fill-t-tertiary"}`} />
                                )}
                                {moduleLabel(m)}
                            </button>
                        );
                    })}
                </div>
            </div>

            <div className="px-5 max-lg:px-3 pb-4">
                <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                    {filtered.map((c) => {
                        const live = LIVE_MODULES.has(c.module) && !c.parked;
                        return (
                            <div
                                key={c.intent}
                                className="flex flex-col gap-2 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30"
                            >
                                <div className="flex items-center gap-2">
                                    <span className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                                        <Icon name={moduleGlyph(c.module)} className="size-4 fill-inherit" />
                                    </span>
                                    <div className="min-w-0">
                                        <div className="text-body-2 text-t-primary truncate">{c.label}</div>
                                        <div className="text-caption text-t-tertiary truncate">&ldquo;{c.example}&rdquo;</div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1.5 flex-wrap mt-auto pt-1">
                                    <Badge variant={parseRiskVariant(c.risk)}>{parseRiskLabel(c.risk)}</Badge>
                                    {live ? (
                                        <span className="ml-auto inline-flex items-center gap-1 text-caption text-primary-02">
                                            <span className="size-1.5 rounded-full bg-primary-02" />
                                            available now
                                        </span>
                                    ) : (
                                        <span className="ml-auto inline-flex items-center gap-1 text-caption text-t-tertiary">
                                            <Icon name="clock" className="size-3 fill-t-tertiary" />
                                            configure first
                                        </span>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* What it will never do */}
            <div className="px-5 max-lg:px-3 pb-5">
                <div className="text-overline uppercase tracking-[0.06em] text-t-tertiary mb-2 flex items-center gap-1.5">
                    <Icon name="lock" className="size-3.5 fill-primary-03" />
                    What it will never do
                </div>
                <div className="grid grid-cols-2 gap-2 max-md:grid-cols-1">
                    {BLOCKED_EXAMPLES.map((b) => (
                        <div
                            key={b.label}
                            className="flex items-start gap-2.5 p-3 rounded-2xl bg-primary-03/[0.05] ring-1 ring-primary-03/15 ring-inset"
                        >
                            <Icon name="block" className="size-4 shrink-0 fill-primary-03 mt-0.5" />
                            <div className="min-w-0">
                                <div className="text-body-2 text-t-primary">{b.label}</div>
                                <div className="text-caption text-t-tertiary mt-0.5">&ldquo;{b.example}&rdquo;</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </Card>
    );
}

function SetupSkeleton() {
    return (
        <>
            {[...Array(3)].map((_, i) => (
                <div key={i} className="card">
                    <div className="flex items-center h-12 pl-5">
                        <div className="skeleton h-4 w-32" />
                    </div>
                    <div className="px-5 pb-5 pt-3 space-y-4">
                        {[...Array(2)].map((__, j) => (
                            <div key={j}>
                                <div className="skeleton h-3 w-24 mb-2" />
                                <div className="skeleton h-11 w-full" />
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </>
    );
}

/* ================================================================= NUMBERS */

// Status badge for a registered AIM phone number.
function numStatusVariant(s: AimNumber["status"]) {
    if (s === "active") return "success" as const;
    if (s === "locked") return "warning" as const;
    return "neutral" as const;
}

function AddNumberModal({
    onClose,
    onAdded,
    onError,
}: {
    onClose: () => void;
    onAdded: (msg: string) => void;
    onError: (m: string) => void;
}) {
    const [phone, setPhone] = useState("");
    const [label, setLabel] = useState("");
    const [role, setRole] = useState<AimVerifyMode>("voice_pin");
    const [grants, setGrants] = useState<string[]>(["analytics"]);
    const [saving, setSaving] = useState(false);

    function toggleGrant(g: string) {
        setGrants((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));
    }

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!phone.trim()) return;
        setSaving(true);
        try {
            await registerAimNumber({
                phone: phone.trim(),
                label: label.trim() || undefined,
                verify_mode: role,
                grants,
            });
            onAdded(`${phone.trim()} registered — verify the OTP to activate it`);
        } catch (err) {
            onError(err instanceof Error ? err.message : "Registration failed");
        } finally {
            setSaving(false);
        }
    }

    return (
        <ModalShell title="Add phone number" icon="mobile" onClose={onClose} wide>
            <form onSubmit={submit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
                    <FormRow label="Phone number" hint="Include country code e.g. +919876543210">
                        <input
                            type="text"
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                            placeholder="+919876543210"
                            className={inputCls}
                            required
                        />
                    </FormRow>
                    <FormRow label="Label" hint="Optional friendly name for this line">
                        <input
                            type="text"
                            value={label}
                            onChange={(e) => setLabel(e.target.value)}
                            placeholder="Riya — sales line"
                            className={inputCls}
                        />
                    </FormRow>
                </div>

                <FormRow label="Verification mode" hint="How this number authenticates commands — voice PIN (default) or OTP SMS.">
                    <select
                        value={role}
                        onChange={(e) => setRole(e.target.value as AimVerifyMode)}
                        className={selectCls}
                    >
                        {AIM_VERIFY_MODES.map((m) => (
                            <option key={m} value={m}>
                                {m === "voice_pin" ? "Voice PIN (4–6 digit, spoken)" : "OTP SMS"}
                            </option>
                        ))}
                    </select>
                </FormRow>

                <FormRow label="Capability grants" hint="What the AI will allow from this number. Default-deny for anything not listed.">
                    <div className="flex flex-wrap gap-2">
                        {KNOWN_GRANTS.map((g) => {
                            const on = grants.includes(g);
                            return (
                                <button
                                    type="button"
                                    key={g}
                                    onClick={() => toggleGrant(g)}
                                    className={`inline-flex items-center gap-1 h-8 px-3 rounded-full border text-button transition-colors ${
                                        on
                                            ? "border-transparent bg-primary-01/12 text-primary-01 fill-primary-01"
                                            : "border-s-subtle text-t-secondary hover:border-s-highlight hover:text-t-primary"
                                    }`}
                                >
                                    {on && <Icon name="check" className="size-3 fill-current" />}
                                    {g}
                                </button>
                            );
                        })}
                    </div>
                </FormRow>

                <div className="flex items-center justify-end gap-3 pt-1">
                    <Button isStroke onClick={onClose} disabled={saving} type="button">Cancel</Button>
                    <Button isBlack disabled={saving} type="submit">
                        {saving ? "Registering…" : "Register number"}
                    </Button>
                </div>
            </form>
        </ModalShell>
    );
}

function NumbersCard({
    numbers,
    writable,
    dormant,
    numModalOpen,
    onOpenAdd,
    onCloseAdd,
    onDeleted,
    onError,
    onAdded,
}: {
    numbers: ReadResult<{ numbers: AimNumber[] }> | null;
    writable: boolean;
    dormant: boolean;
    numModalOpen: boolean;
    onOpenAdd: () => void;
    onCloseAdd: () => void;
    onDeleted: (msg: string) => void;
    onError: (m: string) => void;
    onAdded: (msg: string) => void;
}) {
    const [deletingId, setDeletingId] = useState<string | null>(null);

    const rows = numbers?.kind === "ok" ? numbers.data.numbers : [];
    const numsDormant = dormant || numbers?.kind === "dormant";

    async function handleDelete(n: AimNumber) {
        if (!confirm(`Remove ${n.phone} (${n.label || "unlabelled"})? This cannot be undone.`)) return;
        setDeletingId(n.number_id);
        try {
            await deleteAimNumber(n.number_id);
            onDeleted(`${n.phone} removed`);
        } catch (err) {
            onError(err instanceof Error ? err.message : "Remove failed");
        } finally {
            setDeletingId(null);
        }
    }

    return (
        <>
            <Card
                title="Phone numbers"
                headContent={
                    <div className="ml-auto flex items-center gap-2">
                        <Badge variant="neutral">{rows.length} registered</Badge>
                        {writable && (
                            <button
                                onClick={onOpenAdd}
                                disabled={numsDormant}
                                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary fill-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary hover:fill-t-primary disabled:opacity-50"
                            >
                                <Icon name="plus" className="size-3.5 fill-current" />
                                Add
                            </button>
                        )}
                    </div>
                }
            >
                <div className="overflow-x-auto">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Number</th>
                                <th>Label</th>
                                <th>Role</th>
                                <th>Verify</th>
                                <th>Status</th>
                                <th>Added</th>
                                {writable && <th className="text-right pr-5">Actions</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {numsDormant || rows.length === 0 ? (
                                <tr>
                                    <td colSpan={writable ? 7 : 6}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="mobile" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">
                                                {numsDormant
                                                    ? "Phone numbers appear once the AI Manager is live"
                                                    : "No numbers registered yet"}
                                            </div>
                                            <div className="state-sub max-w-md mx-auto">
                                                Register the phone numbers authorised to call the AI Manager and issue
                                                commands. Each number gets a role and a capability grant list.
                                            </div>
                                            {!numsDormant && writable && (
                                                <button
                                                    onClick={onOpenAdd}
                                                    className="mt-4 inline-flex items-center gap-1.5 h-9 px-4 rounded-full bg-primary-01 text-white text-button hover:bg-primary-02 transition-colors"
                                                >
                                                    <Icon name="plus" className="size-3.5 fill-current" />
                                                    Register first number
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                rows.map((n) => (
                                    <tr key={n.number_id}>
                                        <td>
                                            <span className="font-mono text-body-2 text-t-primary">{n.phone}</span>
                                        </td>
                                        <td className="text-t-secondary">{n.label || <span className="text-t-tertiary">—</span>}</td>
                                        <td><Badge variant={roleVariant(n.role)}>{n.role}</Badge></td>
                                        <td>
                                            <span className="text-caption text-t-secondary">
                                                {n.verify_mode === "voice_pin" ? "Voice PIN" : "OTP"}
                                            </span>
                                        </td>
                                        <td>
                                            <Badge variant={numStatusVariant(n.status)} dot>
                                                {n.status}
                                            </Badge>
                                        </td>
                                        <td className="text-t-secondary whitespace-nowrap">{fmt(n.registered_at)}</td>
                                        {writable && (
                                            <td className="text-right pr-5">
                                                <RowBtn
                                                    icon="delete"
                                                    label={deletingId === n.number_id ? "Removing…" : "Remove"}
                                                    danger
                                                    onClick={() => handleDelete(n)}
                                                />
                                            </td>
                                        )}
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>

            {numModalOpen && (
                <AddNumberModal
                    onClose={onCloseAdd}
                    onAdded={onAdded}
                    onError={onError}
                />
            )}
        </>
    );
}

/* ============================================================= CHANGE PIN */

function ChangePinCard({
    onSuccess,
    onError,
}: {
    onSuccess: (msg: string) => void;
    onError: (m: string) => void;
}) {
    const [oldPin, setOldPin] = useState("");
    const [newPin, setNewPin] = useState("");
    const [confirmPin, setConfirmPin] = useState("");
    const [saving, setSaving] = useState(false);
    const [localError, setLocalError] = useState("");

    const mismatch = confirmPin.length > 0 && newPin !== confirmPin;
    const newPinValid = /^\d{4}$|^\d{6}$/.test(newPin);
    const canSubmit = oldPin.length >= 4 && newPinValid && newPin === confirmPin;

    // Detect backend lockout in the error message
    function isLockoutError(msg: string): boolean {
        return /lock|attempt|too many/i.test(msg);
    }

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!canSubmit) return;
        setLocalError("");
        setSaving(true);
        try {
            await changeFirewallPin(oldPin, newPin);
            // Clear sensitive fields on success
            setOldPin("");
            setNewPin("");
            setConfirmPin("");
            onSuccess("PIN changed successfully — your new PIN is active immediately");
        } catch (err) {
            const msg = err instanceof Error ? err.message : "PIN change failed";
            setLocalError(msg);
            onError(msg);
        } finally {
            setSaving(false);
        }
    }

    return (
        <Card
            title="Change step-up PIN"
            headContent={
                <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                    Never stored in plain text
                </span>
            }
        >
            <div className="px-5 pb-5 max-lg:px-3">
                <p className="text-body-2 text-t-secondary mb-5">
                    Your step-up PIN guards high-risk AI Manager commands. Use a 4- or 6-digit PIN that is
                    different from your previous one. After 5 wrong attempts the PIN locks for 15 minutes.
                </p>

                {localError && (
                    <div className={`mb-4 flex items-start gap-2.5 p-3.5 rounded-2xl ring-1 ring-inset ${
                        isLockoutError(localError)
                            ? "bg-primary-05/8 ring-primary-05/20 text-primary-05"
                            : "bg-primary-03/8 ring-primary-03/20 text-primary-03"
                    } text-body-2`}>
                        <Icon
                            name={isLockoutError(localError) ? "clock" : "info"}
                            className="size-4 fill-current shrink-0 mt-0.5"
                        />
                        <div>
                            <div className="font-medium">
                                {isLockoutError(localError) ? "PIN locked" : "PIN change failed"}
                            </div>
                            <div className="text-caption mt-0.5 opacity-80">{localError}</div>
                            {isLockoutError(localError) && (
                                <div className="text-caption mt-1 opacity-70">
                                    Wait 15 minutes then try again, or ask an admin to reset your PIN from the Team section.
                                </div>
                            )}
                        </div>
                    </div>
                )}

                <form onSubmit={submit} className="space-y-4 max-w-sm">
                    <FormRow label="Current PIN" hint="The PIN you use today for step-up confirmation.">
                        <input
                            type="password"
                            inputMode="numeric"
                            autoComplete="current-password"
                            value={oldPin}
                            onChange={(e) => { setOldPin(e.target.value.replace(/\D/g, "").slice(0, 6)); setLocalError(""); }}
                            placeholder="••••"
                            className={`${inputCls} tracking-[0.4em] font-mono`}
                            required
                        />
                    </FormRow>

                    <FormRow label="New PIN" hint="4 or 6 digits. Not the same as your current PIN.">
                        <input
                            type="password"
                            inputMode="numeric"
                            autoComplete="new-password"
                            value={newPin}
                            onChange={(e) => { setNewPin(e.target.value.replace(/\D/g, "").slice(0, 6)); setLocalError(""); }}
                            placeholder="••••"
                            className={`${inputCls} tracking-[0.4em] font-mono ${
                                newPin.length > 0 && !newPinValid ? "!border-primary-03" : ""
                            }`}
                            required
                        />
                        {newPin.length > 0 && !newPinValid && (
                            <p className="text-caption text-primary-03 mt-1.5">Must be exactly 4 or 6 digits.</p>
                        )}
                    </FormRow>

                    <FormRow
                        label="Confirm new PIN"
                        hint={mismatch ? "PINs do not match." : "Re-enter your new PIN to confirm."}
                    >
                        <input
                            type="password"
                            inputMode="numeric"
                            autoComplete="new-password"
                            value={confirmPin}
                            onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
                            placeholder="••••"
                            className={`${inputCls} tracking-[0.4em] font-mono ${mismatch ? "!border-primary-03" : ""}`}
                            required
                        />
                    </FormRow>

                    <div className="flex items-center gap-3 pt-1">
                        <Button isBlack disabled={!canSubmit || saving} type="submit">
                            {saving ? "Changing…" : "Change PIN"}
                        </Button>
                        <p className="text-caption text-t-tertiary">
                            Effective immediately · hashed on the server
                        </p>
                    </div>
                </form>
            </div>
        </Card>
    );
}
