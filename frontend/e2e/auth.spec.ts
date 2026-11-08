import { expect, test } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { gotoSignedIn, signIn } from './support/session';

/** Sign-in journeys (US-001, UC-01). Run against the stack with the OIDC test double. */
test.describe('signing in', () => {
  test('a visitor opening a protected page lands on the sign-in page, then on that page', async ({
    page,
  }) => {
    await page.goto('/vault');
    await expect(page.locator('h1')).toHaveText('Sign in required');
    await expectNoSeriousViolations(page);

    await page.getByTestId('signin-retry').click();
    await expect(page).toHaveURL(/\/vault$/);
    await expect(page.locator('h1')).toHaveText('Vault');
    await expect(page.getByTestId('user-name')).toContainText('Ada');
  });

  test('the header offers sign-in and then shows the name from the profile', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('sign-in')).toBeVisible();
    await signIn(page);
    await expect(page.getByTestId('sign-in')).toHaveCount(0);
  });

  test('tokens never reach web storage or cookies', async ({ page, context }) => {
    await signIn(page);
    const stored = await page.evaluate(() =>
      JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
    );
    expect(stored).not.toMatch(/eyJ[\w-]{5,}\./); // no JWT anywhere
    expect(stored).not.toContain('access_token');
    expect(stored).not.toContain('refresh_token');
    expect(JSON.stringify(await context.cookies())).not.toMatch(/eyJ[\w-]{5,}\./);
  });

  test('a signed-in reload keeps the session by going through the provider again', async ({
    page,
  }) => {
    await signIn(page);
    await gotoSignedIn(page, '/account');
    await expect(page.locator('h1')).toHaveText('Account');
  });
});

test.describe('signing out', () => {
  test('ends the session: the header offers sign-in again and protected pages ask for it', async ({
    page,
  }) => {
    await signIn(page);
    await page.getByTestId('sign-out').click();

    await expect(page.getByTestId('sign-in')).toBeVisible();
    await expect(page.getByTestId('user-name')).toHaveCount(0);
    await page.goto('/vault');
    await expect(page.locator('h1')).toHaveText('Sign in required');
  });
});

test.describe('cross-origin rules of the API', () => {
  test('a foreign origin gets no CORS permission', async ({ request }) => {
    const response = await request.fetch('/api/v1/me', {
      method: 'OPTIONS',
      headers: {
        Origin: 'https://evil.example',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization',
      },
    });
    expect(response.headers()['access-control-allow-origin']).toBeUndefined();
  });
});
