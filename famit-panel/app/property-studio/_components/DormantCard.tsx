"use client";
import Card from "@/components/Card";

export default function DormantCard() {
    return (
        <Card title="Property Studio">
            <div className="px-5 py-10 max-w-xl">
                <div className="text-h6 mb-2">Turn 2D floor plans into interactive 3D homes</div>
                <p className="text-body-2 text-t-secondary mb-4">
                    Property Studio isn&apos;t enabled for this workspace yet. Once switched on you can
                    upload a floor plan (or just describe a home), get a navigable 3D model in seconds,
                    and send customers a shareable walkthrough link — straight from a call.
                </p>
                <div className="text-caption text-t-tertiary">
                    Ask an admin to set <code className="px-1 rounded bg-b-surface1">FEATURE_PMODEL=1</code> on the
                    backend. The upload &amp; describe modes also need{" "}
                    <code className="px-1 rounded bg-b-surface1">OPENROUTER_API_KEY</code>; built-in sample homes
                    work with no keys at all.
                </div>
            </div>
        </Card>
    );
}
