import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import type { Page } from '@playwright/test';

/**
 * Record/replay for Scryfall (CON-09): E2E tests never reach the real service.
 *
 * Replay is the default: a request is answered from `e2e/fixtures/scryfall/<key>.json`, and a
 * request without a fixture is blocked and reported in `unexpected` (assert it with
 * `expectNoUnmockedScryfall`). To add a fixture, run the test once with `E2E_RECORD=1`: the real
 * response is fetched a single time, stored, and replayed from then on. Be polite when recording:
 * the Scryfall rules (User-Agent, <= 10 requests per second) apply.
 */
const FIXTURES = join(__dirname, '..', 'fixtures', 'scryfall');
const SCRYFALL = /^https:\/\/([a-z0-9-]+\.)?scryfall\.(com|io)\//;

interface Fixture {
  readonly status: number;
  readonly contentType: string;
  readonly body: string;
}

export interface ScryfallMock {
  readonly served: string[];
  readonly unexpected: string[];
}

export function fixtureFile(url: string): string {
  const { pathname, search } = new URL(url);
  const slug = pathname
    .replace(/[^a-z0-9]+/gi, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase();
  const digest = createHash('sha1')
    .update(pathname + search)
    .digest('hex')
    .slice(0, 10);
  return join(FIXTURES, `${slug}-${digest}.json`);
}

export async function mockScryfall(page: Page): Promise<ScryfallMock> {
  const mock: ScryfallMock = { served: [], unexpected: [] };
  const recording = process.env['E2E_RECORD'] === '1';

  await page.route(SCRYFALL, async (route) => {
    const url = route.request().url();
    const file = fixtureFile(url);

    if (!existsSync(file) && recording) {
      const response = await route.fetch({
        headers: {
          'User-Agent': 'MTGCardVault-E2E/0.1',
          Accept: 'application/json;q=0.9,*/*;q=0.8',
        },
      });
      const fixture: Fixture = {
        status: response.status(),
        contentType: response.headers()['content-type'] ?? 'application/json',
        body: await response.text(),
      };
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, JSON.stringify(fixture, null, 2) + '\n');
    }

    if (!existsSync(file)) {
      mock.unexpected.push(url);
      await route.abort('blockedbyclient');
      return;
    }

    const fixture = JSON.parse(readFileSync(file, 'utf-8')) as Fixture;
    mock.served.push(url);
    await route.fulfill({
      status: fixture.status,
      contentType: fixture.contentType,
      body: fixture.body,
      headers: { 'access-control-allow-origin': '*' },
    });
  });

  return mock;
}

export function expectNoUnmockedScryfall(mock: ScryfallMock): void {
  if (mock.unexpected.length > 0) {
    throw new Error(
      `Scryfall requests without a fixture (record them with E2E_RECORD=1):\n${mock.unexpected.join('\n')}`,
    );
  }
}
