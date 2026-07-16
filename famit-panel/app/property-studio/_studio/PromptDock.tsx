"use client";
// Bottom prompt dock (Brainwave PanelMessage), dark. Describe a home OR attach a floor
// plan via the + button, pick is implicit (a file → upload mode), then send.
import { useRef, useState } from "react";
import TextareaAutosize from "react-textarea-autosize";
import { useStudio } from "./store";
import Ico from "./icons";

export default function PromptDock({ className = "" }: { className?: string }) {
    const vision = useStudio((s) => s.vision);
    const provider = useStudio((s) => s.visionProvider);
    const busy = useStudio((s) => s.busy);
    const notice = useStudio((s) => s.notice);
    const buildText = useStudio((s) => s.buildText);
    const buildUpload = useStudio((s) => s.buildUpload);

    const [prompt, setPrompt] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const fileRef = useRef<HTMLInputElement>(null);

    const canSend = !busy && (file ? true : prompt.trim().length > 0);
    function send() {
        if (file) buildUpload(file);
        else buildText(prompt);
    }

    return (
        <div className={className}>
            {notice && <div className="bw-notice bw-notice-warn mb-2">{notice.text}</div>}
            <div className="bw-dock">
                {file ? (
                    <div className="mb-3 flex items-center gap-2 px-1">
                        <span className="bw-row-ic !size-8"><Ico name="image" size={16} /></span>
                        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{file.name}</span>
                        <button type="button" className="bw-icon !size-7" onClick={() => setFile(null)} title="Remove"><Ico name="x" size={15} /></button>
                    </div>
                ) : (
                    <TextareaAutosize
                        className="bw-textarea mb-3 min-h-[1.6rem] px-1"
                        maxRows={5}
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        placeholder="Describe the home — e.g. 3 BHK ~1200 sq ft, living opens to a balcony, kitchen beside dining, 2 baths…"
                    />
                )}

                <div className="flex items-center gap-2">
                    <button type="button" className="bw-icon !size-9 border border-[var(--bw-border-1)]" title="Attach a floor plan" onClick={() => fileRef.current?.click()}>
                        <Ico name="plus" size={18} />
                    </button>
                    <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />

                    <span className="bw-chip">
                        <span className="text-[var(--bw-green)]"><Ico name="flash" size={12} /></span>
                        {file ? "Floor-plan vision" : "Describe"}
                    </span>
                    <span className="bw-chip capitalize">{provider}</span>

                    <div className="ml-auto flex items-center gap-2">
                        {!vision && <span className="bw-chip max-sm:hidden"><span className="bw-dot bg-[var(--bw-orange)]" /> AI key needed</span>}
                        <button type="button" className="bw-icon !size-9" title="Voice (coming soon)"><Ico name="mic" size={17} /></button>
                        <button type="button" disabled={!canSend} onClick={send} className="bw-btn bw-btn-primary !w-10 !p-0" title="Generate 3D model">
                            {busy ? <Ico name="spinner" size={18} className="bw-spin" /> : <Ico name="arrow" size={18} />}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
