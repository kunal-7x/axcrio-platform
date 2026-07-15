/**
 * Cybertroic runtime env. Recommended port-map slot: cybertroic = 3026
 * (3022 governor · 3023 optimizer · 3024 famit-cloud · 3025 grow-connect).
 *
 * Safe defaults everywhere so the service boots + typechecks on a laptop with NO env set
 * (in-memory bus, fake model client, no owner webhook). The box supplies the real values.
 */
export const CYBERTROIC_ENV = {
  port: Number(process.env.PORT ?? 3026),

  /** LLM gateway / OpenRouter key. Absent ⇒ the model client runs as an in-memory fake
   *  (deterministic Sentry classify only — no network), which is the correct Phase-0 path. */
  openRouterApiKey: process.env.OPENROUTER_API_KEY ?? '',
  /** Base URL for the OpenAI-compatible gateway the tiered models route through. */
  modelBaseUrl: process.env.CYBERTROIC_MODEL_BASE_URL ?? 'https://openrouter.ai/api/v1',

  /**
   * The tiered-model ladder ids (the cost story: 99% of events die at the cheap Sentry tier;
   * only what it can't clear climbs to the costly Specialist). Mirrors panel _rules.ts.
   */
  sentryModel: process.env.CYBERTROIC_SENTRY_MODEL ?? 'groq/llama-3.1-8b-instant',
  investigatorModel: process.env.CYBERTROIC_INVESTIGATOR_MODEL ?? 'anthropic/claude-haiku',
  specialistModel: process.env.CYBERTROIC_SPECIALIST_MODEL ?? 'anthropic/claude-opus',

  /** Where owner briefings are POSTed (Slack/WhatsApp/webhook relay). Empty ⇒ log-only notifier. */
  ownerWebhookUrl: process.env.OWNER_WEBHOOK_URL ?? '',

  /** core base URL — reserved for future firewall-gated containment proposals (P4). Optional now. */
  coreBaseUrl: process.env.CORE_BASE_URL ?? '',
} as const;

export function busIsInMemory(): boolean {
  return !process.env.KAFKA_BROKERS || process.env.GROWTH_OS_BUS === 'memory';
}
