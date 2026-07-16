"use client";
// Publish toggle + copyable customer link for the active model. The link points at
// the public /share/property/[token] page the voice agent can text mid-call.
import { useEffect, useState } from "react";
import Button from "@/components/Button";
import { setShare, type ProjectSummary } from "@/lib/pmodel";

export default function ShareBar({
    project,
    onChange,
}: {
    project: ProjectSummary;
    onChange?: (p: Partial<ProjectSummary>) => void;
}) {
    const [isPublic, setIsPublic] = useState(project.public);
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);

    useEffect(() => setIsPublic(project.public), [project.id, project.public]);

    const link =
        typeof window !== "undefined"
            ? `${window.location.origin}/share/property/${project.share_token}`
            : `/share/property/${project.share_token}`;

    async function toggle() {
        setBusy(true);
        try {
            const r = await setShare(project.id, !isPublic);
            setIsPublic(r.public);
            onChange?.({ public: r.public });
        } catch {
            /* keep calm */
        } finally {
            setBusy(false);
        }
    }

    async function copy() {
        try {
            await navigator.clipboard.writeText(link);
            setCopied(true);
            setTimeout(() => setCopied(false), 1600);
        } catch {
            /* ignore */
        }
    }

    return (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-s-subtle bg-b-surface2 px-4 py-3">
            <div className="flex items-center gap-2">
                <span className={`size-2 rounded-full ${isPublic ? "bg-[#00A656]" : "bg-s-stroke2"}`} />
                <span className="text-body-2 font-semibold">
                    {isPublic ? "Shared with customers" : "Private"}
                </span>
            </div>
            <Button isStroke onClick={toggle} disabled={busy} className="ml-auto">
                {isPublic ? "Make private" : "Publish link"}
            </Button>
            {isPublic && (
                <>
                    <input
                        readOnly
                        value={link}
                        onFocus={(e) => e.currentTarget.select()}
                        className="input-base min-w-0 flex-1 text-caption"
                    />
                    <Button isBlack onClick={copy}>
                        {copied ? "Copied!" : "Copy link"}
                    </Button>
                    <Button as="a" href={link} target="_blank" isGray>
                        Open
                    </Button>
                </>
            )}
        </div>
    );
}
