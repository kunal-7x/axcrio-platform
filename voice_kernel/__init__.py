"""voice_kernel — RealtimeVoiceKernel v2 (the layered context-packet kernel).

A NEW, git-TRACKED, additive, flag-gated (default-OFF) package. It NEVER imports
or modifies the live outbound agent (droplet_work/agent.py). When KERNEL_ENABLED
is OFF (the default) the existing prompt-assembly path is byte-for-byte
unchanged.

Public surface (the binding API for downstream workflows W2–W8):
  - ContextPacket + its 6 layers + TokenBudget          (packet.py)
  - the 9 service Protocols + their dataclasses          (contracts.py)
  - KernelConfig                                          (config.py)
  - RealtimeVoiceKernel + build_kernel + KernelServices   (kernel.py)
  - instructions_provider (the OFF-is-identity seam)       (adapter.py)
  - DialogueFSM + ModePolicy + policy_for                  (fsm.py)
  - prompt-cache helpers                                   (prompt_cache.py)
"""
from __future__ import annotations

__version__ = "0.1.0"

from .adapter import instructions_provider
from .config import KernelConfig
from .contracts import (
    BrainPackProvider,
    CallContext,
    ContextEngine,
    DialoguePolicy,
    Event,
    EventBus,
    KernelSession,
    MemoryService,
    ProviderChoice,
    ProviderRouter,
    RagRuntime,
    SpeechPlan,
    SpeechPlanner,
    TurnContext,
    VendorScriptEngine,
)
from .errors import (
    BudgetExceededError,
    ClampError,
    ConfigError,
    ContractViolationError,
    KernelError,
    TenantIdentityError,
)
from .fsm import DialogueFSM, ModePolicy, policy_for
from .kernel import KernelServices, RealtimeVoiceKernel, build_kernel
from .packet import (
    CampaignCard,
    ContextPacket,
    FencedText,
    IdentityLayer,
    IndustryLayer,
    LeadMemory,
    Lifecycle,
    ModeLayer,
    Objection,
    PacketMeta,
    RagSnippet,
    SourceTrust,
    Stage,
    TokenBudget,
    TurnLayer,
    UseCase,
    fence,
)
from .prompt_cache import CacheSplit, cache_breakpoint, is_cacheable_model, split_for_cache

__all__ = [
    "__version__",
    # packet
    "ContextPacket",
    "PacketMeta",
    "IdentityLayer",
    "ModeLayer",
    "IndustryLayer",
    "CampaignCard",
    "Objection",
    "LeadMemory",
    "RagSnippet",
    "TurnLayer",
    "TokenBudget",
    "UseCase",
    "Lifecycle",
    "Stage",
    # trust boundary (C3)
    "SourceTrust",
    "FencedText",
    "fence",
    # contracts
    "ContextEngine",
    "VendorScriptEngine",
    "BrainPackProvider",
    "RagRuntime",
    "SpeechPlanner",
    "ProviderRouter",
    "MemoryService",
    "EventBus",
    "DialoguePolicy",
    "CallContext",
    "KernelSession",
    "TurnContext",
    "SpeechPlan",
    "ProviderChoice",
    "Event",
    # config
    "KernelConfig",
    # kernel
    "RealtimeVoiceKernel",
    "KernelServices",
    "build_kernel",
    # adapter
    "instructions_provider",
    # fsm
    "DialogueFSM",
    "ModePolicy",
    "policy_for",
    # prompt cache
    "CacheSplit",
    "cache_breakpoint",
    "is_cacheable_model",
    "split_for_cache",
    # errors
    "KernelError",
    "BudgetExceededError",
    "ClampError",
    "ContractViolationError",
    "ConfigError",
    "TenantIdentityError",
]
