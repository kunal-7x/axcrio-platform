"use client";

/**
 * S7 — BRAND KIT. The brand memory the AI honours everywhere (cs-workspace §10).
 * Ports the SettingsPage grammar: a sticky left anchor menu + stacked section
 * Cards (Logo · Colours · Tone & language · Preferred CTA · Do-not-use · Auto-
 * extract). Binds GET/POST /api/assets/brand-kits. The vendor sets it once.
 *
 * ⭐ F1 out-of-the-box: "Extract from my website / a logo" seeds palette+logo+tone
 * — dormant-safe (degrades to a calm note if the extract endpoint isn't live yet).
 * Single <Layout title="Brand Kit">, no PageHeader, zero raw hex, Inter Display.
 */

import { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Field from "@/components/Field";
import FieldImage from "@/components/FieldImage";
import Select from "@/components/Select";
import Button from "@/components/Button";
import Spinner from "@/components/Spinner";
import Icon from "@/components/Icon";
import type { SelectOption } from "@/types/select";
import useAssetStatus from "../_hooks/useAssetStatus";
import DormantCard from "../_components/DormantCard";
import {
    getBrandKits,
    saveBrandKit,
    extractBrandKit,
    AssetDormantError,
    type BrandKit,
} from "@/lib/assets";

const ANCHORS = [
    { id: "logo", name: "Logo" },
    { id: "colours", name: "Colours" },
    { id: "tone", name: "Tone & language" },
    { id: "cta", name: "Preferred CTA" },
    { id: "avoid", name: "Do-not-use" },
    { id: "extract", name: "Auto-extract" },
];

const LANGUAGES: SelectOption[] = [
    { id: 1, name: "English" },
    { id: 2, name: "Hindi" },
    { id: 3, name: "Hinglish" },
    { id: 4, name: "Gujarati" },
];

const Page = () => {
    const { enabled, loading } = useAssetStatus();
    const [kit, setKit] = useState<BrandKit | null>(null);
    const [saving, setSaving] = useState(false);
    const [savedNote, setSavedNote] = useState<string | null>(null);

    // editable local mirror
    const [palette, setPalette] = useState<string[]>([]);
    const [newColor, setNewColor] = useState("");
    const [tone, setTone] = useState("");
    const [language, setLanguage] = useState<SelectOption>(LANGUAGES[0]);
    const [defaultCta, setDefaultCta] = useState("");
    const [doNotUse, setDoNotUse] = useState("");
    const [extractUrl, setExtractUrl] = useState("");
    const [extractNote, setExtractNote] = useState<string | null>(null);
    const [extracting, setExtracting] = useState(false);

    useEffect(() => {
        if (!enabled) return;
        getBrandKits().then(({ brand_kits }) => {
            const k = brand_kits[0] || null;
            setKit(k);
            if (k) {
                setPalette(k.palette || []);
                setTone((k.tone || []).join(", "));
                setDefaultCta((k.default_cta || []).join(", "));
                setDoNotUse((k.do_not_use?.words || []).join(", "));
                const langMatch = LANGUAGES.find(
                    (l) => l.name.toLowerCase() === (k.language_pref || "").toLowerCase()
                );
                if (langMatch) setLanguage(langMatch);
            }
        });
    }, [enabled]);

    const save = async () => {
        setSaving(true);
        setSavedNote(null);
        try {
            const saved = await saveBrandKit({
                id: kit?.id,
                palette,
                tone: tone.split(",").map((s) => s.trim()).filter(Boolean),
                language_pref: language.name,
                default_cta: defaultCta.split(",").map((s) => s.trim()).filter(Boolean),
                do_not_use: { words: doNotUse.split(",").map((s) => s.trim()).filter(Boolean) },
            });
            setKit(saved);
            setSavedNote("Brand kit saved.");
        } catch (e) {
            setSavedNote(e instanceof Error ? e.message : "Couldn't save the brand kit.");
        } finally {
            setSaving(false);
        }
    };

    const addColor = () => {
        const c = newColor.trim();
        if (c && !palette.includes(c)) setPalette((p) => [...p, c]);
        setNewColor("");
    };

    const runExtract = async () => {
        setExtracting(true);
        setExtractNote(null);
        try {
            const extracted = await extractBrandKit({ url: extractUrl.trim() || undefined });
            setPalette(extracted.palette || palette);
            setTone((extracted.tone || []).join(", ") || tone);
            setExtractNote("Pulled your brand basics — review and save.");
        } catch (e) {
            if (e instanceof AssetDormantError) {
                setExtractNote("Auto-extract is coming soon. You can set your brand by hand below for now.");
            } else {
                setExtractNote("Couldn't read that source. Try a different URL or add details by hand.");
            }
        } finally {
            setExtracting(false);
        }
    };

    if (loading) {
        return (
            <Layout title="Brand Kit">
                <div className="py-24">
                    <Spinner />
                </div>
            </Layout>
        );
    }

    if (!enabled) {
        return (
            <Layout title="Brand Kit">
                <DormantCard
                    title="Your brand kit activates with Creative Studio"
                    message="Set your logo, colours and tone once — the AI honours them on every creative it makes."
                    icon="feather"
                />
            </Layout>
        );
    }

    return (
        <Layout title="Brand Kit">
            <div className="flex items-start gap-3 max-lg:block">
                {/* sticky anchor menu */}
                <div className="shrink-0 w-60 sticky top-22 max-lg:hidden">
                    <div className="card !p-2">
                        {ANCHORS.map((a) => (
                            <a
                                key={a.id}
                                href={`#${a.id}`}
                                className="flex items-center h-11 px-4 rounded-2xl text-button text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04/50"
                            >
                                {a.name}
                            </a>
                        ))}
                    </div>
                </div>

                {/* section cards */}
                <div className="grow min-w-0">
                    <div id="logo">
                        <Card title="Logo">
                            <div className="px-5 max-lg:px-3">
                                <FieldImage
                                    onChange={() => {}}
                                    initialImage={kit?.logo_url}
                                />
                                <p className="mt-3 text-caption text-t-tertiary">
                                    Your HD logo — placed at the right size on every composite.
                                </p>
                            </div>
                        </Card>
                    </div>

                    <div id="colours">
                        <Card title="Colours">
                            <div className="px-5 max-lg:px-3">
                                <div className="flex flex-wrap items-center gap-2 mb-4">
                                    {palette.map((c, i) => (
                                        <span
                                            key={`${c}-${i}`}
                                            className="group relative size-9 rounded-full ring-1 ring-s-subtle ring-inset"
                                            style={{ backgroundColor: c }}
                                            title={c}
                                        >
                                            <button
                                                className="absolute -top-1 -right-1 size-4 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-0 opacity-0 transition-opacity group-hover:opacity-100"
                                                onClick={() => setPalette((p) => p.filter((_, j) => j !== i))}
                                            >
                                                <Icon className="!size-3 fill-t-secondary" name="close" />
                                            </button>
                                        </span>
                                    ))}
                                    {palette.length === 0 && (
                                        <span className="text-body-2 text-t-secondary">No colours yet.</span>
                                    )}
                                </div>
                                <div className="flex items-end gap-3 max-md:flex-col max-md:items-stretch">
                                    <Field
                                        className="grow"
                                        label="Add a colour"
                                        placeholder="#0B5FFF or rgb(...)"
                                        value={newColor}
                                        onChange={(e) => setNewColor(e.target.value)}
                                    />
                                    <Button isStroke onClick={addColor}>
                                        Add
                                    </Button>
                                </div>
                            </div>
                        </Card>
                    </div>

                    <div id="tone">
                        <Card title="Tone & language">
                            <div className="px-5 max-lg:px-3 space-y-4">
                                <Field
                                    label="Tone"
                                    placeholder="premium, warm, trustworthy"
                                    value={tone}
                                    onChange={(e) => setTone(e.target.value)}
                                />
                                <Select
                                    label="Language"
                                    value={language}
                                    onChange={setLanguage}
                                    options={LANGUAGES}
                                />
                            </div>
                        </Card>
                    </div>

                    <div id="cta">
                        <Card title="Preferred CTA">
                            <div className="px-5 max-lg:px-3">
                                <Field
                                    label="Default CTAs"
                                    placeholder="Book Site Visit, Call Now, Enquire"
                                    value={defaultCta}
                                    onChange={(e) => setDefaultCta(e.target.value)}
                                />
                            </div>
                        </Card>
                    </div>

                    <div id="avoid">
                        <Card title="Do-not-use">
                            <div className="px-5 max-lg:px-3">
                                <Field
                                    label="Words & styles to avoid"
                                    placeholder="cheap, discount-heavy look"
                                    value={doNotUse}
                                    onChange={(e) => setDoNotUse(e.target.value)}
                                />
                                <p className="mt-3 text-caption text-t-tertiary">
                                    The AI avoids these — and learns from what you reject.
                                </p>
                            </div>
                        </Card>
                    </div>

                    <div id="extract">
                        <Card title="Auto-extract brand kit">
                            <div className="px-5 max-lg:px-3">
                                <p className="text-body-2 text-t-secondary mb-4">
                                    Paste your website and we&apos;ll pull your palette, logo and tone.
                                </p>
                                <div className="flex items-end gap-3 max-md:flex-col max-md:items-stretch">
                                    <Field
                                        className="grow"
                                        label="Website URL"
                                        placeholder="https://yourbrand.com"
                                        value={extractUrl}
                                        onChange={(e) => setExtractUrl(e.target.value)}
                                    />
                                    <Button isStroke icon="magic-pencil" onClick={runExtract} disabled={extracting}>
                                        {extracting ? "Reading…" : "Extract"}
                                    </Button>
                                </div>
                                {extractNote && (
                                    <p className="mt-3 text-caption text-t-tertiary">{extractNote}</p>
                                )}
                            </div>
                        </Card>
                    </div>

                    {/* save bar */}
                    <div className="flex items-center gap-3 mt-4">
                        {savedNote && <span className="text-body-2 text-t-secondary">{savedNote}</span>}
                        <Button className="ml-auto" isBlack onClick={save} disabled={saving}>
                            {saving ? "Saving…" : "Save brand kit"}
                        </Button>
                    </div>
                </div>
            </div>
        </Layout>
    );
};

export default Page;
