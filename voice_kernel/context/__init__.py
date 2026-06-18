"""voice_kernel.context — W3 campaign-context subsystem.

The DUAL-LAYER campaign compiler + Campaign Understanding Engine + the concrete
ContextEngine / VendorScriptEngine implementations that fix the two Founder
complaints this wave targets:

  (a) VENDOR SCRIPT IGNORED  -> VendorScriptEngineImpl makes the vendor script the
      AUTHORITATIVE stage-by-stage blueprint, overriding the default flow when
      present (greet→confirm→intro→reason→qualify→pitch→objections→close), with
      dynamic {{variables}}, falling back to the default framework when absent,
      and injection-fenced (script can never override platform safety).

  (b) CAMPAIGN BRIEF LOSSY-COMPRESSED -> compile_campaign is RETRIEVAL-OVER-
      TRUNCATION: the FULL raw brief is preserved verbatim (fenced CAMPAIGN_BRIEF)
      + structured metadata is extracted + a compact CampaignCard is compiled
      using the H13 lossless fields (full_product_summary / full_usps / overflow
      flags). The model behaves like it READ the whole brief.

All public symbols here are DISJOINT from the live agent — zero droplet_work
imports (the kernel isolation guarantee).

Wire into the kernel:

    from voice_kernel import build_kernel, KernelConfig
    from voice_kernel.context import (
        compile_campaign, ContextEngineImpl, VendorScriptEngineImpl,
    )

    compiled = compile_campaign(tenant_id=t, campaign_id=c, brief=brief, fields=f)
    vs = VendorScriptEngineImpl(); vs.register(c, raw_script, variables=vars)
    ce = ContextEngineImpl({c: compiled}, vendor_script=vs, safety_rules=SHARED_RULES)
    kernel = build_kernel(KernelConfig(), context=ce, vendor_script=vs)
"""
from __future__ import annotations

from .campaign_compiler import (
    CompiledCampaign,
    Distiller,
    compile_campaign,
)
from .context_engine import ContextEngineImpl
from .text_hygiene import defang_fences, normalize, sanitize
from .understanding import CampaignUnderstanding, classify
from .vendor_script import (
    CompiledScript,
    VendorScriptEngineImpl,
    compile_script,
    parse_script,
    render_vars,
)

__all__ = [
    # compiler (dual-layer ingestion)
    "compile_campaign",
    "CompiledCampaign",
    "Distiller",
    # understanding engine
    "classify",
    "CampaignUnderstanding",
    # context engine impl
    "ContextEngineImpl",
    # vendor script engine impl
    "VendorScriptEngineImpl",
    "CompiledScript",
    "compile_script",
    "parse_script",
    "render_vars",
    # text hygiene
    "sanitize",
    "normalize",
    "defang_fences",
]
