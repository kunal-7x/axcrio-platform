# Wave: leads-mgmt-feature

Founder ask: Leads page — delete-all (tenant-scoped, confirm-gated), delete specific (multi-select + per-row), sort filter (recent/oldest/name/status). RUN manual-pick — same sort filter.

## Plan / Progress
- [DONE] BE: golden caller.py.LIVEBOX.py edited (md5 ccf9715b -> 32e6062f). GET /leads sort (recent default/oldest/name/status/score); +POST /leads/delete (by ids, BOLA); +DELETE /leads?confirm=DELETE (delete-all, strict tenant_id scope, never cross-tenant). Syntax OK. Additive only.
- [DONE] FE api.ts: deleteLead / deleteLeadsBulk / deleteAllLeads.
- [DONE] FE leads/page.tsx: sort Select, multi-select checkboxes + select-all, bulk delete toolbar, per-row delete (hover trash), delete-all type-to-confirm Modal.
- [DONE] FE run/page.tsx: manual-pick sort Select (PICK_SORTS + sortLeads client-side over pickerRows).
- [DONE] Build green: `npx tsc --noEmit` EXIT 0 + `npm run build` EXIT 0 (/leads 5.68kB, /run 21.1kB).
- [DONE] BE DEPLOYED to box: caller.py md5 ccf9715b -> 32e6062f (md5-gated, py-compiled OK, famit-caller restarted ONLY). EARNER GATE PASS: agent.py 9150fabe UNCHANGED before+after, famit-agent PID 2808658 UNCHANGED, /health 200. Backup `/opt/famit-agent/caller.py.leadsmgmtbak.20260615-174918` (=ccf9715b).
- [DONE] BE VERIFIED over loopback (SAFE, no real wipe — total stayed 30): no-auth=401; sort=recent first 2026-06-15 (newest), sort=oldest first 2026-06-03 (oldest) -> order visibly changes; DELETE /leads w/o confirm=400 (gate); POST /leads/delete empty/bogus ids -> deleted=0 (idempotent, tenant-scoped); total_after=30.
- [DONE] Panel DEPLOYED to FORTRESS 143.110.247.249 (on-box `npm install --legacy-peer-deps` + `npm run build` green; swapped .next only + `systemctl restart famit-panel`). BUILD_ID u6yKGIuhALhhzdzQcywXQ -> **xF8YUvBmTwYj_yP4w7WY4**. (SSH to panel box had a ~2min intermittent timeout window mid-deploy; recovered on retry — edge stayed 200 throughout, zero downtime.) Backup `.next.leadsmgmtbak.20260615-124143`.
- [DONE] Panel VERIFIED on EDGE: panel.famit.in / =200, /leads=200, /run=200; new BUILD_ID xF8YUvBmTwYj_yP4w7WY4 present in served HTML (new build is live, not stale cache). 0 edge 5xx.
- [DONE] FINAL EARNER GATE: agent.py 9150fabe UNCHANGED, famit-agent PID 2808658 NRestarts=0 (never restarted), caller.py 32e6062f, famit-caller active, /health 200, 0 real caller 5xx in 12min.

## OUTCOME: ✅ FULLY LIVE + VERIFIED
- Leads page (panel.famit.in/leads): sort dropdown (Newest/Oldest/Name/Status/Score, default Newest), multi-select checkboxes + bulk Delete-selected, per-row hover-trash delete, Delete-all type-DELETE-to-confirm modal — all tenant-scoped, backed by live endpoints.
- Run page (panel.famit.in/run, step 1 "Pick manually"): same sort dropdown (PICK_SORTS, client-side over picker rows).
- ROLLBACK: BE -> `cp /opt/famit-agent/caller.py.leadsmgmtbak.20260615-174918 /opt/famit-agent/caller.py && systemctl restart famit-caller`. Panel -> `mv /opt/famit-panel/.next /opt/famit-panel/.next.bad && mv /opt/famit-panel/.next.leadsmgmtbak.20260615-124143 /opt/famit-panel/.next && systemctl restart famit-panel`.

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
