import { expect, test } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { requestLog, scryfallIsUp, stubCardImages } from './support/cards';
import { gotoSignedIn, signIn } from './support/session';

/**
 * Catalogue journeys (UC-10, US-012..US-014, US-024) against the Scryfall test double: the stack
 * never contacts the real Scryfall. Outage behaviour lives in catalogue-outage.spec.ts.
 */
test.beforeEach(async ({ page, request }, testInfo) => {
  testInfo.skip(!(await scryfallIsUp(request)), 'the Scryfall test double is not running');
  await stubCardImages(page);
  await signIn(page);
});

test.describe('@UC-10 search', () => {
  test('a partial name lists matching cards with image, name, type and set', async ({ page }) => {
    await gotoSignedIn(page, '/catalogue');
    await expect(page.getByTestId('empty')).toContainText('Find a card');

    await page.getByTestId('q').fill('lightning bolt');
    await page.getByTestId('search').click();

    const results = page.getByTestId('result');
    await expect(results).toHaveCount(2);
    await expect(results.nth(1)).toContainText('Lightning Bolt');
    await expect(results.nth(1).locator('img')).toHaveAttribute('alt', 'Lightning Bolt');
    await expect(page).toHaveURL(/\/catalogue\?q=lightning(%20|\+)bolt$/);
    await expectNoSeriousViolations(page);
  });

  test('a nonsense search shows the empty state', async ({ page }) => {
    await gotoSignedIn(page, '/catalogue?q=zzzqqq');
    await expect(page.getByTestId('empty')).toContainText('No cards found');
    await expectNoSeriousViolations(page);
  });

  test('filters are translated for the source and shared through the address', async ({
    page,
    request,
  }) => {
    await gotoSignedIn(page, '/catalogue');
    await page.getByTestId('q').fill('bolt');
    await page.getByTestId('color-R').check();
    await page.locator('#rarity').selectOption('mythic');
    await page.getByTestId('search').click();
    await expect(page).toHaveURL(/q=bolt&colors=R&rarity=mythic/);
    await expect(page.getByTestId('result').first()).toBeVisible();

    const searches = (await requestLog(request)).filter((r) => r.path === '/cards/search');
    expect(searches.map((r) => r.query['q'])).toContain('name:"bolt" r:mythic c:r');

    await gotoSignedIn(page, page.url());
    await expect(page.getByTestId('color-R')).toBeChecked();
    await expect(page.locator('#rarity')).toHaveValue('mythic');
    await expect(page.getByTestId('result').first()).toBeVisible();
  });

  test('search text cannot inject operators into the source query', async ({ page, request }) => {
    await gotoSignedIn(page, '/catalogue');
    await page.getByTestId('q').fill('bolt" or o:"x');
    await page.getByTestId('search').click();
    await expect(page.getByTestId('result').first()).toBeVisible();
    const sent = (await requestLog(request))
      .filter((r) => r.path === '/cards/search')
      .map((r) => r.query['q']);
    expect(sent).toContain('name:"bolt" name:"or" name:"o:" name:"x"');
  });
});

test.describe('@UC-10 card and printings', () => {
  test('opening a card shows its details and all printings, and another can be selected', async ({
    page,
  }) => {
    await gotoSignedIn(page, '/catalogue?q=bolt');
    await page.getByTestId('result').nth(1).click();

    await expect(page.getByTestId('card-name')).toHaveText('Lightning Bolt');
    await expect(page.getByTestId('set')).toBeVisible();
    await expect(page.getByTestId('prices')).toContainText('USD');
    const art = page.getByTestId('art');
    await expect(art).toBeVisible();
    const ratio = await art.evaluate((img: HTMLImageElement) => img.clientWidth / img.clientHeight);
    expect(ratio).toBeCloseTo(488 / 680, 1); // never cropped or distorted (NFR-LEG-01)

    const rows = page.getByTestId('printing');
    await expect(rows).toHaveCount(6);
    await expect(rows.first()).toContainText(/\(\w+\)/);
    await expect(page.getByTestId('add')).toBeEnabled();
    await expectNoSeriousViolations(page);

    const before = page.url();
    await page.getByTestId('select').first().click();
    await expect(page).not.toHaveURL(before);
    await expect(page.getByTestId('card-name')).toBeVisible();
  });

  test('a card that does not exist says so', async ({ page }) => {
    await gotoSignedIn(page, '/catalogue/00000000-0000-4000-8000-000000000000');
    await expect(page.getByTestId('error')).toContainText('could not find this card');
  });
});

test.describe('@UC-10 Scryfall rules (US-024)', () => {
  test('every request to the source is identified and spaced by at least 100 ms', async ({
    page,
    request,
  }) => {
    await gotoSignedIn(page, '/catalogue?q=bolt');
    await expect(page.getByTestId('result').first()).toBeVisible();
    await gotoSignedIn(page, '/catalogue?q=treasure token');
    await expect(page.getByTestId('result').first()).toBeVisible();

    const log = (await requestLog(request)).filter((r) => r.path.startsWith('/cards'));
    expect(log.length).toBeGreaterThan(1);
    for (const entry of log) {
      expect(entry.user_agent).toMatch(/^MTGCardVault\//);
      expect(entry.accept).toBe('application/json');
    }
    const times = log.map((r) => r.at).sort((a, b) => a - b);
    for (let i = 1; i < times.length; i++) {
      expect(times[i] - times[i - 1]).toBeGreaterThanOrEqual(0.09); // 100 ms, allowing clock jitter
    }
  });
});
