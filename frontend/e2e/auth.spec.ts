import { expect, test } from '@playwright/test';

import { AUTHELIA_URL, signInToAuthelia } from './support/auth';

/**
 * Sample journey on the ephemeral stack (issue #12): sign in at the development Authelia with a
 * seeded user, then open the application shell. Needs the `ci` compose profile; the address of
 * Authelia comes from E2E_AUTHELIA_URL (CI sets it).
 */
test.describe('seeded users and the shell', () => {
  test.skip(!AUTHELIA_URL, 'E2E_AUTHELIA_URL is not set: the ci compose profile is not running');

  for (const user of ['alice', 'bob'] as const) {
    test(`${user} signs in at the identity provider and the shell opens`, async ({
      page,
      context,
    }) => {
      await page.route('**/hello', (route) =>
        route.fulfill({ json: { message: 'Hello, MTG Vault!' } }),
      );

      await signInToAuthelia(page, user);
      const cookies = await context.cookies();
      expect(cookies.map((c) => c.name)).toContain('authelia_session');

      await page.goto('/');
      await expect(page.locator('.header .title')).toHaveText('MTG Card Vault');
      await expect(
        page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link'),
      ).toHaveCount(4);
    });
  }

  test('a wrong password is refused', async ({ page }) => {
    await page.goto(AUTHELIA_URL + '/');
    await page.locator('#username-textfield').fill('alice');
    await page.locator('#password-textfield').fill('not-the-password');
    const answered = page.waitForResponse((r) => r.url().endsWith('/api/firstfactor'));
    await page.locator('#sign-in-button').click();
    expect((await answered).status()).toBe(401);
  });
});
