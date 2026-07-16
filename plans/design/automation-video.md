# DESIGN SPEC — Ad-Creative VIDEO Generation (Async Jobs), PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS

> **Status:** EXECUTION-READY. A build agent implements this verbatim, one unit at a time, crash-safe.
> **Scope:** a NEW automation module under `droplet_work/automation/` (does **not** exist yet — this is greenfield).
> **The verdict (settled, do not relitigate):** hosted aggregator API (**fal.ai** primary, **Replicate** secondary)
> is the default backend; self-host (**Wan 2.2 on a DO GPU droplet**) is a *dormant* third backend with a documented
> breakeven, NOT the default. Every backend is provider-agnostic and **DORMANT-UNTIL-CREDS**: with no keys the module
> is a graceful no-op returning `{"status": "not_configured"}` and **NEVER raises** — byte-for-byte the `whatsapp.py`
> contract.
> **House rules honored:** NEW code only under `droplet_work/automation/`; **DO NOT edit `caller.py` / `agent.py`**
> (the endpoint wiring below is *described*, not implemented — final wiring is deferred to the orchestrator); NO git
> (orchestrator commits); verifiable **offline** (no live external calls in the acceptance test).
> Author: staff-eng design pass, grounded in live source under `droplet_work/`. Last updated: 2026-06-09.

---

## 0. GROUND TRUTH (verified against source — cite before editing)

The live backend is FastAPI `caller:app` on `famit@168.144.153.145:/opt/famit-agent/` (service `famit-caller`,
uvicorn `:8209`, venv `/opt/capsy-agent/.venv` py3.12.3). Public base `https://panel.famit.in/api` (nginx on the
panel box `143.110.247.249`, priv `10.122.0.2`, strips `/api/` → backend `:8209`). Local source of truth:
`C:\Users\kunal\Desktop\caps\droplet_work\`.

**The pattern this module clones (the WhatsApp module — the cited precedent):**

- `droplet_work/whatsapp.py` — provider-agnostic sender. `_cfg()`/`_meta_cfg()` read env at call time; `is_configured()`
  / `meta_configured()` gate; `_build_body(provider, …)` switches request shape per `WA_PROVIDER`; every send returns a
  dict `{"ok", "status", "provider", "to"[, "response"]}` and **never raises** (`try/except Exception` around the POST).
  When unconfigured it returns `{"status": "not_configured"}` and no-ops. **This module mirrors that exactly.**
- Wiring seam (`caller.py`): module imported in a `try/except` → `wa_mod = None` on failure
  (`caller.py:35-37`); endpoints (`POST /whatsapp/send` `caller.py:2939`) call an async wrapper `_wa_send(...)`
  (`caller.py:1053`) that calls `wa_mod.send_whatsapp_async(...)` then logs via `_wa_log(...)`.
- **Persistence pattern:** plain JSON files under `VAR = Path(os.getenv("FAMIT_VAR","/opt/famit-agent/var"))`
  (`caller.py:108`). Helpers `_read(path, default)` / `_write(path, data)` (`caller.py:444/450`); per-entity dirs
  created lazily with `.mkdir(parents=True, exist_ok=True)` under a `_STORE_LOCK` (e.g. `WA_THREADS_DIR`
  `caller.py:118`, `LEDGER_DIR` `caller.py:122`). The video **job store** mirrors `WA_THREADS_DIR`.
- **Auth/RBAC/audit seam:** `resolve_tenant(request)` (`caller.py:371`) → `need_auth()` (`:403`) /
  `can(tenant,"write")` (`:608`) / `_forbidden(msg)` (`:620`) / `_audit(request, tenant, action, object_type,
  object_id, channel=, meta=)` (`:713`). The video endpoints (described in §6) use these identically.
- **Spend metering precedent:** `_charge_call(tenant_id, rec)` (`caller.py:1383`) appends an itemized charge to the
  per-tenant ledger under `LEDGER_DIR` and decrements a prepaid balance. The video spend guardrail (§7) hooks the
  **same** ledger and the (specced-but-unbuilt) wallet firewall from `design/credit-ledger-firewall.md`.

**The ONE load-bearing constraint (the whole design follows from it):**

> **Video generation is an ASYNC, MINUTES-LONG, DOLLAR-HEAVY job — not a fire-and-forget send.** A single 5–8s
> ad clip costs **$0.10–$3.20** (table in §2) and takes **30s–6min** to render. Therefore the surface is
> **submit → poll/webhook → store-artifact**, every job is **reserved against a wallet hold and gated by a human
> approval step before money is spent**, and large MP4 artifacts go to an **S3-compatible object store** (DO Spaces),
> never the JSON store. This is the key difference from `whatsapp.py` (which is a synchronous sub-second send).

---

## 1. WHAT WE'RE BUILDING (one paragraph)

A `droplet_work/automation/video/` package that turns a text/image ad brief into a rendered MP4 **as an async job**,
through a **single provider-agnostic interface** (`submit_video_job` / `poll_video_job`) backed by interchangeable,
dormant-until-creds backends: **fal.ai** (primary aggregator — one key, ~12 models), **Replicate** (secondary
aggregator), **Luma** and **Higgsfield** (direct vendor APIs, optional), and **self-host Wan 2.2 on a DO GPU droplet**
(dormant, breakeven-gated). Jobs persist as JSON records under `var/video_jobs/`, artifacts land in DO Spaces,
spend is reserved→settled against the wallet ledger with a human approval gate, and the whole pipeline is exercisable
**offline** (the dormant path) with zero external calls.

---

## 2. RESEARCH: CHOSEN TOOLS + WHY (2026, cited)

### 2a. The decision in one line
**Default = fal.ai** (cheapest per-second aggregator, one key fronts every top model, true pay-per-use / zero idle
cost, 5–10s cold start). **Replicate** = drop-in secondary (same async-queue shape, broader catalog, official-model
fixed pricing). **Self-host Wan 2.2 on DO** = dormant backend, only wins at sustained high volume (breakeven in §8).

### 2b. Aggregator gateways — the biggest architectural lever (provider-agnostic by construction)

| Gateway | Why it's the default | Async API shape | Auth | Price posture |
|---|---|---|---|---|
| **fal.ai** | One `FAL_KEY` fronts Kling 3.0, Veo 3.1/Lite, Seedance 2.0, Wan 2.6, LTX 2.0, Hunyuan, Hailuo, etc. Pay-per-use, **no idle cost / no minimums**, cold start 5–10s. Cheapest per-second of the aggregators. | `POST https://queue.fal.run/{model-id}` (optional `?fal_webhook=<url>`) → returns `{request_id, status_url, response_url}`; `GET …/requests/{id}/status`; `GET …/requests/{id}` for result. | `Authorization: Key <FAL_KEY>` | Kling 2.5 Turbo Pro **$0.07/s**, Kling 3.0 **~$0.029/s**, Veo 3.1 Lite **$0.05/s**, Veo 3.1 no-audio **$0.20/s** / w-audio **$0.40/s**, Wan 2.6 **~$0.05/s**. |
| **Replicate** | Same async-prediction shape, biggest catalog, "Official Models" give predictable per-output pricing; mature, production-proven. Slightly dearer (video **$0.07–$0.25/s**) + slower cold start (20–60s). | `POST https://api.replicate.com/v1/predictions` (`webhook` field) → returns prediction `{id, urls.get}`; `GET https://api.replicate.com/v1/predictions/{id}`. | `Authorization: Bearer <REPLICATE_API_TOKEN>` | Video **$0.07–$0.25/s**; also raw GPU-second billing (H100 **$0.001525/s**) for custom models. |

**Why an aggregator and not direct vendor APIs as the default:** identical to why `whatsapp.py` defaults to a generic
BSP switch — **one credential, one request shape, swap the model with a config string, no idle infra.** fal/Replicate
absorb every vendor's auth quirk so our module stays a thin, stable interface. This is the cost-optimal choice at
the bursty, low-to-medium volume of ad-creative generation (you render a handful of variants per campaign, not a
firehose).

### 2c. Direct vendor APIs (optional backends, dormant — for when a specific model/feature is required)

| Vendor | API reality (verified) | Auth | Note |
|---|---|---|---|
| **Luma** (Dream Machine / Ray3) | **Real REST API.** Bearer token `luma-xxxx` from the Luma dashboard. Text→video, image→video, video-extend. **Full API access requires a Pro plan** (Standard is limited). | `Authorization: Bearer luma-…` | Good motion/cinematics; keep as an optional direct backend. |
| **Higgsfield** | **Has an API** (image→video, text→motion; aimed at social/marketing creators). API key via header. Thinner docs than fal/Luma. | header API key | Optional; the brief named it. Prefer reaching Higgsfield-style models **via fal** when present, to avoid a second key. |
| **Runway / Kling / Veo / Sora / Seedance / Hailuo** | All exposed **through fal and/or Replicate** in 2026 — no separate integration needed. Reach them by setting the model-id string on the aggregator backend. | (aggregator key) | This is exactly why the aggregator is the default: these become one-line config, not new modules. |

### 2d. Self-host open-weight models on a DO GPU droplet (dormant backend) — and THE LICENSE TRAP

| Model | Maintained 2026? | **Commercial license** | Verdict for an *ad-creative* product |
|---|---|---|---|
| **Wan 2.2 / 2.7** (Alibaba) | **Yes** — actively released (Wan 2.7 suite, early Apr 2026). | **Apache-2.0** — clean commercial use, no territory/MAU limit. | **CHOSEN self-host model.** Safe for paid ad output worldwide. |
| **CogVideoX** (Zhipu) | Yes | **Apache-2.0** — clean. | Safe alternate. |
| **LTX-Video** (Lightricks) | Yes (LTX 2.0) | **Apache-2.0** — clean; fastest/cheapest to run. | Safe alternate; good for speed. |
| **Mochi** (Genmo) | Yes | **Apache-2.0** — clean. | Safe alternate. |
| **HunyuanVideo** (Tencent) | Yes | ⚠️ **RESTRICTED. Output use is PROHIBITED in the EU, UK, and South Korea** (license "Territory" excludes them), and a **>100M MAU** ceiling needs a separate Tencent license. | **DO NOT self-host for our ad output.** This is a hard gate for a product that sells/serves the generated ads. *Hunyuan is fine only via fal/Replicate, where the gateway holds the license relationship — and even then, flag the geo risk.* |

> **License rule baked into the module:** the self-host backend defaults to **Wan 2.2 (Apache-2.0)**. A
> `VIDEO_SELFHOST_MODEL` other than the Apache-2.0 allowlist (`wan*`, `cogvideox*`, `ltx*`, `mochi*`) is **refused**
> with `{"status":"error:license_gate"}` — the module will not silently render commercial ad output under a
> territory/MAU-restricted license.

### 2e. DO GPU droplet economics (verified, for the self-host breakeven in §8)

DigitalOcean GPU Droplets, simple per-hour, no commitment: **L40S $1.57/GPU-hr**, **RTX 6000 Ada $1.57/hr**,
**single H100 $2.99/GPU-hr on-demand** ($1.99 with multi-month commit), **H200 $3.44/hr**, **RTX 4000 Ada $0.76/hr**.
GPU droplets typically require a **quota/access request** to DO before first launch (no self-serve for the big SKUs) —
the founder must request this; see creds list §9.

---

## 3. PROVIDER MATRIX (what the module's `_build_*` switch handles)

```
VIDEO_PROVIDER ∈ { fal | replicate | luma | higgsfield | selfhost | generic }   (default: "" → not_configured / no-op)
```

| provider | submit endpoint | auth header | poll/result | artifact field in result |
|---|---|---|---|---|
| `fal` | `POST https://queue.fal.run/{model}` (`?fal_webhook=`) | `Authorization: Key <FAL_KEY>` | `GET …/requests/{id}/status` → `…/requests/{id}` | `data.video.url` (model-dependent; resolver maps it) |
| `replicate` | `POST https://api.replicate.com/v1/predictions` (body `{version, input, webhook}`) | `Authorization: Bearer <REPLICATE_API_TOKEN>` | `GET https://api.replicate.com/v1/predictions/{id}` | `output` (URL or list) |
| `luma` | `POST https://api.lumalabs.ai/dream-machine/v1/generations` | `Authorization: Bearer luma-…` | `GET …/generations/{id}` | `assets.video` |
| `higgsfield` | `POST <HIGGSFIELD_API_URL>` | header API key | provider-specific | provider-specific |
| `selfhost` | `POST http://<DO_GPU_PRIVATE_IP>:<port>/generate` (our own FastAPI worker on the GPU box) | `Authorization: Bearer <VIDEO_SELFHOST_TOKEN>` | `GET …/jobs/{id}` | `video_url` (DO Spaces URL the worker writes) |
| `generic` | `POST <VIDEO_API_URL>` flat JSON `{prompt, image_url, params}` | `Authorization: Bearer <VIDEO_API_KEY>` | `GET <VIDEO_STATUS_URL>/{id}` | `video_url` |

The `generic` shape (mirroring `whatsapp.py`'s `generic` default) lets the founder point ANY future vendor at the
module by setting three env vars — no code change.

> **Endpoint-verification caveat (read before implementing §3):** only the **fal** queue shape was confirmed against
> live docs (`fal.ai/docs/model-endpoints/queue`, fetched 2026-06-09 — see References [6]). The Replicate
> (`/v1/predictions`), Luma (`/dream-machine/v1/generations`), and Higgsfield paths are from 2026 search results /
> recall and are **directionally correct but unconfirmed** — the build agent MUST verify the exact path, body schema,
> and result-field for each non-fal provider against that vendor's current docs at implementation time. The
> provider-agnostic `_build_*` switch makes this a localized, low-risk change.

---

## 4. FILES & PACKAGE LAYOUT (NEW — all under `droplet_work/automation/`)

```
droplet_work/automation/
  __init__.py
  video/
    __init__.py
    config.py          # env reads: VIDEO_PROVIDER, *_KEY/_TOKEN/_URL, model ids, SPACES_*, caps. is_configured()/which_provider()
    providers.py       # _build_submit(provider,brief) -> (url, headers, json); _parse_submit_resp(); _build_status(); _parse_result()->artifact_url|status
    client.py          # submit_video_job(brief)->dict ; poll_video_job(job)->dict ; async variants. The httpx try/except-wrapped POST/GET. NEVER raises.
    store.py           # JSON job store under VAR/video_jobs/<job_id>.json (mirrors WA_THREADS_DIR). create/read/update/list. _STORE_LOCK-safe.
    artifacts.py       # download finished video, push to DO Spaces (boto3 S3-compat); return public/signed URL. No-op if SPACES_* unset (keeps URL from provider).
    cost.py            # estimate_cost(brief)->Decimal (duration_s * per_second_rate[provider][model]); reserve()/settle()/refund() shims onto the wallet ledger.
    approval.py        # approval-gate state machine: a job over VIDEO_APPROVAL_THRESHOLD_USD parks in status "awaiting_approval" until approve_job()/reject_job().
    selfhost_worker.py # OPTIONAL FastAPI app that runs ON the DO GPU droplet (Wan 2.2 + ComfyUI/diffusers). NOT imported by caller.py. Deployed separately.
    schema.py          # dataclasses/TypedDicts: VideoBrief, VideoJob, JobStatus enum.
    tests/
      test_dormant.py        # OFFLINE acceptance test (§10) — the gate. No network.
      test_providers_shape.py # asserts each _build_submit() shape WITHOUT sending (golden-dict compare).
      fixtures/                # canned provider responses for parse tests.
```

**Nothing here is imported by `caller.py`/`agent.py` yet.** The orchestrator wires §6 endpoints later. Until then the
package is fully testable in isolation (§10).

---

## 5. DATA MODEL

### 5a. `VideoBrief` (input)
```python
@dataclass
class VideoBrief:
    tenant_id: str
    prompt: str                      # the ad copy / scene description
    image_url: str = ""              # optional image→video seed (product shot)
    duration_s: int = 6             # clip length; caps to VIDEO_MAX_DURATION_S
    aspect_ratio: str = "9:16"      # ad default = vertical; also "1:1","16:9"
    model: str = ""                 # override; else provider default model id
    provider: str = ""              # override; else VIDEO_PROVIDER
    resolution: str = "720p"
    extra: dict = field(default_factory=dict)   # passthrough provider params
```

### 5b. `VideoJob` (persisted record — `var/video_jobs/<job_id>.json`)
```python
{
  "job_id": "vj_<uuid4hex>",
  "tenant_id": "...",
  "provider": "fal",
  "model": "fal-ai/wan-2.6/text-to-video",
  "status": "queued|awaiting_approval|submitted|running|succeeded|failed|cancelled|not_configured",
  "external_id": "<request_id from provider>",
  "status_url": "...", "result_url": "...",
  "brief": { ...VideoBrief... },
  "estimated_cost_usd": "0.42",     # Decimal-as-string
  "hold_id": "<wallet hold id>",    # set when reserved; "" when dormant
  "artifact_url": "",               # final video URL (DO Spaces or provider CDN)
  "approval": {"required": true, "by": "", "at": "", "decision": ""},
  "attempts": 0, "error": "",
  "created_at": "...", "updated_at": "..."
}
```

### 5c. Status lifecycle
```
(submit) → estimate_cost → reserve hold
   → [cost > threshold] → awaiting_approval ──approve──┐
   → [cost ≤ threshold] ───────────────────────────────┤
                                                        ▼
                                       submitted → running → succeeded → settle hold → store artifact
                                                        │
                                                        └→ failed/cancelled → refund hold
   (no creds at submit) → not_configured (no hold, no spend, no raise)
```

---

## 6. ENDPOINTS (DESCRIBED ONLY — orchestrator wires into `caller.py` later; DO NOT edit caller.py now)

All mirror the WhatsApp endpoint conventions (`resolve_tenant`→`need_auth`/`can(t,"write")`→`_forbidden`; `_audit(...)`):

| Method + path | Role | Behavior |
|---|---|---|
| `POST /video/jobs` | write | Body: brief fields (Form, like `/whatsapp/send` `caller.py:2939`). Creates a `VideoJob`, estimates cost, reserves a hold; returns `{job_id, status, estimated_cost_usd, configured}`. If unconfigured → `200 {status:"not_configured"}`. |
| `GET /video/jobs` | read | List the caller-tenant's jobs (admin sees all), most-recent first (mirrors `/whatsapp/log` `caller.py:2967`). |
| `GET /video/jobs/{job_id}` | read | One job record (tenant-scoped). |
| `POST /video/jobs/{job_id}/approve` | **manager+** | Approve an `awaiting_approval` job → submits it to the provider. `_audit(..., "video.approve", ...)`. |
| `POST /video/jobs/{job_id}/reject` | manager+ | Reject → refund hold, status `cancelled`. |
| `POST /video/jobs/{job_id}/cancel` | write | Best-effort provider cancel + refund hold. |
| `POST /video/webhook` | **no auth** (provider-signed) | Provider callback (fal `fal_webhook` / Replicate `webhook`). Verify a shared-secret/signature (mirror `_verify_meta_signature` `caller.py:2992`). Update job → `succeeded/failed`, settle/refund, kick artifact pull. Always returns fast 200 (like `/whatsapp/inbound` `caller.py:3032`). |
| `GET /video/jobs/{job_id}/poll` | read | Server-side polls the provider status URL (fallback when no webhook). Idempotent. |

**The poll worker:** a lightweight async loop (the orchestrator may run it as a background task in `caller.py`'s
existing scheduler, OR as a small standalone `python -m automation.video.poller`) that walks `submitted/running` jobs
and calls `poll_video_job`. Webhook is preferred; poller is the dormant-safe fallback. **Neither is implemented in
caller.py by this spec.**

---

## 7. SPEND / APPROVAL / AUDIT GUARDRAILS (the dollar-heavy part)

1. **Estimate before spend.** `cost.estimate_cost(brief)` = `duration_s × rate[provider][model]` using a small static
   rate table (the §2b numbers) with a safety multiplier `VIDEO_COST_SAFETY=1.25`. Never submit without an estimate.
2. **Reserve → settle → refund (wallet firewall).** On submit, `cost.reserve(tenant_id, estimate)` places a **hold**
   via the wallet ledger specced in `design/credit-ledger-firewall.md` (tables `wallet_holds`/`wallet_transactions`).
   On `succeeded`, `settle()` converts the hold to a debit at the **actual** provider-billed amount (from the result
   payload when present, else the estimate). On `failed/cancelled`, `refund()` releases the hold. **Until that ledger
   is built, `cost.py` degrades to the existing `_charge_call`/`LEDGER_DIR` JSON ledger pattern** (`caller.py:1383`) —
   append-only itemized charge, decrement prepaid balance — so spend tracking works today and upgrades transparently.
3. **Per-tenant + per-day spend cap.** `VIDEO_DAILY_CAP_USD` (default e.g. 20) and `VIDEO_MONTHLY_CAP_USD`. A submit
   that would exceed the cap is refused with `{"status":"error:cap_exceeded"}` — money cannot run away.
4. **Human approval gate.** Any job with `estimated_cost_usd > VIDEO_APPROVAL_THRESHOLD_USD` (default e.g. 1.00) parks
   in `awaiting_approval` and is **not** submitted until a manager+ calls `/approve`. `VIDEO_AUTO_APPROVE=0` (default)
   forces approval for ALL jobs regardless of cost when the founder wants a hard manual gate.
5. **Audit every state change.** `_audit(request, t, "video.submit|video.approve|video.reject|video.succeeded",
   "video", job_id, channel="video", meta={"provider":…, "cost":…, "status":…})` — same call used by every mutating
   endpoint today. Provides the AI-decision/spend audit trail.
6. **Idempotency.** Submit accepts an optional `idempotency_key`; a repeat key returns the existing job (mirrors the
   wallet idempotency table) so a retried request never double-charges.

---

## 8. SELF-HOST: WHEN IT WINS (honest breakeven, not an assertion)

Self-host **does not** win by default. A DO **L40S at $1.57/hr** renders Wan-2.2 at roughly **1.5–3 min wall per
6s clip** (model/res-dependent) → effective **$0.04–$0.08 per clip in GPU time** *only when the GPU is busy*. But the
droplet bills **whether or not it's rendering**, so idle time is pure loss.

- **Hosted fal** (Wan 2.6 ~$0.05/s) ≈ **$0.30 per 6s clip**, **zero idle cost.**
- **Self-host L40S** ≈ **$1.57/hr ÷ clips-per-hour.** At 1.5 min/clip → ~40 clips/hr → **~$0.04/clip** *if you keep it
  full*; at 5 clips/hr it's **~$0.31/clip** — same as hosted but now you also own ops, cold-starts, and the quota
  request.

**Breakeven:** self-host beats fal only above **~30–40 rendered clips per GPU-hour sustained** (≈ continuous batch
load). Ad-creative volume is bursty (a few variants per campaign), so **hosted wins until there's a sustained queue.**
Therefore: ship hosted; keep `selfhost` a **dormant backend** with the Apache-2.0 Wan worker (`selfhost_worker.py`)
documented and a one-command DO deploy, flipped on only when telemetry shows a standing queue. This is the same
"compose first, self-host where it provably wins" rule used elsewhere in Famit.

---

## 9. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> Until ALL are blank the module is a no-op (`not_configured`). Provide **only fal.ai + DO Spaces** to go live cheaply;
> the rest are optional alternates. Nothing here is required for the offline acceptance test.

**TIER 1 — minimum to go live (hosted, cheapest path):**
| Env var | What it is | Where to get it |
|---|---|---|
| `VIDEO_PROVIDER=fal` | selects the fal backend | (set after key exists) |
| `FAL_KEY` | fal.ai API key | fal.ai → dashboard → API Keys. Add billing/credits. |
| `VIDEO_FAL_MODEL` | model id, e.g. `fal-ai/wan-2.6/text-to-video` (cheap, Apache) or `fal-ai/kling-video/v3` | fal model catalog |
| `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`, `SPACES_REGION`, `SPACES_ENDPOINT` | DO Spaces (S3-compatible) for storing finished MP4s | DO console → Spaces → create bucket + access keys |

**TIER 2 — optional alternate backends (only if you want them):**
| Env var | For |
|---|---|
| `REPLICATE_API_TOKEN` (+ `VIDEO_REPLICATE_MODEL`) | Replicate backend (`VIDEO_PROVIDER=replicate`). replicate.com → account → API tokens. |
| `LUMA_API_KEY` (`luma-…`, **Pro plan for full API**) | Luma direct backend. lumalabs.ai dashboard. |
| `HIGGSFIELD_API_KEY`, `HIGGSFIELD_API_URL` | Higgsfield direct backend. |
| `VIDEO_API_URL`, `VIDEO_API_KEY` | the `generic` catch-all for any future vendor. |

**TIER 3 — self-host (only when breakeven §8 is hit):**
| Item | What the founder must do |
|---|---|
| **DO GPU quota** | Request GPU-droplet access in the DO console / via support (not self-serve for L40S/H100). |
| `VIDEO_SELFHOST_URL`, `VIDEO_SELFHOST_TOKEN` | private IP + bearer of the `selfhost_worker.py` box. |
| `VIDEO_SELFHOST_MODEL` | must be on the Apache-2.0 allowlist (`wan*`/`cogvideox*`/`ltx*`/`mochi*`) — Hunyuan is **refused** for ad output (license §2d). |

**Guardrail knobs (have safe defaults; founder may tune):**
`VIDEO_APPROVAL_THRESHOLD_USD` (1.00), `VIDEO_AUTO_APPROVE` (0), `VIDEO_DAILY_CAP_USD` (20),
`VIDEO_MONTHLY_CAP_USD` (300), `VIDEO_MAX_DURATION_S` (10), `VIDEO_COST_SAFETY` (1.25),
`VIDEO_WEBHOOK_SECRET` (shared secret for `/video/webhook` signature).

---

## 10. OFFLINE ACCEPTANCE TEST (the gate — no creds, no network, no external calls)

`automation/video/tests/test_dormant.py` — must pass with **all env unset** and **no network**:

1. **Config gate:** `config.is_configured()` is `False` with no env; `which_provider()` is `""`.
2. **Dormant submit:** `client.submit_video_job(VideoBrief(tenant_id="t1", prompt="x"))` returns
   `{"status":"not_configured", ...}`, **does NOT raise**, places **no wallet hold**, writes **no** spend, and either
   writes no job record or writes one with status `not_configured`.
3. **Dormant poll:** `client.poll_video_job({...})` on a not_configured job returns gracefully, no raise.
4. **Provider-shape goldens (`test_providers_shape.py`):** for each provider, `providers._build_submit(provider,
   brief)` returns the exact `(url, headers, json)` matching a committed golden dict — asserting request shape
   **without sending anything**. (Same idea as verifying `whatsapp.py._build_body` per provider.)
5. **Parse goldens:** `providers._parse_result(canned_fixture)` extracts the right `artifact_url` / status from a
   saved fixture for fal & replicate — no live call.
6. **Guardrails:** `cost.estimate_cost` math is deterministic; a brief over `VIDEO_APPROVAL_THRESHOLD_USD` yields
   `approval.required=True`; a brief over `VIDEO_DAILY_CAP_USD` is refused. All pure-function, offline.
7. **License gate:** `selfhost` with `VIDEO_SELFHOST_MODEL=hunyuan-video` (and creds *mocked* present) returns
   `{"status":"error:license_gate"}` without sending.
8. **Never-raises invariant:** monkeypatch `httpx` POST to throw → every public function still returns a dict with
   `error:` status, never propagates. (Mirrors the `try/except Exception` in `whatsapp.py`.)

Run: `pytest droplet_work/automation/video/tests -q`. **Green with zero network = acceptance.** This is exactly how
"verifiable offline / no live external calls" is satisfied — the dormant no-op path is the testable contract.

---

## 11. HONEST REAL-vs-HYPE

- **Real:** fal/Replicate are genuine one-key gateways to every top 2026 video model; pay-per-use, no idle cost; the
  async-queue shape is stable and well-documented; Wan 2.2 is genuinely Apache-2.0 and production-usable; DO GPU
  droplets are real per-hour SKUs. These are safe to build on.
- **Hype / traps to resist:**
  - "**Self-host is free / cheaper**" — false at our volume; the GPU bills idle. Hosted wins until a sustained queue
    (§8). Don't lead with self-host.
  - "**Just use HunyuanVideo, it's open**" — **license trap**: output prohibited in EU/UK/South Korea + 100M-MAU
    ceiling. Not safe for self-hosted commercial ad output. Use Wan/CogVideoX/LTX instead.
  - "**Veo/Sora quality at $0.05/s**" — the cheap tiers (Veo Lite, Wan) are good for variants/drafts; flagship audio
    /4K tiers are **8–12× dearer** ($0.40–$0.60/s). The cost estimator + caps exist precisely because model choice
    swings spend by an order of magnitude.
  - "**It's instant**" — no; 30s–6min/clip. The whole module is async *because* of this. Anyone expecting a
    synchronous return is wrong.
  - **Audio/lipsync/consistency** across shots is still the weak spot of open models; for premium ad spots the hosted
    flagships (Veo 3.1 w/ audio, Kling 3.0) are worth the price — keep them one config-string away via the aggregator.

---

## 12. BUILD SEQUENCE (units a build agent ships, each crash-safe + offline-verifiable)

1. `schema.py` + `store.py` + `config.py` → unit test: create/read/list a job offline. ✅ commit.
2. `providers.py` `_build_submit`/`_parse_*` for `fal` + `generic` → `test_providers_shape.py` goldens. ✅ commit.
3. `client.py` `submit_video_job`/`poll_video_job` (httpx try/except, never-raises) + `test_dormant.py`. ✅ commit.
4. `cost.py` + `approval.py` (estimate/reserve/settle on the JSON-ledger fallback; caps; threshold) + tests. ✅ commit.
5. `artifacts.py` (DO Spaces push, no-op when `SPACES_*` unset). ✅ commit.
6. Add `replicate`, `luma`, `higgsfield`, `selfhost` provider shapes + license gate + goldens. ✅ commit.
7. `selfhost_worker.py` (Wan 2.2 + DO deploy doc) — **dormant**, not wired. ✅ commit.
8. Hand the §6 endpoint table to the orchestrator for `caller.py` wiring (DO NOT do it here).

> Every unit is green offline before the next starts. An interruption costs at most one unit. No edits to
> `caller.py`/`agent.py`. No git (orchestrator commits).

---

## 13. REFERENCES (sources, accessed 2026-06-09)

Load-bearing claims are anchored here. Primary sources preferred for licenses; blogs used only for price comparison.

1. **fal.ai video model catalog + per-second pricing** (Kling 3.0 ~$0.029/s, Veo 3.1 Lite $0.05/s, Wan 2.6 ~$0.05/s,
   pay-per-use/no idle, 5–10s cold start): https://fal.ai/pricing and https://fal.ai/learn/tools/ai-video-generators
2. **Cross-vendor per-second price comparison 2026** (Sora 2 / Veo 3.1 / Kling 3.0 / Runway costs):
   https://www.buildmvpfast.com/api-costs/ai-video and https://devtk.ai/en/blog/ai-video-generation-pricing-2026/
3. **Replicate video pricing + async-prediction model** ($0.07–$0.25/s video; H100 $0.001525/s; official models):
   https://replicate.com/pricing and https://replicate.com/collections/text-to-video
4. **Aggregator comparison (fal vs Replicate)**: https://www.teamday.ai/blog/ai-image-video-api-providers-comparison-2026
5. **Open-weight licenses — Apache-2.0 (Wan / CogVideoX / LTX-Video / Mochi)**:
   https://www.pixazo.ai/blog/best-open-source-ai-video-generation-models ;
   Wan 2.7 Apache-2.0 (Apr 2026): https://ponpon.ai/blog/wan-27-alibaba-open-source-video-model
6. **fal async queue API shape** (`POST queue.fal.run/{model}`, `?fal_webhook=`, `request_id`, status/result URLs,
   `Authorization: Key`): https://fal.ai/docs/model-endpoints/queue  ← *the one endpoint shape verified live.*
7. **HunyuanVideo LICENSE — EU/UK/South Korea output prohibition + 100M-MAU ceiling (the license trap, PRIMARY
   source)**: https://huggingface.co/tencent/HunyuanVideo/blob/main/LICENSE and
   https://deepwiki.com/Tencent/HunyuanVideo/5-license-and-legal (corroborated:
   https://news.ycombinator.com/item?id=43420870)
8. **Luma Dream Machine / Ray3 REST API** (Bearer `luma-…`, Pro plan for full API access):
   https://docs.lumalabs.ai/docs/api and https://docs.lumalabs.ai/docs/video-generation
9. **Higgsfield API** (image→video / text→motion; header API key) — *only a third-party directory source found, NOT
   Higgsfield's own docs; treat as unconfirmed*: https://www.pixazo.ai/models/higgsfield
10. **DigitalOcean GPU Droplet hourly pricing** (L40S $1.57/hr, H100 $2.99/hr on-demand / $1.99 committed, H200
    $3.44/hr, RTX 4000 Ada $0.76/hr; quota request typically required):
    https://www.digitalocean.com/pricing/gpu-droplets

---

## RED-TEAM FIXES (folded)

> Adversarial review pass, 2026-06-09. Every claim below was re-verified against primary/live sources or the cited
> local source files. **Verdict: GO** — the tools are real and active in 2026, the dormant-until-creds contract is
> non-breaking by construction (greenfield `automation/`, nothing imported by `caller.py`/`agent.py`), and the spend
> guardrails are real. The fixes below close gaps that would otherwise produce a wrong or unsafe build. They do **not**
> change the architecture; they correct contract names, one missing abuse vector, and a few stale numbers.

### RTF-1 (CRITICAL — the missing abuse vector): content/AUP abuse on a SHARED provider key
The spec treats **spend** as the only abuse vector. It is not. One `FAL_KEY` (or one `REPLICATE_API_TOKEN`) fronts
**every tenant**. A single tenant submitting a prompt/image that trips the provider's Acceptable Use Policy
(non-consensual deepfake, sexual content involving minors, real-person likeness, trademarked characters, election
/political manipulation) can get the **shared provider account suspended** — which kills video generation for *all*
tenants at once — and creates platform-level legal exposure. fal, Replicate, and Luma all publish AUPs and enforce
them at the account level. **Spend caps do nothing against this.** Fixes, baked into the module:
- **Pre-submit content screen** (`providers.py`/new `safety.py`): before any hold or network call, run the
  `brief.prompt` (and any `image_url`) through a cheap moderation gate. Default = a local denylist of high-risk terms
  + a pluggable `VIDEO_MODERATION_URL` hook (e.g. an LLM/classifier call) that is itself dormant-until-configured. A
  blocked brief returns `{"status":"error:content_blocked"}` **before** reserve/submit — no spend, no provider call,
  no raise. This is the same fail-closed posture as the license gate (§2d).
- **Key isolation / BYO-key as the structural fix:** support `VIDEO_FAL_KEY__<tenant_id>` override resolution in
  `config.py` so a high-volume/high-risk tenant can be moved to its own key, blast-radius-isolating an AUP strike.
  Document BYO-key as the recommended posture once multiple tenants generate at scale.
- **Already covered (note, don't rebuild):** `_audit(...)` (caller.py ~:713) records the submitting tenant + prompt
  + provider on `video.submit`, giving the traceability needed to identify and cut off an abusing tenant after the
  fact. The gap was *prevention*, now closed by the pre-submit screen.
- **Residual:** no moderation filter is perfect; a determined tenant can still craft a prompt that passes the screen
  yet trips the provider AUP. BYO-key isolation is the only true blast-radius cap. Accept and monitor.

### RTF-2 (CONTRACT BUG): `refund()` does not exist on the wallet firewall — it is `release()`
`cost.py` (§4) and §7.2 call `cost.refund()`. The firewall in `design/credit-ledger-firewall.md` exposes
`reserve() / settle() / release() / topup() / balance()` (see its `wallet.py` row; `refund` is a transaction *kind*
`hold_release`/`refund`, **not** a method). **Fix:** rename the failure-path shim to `release()` (keep `refund` only
as the ledger `kind` string). Everywhere this spec says "refund hold" read "release hold (`release()`)".

### RTF-3 (HONESTY GAP): the `_charge_call` fallback CANNOT do holds — degrade is weaker than §7.2 implies
§7.2 says spend degrades to the existing `_charge_call`/`LEDGER_DIR` pattern "until the wallet ledger is built." But
`_charge_call` (caller.py:1383) is a **one-shot, post-hoc** charge built for *calls* — it reads `duration_s`, computes
`_call_cost`, and decrements a prepaid balance **after** the work happens. It has **no reserve→settle→release**. So in
fallback mode the "money can't run away *before* spend" guarantee does **not** hold; protection degrades to
**daily/monthly cap + approval-gate + post-hoc charge** only. **Fix (pick one, state it):** (a) honestly document the
fallback as "cap + approval + post-hoc charge, no pre-spend hold," OR (b) ship a tiny JSON hold-store in `cost.py`
(`VAR/video_holds/<hold_id>.json`, `_STORE_LOCK`-guarded: write-on-reserve, delete-on-settle/release, sum-open-holds
checked against the cap) so the reserve→settle→release contract is real even before Postgres. **(b) is preferred** —
it is ~40 lines and makes the cap enforceable atomically-ish in the dormant/pre-Postgres era. Note the **TOCTOU**
caveat either way: in the JSON fallback, two concurrent submits can both pass the cap check before either writes its
hold; the Postgres firewall's atomic conditional UPDATE fixes this, the JSON store only mitigates it (`_STORE_LOCK`
around the read-check-write narrows but does not eliminate the window within a single process).

### RTF-4 (IMPLEMENTATION TRAP): webhook signature verification is per-provider, NOT one shared secret
§6/§7 say `/video/webhook` should "mirror `_verify_meta_signature`" using one `VIDEO_WEBHOOK_SECRET`. That is wrong
for the actual providers and a build agent will implement it insecurely:
- **fal** signs with **ED25519**; you verify against public keys fetched from the JWKS at
  `https://rest.alpha.fal.ai/.well-known/jwks.json` (cache ≤24h). Headers: `X-Fal-Webhook-Signature` (hex),
  `X-Fal-Webhook-Timestamp`, `X-Fal-Webhook-Request-Id`, `X-Fal-Webhook-User-Id`. There is **no shared secret** —
  it is asymmetric.
- **Replicate** uses **HMAC-SHA256** (Svix-style): HMAC the signed content with the base64 part of a `whsec_`-prefixed
  signing secret. Headers: `webhook-id`, `webhook-timestamp`, `webhook-signature`. Replay-guard via the timestamp.
- **Fix:** `providers.py` gets a per-provider `verify_webhook(provider, headers, body) -> bool`. Config becomes
  `VIDEO_FAL_JWKS_URL` (default the URL above) and `VIDEO_REPLICATE_WEBHOOK_SECRET` (`whsec_…`). Keep
  `VIDEO_WEBHOOK_SECRET` **only** for the `selfhost`/`generic` shared-secret shape. Verification is **fail-closed**:
  unverifiable signature → drop, never mutate the job. (Sources: fal & Replicate webhook docs, References [11][12].)

### RTF-5 (COST CORRECTNESS): the estimator assumes per-second, but Wan (and some models) bill flat-rate per generation
§7.1's `estimate_cost = duration_s × rate[provider][model]` is wrong for **flat-rate** models. Verified: on fal, **Wan
bills a flat ~$0.20–$0.40 per generation** (variant-dependent), not per second; Veo audio/4K tiers are also stepped,
not linear. `VIDEO_COST_SAFETY=1.25` will **not** cover a per-second formula applied to a flat-rate model at long
durations. **Fix:** the rate table carries a per-model **pricing mode**: `{"mode":"per_second","rate":0.05}` or
`{"mode":"per_generation","rate":0.30}` (and optionally `per_resolution_step`). `estimate_cost` switches on mode.
This keeps the cap/approval math honest across the catalog.

### RTF-6 (BUILD HYGIENE): cited `caller.py` line numbers have drifted — grep the SYMBOL, never the line
Spot-check found the cited line numbers stale (the *functions exist*, the numbers moved): e.g. `caller.py:2939` is now
`if topup is not None:` not the `/whatsapp/send` body; `:2967` is the `_wa_send(...)` call; `:2992` is
`q = request.query_params` not `_verify_meta_signature`; `:3032` is interactive-message parsing not `/whatsapp/inbound`.
The load-bearing symbols verified correct: `is_configured()`/`_build_body()` in `whatsapp.py` (:107/:146,
`not_configured` + never-raises documented), `_charge_call` (caller.py:1383), `resolve_tenant`/`need_auth`/`can`/
`_audit` (:371/:403/:608/:713), `VAR`/`_read`/`_write` (:108/:444/:450). **Fix:** the build agent MUST locate every
seam by `grep`-ing the function/route name, and treat all cited line numbers in this spec as approximate hints only.

### RTF-7 (STALE NUMBERS / NAMING — note-and-move-on, no decision changes)
- **DO H100** is now **~$3.39/GPU-hr** on-demand (was $2.99 when first cited). The self-host **breakeven (§8) uses the
  L40S at $1.57/hr, which is re-confirmed**, so no decision changes — but correct the H100 figure if reproduced.
- **Wan version drift:** the live open releases are **Wan 2.5 / 2.7**; "Wan 2.6" is used loosely in §2/§5. The example
  model id `fal-ai/wan-2.6/text-to-video` **may not resolve** — the build agent must pick the exact current model id
  from fal's catalog at implementation time (the provider-agnostic switch makes this a one-string change).
- **Higgsfield is MORE real than §2c admits (safe direction):** beyond the third-party directory, Higgsfield ships a
  first-party API (`cloud.higgsfield.ai`) and an official Python SDK (`higgsfield-ai/higgsfield-client`), header API
  key. Still optional; prefer reaching it via fal when present to avoid a second key. No change to the design, just a
  confidence upgrade.

### Net effect on the build
All seven are localized: RTF-1 adds a fail-closed `safety.py` screen + a tenant-key override (one new small file +
config), RTF-2 is a rename, RTF-3 is ~40 lines of JSON hold-store (or one honest sentence), RTF-4 is a per-provider
`verify_webhook` (the provider-agnostic switch already isolates it), RTF-5 is a pricing-mode field on the rate table,
RTF-6/7 are notes. **None touch `caller.py`/`agent.py`, none break the dormant contract, all remain offline-testable**
(add cases to §10: content-blocked-before-spend; pricing-mode estimator; per-provider webhook verify with canned
headers; release()-not-refund on the failure path).

### Updated references (added by this pass)
11. **fal webhook signature verification — ED25519 + JWKS** (`X-Fal-Webhook-*` headers, JWKS at
    `rest.alpha.fal.ai/.well-known/jwks.json`): https://docs.fal.ai/model-apis/model-endpoints/webhooks
12. **Replicate webhook verification — HMAC-SHA256, `whsec_` signing secret, `webhook-*` headers**:
    https://replicate.com/docs/topics/webhooks/verify-webhook
13. **Replicate async prediction API confirmed live** (`POST /v1/predictions`, `webhook` field, `Authorization:
    Bearer`, `urls.get` poll): https://replicate.com/docs/topics/predictions/create-a-prediction
14. **Wan flat-rate-per-generation pricing on fal (~$0.20–$0.40/gen, not strictly per-second)** + fal pay-per-use/no
    idle re-confirmed 2026: https://fal.ai/pricing
15. **Higgsfield first-party API + official SDK** (`cloud.higgsfield.ai`, `higgsfield-ai/higgsfield-client`):
    https://cloud.higgsfield.ai/ and https://github.com/higgsfield-ai/higgsfield-client
16. **credit-ledger-firewall local design — `reserve()/settle()/release()` (NOT `refund()`); `wallet_holds`/
    `wallet_transactions`/`wallet_idempotency`; PG-degrade no-op**: `design/credit-ledger-firewall.md`
