// ============================================================================
// Curated ElevenLabs voice catalogue — FRONTEND-ONLY fallback + enrichment.
//
// Why this exists: the backend /voices route reads the live ElevenLabs catalogue
// behind an env key. When that key is absent (or the call fails) it honestly
// returns an EMPTY list — which is why the Voice card used to read "0 voices".
// Rather than show an empty wall, the Run page falls back to THIS hand-picked
// set so a vendor can always browse, preview and pick a premium voice.
//
// Everything here is PUBLIC, FREE and zero-burn:
//   • voice_id   — the real ElevenLabs premade voice id (works the moment a key
//                  is connected; these ids exist in every account by default)
//   • preview_url — the voice's PUBLIC sample MP3 on Google Cloud Storage. No
//                  key, no synthesis. The gallery plays it directly (buffered to
//                  audio/mpeg client-side so Safari accepts it too).
//
// This file touches NO backend and NO voice-agent core. It is presentation +
// a static data table. When the backend returns a non-empty live list, that
// list wins; this catalogue only fills the gap and enriches matching ids with a
// persona so even live voices get a friendly "Best for…" line.
// ============================================================================

import { type Voice } from "@/lib/api";

export type CuratedVoice = Voice & {
    age?: string;
    // short "Best for …" framing shown under the name
    persona: string;
    // one-line personality / texture
    blurb: string;
    // 1–2 quick descriptors rendered as chips
    tags: string[];
    // surfaced with a small star — our picks for outbound conversations
    recommended?: boolean;
};

const GCS = "https://storage.googleapis.com/eleven-public-prod/premade/voices";

// A premium, conversational-first selection. We deliberately skip the
// "war veteran / witch / video-game" character voices — these are the warm,
// credible, human-on-a-call voices that suit outbound sales & support.
export const CURATED_VOICES: CuratedVoice[] = [
    {
        voice_id: "pNInz6obpgDQGcFmaJgB",
        name: "Adam",
        accent: "American",
        gender: "male",
        age: "Adult",
        persona: "Confident & grounded",
        blurb: "Deep, assured delivery that lands a pitch without pushing.",
        tags: ["Deep", "Persuasive"],
        recommended: true,
        preview_url: `${GCS}/pNInz6obpgDQGcFmaJgB/38a69695-2ca9-4b9e-b9ec-f07ced494a58.mp3`,
    },
    {
        voice_id: "21m00Tcm4TlvDq8ikWAM",
        name: "Rachel",
        accent: "American",
        gender: "female",
        age: "Young",
        persona: "Warm & professional",
        blurb: "Calm, polished and easy to trust on a first call.",
        tags: ["Warm", "Calm"],
        recommended: true,
        preview_url: `${GCS}/21m00Tcm4TlvDq8ikWAM/df6788f9-5c96-470d-8312-aab3b3d8f50a.mp3`,
    },
    {
        voice_id: "XrExE9yKIg1WjnnlVkGX",
        name: "Matilda",
        accent: "American",
        gender: "female",
        age: "Young",
        persona: "Warm & welcoming",
        blurb: "Friendly and bright — opens doors and keeps people listening.",
        tags: ["Friendly", "Bright"],
        recommended: true,
        preview_url: `${GCS}/XrExE9yKIg1WjnnlVkGX/b930e18d-6b4d-466e-bab2-0ae97c6d8535.mp3`,
    },
    {
        voice_id: "ErXwobaYiN019PkySvjV",
        name: "Antoni",
        accent: "American",
        gender: "male",
        age: "Young",
        persona: "Friendly & natural",
        blurb: "Well-rounded, conversational — sounds like a real teammate.",
        tags: ["Natural", "Versatile"],
        preview_url: `${GCS}/ErXwobaYiN019PkySvjV/ee9ac367-91ee-4a56-818a-2bd1a9dbe83a.mp3`,
    },
    {
        voice_id: "onwK4e9ZLuTAKqWW03F9",
        name: "Daniel",
        accent: "British",
        gender: "male",
        age: "Adult",
        persona: "Authoritative & polished",
        blurb: "News-presenter poise — credible for premium offers.",
        tags: ["Polished", "Credible"],
        preview_url: `${GCS}/onwK4e9ZLuTAKqWW03F9/7eee0236-1a72-4b86-b303-5dcadc007ba9.mp3`,
    },
    {
        voice_id: "EXAVITQu4vr4xnSDxMaL",
        name: "Bella",
        accent: "American",
        gender: "female",
        age: "Young",
        persona: "Soft & reassuring",
        blurb: "Gentle and unhurried — great for sensitive conversations.",
        tags: ["Soft", "Gentle"],
        preview_url: `${GCS}/EXAVITQu4vr4xnSDxMaL/941b779e-c2ad-48d4-bddb-28d1a68fa27e.mp3`,
    },
    {
        voice_id: "TxGEqnHWrfWFTfGW9XjX",
        name: "Josh",
        accent: "American",
        gender: "male",
        age: "Young",
        persona: "Deep & persuasive",
        blurb: "Rich low register that reads as capable and calm.",
        tags: ["Deep", "Calm"],
        preview_url: `${GCS}/TxGEqnHWrfWFTfGW9XjX/3ae2fc71-d5f9-4769-bb71-2a43633cd186.mp3`,
    },
    {
        voice_id: "IKne3meq5aSn9XLyUdCD",
        name: "Charlie",
        accent: "Australian",
        gender: "male",
        age: "Adult",
        persona: "Casual & approachable",
        blurb: "Relaxed conversational tone that lowers the guard.",
        tags: ["Casual", "Relaxed"],
        preview_url: `${GCS}/IKne3meq5aSn9XLyUdCD/102de6f2-22ed-43e0-a1f1-111fa75c5481.mp3`,
    },
    {
        voice_id: "pMsXgVXv3BLzUgSXRplE",
        name: "Serena",
        accent: "American",
        gender: "female",
        age: "Adult",
        persona: "Pleasant & helpful",
        blurb: "Even, interactive delivery built for back-and-forth.",
        tags: ["Pleasant", "Clear"],
        preview_url: `${GCS}/pMsXgVXv3BLzUgSXRplE/d61f18ed-e5b0-4d0b-a33c-5c6e7e33b053.mp3`,
    },
    {
        voice_id: "TX3LPaxmHKxFdv7VOQHJ",
        name: "Liam",
        accent: "American",
        gender: "male",
        age: "Young",
        persona: "Clear & articulate",
        blurb: "Neutral, crisp diction — every word stays intelligible.",
        tags: ["Crisp", "Neutral"],
        preview_url: `${GCS}/TX3LPaxmHKxFdv7VOQHJ/63148076-6363-42db-aea8-31424308b92c.mp3`,
    },
    {
        voice_id: "oWAxZDx7w5VEj9dCyTzz",
        name: "Grace",
        accent: "American · Southern",
        gender: "female",
        age: "Young",
        persona: "Gentle & caring",
        blurb: "Soft Southern lilt — disarming and easy to like.",
        tags: ["Gentle", "Caring"],
        preview_url: `${GCS}/oWAxZDx7w5VEj9dCyTzz/84a36d1c-e182-41a8-8c55-dbdd15cd6e72.mp3`,
    },
    {
        voice_id: "Yko7PKHZNXotIFUBG7I9",
        name: "Matthew",
        accent: "British",
        gender: "male",
        age: "Adult",
        persona: "Calm & trustworthy",
        blurb: "Measured British delivery that never feels rushed.",
        tags: ["Calm", "Measured"],
        preview_url: `${GCS}/Yko7PKHZNXotIFUBG7I9/02c66c93-a237-436f-8a7d-43e8c49bc6a3.mp3`,
    },
    {
        voice_id: "ZQe5CZNOzWyzPSCn5a3c",
        name: "James",
        accent: "Australian",
        gender: "male",
        age: "Adult",
        persona: "Steady & credible",
        blurb: "Newsroom-calm pace that signals competence.",
        tags: ["Steady", "Credible"],
        preview_url: `${GCS}/ZQe5CZNOzWyzPSCn5a3c/35734112-7b72-48df-bc2f-64d5ab2f791b.mp3`,
    },
    {
        voice_id: "ThT5KcBeYPX3keUQqHPh",
        name: "Dorothy",
        accent: "British",
        gender: "female",
        age: "Young",
        persona: "Bright & pleasant",
        blurb: "Light, friendly and clear — keeps energy up on a call.",
        tags: ["Bright", "Friendly"],
        preview_url: `${GCS}/ThT5KcBeYPX3keUQqHPh/981f0855-6598-48d2-9f8f-b6d92fbbe3fc.mp3`,
    },
    {
        voice_id: "VR6AewLTigWG4xSOukaG",
        name: "Arnold",
        accent: "American",
        gender: "male",
        age: "Adult",
        persona: "Crisp & energetic",
        blurb: "Punchy and articulate — good for upbeat, fast offers.",
        tags: ["Energetic", "Crisp"],
        preview_url: `${GCS}/VR6AewLTigWG4xSOukaG/316050b7-c4e0-48de-acf9-a882bb7fc43b.mp3`,
    },
    {
        voice_id: "LcfcDJNUP1GQjkzn1xUU",
        name: "Emily",
        accent: "American",
        gender: "female",
        age: "Young",
        persona: "Calm & soothing",
        blurb: "Quiet confidence — reassuring for careful conversations.",
        tags: ["Calm", "Soothing"],
        preview_url: `${GCS}/LcfcDJNUP1GQjkzn1xUU/e4b994b7-9713-4238-84f3-add8fccaaccd.mp3`,
    },
];

// Best-fit OUTBOUND use-case per voice — a "recommended for" label (not a hard
// rule), shown on the poster card. Defaults to "Conversational" for anything
// unmapped (e.g. a live/cloned voice).
const USE_CASE: Record<string, string> = {
    pNInz6obpgDQGcFmaJgB: "Sales", // Adam
    "21m00Tcm4TlvDq8ikWAM": "Support", // Rachel
    XrExE9yKIg1WjnnlVkGX: "Reception", // Matilda
    ErXwobaYiN019PkySvjV: "Sales", // Antoni
    onwK4e9ZLuTAKqWW03F9: "Sales", // Daniel
    EXAVITQu4vr4xnSDxMaL: "Support", // Bella
    TxGEqnHWrfWFTfGW9XjX: "Sales", // Josh
    IKne3meq5aSn9XLyUdCD: "Surveys", // Charlie
    pMsXgVXv3BLzUgSXRplE: "Support", // Serena
    TX3LPaxmHKxFdv7VOQHJ: "Reminders", // Liam
    oWAxZDx7w5VEj9dCyTzz: "Support", // Grace
    Yko7PKHZNXotIFUBG7I9: "Collections", // Matthew
    ZQe5CZNOzWyzPSCn5a3c: "Sales", // James
    ThT5KcBeYPX3keUQqHPh: "Reception", // Dorothy
    VR6AewLTigWG4xSOukaG: "Sales", // Arnold
    LcfcDJNUP1GQjkzn1xUU: "Reminders", // Emily
};

// Persona/blurb/tags/useCase/tone keyed by voice_id, so a LIVE voice returned by
// the backend that happens to be one of these premade ids still gets the framing.
export const VOICE_META: Record<
    string,
    {
        persona: string;
        blurb: string;
        tags: string[];
        recommended?: boolean;
        age?: string;
        useCase: string;
        tone: string;
    }
> = Object.fromEntries(
    CURATED_VOICES.map((v) => [
        v.voice_id,
        {
            persona: v.persona,
            blurb: v.blurb,
            tags: v.tags,
            recommended: v.recommended,
            age: v.age,
            useCase: USE_CASE[v.voice_id] || "Conversational",
            // the single mood word under the card (first tag, lower-cased)
            tone: (v.tags[0] || "natural").toLowerCase(),
        },
    ])
);

// ── flag emojis for a voice: 🇮🇳 (every voice speaks Hindi on the multilingual
// engine) + the voice's native-accent flag. ───────────────────────────────────
const ACCENT_FLAG: Record<string, string> = {
    american: "🇺🇸",
    british: "🇬🇧",
    english: "🇬🇧",
    australian: "🇦🇺",
    irish: "🇮🇪",
    indian: "🇮🇳",
    canadian: "🇨🇦",
    swedish: "🇸🇪",
    italian: "🇮🇹",
    southern: "🇺🇸",
    essex: "🇬🇧",
    transatlantic: "🌐",
};

export function accentFlags(accent?: string): string {
    const tokens = (accent || "")
        .toLowerCase()
        .split(/[-·\s]+/)
        .filter(Boolean);
    const native = tokens.map((t) => ACCENT_FLAG[t]).find(Boolean) || "🌐";
    return native === "🇮🇳" ? "🇮🇳" : `🇮🇳 ${native}`;
}

// ── per-voice aurora palette (deterministic). RAW HEX is intentional here: this
// is GRADIENT ARTWORK on the poster card, a vibrant jewel-tone family that the
// neutral UI tokens deliberately don't cover. The cards are dark-on-both-themes
// by design (like the Figma), so they read identically in light + dark. ────────
// Each palette: a DEEP base, two mid hues (a,b) and one BRIGHT hot core (c).
// The high base↔core contrast is what makes the mesh read rich + fluid (not a
// flat wash). c is the glowing plume.
export type Aurora = { base: string; a: string; b: string; c: string };
const AURORAS: Aurora[] = [
    { base: "#160427", a: "#6d28d9", b: "#a21caf", c: "#ec4899" }, // violet → fuchsia → hot pink (the Figma)
    { base: "#040f1f", a: "#1d4ed8", b: "#0891b2", c: "#22d3ee" }, // royal blue → cyan
    { base: "#03160f", a: "#047857", b: "#0d9488", c: "#34d399" }, // emerald → mint
    { base: "#1f0510", a: "#9f1239", b: "#c026d3", c: "#fb7185" }, // crimson → rose
    { base: "#0a0524", a: "#4338ca", b: "#7c3aed", c: "#818cf8" }, // indigo → periwinkle
    { base: "#200617", a: "#9d174d", b: "#7e22ce", c: "#f472b6" }, // magenta → orchid
    { base: "#1a0a04", a: "#c2410c", b: "#db2777", c: "#fb923c" }, // ember → amber
];

export function auroraPalette(voiceId: string): Aurora {
    let h = 0;
    for (let i = 0; i < voiceId.length; i++) h = (h * 31 + voiceId.charCodeAt(i)) >>> 0;
    return AURORAS[h % AURORAS.length];
}

// ── card gradient ART (real fluid-gradient images in /public/voice-gradients).
// There are exactly 16 images and 16 curated voices → a clean 1:1 mapping in
// catalogue order; any other (live/cloned) voice gets a deterministic pick. ────
const GRADIENT_COUNT = 16;
const GRADIENT_BY_ID: Record<string, string> = Object.fromEntries(
    CURATED_VOICES.map((v, i) => [v.voice_id, `/voice-gradients/g${i + 1}.jpg`])
);

export function gradientImage(voiceId: string): string {
    const mapped = GRADIENT_BY_ID[voiceId];
    if (mapped) return mapped;
    let h = 0;
    for (let i = 0; i < voiceId.length; i++) h = (h * 31 + voiceId.charCodeAt(i)) >>> 0;
    return `/voice-gradients/g${(h % GRADIENT_COUNT) + 1}.jpg`;
}

// a dark fallback colour shown behind the image while it loads
export function cardBase(voiceId: string): string {
    return auroraPalette(voiceId).base;
}

// Tidy a raw accent/label ("american-southern", "british-essex") into a chip.
export function prettyAccent(raw?: string): string {
    if (!raw) return "";
    return raw
        .split(/[-·]/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
        .join(" · ");
}

// Deterministic avatar tint per voice (token-based, dark-safe). The COLOUR
// lives in the translucent background (warm brand palette → one family, never a
// rainbow); the initials always use text-t-primary so they stay high-contrast
// in BOTH themes (the background alone can't guarantee ≥4.5:1, the foreground
// must). Per-theme alphas keep the wash visible on light AND dark surfaces.
const AVATAR_TINTS = [
    "bg-primary-01/15 text-t-primary dark:bg-primary-01/25",
    "bg-primary-02/25 text-t-primary dark:bg-primary-02/28",
    "bg-primary-05/55 text-t-primary dark:bg-primary-05/20",
    "bg-[#00A656]/14 text-t-primary dark:bg-[#00A656]/22", // semantic success accent (allowed)
    "bg-primary-04/22 text-t-primary dark:bg-primary-04/30",
];

export function avatarTint(voiceId: string): string {
    let h = 0;
    for (let i = 0; i < voiceId.length; i++) h = (h * 31 + voiceId.charCodeAt(i)) >>> 0;
    return AVATAR_TINTS[h % AVATAR_TINTS.length];
}

export function voiceInitials(name?: string): string {
    if (!name) return "·";
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "·";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
