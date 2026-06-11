# @growth-os/metering

Shared per-tenant usage meters → `credit.consumed` (P10 observable, §7.5 billing). Phase-0 = the
meter vocabulary (`MeterKind`, `MeterEvent`) + a `MeterRecorder` port with a console default.
All amounts are INR **paise** integers (P4, mirrors the live wallet). Concrete bus/ClickHouse
recorder lands with billing + the LLM gateway.
