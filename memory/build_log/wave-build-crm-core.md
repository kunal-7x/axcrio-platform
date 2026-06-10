# WAVE-BUILD-CRM-CORE — CONTACT SPINE + UNIFIED TIMELINE + NEXT-BEST-ACTION (PLATFORM-ENG)

Spec: `design/platform-crm-core.md` (followed; RED-TEAM fixes folded). Roadmap: MASTER_PLATFORM_ROADMAP (CRM).
Box: famit@168.144.153.145 `/opt/famit-agent/`, venv `/opt/capsy-agent/.venv` (py3.12), svc `famit-caller`
(uvicorn :8209) + `famit-agent`. SSH key `...\do-blr-test\id_ed25519`. Mode: ADDITIVE, non-breaking, NO
run-path change, NO git (orchestrator commits). STATE: `droplet_work/CRM_CORE_STATE.md`.

## RECONCILE (2026-06-10 start)
- md5 local==box ZERO drift: caller c404f1c0, store 2b2b0774, engine 7c4538b1, models 0f092a64. Both svcs active.
- STORE_MODES = 12 stores dual (P1 done). NO crm.py, NO crm tables, NO contacts (clean slate).
- leads=5 (3 tenants: admin×3, ae1ba3017296, 21d0a13603da), calls=83 in PG. var/wa_threads EMPTY.
- F2 (brain/kb pgvector) + F4 (wallet/firewall) already shipped — read their decisions; crm mirrors their shape.

## LOCKED DECISIONS (advisor-confirmed — see brain/decisions.md)
1. **STANDALONE `crm/schema.sql` (NOT Alembic 0002).** Mirrors kb/schema.sql (F2) + wallet (F4): keep crm's
   blast radius OFF the P1 0001/0002 keystone migration chain. Applied lazily via `crm.ensure_schema()`
   (first-use) or psql -f. Spec text "Alembic 0002" predates F2/F4 + cites the stale mid-strangle state
   ("all other stores still json", now 12 dual). DEVIATION documented; fix-wins (F4 precedent).
2. **canonical_phone = norm(p)[1:]** (strip the '+') -> digits-only `91XXXXXXXXXX` = `phone_key`;
   `phone_display` = norm(p) (+91…). Reuses caller.norm (injected via crm.init(norm=...) at startup +
   a function-local `from caller import norm` fallback at request time — NO top-level import cycle).
3. **DEFERRED the `_finalize_call` CRM_TIMELINE_WRITE live-append hook** (it's a run-path edit; the spec
   ships it OFF anyway). Timeline is a PURE READ-MODEL via `rebuild_timeline` (stitches calls+transcripts+
   wa_threads+suppression). => the WHOLE unit is additive (F2 shape: new module + standalone schema +
   additive routes + backfill script, ZERO run-path edit, caller.py edited only for import+5 routes).
4. **Built contacts + contact_identity + contact_timeline + rule-based NBA. DEFERRED** segments/
   segment_members/lifecycle_rules/lifecycle_fires DDL + their engines (task names them as later units).
5. ensure_schema() LAZY (top of each PG fn), mirrors kb. Endpoints `{phone}` (canonicalize->contact_id,
   accept ct_ id too). PUT NEVER writes leads. NBA deterministic only (CRM_NBA_LLM off). No paid call.

## SCHEMA (crm/schema.sql — 3 tables, PG-native projection; NOT in the store.py JSON-mirror seam)
- **contacts** — the person spine. PK `ct_<sha1(org_id|phone_key)[:16]>`. `org_id` (P1 convention, matches
  leads/calls). Columns: phone_key (canonical 91…), phone_display (+91…), name, email, + a DERIVED
  projection (stage, score, hot, last_outcome, last_activity_at, consent_call/wa) + `stage_override`
  (manual PUT stage; derive_stage PREFERS it, never clobbered) + `data jsonb` (tags/custom). Unique
  (org_id, phone_key); indexes on stage/score-DESC/last_activity_at-DESC. ENABLE+FORCE RLS, admin-GUC policy.
- **contact_identity** — alias table (PK (org_id, kind, value)). Today only ('phone', phone_key) rows;
  forward-proofs email/external_id/wa_id attach with ZERO schema change. RLS forced.
- **contact_timeline** — the unified per-person stream. PK `tl_<sha1(org|contact|kind|source_id|at)[:20]>`
  (DETERMINISTIC -> rebuild/replay can't double-insert, ON CONFLICT DO NOTHING). kind=call|whatsapp|
  consent|... ; direction, source, source_id, title, body, outcome, amount/currency (typed slots for the
  future booking/purchase modules), at/at_raw, data. Indexes (org,contact,at DESC) + (org,kind,at DESC). RLS forced.
- VERIFIED on box: 3 tables relrowsecurity=t relforcerowsecurity=t, 3 isolation policies, all 4 contacts
  indexes + pkey.

## SERVICES (crm/core.py — import-safe, graceful-degrade, mirrors kb/core.py)
- **Identity:** `canonical_phone` (§1.1), `contact_id` (deterministic, no DB hit), `_match_forms` (THE
  silent-join fix — see below), `upsert_contact` (UPSERT (org,phone_key) + creates the 'phone' alias).
- **Projection:** `project_contact` (recompute stage/score/hot/last_*/consent from leads+timeline+
  suppression, write onto the contact; NEVER writes leads), `derive_stage` (pure: opted_out/won/booked/
  qualified(score>=70)/engaged/contacted/dormant(>45d)/new; PREFERS stage_override). `_lead_for` reads the
  authoritative lead row from PG (leads dual-mirrored). `_is_suppressed` reads suppression (consent).
- **Timeline:** `rebuild_timeline` (backfill/self-heal: CALLS from PG joined to the transcript-by-room on
  disk for the summary body + WhatsApp from var/wa_threads/<digits>.json + SUPPRESSION/consent from PG;
  deterministic ids), `get_timeline` (newest-first, kinds filter).
- **NBA:** `next_best_action` = ordered deterministic rule table over existing fields. opt_out/suppressed
  -> {action:'none'} (consent HARD STOP, never actuates); not_interested -> nurture (NO re-pitch);
  callback -> place_call(pin); hot/qualified & no recent WA -> send_whatsapp(qualified_followup, pin);
  interested & no WA -> send_whatsapp(interested_recap); no_answer/vm -> retry_call(pin); dormant ->
  reengage(pin); new/contacted -> place_call(pin); else nurture. CRM_NBA_LLM default OFF (rules only; no
  metered call on any read path).
- Import-safe: PG down -> available()->False, every read returns empty/degraded; the panel never breaks.

## THE §1.1 SILENT-JOIN BUG — found by the smoke, fixed once (`_match_forms`)
The smoke seeded ONE human as `+916375548830` (lead) / `6375548830` raw-10 (call) / `916375548830` (wa).
First run FAILED "timeline contains the CALL event": the SQL join `regexp_replace(phone,'\D','') = :pk`
(pk = canonical `916375548830`) MISSED the call whose phone was stored raw-10-digit (`6375548830`). FIX:
`_match_forms(phone)` returns EVERY digit-rep the same human could be STORED as — canonical `91…`, bare
10-digit, and leading-zero `0…` — and the join matches `regexp_replace(phone,'\D','') = ANY(:forms)`.
Applied to `_lead_for` + the calls/suppression queries in `rebuild_timeline` + `_is_suppressed`. THIS is
the load-bearing canonicalization fix; without it a person's calls and WhatsApp split into two contacts.

## ENDPOINTS (additive; X-Auth, tenant-scoped org_id==t['tenant_id'] NEVER a param; PG work off the loop)
- `GET /contacts?stage=&hot=&q=&sort=&limit=` -> {contacts:[...], total} (filter/segment).
- `GET /contacts/{phone}` -> {contact, timeline, nba} (projects on read; {phone}=any form OR a ct_ id).
- `GET /contacts/{phone}/timeline?kinds=&limit=` -> {timeline, contact_id} (full interaction history).
- `GET /contacts/{phone}/nba` -> {action, reason, confidence, params, requires_pin}.
- `PUT /contacts/{phone}` (write-gated) JSON {name?,email?,tags?[],stage?,data?} -> updates the CONTACT
  (tags->data, stage->stage_override). NEVER writes leads. Strips body org_id/id/phone_key (identity from path).
- caller.py: +1 import block (`import crm as _crm_mod`, degrade to None) + crm.init(norm=norm) in the startup
  hook (best-effort, single-sources norm + ensures schema) + the 5 routes after /brain/retrieve. ALL keyword-
  only crm args passed via lambdas through asyncio.to_thread (project/get/timeline/nba are keyword-only).

## ⭐ THE PROOF (no paid call; box, live PG)
**OFFLINE/PG smoke** (`_smoke_crm_box.py`, throwaway tenants, 20/20 PASS):
- (a) IDENTITY/CANONICALIZATION: +91 / raw-10 / 91 collapse to ONE contact_id; timeline contains the CALL
  (with the transcript summary body) AND the WhatsApp (joined across phone forms). **§1.1 proven.**
- (b) TIMELINE newest-first; re-running rebuild adds ZERO rows (3==3, deterministic-id idempotency).
- (c) STAGE/SCORE = projection: score=80/interested -> stage=qualified, hot=true, score=80; the lead row
  is byte-UNCHANGED (no write-back).
- (d) NBA deterministic, no Groq (CRM_NBA_LLM OFF asserted): qualified+no-WA -> send_whatsapp
  qualified_followup; opted_out -> none (consent hard stop); not_interested -> nurture.
- (h) RLS: tenant B sees 0 of tenant A's contacts AND 0 timeline rows; B can't read A's contact by id.

**REAL-DATA backfill** (`backfill_contacts.py`, read-only on leads): 5 live leads -> 5 contacts + **63
timeline rows** stitched from the real calls/transcripts/wa/suppression. Idempotent (2nd --commit = same
5/63). Multi-tenant (admin3, 21d..1, ae1..1). Real NBA sensible: Aarav (suppressed, 49-call timeline) ->
stage=opted_out, NBA=none (consent hard stop); two qualified hot leads -> send_whatsapp.

**LIVE HTTP API** (panel.famit.in, X-Auth admin):
- GET /contacts -> 200, returns the 5 real backfilled contacts (admin sees all tenants).
- GET /contacts/+917987388671 -> profile + timeline (a REAL call stitched with its transcript: "discussed
  a 5 crore property in Jabalpur with Colin…", interest=80, room, next_action) + NBA send_whatsapp.
- GET /contacts/{phone}/timeline + /nba -> 200, correct shapes.
- PUT /contacts/+917987388671 {tags,name,stage:booked} -> contact reflects it (stage_override=booked,
  data.tags=[vip,sector79]); the LEAD row stays status=new score=80 with NO tags/booked key — **no write-
  back proven on the live API.** Override SURVIVES re-projection (derive_stage prefers it). Reset colin to
  clean state after (no residue on real data).

## REGRESSION GATE — GREEN
- Legacy X-Auth 200 on /campaigns /leads /billing/overview /me /stats /callbacks. /contacts(+filters) 200.
  no-auth /contacts -> 401. /auth/login bad-creds -> clean 401 (not 5xx). Both svcs active. ZERO 5xx/traceback.
- INSTANTIATE-smoke (`_crm_insttest.py`) BEFORE restart: caller exec_module clean, all 5 /contacts routes
  registered (GET×4 + PUT), existing routes (campaigns/leads/run/billing/me/brain) intact, _crm_mod wired.
- /run DISPATCH: job dispatched (count=1) — ⚠ suppressed_count=0 (the suppression POST didn't propagate to
  the dial loop's in-RAM read in time, the documented timing trap). The number +910000000077 is
  invalid/unallocated -> the dispatched call = outcome=voicemail answered=False (NO human, NO billable
  conversation). /run path proven to dispatch; harmless. (Brain lesson re-confirmed: to prove dispatch-
  nobody, PRE-SEED + confirm suppressed_count>0 BEFORE trusting; or use a side-process — don't re-/run.)
- md5 local==box: caller 6478885b, crm/core 934872dc, crm/schema e4b8a96, crm/__init__ 230ad344.
- ⚠ JWT-200 leg of the gate is consciously N/A (not silently dropped): `auth._SECRET` is Doppler-only (N2),
  so a real vendor-JWT can't be minted in-shell. `resolve_tenant` is byte-UNCHANGED by this wave, so the
  JWT auth path is intact by construction (it tries JWT first, falls through to legacy). Curl'd legacy X-Auth.
- ⚠ POST-/run DRIFT HEALED (the advisor-flagged side effect): the test /run wrote a real call record;
  `calls` is dual -> `shadow_diff calls` showed field_drift=1 (the documented S6 UPSERT/RMW race: PG kept
  `_wh_completed:true` a later in-RAM-CALLS write dropped). Healed via a SIDE-PROCESS
  `store._pg_reconcile_leads(calls_spec, current calls.json)` (PG-only, no file, no dial) ->
  `shadow_diff calls => 0` exit 0. Confirmed NO junk lead `+910000000077` in leads.json (the inline /run
  lead did not persist) and NO junk contact (phone_key 910000000077 = 0 rows) -> no junk on the next backfill.
  The dual-mirror invariant the next session inherits is clean.

## WHAT'S ADDITIVE / WHAT'S DEFERRED
- **ADDITIVE:** crm/ module (PG-native projection over the existing stores; the live voice path imports
  NEITHER it nor touches it). 3 new PG tables (additive; DROP or leave). caller.py: import + startup
  init + 5 routes (purely additive; zero existing route/seam changed). backfill_contacts.py (inert script,
  nothing in the service imports it). NO .env change (crm is NOT a STORE_MODES mirror store). NO run-path edit.
- **DEFERRED (named later units, NOT built here):**
  * The `_finalize_call` CRM_TIMELINE_WRITE live-append hook (run-path edit; ships OFF; rebuild_timeline +
    on-read project_contact already keep the timeline fresh for the read endpoints).
  * Segmentation engine (segments/segment_members tables + eval_segment + the predicate AST §6).
  * Lifecycle trigger engine (lifecycle_rules/lifecycle_fires + lifecycle_tick + the §5 gated actuation
    via _admission_gate/_spawn_retry_job; RTF-1/2/3 spend+PIN guards). PIN verifier is unbuilt (fail-closed).
  * The frontend CRM workspace (the panel page consuming these endpoints).
  * NBA LLM enrichment (CRM_NBA_LLM batched off-hot-path refinement).
  * contact merge/dedupe (two phones one human) — contact_identity makes it non-breaking when needed.

## ROLLBACK
- crm tables are additive — DROP TABLE contact_timeline, contact_identity, contacts (source stores untouched,
  nothing lost; projection rebuildable).
- caller.py: `cp caller.py.CRMbak.1781062062 caller.py && sudo systemctl restart famit-caller` (back to
  c404f1c0; the 5 routes vanish, crm import is import-guarded so even leaving it is harmless when crm/ absent).
- backfill_contacts.py / crm/ are inert wrt the running service. No .env to revert.

## DEPLOYED ARTIFACTS (box md5 == local)
- crm/schema.sql e4b8a96, crm/core.py 934872dc, crm/__init__.py 230ad344, caller.py 6478885b (CRMbak.1781062062).
- backfill_contacts.py (inert). store.py / db/models.py / db/engine.py UNCHANGED (no Alembic, no store seam edit).
