import { expect, test } from '@playwright/test';

test.describe('walking skeleton', () => {
  test('the page shows the greeting served by the API through the generated client', async ({
    page,
  }) => {
    await page.goto('/');

    await expect(page).toHaveTitle('MTG Card Vault');
    await expect(page.locator('header .title')).toHaveText('MTG Card Vault');
    await expect(page.getByTestId('greeting')).toHaveText('Hello, MTG Vault!');
  });

  test('shows an error alert when the API is unreachable', async ({ page }) => {
    await page.route('**/hello', (route) => route.abort('connectionrefused'));

    await page.goto('/');

    await expect(page.getByTestId('error')).toHaveText('The API could not be reached.');
    await expect(page.getByTestId('greeting')).toHaveCount(0);
  });

  test('health endpoints are reachable through the web entry point', async ({ request }) => {
    const live = await request.get('/healthz');
    expect(live.ok()).toBeTruthy();
    expect(await live.json()).toEqual({ status: 'ok' });

    const ready = await request.get('/readyz');
    expect(ready.ok()).toBeTruthy();
    expect(await ready.json()).toEqual({ status: 'ready' });
  });
});
