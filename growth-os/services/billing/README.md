# billing (service)

> Plane: **CORE** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> CORE plane (§3). In Phase 0–1 the core deployable bundles gateway+tenants+integration-hub+ledger+flags+notify (see services/core); this service is a separate bounded context split out as scale demands.

## Purpose
Credit wallets, usage meters, plans, INR+GST invoices, Razorpay/Stripe webhooks (§7.5).

## Owns (write model — P2: no other service reads this DB)
wallets, meters, plans, invoices

## Events
- **Emits:** credit.consumed (sink), invoice.*
- **Consumes:** credit.consumed

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/billing.yaml`) + AsyncAPI 3 (`contracts/asyncapi/billing.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
