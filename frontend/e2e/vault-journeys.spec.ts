import { expect, test, type Page } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { controlScryfall, scryfallIsUp, stubCardImages } from './support/cards';
import { gotoSignedIn, signIn } from './support/session';
import { emptyVault } from './support/tokens';

/**
 * Vault journeys (UC-03..UC-06, US-005..US-010, US-025). They change one user's vault in the shared
 * database, so they run alone in the serial project (see playwright.config.ts).
 */
test.beforeEach(async ({ page, request }, testInfo) => {
  testInfo.skip(!(await scryfallIsUp(request)), 'the Scryfall test double is not running');
  await controlScryfall(request, { reset: true });
  await emptyVault(request);
  await stubCardImages(page);
  await signIn(page);
});

async function addFromCatalogue(
  page: Page,
  search: string,
  resultIndex: number,
  values: { quantity: number; condition?: string; finish?: string },
): Promise<void> {
  await gotoSignedIn(page, `/catalogue?q=${encodeURIComponent(search)}`);
  await page.getByTestId('result').nth(resultIndex).click();
  await expect(page.getByTestId('card-name')).toBeVisible();
  await page.getByTestId('add').click();
  await page.locator('#entry-quantity').fill(String(values.quantity));
  if (values.condition) {
    await page.locator('#entry-condition').selectOption(values.condition);
  }
  if (values.finish) {
    await page.locator('#entry-finish').selectOption(values.finish);
  }
  await page.getByTestId('submit').click();
  await expect(page.getByTestId('added')).toBeVisible();
}

test.describe('@UC-03 add', () => {
  test('@UC-03 a printing from the catalogue is added, and adding it again merges the quantity', async ({
    page,
  }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 2, finish: 'foil' });
    await expect(page.getByTestId('added')).toContainText('You now own 2');

    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('entry')).toHaveCount(1);
    await expect(page.getByTestId('entry')).toContainText('Lightning Bolt');
    await expect(page.getByTestId('entry-quantity')).toHaveText('2');

    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 1, finish: 'foil' });
    await expect(page.getByTestId('added')).toContainText('You now own 3');
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('entry')).toHaveCount(1);
    await expect(page.getByTestId('entry-quantity')).toHaveText('3');
  });

  test('@UC-03 a different condition is a second entry', async ({ page }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 1, finish: 'foil' });
    await addFromCatalogue(page, 'lightning bolt', 1, {
      quantity: 1,
      condition: 'LP',
      finish: 'foil',
    });
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('entry')).toHaveCount(2);
  });

  test('@UC-03 invalid input is explained next to the field and nothing is saved', async ({
    page,
  }) => {
    await gotoSignedIn(page, '/catalogue?q=bolt');
    await page.getByTestId('result').nth(1).click();
    await page.getByTestId('add').click();
    await page.locator('#entry-quantity').fill('0');
    await page.getByTestId('submit').click();
    await expect(page.getByTestId('quantity-error')).toBeVisible();
    await expectNoSeriousViolations(page);
    await page.getByTestId('cancel').click();
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('empty')).toContainText('Your vault is empty');
  });
});

test.describe('@UC-06 view', () => {
  test('@UC-06 an empty vault offers scanning and searching, accessibly', async ({ page }) => {
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('empty')).toContainText('Your vault is empty');
    await expect(page.getByTestId('empty-scan')).toHaveAttribute('href', '/scan');
    await expect(page.getByTestId('empty-catalogue')).toHaveAttribute('href', '/catalogue');
    await expectNoSeriousViolations(page);
  });

  test('@UC-06 entries can be searched, filtered and sorted, and the view is in the address', async ({
    page,
  }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 4, finish: 'foil' });
    await addFromCatalogue(page, 'treasure token', 0, { quantity: 1 });
    await addFromCatalogue(page, 'treasure token', 1, { quantity: 2 });
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('entry')).toHaveCount(3);
    await expectNoSeriousViolations(page);

    await page.getByTestId('q').fill('bolt');
    await page.getByTestId('search').click();
    await expect(page.getByTestId('entry')).toHaveCount(1);
    await expect(page).toHaveURL(/q=bolt/);

    await page.getByTestId('clear').click();
    await page.getByTestId('sort-quantity').click();
    await expect(page).toHaveURL(/sort=quantity&dir=asc/);
    await expect(page.getByTestId('entry-quantity').first()).toHaveText('1');
    await page.getByTestId('sort-quantity').click();
    await expect(page.getByTestId('entry-quantity').first()).toHaveText('4');

    await gotoSignedIn(page, page.url());
    await expect(page.getByTestId('entry')).toHaveCount(3);
    await expect(page.getByTestId('entry-quantity').first()).toHaveText('4');
  });
});

test.describe('@UC-04 edit', () => {
  test('@UC-04 the quantity of an entry can be changed', async ({ page }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 1, finish: 'foil' });
    await gotoSignedIn(page, '/vault');
    await page.getByTestId('edit').click();
    await page.locator('#entry-quantity').fill('7');
    await page.getByTestId('submit').click();
    await expect(page.getByTestId('notice')).toContainText('Saved');
    await expect(page.getByTestId('entry-quantity')).toHaveText('7');
  });

  test('@UC-04 editing into an existing combination merges the two entries', async ({ page }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 2, finish: 'foil' });
    await addFromCatalogue(page, 'lightning bolt', 1, {
      quantity: 3,
      condition: 'LP',
      finish: 'foil',
    });
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('entry')).toHaveCount(2);
    await page.getByTestId('entry').filter({ hasText: 'LP' }).getByTestId('edit').click();
    await page.locator('#entry-condition').selectOption('NM');
    await page.getByTestId('submit').click();
    await expect(page.getByTestId('notice')).toContainText('Merged');
    await expect(page.getByTestId('entry')).toHaveCount(1);
    await expect(page.getByTestId('entry-quantity')).toHaveText('5');
  });
});

test.describe('@UC-05 remove', () => {
  test('@UC-05 removing asks first; cancelling keeps the entry, confirming deletes it', async ({
    page,
  }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 1, finish: 'foil' });
    await gotoSignedIn(page, '/vault');
    await page.getByTestId('remove').click();
    await expect(page.getByTestId('remove-question')).toContainText('Lightning Bolt');
    await page.getByTestId('remove-cancel').click();
    await expect(page.getByTestId('entry')).toHaveCount(1);

    await page.getByTestId('remove').click();
    await page.getByTestId('remove-confirm').click();
    await expect(page.getByTestId('notice')).toContainText('removed');
    await expect(page.getByTestId('empty')).toContainText('Your vault is empty');
  });
});

test.describe('@UC-06 outage (US-025)', () => {
  test('@UC-06 the vault is listed and editable while Scryfall is down', async ({
    page,
    request,
  }) => {
    await addFromCatalogue(page, 'lightning bolt', 1, { quantity: 2, finish: 'foil' });
    await controlScryfall(request, { fail: 503 });
    await gotoSignedIn(page, '/vault');
    await expect(page.getByTestId('entry')).toContainText('Lightning Bolt');
    await page.getByTestId('edit').click();
    await page.locator('#entry-quantity').fill('3');
    await page.getByTestId('submit').click();
    await expect(page.getByTestId('entry-quantity')).toHaveText('3');
    await expectNoSeriousViolations(page);
  });
});
