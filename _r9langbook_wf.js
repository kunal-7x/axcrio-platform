export const meta = {
  name: 'round9-lang-booking',
  description: 'READ-ONLY diagnosis of two regressions (dead-air + loop already fixed): (1) LANGUAGE-MIRROR broken - the AI must reply in whatever language the user speaks (English->English, Hindi->Hindi) and follow mid-call switches; this worked perfectly before and is now broken (likely the lean-prompt rewrite dropped the language rule, or the langdetect/language-hint path). (2) BOOKING-PAGE - a booked site-visit must reflect in the panel booking page (built+tested before, now not writing). Traces both to file:line + the fix. NO box mutation.',
  phases: [
    { title: 'Diagnose', detail: 'language-mirror regression + booking->panel integration (read-only)' },
    { title: 'Synthesize', detail: 'proven cause + fix for both' },
  ],
}
const BASE = "READ-ONLY (plan mode - mutate NOTHING). The dead-air + 'haan' loop are ALREADY FIXED + live (agent.py 11a865fe key-spread; prompt.py 4ae81ac6 lean). TWO REGRESSIONS to diagnose: (1) LANGUAGE-MIRROR: the AI must reply in the language the user speaks - English->English, Hindi->Hindi - and detect mid-call switches (e.g. user asks in Hindi then says 'yes tell me more' in English -> continue English). This worked PERFECTLY in the past, now BROKEN. (2) BOOKING-PAGE: when a site-visit is booked/scheduled in a call, it must appear in the panel's booking page (built + tested before, now not reflecting). Box (READ-ONLY): ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145, /opt/famit-agent/ (PowerShell ssh). Voice/TTS/.env LOCKED - brain = prompt.py + agent.py conversation logic; booking = agent.py booking tool + caller.py/panel integration.";

phase('Diagnose')
const d = await parallel([
  () => agent(BASE + " [LANGUAGE-MIRROR] Diagnose why the AI no longer mirrors the user's language. Read the LIVE prompt.py (4ae81ac6) - does it still contain a language-mirror rule ('reply in the language the user speaks; follow switches'), or did the lean rewrite DROP it? Then read agent.py: langdetect.py, the LanguageTracker / on_user_turn_completed language-hint injection, SARVAM_STT_LANG, the per-turn language note. Compare to the golden prompt 17ad3e0d (which had the working language rule per the plan's A1 work). Pin the regression: dropped prompt rule vs broken langdetect vs the STT language. Give the exact fix (re-add the language-mirror rule to the lean prompt and/or fix the hint path) file:line - keeping the prompt LEAN (don't re-bloat -> avoid the loop).", {label:'d:lang', phase:'Diagnose', model:'opus', effort:'high', agentType:'Explore'}),
  () => agent(BASE + " [BOOKING-PAGE] Trace the booking->panel integration end to end. In agent.py: find where a site-visit booking is captured (the booking tool/function) and whether it PERSISTS (HTTP POST to caller.py / a DB write / an event). In caller.py + the panel: find the booking page's data source (the endpoint/table it reads). Is the call-side booking actually being written, and does the panel read the same place? Where is the chain BROKEN (the write not firing, wrong endpoint, a flag off, the booking page reading a different source)? Give the exact break + fix, file:line.", {label:'d:book', phase:'Diagnose', model:'opus', effort:'high', agentType:'Explore'}),
])

phase('Synthesize')
const syn = await agent(BASE + " [SYNTHESIZE] From the two diagnoses below, give a TIGHT proven-cause + fix for each, for the plan: (A) LANGUAGE-MIRROR - the exact cause + the minimal lean fix (file:line); (B) BOOKING-PAGE - the exact broken link + the fix (file:line). Note earner-touch + risk for each, and that both are small/easily-implementable per the founder. Return the plan text.\n\n[LANG] " + String(d[0]||'').slice(0,4000) + "\n\n[BOOK] " + String(d[1]||'').slice(0,4000), {label:'syn:fix', phase:'Synthesize', model:'opus', effort:'high'})

return { diagnosed: d.filter(Boolean).length, plan: syn }
