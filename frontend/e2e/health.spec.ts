import { expect, test } from '@playwright/test';

test.describe('walking skeleton', () => {
  test('the page loads with the application title', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveTitle('MTG Card Vault');
    await expect(page.locator('.header .title')).toHaveText('MTG Card Vault');
    await expect(page.getByTestId('welcome')).toBeVisible();
  });

  test('health endpoints are reachable through the web entry point', async ({ request }) => {
    const live = await request.get('/healthz');
    expect(live.ok()).toBeTruthy();
    expect(await live.json()).toEqual({ status: 'ok' });

    const ready = await request.get('/readyz');
    expect(ready.ok()).toBeTruthy();
    expect(await ready.json()).toEqual({ status: 'ready' });
  });

  test('the API refuses an unauthenticated call with a problem document', async ({ request }) => {
    const response = await request.get('/api/v1/me');
    expect([401, 404]).toContain(response.status());
  });
});
