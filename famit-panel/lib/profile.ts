"use client";

// ============================================================================
// ROUND-6 LANE 4 — local profile store (photo / username / avatar / emoji).
//
// The Profile & Settings page (app/settings) writes here; the top-navbar avatar
// (components/Header/User) reads here so a change shows instantly everywhere.
// Persisted to localStorage (durable across reloads) and broadcast via a custom
// event + the native `storage` event so an open tab updates live (no refresh).
//
// This is the FRONTEND lane: there is no profile-write backend endpoint exposed
// in this lane, so the store is client-local (per-browser). If/when a backend
// /me/profile PUT lands, swap `save` to also POST — the read API stays the same.
// ============================================================================

export type AvatarKind = "photo" | "preset" | "emoji";

export type Profile = {
    username: string;
    avatarKind: AvatarKind;
    // photo: a data: URL (uploaded image, downscaled). preset: "/images/avatars/N.png".
    photo: string;
    preset: string;
    emoji: string;
};

const KEY = "famit_profile";
export const PROFILE_EVENT = "famit:profile-changed";

export const DEFAULT_PROFILE: Profile = {
    username: "",
    avatarKind: "preset",
    photo: "",
    preset: "/images/avatar-sm.png",
    emoji: "🙂",
};

// Built-in preset avatars shipped with the panel (public/images/avatars/*).
export const PRESET_AVATARS: string[] = [
    "/images/avatar-sm.png",
    ...Array.from({ length: 9 }, (_, i) => `/images/avatars/${i + 1}.png`),
];

// A small curated emoji set for the "avatar/emoji" option.
export const EMOJI_CHOICES = [
    "🙂", "😎", "🚀", "🔥", "💼", "📞", "🎯", "⭐", "💡", "🤝",
    "🦄", "🐯", "🌙", "🍀", "👑", "⚡",
];

export function getProfile(): Profile {
    if (typeof window === "undefined") return DEFAULT_PROFILE;
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return DEFAULT_PROFILE;
        return { ...DEFAULT_PROFILE, ...(JSON.parse(raw) as Partial<Profile>) };
    } catch {
        return DEFAULT_PROFILE;
    }
}

export function saveProfile(p: Profile): void {
    if (typeof window === "undefined") return;
    try {
        localStorage.setItem(KEY, JSON.stringify(p));
        // Notify same-tab listeners (storage event only fires cross-tab).
        window.dispatchEvent(new CustomEvent(PROFILE_EVENT));
    } catch {
        /* quota / private mode — ignore, UI still reflects in-memory state */
    }
}

// The image src the navbar/avatar should render for a profile (emoji handled by
// the caller as text, so this returns "" for the emoji kind).
export function avatarSrc(p: Profile): string {
    if (p.avatarKind === "photo" && p.photo) return p.photo;
    if (p.avatarKind === "preset" && p.preset) return p.preset;
    if (p.avatarKind === "emoji") return "";
    return p.preset || DEFAULT_PROFILE.preset;
}

// Downscale an uploaded image File to a square data URL (≤256px, JPEG q0.82) so
// localStorage stays small and the avatar loads instantly. Returns a data: URL.
export function fileToAvatarDataURL(file: File, size = 256): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("Could not read the image."));
        reader.onload = () => {
            const img = new Image();
            img.onerror = () => reject(new Error("That file is not a valid image."));
            img.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width = size;
                canvas.height = size;
                const ctx = canvas.getContext("2d");
                if (!ctx) return reject(new Error("Canvas unavailable."));
                // center-crop to a square
                const min = Math.min(img.width, img.height);
                const sx = (img.width - min) / 2;
                const sy = (img.height - min) / 2;
                ctx.drawImage(img, sx, sy, min, min, 0, 0, size, size);
                resolve(canvas.toDataURL("image/jpeg", 0.82));
            };
            img.src = String(reader.result);
        };
        reader.readAsDataURL(file);
    });
}
