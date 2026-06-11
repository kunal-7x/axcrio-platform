# mod-whatsapp-builder — WhatsApp Campaign Builder (module + send-side engine + workspace)

> Durable brain note for the WhatsApp Campaign Builder. Companion to the sibling design docs under
> `caps/design/wa-*.md` and the asset-service memory (`memory/creative-studio-asset-service.md`). Append-only.

**2026-06-11 — MASTER BUILD PLAN synthesized (`caps/WHATSAPP_CAMPAIGN_BUILDER_PLAN.md`, READ-ONLY design
wave — no app code, no git, no deploy).** Combines the FIVE design docs into ONE crash-safe, wave-ordered
build plan:
- `design/wa-builder-frontend.md` — the premium 11-step `/whatsapp` campaign WORKSPACE (① Launchpad → ②
  Campaign → ③ AI Templates → ④ Creative → ⑤ Banner Studio → ⑥ Preview → ⑦ Approval → ⑧ Audience → ⑨ Schedule
  → ⑩ Delivery → ⑪ Analytics; ZERO new component families — ports Core_2 archetypes; pinned WhatsApp phone-mock
  = restyled `Message` bubble; dot-matrix loader).
- `design/wa-template-ai-backend.md` — the AI template-gen BRAIN = a thin `whatsapp-builder` MODULE in the
  monolith (`droplet_work/whatsapp_builder/`, NOT a new service; droplets 3/3 full; AIM in-process precedent).
  LLM PROPOSES, deterministic **Meta-compliance validator is the AUTHORITY**. 4 FORCE-RLS `ai_wa_*` tables.
- `design/wa-creative-integration.md` — the no-upload ATTACH seam (bind `asset_id` not bytes; two doors to the
  Asset Library; version-compare; the resolve→`media_id`+resumable `header_handle`→IMAGE-header template last
  mile).
- `design/wa-delivery-analytics.md` — the SEND-SIDE engine (`wa_campaign_*` schema; `cells` rollup per
  template×creative×audience; consent/session gate; quality-tier throttle; durable Sender reusing `send_kit()`;
  learning loop).
- `design/wa-out-of-box.md` — top-5 OOB features (F1 follow-ups · F4 voice+WA · F3 per-lead creative · F2
  leaderboard · F5 promote-to-ad), build order F2→F1→F3→F4→F5.

**THE TWO-LANE SHAPE (the key sequencing decision):** the AI-template backend + the Meta media-template wiring
are **NON-frontend → build in the BACKEND lane NOW**, in parallel with the UI-overhaul, dormant-safe +
offline-testable + zero new creds. The **frontend workspace is GATED** — it runs only AFTER the UI-overhaul
lane (W1 shell shipped) + the Creative-Studio frontend + Asset Library it embeds. The two lanes meet at the
HTTP-route / ToolSpec **contract** the backend publishes.

**THE WAVES:**
- **B0** schema/store → **`validate.py` FIRST (the authority)** → `personalize.py`.
- **B1** context+prompt → LLM(reuse Groq→OpenRouter)+generate+credit(F4 reserve/settle/release) → structure/CTA
  → mutators+audit → learning read → router+ToolSpec (`whatsapp.generate_templates`); `test_builder_offline.py`
  green (13 assertions, zero net/creds).
- **B2** attach approved `AssetRef` → resolve→Meta media upload (KEY SUBTLETY: resumable `header_handle` at
  template-create + cached `media_id` per send = TWO refs from same bytes) → dormant submit-to-meta.
- **B3** ported run-campaign audience + consent/session gate → `wa_campaign_*` schema → scheduler + hard
  quality-tier throttle (1K/10K/100K/∞; auto-throttle on YELLOW/RED) → durable Sender (REUSES `send_kit()`) →
  webhook tracking funnel → `cells` analytics → learning loop (winner writeback + clone/optimize/repurpose).
- **B2 ∥ B3** parallel (different modules) after their B0/B1 deps; ONE agent per module.
- **F0** UI-overhaul shell (W1 ✓) + Creative-Studio FE + Asset Library (the gate).
- **F1** shell+11-step rail+① Launchpad → ②Campaign+⑥Preview+phone-mock → ⑨Schedule+⑩Delivery (elevate LIVE
  log) — needs only the live send path, builds ahead of creative steps.
- **F2** ③AI-cards → ④Creative picker → attach+version-compare → ⑤Banner-Studio drawer (needs Creative-Studio
  FE + B1/B2).
- **F3** ⑦two-gate Approval → ⑧Audience+insights → ⑪Analytics+learning-reuse cards.
- **F4** OOB top-5 chains (F2→F1→F3→F4→F5).

**THE LIVE-PATH INVARIANT:** today's `/whatsapp/send` + message-log never break; every backend wave is
flag-gated (`FEATURE_WHATSAPP` OFF → live path untouched); F1.3 elevates the live log, never replaces it.
**One money path** (LLM gen via `wallet.reserve(resource_type="wa_template_gen")`, banner via `creative.*`,
per-msg send via the meter; attach free); tenant-from-token never body; FORCE-RLS on `ai_wa_*`/`wa_campaign_*`;
immutable audit. **Crash-safe:** one agent per module, build→offline-test→commit per unit, "IN PROGRESS" line
in a per-lane STATE file; opus for validator/learning/send-orchestration, sonnet for the Core_2 ports.

**FOUNDER GO-LIVE PREREQUISITES (box-side, for COLD outside-24h list sends only — the whole builder
builds+offline-passes WITHOUT them; verified `WHATSAPP_GOLIVE.md`):** (1) the new permanent `EAA…` token into
`/opt/famit-agent/.env` `META_WA_TOKEN` (box still holds the OLD `4234…` token — the #1 in-app-send fix); (2)
**ONE approved real Meta template (IMAGE header + body + CTA)** — **THE #1 launch blocker**; only `hello_world`
(test-number-only) exists; (3) set `FEATURE_WHATSAPP`/`WHATSAPP_ENABLED` + `systemctl restart famit-caller`;
(4) subscribe the live webhook (`https://panel.famit.in/api/whatsapp/inbound`, token `evsaivoiceagent`) to the
`messages` field — endpoint already VERIFIED; (5) confirm the "MedFlow" / +91 97550 40013 WABA is intended; (6)
optional caps/consent config. Open-session sends (someone who messaged in 24h) work TODAY via the free-form
path. Honest: AI writes compliant DRAFTS a human approves; Meta still approves the template; the learning loop
biases style, never fabricates facts.

**2026-06-11 — UNIT B1 SHIPPED (the AI template-gen MODULE; backend lane; offline-green; mounted flag-OFF).**
Built per `design/wa-template-ai-backend.md` as `whatsapp_builder/` (deployed `/opt/famit-agent/whatsapp_builder/`).
Two-layer brain LIVE in code: LLM proposes (reused Groq→OpenRouter seam, **OpenRouter env = founder typo
`OPNEROUTER_API_KEY`**), deterministic **`validate.py` is the AUTHORITY** (Meta 2026 grammar:
header/body≤1024/footer≤60-no-var/buttons≤10-≤2URL-≤1phone-text≤25; `{{n}}` sequential gap-free non-adjacent
not-at-edges example-per-placeholder; category auto-classify MARKETING/UTILITY/AUTH via weighted phrases — the
validator decides, never the model; NO-INVENT scrub regex-strips fabricated price/RERA+modifier/%off/guarantee/
phone NOT in context → `needs_fact`, blocks approve). `personalize.py` renumbers named→positional + binds
lead_field/fallback/sample. 4 FORCE-RLS `ai_wa_*` tables (`db/ddl_ai_wa.sql`, admin-GUC ddl_wallet shape,
standalone-applied) + JSONL offline fallback. Credit via `wallet.reserve(resource_type="wa_template_gen",idem_key)`
→ settle/release (failed gen never charges; idem no-double-reserve). `attach_banner` = creative.* tenant-checked
(cross-tenant refused). `meta_submit.py` dormant (correct `POST /{waba}/message_templates` body). Token-deriving
`build_router(resolve_tenant,can,need_auth,forbidden,firewall)` → 11 routes `/whatsapp/campaign/*` (tenant ALWAYS
from token). **caller.py mount appended** behind `FEATURE_WHATSAPP_BUILDER` (default OFF → byte-identical), diff =
ONLY the additive block. **`test_builder_offline.py` = ALL 13 PASS exit 0** (httpx patched-to-RAISE = zero network),
green locally + in the box capsy venv. **Regression GREEN on box:** core /campaigns /leads /me 200, /run/preview
POST 200, builder routes 404 (flag OFF), famit-caller+famit-aiasset active, zero 5xx. Rollback =
`caller.py.WABbak.20260611-021904`. Build report `memory/build_log/wave-build-wa-builder.md`. **DEFERRED to
orchestrator:** apply DDL via psql(famit_app) → register `whatsapp.generate_templates` ToolSpec → wire
`/whatsapp/inbound` metric writeback (learning) → banner media-upload last-mile → flip flag ON after schema.

**2026-06-11 — UNIT B2 SHIPPED (WhatsApp + DO Spaces GO-LIVE; report `build_log/wave-build-B2-wa-spaces-golive.md`).**
Real EAA `META_WA_TOKEN` (202c) + `FEATURE_WHATSAPP=1` on `/opt/famit-agent/.env` (box was BLANK, not the
old `4234..`). SPACES_* added to `/opt/famit-aiasset/.env` + **`boto3` pip-installed into the aiasset venv
(was MISSING → the silent Spaces blocker)**. THREE code fixes (all backed up `*.B2bak/*.WABbak.20260610-213324`,
live earner safe): (1) `image_banner_studio/storage.py` `_spaces_mirror()` wired into `save_job` — best-effort
mirror of banner bytes to Spaces via the EXISTING `asset_library.spaces.put_bytes`, attaches
`spaces_key/spaces_url/storage`, dormant-safe + never-raises (writes BOTH local + Spaces); (2) `whatsapp.py`
`_meta_to()` strips the leading `+` (Graph 404s on `+`-prefixed `to`); (3) `caller.py` `_wa_send(is_text)` —
the in-app `/whatsapp/send` text path was sending raw text as a TEMPLATE NAME (Graph #132001) → now routes
free-form text to `send_whatsapp_text_async`; (4) `asset_library/spaces.py` `put_bytes` retries WITHOUT ACL
on `UnsupportedAclConfiguration` (bucket `capsy-recordings` has **object-ownership enforced / ACLs disabled**;
objects served via PRESIGNED url, bucket is private → direct public URL = 403). TEST a PASS: in-app send
`sent:200` wamid `...QkYzMkQ4MkYwRDg4MkUyMTE4AA==`. TEST b PASS: OpenRouter banner (1.38MB) → Spaces key
`creative/admin/banner/<job>/0.png`, HEAD image/png. Regression GREEN (core 200, builder 404 flag-OFF,
webhook verify 200, voice untouched, zero 5xx). Cold-send still needs a real approved Meta template (only
`hello_world`) — founder's Meta gate.

**2026-06-11 — UNIT C2 GO-LIVE (the builder is now LIVE on the box; report `build_log/wave-build-wa-builder.md`
§C2).** All B1-deferred wiring done except inbound-metric writeback + banner last-mile. (1) `ddl_ai_wa.sql`
APPLIED via psql(famit_app) — the B1 "standalone-applied" claim was FALSE (pre-count=0); the 4 `ai_wa_*` tables
now exist with FORCE-RLS + per-table isolation policy, cross-tenant read PROVEN 0 (seed A → read-as-B=0,
read-as-A=1, no-GUC=0). (2) `whatsapp.generate_templates` ToolSpec REGISTERED in the BOX workforce catalog
(box catalog = source-of-truth, carries B3 creative wiring; droplet_work/ was stale) + stub mirror + granted to
`whatsapp`+`ops` roles (scope→write action, spend=0 because the builder meters its own credit). (3)
`FEATURE_WHATSAPP_BUILDER=1` + restart. (4) SMOKE GREEN: `POST /whatsapp/campaign/c17e55e9f3/generate-templates`
(admin) → 200 (was 404), `status:accepted` via `groq:llama-4-scout`, 3 MARKETING templates, validator
authority (`compliance.valid no_invent_flags=[]`), persisted 6 rows, money hold id99 `wa_template_gen` reserve
Rs4→settle Rs4 no-double-charge. **TWO REQUIRED BUGS FIXED (don't re-derive):** (a) `router.py` imported
FastAPI `Request/Body` INSIDE `build_router` → with `from __future__ import annotations` FastAPI couldn't
resolve the string `"Request"` → 422 `query.request required` + `/openapi.json` 500 → FIX = hoist the FastAPI
import to MODULE scope (booking/router.py already does this); (b) `credit.reserve` called `wallet.reserve`
WITHOUT `is_admin` → its `wallet_idempotency` INSERT was RLS-refused → spurious `insufficient_credits` even when
funded → FIX = thread `is_admin` through `credit.reserve`+`generate.py` (wallet.settle/release already run
is_admin=True internally; only reserve takes the flag, same as the asset svc). Regression GREEN (core 200,
famit-bridge voice active, zero request-path 5xx, live `/whatsapp/send` byte-untouched). Backups `*.C2bak.20260611`
on box (router/credit/generate/catalog/stub_tools/roles/.env). STILL DEFERRED: inbound-webhook metric writeback,
banner last-mile, and cold-send (founder's real-Meta-template gate).
