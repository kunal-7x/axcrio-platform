# infra/terraform — production IaC (placeholder)

Provisions the production backbone (§4): managed Postgres, ClickHouse, the Kafka-API bus, Temporal
(Cloud or self-hosted), Redis, object store, and the K8s/Fly/ECS runtime, all in `ap-south-1`
(Mumbai, data-residency v1, §5.1). Empty in Phase 0 — the dev compose stack is authoritative until
the production box / managed-services decision is made (see infra/README.md).
