# TELEGRAM ECOSYSTEM — DIAGNOSIS + EARNER-SAFE BUILD PLAN

> READ-ONLY diagnosis (2026-06-15). Box `famit@168.144.153.145` `/opt/famit-agent`.
> Live facts: caller.py md5 `ccf9715b` (8094 lines) · agent.py md5 `9150fabe` UNCHANGED ·
> all comm flags ON for tenant `admin` (`COMM_ENABLED · COMM_TELEGRAM_ENABLED ·
> FEATURE_TELEGRAM_FOUNDER_ALERT · FEATURE_TELEGRAM_FOLLOWUP · COMM_BRAIN_ENABLED ·
> COMM_COST_GUARDS_ENABLED · COMM_METERING_ENABLED · COMM_TOKEN_BUCKET_ENABLED`).
> Founder chat_id `1862240811` persisted (sentinel). `comm-poll.service` running (PID 2961553).
>
> **The headline:** the comm package is well-built and LIVE, but it is wired into the WRONG
> finalize (outbound only) and it NEVER seeds the brain's session with the real call facts.
> Those two gaps explain complaints 1, 2 and 4. Complaints 3, 5, 6 are mostly-present and need
> small additive work. **The #1 fix is grounding — seed `comm_sessions` post-call so the brain
> stops hallucinating.**

---

## A) ROOT CAUSE OF EACH COMPLAINT (file:line + why)

### Complaint 1 — "after an INBOUND call no Telegram follow-up fires" — ROOT CAUSE FOUND
The comm post-call hook is wired into **only the OUTBOUND dial loop**, not the inbound voice path.

- The hook lives at `caller.py:2796-2818` (the `COMMUNICATION (W1-P3)` block) — inside
  `_finalize_call` (`caller.py:2705`). `_finalize_call` is called from exactly ONE place,
  `caller.py:2873`, inside `run_job` (the **outbound** dialer). Grep proof: `_finalize_call(` has
  one call site (2873).
- The **inbound** call is a SEPARATE process — `aim_voice_agent.py` (169 KB, the AI-Manager voice
  agent). Its session lifecycle is `_AimSessionLogger.finish()` (`aim_voice_agent.py:2069`) +
  `_on_room_disconnected_log` (`:2813`) writing the `ai_manager_sessions` PG table (REC-A). It does
  **NOT** import or call `comm.post_call` / `comm.engine` / `comm.founder_alert` —
  `grep "comm\.post_call|comm\.engine|from comm|comm\.founder" aim_voice_agent.py` → **0 hits (RC=1)**.
- The ONLY post-call human-notify on inbound is `transfer_to_human → notify_handoff_team` (WhatsApp)
  fired from `aim_voice_agent.py:831` (`_vt.notify_handoff_team`). That is WhatsApp, not Telegram,
  and only fires on an explicit transfer/hot path — not as a general post-call follow-up.
- The reconciliation sweep (`scheduler_loop`, the second region of `_finalize_call`'s file) re-emits
  webhooks for late transcripts but **also does not call the comm hook** — so even outbound
  late-reconciled calls skip the Telegram follow-up.

**Why the founder's real inbound test produced nothing on Telegram:** his call went through
`aim_voice_agent.py`, which has no Telegram seam at all. The founder hot-lead ALERT and the contact
auto-summary both live behind the outbound-only `_finalize_call` hook. (Even on an OUTBOUND call the
contact auto-summary would no-op `no_destination` unless the lead had `/start`-ed the bot — see B.)

### Complaint 2 — "Telegram conversation has NO call context; the bot hallucinated property details" — ROOT CAUSE FOUND (this is the #1 fix)
The brain reads call grounding from the **session row**, but **nothing ever writes it there**.

- The brain assembles its ctx in `comm/webhook.py:284 _build_ctx`, which reads
  `sess.get("call_summary")` / `next_action` / `outcome` / `interest` / `company_name` /
  `product_name` / `product_summary` (`webhook.py:295-303`). The brain injects these into the
  system prompt at `comm/brain.py:155 _build_grounding` + `:186 build_system_prompt`. **If
  `call_summary` is empty, the grounding paragraph is empty** → the prompt says only "you are Riya
  continuing a conversation after a phone call" with NO facts → the LLM invents the property.
- The session row is created by `comm/sessions.py:70 get_or_create`, which writes **only identity
  columns** (chat_id, phone, lead_id, call_id, persona). It does **NOT** write
  `call_summary/next_action/outcome/interest`. `append_turn` (`sessions.py:117`) only appends turns.
- **There is NO seeding function anywhere in the comm package.** Grep the whole package: nothing
  ever `UPDATE comm_sessions SET call_summary=...`. `comm/post_call.py:run` (the post-call task)
  sends an alert + a summary message but **never seeds the session**. The DDL even documents the
  intent — `ddl_comm.sql` comment on `call_summary`: *"post-call seed … in W1 it is seeded by the
  post-call hook only"* — but that seed code was never written.
- Secondary bug: `_build_ctx` reads `company_name/product_name/product_summary`
  (`webhook.py:301-303`) but those **columns do not exist** in `comm_sessions` (DDL + live
  `information_schema` both confirm: only `…call_summary, next_action, outcome, interest…`). So even
  product/brand context is structurally unreachable today.
- The build-log's "grounded reply PROOF" passed only because the test **manually INSERTed** a
  `call_summary` into the session by raw SQL ("Seeded a comm_session with call_summary=…"). In a
  real flow nothing does that → the founder's transcript (fabricated "xyz, 2000 sqft, 3 BHK, 1.5 cr")
  is the expected output of an ungrounded brain.

### Complaint 3 — "Hot-lead HANDOFF to the telecaller/handoff list is missing (on Telegram)" — PARTIALLY PRESENT
- A handoff path EXISTS but is **WhatsApp-only**: `caller.py:1911 notify_handoff_team` sends the
  lead phone + summary + score to every handoff-list number via `_wa_send`. It is fired on the
  outbound hot branch (`caller.py:2789`, inside the `_score >= 70` block) and on inbound transfer
  (`aim_voice_agent.py:831`).
- There is **NO Telegram handoff card** to the telecallers. The comm package only alerts the
  FOUNDER (`comm/founder_alert.py:115 send_hot_lead_alert`, to the founder's own chat_id) — not the
  handoff-list people. The founder wants the handoff TEAM (telecallers) to get a Telegram card with
  {phone, summary, what they asked} so they can call the lead. That Telegram-to-team leg does not
  exist. (And it inherits complaint-1's gap: it's not wired on inbound at all.)

### Complaint 4 — "Rich follow-up missing (template + links + BANNER + VIDEO) to the interested person on Telegram" — NOT BUILT
- The contact auto-summary (`comm/post_call.py:112 _draft_summary_text` / `:168` send) is **text
  only** — no banner image, no video, no links/buttons. It is also gated on `contact_chat_id`
  (`post_call.py:169`) which is empty unless the lead `/start`-ed the bot (see B — a lead can't be
  cold-messaged).
- The Telegram adapter **already supports** media + buttons (`comm/channels/telegram.py` routes
  `sendPhoto`/`sendVideo`/`sendDocument` + inline URL buttons; the W1-P1 log confirms this), and a
  `file_id` cache exists (`comm_asset_cache`). So the rich-template send is a content-assembly task,
  not a transport task — the pipe is there, the payload isn't.
- The banner library and the composite video both exist (see C) but nothing in the comm package
  fetches a banner or renders/attaches a video.

### Complaint 5 — "I can't SEE the Communication tab" — CONFIRMED: FE EXISTS, NOT DEPLOYED
- Full FE is built + committed on `fe/unify-run-wavec`: `famit-panel/app/communication/page.tsx`
  + `_body.tsx` + `_shared.tsx` + 4 views (`_views/ChannelsView·BuilderView·InboxView·
  AnalyticsView.tsx`) + 2 components (`_components/TelegramSetup·TelegramPreview.tsx`) + nav entry
  `famit-panel/contstants/navigation.tsx:157` (`Engage > Communication`, `/communication`,
  `feature_key:"engage.communication"`). tsc/build/eslint/gitleaks all green (commit `c2d4e02`).
- **Root cause = panel not deployed** (a separate agent owns the canonical panel deploy). No code
  gap. One gap to note: the InboxView is read/poll + one-tap takeover (live composer send is W4), and
  it renders nothing until `COMM_ENABLED` makes `/api/comm/*` return 200 through the public edge —
  which needs the panel deploy AND the comm router reachable via the panel proxy (caller :8209 is
  firewalled to the panel box only). After deploy, verify `/api/comm/channels` returns 200 (not 404)
  through `panel.famit.in`.

### Complaint 6 — "Create a simple voice+transcript ($0) video from ANY script in the UI" — MOSTLY PRESENT, 1 UI GAP
- The composite tier IS the default and IS $0-gen: `VideoCreatePanel.tsx:88 tier default "composite"`;
  `TierTabs.tsx` Composite = ≈₹0.25/clip, no gen key; the command box accepts any instruction;
  `canGenerate = enabled && campaign && instruction.trim().length > 0` (`VideoCreatePanel.tsx:120`).
  BE is live (Video Studio activated 2026-06-15; `compose_worker.py` auto-spawns a detached render;
  proven real MP4 — see `memory/wave_runs/video-studio-activate-real.md`).
- **The one gap:** `canGenerate` requires a **campaign** to be selected (`!!campaign`). There is no
  "script-only, no campaign" path — the composite render derives its visual from the campaign
  (`compose_worker.resolve_visual` falls back to a branded color slate, so a no-campaign render is
  technically possible, but the UI blocks Generate without a campaign). To let the founder type ANY
  script with no campaign, the UI must allow a campaign-less composite (send a synthetic/`_adhoc`
  brief; BE already has a slate fallback). Small FE change + a BE brief tweak.

---

## B) THE HONEST TELEGRAM REALITY (do not over-promise)

Telegram bots **cannot cold-message a phone number.** A bot can only send to a `chat_id`, and a
`chat_id` only exists **after that user has messaged the bot first** (tapped Start / sent a message).
There is no phone→chat_id lookup. This is a hard Telegram platform constraint, not a bug.

What this means for each leg:

1. **Founder + telecaller/handoff team → rich hot-lead cards: FULLY POSSIBLE.** They opt in ONCE
   (tap `@mr_kunal_bot`, or a per-tenant bot, send any message → we capture their chat_id via
   getUpdates and persist it, exactly like the founder sentinel `sessions.py:261 set_founder_chat_id`).
   After that one tap they get cards forever. **This is the realistic, high-value path — build it.**
   The founder already did his tap (chat_id `1862240811`).

2. **A LEAD converses with Riya on Telegram: POSSIBLE ONLY via a tap-to-chat deep-link.** We must
   GET the lead to message the bot first. The mechanism exists: `comm/deeplink.py:120 mint` makes a
   signed single-use `https://t.me/<bot>?start=<payload>` link; when the lead taps it,
   `webhook._maybe_handle_start` binds their chat_id + writes a `telegram_start` consent row. We
   deliver that link to the lead **during/after the call** via an existing channel — the agent says
   it / SMS / WhatsApp. We **cannot** auto-DM the lead on Telegram before they tap.

3. **Auto-messaging the lead's phone (no tap) needs WhatsApp or SMS — both gated.** WhatsApp is the
   live earner channel (don't touch its Meta logic for this); SMS is DLT-gated (W5, 5-10 day TRAI
   registration). So the "after the call, automatically send the lead a rich template" leg is
   **Telegram-only-IF-they-tapped**, otherwise WhatsApp/SMS. Be explicit with the founder: the rich
   Telegram follow-up to a lead requires the lead to have tapped the deep-link; the zero-touch
   version of that is the WhatsApp path that already exists (`_wa_ai_followup`).

**Net honest framing:** the team-handoff Telegram card (#3) and the founder alert (#1) are 100%
deliverable. The lead-facing rich Telegram follow-up (#4) is deliverable to leads who tapped the
deep-link; for everyone else it's the existing WhatsApp follow-up. Don't promise cold Telegram DMs
to leads — they're impossible.

---

## C) REUSE INVENTORY (file:line — mirror these, don't reinvent)

| What | Where | Notes |
|---|---|---|
| **Handoff-list source (telecaller numbers)** | `caller.py:1785 _handoff_get(tenant_id)` → reads the Business Brain `handoff` block at `var/brain/<tenant>.json`; returns `[{name, phone/whatsapp, ...}]`. Setters `:1821 _handoff_set` / `:1862 _handoff_add_one`. | This is the list to send the Telegram handoff card to. Same source `notify_handoff_team` uses. |
| **WhatsApp hot-lead handoff (template to mirror)** | `caller.py:1911 notify_handoff_team` — builds `🔥 Hot lead: {name} ({phone}). Score {sc}/100. Summary: {summ}. Reply to take over.` + params `[name,phone,summ,score]`; loops the handoff team. | Mirror the body/loop for Telegram; reuse `_handoff_get`. |
| **Outbound WA follow-up content logic** | `caller.py:2355 _wa_ai_followup` + `:2144 _wa_draft_followup_text` (reads summary/next_action/interest/company/product) + `:2189 _wa_reply_text`. | The field-read template for assembling rich follow-up text. `comm/brain.py` is already a copy of `_wa_reply_text`. |
| **Founder alert (template + chat_id resolve)** | `comm/founder_alert.py:66 build_alert_envelope` + `:115 send_hot_lead_alert`; chat_id via `engine.derive_founder_chat_id` (cached getUpdates, persisted sentinel). | Copy this shape for the per-recipient TEAM handoff card. |
| **Telegram media + buttons transport** | `comm/channels/telegram.py` — `sendMessage/sendPhoto/sendVideo/sendDocument` + inline URL buttons + `file_id` cache (`comm_asset_cache`). | The rich-template PIPE already works; only the payload assembly is missing. |
| **Banner library (generated banners/images)** | `ai_asset` service (`/opt/famit-aiasset/`). List: `ai_asset/endpoints.py:182 GET /assets?media_type=image&campaign_id=...`. Presigned bytes: `:222 /assets/{id}/raw` (302 → presigned Spaces URL, `_spaces.presign(key, 86400)`). | Fetch one campaign banner's presigned URL → pass as a Telegram `MediaItem(url=...)`. Caller↔aiasset over VPC loopback `10.122.0.4:8310` with `AIASSET_SERVICE_TOKEN` (already wired for the video bridge, `caller.py:7442`). |
| **Composite video render invocation** | `media_gen/video/client.py:41 submit_video_job(brief)` → `compose.submit` (`compose.py:230`) → `_dispatch_render` (`:297`) → `compose_worker.enqueue(plan)` which auto-spawns a detached `python -m media_gen.video.compose_worker <job_id> --bridge` (flag `VIDEO_COMPOSE_SPAWN`, default ON). Finished MP4 → Spaces → ai_asset library bridge → `/assets?media_type=video` → `/assets/{id}/raw` presigns the MP4. | Reuse the SAME presigned-URL pattern as the banner to attach the video to a Telegram `sendVideo`. |
| **Brain grounding layers (where to feed facts)** | `comm/webhook.py:284 _build_ctx` (reads session seeds) → `comm/brain.py:155 _build_grounding` / `:186 build_system_prompt`. `_memory_recap` (`webhook.py:312`) for cross-call history. | The seed target is `comm_sessions.call_summary/next_action/outcome/interest`. |
| **Post-call hook + snapshot (the seam to extend)** | `caller.py:2796` block → `comm/post_call.py:46 snapshot` (pure-sync) + `:142 run` (detached). | Add session-seeding + handoff-card + rich-followup INSIDE `post_call.run` (no caller.py edit needed for those — see plan). |
| **Inbound finalize seam (needs the hook added)** | `aim_voice_agent.py:2069 _AimSessionLogger.finish()` + `:2813 _on_room_disconnected_log` (the inbound hangup). `capture_interest` (`:1835`) stashes `_interest_note`. | This is the one place that must additively call a `comm.post_call`-style detached task for inbound. **aim_voice_agent runs in the SAME box but is a DIFFERENT service from the earner agent.py** — confirm which systemd unit owns it before editing. |
| **Inbound interest/outcome signals** | `ai_manager_sessions` (REC-A PG) + `_fields["_interest_note"]`. Inbound does not produce a 0-100 score the way outbound does; the hot gate on inbound is `transfer_to_human` / explicit "hot". | The inbound snapshot must derive its summary/interest from the AIM session, not from `rec/tr`. |

---

## D) THE ORDERED, EARNER-SAFE BUILD PLAN

**HARD RULES encoded in every unit below:** NEVER edit/restart `agent.py` (earner md5 `9150fabe…`).
Any `caller.py` edit goes through `CALLER_EDIT_LOCK.md` + box-fresh md5 (golden `ccf9715b`) +
anchor-string (3 variants exist; never line numbers) + `asyncio.create_task`-never-`await` on the
dial loop + pure-sync snapshot. All new flags default OFF (resting byte-identical). One box-mutating
change at a time; earner gate (agent.py md5 unchanged · famit-agent NOT restarted · /health 200 ·
0 5xx · NO ring) **before+after under an induced Telegram outage**. gitleaks `protect --staged` = 0.
The bot token stays in the vault — never logged, never on argv. Restart ONLY famit-caller /
famit-aiasset / the poll worker / the inbound voice unit — NEVER famit-agent.

> **Most units are pure `comm/` package edits = NO caller.py edit = NO lock needed** (the W1-P2
> mount already routes everything through `comm.post_call.run` and the webhook). Only Unit-3
> (inbound seam) touches a caller-class file (`aim_voice_agent.py`) and needs the lock + golden +
> anchor discipline.

---

### UNIT 1 — ⭐ THE #1 FIX: seed `comm_sessions` with the real call facts (stops the hallucination)
- **What:** add `comm/sessions.py:seed_call_context(tenant_id, *, chat_id_or_phone, call_summary,
  next_action, outcome, interest, company_name, product_name, lead_id, call_id)` that
  `UPDATE comm_sessions SET call_summary/next_action/outcome/interest=… WHERE …` (upsert the row
  first via `get_or_create`). Call it from `comm/post_call.py:run` for EVERY finalized call (not just
  hot) so the session is grounded the moment the lead later taps the deep-link and chats. Also add a
  migration adding `company_name/product_name/product_summary` columns to `comm_sessions` (the brain
  already reads them) — OR drop those three reads from `_build_ctx` and fold product context into
  `call_summary`. Prefer adding the 3 columns (additive DDL, drop-safe).
- **Files:** `comm/sessions.py` (+seed fn), `comm/post_call.py` (call seed in `run` + carry the
  fields in `snapshot`), `communication/db/ddl_comm.sql` (+3 columns, idempotent `ADD COLUMN IF NOT
  EXISTS`). **NO caller.py edit** (post_call.run already runs detached).
- **Box-mutating?** Yes (deploy comm files + apply additive DDL + restart famit-caller). No caller.py,
  no lock.
- **Model:** opus (this is the correctness keystone).
- **Parallel?** Must land FIRST; everything else builds on a grounded session. Serialize.
- **Acceptance:** seed a real outbound call → row has non-empty `call_summary`; then POST a real
  inbound webhook for that chat → `_build_ctx` returns the call_summary → brain reply references the
  REAL property/summary, invents nothing. Re-run the founder's exact transcript ("mujhe property ke
  details bhejo") → the reply uses the real call facts or says "let me have the team confirm" — NO
  fabricated "xyz 2000 sqft 3 BHK 1.5 cr". Earner gate green.

### UNIT 2 — Telegram HOT-LEAD HANDOFF CARD to the telecaller/handoff team (complaint 3)
- **What:** add `comm/handoff.py:send_handoff_cards(tenant_id, snap)` — read the team via
  `_handoff_get` (bridge it into the comm package: either import the caller helper read-only, or read
  `var/brain/<tenant>.json` `handoff` block directly), resolve each member's persisted Telegram
  chat_id (only those who tapped the bot; same getUpdates+persist sentinel pattern as the founder),
  and send each a card: `🔥 Hot lead: {name} ({phone}) — score {sc}/100. They asked: {summary}.` +
  an "Open in panel / Call now" URL button. Members without a chat_id are skipped (and surfaced in
  the FE so the founder can invite them). Wire it into `comm/post_call.py:run` on the hot branch
  (alongside the founder alert), behind a new flag `FEATURE_TELEGRAM_HANDOFF` (default OFF).
- **Files:** `comm/handoff.py` (NEW), `comm/post_call.py` (call it on hot), `comm/config.py` (+flag),
  `comm/sessions.py` (a team-member chat_id persistence helper, mirrors `set_founder_chat_id`).
  **NO caller.py edit.**
- **Box-mutating?** Yes (comm deploy + flag + restart famit-caller). No lock.
- **Model:** sonnet.
- **Parallel?** Can run after Unit-1 lands; independent of Unit-3/4.
- **Acceptance:** a team member taps the bot → their chat_id persists → a hot call → each opted-in
  member gets the card with phone+summary+what-they-asked + button; non-opted members skipped
  cleanly; founder still gets his own alert. Earner gate green.

### UNIT 3 — ⚠️ WIRE THE INBOUND PATH (complaint 1) — the ONE caller-class edit
- **What:** add an additive, flag-gated, `create_task`-never-`await` post-call hook to the INBOUND
  voice path so inbound calls fire the same comm.post_call (founder alert + handoff cards + grounding
  seed + rich follow-up). The seam is `aim_voice_agent.py:2069 _AimSessionLogger.finish()` (or the
  `:2813` disconnect handler). Build a `comm.post_call.snapshot_inbound(aim_session_fields)` that
  reads the AIM session (summary, `_interest_note`, caller name/phone, campaign) — NOT `rec/tr` — and
  `asyncio.create_task(comm.post_call.run(snap))`. Behind `COMM_ENABLED` + the existing sub-flags.
- **Files:** `aim_voice_agent.py` (the hook — anchor-string, +N lines, single hunk), `comm/post_call.py`
  (a `snapshot_inbound` builder). **This touches a caller-class live file** → CALLER_EDIT_LOCK +
  box-fresh md5 of `aim_voice_agent.py` + anchor-string + py_compile on the inbound venv +
  backup-before. Confirm the inbound systemd unit name first; restart ONLY that unit, NEVER
  famit-agent.
- **Box-mutating?** Yes — the highest-risk unit (it edits the live inbound agent). Do it ALONE,
  after Units 1+2 are proven, with an immediate revert path (restore the `.bak`).
- **Model:** opus (live-earner-adjacent surgery).
- **Parallel?** NO — serialize; it's the riskiest box change.
- **Acceptance:** place a REAL inbound test call that ends hot → founder gets a Telegram alert AND
  the team gets handoff cards AND the session is seeded → a later lead chat is grounded. Earner gate
  green before+after under induced outage; inbound voice still answers normally (place a real inbound
  ring before+after); agent.py md5 unchanged; famit-agent not restarted.

### UNIT 4 — RICH FOLLOW-UP to the interested lead (template + links + BANNER + VIDEO) (complaint 4)
- **What:** upgrade `comm/post_call.py` contact-summary leg into a rich template: (a) AI-composed
  text from the REAL call facts (reuse the `_wa_draft_followup_text` field grammar), (b) fetch one
  campaign BANNER from ai_asset (`GET /assets?media_type=image&campaign_id=…` → `/assets/{id}/raw`
  presigned URL) as a `MediaItem`, (c) attach the composite VIDEO if one exists for the campaign
  (`/assets?media_type=video&campaign_id=…` → presigned MP4), (d) URL buttons (panel / site / book).
  Gated `FEATURE_TELEGRAM_RICH_FOLLOWUP` (default OFF). **Send ONLY to a lead who tapped the
  deep-link** (`contact_chat_id` present) — for everyone else it remains the existing WhatsApp
  follow-up (do not cold-DM). Reuse `comm_asset_cache` `file_id` so re-sends are ₹0.
- **Files:** `comm/post_call.py` (rich payload assembly), `comm/asset_bridge.py` (NEW — the
  read-only ai_asset banner/video fetch over VPC `10.122.0.4:8310` with `AIASSET_SERVICE_TOKEN`),
  `comm/config.py` (+flag). **NO caller.py edit.**
- **Box-mutating?** Yes (comm deploy + flag + restart famit-caller). No lock.
- **Model:** sonnet (opus for the asset-bridge auth if needed).
- **Parallel?** After Unit-1; can overlap Unit-2 (different files). Needs the deep-link delivery
  (below) to have any real lead destination.
- **Acceptance:** a lead who tapped the deep-link + had a real call → receives text + banner image +
  (if rendered) video + buttons, all grounded in the real call; a lead with no chat_id → clean
  `no_destination` no-op (WhatsApp path unchanged). Earner gate green.

### UNIT 4b — DEEP-LINK DELIVERY so leads can actually reach Riya on Telegram (enables 4)
- **What:** make the agent offer/deliver the `t.me/<bot>?start=<payload>` link during/after the call
  (voice CTA + a WhatsApp/SMS send of the link via the existing channels), so leads bind a chat_id.
  Without this, the lead-facing rich follow-up has no destination for anyone. `comm/deeplink.py:mint`
  + `endpoints.py POST /comm/channels/telegram/deeplink` already exist; this unit is the DELIVERY +
  a small FE affordance.
- **Files:** the existing WhatsApp follow-up path (additive: append the link) + FE Communication tab
  (show the deep-link / QR). **NO earner edit** (WhatsApp send of a link is additive content).
- **Model:** sonnet. **Parallel:** with Unit-4. **Acceptance:** tap the delivered link → chat_id
  binds + consent row → the lead can chat with grounded Riya.

### UNIT 5 — CONFIRM/POLISH complaint 5 (Communication tab) — FE deploy verify
- **What:** no build needed; the FE exists + committed. Confirm the canonical panel deploy (owned by
  the other agent) includes `fe/unify-run-wavec`, then verify `/api/comm/channels` returns 200 (not
  404) through `panel.famit.in`, the tab renders, Inbox lists the (now-grounded) sessions.
- **Files:** none (verification only) — or a one-line nav/route fix if the deploy surfaces a gap.
- **Model:** haiku (verify) / sonnet (if a gap). **Parallel:** independent. **Acceptance:** founder
  sees Engage > Communication, Channels setup works (getMe ok), Inbox shows real grounded sessions.

### UNIT 6 — CONFIRM/POLISH complaint 6 (script-only $0 video) — small FE+BE
- **What:** allow a campaign-less composite render so the founder can type ANY script. FE: relax
  `VideoCreatePanel.tsx:120 canGenerate` to allow no-campaign when tier=composite (send an `_adhoc`
  brief); BE: `submit_video_job` accepts a campaign-less brief and `compose_worker.resolve_visual`
  uses the branded slate fallback (already exists). Keep the $0 composite default.
- **Files:** `famit-panel/app/creative/video/_components/VideoCreatePanel.tsx` (+ `lib/video.ts`
  brief), `media_gen/video/compose.py`/`client.py` (accept adhoc brief). **NO earner edit.**
- **Model:** sonnet. **Parallel:** independent. **Acceptance:** type a script with no campaign →
  Generate → a real composite MP4 renders ($0 gen) → appears in the library → playable.

---

### Recommended order (impact × earner-safety)
1. **Unit 1 (grounding seed)** — the #1 fix; nothing else is trustworthy until the brain stops
   hallucinating. Pure comm + additive DDL, low risk.
2. **Unit 2 (Telegram handoff cards)** — high founder value, pure comm, low risk.
3. **Unit 4 + 4b (rich follow-up + deep-link delivery)** — pure comm + FE, no earner edit.
4. **Unit 5 (FE deploy verify)** — unblocks the founder SEEING all of it (coordinate with the deploy
   agent).
5. **Unit 6 (script-only video)** — small, independent, no earner edit.
6. **Unit 3 (inbound seam) LAST** — the only caller-class edit; do it alone, lock + golden +
   anchor + real inbound ring before/after + immediate revert. Highest risk → ship it once the
   safe units are proven.

**One-line summary:** the comm package is live but (a) wired only to the OUTBOUND finalize and (b)
never seeds the brain's session — so inbound produces nothing and the brain hallucinates. Fix
grounding first (Unit 1), add the Telegram team handoff (Unit 2) and rich lead follow-up (Unit 4),
wire the inbound seam carefully and last (Unit 3), and verify the already-built FE + script-only
video. Telegram cannot cold-DM a lead — the lead-facing legs require a one-tap deep-link; the
team/founder legs are 100% deliverable.
