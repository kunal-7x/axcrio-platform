# infra/ — local dev stack + deploy placeholders

## docker-compose.dev.yml — the 6 backbone dependencies
| service | image (pinned) | host ports | role |
|---------|----------------|-----------|------|
| postgres | `postgres:16.4-alpine` | 5432 | OLTP, schema-per-service, RLS (§5.1) |
| redpanda | `redpandadata/redpanda:v24.2.7` | 9092 (kafka), 8081 (schema-registry), 8082, 9644 | event bus (Kafka API) + JSON-Schema registry (§6) |
| redpanda-console | `redpandadata/console:v2.7.2` | 8088 | topics + schema UI |
| redis | `redis:7.4-alpine` | 6379 | cache / locks / rate buckets (§5.3) |
| clickhouse | `clickhouse/clickhouse-server:24.8` | 8123 (http), 9000 (native) | analytics warehouse (§8.5) |
| temporal | `temporalio/auto-setup:1.25.1` | 7233 | durable workflows (§7.8) — uses the postgres above |
| temporal-ui | `temporalio/ui:2.31.2` | 8233 | workflow UI |
| minio | `minio/minio` | 9002 (s3), 9001 (console) | object store / DAM assets (§4) |

```bash
pnpm infra:up      # docker compose -f infra/docker-compose.dev.yml up -d
pnpm infra:down
docker compose -f infra/docker-compose.dev.yml config   # static-validate without booting
```

Copy [`.env.example`](./.env.example) → `.env` (consumed by `packages/config`, zod-validated).

## ⚠ BOX REQUIRED — honest runtime note (D8)
This stack is **written + statically validated as files**, but it is **not booted on the dev laptop**:
the machine is too small to run all six containers comfortably and the DigitalOcean droplet quota is
**3/3 full**. Production therefore needs one of:
1. a new/bigger box (or the DO limit raised), or
2. **managed services** — managed Postgres + ClickHouse Cloud + a Kafka-API-compatible managed bus +
   **Temporal Cloud** — which sidesteps the droplet wall entirely (recommended; see
   `docs/architecture-phase0.md` "PROD reuse-vs-new").

Port note: ClickHouse native already owns host `9000`, so MinIO's S3 API is mapped to host `9002`.

## terraform/ and helm/
Placeholders for the production path (§4 Docker+K8s or Fly/ECS + Terraform). Empty in Phase 0;
the dev compose file is the single source of "what the platform depends on" until then.
