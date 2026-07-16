"""Idempotent in-place patch for famit-panel/lib/api.ts ON THE BOX (which has diverged from local).
Adds ONLY the needed additive changes — never ships local wholesale (would clobber box-only code).
Two independent, idempotent blocks:
  1) generateCampaignScript() gains optional `opts` + a new getScriptStudioMeta() + ScriptStudioMeta type.
  2) a VoiceCost type + `cost?: VoiceCost` on VoiceCallBundle (for the call-detail cost breakdown).
Usage: python _patch_api_studio_meta.py [path]"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/opt/haptica/famit-panel/lib/api.ts"
s = open(PATH).read()
orig = s
changed = []

# ── block 1: Script Studio 2.0 (opts + getScriptStudioMeta) ──────────────────────────────────
if "getScriptStudioMeta" not in s:
    sig_old = ("    cid: string,\n    brief?: string\n"
               "): Promise<{ ok: boolean; script?: string; model_label?: string; error?: string; message?: string }> {")
    sig_new = ("    cid: string,\n    brief?: string,\n    opts?: Record<string, unknown>\n"
               "): Promise<{ ok: boolean; script?: string; model_label?: string; error?: string; message?: string }> {")
    body_old = '            body: JSON.stringify({ brief: brief || "" }),'
    body_new = ('            body: JSON.stringify({\n'
                '                brief: brief || "",\n'
                '                ...(opts && Object.keys(opts).length ? { opts } : {}),\n'
                '            }),')
    if sig_old in s and body_old in s:
        s = s.replace(sig_old, sig_new, 1).replace(body_old, body_new, 1)
        s += '''

// Script Studio 2.0 option catalogue (categories/goals/lead-warmth/dials) — drives the builder UI.
export type ScriptStudioMeta = {
    categories: { id: string; label: string; when?: string; framework?: string }[];
    goals: { id: string; label: string }[];
    lead_warmth: { id: string; label: string }[];
    tones: string[];
    lengths: string[];
    push: string[];
    model_label?: string;
};
const _EMPTY_STUDIO_META: ScriptStudioMeta = {
    categories: [], goals: [], lead_warmth: [], tones: [], lengths: [], push: [],
};
export async function getScriptStudioMeta(): Promise<ScriptStudioMeta> {
    try {
        const res = await fetch(`${BASE}/script/studio-meta`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return _EMPTY_STUDIO_META;
        return (await res.json().catch(() => _EMPTY_STUDIO_META)) as ScriptStudioMeta;
    } catch {
        return _EMPTY_STUDIO_META;
    }
}
'''
        changed.append("studio-meta")
    else:
        print("WARN: generateCampaignScript shape not found — skipping studio-meta block")

# ── block 2: VoiceCost type + cost on VoiceCallBundle (call-detail cost breakdown) ────────────
if "VoiceCost" not in s:
    bundle_old = "export type VoiceCallBundle = { detail?: ObsRow; timeline?: ObsRow[]; latency?: ObsRow; error?: string };"
    bundle_new = ("export type VoiceCost = {\n"
                  "    telephony: number; stt: number; llm: number; tts: number; total: number; per_min: number;\n"
                  "    duration_min: number; currency?: string; rate_keys?: Record<string, string>;\n"
                  "};\n"
                  "export type VoiceCallBundle = { detail?: ObsRow; timeline?: ObsRow[]; latency?: ObsRow; cost?: VoiceCost; error?: string };")
    if bundle_old in s:
        s = s.replace(bundle_old, bundle_new, 1)
        changed.append("VoiceCost")
    else:
        print("WARN: VoiceCallBundle anchor not found — skipping VoiceCost block")

# ── block 3: Tier optional fields (available / recommended / unavailable_reason) ─────────────
tier_anchor = "    blurb: string;\n    est_inr_per_min: number;\n    stt: TierRole;"
if tier_anchor in s and "    available?: boolean;\n    recommended?: boolean;" not in s:
    s = s.replace(
        tier_anchor,
        ("    blurb: string;\n    est_inr_per_min: number;\n"
         "    available?: boolean;\n    recommended?: boolean;\n    unavailable_reason?: string;\n"
         "    stt: TierRole;"),
        1)
    changed.append("Tier-fields")

# ── block 4: getOverviewGeo (#26) — RUNTIME-CRITICAL named export the overview page imports ──
if "getOverviewGeo" not in s:
    anchor = "export const getFleetVendors = getAdminVendors;"
    if anchor in s:
        s = s.replace(anchor, anchor + '''

// #26 Control-Overview globe: recent call activity aggregated by Indian city.
export type GeoPoint = { city: string; lat: number; lng: number; calls: number; weight: number };
export type OverviewGeo = {
    points: GeoPoint[];
    hub: { lat: number; lng: number; label: string };
    total_calls: number; mapped_calls: number; cities: number; live: number; generated_at?: string;
};
export async function getOverviewGeo(): Promise<OverviewGeo> {
    const empty: OverviewGeo = { points: [], hub: { lat: 22.59, lng: 78.96, label: "India" }, total_calls: 0, mapped_calls: 0, cities: 0, live: 0 };
    try {
        const res = await fetch(`${BASE}/admin/overview/geo`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return empty;
        return (await res.json().catch(() => empty)) as OverviewGeo;
    } catch {
        return empty;
    }
}''', 1)
        changed.append("getOverviewGeo")
    else:
        print("WARN: getFleetVendors anchor not found — skipping getOverviewGeo block (overview globe needs it!)")

# ── block 5: NavConfig stage/unavailable (#25) — type-only (build ignores TS); runtime reads work regardless ──
nav_anchor = "    custom?: NavCustomItem[]; // admin-created links / sections"
if nav_anchor in s and "stage?: Record<string, \"beta\" | \"premium\">" not in s:
    s = s.replace(nav_anchor, nav_anchor + (
        '\n    stage?: Record<string, "beta" | "premium">; // #25 nav key -> maturity pill'
        '\n    unavailable?: string[]; // #25 nav keys hidden from the end user'), 1)
    changed.append("NavConfig-gating")

# ── block 6: VoiceCallCampaign + campaign on VoiceCallBundle (#22) ──
if "VoiceCallCampaign" not in s:
    # the cost block (block 2) already added `cost?: VoiceCost;` to the bundle on a prior run.
    for bundle_old in (
        "export type VoiceCallBundle = { detail?: ObsRow; timeline?: ObsRow[]; latency?: ObsRow; cost?: VoiceCost; error?: string };",
        "export type VoiceCallBundle = { detail?: ObsRow; timeline?: ObsRow[]; latency?: ObsRow; error?: string };",
    ):
        if bundle_old in s:
            ins = ('export type VoiceCallCampaign = { id: string; name?: string; category?: string; category_label?: string };\n'
                   + bundle_old.replace("error?: string };", "campaign?: VoiceCallCampaign; error?: string };"))
            s = s.replace(bundle_old, ins, 1)
            changed.append("VoiceCallCampaign")
            break

# ── block 7: Campaign.category (#22 / image-#12) — type-only. Guard on our OWN inserted marker so a
# repeat run is a no-op even if local/box already carries category fields with a different comment. ──
camp_anchor = "    status: string;\n    created_at: string;"
if camp_anchor in s and "#22 campaign script category" not in s and "category?: string;" not in s:
    s = s.replace(camp_anchor, camp_anchor + (
        "\n    category?: string; // #22 campaign script category"
        "\n    category_label?: string; // #22 human label"), 1)
    changed.append("Campaign-category")

if s != orig:
    open(PATH, "w").write(s)
    print("patched lib/api.ts: " + (", ".join(changed) or "none"))
else:
    print("api.ts already fully patched — no-op")
