# tools/seed

Dev + Tenant-Zero seed data. Phase-0 placeholder. The key seed (later phase) is the **Origin
Connection** for the live Famit/Axcrio platform: an `integration-hub` connection of
`provider:origin` with an `ORIGIN_SERVICE_TOKEN`, so the live caller.py can PUSH
campaign.requested/call.completed/wa.* and PULL reports (D4, §3 of architecture-phase0.md).
Tenant is resolved from the token, never the body (P6).
