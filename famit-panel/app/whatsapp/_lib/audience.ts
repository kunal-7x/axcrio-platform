// WhatsApp Campaign Builder — ⑧ Audience.
// REUSE the Run-Campaign audience builder verbatim (spec §2 ⑧: "Reuse the
// run-campaign audience filters for Audience"). Same temperature bands, same
// composable filters, same truthful client-side preview count. No re-derivation.

export {
    tempOf,
    inBand,
    applyTempFilter,
    applyQuery,
    resolveAudience,
    breakdownOf,
    dedupeById,
    type AudienceFilter,
    type Breakdown,
} from "@/app/run/_lib/audience";

export {
    TEMP_DEFS,
    type Temp,
} from "@/app/run/_lib/types";
