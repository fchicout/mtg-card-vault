import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { signIn } from './support/session';

/**
 * Identity journeys of the identity milestone (US-001..US-004, UC-01, UC-09) against the OIDC test
 * double: sign-in, silent renewal, a revoked or failing refresh, a cancelled login, sign-out.
 */
const OIDC = process.env['E2E_OIDC_URL'] ?? 'https://localhost:9000';

async function control(request: APIRequestContext, change: Record<string, unknown>): Promise<void> {
  const response = await request.post(`${OIDC}/__control`, { data: change });
  expect(response.ok()).toBeTruthy();
}

async function state(
  request: APIRequestContext,
): Promise<{ code_grants: number; refresh_grants: number }> {
  return (await request.get(`${OIDC}/__state`)).json();
}

/** Collects what the browser would show in its console about the page's security policy. */
function watchSecurityProblems(page: Page): string[] {
  const problems: string[] = [];
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (/content security policy|refused to (connect|load|execute)/i.test(message.text())) {
      problems.push(message.text());
    }
  });
  return problems;
}

test.beforeEach(async ({ request }, testInfo) => {
  const reachable = await request
    .get(`${OIDC}/.well-known/openid-configuration`)
    .then((r) => r.ok())
    .catch(() => false);
  testInfo.skip(!reachable, 'the OIDC test double is not running (deploy/compose.e2e.yaml)');
  await control(request, { reset: true });
});

test.afterEach(async ({ request }) => {
  await control(request, { reset: true }).catch(() => undefined);
});

test.describe('UC-01 sign in', () => {
  test('@UC-01 public pages need no session, and signing in raises no security problem', async ({
    page,
  }) => {
    const problems = watchSecurityProblems(page);
    await page.goto('/');
    await expect(page.getByTestId('welcome')).toBeVisible();
    await expect(page.getByTestId('sign-in')).toBeVisible();

    await signIn(page);
    await page.getByRole('link', { name: 'Account' }).click();
    await expect(page.locator('h1')).toHaveText('Account');
    await expectNoSeriousViolations(page);
    expect(problems).toEqual([]);
  });

  test('@UC-01 a cancelled login explains itself and a retry succeeds', async ({
    page,
    request,
  }) => {
    await control(request, { next_login: 'deny' });
    await page.goto('/');
    await page.getByTestId('sign-in').click();

    await expect(page.locator('h1')).toHaveText('Sign in required');
    await expect(page.getByTestId('empty')).toContainText('cancelled or could not be completed');
    await expectNoSeriousViolations(page);

    await page.getByTestId('signin-retry').click();
    await expect(page.getByTestId('user-name')).toBeVisible();
  });
});

test.describe('UC-01 session renewal (US-003)', () => {
  test('@UC-01 the session is renewed silently before the token ends', async ({
    page,
    request,
  }) => {
    await control(request, { access_ttl: 6 });
    await signIn(page);
    await expect
      .poll(async () => (await state(request)).refresh_grants, { timeout: 20_000 })
      .toBeGreaterThanOrEqual(1);

    await page.getByRole('link', { name: 'Account' }).click();
    await expect(page.locator('h1')).toHaveText('Account');
    await expect(page.getByTestId('user-name')).toBeVisible();
  });

  test('@UC-01 a revoked refresh token sends the user through the provider and back to the page', async ({
    page,
    request,
  }) => {
    await control(request, { access_ttl: 6 });
    await signIn(page);
    await page.getByRole('link', { name: 'Account' }).click();
    await expect(page.locator('h1')).toHaveText('Account');

    await control(request, { revoke_all: true });
    await expect
      .poll(async () => (await state(request)).code_grants, { timeout: 25_000 })
      .toBeGreaterThanOrEqual(2);
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByTestId('user-name')).toBeVisible();
  });

  test('@UC-01 a failing provider ends in the retry page, and the retry works once it recovers', async ({
    page,
    request,
  }) => {
    await control(request, { access_ttl: 6 });
    await signIn(page);

    await control(request, { token_status: 500 });
    await expect(page.locator('h1')).toHaveText('Sign in required', { timeout: 25_000 });
    await expect(page.getByTestId('empty')).toContainText('could not be completed');

    await control(request, { token_status: 0 });
    await page.getByTestId('signin-retry').click();
    await expect(page.getByTestId('user-name')).toBeVisible();
  });
});

test.describe('UC-09 sign out', () => {
  test('@UC-09 sign-out revokes the refresh token and ends the session', async ({
    page,
    request,
  }) => {
    await signIn(page);
    await page.getByTestId('sign-out').click();

    await expect(page.getByTestId('sign-in')).toBeVisible();
    await page.goto('/vault');
    await expect(page.locator('h1')).toHaveText('Sign in required');
    await page.getByTestId('signin-retry').click();
    await expect(page.locator('h1')).toHaveText('Vault');
    expect((await state(request)).code_grants).toBeGreaterThanOrEqual(2);
  });
});
