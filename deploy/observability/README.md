# Haptica Observability (Phase 3)

A dedicated droplet running the observability backends, surfaced **white-labeled** inside
Haptica (the operator never sees SigNoz/Grafana/Prometheus branding — the Haptica backend
queries them server-side and renders native, core-design-system views).

**Architecture**
- **SigNoz** — distributed traces + logs + application metrics (apps export via OTLP).
- **Prometheus** — infra/host/container metrics (scrapes node-exporter + cadvisor on both boxes
  and the Haptica backend `/metrics`).
- **Grafana** — operator dashboards over Prometheus (+ optionally SigNoz's ClickHouse).
- Everything runs on the **`haptica-observability`** droplet. The droplet firewall (UFW, set by
  the provisioning cloud-init) lets **only haptica-prod** reach the telemetry/query ports, so the
  stack is private by construction. Apps push telemetry **out** to it; Haptica's backend reads
  **back** from it — no public exposure.

---

## Step 1 — Provision the droplet (YOU run this)

```
! python3 "$(pwd)/infra/provision-observability-droplet.py"
```
Idempotent. It prints `OBS_DROPLET_IP`. Docker installs via cloud-init (~2–3 min). Hand the IP
back to Claude.

## Step 2 — Deploy the stack (Claude, on the droplet)

SigNoz (its own tested compose, pinned):
```
git clone -b main --depth 1 https://github.com/SigNoz/signoz.git /opt/signoz
cd /opt/signoz/deploy/docker && docker compose up -d        # OTLP collector on :4317/:4318
```

Metrics half (this folder, rsynced to the droplet):
```
mkdir -p /opt/obs && rsync -a deploy/observability/ root@<OBS_IP>:/opt/obs/
ssh root@<OBS_IP> 'cd /opt/obs && cp .env.obs.example .env.obs   # set GRAFANA_ADMIN_PASSWORD
                   docker compose --env-file .env.obs up -d'
```

## Step 3 — Wire haptica-prod telemetry (Claude)

1. **Apps → SigNoz (traces/logs/app-metrics).** In `deploy/.env.deploy` set:
   ```
   OTEL_EXPORTER_OTLP_ENDPOINT=http://<OBS_IP>:4317
   OTEL_SERVICE_NAME=haptica-backend      # worker overrides to haptica-agent in its compose
   ```
   Rebuild `backend` + `worker`. The OTel instrumentation is **dormant until this is set**, so
   prod is byte-identical before wiring. (The instrumentation lives in `caller.py`/`agent.py`,
   guarded; see `deploy/requirements.backend.txt` for the OTel deps.)

2. **Prometheus scraping of haptica-prod.** Add node-exporter + cadvisor to the prod box and
   expose the backend `/metrics` + exporters to the **obs droplet IP only** (DO firewall
   `haptica-fw`: allow obs IP → tcp 8091,9100,8085). Targets are pre-listed in `prometheus.yml`.

## Step 4 — White-label surfacing in Haptica (Claude)

A super-admin **"Performance"** page (core design system, no vendor names) + a backend proxy
(`/admin/metrics/query`, super-admin-gated) that queries the Prometheus HTTP API (and SigNoz's
query API for error-rate/trace summaries) over the private path, rendered as native charts.

---

## Security / white-label invariants
- The obs droplet's UFW allows **only haptica-prod** to the telemetry/query ports; SSH is the
  only thing open to the world. SigNoz/Grafana UIs are never publicly reachable.
- Grafana admin password comes from `.env.obs` (never committed). Sign-up disabled.
- Haptica clients only ever see the native Haptica views — the vendor systems are an
  implementation detail behind the operator's private surface.
