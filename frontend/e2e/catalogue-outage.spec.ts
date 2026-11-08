import { expect, test } from '@playwright/test';

import { controlScryfall, scryfallIsUp, stubCardImages } from './support/cards';
import { gotoSignedIn, signIn } from './support/session';

/**
 * US-025: the catalogue says so when Scryfall is down and recovers by itself. These journeys fail
 * the shared Scryfall double, so they run alone in the serial project (see playwright.config.ts).
 */
test.beforeEach(async ({ page, request }, testInfo) => {
  testInfo.skip(!(await scryfallIsUp(request)), 'the Scryfall test double is not running');
  await controlScryfall(request, { reset: true });
  await stubCardImages(page);
  await signIn(page);
});

test.afterEach(async ({ request }) => {
  await controlScryfall(request, { reset: true }).catch(() => undefined);
  // Let the API's circuit breaker (3 s open in this stack) reach half-open before the next test.
  await new Promise((resolve) => setTimeout(resolve, 3_500));
});

test('@UC-10 an outage shows a friendly message, never a stack trace, and the page recovers', async ({
  page,
  request,
}) => {
  await controlScryfall(request, { fail: 503 });
  await gotoSignedIn(page, '/catalogue?q=lightning%20bolt%20storm');
  const error = page.getByTestId('error');
  await expect(error).toContainText('temporarily unavailable', { timeout: 30_000 });
  await expect(page.locator('body')).not.toContainText(/traceback|exception|stack/i);

  await controlScryfall(request, { fail: 0 });
  // The circuit breaker lets a probe through after a few seconds; "Try again" until it closes.
  await expect(async () => {
    await page.getByTestId('retry').click();
    await expect(page.getByTestId('result').first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 30_000 });
});

test('@UC-10 a throttled source is reported as busy', async ({ page, request }) => {
  await controlScryfall(request, { fail: 429, retry_after: 60 });
  await gotoSignedIn(page, '/catalogue?q=lightning%20bolt%20again');
  await expect(page.getByTestId('error')).toContainText('busy', { timeout: 30_000 });
});
