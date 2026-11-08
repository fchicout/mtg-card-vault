import { expect, type Page } from '@playwright/test';

/**
 * Signs in through the real user interface against the OIDC test double of the E2E stack
 * (deploy/compose.e2e.yaml). The double logs the default user in automatically, so one click on
 * "Sign in" ends on the start page with the user's name in the header.
 */
export async function signIn(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByTestId('sign-in').click();
  await expect(page.getByTestId('user-name')).toBeVisible({ timeout: 20_000 });
}

/**
 * Opens a page after signing in. A full page load drops the in-memory tokens, so the app goes
 * through the provider again before the page is usable; wait for that to finish.
 */
export async function gotoSignedIn(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByTestId('user-name')).toBeVisible({ timeout: 20_000 });
}
