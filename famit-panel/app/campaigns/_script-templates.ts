// P7.3 — Script Studio 2.0 starter TEMPLATES by vertical. Each is a seed set of typed blocks the
// operator loads into the builder and then edits. Pure frontend data (no ids — the builder assigns
// them on load). Content is intentionally neutral + editable; {{vars}} are author placeholders.

import type { ScriptBlock } from "./_block-builder";

export type TemplateBlock = Omit<ScriptBlock, "id">;
export type ScriptTemplate = { id: string; label: string; blurb: string; blocks: TemplateBlock[] };

const greet = (t: string): TemplateBlock => ({ type: "greeting", enabled: true, text: t });
const qual = (text: string, items: string[]): TemplateBlock => ({ type: "qualification", enabled: true, text, items });
const disc = (items: string[]): TemplateBlock => ({ type: "discovery", enabled: true, items });
const obj = (qa: { q: string; a: string }[]): TemplateBlock => ({ type: "objection", enabled: true, qa });
const faq = (qa: { q: string; a: string }[]): TemplateBlock => ({ type: "faq", enabled: true, qa });
const close = (goal: string, options: string[]): TemplateBlock => ({ type: "closing", enabled: true, goal, options });

export const SCRIPT_TEMPLATES: ScriptTemplate[] = [
    {
        id: "sales", label: "Sales", blurb: "Outbound product/offer pitch → book a demo or visit.",
        blocks: [
            greet("Warm, upbeat opener: introduce yourself + the company, and why you're calling in one friendly line."),
            qual("What's the most important thing you're looking for right now?", ["Is this for yourself or your team?", "What are you using today?"]),
            disc(["What's prompting you to look into this now?", "What would a great outcome look like for you?"]),
            obj([{ q: "It's too expensive", a: "Acknowledge the budget, reframe around value/ROI, and offer a flexible plan or a smaller starting option." }, { q: "I need to think about it", a: "Validate it, ask what specifically they want to weigh, and offer a no-pressure next step." }]),
            close("book a demo or a site visit", ["a quick online demo", "or an in-person visit"]),
        ],
    },
    {
        id: "support", label: "Customer Support", blurb: "Proactive check-in / issue resolution callback.",
        blocks: [
            greet("Calm, reassuring opener: confirm who you're speaking with and that you're calling to help with their recent request."),
            qual("Just to make sure I help with the right thing — what's the main issue you're facing?", ["When did it start?"]),
            disc(["Have you tried anything so far?", "How is this affecting you day to day?"]),
            faq([{ q: "How long will this take to resolve?", a: "Give an honest, specific timeframe and what happens next." }, { q: "Will I be charged?", a: "Clarify cost up front, warmly and plainly." }]),
            close("resolve the issue or schedule a follow-up", ["a fix on this call", "or a scheduled callback"]),
        ],
    },
    {
        id: "real-estate", label: "Real Estate", blurb: "Property interest → site visit booking.",
        blocks: [
            greet("Friendly opener: mention the project/property and that you're calling about their interest."),
            qual("What kind of home are you looking for?", ["Which area suits you best?", "Is this to live in or to invest?"]),
            disc(["What's your ideal possession timeline?", "What's most important — location, size, or budget?"]),
            obj([{ q: "Price is high", a: "Acknowledge, highlight value (location/amenities/appreciation), and offer payment-plan or a smaller config." }, { q: "Just browsing", a: "Keep it warm, offer a no-obligation site visit to see it in person." }]),
            close("book a site visit", ["a guided site visit", "or a video walkthrough"]),
        ],
    },
    {
        id: "healthcare", label: "Healthcare", blurb: "Appointment / care plan reminder + booking. (Be compliant.)",
        blocks: [
            greet("Warm, respectful opener: identify the clinic and that you're calling about their care/appointment."),
            qual("How have you been feeling since your last visit?", ["Are you due for a check-up or follow-up?"]),
            disc(["Any symptoms or concerns you'd like to mention to the doctor?", "What time of day works best for you?"]),
            faq([{ q: "Is this covered by insurance?", a: "Explain coverage simply and what to bring." }, { q: "Do I need to prepare anything?", a: "Give clear, gentle prep instructions." }]),
            close("book an appointment", ["an in-clinic visit", "or a teleconsult"]),
        ],
    },
    {
        id: "recruitment", label: "Recruitment", blurb: "Candidate outreach → screen + schedule interview.",
        blocks: [
            greet("Upbeat opener: introduce yourself + company and the role you're reaching out about."),
            qual("Are you open to exploring a new opportunity right now?", ["What are you doing currently?", "What would make a move worth it?"]),
            disc(["What are you looking for in your next role?", "What's your notice period / availability?"]),
            obj([{ q: "I'm happy where I am", a: "Respect it, plant the seed about what's different here, and ask to keep in touch." }, { q: "What's the salary?", a: "Give an honest range and tie it to the full package + growth." }]),
            close("schedule a screening interview", ["a short intro call", "or a video interview"]),
        ],
    },
    {
        id: "banking", label: "Banking", blurb: "Product offer (card/loan/account) → application/appointment.",
        blocks: [
            greet("Professional, trustworthy opener: identify the bank and the pre-approved/eligible offer."),
            qual("What do you currently use for this — and what would make it better?", ["Are you a current customer?"]),
            disc(["What matters most — rate, rewards, or convenience?", "What's your monthly usage like?"]),
            obj([{ q: "I already have one", a: "Acknowledge, then differentiate on rate/rewards/service and offer a quick comparison." }, { q: "Is there a hidden fee?", a: "Be fully transparent about fees up front — it builds trust." }]),
            close("complete the application or book a branch visit", ["apply on this call", "or a branch appointment"]),
        ],
    },
    {
        id: "insurance", label: "Insurance", blurb: "Policy interest / renewal → quote + advisor call.",
        blocks: [
            greet("Warm, consultative opener: identify the company and that you're calling about cover/renewal."),
            qual("What are you most looking to protect — health, family, or assets?", ["Do you have any cover today?"]),
            disc(["Who depends on you financially?", "What's your budget comfort per month?"]),
            obj([{ q: "I can't afford it", a: "Reframe around peace of mind and offer a right-sized plan within budget." }, { q: "I'll do it later", a: "Gently note that cover is cheaper and easier the earlier you start." }]),
            close("share a tailored quote / book an advisor call", ["a quick quote on this call", "or a call with an advisor"]),
        ],
    },
    {
        id: "education", label: "Education", blurb: "Course/admission interest → counselling session.",
        blocks: [
            greet("Encouraging opener: introduce the institute and the program they showed interest in."),
            qual("What's your goal with this course?", ["Are you a student, working, or a parent enquiring?"]),
            disc(["What's your current background?", "When are you looking to start?"]),
            obj([{ q: "It's costly", a: "Acknowledge, highlight outcomes/placements, and mention EMI or scholarship options." }, { q: "Will this help my career?", a: "Give concrete outcomes — skills, certification, placement support." }]),
            close("book a counselling session", ["a counselling call", "or a campus visit"]),
        ],
    },
];
