# ROUND5 FRONTEND2 — DEPLOY STATE

Date: 2026-06-19 · Branch: fix/realtime-voice-kernel-v2

## Shipped
Selective panel changes (4 lanes) — vendor logos (public/vendors/*.svg),
ConfirmDeleteModal, ProviderLogo, nav + lib/api + lib/queries wiring, and page
edits across ai-manager, booking, calls, campaigns, creative, crm, leads,
suppression, webhooks. `next build` EXIT 0 (no TS errors). Pre-built .next shipped
(NOT built on-box). Panel box ONLY — voice box untouched.

## Facts
- Commit: 87e97bc
- Live BUILD_ID: ZsE_YmL4rT80F9v6BcNLI (prev 5QSKx7TnwhQTRGnBthPCl)
- Box: root@143.110.247.249 (/opt/famit-panel), service famit-panel
- gitleaks --staged: 0 leaks · selective add (never -A)
- Backup: /opt/famit-panel/.next.R5UI2bak.20260619-152545

## Verify (all PASS)
- systemctl is-active famit-panel = active
- box BUILD_ID = ZsE_YmL4rT80F9v6BcNLI (new)
- http://127.0.0.1:3001/ = 200
- https://panel.famit.in/ = 200

## Rollback
ssh root@143.110.247.249 'cd /opt/famit-panel && rm -rf .next && cp -a .next.R5UI2bak.20260619-152545 .next && chown -R deployuser:deployuser .next && systemctl restart famit-panel'
