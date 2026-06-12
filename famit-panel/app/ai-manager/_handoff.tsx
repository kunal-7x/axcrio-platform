"use client";

// HANDOFF TEAM — the per-tenant human-escalation roster manager.
//
// One reusable component used in TWO places: the dedicated "Handoff Team" view
// (/ai-manager/handoff) and a compact section inside Run-a-Campaign (so the vendor
// can review / add escalation people right before launch). It owns ALL the wiring
// (list / add / reorder / enable-toggle / delete) against the LIVE backend
// (lib/api.ts handoff methods → /brain/handoff*).
//
// WHAT IT IS, in plain words: when a caller asks for a human, or a lead is hot,
// the AI rings these people IN ORDER — the first available answers and is bridged
// into the live call; if nobody answers, the hot lead is sent to their WhatsApp.
//
// Premium reference-kit (Card / Button / Badge / Icon / Modal / Switch / Field),
// Inter Display, zero raw hex (Signal tokens only). Dormant-safe: an empty list
// shows a calm "add your first escalation contact" state; a 4xx/5xx surfaces a
// quiet inline note, never an error wall. Read-only roles (agents) see the list
// but no edit controls. Touches no app-wide component, no globals.css.

import { useCallback, useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Modal from "@/components/Modal";
import Switch from "@/components/Switch";
import { useMe, canWrite } from "@/lib/auth";
import {
    getHandoffTeam,
    addHandoffMember,
    saveHandoffOrder,
    removeHandoffMember,
    HandoffError,
    type HandoffMember,
} from "@/lib/api";

/* ----------------------------------------------------------------- helpers */

// Client-side mirror of the backend +91 guard — gives instant feedback before the
// round-trip; the backend remains the real validator (400 on bad input).
function normalizePhone(raw: string): string {
    const t = raw.trim().replace(/[\s()-]/g, "");
    if (!t) return "";
    if (t.startsWith("+")) return t;
    // bare 10-digit Indian mobile -> prefix +91; "91XXXXXXXXXX" -> +91…
    if (/^[6-9]\d{9}$/.test(t)) return `+91${t}`;
    if (/^91[6-9]\d{9}$/.test(t)) return `+${t}`;
    if (/^0[6-9]\d{9}$/.test(t)) return `+91${t.slice(1)}`;
    return t;
}

function isValidIndianMobile(phone: string): boolean {
    return /^\+91[6-9]\d{9}$/.test(phone);
}

const EMPTY_FORM = { phone: "", whatsapp: "", role: "", hours: "" };

/* ============================================================ the component */

export default function HandoffTeam({ compact = false }: { compact?: boolean }) {
    const { me } = useMe();
    const writable = canWrite(me);

    const [team, setTeam] = useState<HandoffMember[]>([]);
    const [loading, setLoading] = useState(true);
    const [note, setNote] = useState(""); // quiet inline note (errors / confirmations)
    const [noteTone, setNoteTone] = useState<"info" | "danger" | "success">("info");
    const [busy, setBusy] = useState(false); // a PUT/DELETE is in flight (locks the row controls)

    // add-member modal
    const [addOpen, setAddOpen] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [formErr, setFormErr] = useState("");
    const [saving, setSaving] = useState(false);

    const load = useCallback(() => {
        setLoading(true);
        getHandoffTeam()
            .then((r) => setTeam(r.team))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const enabledCount = useMemo(() => team.filter((m) => m.enabled).length, [team]);

    const flash = (msg: string, tone: "info" | "danger" | "success" = "info") => {
        setNoteTone(tone);
        setNote(msg);
    };

    // Persist the full ordered list (REORDER / enable-toggle). Optimistic: the
    // caller already mutated `next`; we reconcile by reloading on failure.
    const persistOrder = useCallback(
        async (next: HandoffMember[]) => {
            const prev = team;
            setTeam(next.map((m, i) => ({ ...m, priority: i + 1 })));
            setBusy(true);
            setNote("");
            try {
                await saveHandoffOrder(next);
            } catch (e) {
                setTeam(prev); // roll back on failure
                flash(e instanceof HandoffError ? e.message : "Couldn't save the new order.", "danger");
            } finally {
                setBusy(false);
            }
        },
        [team]
    );

    const move = (idx: number, dir: -1 | 1) => {
        const j = idx + dir;
        if (j < 0 || j >= team.length) return;
        const next = [...team];
        [next[idx], next[j]] = [next[j], next[idx]];
        persistOrder(next);
    };

    const toggleEnabled = (idx: number, on: boolean) => {
        const next = team.map((m, i) => (i === idx ? { ...m, enabled: on } : m));
        persistOrder(next);
    };

    const remove = async (phone: string) => {
        const prev = team;
        setTeam(team.filter((m) => m.phone !== phone));
        setBusy(true);
        setNote("");
        try {
            await removeHandoffMember(phone);
            flash("Removed from the handoff team.", "success");
        } catch (e) {
            setTeam(prev);
            flash(e instanceof HandoffError ? e.message : "Couldn't remove that contact.", "danger");
        } finally {
            setBusy(false);
        }
    };

    const openAdd = () => {
        setForm(EMPTY_FORM);
        setFormErr("");
        setAddOpen(true);
    };

    const submitAdd = async () => {
        const phone = normalizePhone(form.phone);
        if (!isValidIndianMobile(phone)) {
            setFormErr("Enter a valid Indian mobile number (it must start with +91).");
            return;
        }
        const wa = form.whatsapp.trim() ? normalizePhone(form.whatsapp) : "";
        setSaving(true);
        setFormErr("");
        try {
            await addHandoffMember({
                phone,
                whatsapp: wa || undefined,
                role: form.role.trim() || undefined,
                hours: form.hours.trim() || undefined,
                // omit priority -> backend auto-appends (max+1)
                enabled: true,
            });
            setAddOpen(false);
            flash("Added to the handoff team.", "success");
            load();
        } catch (e) {
            setFormErr(e instanceof HandoffError ? e.message : "Couldn't add that contact — try again.");
        } finally {
            setSaving(false);
        }
    };

    /* ------------------------------------------------------------- explainer */
    const explainer = (
        <p className={`text-body-2 text-t-secondary ${compact ? "px-5 max-lg:px-3 pb-1" : ""}`}>
            When a caller asks for a human — or a lead is hot — the AI rings these
            people <span className="text-t-primary">in order</span>. The first to
            answer is <span className="text-t-primary">bridged into the live call</span>.
            If nobody answers, the hot lead is sent to their{" "}
            <span className="text-t-primary">WhatsApp</span>.
        </p>
    );

    /* --------------------------------------------------------------- the body */
    const body = (
        <>
            {note && (
                <div
                    className={`mx-5 max-lg:mx-3 mb-3 flex items-center gap-2 p-3 rounded-2xl text-body-2 ${
                        noteTone === "danger"
                            ? "bg-primary-03/8 text-primary-03"
                            : noteTone === "success"
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-b-surface2 text-t-secondary"
                    }`}
                >
                    <Icon
                        name={noteTone === "success" ? "check-circle-fill" : "info"}
                        className="size-4 fill-current shrink-0"
                    />
                    {note}
                </div>
            )}

            {loading ? (
                <div className="px-5 max-lg:px-3 pb-5 space-y-2">
                    {[...Array(compact ? 2 : 3)].map((_, i) => (
                        <div key={i} className="skeleton h-16 w-full rounded-2xl" />
                    ))}
                </div>
            ) : team.length === 0 ? (
                <div className="px-5 max-lg:px-3 pb-2">
                    <div className="state-block !py-10">
                        <span className="state-glyph">
                            <Icon name="profile" className="fill-inherit" />
                        </span>
                        <div className="state-title">No handoff team yet</div>
                        <div className="state-sub">
                            Add your first escalation contact — the person the AI
                            rings when a caller wants to talk to a human.
                        </div>
                        {writable && (
                            <Button isStroke icon="plus" onClick={openAdd} className="mt-1">
                                Add contact
                            </Button>
                        )}
                    </div>
                </div>
            ) : (
                <ul className="px-3 max-lg:px-2 pb-3 space-y-2">
                    {team.map((m, i) => (
                        <li
                            key={m.phone}
                            className={`group rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3 max-lg:p-2.5 transition-opacity ${
                                m.enabled ? "" : "opacity-60"
                            }`}
                        >
                            <div className="flex items-center gap-3 max-sm:gap-2">
                                {/* reorder controls */}
                                {writable && team.length > 1 && (
                                    <div className="flex flex-col shrink-0">
                                        <button
                                            onClick={() => move(i, -1)}
                                            disabled={i === 0 || busy}
                                            aria-label="Move up"
                                            className="grid place-items-center size-6 rounded-md text-t-tertiary transition-colors hover:bg-b-surface1 hover:text-t-primary disabled:opacity-30 disabled:hover:bg-transparent"
                                        >
                                            <Icon name="chevron" className="size-4 fill-current rotate-180" />
                                        </button>
                                        <button
                                            onClick={() => move(i, 1)}
                                            disabled={i === team.length - 1 || busy}
                                            aria-label="Move down"
                                            className="grid place-items-center size-6 rounded-md text-t-tertiary transition-colors hover:bg-b-surface1 hover:text-t-primary disabled:opacity-30 disabled:hover:bg-transparent"
                                        >
                                            <Icon name="chevron" className="size-4 fill-current" />
                                        </button>
                                    </div>
                                )}

                                {/* priority badge */}
                                <span className="grid place-items-center size-9 max-sm:size-8 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle text-button text-t-secondary tabular-nums dark:bg-shade-04/50">
                                    {i + 1}
                                </span>

                                {/* identity */}
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="text-body-2 text-t-primary font-medium td-num truncate">
                                            {m.phone}
                                        </span>
                                        {m.role && (
                                            <span className="text-caption text-t-tertiary truncate">{m.role}</span>
                                        )}
                                    </div>
                                    <div className="mt-0.5 flex items-center gap-x-3 gap-y-0.5 flex-wrap text-caption text-t-tertiary">
                                        {m.whatsapp && (
                                            <span className="inline-flex items-center gap-1">
                                                <Icon name="chat" className="size-3.5 fill-t-tertiary" />
                                                <span className="td-num">{m.whatsapp}</span>
                                            </span>
                                        )}
                                        <span className="inline-flex items-center gap-1">
                                            <Icon name="clock" className="size-3.5 fill-t-tertiary" />
                                            {m.hours || "24×7"}
                                        </span>
                                    </div>
                                </div>

                                {/* enabled state */}
                                <div className="shrink-0 flex items-center gap-2.5 max-sm:gap-2">
                                    {writable ? (
                                        <Switch
                                            checked={m.enabled}
                                            onChange={(on) => toggleEnabled(i, on)}
                                        />
                                    ) : (
                                        <Badge variant={m.enabled ? "success" : "neutral"} dot>
                                            {m.enabled ? "On" : "Off"}
                                        </Badge>
                                    )}
                                    {writable && (
                                        <button
                                            onClick={() => remove(m.phone)}
                                            disabled={busy}
                                            aria-label="Remove contact"
                                            className="grid place-items-center size-8 rounded-lg text-t-tertiary transition-colors hover:bg-primary-03/10 hover:text-primary-03 disabled:opacity-40"
                                        >
                                            <Icon name="trash" className="size-4 fill-current" />
                                        </button>
                                    )}
                                </div>
                            </div>
                        </li>
                    ))}
                </ul>
            )}

            {!writable && me && team.length > 0 && (
                <p className="px-5 max-lg:px-3 pb-4 text-caption text-t-tertiary">
                    Your role is read-only — you can review the handoff team but not change it.
                </p>
            )}
        </>
    );

    /* ----------------------------------------------- the add-member modal */
    const modal = (
        <Modal open={addOpen} onClose={() => setAddOpen(false)} classWrapper="!max-w-115">
            <div className="text-h5 mb-1">Add an escalation contact</div>
            <p className="text-body-2 text-t-secondary mb-6">
                The AI will ring this person when a caller asks for a human or a lead is hot.
            </p>

            <div className="space-y-4">
                <ModalField
                    label="Phone number"
                    required
                    placeholder="+91 98765 43210"
                    value={form.phone}
                    onChange={(v) => setForm((f) => ({ ...f, phone: v }))}
                    hint="Indian mobile — must start with +91. This is the line the AI dials."
                />
                <ModalField
                    label="WhatsApp number"
                    placeholder="Same as phone, or another number"
                    value={form.whatsapp}
                    onChange={(v) => setForm((f) => ({ ...f, whatsapp: v }))}
                    hint="Where the hot lead is sent if nobody answers the call. Optional."
                />
                <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
                    <ModalField
                        label="Role"
                        placeholder="e.g. Sales lead"
                        value={form.role}
                        onChange={(v) => setForm((f) => ({ ...f, role: v }))}
                    />
                    <ModalField
                        label="Availability"
                        placeholder="e.g. 09:00-20:00 or 24x7"
                        value={form.hours}
                        onChange={(v) => setForm((f) => ({ ...f, hours: v }))}
                    />
                </div>
            </div>

            {formErr && (
                <div className="mt-4 flex items-center gap-2 p-3 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2">
                    <Icon name="info" className="size-4 fill-current shrink-0" />
                    {formErr}
                </div>
            )}

            <div className="mt-7 flex items-center justify-end gap-3">
                <Button isStroke onClick={() => setAddOpen(false)} disabled={saving}>
                    Cancel
                </Button>
                <Button isBlack icon="plus" onClick={submitAdd} disabled={saving || !form.phone.trim()}>
                    {saving ? "Adding…" : "Add to team"}
                </Button>
            </div>
        </Modal>
    );

    /* ------------------------------------------------------ compose surfaces */

    // The Card head action: priority/enabled summary + Add button.
    const headContent = (
        <div className="ml-auto flex items-center gap-2.5 max-sm:gap-2">
            {!loading && team.length > 0 && (
                <span className="text-caption text-t-tertiary max-sm:hidden">
                    {enabledCount} of {team.length} active
                </span>
            )}
            {writable && team.length > 0 && (
                <Button isStroke icon="plus" className="!h-9 !px-4 text-button" onClick={openAdd}>
                    Add
                </Button>
            )}
        </div>
    );

    return (
        <Card title={compact ? "Handoff team" : "Escalation contacts"} headContent={headContent}>
            <div className="px-5 max-lg:px-3 pb-3">{explainer}</div>
            {body}
            {modal}
        </Card>
    );
}

/* ----------------------------------------------------------- sub-components */

function ModalField({
    label,
    hint,
    required,
    placeholder,
    value,
    onChange,
}: {
    label: string;
    hint?: string;
    required?: boolean;
    placeholder?: string;
    value: string;
    onChange: (v: string) => void;
}) {
    return (
        <label className="block">
            <span className="block text-button mb-2 text-t-primary">
                {label}
                {required && <span className="text-primary-03 ml-0.5">*</span>}
            </span>
            <input
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={placeholder}
                className="input-base w-full h-11 px-4 rounded-2xl text-body-2"
            />
            {hint && <span className="block text-caption text-t-tertiary mt-1.5">{hint}</span>}
        </label>
    );
}
