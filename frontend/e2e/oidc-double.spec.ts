import { createHash, randomBytes } from 'node:crypto';

import { expect, test, type APIRequestContext } from '@playwright/test';

/**
 * The stack's API accepts tokens from the OIDC test double (issue #59): authorization code with
 * PKCE, then a call to the protected API through the web entry point. Runs only when the overlay
 * `deploy/compose.e2e.yaml` provides the double (E2E_OIDC_URL, default http://localhost:9000).
 */
const OIDC = process.env['E2E_OIDC_URL'] ?? 'https://localhost:9000';
const REDIRECT = 'https://localhost:8443/callback';

test.beforeEach(async ({ request }, testInfo) => {
  const reachable = await request
    .get(`${OIDC}/.well-known/openid-configuration`)
    .then((r) => r.ok())
    .catch(() => false);
  testInfo.skip(!reachable, 'the OIDC test double is not running (deploy/compose.e2e.yaml)');
});

async function signIn(request: APIRequestContext, hint = 'user-1'): Promise<string> {
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
      login_hint: hint,
    },
  });
  expect(authorize.status()).toBe(302);
  const code = new URL(authorize.headers()['location']).searchParams.get('code');
  expect(code).toBeTruthy();
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

test.describe('API with tokens from the OIDC double', () => {
  test('a signed-in user is provisioned and gets a stable profile', async ({ request }) => {
    const token = await signIn(request);
    const headers = { Authorization: `Bearer ${token}` };

    const first = await request.get('/api/v1/me', { headers });
    expect(first.status()).toBe(200);
    const profile = await first.json();
    expect(profile.display_name).toBe('Ada Lovelace');

    const second = await request.get('/api/v1/me', { headers });
    expect((await second.json()).id).toBe(profile.id);
  });

  test('two users get two separate accounts', async ({ request }) => {
    const ada = await (
      await request.get('/api/v1/me', {
        headers: { Authorization: `Bearer ${await signIn(request, 'user-1')}` },
      })
    ).json();
    const grace = await (
      await request.get('/api/v1/me', {
        headers: { Authorization: `Bearer ${await signIn(request, 'user-2')}` },
      })
    ).json();
    expect(grace.id).not.toBe(ada.id);
    expect(grace.display_name).toBe('Grace Hopper');
  });

  test('a forged token is refused with a challenge', async ({ request }) => {
    const response = await request.get('/api/v1/me', {
      headers: { Authorization: 'Bearer not.a.token' },
    });
    expect(response.status()).toBe(401);
    expect(response.headers()['www-authenticate']).toContain('invalid_token');
  });
});
