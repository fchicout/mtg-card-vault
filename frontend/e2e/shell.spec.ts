import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

/**
 * Application shell (issue #9, NFR-USA-01..03, NFR-LEG-01, FR-API-02). The API is mocked at the
 * network edge so these tests need only the front end; they also run against the full stack.
 */
const ROUTES = [
  '/',
  '/vault',
  '/catalogue',
  '/scan',
  '/account',
  '/signin-required',
  '/no-such-page',
];
const THEMES = ['light', 'dark'] as const;

async function mockGreeting(page: Page): Promise<void> {
  await page.route('**/hello', (route) =>
    route.fulfill({ json: { message: 'Hello, MTG Vault!' } }),
  );
}

async function useTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((value) => localStorage.setItem('mtgvault.theme', value), theme);
}

async function seriousViolations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return result.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
}

for (const theme of THEMES) {
  test.describe(`${theme} theme`, () => {
    for (const route of ROUTES) {
      test(`${route}: accessible, with the legal footer`, async ({ page }) => {
        await mockGreeting(page);
        await useTheme(page, theme);
        await page.goto(route);
        await expect(page.locator('h1')).toBeVisible();
        await expect(page.locator('body')).toHaveAttribute('cds-theme', theme);

        const footer = page.getByTestId('footer');
        await expect(footer).toContainText('Scryfall');
        await expect(footer).toContainText('unofficial Fan Content');
        await expect(footer).toContainText('not approved or endorsed by Wizards of the Coast');

        expect(await seriousViolations(page)).toEqual([]);
      });
    }
  });
}

test.describe('navigation', () => {
  test.beforeEach(async ({ page }) => mockGreeting(page));

  test('the four sections are reachable and mark the current page', async ({ page }) => {
    await page.goto('/');
    for (const [name, path] of [
      ['Vault', '/vault'],
      ['Catalogue', '/catalogue'],
      ['Scan', '/scan'],
      ['Account', '/account'],
    ] as const) {
      await page
        .getByRole('navigation', { name: 'Main navigation' })
        .getByRole('link', { name })
        .click();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(page.locator('h1')).toHaveText(name);
      await expect(page).toHaveTitle(`${name} - MTG Card Vault`);
    }
  });

  test('works at 768 px: no horizontal scrolling, the navigation is usable and accessible', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto('/vault');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await expect(
      page
        .getByRole('navigation', { name: 'Main navigation' })
        .getByRole('link', { name: 'Catalogue' }),
    ).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test('can be operated with the keyboard alone', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).toBeTruthy();
    await page.getByRole('link', { name: 'Scan' }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/scan$/);
  });

  test('the theme switch works with Enter and with Space', async ({ page }) => {
    await page.goto('/');
    const toggle = page.getByTestId('theme-toggle');
    const read = () => page.locator('body').getAttribute('cds-theme');
    const start = await read();
    await toggle.focus();
    await page.keyboard.press('Space');
    const afterSpace = await read();
    expect(afterSpace).not.toBe(start);
    await page.keyboard.press('Enter');
    expect(await read()).toBe(start);
  });

  test('the theme can be switched and is remembered', async ({ page }) => {
    await page.goto('/');
    const before = await page.locator('body').getAttribute('cds-theme');
    await page.getByTestId('theme-toggle').click();
    const after = await page.locator('body').getAttribute('cds-theme');
    expect(after).not.toBe(before);
    await page.reload();
    await expect(page.locator('body')).toHaveAttribute('cds-theme', after!);
  });
});

test.describe('API errors (FR-API-02)', () => {
  test('a problem document becomes a plain-language alert with the correlation id in the details', async ({
    page,
  }) => {
    await page.route('**/hello', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/problem+json',
        json: {
          type: 'urn:mtgvault:problem:upstream-unavailable',
          title: 'Service Unavailable',
          status: 503,
          detail: 'Scryfall is down.',
          correlation_id: 'e2e-corr-503',
        },
      }),
    );
    await page.goto('/');

    const alert = page.getByTestId('alert-message');
    await expect(alert).toHaveText(/not available\. Try again in a moment\./);
    await expect(alert).not.toContainText('Scryfall is down');
    await expect(page.getByTestId('correlation-id')).toBeHidden();
    await page.getByTestId('alert-details').locator('summary').click();
    await expect(page.getByTestId('correlation-id')).toHaveText('e2e-corr-503');
    await expect(page.getByTestId('error')).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test('an unreachable API is explained, and retry loads the greeting', async ({ page }) => {
    let calls = 0;
    await page.route('**/hello', (route) => {
      calls += 1;
      return calls === 1
        ? route.abort('connectionrefused')
        : route.fulfill({ json: { message: 'Hello, MTG Vault!' } });
    });
    await page.goto('/');
    await expect(page.getByTestId('alert-message')).toContainText('cannot be reached');
    await page.getByTestId('retry').click();
    await expect(page.getByTestId('greeting')).toHaveText('Hello, MTG Vault!');
  });
});
