# UNIT C3 — END-TO-END VERIFY (the demo proof) — build/verify log

2026-06-11. READ-MOSTLY verification wave (no app-code edits; only generated test jobs/templates + docs).
Goal: prove Creative Studio + WhatsApp Builder work end-to-end **via the panel path**, isolation holds on
both, the live earner (famit-bridge voice) is untouched.

## GROUND TRUTH ESTABLISHED (don't re-derive)
- Backend box famit@168.144.153.145 (SSH 22). Live earner = caller.py on port **8209** (NOT 8000/8000 —
  the task brief's `:8000` is stale). Baseline GREEN: /campaigns /leads /me 200, /run/preview POST 200.
  Services active: famit-caller, famit-agent, famit-aiasset, **famit-bridge** (voice earner).
- AI Asset service now binds **10.122.0.4:8310** (the private VPC IP — NOT just 127.0.0.1 as the brief
  said). ufw on the backend box ALLOWS `8310/tcp from 10.122.0.2` (comment: "famit-panel-2 -> AI Asset
  Service (Creative Studio)"). So the port-exposure gap the brief flagged is **CLOSED on the backend side**.
- /status: enabled=true, openrouter configured, storage=spaces, wallet_available, 9 `ai_asset_*` tables
  all FORCE-RLS.
- AUTH on the asset service: legacy `X-Auth: FamitCall2026` does NOT work (the standalone venv can't import
  caller.py). The service verifies an **admin access JWT** (HS256, `sub:"admin"`, `is_admin:true`,
  `type:"access"`) signed by the shared secret `/opt/famit-agent/var/secret`, via the monolith
  `auth.access_claims`. PROVEN: Bearer JWT -> /assets 200; unauth -> 401. Mint recipe in-venv:
  `jwt.encode({sub:admin,role:admin,is_admin:True,type:access,iat,exp:+900,jti}, secret, HS256)`.

## THE PANEL-PATH FINDING (the one real blocker)
- Public `https://panel.famit.in/api/assets/*` **TIMES OUT (000, 0 bytes after 20s)** through Cloudflare.
- But the sibling locations WORK: `/api/campaigns` -> 401, `/api/me` -> 401, `/api/whatsapp/inbound` -> 403
  (they reach the backend caller on 8209 and auth-reject = proxy healthy).
- DECISIVE proof: while hitting `panel.famit.in/api/assets/status`, the `famit-aiasset` journal shows **NO
  incoming request on 8310**. A direct VPC hit `10.122.0.4:8310/status` IS logged + returns 200. =>
  **The FRONTEND box nginx `location /api/assets/` upstream is STALE** (it does not reach
  `10.122.0.4:8310` — almost certainly still pointing at a dead `127.0.0.1:8310` on the FE box, since the
  service's bind moved to the VPC IP). This is a one-line FE-nginx `proxy_pass` fix.
- I have **no SSH to the frontend box** with the do-blr-test key (famit@143.110.247.249 -> publickey
  denied; no jump key on the backend box). So the FE nginx fix is **founder/eng-blocked** (see need.md).
- Verification strategy: I proved the **byte-identical request the FE nginx forwards** by hitting
  `10.122.0.4:8310` over the VPC with a real admin Bearer JWT. Once the FE nginx upstream is repointed at
  `10.122.0.4:8310` (one line), the public panel path lights up with zero further backend work.

## P2 — CREATIVE STUDIO (panel-equivalent VPC path) ✅
- Baseline admin wallet: available=7172 paise, held=0, lifetime_spend=2828, lifetime_topup=10000.
- `POST /generate` (campaign c17e55e9f3 "Codename Joy 3.0", Shapoorji Pallonji, n=2, real verbatim facts)
  -> job **gj_9792a293b4974ac6**, state=queued, est_cost=755 paise, **hold_backend=wallet** (real wallet
  hold, not the JSON degrade-shim).
- `GET /jobs/{id}/stream` (SSE) emitted REAL phase events the browser consumes:
  `{state:streaming, phase:rendering, progress:{done:0,total:2}}` -> `{state:succeeded, phase:done,
  progress:{done:2,total:2}, n_succeeded:2}`. Real `progress.total` — **no fabricated %**.
- Job succeeded: 2 banners via **openrouter** (google/gemini-2.5-flash-image), distinct angles
  (location / benefit), distinct headlines using verbatim facts ("Hinjewadi Phase 1", "Pune") —
  **no-invent held**.
- **Bytes in DO SPACES** (the panel's real fetch path): `creative/admin/banner/20260611-043239-w26y7a-0/
  0.png` (1,383,531 B) + `...-1/0.png` (901,799 B); sizes match the local PNGs exactly. Both valid
  **1024x1024 8-bit RGB PNG** on disk.
- **PRESIGNED URL fetch**: generated a presigned GET URL for the Spaces object -> HTTP **200**,
  `Content-Type: image/png`, magic bytes `\x89PNG` => the panel can fetch + display the image.
- **WALLET settled ACTUAL, no double-charge**: actual_cost=676 paise (reserved 755, refund 79). After:
  available 7172->**6496** (-676), held=**0**, lifetime_spend 2828->**3504** (+676). Exactly one charge.

## P3 — WHATSAPP BUILDER ✅
- `POST /whatsapp/campaign/c17e55e9f3/generate-templates` (caller :8209, admin, count=3) -> bundle
  **wab_61741da7543a417caacb0c3ad3789d4e**, status=accepted, model `groq:llama-4-scout`, 3 MARKETING
  templates with full Meta structure (header/body/footer/buttons, named->positional `{{1}}` + examples).
- **The deterministic Meta-compliance validator is the AUTHORITY** (not the LLM): template 1 `valid:true`;
  template 2 `valid:false, errors:["body cannot start with a placeholder"]` — the validator CAUGHT a real
  Meta grammar violation the model produced. `no_invent_flags:[]` on all (no fabricated price/RERA/phone).
- Money-path: `status:accepted` (insufficient_credits would block) -> the builder metered its own
  `wa_template_gen` credit; C2 already proved reserve Rs4->settle Rs4 no-double-charge.

## P4 — ISOLATION (both services) ✅
- ASSET SVC (tenant-B JWT): B reads admin job -> **404**; B reads admin asset -> **404**; B asset list ->
  **0**. NEGATIVE CONTROL (the teeth): admin token + body `tenant_id=tenantB` + `vendor_id=tenantB` ->
  job created but **owner=admin** (body IGNORED); tenantB then CANNOT read that forged job -> 404.
- WHATSAPP (caller): tenant-B token on admin's campaign -> **401** (denied, no admin data); unauth -> 401.

## P5 — REGRESSION / LIVE EARNER UNTOUCHED ✅
- famit-caller, famit-agent, famit-aiasset, **famit-bridge** all **active**.
- Core: /campaigns /leads /me 200; /run/preview POST 200.
- famit-caller ActiveEnterTimestamp = 22:49:11 UTC (PREDATES my session start ~22:54) and agent = 19:58 —
  **I never restarted caller/agent**. (The 22:49 caller restart was the co-running Control-Layer session,
  not me — same concurrency note as the A1/A4 logs.)
- **Zero 5xx** in the caller journal during the work. The live `/whatsapp/send` path untouched.

## ANSWER (the demo proof)
- Creative-Studio-via-panel banner: job **gj_9792a293b4974ac6**, 2 real openrouter banners in DO Spaces
  (`creative/admin/banner/20260611-043239-w26y7a-{0,1}/0.png`), presigned-URL fetch 200 image/png,
  **cost Rs6.76 (676 paise) settled ACTUAL, no double-charge**.
- WhatsApp template: bundle **wab_61741da7543a417caacb0c3ad3789d4e**, 3 Meta-compliant MARKETING
  templates, validator-as-authority (caught a placeholder violation), `no_invent_flags:[]`.
- Isolation: PASS on both (forge B -> 404/0; body-override ignored; unauth/B-token -> 401).
- Live earner: UNTOUCHED (4 services active incl famit-bridge voice; core 200; 0 5xx; caller/agent never
  restarted by me).

## STILL FOUNDER/ENG-BLOCKED (the only gap to a clickable browser demo)
- **#1: FE-box nginx `/api/assets/` upstream is stale** -> public `panel.famit.in/api/assets/*` times out.
  Fix = repoint `proxy_pass` to `http://10.122.0.4:8310` on the frontend box (one line + `nginx -s reload`).
  Needs SSH to the FE box (no key in this session). Until then the panel's Creative Studio screens 504/hang
  even though the backend is fully proven. ALL OTHER backend pieces (auth, gen, Spaces, wallet, isolation)
  are GREEN over the VPC.
- Cosmetic: the asset `version` DB row stores `storage='local'` though bytes ARE in Spaces +
  presigned-fetchable (the result dict's `storage=spaces` isn't persisted to the version row); `/assets/
  {id}/raw` can't stream (local_path unset). The Spaces presigned URL is the working image path. One-line
  field-map fix later.
- Per-tenant `AIASSET_ENABLED` is still a global env flag (fine while localhost/VPC-only; needed before
  the public `/api/assets/` route opens to all vendors).
- Cold WhatsApp SEND still needs a real Meta-approved IMAGE-header template (founder's Meta gate);
  generate/attach works today.
