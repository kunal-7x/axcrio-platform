# UNIT W2b — WhatsApp Campaign Builder (11-step workspace)

Spec: design/wa-builder-frontend.md + design/wa-creative-integration.md
Rule: PORT reference components, Inter Display, single Layout title, zero raw hex, dormant-safe.

## Files
- app/whatsapp/page.tsx                         — shell: Layout + horizontal Tabs step rail + step router  [DONE]
- app/whatsapp/_lib/types.ts                    — local types (Step, AssetRef, TemplateDraft, CampaignCtx) [DONE]
- app/whatsapp/_lib/waapi.ts                    — dormant-safe creative.* + wa-template-gen bindings        [DONE]
- app/whatsapp/_lib/audience.ts                 — re-export run-campaign audience logic                     [DONE]
- app/whatsapp/_components/ComingSoon.tsx       — premium not_configured card (404/503)                     [DONE]
- app/whatsapp/_components/PhonePreview.tsx     — pinned WhatsApp phone mock (restyled bubble)              [DONE]
- app/whatsapp/_components/AiSuggestionCard.tsx — compose card (Card+Badge+Button)                          [DONE]
- app/whatsapp/_components/NoInventNote.tsx     — master §20 guardrail note                                 [DONE]
- app/whatsapp/_steps/*.tsx                      — 11 step bodies                                            [DONE]

## LIVE vs DORMANT
- LIVE today: ⑨ Schedule(send-now) + ⑩ Delivery + message log  -> /api/whatsapp/{send,log}
- LIVE: ② Campaign list (/api/campaigns), ⑧ Audience (/api/leads,batches,suppression), ⑥ Preview (client-side)
- DORMANT-SAFE (coming-soon card on 404/503): ③ AI Templates, ④ Creative, ⑤ Banner Studio, ⑦ asset-approve, ⑪ Analytics
  -> /api/whatsapp/templates/generate, /api/assets/* (creative.*)

## Verify
- npm run build NOT run here (deploy agent builds). Typecheck via tsc if needed.
- DONE: `npx tsc --noEmit` → ZERO errors in app/whatsapp (only pre-existing
  components/GenerationLoader/field.ts:113-114 errors remain — NOT my file,
  parallel Creative Studio unit, outside scope/do-not-edit components/).
- DONE: ZERO raw hex in app/whatsapp (grep clean). Token-pure.
- Components/ untouched. No npm build run. Run-campaign audience reused via re-export.
