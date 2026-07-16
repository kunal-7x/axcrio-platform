"use client";
// PUBLIC customer-facing 3D property model. No login (exempted in app/providers.tsx).
// The voice agent can text this link mid-call; the customer explores the home and taps
// the branded call-to-action to book a visit — closing the loop back into the funnel.
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { getShare, type ShareData } from "@/lib/pmodel";

const ModelViewer = dynamic(() => import("@/app/property-studio/_components/ModelViewer"), {
    ssr: false,
    loading: () => (
        <div className="flex h-full items-center justify-center bg-[#0c1018] text-white/70">
            Loading 3D model…
        </div>
    ),
});

export default function SharePage() {
    const params = useParams<{ token: string }>();
    const token = params?.token as string;
    const [data, setData] = useState<ShareData | null>(null);
    const [err, setErr] = useState(false);

    useEffect(() => {
        if (!token) return;
        getShare(token)
            .then(setData)
            .catch(() => setErr(true));
    }, [token]);

    if (err)
        return (
            <div className="flex min-h-screen flex-col items-center justify-center bg-b-surface1 px-6 text-center">
                <div className="text-h5 mb-2">This 3D model link isn&apos;t available</div>
                <p className="text-body-2 text-t-secondary">
                    The link may have been unpublished. Please ask your agent for an updated link.
                </p>
            </div>
        );

    if (!data)
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#0c1018] text-white/70">
                Loading 3D model…
            </div>
        );

    const b = data.branding;
    return (
        <div className="flex h-[100dvh] flex-col bg-[#0c1018]">
            <header className="flex items-center justify-between gap-3 px-5 py-3 text-white">
                <div className="min-w-0">
                    <div className="truncate text-[17px] font-semibold leading-tight">{data.name}</div>
                    <div className="text-[12px] text-white/55">{b.tagline}</div>
                </div>
                <div className="shrink-0 text-[12px] text-white/45">
                    Powered by <span className="font-semibold text-white/70">{b.brand}</span>
                </div>
            </header>

            <div className="relative min-h-0 flex-1 px-3">
                <ModelViewer scene={data.scene} title={data.name} className="h-full" />
            </div>

            <footer className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="text-[13px] text-white/60">
                    {data.scene.meta.bedrooms} bed · {data.scene.meta.baths} bath ·{" "}
                    {data.scene.meta.rooms} rooms · {Math.round(data.scene.meta.area_sqft)} ft²
                </div>
                {b.cta_href ? (
                    <a
                        href={b.cta_href}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-full bg-[#2A85FF] px-5 py-2.5 text-[14px] font-semibold text-white shadow-[0_6px_18px_rgba(42,133,255,.4)] transition-transform active:scale-[0.98]"
                    >
                        {b.cta_label} →
                    </a>
                ) : (
                    <span className="rounded-full bg-white/10 px-5 py-2.5 text-[14px] font-semibold text-white/85">
                        {b.cta_label}
                    </span>
                )}
            </footer>
        </div>
    );
}
