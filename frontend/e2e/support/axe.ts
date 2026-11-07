import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

/** WCAG 2.1 level A and AA, the bar of NFR-USA-02. */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/** Serious and critical findings on the current page, one readable line each. */
export async function seriousViolations(page: Page): Promise<string[]> {
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations
    .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
    .map(
      (violation) =>
        `${violation.impact} ${violation.id}: ${violation.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
    );
}

/** Fails the test, listing every serious or critical accessibility violation on the page. */
export async function expectNoSeriousViolations(page: Page): Promise<void> {
  const found = await seriousViolations(page);
  if (found.length > 0) {
    throw new Error(`Accessibility violations (serious/critical):\n${found.join('\n')}`);
  }
}
