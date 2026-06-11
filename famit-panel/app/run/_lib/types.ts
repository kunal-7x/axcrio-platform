// Run-Campaign Audience Builder — local types + constants.
// Kept local to app/run per the orchestrator's "logic in app/run/_lib" rule.

import { type TabsOption } from "@/types/tabs";

// Temperature bands reuse the EXACT thresholds from app/leads/page.tsx:
//   hot  score >= 70
//   warm 40 <= score < 70
//   cold score < 40 OR unscored
export type Temp = "hot" | "warm" | "cold";

export const TEMP_DEFS: { key: Temp; label: string; hint: string }[] = [
    { key: "hot", label: "Hot", hint: "Score 70+" },
    { key: "warm", label: "Warm", hint: "Score 40–69" },
    { key: "cold", label: "Cold", hint: "Under 40 / unscored" },
];

// Source-mode tabs (composable layers, not exclusive screens — see spec §3).
export const SOURCE_TABS: TabsOption[] = [
    { id: 1, name: "All stored" },
    { id: 2, name: "By temperature" },
    { id: 3, name: "By upload" },
    { id: 4, name: "Pick manually" },
];

export const SOURCE_ID = {
    all: 1,
    temperature: 2,
    upload: 3,
    manual: 4,
} as const;
