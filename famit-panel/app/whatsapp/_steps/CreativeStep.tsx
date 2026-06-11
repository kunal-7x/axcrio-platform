// ④ CREATIVE SELECTION — browse the Asset Library, pick a banner (DraftsPage
// card-grid archetype + grid/list Tabs toggle). Browse/search/filter/attach
// approved banners via creative.search. NO manual upload.
//
// DORMANT-SAFE: :8310 dormant (404/503) → ComingSoon; the user can still skip to
// a text-only template, or open the Banner Studio (also dormant-safe).

"use client";

import { useCallback, useEffect, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Search from "@/components/Search";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Image from "@/components/Image";
import Spinner from "@/components/Spinner";
import Select from "@/components/Select";
import { type SelectOption } from "@/types/select";
import ComingSoon from "../_components/ComingSoon";
import { searchAssets } from "../_lib/waapi";
import { type StepCtx, type AssetRef } from "../_lib/types";

const ANGLE_OPTS: SelectOption[] = [
    { id: 0, name: "All angles" },
    { id: 1, name: "Price" },
    { id: 2, name: "Urgency" },
    { id: 3, name: "Trust" },
    { id: 4, name: "Offer" },
];
const SORT_OPTS: SelectOption[] = [
    { id: 0, name: "Top performing" },
    { id: 1, name: "Newest" },
];

export default function CreativeStep({ campaign, draft, setDraft, goTo, notify }: StepCtx) {
    const [phase, setPhase] = useState<"loading" | "ready" | "dormant">("loading");
    const [items, setItems] = useState<AssetRef[]>([]);
    const [q, setQ] = useState("");
    const [angle, setAngle] = useState<SelectOption>(ANGLE_OPTS[0]);
    const [sort, setSort] = useState<SelectOption>(SORT_OPTS[0]);

    const load = useCallback(async () => {
        setPhase("loading");
        const r = await searchAssets({
            campaign_id: campaign?.id,
            kind: "wa_poster,banner",
            status: "approved",
            angle: angle.id ? angle.name.toLowerCase() : undefined,
            sort: sort.id === 0 ? "top_ctr" : "newest",
        });
        if (!r.configured) {
            setPhase("dormant");
            return;
        }
        setItems(r.items);
        setPhase("ready");
    }, [campaign?.id, angle, sort]);

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [campaign?.id, angle.id, sort.id]);

    // client-side free-text filter over the loaded gallery (truthful, no refetch)
    const shown = items.filter((a) => {
        const s = q.trim().toLowerCase();
        if (!s) return true;
        return (a.title || "").toLowerCase().includes(s) || (a.angle || "").toLowerCase().includes(s);
    });

    const attach = (a: AssetRef) => {
        setDraft({ asset_id: a.id, asset_url: a.url || a.thumb_url, asset_approved: a.status === "approved" || a.status === "winner" });
        notify("Banner attached", "success");
        goTo("preview");
    };

    if (phase === "dormant") {
        return (
            <ComingSoon
                title="Creative selection"
                body="Connect the Asset Library and every banner you generate becomes instantly browseable, searchable and attachable here — no manual upload, ever."
                icon="camera"
                fallbackLabel="Generate a banner instead"
                onFallback={() => goTo("banner")}
            />
        );
    }

    return (
        <Card
            title="Pick a banner"
            headContent={
                <div className="flex items-center gap-2">
                    <Button isStroke icon="magic-pencil" onClick={() => goTo("banner")}>Generate new</Button>
                    <Button isStroke onClick={() => attach({ id: "", status: "approved" })}>Use no image</Button>
                </div>
            }
        >
            {/* filter row */}
            <div className="flex flex-wrap items-center gap-3 px-5 pb-3 max-lg:px-3">
                <Search className="w-56 max-md:w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search banners" isGray />
                <Select className="w-40" value={angle} onChange={setAngle} options={ANGLE_OPTS} />
                <Select className="w-44" value={sort} onChange={setSort} options={SORT_OPTS} />
            </div>

            {phase === "loading" ? (
                <div className="py-16"><Spinner /></div>
            ) : shown.length === 0 ? (
                <div className="flex flex-col items-center text-center py-16 px-5">
                    <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                        <Icon className="fill-t-secondary" name="camera" />
                    </div>
                    <div className="text-sub-title-1 text-t-primary">No banners yet for this campaign</div>
                    <div className="mt-1 max-w-80 text-body-2 text-t-secondary">Generate one in the Banner Studio — it auto-saves here.</div>
                    <Button isBlack className="mt-6" icon="magic-pencil" onClick={() => goTo("banner")}>Generate a banner</Button>
                </div>
            ) : (
                <div className="grid grid-cols-3 gap-4 p-5 pt-2 max-3xl:grid-cols-2 max-md:grid-cols-1">
                    {shown.map((a) => {
                        const selected = draft.asset_id === a.id;
                        return (
                            <button
                                key={a.id}
                                onClick={() => attach(a)}
                                className={`group flex flex-col text-left rounded-3xl overflow-hidden bg-b-surface2 ring-1 transition-shadow hover:shadow-depth ${selected ? "ring-primary-01" : "ring-s-subtle"}`}
                            >
                                <div className="relative h-44 w-full bg-b-surface1">
                                    {(a.thumb_url || a.url) && <Image className="object-cover" src={(a.thumb_url || a.url) as string} alt={a.title || ""} fill sizes="320px" />}
                                    {a.status === "winner" && <Badge className="absolute top-3 left-3" variant="success">Winner</Badge>}
                                </div>
                                <div className="flex items-center gap-2 p-3.5">
                                    <div className="grow min-w-0">
                                        <div className="text-button text-t-primary truncate">{a.title || "Banner"}</div>
                                        <div className="text-caption text-t-tertiary">
                                            {a.angle ? `${a.angle}` : "Banner"}{a.used_count != null ? ` · used in ${a.used_count}` : ""}
                                        </div>
                                    </div>
                                    {a.score != null && <Badge variant="info">{a.score}</Badge>}
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </Card>
    );
}
