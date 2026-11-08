import { expect, type APIRequestContext, type Page } from '@playwright/test';

/** The Scryfall test double of the E2E stack (deploy/compose.e2e.yaml). */
export const SCRYFALL = process.env['E2E_SCRYFALL_URL'] ?? 'http://localhost:9100';

// A 1x1 PNG: card images come from Scryfall's CDN, which tests never contact.
const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

export async function stubCardImages(page: Page): Promise<void> {
  await page.route('https://cards.scryfall.io/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL }),
  );
}

export interface LoggedRequest {
  path: string;
  query: Record<string, string>;
  user_agent: string | null;
  accept: string | null;
  at: number;
}

export async function requestLog(request: APIRequestContext): Promise<LoggedRequest[]> {
  const response = await request.get(`${SCRYFALL}/__requests`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function controlScryfall(
  request: APIRequestContext,
  change: Record<string, unknown>,
): Promise<void> {
  expect((await request.post(`${SCRYFALL}/__control`, { data: change })).ok()).toBeTruthy();
}

export async function scryfallIsUp(request: APIRequestContext): Promise<boolean> {
  return request
    .get(`${SCRYFALL}/__requests`)
    .then((r) => r.ok())
    .catch(() => false);
}
