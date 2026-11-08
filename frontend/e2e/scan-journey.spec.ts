import { expect, test } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { controlScryfall, scryfallIsUp, stubCardImages } from './support/cards';
import { gotoSignedIn, signIn } from './support/session';
import { emptyVault } from './support/tokens';

/**
 * Scan journey (UC-02, US-015..US-019): the fake camera shows a card titled "LIGHTNING BOLT"; the
 * real frame goes through the real API, Tesseract and the Scryfall double. It adds vault entries,
 * so it runs alone in the serial project (see playwright.config.ts).
 */
test.beforeEach(async ({ page, request, browserName }, testInfo) => {
  testInfo.skip(browserName !== 'chromium', 'the fake camera exists only in Chromium');
  testInfo.skip(!(await scryfallIsUp(request)), 'the Scryfall test double is not running');
  await controlScryfall(request, { reset: true });
  await emptyVault(request);
  await stubCardImages(page);
  await signIn(page);
});

test('@UC-02 a scanned card is only added after the person confirms it', async ({ page }) => {
  await page.getByRole('link', { name: 'Scan' }).first().click();
  await expect(page.getByRole('heading', { name: 'Scan' })).toBeVisible();
  await page.getByTestId('start-camera').click();
  await expect(page.getByTestId('camera-preview')).toBeVisible();
  await expectNoSeriousViolations(page);

  await page.getByTestId('capture').click();
  const candidates = page.getByTestId('candidate');
  await expect(candidates.first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('scan-read')).toContainText('LIGHTNING BOLT');
  await expect(candidates.first()).toContainText('Lightning Bolt');

  // Nothing is in the vault yet: scanning never adds by itself.
  await page.getByTestId('choose').first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByTestId('cancel').click();
  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('entry')).toHaveCount(0);

  await gotoSignedIn(page, '/scan');
  await page.getByTestId('start-camera').click();
  await page.getByTestId('capture').click();
  await page.getByTestId('choose').first().click();
  await page.locator('#entry-quantity').fill('2');
  await page.getByTestId('submit').click();
  await expect(page.getByTestId('scan-added')).toContainText('Added Lightning Bolt');

  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('entry')).toHaveCount(1);
  await expect(page.getByTestId('entry-quantity')).toHaveText('2');
});

test('@UC-02 the person can leave for the manual search with what was read', async ({ page }) => {
  await gotoSignedIn(page, '/scan');
  await page.getByTestId('start-camera').click();
  await page.getByTestId('capture').click();
  await expect(page.getByTestId('manual-search')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('manual-search').click();
  await expect(page).toHaveURL(/\/catalogue\?q=LIGHTNING/);
});
