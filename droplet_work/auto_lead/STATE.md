# Auto Lead — STATE

Real-time, multi-source lead ingestion + automation. Replaces the dormant
"Leads & CRM"/Customer-360 nav entry with **Auto Lead** (`/auto-lead`): connect
sources → monitor in real time → auto-import every lead → validate/dedupe → route
into Haptica's leads pipeline (so Riya can call them).

## Why this shape
Most real lead sources deliver via **webhooks** (website forms, Zapier/Make,
Meta/Google lead forms, custom backends) — so a universal real-time webhook
ingestion engine with field-mapping covers a huge surface FOR REAL, no OAuth. Pull
sources (email IMAP, Apollo) get a polling adapter through the SAME pipeline.

## Backend (`droplet_work/auto_lead/`, mounted in caller.py via build_router)
- `pipeline.py` — `extract_candidate(payload, mapping)` honors an explicit field
  MAPPING (dot-paths) then AUTO-DETECTS common keys + the Meta `field_data` /
  Google `user_column_data` nested shapes. `validate(cand, rules, norm)` →
  (ok, reason, phone_norm).
- `sources.py` — `SOURCE_TYPES` registry (drives the UI: label/icon/mode/fields)
  for custom / website / zapier / meta_ads / google_ads / whatsapp (push) + email /
  apollo (pull). `poll_source(source)` = real IMAP email poller + best-effort Apollo.
- `store.py` — per-tenant `{sources, events, settings}` JSON under VAR; sources carry
  an unguessable `token`; events = capped ring buffer (live feed).
- `router.py` — endpoints + the pipeline core (`_process`: extract→validate→dedup→
  route via injected `add_lead`→event+stats) + `poll_once()`.
- `_smoke.py` — 36-check offline test (pipeline shapes, store, full router incl.
  public ingest, dedup, honeypot, form-encoded, dry-run, feed, overview, disable).

### Endpoints (prefix `/auto-lead`)
- **`POST /auto-lead/ingest/{token}`** — PUBLIC real-time webhook (unauth; tenant from
  the per-source token; 64 KB cap + honeypot on top of caller.py's global IP
  rate-limit). JSON or form-encoded.
- `GET types` · sources CRUD (`GET/POST/GET{id}/PATCH/DELETE`) · `POST {id}/test`
  (dry-run plan) · `POST {id}/sync` (poll pull source now) · `GET feed` · `GET
  overview` · `GET/PUT settings`.

### caller.py integration
Injects `_al_add_lead(tenant_id, lead)` — the EXACT lock-guarded, phone-normalised,
per-tenant-deduped write to `leads.json` the `/leads` endpoint does (single source of
truth). A startup task drives `poll_once()` every `AUTO_LEAD_POLL_INTERVAL` (120s).
`FEATURE_AUTO_LEAD` default ON; import-guarded + dormant-safe.

## Frontend (`famit-panel/app/auto-lead/`)
`page.tsx` (tabs: Overview / Sources / Live Feed) + `_components/` (Overview KPIs +
by-source + latest; Sources gallery+list with enable toggle; SourceModal =
connect [webhook URL+copy+test OR credentials+sync] + field-mapping + validation +
routing controls; Feed = auto-refreshing live stream). Nav "Auto Lead" → /auto-lead.

## Operating it
Sources → "Add a source" → pick a type. Push types: copy the webhook URL into the
platform (or Zapier) + "Send a test lead". Pull types (email/Apollo): enter
credentials + "Sync now" (also polled every 120s). Each accepted lead lands in
**Leads** (callable by campaigns) with source + tags; optionally marked hot / pushed
to Sales CRM. Live Feed streams every ingest with its validation outcome.

## Verified
`py_compile` clean (module + caller.py); `_smoke` 36/36; frontend `tsc` 0 errors +
`next build` ✓. LIVE on prod (v1.5.0): public webhook ingest accepted a lead that
landed in leads.json (source `auto:website`), dedup + missing-phone rejected
correctly, feed recorded events.
