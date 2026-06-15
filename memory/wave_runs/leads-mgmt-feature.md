# Wave: leads-mgmt-feature

Founder ask: Leads page — delete-all (tenant-scoped, confirm-gated), delete specific (multi-select + per-row), sort filter (recent/oldest/name/status). RUN manual-pick — same sort filter.

## Plan / Progress
- [DONE] BE: golden caller.py.LIVEBOX.py edited (md5 ccf9715b -> 32e6062f). GET /leads sort (recent default/oldest/name/status/score); +POST /leads/delete (by ids, BOLA); +DELETE /leads?confirm=DELETE (delete-all, strict tenant_id scope, never cross-tenant). Syntax OK. Additive only.
- [DONE] FE api.ts: deleteLead / deleteLeadsBulk / deleteAllLeads.
- [DONE] FE leads/page.tsx: sort Select, multi-select checkboxes + select-all, bulk delete toolbar, per-row delete (hover trash), delete-all type-to-confirm Modal.
- [DONE] FE run/page.tsx: manual-pick sort Select (PICK_SORTS + sortLeads client-side over pickerRows).
- [IN PROGRESS] Build green (tsc + build).
- [ ] Deploy panel to FORTRESS + caller.py to box (famit-caller restart only).
- [ ] Earner gate before/after; verify on edge.

## Earner baseline (BEFORE) captured @ start
- voice box famit-livekit 168.144.153.145, ssh user=famit key=~/.ssh/do-blr-test/id_ed25519
- box caller.py md5 ccf9715b == local LIVEBOX golden (safe to edit). agent.py md5 9150fabe (UNCHANGED target).
- famit-caller listens :8209; /health=200 db/redis/livekit ok; famit-agent PID 2808658; 0 caller 5xx.

## Key findings
- Backend caller.py: GET /leads @4781 (already has sort==score, limit/offset/total/next). DELETE /leads/{lead_id} @4883 ALREADY EXISTS (per-row, BOLA-guarded) — FE just doesn't use it.
- `_leads_for(t)` @4707: admin tenant returns ALL leads cross-tenant → delete-all MUST scope by tenant_id explicitly, never via the admin all-view.
- LEADS_FILE @259 = VAR/leads.json; _read/_write @812/818. _audit @1101. can(t,"write") @976. require_object @1004 (BOLA).
- FE: lib/api.ts getLeads already sends `sort`; useLeadsInfinite already threads `sort`. Lead type @58. addLeads @590.
- FE leads page: famit-panel/app/leads/page.tsx (VirtualRows table). Run manual-pick: app/run/page.tsx showManual block @857 (pickerRows from _lib/audience.ts).

## Box golden md5 (CALLER_EDIT_LOCK): ccf9715bbc2da14ed989dac3af95c5fe — re-pull + verify before edit.
## Earner baseline: agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 — must stay UNCHANGED; famit-agent NOT restarted.
