#!/usr/bin/env node
/**
 * Phase-0 scaffold helper: create README placeholders for every service/agent/app deployable
 * named in BUILD-SPEC §20, grouped by plane (§3). Idempotent: never overwrites an existing file
 * (so the live `services/core` work and any other in-flight agent's files are untouched).
 *
 *   node tools/scaffold/make-placeholders.mjs
 *
 * This does NOT create service code — only the directory + a README that records the service's
 * §3 purpose, what it OWNS, what it emits/consumes, and its build phase. Contracts-first (P1):
 * code only lands once the service's OpenAPI/AsyncAPI contract exists in /contracts.
 */

import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** [dir, name, plane, phase, purpose, owns, emits, consumes, reuse?] */
const SERVICES = [
  // CORE (Phase 0) — `core` itself is owned by the core agent; skip it here.
  ['services/billing', 'billing', 'CORE', 'P1', 'Credit wallets, usage meters, plans, INR+GST invoices, Razorpay/Stripe webhooks (§7.5).', 'wallets, meters, plans, invoices', 'credit.consumed (sink), invoice.*', 'credit.consumed'],
  // DATA & SIGNALS (Phase 1)
  ['services/ingestion', 'ingestion', 'DATA', 'P1', 'One hardened front door for ALL inbound webhooks; verify sig -> persist raw -> normalize -> emit canonical event (§8.2).', 'webhooks_raw, verify tokens, normalizers', 'lead.captured, wa.message.received, call.completed, sale.recorded', '(external webhooks: Meta leadgen, WABA, Razorpay, origin)'],
  ['services/tracking', 'tracking', 'DATA', 'P1', '1P measurement: pixel, click-ID capture (fbclid/gclid/wbraid), UTM canon, session stitching, server-side tag (§8.1).', 'pixel endpoint, sessions, click-ID store', 'lead.captured (mints correlation_id), page.view', '—'],
  ['services/identity', 'identity', 'DATA', 'P1', 'One person_id per human across phone/wa_id/email/click-IDs/CRM; deterministic merge; DPDP erasure entry (§8.3).', 'persons, identifiers, merges, journey<->person map', 'identity.resolved (re-keys correlation_id)', 'lead.captured, call.completed, wa.message.*'],
  ['services/signals', 'signals', 'DATA', 'P1', '★FLAGSHIP (§11): ground-truth outcomes -> CAPI/Enhanced-Conversions with value=lead_score; dedup, EMQ reports.', 'event-mapping config, dispatch log, dedup keys, EMQ', 'signal.dispatched', 'lead.scored, booking.*, sale.recorded, call.outcome'],
  ['services/warehouse-api', 'warehouse-api', 'DATA', 'P2', 'ClickHouse read API + the SEMANTIC METRICS LAYER (CPL, CPqL=NORTH STAR, ROAS...). One metric definition everywhere (§8.5).', 'metrics layer, ad_metrics_4h, journeys, spend_daily', 'benchmark.updated (rollups)', 'ad.metrics.snapshot, all events (mirror)'],
  ['services/attribution', 'attribution', 'DATA', 'P4', 'Deterministic journey attribution + incrementality (geo-holdout, MMM-lite). Never present platform ROAS as truth (§8.6).', 'journey attribution, holdout config', 'insight.discovered (lift)', 'journeys, spend_daily'],
  ['services/benchmarks', 'benchmarks', 'DATA', 'P3', 'Anonymized cross-tenant CPL/CPqL/CTR/CVR by industry×geo×objective; k-anon (cells>=8) + noise (§8.7, moat 4).', 'benchmark cells, cohort priors', 'benchmark.updated', 'creative_dna_perf (aggregated)'],
  // ACTIVATION (Phase 1)
  ['services/campaign-compiler', 'campaign-compiler', 'ACTIVATION', 'P1', 'MediaPlan -> exact platform payloads (Meta MAPI v25+ baked, ⚠VERIFY-LIVE); budget floor; dry-run diff (§10.1).', 'platform payload builders, dry-run differ', 'campaign.compiled', 'strategy.compiled'],
  ['services/executor', 'executor', 'ACTIVATION', 'P1', 'The ONLY component allowed to call connector mutations; consumes SIGNED ActionPlans; Temporal LaunchSaga + compensation (§10.2, P4).', 'execution saga, platform-id writeback', 'action.executed, action.failed, action.rolled_back', 'action.plan.signed'],
  ['services/connector-meta', 'connector-meta', 'ACTIVATION', 'P1', 'Meta read (async insights, entity sync, learning-phase, Ad Library) + write (executor-only); SANDBOX mode (§10.3).', 'Meta API client, rate buckets, sandbox', 'ad.metrics.snapshot', 'executor mutation commands'],
  ['services/connector-google', 'connector-google', 'ACTIVATION', 'P3', 'Google Search/PMax + Enhanced Conversions + offline adjustments; test accounts; write = executor-only (§10.4).', 'Google Ads client, rate buckets', 'ad.metrics.snapshot', 'executor mutation commands'],
  ['services/audiences', 'audiences', 'ACTIVATION', 'P3', 'Customer-list (hashed, consent-checked), engagement + ★conversation-outcome audiences; exclusion hygiene (§10.5).', 'audience defs, hashed lists', 'audience.health', 'lead.scored, call.outcome, sale.recorded'],
  ['services/budget-governor', 'budget-governor', 'ACTIVATION', 'P1', 'Money safety as architecture: budget tree, hard caps, anomaly sentinel; every spend-changing plan needs a Governor stamp (§13, P4).', 'budget tree, caps, stamps, sentinel', 'budget.threshold.crossed, budget.anomaly.detected', 'ad.metrics.snapshot, action.plan.created'],
  ['services/experiments', 'experiments', 'ACTIVATION', 'P2', 'Gamma–Poisson posteriors per arm; Thompson allocation; learning-phase state machine (§12.1).', 'arms, posteriors, allocations', 'experiment.evaluated', 'ad.metrics.snapshot, lead.scored'],
  ['services/optimizer', 'optimizer', 'ACTIVATION', 'P1', 'Draft/Trash/Promote brain: guardrails G1–G6, promote, mitosis; every decision emits an Explanation (§12, P5).', 'decision engine, guardrail rules', 'optimization.decision, memory.updated', 'experiment.evaluated, ad.metrics.snapshot'],
  ['services/compliance-engine', 'compliance-engine', 'ACTIVATION', 'P1', 'Deterministic rule packs per platform/category/geo (RERA, finance, health) + LLM policy critic; pass|fix|block (§10.9).', 'rule packs, policy critic', 'creative.qa.evaluated (compliance verdict)', 'creative.generated, lp.published'],
  // CREATIVE (Phase 1)
  ['services/brand-kit', 'brand-kit', 'CREATIVE', 'P2', 'Logos, palette, self-hosted licensed fonts, tone axes, do/dont, locale variants; auto-extracted at onboarding; versioned (§15.1).', 'brand kit versions', 'brandkit.updated', 'onboarding crawl'],
  ['services/creative-studio', 'creative-studio', 'CREATIVE', 'P1', 'Statics PIPELINE (not a prompt): brief->layout->background->deterministic typography->brand->locale->DAM. REUSE the live AI Asset Service for gen-background (§15.2).', 'render pipeline, compositor', 'creative.generated', 'creative.requested (from CIB cells)'],
  ['services/video-studio', 'video-studio', 'CREATIVE', 'P2', 'Script->storyboard->scene sourcing->TTS VO->Remotion render->DAM (§15.3).', 'video render pipeline', 'creative.generated', 'creative.requested'],
  ['services/copy', 'copy', 'CREATIVE', 'P2', 'Copy generation along the diversity matrix (5 hooks x 1 body before 1 x 5); per-language register (§15).', 'copy variants', 'creative.generated (copy)', 'creative.requested'],
  ['services/creative-qa', 'creative-qa', 'CREATIVE', 'P1', 'Gate before launchable: spec/brand/compliance/pre-flight score + Entity-ID cluster-risk diversity rubric (block <8/10) (§15.4).', 'QA rubric, cluster detector', 'creative.qa.evaluated', 'creative.generated'],
  ['services/dam', 'dam', 'CREATIVE', 'P1', 'Asset + metadata store: Creative DNA tags, embeddings, perf rollup, fatigue, rights, approval state (§15.5).', 'assets, DNA, embeddings, rights', 'creative.approved, creative.fatigued', 'creative.qa.evaluated, optimization.decision'],
  ['services/landing-pages', 'landing-pages', 'CREATIVE', 'P2', 'Block-based SSR LPs; message-match per ad angle; forms->instant lead.captured; click-ID capture; CWV budget (§15.6).', 'LP blocks, message-match engine', 'lead.captured, lp.cta.click', 'creative.approved'],
  ['services/catalog', 'catalog', 'CREATIVE', 'P4', 'E-comm feed: Shopify/Woo -> normalized -> Meta catalog + Google Merchant Center; diagnostics; powers Advantage+ DPA/PMax (§15.7).', 'product feed, sync state', 'catalog.synced', 'shopify/woo webhooks'],
  // ENGAGEMENT (Phase 1) — REUSE the existing Famit stack via the Origin Connector
  ['services/whatsapp', 'whatsapp', 'ENGAGEMENT', 'P1', 'WABA template lifecycle + category-aware cost meter + window-aware sends. ADAPTER over the live whatsapp.py (§16.1, Tenant Zero).', 'template registry, send scheduler', 'wa.message.sent', 'wa.message.received, journey steps'],
  ['services/voice-adapter', 'voice-adapter', 'ENGAGEMENT', 'P1', 'Wraps the existing AI calling (LiveKit/Vobiz agent.py). Outbound trigger; consumes call.completed+transcript -> call.outcome; hot-lead SLA<=60s (§16.2).', 'call triggers, outcome mapper', 'call.outcome', 'call.completed, lead.scored(hot)'],
  ['services/journeys', 'journeys', 'ENGAGEMENT', 'P2', 'Declarative follow-up DSL (WA+voice); every step consent+cap-checked; the journey IS the signal factory (§16.3).', 'journey defs, step runner', 'wa.message.sent, call.initiated', 'lead.captured, wa.message.received, call.outcome'],
  ['services/crm-sync', 'crm-sync', 'ENGAGEMENT', 'P3', 'Bi-directional CRM field mapping (HubSpot/Zoho/Sheets/origin); ours is journey source of truth (§16.4).', 'field maps, sync log', 'crm.synced', 'lead.*, booking.*, sale.recorded'],
  // EXPERIENCE (Phase 1)
  ['services/approval-inbox', 'approval-inbox', 'EXPERIENCE', 'P1', 'Unified approval queue (dashboard + WhatsApp interactive Approve/Reject/Ask-why); Temporal signal on response; auto-escalate (§17.2).', 'approval queue, escalation timers', 'approval.granted, approval.denied', 'approval.requested'],
  ['services/ai-manager', 'ai-manager', 'EXPERIENCE', 'P3', 'Phone/WA command center — EXTENDS the live AI Manager. Commands -> SAME ActionPlan path (no side door); caller verify + read-back for money (§17.3).', 'NLU intent map, command grammar', 'action.plan.created', 'voice/WA inbound commands'],
  ['services/narrative-reports', 'narrative-reports', 'EXPERIENCE', 'P1', 'AI CMO Brief: daily WhatsApp voice note + card (spend, CPqL vs target, best/worst creative, 1 decision). Numbers from the metrics layer only (§17.4).', 'brief composer, schedule', 'report.briefed', 'metrics layer reads'],
  ['services/public-api', 'public-api', 'EXPERIENCE', 'P3', 'Everything the dashboard can do, the API can do; signed webhooks lead.*/optimization.decision/report.*. Sellable standalone (§17.5).', 'public REST, signed webhooks-out', 'webhook.delivered', '(all canonical events)'],
];

const AGENTS = [
  // INTELLIGENCE plane — Python/FastAPI (uv workspace)
  ['agents/llm-gateway', 'llm-gateway', 'P2', 'All model calls route here: tiers reasoning|bulk|cheap; structured-output validation vs /contracts/schemas; per-tenant token budgets->credit.consumed; cache; eval traces (§9.1, P8). NO raw SDK calls in services.'],
  ['agents/agent-orchestrator', 'agent-orchestrator', 'P2', 'Research War Room = Temporal workflow fanning out TYPED agent activities (12 roster agents) + a Synthesizer -> CIB (§9.2/§9.3).'],
  ['agents/knowledge', 'knowledge', 'P2', 'Vendor Brain / RAG: per-tenant corpus chunked+embedded (pgvector) with source+freshness; grounds all agents + answer bots (§9.4).'],
  ['agents/lead-scoring', 'lead-scoring', 'P1', '★ Feeds the flagship: score 0-100 + tier + reasons <=15min of any signal; v1 transparent heuristic; features ALWAYS stored (§9.5). Emits lead.scored.'],
  ['agents/insight-miner', 'insight-miner', 'P2', 'Conversation->Creative: nightly cluster WA inbound + call transcripts -> insight.discovered; auto-draft counter-objection briefs (§9.6).'],
  ['agents/memory', 'memory', 'P2', 'Learning Memory: per-tenant playbooks, creative_dna_perf (gene-level), negative_memory; write ONLY via memory.updated events; read via memory.read (§14).'],
  ['agents/forecast', 'forecast', 'P2', 'Forecast + War-Game: Monte-Carlo pre-launch from cohort posteriors -> min_viable_test, P(hit target), expected range; powers the reverse planner (§14.5).'],
  ['agents/strategy-compiler', 'strategy-compiler', 'P1', 'CIB -> MediaPlan (concrete campaign/adset/ad tree per platform). Deterministic given CIB+config; validated vs media_plan.schema.json (§9.9).'],
];

const APPS = [
  ['apps/dashboard', 'dashboard', 'P1', 'Next.js + shadcn operator console: connect -> wizard -> live feed (SSE) -> approvals -> report. Uses @growth-os/sdk against the public API (§17, the dashboard uses the API).'],
  ['apps/lp-runtime', 'lp-runtime', 'P2', 'Landing-page runtime: SSR block renderer for message-match LPs on our subdomain / vendor CNAME; the 1P pixel + instant lead.captured (§15.6).'],
];

function planeBlurb(plane) {
  return {
    CORE: 'CORE plane (§3). In Phase 0–1 the core deployable bundles gateway+tenants+integration-hub+ledger+flags+notify (see services/core); this service is a separate bounded context split out as scale demands.',
    DATA: 'DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.',
    ACTIVATION: 'ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).',
    CREATIVE: 'CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.',
    ENGAGEMENT: 'ENGAGEMENT plane (§3/§16). WRAPS the existing Famit stack (voice/WhatsApp) via adapters + the Origin Connector — do NOT rebuild.',
    EXPERIENCE: 'EXPERIENCE plane (§3/§17). Trust surfaces: autopilot levels, approvals, the AI-CMO brief, the public API.',
  }[plane];
}

function serviceReadme([_dir, name, plane, phase, purpose, owns, emits, consumes]) {
  return `# ${name} (service)

> Plane: **${plane}** · Build phase: **${phase}** · Runtime: NestJS (Fastify) · §20 deployable.
> ${planeBlurb(plane)}

## Purpose
${purpose}

## Owns (write model — P2: no other service reads this DB)
${owns}

## Events
- **Emits:** ${emits}
- **Consumes:** ${consumes}

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(\`contracts/openapi/${name}.yaml\`) + AsyncAPI 3 (\`contracts/asyncapi/${name}.yaml\`) contract exists.
Built in phase **${phase}** (§21). Do not add business logic before then.
`;
}

function agentReadme([_dir, name, phase, purpose]) {
  return `# ${name} (agent)

> Plane: **INTELLIGENCE** · Build phase: **${phase}** · Runtime: Python 3.12 / FastAPI · uv workspace member · §20 deployable.

## Purpose
${purpose}

## Status
**Phase-0 placeholder.** Contracts-first (P1). All structured outputs are validated against the
JSON Schemas in \`/contracts/schemas\`. All model calls go through the LLM Gateway (P8) — no raw
provider SDK calls. Built in phase **${phase}** (§21).

## uv workspace
A \`pyproject.toml\` (package \`growth_os_${name.replace(/-/g, '_')}\`) makes this a uv workspace member
(root \`pyproject.toml\` -> \`[tool.uv.workspace] members = ["agents/*"]\`). Code lands in its phase.
`;
}

function appReadme([_dir, name, phase, purpose]) {
  return `# ${name} (app)

> Build phase: **${phase}** · Runtime: Next.js · §20 deployable.

## Purpose
${purpose}

## Status
**Phase-0 placeholder.** Consumes \`@growth-os/sdk\` + \`@growth-os/ui\`. Built in phase **${phase}** (§21).
`;
}

function agentPyproject(name) {
  const pkg = `growth_os_${name.replace(/-/g, '_')}`;
  return `# ${name} — GROWTH OS intelligence-plane agent (uv workspace member). Phase-0 skeleton.
[project]
name = "${pkg}"
version = "0.0.0"
description = "GROWTH OS agent: ${name}. FastAPI service. Code lands in its build phase (§21)."
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn>=0.32.0",
  "pydantic>=2.9.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/${pkg}"]
`;
}

function agentInit(name) {
  return `"""GROWTH OS agent: ${name} (Phase-0 placeholder). FastAPI app lands in its build phase."""\n`;
}

let created = 0;
let skipped = 0;
function put(path, content) {
  const abs = join(ROOT, path);
  if (existsSync(abs)) {
    skipped++;
    return;
  }
  mkdirSync(dirname(abs), { recursive: true });
  writeFileSync(abs, content, 'utf8');
  created++;
}

for (const s of SERVICES) put(join(s[0], 'README.md'), serviceReadme(s));
for (const a of AGENTS) {
  put(join(a[0], 'README.md'), agentReadme(a));
  put(join(a[0], 'pyproject.toml'), agentPyproject(a[1]));
  const pkg = `growth_os_${a[1].replace(/-/g, '_')}`;
  put(join(a[0], 'src', pkg, '__init__.py'), agentInit(a[1]));
}
for (const ap of APPS) put(join(ap[0], 'README.md'), appReadme(ap));

console.log(`[scaffold] placeholders: ${created} created, ${skipped} already present (left untouched).`);
