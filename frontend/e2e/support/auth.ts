import type { BrowserContext, Page } from '@playwright/test';

/**
 * Sign-in helper for the development Authelia of the `ci` compose profile (issue #4). The seeded
 * users `alice` and `bob` share the documented dev password; nothing here is a real credential.
 * It signs in at the identity provider itself; signing in through the SPA's own OIDC flow arrives
 * with the identity milestone (issue #17) and will reuse the stored session.
 */
export const AUTHELIA_URL = process.env['E2E_AUTHELIA_URL'] ?? '';
export const DEV_PASSWORD = 'dev-only-password';

export async function signInToAuthelia(page: Page, user: 'alice' | 'bob' = 'alice'): Promise<void> {
  // After a successful sign-in Authelia sends the browser to the application's address on the
  // dev domain (its `default_redirection_url`). That host does not exist in tests: answer it, so the
  // redirect ends quietly instead of interrupting the test's next navigation.
  await page.route('https://app.localtest.me:4200/**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<title>signed in</title>' }),
  );
  await page.goto(AUTHELIA_URL + '/');
  await page.locator('#username-textfield').fill(user);
  await page.locator('#password-textfield').fill(DEV_PASSWORD);
  const answered = page.waitForResponse((r) => r.url().endsWith('/api/firstfactor'));
  await page.locator('#sign-in-button').click();
  const response = await answered;
  if (!response.ok()) {
    throw new Error(`Authelia refused the sign-in of ${user}: HTTP ${response.status()}`);
  }
  await page.waitForURL('https://app.localtest.me:4200/**');
}

/** Saves cookies and storage so later tests can start already signed in. */
export async function saveSession(context: BrowserContext, file: string): Promise<void> {
  await context.storageState({ path: file });
}
