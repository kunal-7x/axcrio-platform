// ============================================================
// lib/verticals.ts — multi-vertical / persona / language catalogue (panel side)
//
// The agent's `verticals/` package (haptica-mesh + famit-haptica) is the source of
// truth. This file mirrors its `catalogue()` output so the campaign form + the
// super-admin page can render the Field → Sub-option → Persona → Language pickers.
//
// getVerticals() prefers the LIVE catalogue (GET ${BASE}/verticals, overlay-merged on
// the box) and falls back to STATIC_VERTICALS on any error/404 — the same dormant-safe
// idiom as getVoiceConfig/getTiers. STATIC_VERTICALS is generated from the Python
// catalogue() (keep in sync if you add verticals in code rather than via the overlay).
// ============================================================

import { BASE, authHeaders } from "./api";

export type VerticalSubOption = { key: string; label: string; goal: string };
export type VerticalField = {
    key: string;
    label: string;
    tone: string;
    default_persona: string | null;
    default_languages: string[];
    sub_options: VerticalSubOption[];
};
export type VerticalPersona = {
    key: string;
    display: string;
    gender: string;
    tone: string;
    languages: string[];
    sarvam_voice: string | null;
};
export type VerticalLanguage = {
    code: string;
    name: string;
    native: string;
    el_speakable: boolean;
    sarvam_speakable: boolean;
    international?: boolean;
};
export type VerticalsCatalogue = {
    version: string;
    fields: VerticalField[];
    personas: VerticalPersona[];
    languages: VerticalLanguage[];
};

// --- static mirror (generated from verticals.composer.catalogue()) ------------
export const STATIC_VERTICALS: VerticalsCatalogue = {
    version: "1.0.0",
    fields: [
        { key: "medical", label: "Medical / Healthcare", tone: "calm, caring, reassuring", default_persona: "dr_meera", default_languages: ["hi", "en"], sub_options: [
            { key: "appointment_reminder", label: "Appointment reminder", goal: "upcoming appointment confirm या reschedule कराना" },
            { key: "lab_result_followup", label: "Lab result follow-up", goal: "report तैयार होने की सूचना दे कर consult/pickup करवाना" },
            { key: "teleconsult_followup", label: "Teleconsultation follow-up", goal: "पिछले consult के बाद हाल पूछ कर follow-up video/call book कराना" },
            { key: "medication_adherence", label: "Medication adherence", goal: "बताई गई दवा समय पर लेने की याद दिलाना + refill offer" },
            { key: "health_checkup_promo", label: "Preventive checkup promotion", goal: "preventive health package की जानकारी दे कर checkup book कराना" },
        ] },
        { key: "sales", label: "Sales", tone: "confident, warm, value-led", default_persona: "rohan_pro", default_languages: ["hi", "en"], sub_options: [
            { key: "cold_outreach", label: "Cold outreach", goal: "product/service में रुचि जगा कर अगला step (demo/meeting) तय करना" },
            { key: "lead_qualification", label: "Lead qualification", goal: "budget/need/timeline समझ कर lead को qualify करना" },
            { key: "demo_booking", label: "Demo / meeting booking", goal: "एक product demo या meeting slot book कराना" },
            { key: "upsell_crosssell", label: "Upsell / cross-sell", goal: "मौजूदा customer को relevant upgrade/add-on offer करना" },
            { key: "renewal", label: "Renewal / retention", goal: "expire हो रहे plan/subscription को renew कराना" },
            { key: "winback", label: "Win-back (lapsed customer)", goal: "छोड़ चुके customer को वापस लाना" },
        ] },
        { key: "education", label: "Education", tone: "encouraging, guiding, patient", default_persona: "neha_counsel", default_languages: ["hi", "en"], sub_options: [
            { key: "admission_promotion", label: "Admission / course promotion", goal: "course/program की जानकारी दे कर admission counselling book कराना" },
            { key: "counseling", label: "Career / admission counselling", goal: "student के लक्ष्य समझ कर सही course/path suggest करना + अगला step" },
            { key: "fee_reminder", label: "Fee reminder", goal: "pending fee की शालीन याद दिलाना + payment में मदद" },
            { key: "demo_class", label: "Free demo / trial class", goal: "एक free demo/trial class schedule कराना" },
            { key: "reengagement", label: "Re-engagement (dropped student)", goal: "बीच में छोड़ चुके student को वापस पढ़ाई से जोड़ना" },
        ] },
        { key: "finance", label: "Finance / Banking", tone: "trustworthy, clear, measured", default_persona: "arjun_advisor", default_languages: ["hi", "en"], sub_options: [
            { key: "emi_reminder", label: "EMI / payment reminder", goal: "आने वाली/pending EMI की शालीन याद दिलाना + payment path" },
            { key: "loan_offer", label: "Loan / credit offer", goal: "eligible loan/credit की जानकारी दे कर application आगे बढ़ाना" },
            { key: "kyc_update", label: "KYC / profile update", goal: "KYC/details update के लिए सही, सुरक्षित step बताना" },
            { key: "investment_advisory", label: "Investment / SIP", goal: "goal-based निवेश/SIP समझा कर एक review call तय करना" },
            { key: "card_sales", label: "Credit card / product sales", goal: "relevant card/product के फ़ायदे बता कर apply कराना" },
        ] },
        { key: "real_estate", label: "Real Estate", tone: "warm, aspirational, credible", default_persona: "aisha_warm", default_languages: ["hi", "en"], sub_options: [
            { key: "site_visit_booking", label: "Site visit / presentation booking", goal: "एक free site visit या online presentation book कराना" },
            { key: "project_promotion", label: "New project launch", goal: "नए project/inventory की जानकारी दे कर रुचि लेना" },
            { key: "resale_followup", label: "Resale / inventory follow-up", goal: "पहले दिखाई property/lead पर follow-up कर के decision आगे बढ़ाना" },
        ] },
        { key: "insurance", label: "Insurance", tone: "reassuring, honest, clear", default_persona: "priya_support", default_languages: ["hi", "en"], sub_options: [
            { key: "policy_renewal", label: "Policy renewal", goal: "expire हो रही policy समय पर renew कराना (कवर टूटने से बचाना)" },
            { key: "new_policy", label: "New policy / quote", goal: "ज़रूरत समझ कर सही cover suggest करना + एक advisor call तय करना" },
            { key: "claim_assist", label: "Claim assistance", goal: "claim process में मदद कर के अगला ज़रूरी step बताना" },
        ] },
        { key: "ecommerce", label: "E-commerce / Retail", tone: "friendly, quick, helpful", default_persona: "aisha_warm", default_languages: ["hi", "en"], sub_options: [
            { key: "abandoned_cart", label: "Abandoned cart recovery", goal: "अधूरे order को complete कराना" },
            { key: "order_confirmation", label: "Order / COD confirmation", goal: "order (ख़ासकर COD) confirm कराना" },
            { key: "delivery_followup", label: "Delivery / feedback follow-up", goal: "delivery का हाल पूछना + feedback/अगली खरीद" },
        ] },
        { key: "hospitality", label: "Hospitality / Travel", tone: "gracious, warm, attentive", default_persona: "aisha_warm", default_languages: ["hi", "en"], sub_options: [
            { key: "booking_confirmation", label: "Booking confirmation", goal: "reservation (hotel/table/ticket) confirm या adjust कराना" },
            { key: "offer_promotion", label: "Package / offer promotion", goal: "relevant package/offer बता कर booking कराना" },
            { key: "feedback", label: "Post-stay feedback", goal: "अनुभव पूछना + दोबारा आने/review का step" },
        ] },
        { key: "recruitment", label: "Recruitment / HR", tone: "professional, respectful, clear", default_persona: "priya_support", default_languages: ["hi", "en"], sub_options: [
            { key: "interview_scheduling", label: "Interview scheduling", goal: "candidate का interview slot तय/confirm करना" },
            { key: "candidate_screening", label: "Initial screening", goal: "basic fit (experience/notice/location/expectation) जाँचना" },
            { key: "offer_followup", label: "Offer follow-up", goal: "दिए गए offer पर decision और joining confirm करना" },
        ] },
        { key: "logistics", label: "Logistics / Delivery", tone: "efficient, polite, clear", default_persona: "rohan_pro", default_languages: ["hi", "en"], sub_options: [
            { key: "delivery_scheduling", label: "Delivery scheduling", goal: "delivery का सुविधाजनक समय/पता तय करना" },
            { key: "failed_delivery", label: "Failed delivery re-attempt", goal: "छूटी delivery का कारण समझ कर re-attempt तय करना" },
            { key: "pickup_request", label: "Pickup / return coordination", goal: "return/pickup का समय और पता तय करना" },
        ] },
        { key: "fitness", label: "Fitness / Wellness", tone: "energetic, motivating, positive", default_persona: "vikram_closer", default_languages: ["hi", "en"], sub_options: [
            { key: "trial_booking", label: "Free trial / session booking", goal: "एक free trial session/class book कराना" },
            { key: "membership_renewal", label: "Membership renewal", goal: "membership renew कराना" },
            { key: "reactivation", label: "Inactive member re-activation", goal: "छूट चुके member को वापस लाना" },
        ] },
        { key: "ngo", label: "NGO / Non-profit", tone: "warm, sincere, respectful", default_persona: "neha_counsel", default_languages: ["hi", "en"], sub_options: [
            { key: "donation_appeal", label: "Donation appeal", goal: "cause समझा कर एक contribution के लिए राज़ी करना" },
            { key: "volunteer_signup", label: "Volunteer sign-up", goal: "volunteer के तौर पर जोड़ना" },
            { key: "donor_followup", label: "Donor thank-you / follow-up", goal: "पुराने donor को धन्यवाद + असर बता कर दोबारा जोड़ना" },
        ] },
    ],
    personas: [
        { key: "aisha_warm", display: "Aisha", gender: "female", tone: "warm, friendly, unhurried", languages: ["hi", "en", "hinglish"], sarvam_voice: "anushka" },
        { key: "priya_support", display: "Priya", gender: "female", tone: "patient, supportive, calm", languages: ["hi", "en", "hinglish"], sarvam_voice: "manisha" },
        { key: "dr_meera", display: "Dr. Meera", gender: "female", tone: "calm, clinical, empathetic", languages: ["hi", "en", "hinglish"], sarvam_voice: "vidya" },
        { key: "neha_counsel", display: "Neha", gender: "female", tone: "encouraging, guiding, warm", languages: ["hi", "en", "hinglish"], sarvam_voice: "arya" },
        { key: "rohan_pro", display: "Rohan", gender: "male", tone: "professional, confident, crisp", languages: ["hi", "en", "hinglish"], sarvam_voice: "abhilash" },
        { key: "arjun_advisor", display: "Arjun", gender: "male", tone: "consultative, trustworthy, measured", languages: ["hi", "en", "hinglish"], sarvam_voice: "karun" },
        { key: "vikram_closer", display: "Vikram", gender: "male", tone: "energetic, persuasive, upbeat", languages: ["hi", "en", "hinglish"], sarvam_voice: "hitesh" },
        { key: "kabir_calm", display: "Kabir", gender: "male", tone: "respectful, calm, firm-but-polite", languages: ["hi", "en", "hinglish"], sarvam_voice: "abhilash" },
    ],
    languages: [
        { code: "hi", name: "Hindi", native: "हिन्दी", el_speakable: true, sarvam_speakable: true },
        { code: "en", name: "English", native: "English", el_speakable: true, sarvam_speakable: true },
        { code: "hinglish", name: "Hinglish", native: "Hinglish", el_speakable: true, sarvam_speakable: true },
        { code: "bn", name: "Bengali", native: "বাংলা", el_speakable: false, sarvam_speakable: true },
        { code: "ta", name: "Tamil", native: "தமிழ்", el_speakable: false, sarvam_speakable: true },
        { code: "te", name: "Telugu", native: "తెలుగు", el_speakable: false, sarvam_speakable: true },
        { code: "kn", name: "Kannada", native: "ಕನ್ನಡ", el_speakable: false, sarvam_speakable: true },
        { code: "ml", name: "Malayalam", native: "മലയാളം", el_speakable: false, sarvam_speakable: true },
        { code: "mr", name: "Marathi", native: "मराठी", el_speakable: false, sarvam_speakable: true },
        { code: "gu", name: "Gujarati", native: "ગુજરાતી", el_speakable: false, sarvam_speakable: true },
        { code: "pa", name: "Punjabi", native: "ਪੰਜਾਬੀ", el_speakable: false, sarvam_speakable: true },
        { code: "od", name: "Odia", native: "ଓଡ଼ିଆ", el_speakable: false, sarvam_speakable: true },
        { code: "es", name: "Spanish", native: "Español", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "fr", name: "French", native: "Français", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "de", name: "German", native: "Deutsch", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "it", name: "Italian", native: "Italiano", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "pt", name: "Portuguese", native: "Português", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "nl", name: "Dutch", native: "Nederlands", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "pl", name: "Polish", native: "Polski", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "tr", name: "Turkish", native: "Türkçe", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "ru", name: "Russian", native: "Русский", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "ar", name: "Arabic", native: "العربية", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "zh", name: "Chinese (Mandarin)", native: "中文", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "ja", name: "Japanese", native: "日本語", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "ko", name: "Korean", native: "한국어", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "id", name: "Indonesian", native: "Bahasa Indonesia", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "fil", name: "Filipino", native: "Filipino", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "uk", name: "Ukrainian", native: "Українська", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "vi", name: "Vietnamese", native: "Tiếng Việt", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "sv", name: "Swedish", native: "Svenska", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "ro", name: "Romanian", native: "Română", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "el", name: "Greek", native: "Ελληνικά", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "cs", name: "Czech", native: "Čeština", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "da", name: "Danish", native: "Dansk", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "fi", name: "Finnish", native: "Suomi", el_speakable: true, sarvam_speakable: false, international: true },
        { code: "ms", name: "Malay", native: "Bahasa Melayu", el_speakable: true, sarvam_speakable: false, international: true },
    ],
};

// --- API: prefer the live catalogue, fall back to the static mirror -----------
export async function getVerticals(): Promise<VerticalsCatalogue> {
    try {
        const res = await fetch(`${BASE}/verticals`, { headers: authHeaders() });
        if (!res.ok) return STATIC_VERTICALS;
        const data = (await res.json()) as Partial<VerticalsCatalogue> | null;
        if (data && Array.isArray(data.fields) && data.fields.length
            && Array.isArray(data.personas) && Array.isArray(data.languages)) {
            return {
                version: String(data.version ?? STATIC_VERTICALS.version),
                fields: data.fields as VerticalField[],
                personas: data.personas as VerticalPersona[],
                languages: data.languages as VerticalLanguage[],
            };
        }
        return STATIC_VERTICALS;
    } catch {
        return STATIC_VERTICALS;
    }
}

// --- super-admin overrides (no-deploy, VAR/verticals_overrides.json) ----------
// Mirrors the getTierConfig/saveTierConfig contract: GET returns {overrides, effective};
// POST deep-merges a partial on the box. Dormant-safe: if the backend route isn't wired
// yet, GET degrades to {overrides:{}, effective: <static/live catalogue>}.
export type VerticalsConfigView = { overrides: Record<string, unknown>; effective: VerticalsCatalogue };

export async function getVerticalsConfig(): Promise<VerticalsConfigView> {
    try {
        const res = await fetch(`${BASE}/admin/verticals-config`, { headers: authHeaders() });
        if (!res.ok) return { overrides: {}, effective: await getVerticals() };
        const data = (await res.json()) as { overrides?: Record<string, unknown>; effective?: VerticalsCatalogue } | null;
        const effective = data?.effective && Array.isArray(data.effective.fields) ? data.effective : await getVerticals();
        return { overrides: (data?.overrides && typeof data.overrides === "object" ? data.overrides : {}), effective };
    } catch {
        return { overrides: {}, effective: await getVerticals() };
    }
}

export async function saveVerticalsConfig(partial: Record<string, unknown>): Promise<VerticalsConfigView> {
    const res = await fetch(`${BASE}/admin/verticals-config`, {
        method: "POST",
        headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
        body: JSON.stringify(partial),
    });
    if (!res.ok) throw new Error(`Save failed (${res.status})`);
    const data = (await res.json()) as { overrides?: Record<string, unknown>; effective?: VerticalsCatalogue } | null;
    const effective = data?.effective && Array.isArray(data.effective.fields) ? data.effective : await getVerticals();
    return { overrides: (data?.overrides && typeof data.overrides === "object" ? data.overrides : partial), effective };
}

// --- pure helpers -------------------------------------------------------------
export function fieldByKey(cat: VerticalsCatalogue, key: string): VerticalField | undefined {
    return cat.fields.find((f) => f.key === key);
}
export function subOptionsFor(cat: VerticalsCatalogue, fieldKey: string): VerticalSubOption[] {
    return fieldByKey(cat, fieldKey)?.sub_options ?? [];
}
export function personaByKey(cat: VerticalsCatalogue, key: string): VerticalPersona | undefined {
    return cat.personas.find((p) => p.key === key);
}
export function languageByCode(cat: VerticalsCatalogue, code: string): VerticalLanguage | undefined {
    return cat.languages.find((l) => l.code === code);
}
