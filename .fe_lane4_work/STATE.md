# ROUND-6 FRONTEND LANE 4 — Profile/Settings + Dynamic Permissions + Removals

Branch: fix/realtime-voice-kernel-v2. Touch ONLY this lane. Do NOT git-commit (Ship does).

## DONE
1. Profile/Settings sidebar + navbar:
   - contstants/navigation.tsx: added top-level "Settings" link in `navigation`; replaced
     navigationUser Do-Not-Call with "Profile" (both Settings+Profile → /settings).
   - app/settings/page.tsx: rewritten as production-grade "Profile & Settings" (photo upload
     w/ canvas downscale, display name, preset-avatar grid, emoji picker, save → localStorage).
   - lib/profile.ts (NEW): localStorage profile store + live broadcast event + avatar helpers.
   - components/Header/User/index.tsx: navbar avatar now mirrors profile (photo/preset/emoji), live.
2. Dynamic super-admin permissions from CURRENT nav:
   - lib/navRegistry.ts (NEW): derives module/page nodes from navigation.tsx + adds
     grow.campaigns.script / grow.campaigns.render_brain; mergeNavRegistry(seed) = additive dedup.
   - lib/api.ts: fallbackEntitlements() now merges nav-derived nodes → matrix auto-tracks the rail
     (Creative Studio, Message/WhatsApp, Revenue Tools, KB, Integrations, campaign-SCRIPT show up).
     type-only import back from api → no runtime cycle.
3. Removals:
   - app/crm/page.tsx STAGE_TABS: removed "Won"/"Lost" (kept New/Contacted/Engaged/Qualified).
   - app/leads/page.tsx: removed duplicate "Lead" column (LeadBadge) — Temperature col already shows it.
   - contstants/navigation.tsx: removed Do-Not-Call from navigationUser (it's a Calls-page tab now).

## VERIFY
- tsc / next build (typecheck) green.
