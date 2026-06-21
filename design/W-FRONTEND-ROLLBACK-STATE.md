# W-FRONTEND-ROLLBACK-STATE — compaction-proof record (2026-06-19)

## What happened (the regression)
The W15 "UI consolidation" (panel commit ~`15826f2`, branch `fix/realtime-voice-kernel-v2`)
REPLACED the sidebar/navigation with a stripped-down one. It did NOT delete feature pages —
all routes still exist on disk (`app/creative/{brand,library,video}`, ads, campaigns,
communication, integrations, knowledge, leads, payments, support, vendors, webhooks, whatsapp,
ai-manager, booking, funnels, workflows, …) — but the new nav only linked a handful and gutted
the Creative Studio nav to a single studio. Founder saw it as "you erased my whole product."
LESSON (append to AGENT_LEARNINGS): never REPLACE the founder's existing IA/nav — only ADD.
A consolidation that drops nav links reads as deletion to a non-technical owner.

## Action taken — ROLLBACK (live panel restored)
- Box: FORTRESS panel `root@143.110.247.249`, service `famit-panel` (:3001). Voice box UNTOUCHED.
- Restored `/opt/famit-panel/.next` from `/opt/famit-panel/.next.W16bak.20260618-191059`
  (= pre-W15 full-featured build, BUILD_ID `xF8YUvBmTwYj_yP4w7WY4`).
- Preserved the W15 dashboard build first at `/opt/famit-panel/.next.W15dash` (so it can be re-added).
- `systemctl restart famit-panel` → `LOCAL_HTTP=200`. Restored build verified to expose ALL feature
  routes (creative, crm, ads, campaigns, ai-manager, booking, funnels, integrations, knowledge,
  leads, payments, support, vendors, whatsapp, workflows).
- Full pre-W15 source tar also on box: `/opt/famit-panel.W16bak.20260618-191059.tar.gz` (92M).

## Current live state
- panel.famit.in = FULL pre-W15 product (all features + full nav). Founder's product is back.
- The good W15 dashboard is NOT currently live (reverts with the rollback). It will return
  ADDITIVELY (full product + dashboard-at-home + working filters) via the reconcile build below.

## In flight
- `frontend-reconcile-and-plan` workflow (run `wf_2036c586-a08`, task `w4drsb37y`): maps nav-vs-routes,
  diagnoses the dummy dashboard filters, reconstructs done/pending + voice-heart status, then BUILDS
  the additive merge on-branch + npm-build-verify, NO deploy. Output → `design/W-FRONTEND-RECONCILE-PLAN.md`.
- W-VOICE-HEART (the core voice brain) still running — founder's #1 priority.
- W-WIRE-OPS: DONE — caller.py live-data backbone wired + deployed dormant (flags OFF, earner
  agent.py md5 unchanged, only famit-caller restarted). Per-flag flips are founder-gated.

## Next step (after reconcile build returns + I review)
Gated deploy of the merged panel build (full features + dashboard + working filters) to the panel
box only — backup current `.next`, swap, restart famit-panel, verify 200 + nav shows everything +
filters work. Then founder visual check.

## Rollback-of-rollback (re-show W15 dashboard build, if ever needed)
`ssh -i ~/.ssh/do-blr-test/id_ed25519 root@143.110.247.249 'rm -rf /opt/famit-panel/.next && cp -a /opt/famit-panel/.next.W15dash /opt/famit-panel/.next && chown -R deployuser:deployuser /opt/famit-panel/.next && systemctl restart famit-panel'`
