# HANDOFF TEAM UI — build state (branch feat/premium-ui, FRONTEND ONLY)

Backend (LIVE, tenant-from-token, write-role gated, via /api proxy):
- GET    /brain/handoff -> [{ phone, whatsapp?, role?, hours?, priority, enabled }] (priority order)
- POST   /brain/handoff/add  { phone, whatsapp?, role?, hours?, priority?, enabled? } (idempotent by phone; +91 or 400)
- DELETE /brain/handoff/remove?phone=<E164>
- PUT    /brain/handoff  { handoff:[ordered list] }  (REORDER / enable-toggle / bulk save)
- GET    /ai-manager/live  -> emits handoff "Dialing #N" + target + Bridged/Failed

## Units
- [DONE] U1 lib/api.ts: HandoffMember type + getHandoffTeam/addHandoffMember/removeHandoffMember/saveHandoffOrder + HandoffError (parses {error}, invalid-phone). Dormant-safe (404/network -> empty list).
- [DONE] U2 app/ai-manager/_handoff.tsx: reusable HandoffTeam manager (list/add modal/reorder up-down/enable Switch/delete), read-only aware, dormant-safe, premium reference-kit. `compact` prop for the Run embed.
- [DONE] U3 app/ai-manager/handoff/page.tsx: dedicated view = Layout + explainer + manager.
- [DONE] U4 sidebar: "Handoff Team" child under AI Manager group (/ai-manager/handoff).
- [DONE] U5 app/run/page.tsx: compact "Handoff team" section in the left rail before launch.
- [DONE] U6 app/ai-manager/live/page.tsx + _lib getAimLive(): Live Calls monitor, Dialing #N -> Bridged/Failed progression. Sidebar child "Live Calls".
- [DONE] U7 verify: npx tsc --noEmit clean + npm run build EXIT 0. tsc clean; build EXIT 0 (54 routes, /ai-manager/handoff + /ai-manager/live present).

## Decisions
- AI Manager is ONE page w/ tabs; the prompt names app/ai-manager/live + a dedicated handoff view -> created as their own routes under the AI Manager group (reachable from sidebar). Both are manager-gated by the group.
- No `phone` icon in registry -> use `mobile`. No up/down arrow icon -> `chevron` rotated for reorder.
- Reuse Core_2 kit: Card/Button/Badge/Icon/Modal/Switch/Field/Layout. Zero raw hex (Signal tokens).
</content>
</invoke>
