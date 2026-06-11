# apps/ — end-user applications (Next.js)

| app | phase | purpose |
|-----|-------|---------|
| dashboard | P1 | Operator console: connect → wizard → live feed (SSE) → approvals → AI-CMO report. Uses `@growth-os/sdk` + `@growth-os/ui`. The dashboard consumes the SAME public API it ships (§17.5). |
| lp-runtime | P2 | Landing-page runtime: SSR block renderer for message-match LPs (our subdomain / vendor CNAME); the 1P pixel + instant `lead.captured` (§15.6). |

Phase-0 = placeholders. Built per phase (§21).
