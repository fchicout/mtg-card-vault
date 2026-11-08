import { createHash, randomBytes } from 'node:crypto';

import { expect, type APIRequestContext } from '@playwright/test';

/** Raw OIDC calls against the test double, to act as a user without the browser (see oidc-double.spec.ts). */
export const OIDC = process.env['E2E_OIDC_URL'] ?? 'https://localhost:9000';
const REDIRECT = 'https://localhost:8443/callback';

export async function accessToken(request: APIRequestContext, user = 'user-1'): Promise<string> {
  const verifier = randomBytes(48).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const authorize = await request.get(`${OIDC}/authorize`, {
    maxRedirects: 0,
    params: {
      client_id: 'mtgvault-test',
      redirect_uri: REDIRECT,
      response_type: 'code',
      scope: 'openid profile email offline_access',
      state: 'e2e',
      code_challenge: challenge,
      code_challenge_method: 'S256',
      login_hint: user,
    },
  });
  const code = new URL(authorize.headers()['location']).searchParams.get('code');
  const token = await request.post(`${OIDC}/token`, {
    form: {
      grant_type: 'authorization_code',
      code: code!,
      redirect_uri: REDIRECT,
      code_verifier: verifier,
    },
  });
  expect(token.ok()).toBeTruthy();
  return (await token.json()).access_token as string;
}

export function bearer(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` };
}

/** Removes every vault entry of a user through the API: tests start from an empty vault. */
export async function emptyVault(request: APIRequestContext, user = 'user-1'): Promise<void> {
  const headers = bearer(await accessToken(request, user));
  for (;;) {
    const page = await (
      await request.get('/api/v1/vault/entries', { headers, params: { page_size: 200 } })
    ).json();
    if (page.items.length === 0) {
      return;
    }
    for (const entry of page.items) {
      await request.delete(`/api/v1/vault/entries/${entry.id}`, { headers });
    }
  }
}
