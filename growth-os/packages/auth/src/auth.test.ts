import { describe, it, expect } from 'vitest';
import { mintDevToken, DevJwtVerifier, AuthError } from './index.js';

const claims = {
  sub: '00000000-0000-7000-8000-0000000000aa',
  tenant_id: '00000000-0000-7000-8000-000000000001',
  workspace_id: '00000000-0000-7000-8000-000000000002',
  role: 'Owner' as const,
};

describe('dev JWT stub (D5)', () => {
  it('mints a token the verifier accepts, resolving tenant from the TOKEN (P6)', async () => {
    const { access_token } = await mintDevToken(claims);
    const ctx = await new DevJwtVerifier().verify(access_token);
    expect(ctx.tenant_id).toBe(claims.tenant_id);
    expect(ctx.workspace_id).toBe(claims.workspace_id);
    expect(ctx.role).toBe('Owner');
    expect(ctx.sub).toBe(claims.sub);
  });

  it('rejects a garbage token', async () => {
    await expect(new DevJwtVerifier().verify('not.a.jwt')).rejects.toBeInstanceOf(AuthError);
  });
});
