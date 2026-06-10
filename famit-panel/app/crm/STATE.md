# CRM workspace page — build STATE (crash-safe)

Task: FRONTEND PAGE "CRM workspace (app/crm + contact profile)" in famit-panel.
Reuse premium components (Layout/Card/KpiCard/Badge/.data-table/.state-block).
Wire to crm-core §7 endpoints; graceful "not configured" when dormant (router is
DEFINED-NOT-MOUNTED on live API -> /contacts* returns 404).

Constraint: edit ONLY this page's own files under app/crm. Do NOT touch
globals.css, navigation.tsx, lib/api.ts, or other pages. No deploy (ship step
does nav+build+deploy).

Backend contract (design/platform-crm-core.md §7), all X-Auth, tenant-scoped:
- GET /contacts?stage=&hot=&segment=&q=&sort=&limit= -> {contacts:[{id,phone_display,name,stage,score,hot,last_outcome,last_activity_at}], total}
- GET /contacts/{id} -> {contact:{...full...}, lead:{...}, nba:{action,reason,requires_pin}}
- GET /contacts/{id}/timeline?kinds=&limit= -> {timeline:[{kind,direction,title,body,outcome,amount,at}], contact_id}
- GET /contacts/{id}/nba -> {action,reason,confidence,params,requires_pin}
- GET /segments -> {segments:[...]}  (for the segment filter dropdown)
Dormant: 404/501/network -> render premium "CRM not configured / coming soon".
ONLY 401 redirects to /login.

Units:
- U1 client.ts (colocated API client + types)            -> DONE
- U2 page.tsx (workspace list + KPIs + filters + search) -> DONE
- U3 [id]/page.tsx (contact profile)                     -> DONE
- U4 npx tsc --noEmit + npm run build green              -> DONE

Files created (all under app/crm/):
- app/crm/client.ts
- app/crm/_ui.tsx
- app/crm/page.tsx
- app/crm/[id]/page.tsx
- app/crm/STATE.md (this file)

RECONCILED against as-built API (droplet_work/caller.py @1971-2065 + crm/core.py),
NOT just design §7 — the routes ARE mounted in caller.py (NOT defined-not-mounted):
- path param is {phone} but accepts a ct_ contact id (my list passes c.id=ct_... OK)
- detail returns {contact, timeline, nba} — NO top-level `lead`; lead truth is
  PROJECTED INTO contact (stage/score/hot/last_outcome). Profile now reads lead-ish
  fields off `contact`; seeds timeline from the embedded detail.timeline for "all".
- list/timeline/nba answer 200 with a `note` ("crm module unavailable"/"pg_unavailable")
  when dormant, NOT a 404 -> isDormantResponse() note-check + null-contact -> dormant.
- 404 = genuine "contact not found" (CrmNotFoundError, distinct state), NOT dormant.
- nba shape {action,reason,confidence,params,requires_pin} matches exactly; all 6
  action verbs covered by nbaMeta; sort fixed to "last_activity_at".

VERIFY: `npx tsc --noEmit` clean; clean `npm run build` -> Compiled successfully,
55/55 pages, both /crm (6.43kB) and /crm/[id] (5.79kB) routes present.
(A mid-run .next cache race caused a transient "Unexpected end of JSON input" —
fixed by killing stray node + rm -rf .next; the clean rebuild is fully green.)
No globals.css / navigation.tsx / lib/api.ts / other-page edits. Not deployed.

NOTE for ship step: add a nav entry for /crm (the page intentionally does NOT
touch navigation.tsx). Suggested: Intelligence or Outreach group, icon "profile",
label "CRM" / "Contacts", roles manager+ (read is fine for agents too).
