# BRAIN — Creative Studio ▸ Platform Integrations (master §32–34)

Durable facts + learnings. Append, never delete. Design doc: `design/creative-studio-integrations.md`
(written 2026-06-11, READ-ONLY design wave). Parent spec: `CREATIVE_STUDIO_MASTER_PROMPT.md`.

## THE MODEL (the whole integration in two surfaces)
- Every plane (WhatsApp/Adbot/AI-Manager/Workflows/Campaigns/Funnels/Landing) talks to the dedicated
  **AI Asset Service** through EXACTLY TWO surfaces: (1) a unified **`creative.*` tool/HTTP contract**
  (generate/edit/regenerate/approve/reject/search/get + send_to_whatsapp/send_to_adbot), and (2) the
  **Asset Library** as the canonical tenant-scoped cross-platform store. NEVER a second money-path or
  second tool surface per plane. This is the §32-34 discipline.
- `creative.*` exists in BOTH forms hitting the SAME service/gates: as workforce **`ToolSpec`s** (for
  AI-Manager + Workflow Action nodes — risk/permission/wallet gates already built apply unchanged) AND as
  **HTTP routes** `APIRouter(prefix="/creative")` (UI/ads/WhatsApp). One risk table, one wallet, one audit
  channel=`creative`, one RLS boundary.
- Every generating call: async (Hatchet F3 `job_id`) + credit-gated (`wallet.reserve(tenant_id,
  amount_minor:int, resource_type, resource_id, idem_key)->hold_id|None` then settle/release, INR PAISE,
  idempotent, tag `hold_backend`) + audited. Reuses F3/F4 verbatim.

## THE ALREADY-BUILT SEAMS THIS WIRES (don't re-derive — they exist as dormant/parked)
- **AI Manager** already has: a `creative` workforce ROLE, an `adapters/creative.py` ModuleAdapter
  (aim-architecture.md §3.1), a `creative_pack` Hatchet worker workflow, and `target_module='creative'` in
  its action schema. THESE are the "parked creative adapters" — they call the new service over the
  authenticated localhost loopback (monolith_client pattern, scoped tenant token, NOT body-vendor). Pass
  the AIM `idem_key` DOWN to creative.generate so the wallet hold is single-charged (F4 ON CONFLICT).
- **Ads-engine** (creative-ads-engine.md) consumes a list of approved `AssetRef`s via
  `batch_link.fetch()` / `propose_experiment` reading `search(status="approved")` — NOT raw generation.
  Writes back `attach_ad_ref`/`update_metrics`/`set_status(winner|trashed)`, keyed by `variant_id`.
  "More like winner" via `regenerate(mode=more_like_winner)` = the growth flywheel.
- **WhatsApp-creative** (creative-whatsapp-creative.md) fetches asset bytes by `creative.get`/library `url`
  (upload-once cache keyed `(phone_number_id, file_sha)`) and attaches as a TEMPLATE MEDIA HEADER; writes
  delivery/read/click/booking back via `update_metrics`. Template approval stays Meta's gate.
- **Workflow-studio** (platform-workflow-studio.md): `creative.*` ToolSpecs are Action nodes
  OUT-OF-THE-BOX (it "only needs the ToolSpec"). The compiler DOMINATOR check forces a BUDGET node (+
  APPROVAL on money/send) on every path from trigger — same safety as any money tool. Risk read from
  ToolSpec metadata, never tenant JSON.
- **Asset Library** (creative-asset-library.md) is the ONE canonical store; `GET /creative/assets` is the
  ONE search API (video doc's `/creative/video/assets` is a thin alias == `?kind=video`).

## KEY RULES (load-bearing)
- **Only `status=approved` assets leave the studio** (to Adbot or a WA blast) unless tenant enables
  auto-mode. `creative.approve` is classed `destructive` (the content-policy firewall — the human gate
  before machine creative spends money). Default biases safe (master §41 no auto-launch).
- **Versions not overwrites:** `edit`/`regenerate` create NEW `AssetRef`s; lineage kept (master §41).
- **Status = cross-plane visibility:** draft=studio-only, approved=any plane, winner=preferred (search
  default-ranks winners), trashed/rejected=hidden-but-kept (audit + learning).
- **Asset stays campaign-linked forever** (`campaign_id` set at gen, never lost) → all reuse + all perf
  rolls up to the originating campaign.
- **Media routing:** Phase-1 service = STATIC VISUALS ONLY. `creative.generate_video`->Video AI,
  `creative.generate_brochure`->Brochure AI. The service may make the COVER/hero image only, never the
  full video/PDF (master §2 OUT scope).

## PERFORMANCE-LEARNING (§30/§31) — the loop that makes it a *learning* designer
- Signals (WhatsApp delivered/read/click/booking + ads CTR/CPC/ROI/conv + human approve/reject/edit +
  score) write back into each `AssetRef.metrics/status/score`. `creative.generate` reads
  `library.performance_summary(tenant, industry, campaign)` INTO the stage-1 LLM prompt-builder → next
  batch over-weights winning angles/styles/CTA/language, down-weights rejected. It's a READ of the
  library's own fields — no new model, no new store.
- HONEST: it biases STYLE/angle/CTA, never invents FACTS (master §20 — never fabricate price/RERA/
  testimonial). Cold-start tenant → industry-pack defaults. No "guaranteed winning ad" claim.

## SECURITY POSTURE (every seam respects)
- Tenant from TOKEN never body; handoffs (to-adbot/to-whatsapp) re-assert `AssetRef.tenant_id==token`
  (media-gen dual-channel trap: overwrite body tenant + ownership-check by-id routes; negative control =
  body vendor_id must fail to forge). FORCE-RLS `ai_asset_*` (own schema, admin-GUC, like ai_manager_*).
  One money-path. Dormant-until-creds everywhere -> `not_configured`, never raises into a call/run/loop.

## WIRING IS DEFERRED (orchestrator-owned) — 6 small dormant-safe offline-testable seams (doc §9)
register ToolSpecs -> wire adapters/creative.py + creative_pack -> ads feed-in/feedback -> WA
browse/attach+writeback -> workflow palette + 2 flow templates -> performance-learning read. No
destructive spine edit. NET-NEW is ONLY the `creative.*` contract + the performance-feedback read; adds
no new media engine / ad adapter / WA client / workflow node type.
</content>
</invoke>
