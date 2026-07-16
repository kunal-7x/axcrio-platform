-- ElevateX V2-W4 — seed the _global "reasoning_model" provider def (founder decision #2).
--
-- This is the VAULT CONNECTION TYPE behind the litellm gateway (ads_engine/llm_gateway.py).
-- A vendor READS this _global def (RLS read-share) and adds their OWN key against it (creating a
-- per-tenant provider_credentials row) — exactly the same _global pattern as the ad-gen models.
-- The blob a tenant stores (AES-256-GCM, AAD-bound) carries:
--     { "provider": "openrouter|groq|anthropic|openai|sarvam",
--       "model":    "<selected model id>",
--       "api_key":  "<the tenant's key>",
--       "monthly_cap_minor": <optional paise cap>,
--       "base_url": "<optional override>" }
--
-- named_provider = 'reasoning_model' is the channel-accurate resolver key
-- (vault_adapter._CHANNEL_NAMED["reasoning"] = "reasoning_model"); capability 'reasoning'.
-- ONE key -> ANY model when provider=openrouter; or a direct provider key + selected model.
--
-- IDEMPOTENT: re-running is a no-op (UNIQUE (tenant_id, slug) + ON CONFLICT DO NOTHING).
-- Run as the super-admin / migration role (the _global write-lock blocks tenant inserts).

INSERT INTO provider_definitions
    (tenant_id, slug, display_name, provider_type, capabilities, base_url,
     auth_scheme, auth_header_name, auth_value_tmpl, transform_type, named_provider,
     model_default, cost_unit, is_enabled, is_platform_default, created_by)
VALUES
    ('_global', 'reasoning-model', 'Reasoning Model (BYOK LLM)', 'hosted_api',
     '["reasoning","tool_call","text_gen"]'::jsonb, 'https://openrouter.ai/api/v1',
     'bearer', 'Authorization', 'Bearer {key}', 'openai_compat', 'reasoning_model',
     'anthropic/claude-3.5-sonnet', 'per_1k_tokens', true, true, 'seed:v2-w4')
ON CONFLICT (tenant_id, slug) DO NOTHING;
