"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Link, Element } from "react-scroll";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Switch from "@/components/Switch";
import Field from "@/components/Field";
import Icon from "@/components/Icon";
import { useMe } from "@/lib/auth";
import {
    getProfile,
    saveProfile,
    fileToAvatarDataURL,
    PRESET_AVATARS,
    EMOJI_CHOICES,
    type Profile,
} from "@/lib/profile";

// ROUND-6 LANE 4 — unified "Profile & Settings": a production-grade account page
// (photo upload + username + preset avatar / emoji + notification prefs + about +
// sign-out). Profile fields persist to lib/profile (localStorage; the navbar
// avatar reads the same store and updates live). Reuses Core_2 Card/Button/Field/
// Switch — no UI invented from scratch.
const sections = [
    { title: "Profile", icon: "profile", description: "Photo, name & avatar", to: "profile" },
    { title: "Account", icon: "logout", description: "Session & sign out", to: "account" },
    { title: "Notifications", icon: "bell", description: "How you get alerts", to: "notifications" },
    { title: "About", icon: "info", description: "Platform details", to: "about" },
];

const ElementWithOffset = ({ name, children }: { name: string; children: React.ReactNode }) => (
    <div className="relative">
        <Element className="absolute -top-22 left-0 right-0" name={name} />
        {children}
    </div>
);

export default function SettingsPage() {
    const router = useRouter();
    const { me } = useMe();
    const [showConfirm, setShowConfirm] = useState(false);
    const [callAlerts, setCallAlerts] = useState(true);
    const [dailyDigest, setDailyDigest] = useState(false);
    const [approvals, setApprovals] = useState(true);

    // ── Profile state (hydrated from the local store on mount) ──
    const [profile, setProfile] = useState<Profile>(getProfile);
    const [savedTick, setSavedTick] = useState(false);
    const [uploadErr, setUploadErr] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    // Seed the username from /me the first time if the user never set one.
    useEffect(() => {
        if (!profile.username && me?.name) {
            setProfile((p) => ({ ...p, username: me.name }));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [me?.name]);

    function patch(p: Partial<Profile>) {
        setProfile((cur) => ({ ...cur, ...p }));
    }

    function handleSaveProfile() {
        const clean: Profile = { ...profile, username: profile.username.trim() };
        setProfile(clean);
        saveProfile(clean);
        setSavedTick(true);
        setTimeout(() => setSavedTick(false), 2200);
    }

    async function handlePhoto(file: File | null) {
        setUploadErr("");
        if (!file) return;
        if (!file.type.startsWith("image/")) {
            setUploadErr("Please choose an image file (PNG or JPG).");
            return;
        }
        if (file.size > 8 * 1024 * 1024) {
            setUploadErr("That image is over 8 MB — pick a smaller one.");
            return;
        }
        try {
            const dataUrl = await fileToAvatarDataURL(file);
            patch({ photo: dataUrl, avatarKind: "photo" });
        } catch (e) {
            setUploadErr(e instanceof Error ? e.message : "Could not process that image.");
        }
    }

    function handleLogout() {
        if (typeof window !== "undefined") {
            localStorage.removeItem("famit_token");
        }
        router.push("/login");
    }

    const prefs = [
        { id: 1, title: "Call outcome alerts", checked: callAlerts, onChange: setCallAlerts },
        { id: 2, title: "Daily digest email", checked: dailyDigest, onChange: setDailyDigest },
        { id: 3, title: "Approval requests", checked: approvals, onChange: setApprovals },
    ];

    return (
        <Layout title="Profile & Settings">
            <div className="flex items-start max-lg:block">
                {/* Sticky section menu */}
                <div className="card sticky top-22 shrink-0 w-80 max-3xl:w-72 max-2xl:w-64 max-lg:hidden">
                    <div className="flex flex-col gap-1">
                        {sections.map((item) => (
                            <Link
                                key={item.to}
                                className="group relative flex items-center h-16 px-3 cursor-pointer"
                                activeClass="[&_.box-hover]:!visible [&_.box-hover]:!opacity-100"
                                to={item.to}
                                smooth
                                duration={500}
                                spy
                                offset={-100}
                            >
                                <div className="box-hover" />
                                <div className="relative z-2 flex justify-center items-center shrink-0 size-11 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name={item.icon} />
                                </div>
                                <div className="relative z-2 w-[calc(100%-2.75rem)] pl-4">
                                    <div className="text-button">{item.title}</div>
                                    <div className="mt-1 truncate text-caption text-t-secondary">{item.description}</div>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>

                {/* Section cards */}
                <div className="flex flex-col gap-3 w-[calc(100%-20rem)] pl-3 max-3xl:w-[calc(100%-18rem)] max-2xl:w-[calc(100%-16rem)] max-lg:w-full max-lg:pl-0">
                    {/* ── PROFILE ── */}
                    <ElementWithOffset name="profile">
                        <Card title="Profile">
                            <div className="px-5 pb-6 pt-2 max-lg:px-3">
                                {/* Avatar + uploader */}
                                <div className="flex items-center gap-5 max-md:flex-col max-md:items-start">
                                    <AvatarPreview profile={profile} />
                                    <div className="flex flex-col gap-2">
                                        <div className="flex items-center gap-3">
                                            <Button
                                                isStroke
                                                className="!h-10 !px-4"
                                                onClick={() => fileRef.current?.click()}
                                            >
                                                <Icon className="size-4 fill-t-secondary mr-1.5" name="upload" />
                                                Upload photo
                                            </Button>
                                            {profile.photo && (
                                                <button
                                                    type="button"
                                                    className="text-caption text-t-tertiary hover:text-primary-03 transition-colors"
                                                    onClick={() => patch({ photo: "", avatarKind: "preset" })}
                                                >
                                                    Remove
                                                </button>
                                            )}
                                        </div>
                                        <div className="text-caption text-t-tertiary">
                                            PNG or JPG, square works best — auto-cropped to a circle.
                                        </div>
                                        <input
                                            ref={fileRef}
                                            type="file"
                                            accept="image/png,image/jpeg,image/webp"
                                            className="hidden"
                                            onChange={(e) => handlePhoto(e.target.files?.[0] ?? null)}
                                        />
                                        {uploadErr && (
                                            <div className="text-caption text-primary-03">{uploadErr}</div>
                                        )}
                                    </div>
                                </div>

                                {/* Username */}
                                <div className="mt-6 max-w-md">
                                    <Field
                                        label="Display name"
                                        placeholder="e.g. Kunal Kumar"
                                        value={profile.username}
                                        onChange={(e) => patch({ username: e.target.value })}
                                    />
                                </div>

                                {/* Preset avatars */}
                                <div className="mt-6">
                                    <div className="text-button mb-3">Choose an avatar</div>
                                    <div className="flex flex-wrap gap-2.5">
                                        {PRESET_AVATARS.map((src) => {
                                            const active = profile.avatarKind === "preset" && profile.preset === src;
                                            return (
                                                <button
                                                    key={src}
                                                    type="button"
                                                    onClick={() => patch({ preset: src, avatarKind: "preset" })}
                                                    className={`relative size-12 rounded-full overflow-hidden ring-2 transition-all ${
                                                        active ? "ring-primary-01" : "ring-transparent hover:ring-s-highlight"
                                                    }`}
                                                    aria-label="Use this avatar"
                                                >
                                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                                    <img src={src} alt="" className="size-full object-cover" />
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Emoji avatars */}
                                <div className="mt-6">
                                    <div className="text-button mb-3">…or pick an emoji</div>
                                    <div className="flex flex-wrap gap-2">
                                        {EMOJI_CHOICES.map((em) => {
                                            const active = profile.avatarKind === "emoji" && profile.emoji === em;
                                            return (
                                                <button
                                                    key={em}
                                                    type="button"
                                                    onClick={() => patch({ emoji: em, avatarKind: "emoji" })}
                                                    className={`grid place-items-center size-11 rounded-full text-xl bg-b-surface1 ring-2 transition-all ${
                                                        active ? "ring-primary-01" : "ring-transparent hover:ring-s-highlight"
                                                    }`}
                                                    aria-label={`Use ${em}`}
                                                >
                                                    {em}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Save */}
                                <div className="mt-7 flex items-center gap-3">
                                    <Button isBlack className="!h-11 !px-6" onClick={handleSaveProfile}>
                                        Save profile
                                    </Button>
                                    {savedTick && (
                                        <span className="inline-flex items-center gap-1.5 text-caption text-primary-02">
                                            <Icon className="size-4 fill-primary-02" name="check-circle" />
                                            Saved
                                        </span>
                                    )}
                                </div>
                            </div>
                        </Card>
                    </ElementWithOffset>

                    {/* ── ACCOUNT ── */}
                    <ElementWithOffset name="account">
                        <Card title="Account">
                            <div className="flex justify-between items-center gap-6 px-5 pb-5 pt-2 max-lg:px-3">
                                <div>
                                    <div className="text-button text-t-primary">Session</div>
                                    <div className="mt-1 text-caption text-t-secondary">
                                        {me?.email ? `Signed in as ${me.email}` : "You are currently signed in."}
                                    </div>
                                </div>
                                {!showConfirm ? (
                                    <Button
                                        isStroke
                                        className="shrink-0 !h-10 !px-5 hover:!border-primary-03/40 hover:!text-primary-03"
                                        onClick={() => setShowConfirm(true)}
                                    >
                                        Sign out
                                    </Button>
                                ) : (
                                    <div className="flex items-center gap-3 shrink-0">
                                        <span className="text-caption text-t-secondary">Confirm?</span>
                                        <Button
                                            isStroke
                                            className="!h-10 !px-4 !border-primary-03/40 !text-primary-03 hover:!border-primary-03"
                                            onClick={handleLogout}
                                        >
                                            Yes, sign out
                                        </Button>
                                        <Button isStroke className="!h-10 !px-4" onClick={() => setShowConfirm(false)}>
                                            Cancel
                                        </Button>
                                    </div>
                                )}
                            </div>
                        </Card>
                    </ElementWithOffset>

                    {/* ── NOTIFICATIONS ── */}
                    <ElementWithOffset name="notifications">
                        <Card title="Notifications">
                            <div className="px-5 max-lg:px-3">
                                {prefs.map((p) => (
                                    <div
                                        key={p.id}
                                        className="flex justify-between items-center gap-6 py-5 border-b border-s-subtle last:border-b-0"
                                    >
                                        <div className="text-button text-t-primary">{p.title}</div>
                                        <Switch
                                            className="shrink-0"
                                            checked={p.checked}
                                            onChange={() => p.onChange(!p.checked)}
                                        />
                                    </div>
                                ))}
                            </div>
                        </Card>
                    </ElementWithOffset>

                    {/* ── ABOUT ── */}
                    <ElementWithOffset name="about">
                        <Card title="About Famit">
                            <div className="px-5 pb-5 pt-2 max-lg:px-3">
                                {[
                                    ["Product", "Famit AI Tele-Calling"],
                                    ["Agent", "Riya (Hindi/Hinglish)"],
                                    ["Backend", "panel.famit.in"],
                                    ["Version", "core-2"],
                                ].map(([k, v]) => (
                                    <div
                                        key={k}
                                        className="flex justify-between items-center gap-6 py-4 border-b border-s-subtle last:border-b-0 text-body-2"
                                    >
                                        <span className="text-t-secondary">{k}</span>
                                        <span className="text-t-primary font-medium">{v}</span>
                                    </div>
                                ))}
                            </div>
                        </Card>
                    </ElementWithOffset>
                </div>
            </div>
        </Layout>
    );
}

// The big live avatar preview (photo / preset image / emoji).
function AvatarPreview({ profile }: { profile: Profile }) {
    const ring = "ring-1 ring-s-subtle";
    if (profile.avatarKind === "emoji") {
        return (
            <div className={`grid place-items-center size-20 rounded-full bg-b-surface1 text-4xl shrink-0 ${ring}`}>
                {profile.emoji}
            </div>
        );
    }
    const src =
        profile.avatarKind === "photo" && profile.photo ? profile.photo : profile.preset;
    return (
        <div className={`size-20 rounded-full overflow-hidden bg-b-surface1 shrink-0 ${ring}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={src} alt="Avatar preview" className="size-full object-cover" />
        </div>
    );
}
