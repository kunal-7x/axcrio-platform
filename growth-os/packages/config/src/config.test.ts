import { describe, it, expect } from 'vitest';
import { loadCoreConfig, ConfigError } from './index.js';

describe('loadCoreConfig', () => {
  it('applies laptop defaults: in-memory bus + no db + dev token on', () => {
    const c = loadCoreConfig({} as NodeJS.ProcessEnv);
    expect(c.busInMemory).toBe(true);
    expect(c.dbEnabled).toBe(false);
    expect(c.devTokenEnabled).toBe(true);
    expect(c.PORT).toBe(3000);
  });

  it('disables the dev token in production (D5)', () => {
    const c = loadCoreConfig({ NODE_ENV: 'production' } as NodeJS.ProcessEnv);
    expect(c.isProd).toBe(true);
    expect(c.devTokenEnabled).toBe(false);
  });

  it('enables db when a DATABASE_URL is present', () => {
    const c = loadCoreConfig({ DATABASE_URL: 'postgres://u:p@localhost:5432/db' } as NodeJS.ProcessEnv);
    expect(c.dbEnabled).toBe(true);
  });

  it('throws ConfigError on an invalid PORT', () => {
    expect(() => loadCoreConfig({ PORT: 'not-a-number' } as NodeJS.ProcessEnv)).toThrow(ConfigError);
  });
});
