"use client";
// The "make a model" surface: three input modes — a built-in Sample (zero config),
// an uploaded floor-plan image (vision), or a free-text brief (LLM). Each mode creates
// a project then builds it; errors surface as calm inline notices (never error-walls).
import { useRef, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import {
    analyzeImage,
    buildFromSample,
    buildFromText,
    createProject,
    PModelError,
    type BuildResult,
    type SampleInfo,
} from "@/lib/pmodel";

type Mode = "sample" | "upload" | "describe";
type Notice = { kind: "info" | "warning"; text: string } | null;

const errText = (e: unknown): string => {
    const code = e instanceof PModelError ? e.code : "";
    if (code.includes("not_configured"))
        return "The AI vision model isn't configured yet (set OPENROUTER_API_KEY). You can still use the sample homes.";
    if (code === "no_rooms_detected")
        return "Couldn't read rooms from that plan. Try a clearer, top-down floor plan image.";
    return "Something went wrong building the model. Please try again.";
};

export default function CreatePanel({
    vision,
    samples,
    onBuilt,
    onBusyChange,
}: {
    vision: boolean;
    samples: SampleInfo[];
    onBuilt: (r: BuildResult) => void;
    onBusyChange?: (b: boolean) => void;
}) {
    const [mode, setMode] = useState<Mode>("sample");
    const [busy, setBusy] = useState(false);
    const [notice, setNotice] = useState<Notice>(null);
    const [sampleKind, setSampleKind] = useState(samples[0]?.kind || "apartment_2bhk");
    const [name, setName] = useState("");
    const [prompt, setPrompt] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    async function run(fn: () => Promise<BuildResult>) {
        setNotice(null);
        setBusy(true);
        onBusyChange?.(true);
        try {
            onBuilt(await fn());
        } catch (e) {
            setNotice({ kind: "warning", text: errText(e) });
        } finally {
            setBusy(false);
            onBusyChange?.(false);
        }
    }

    const genSample = () =>
        run(async () => {
            const title = samples.find((s) => s.kind === sampleKind)?.title || "Sample home";
            const p = await createProject(name || title);
            return buildFromSample(p.id, sampleKind);
        });

    const genUpload = () =>
        run(async () => {
            const f = fileRef.current?.files?.[0];
            if (!f) throw new PModelError("no_file", "Choose a floor plan image first.");
            const p = await createProject(name || f.name.replace(/\.[^.]+$/, ""));
            return analyzeImage(p.id, f);
        });

    const genText = () =>
        run(async () => {
            if (!prompt.trim()) throw new PModelError("no_prompt", "Describe the home first.");
            const p = await createProject(name || prompt.slice(0, 40));
            return buildFromText(p.id, prompt.trim());
        });

    const Tab = ({ id, label }: { id: Mode; label: string }) => (
        <button
            type="button"
            onClick={() => { setMode(id); setNotice(null); }}
            className={`h-8 px-3 rounded-full text-[13px] font-semibold transition-colors ${
                mode === id ? "bg-primary-01 text-white" : "bg-b-surface1 text-t-secondary hover:text-t-primary"
            }`}
        >
            {label}
        </button>
    );

    return (
        <Card title="Create a 3D model">
            <div className="px-5 pb-5 pt-1">
                <div className="flex gap-2 mb-4">
                    <Tab id="sample" label="Sample" />
                    <Tab id="upload" label="Upload plan" />
                    <Tab id="describe" label="Describe" />
                </div>

                <label className="block mb-3">
                    <span className="text-caption text-t-tertiary">Project name (optional)</span>
                    <input
                        className="input-base focus-ring mt-1 w-full"
                        placeholder="e.g. Marina Heights · 3 BHK"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />
                </label>

                {mode === "sample" && (
                    <div>
                        <div className="text-caption text-t-tertiary mb-2">Pick a starter home</div>
                        <div className="grid gap-2">
                            {samples.map((s) => (
                                <button
                                    key={s.kind}
                                    type="button"
                                    onClick={() => setSampleKind(s.kind)}
                                    className={`text-left rounded-xl border px-3 py-2.5 transition-colors ${
                                        sampleKind === s.kind
                                            ? "border-primary-01 bg-primary-01/5"
                                            : "border-s-subtle hover:border-s-stroke2"
                                    }`}
                                >
                                    <div className="text-body-2 font-semibold">{s.title}</div>
                                    <div className="text-caption text-t-tertiary">{s.desc}</div>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {mode === "upload" && (
                    <div>
                        {!vision && (
                            <div className="mb-3 rounded-lg bg-[#EF9D0E]/12 px-3 py-2 text-caption text-[#8a5e07]">
                                Vision model not configured — uploads need OPENROUTER_API_KEY. Try a Sample meanwhile.
                            </div>
                        )}
                        <div className="text-caption text-t-tertiary mb-2">
                            Upload a top-down floor plan (PNG / JPG)
                        </div>
                        <input
                            ref={fileRef}
                            type="file"
                            accept="image/*"
                            className="block w-full text-body-2 file:mr-3 file:rounded-full file:border-0 file:bg-b-surface1 file:px-4 file:py-2 file:text-body-2 file:font-semibold"
                        />
                        <div className="text-caption text-t-tertiary mt-2">
                            The AI reads rooms, walls and doors, then builds a navigable model.
                        </div>
                    </div>
                )}

                {mode === "describe" && (
                    <div>
                        <div className="text-caption text-t-tertiary mb-2">Describe the home</div>
                        <textarea
                            className="input-base focus-ring w-full min-h-28 resize-y"
                            placeholder="3 BHK, ~1200 sq ft, living room opening to a balcony, kitchen beside dining, two bedrooms with attached baths…"
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                        />
                    </div>
                )}

                {notice && (
                    <div
                        className={`mt-3 rounded-lg px-3 py-2 text-caption ${
                            notice.kind === "warning" ? "bg-warning/10 text-warning" : "bg-primary-01/10 text-primary-01"
                        }`}
                    >
                        {notice.text}
                    </div>
                )}

                <div className="mt-4">
                    <Button
                        isBlack
                        className="w-full"
                        disabled={busy}
                        onClick={mode === "sample" ? genSample : mode === "upload" ? genUpload : genText}
                    >
                        {busy ? "Building model…" : "Generate 3D model"}
                    </Button>
                </div>
            </div>
        </Card>
    );
}
