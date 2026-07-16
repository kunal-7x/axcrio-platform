# STATE — UI PREMIUM WAVE 2 (FRONTEND-ENG) — 2026-06-10

Target: caps/famit-panel (live at panel.famit.in on root@143.110.247.249 /opt/famit-panel).
NON-BREAKING restyle/structure only. No API/route/logic change. No git.

## THE 5 FIXES
1. Collapsible sidebar GROUPS (Dropdown list: pattern) for the WHOLE sidebar + a
   "Create Studio" COMING-SOON group (disabled children, no pages built).
2. Remove dark-mode ThemeButton from top navbar (Header line ~120). Toggle stays in Sidebar.
3. Remove vertical dividing line = sidebar scrollbar TRACK (scrollbar-track-b-surface2
   on Sidebar RemoveScroll) → make transparent. (No literal border exists — advisor-confirmed.)
4. Remove DUPLICATE page heading in Header (title block lines ~87-98). Add ml-auto to actions.
5. Premium polish via Core_2 token language (cohesion, not marketing/3D bits).

## ADVISOR-CAUGHT LANDMINES (must honor)
- Dropdown renders ALL list children unconditionally → role-gating breaks. Add `roles`
  to child type + filter; hide a group empty after filter. Keep Vendors(admin) gated.
- Coming-soon children CANNOT be NavLinks (always render <Link href> → 404). Add
  `comingSoon` flag → Dropdown renders dimmed <div> + "Soon" pill.
- Don't make Dashboard "/" a list child (pathname.includes("/") always true).
- Removing Header title left-shifts actions → add ml-auto to actions container; drop
  unused title/ThemeButton imports from Header.

## UNITS (flip IN PROGRESS -> DONE)
- U1 navigation.tsx — regroup into collapsible groups + Create Studio coming-soon. STATUS: DONE
- U2 Sidebar/Dropdown — roles + comingSoon child support; hide empty groups. STATUS: DONE
- U3 Sidebar — scrollbar-track transparent (Fix 3). STATUS: DONE
- U4 Header — remove ThemeButton (Fix 2) + remove title block (Fix 4) + ml-auto. STATUS: DONE
- U5 premium polish (Fix 5) — bounded token/cohesion polish. STATUS: DONE (nav-group + soon-pill css)
- U6 VERIFY — real un-sandboxed build EXIT 0 + tsc + dangling grep. STATUS: DONE (build OK)
- U7 DEPLOY — backup /opt/famit-panel, deploy, verify 200. STATUS: DONE (LIVE)

## FINAL: ✅ LIVE on https://panel.famit.in (2026-06-10). All 5 fixes verified in
the live served HTML through nginx. Routes 200; authed /api/stats 200, unauthed 401.
Build log: memory/build_log/wave-build-ui-premium-2.md. Brain appended (mistakes+patterns).

## ROLLBACK
Box backup /opt/famit-panel.bak.1781052937 (cp -a). Rollback = rm -rf /opt/famit-panel &&
mv /opt/famit-panel.bak.1781052937 /opt/famit-panel && systemctl restart famit-panel.
⚠️ After ANY restart confirm `ps -o lstart -p $(pgrep -f next-server)` start time is
fresh — the first restart this wave silently didn't take (old pid kept serving).
