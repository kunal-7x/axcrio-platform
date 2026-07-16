"""credits/ — Haptica credit-wallet + payment infrastructure.

A thin, pluggable billing layer that sits ON TOP of the existing wallet / billing.json /
cost_ledger primitives in caller.py. It introduces ONE customer-facing unit — the **credit** —
and a transparent **service costing matrix** mapping every billable Haptica service to a credit
price (provider cost basis + platform margin).

Design goals (per the founder's spec):
  • DEEP integration — every service tracks + consumes credits through ONE engine.
  • PLUGGABLE — the BillingEngine ABC has a LocalCreditEngine (default, ships today on the
    existing JSON/Postgres wallet) and a FlexpriceEngine (REST adapter, flip on with
    BILLING_ENGINE=flexprice once the FlexPrice stack is provisioned). No migration gamble.
  • DORMANT-SAFE — absent Postgres wallet / unconfigured payment gateway / missing FlexPrice
    all degrade to a clean, non-breaking state. A credits failure NEVER breaks a call.

Public surface:
  get_engine()                  -> the active BillingEngine (Local or Flexprice)
  pricing.matrix(var_dir)       -> the costing matrix payload
  router.router / router.wire   -> the FastAPI APIRouter mounted by caller.py at /credits
"""
from __future__ import annotations

from .engine import get_engine, BillingEngine, LocalCreditEngine  # noqa: F401

__all__ = ["get_engine", "BillingEngine", "LocalCreditEngine"]
