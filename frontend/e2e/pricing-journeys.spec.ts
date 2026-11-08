import { expect, test, type Page } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { controlScryfall, scryfallIsUp, stubCardImages } from './support/cards';
import { gotoSignedIn, signIn } from './support/session';
import { emptyVault } from './support/tokens';
import { runWorkerOnce, workerIsAvailable } from './support/worker';

/**
 * Pricing journeys (UC-06, UC-07, UC-08, US-020..US-023): values on the vault page, the
 * collection summary and the price refresh, through the real API, database and worker, with the
 * Scryfall double as the price source. They change prices in the shared double and the vault of
 * one user, so they run alone in the serial project.
 */
test.beforeEach(async ({ page, request, browserName }, testInfo) => {
  testInfo.skip(browserName !== 'chromium', 'the serial journeys run in Chromium only');
  testInfo.skip(!(await scryfallIsUp(request)), 'the Scryfall test double is not running');
  testInfo.skip(!(await workerIsAvailable()), 'the worker service is not running');
  await controlScryfall(request, { reset: true });
  await emptyVault(request);
  await stubCardImages(page);
  await signIn(page);
});

/** Adds the printing at `index` of a search and returns its id (from the card page address). */
async function addFromCatalogue(
  page: Page,
  search: string,
  index: number,
  quantity: number,
): Promise<string> {
  await gotoSignedIn(page, `/catalogue?q=${encodeURIComponent(search)}`);
  await page.getByTestId('result').nth(index).click();
  await expect(page.getByTestId('card-name')).toBeVisible();
  const id = page.url().split('/').pop() ?? '';
  await page.getByTestId('add').click();
  await page.locator('#entry-quantity').fill(String(quantity));
  await page.getByTestId('submit').click();
  await expect(page.getByTestId('added')).toBeVisible();
  return id;
}

test('@UC-07 the vault shows unit prices and line values and the summary adds them up', async ({
  page,
  request,
}) => {
  await gotoSignedIn(page, '/catalogue?q=lightning%20bolt');
  await page.getByTestId('result').nth(1).click();
  const bolt = page.url().split('/').pop() ?? '';
  await controlScryfall(request, { prices: { [bolt]: { usd: '1.50', eur: '1.30' } } });
  await addFromCatalogue(page, 'lightning bolt', 1, 2);

  await gotoSignedIn(page, '/vault');
  const row = page.getByTestId('entry');
  await expect(row).toHaveCount(1);
  await expect(page.getByTestId('entry-price')).toHaveText('$1.50');
  await expect(page.getByTestId('entry-price-eur')).toHaveText('€1.30');
  await expect(page.getByTestId('entry-value')).toHaveText('$3.00');
  await expect(page.getByTestId('entry-value-eur')).toHaveText('€2.60');
  await expect(page.getByTestId('summary-cards')).toHaveText('2');
  await expect(page.getByTestId('summary-usd')).toHaveText('$3.00');
  await expect(page.getByTestId('summary-eur')).toHaveText('€2.60');
  await expect(page.getByTestId('lower-bound')).toHaveCount(0);
  await expect(page.getByTestId('stale')).toHaveCount(0);
  await expectNoSeriousViolations(page);
});

test('@UC-07 a card without a price says so and makes the total a lower bound', async ({
  page,
  request,
}) => {
  await gotoSignedIn(page, '/catalogue?q=lightning%20bolt');
  await page.getByTestId('result').nth(1).click();
  const bolt = page.url().split('/').pop() ?? '';
  await controlScryfall(request, { prices: { [bolt]: { usd: '1.50', eur: '1.30' } } });
  await addFromCatalogue(page, 'lightning bolt', 1, 1);
  await addFromCatalogue(page, 'lightning bolt', 0, 3); // the double-faced one has no prices

  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('entry')).toHaveCount(2);
  await expect(page.getByTestId('summary-cards')).toHaveText('4');
  await expect(page.getByTestId('summary-usd')).toHaveText('$1.50');
  await expect(page.getByTestId('lower-bound')).toContainText('lower bound');
  await expect(page.getByTestId('unpriced-usd')).toContainText('1');
  await expect(page.locator('[data-testid="entry-price"]', { hasText: 'no price' })).toHaveCount(1);
  await expectNoSeriousViolations(page);
});

test('@UC-08 the refresh brings new prices into the vault and the summary', async ({
  page,
  request,
}) => {
  await gotoSignedIn(page, '/catalogue?q=lightning%20bolt');
  await page.getByTestId('result').nth(1).click();
  const bolt = page.url().split('/').pop() ?? '';
  await controlScryfall(request, { prices: { [bolt]: { usd: '1.50', eur: '1.30' } } });
  await addFromCatalogue(page, 'lightning bolt', 1, 2);

  await controlScryfall(request, { prices: { [bolt]: { usd: '2.25', eur: '1.90' } } });
  const run = await runWorkerOnce();
  expect(run.code, run.output).toBe(0);
  expect(run.output).toContain('price refresh finished');

  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('entry-price')).toHaveText('$2.25');
  await expect(page.getByTestId('entry-value')).toHaveText('$4.50');
  await expect(page.getByTestId('summary-usd')).toHaveText('$4.50');
  await expect(page.getByTestId('summary-eur')).toHaveText('€3.80');
});

test('@UC-08 a throttled or failing source leaves the old prices in place', async ({
  page,
  request,
}) => {
  await gotoSignedIn(page, '/catalogue?q=lightning%20bolt');
  await page.getByTestId('result').nth(1).click();
  const bolt = page.url().split('/').pop() ?? '';
  await controlScryfall(request, { prices: { [bolt]: { usd: '1.50', eur: '1.30' } } });
  await addFromCatalogue(page, 'lightning bolt', 1, 1);

  await controlScryfall(request, {
    prices: { [bolt]: { usd: '9.99' } },
    fail: 429,
    retry_after: 0,
  });
  await runWorkerOnce(); // the batch fails; the run ends without touching the stored prices
  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('entry-price')).toHaveText('$1.50');
  await expect(page.getByTestId('summary-usd')).toHaveText('$1.50');

  await controlScryfall(request, { fail: 0 });
  const healed = await runWorkerOnce();
  expect(healed.code, healed.output).toBe(0);
  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('entry-price')).toHaveText('$9.99');
});
