// GROWTH OS — flat ESLint config (root, shared by all TS packages/services).
// Phase 0 keeps lint lightweight + deterministic: TS recommended + import hygiene.
// Tightened per-plane in later phases.
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/.turbo/**',
      '**/node_modules/**',
      '**/coverage/**',
      '**/src/generated/**',
      'contracts/**',
    ],
  },
  ...tseslint.configs.recommended,
  {
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
);
