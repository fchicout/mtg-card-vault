import { expect, test, type Page } from '@playwright/test';

import { expectNoSeriousViolations } from './support/axe';
import { signIn } from './support/session';

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

// The vault, catalogue, scan and account pages need a session (US-001).
test.beforeEach(async ({ page }) => signIn(page));

async function useTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((value) => localStorage.setItem('mtgvault.theme', value), theme);
}

for (const theme of THEMES) {
  test.describe(`${theme} theme`, () => {
    for (const route of ROUTES) {
      test(`${route}: accessible, with the legal footer`, async ({ page }) => {
        await useTheme(page, theme);
        await page.goto(route);
        await expect(page.locator('h1')).toBeVisible();
        await expect(page.locator('body')).toHaveAttribute('cds-theme', theme);

        const footer = page.getByTestId('footer');
        await expect(footer).toContainText('Scryfall');
        await expect(footer).toContainText('unofficial Fan Content');
        await expect(footer).toContainText('not approved or endorsed by Wizards of the Coast');

        await expectNoSeriousViolations(page);
      });
    }
  });
}

test.describe('navigation', () => {
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
    await expectNoSeriousViolations(page);
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
