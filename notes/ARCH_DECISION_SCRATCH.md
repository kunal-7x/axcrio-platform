# Arch decision scratch (crash-safe; answer is returned as agent text, not this file)

VERDICT: Service-extractable MODULAR MONOLITH. Confirms prior STRANGLE & EVOLVE.
Decisive lens: AI-agent operability w/ NO human SRE.

Codebase reality:
- caller.py = 3422 lines, ~60 routes on single @app FastAPI, shared in-RAM state,
  one _STORE_LOCK (asyncio.Lock) serializing JSON writes. True monolith.
- agent.py (874) = LiveKit voice worker ALREADY separate service.
- Hatchet (durable orch) + Postgres strangler mid-flight = async plane being extracted.
- orchestration-hatchet.md §0.3/0.4 already documents the EXACT distributed hazards
  (asyncio.Lock doesn't span processes; global CALLS/LEADS diverge across processes;
  JSON corruption / lost updates) — i.e. the monolith's hidden microservice tax is real
  and already biting just from adding ONE worker process.

Steelman that bites (advisor): physical split lets multiple agents work parallel w/o
lost-write collisions ("one agent per file, ever"). REBUTTAL = parallelism comes from
CODE modularity (packages/Packwerk-style boundaries), NOT network/process separation.
Microservices conflate the two; only the first is needed; the second is pure debug tax
an SRE-less agent can least afford. CORE FINDING.

Evidence (verified, not recalled):
- Prime Video 2023: micro/serverless -> monolith, >90% cost cut (Step Functions per-transition).
- Segment "Goodbye Microservices" 2018: complexity exploded, defect rate up, went back.
- CNCF 2025 survey: ~42% consolidated services back; drivers = debug complexity, ops overhead, net latency.
- Fowler MonolithFirst / MicroservicePremium: premium = exactly the distributed tax; build monolith first.
- Shopify majestic/modular monolith: 173B reqs / 284M rpm Black Friday 2024, horizontal scale + Packwerk. $500M-scale w/o micro.
- AI-SRE literature 2025-26: nascent, monitors the agents themselves; "operational complexity not model capability is the blocker." Thin evidence = the finding.

Scale-triggers for extraction (ALL must hold): divergent load profile (GPU media/video/ads = real candidate) AND clean data boundary (no shared txn w/ core) AND independent deploy cadence. Tie each to a metric.

STATUS: research done, writing final answer.
