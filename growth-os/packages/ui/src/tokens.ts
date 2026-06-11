/**
 * GROWTH OS design tokens (Phase-0 placeholder). The real brand kit is per-tenant + versioned
 * (§15.1) and self-hosts licensed fonts. These app-chrome tokens are the product shell only.
 */
export const tokens = {
  radius: { sm: '0.375rem', md: '0.5rem', lg: '0.75rem' },
  font: {
    sans: 'Inter, ui-sans-serif, system-ui, sans-serif',
    mono: 'ui-monospace, SFMono-Regular, monospace',
  },
} as const;

export type Tokens = typeof tokens;
