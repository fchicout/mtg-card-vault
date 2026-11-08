import { expect, test } from '@playwright/test';

import { OIDC, accessToken, bearer, emptyVault } from './support/tokens';
import { scryfallIsUp, stubCardImages } from './support/cards';
import { gotoSignedIn, signIn } from './support/session';

/** US-011: a second signed-in user sees nothing of the first user's vault and cannot touch it. */
test.afterEach(async ({ request }) => {
  // The provider's session must not stay on user 2 for the next file.
  await request.post(`${OIDC}/__control`, { data: { reset: true } }).catch(() => undefined);
});

test.beforeEach(async ({ request }, testInfo) => {
  testInfo.skip(!(await scryfallIsUp(request)), 'the Scryfall test double is not running');
  await emptyVault(request, 'user-1');
  await emptyVault(request, 'user-2');
});

test('@UC-06 user 2 sees an empty vault and cannot read, change or remove user 1 entries', async ({
  page,
  request,
}) => {
  const ada = bearer(await accessToken(request, 'user-1'));
  const cards = await (
    await request.get('/api/v1/catalog/cards', { headers: ada, params: { q: 'lightning bolt' } })
  ).json();
  const card = cards.items[1].id;
  const created = await request.post('/api/v1/vault/entries', {
    headers: ada,
    data: { card_id: card, quantity: 3, finish: 'foil' },
  });
  expect(created.status()).toBe(201);
  const entryId = (await created.json()).id as string;

  const grace = bearer(await accessToken(request, 'user-2'));
  const theirs = await (await request.get('/api/v1/vault/entries', { headers: grace })).json();
  expect(theirs.items).toEqual([]);
  expect(
    (
      await request.patch(`/api/v1/vault/entries/${entryId}`, {
        headers: grace,
        data: { quantity: 1 },
      })
    ).status(),
  ).toBe(404);
  expect(
    (await request.delete(`/api/v1/vault/entries/${entryId}`, { headers: grace })).status(),
  ).toBe(404);
  const foreign = await request.post('/api/v1/vault/entries', {
    headers: grace,
    data: { card_id: card, quantity: 1, finish: 'foil', user_id: 'someone-else' },
  });
  expect(foreign.status()).toBe(422);

  // In the browser as user 2: an empty vault, not user 1's.
  await stubCardImages(page);
  await request.post(`${OIDC}/__control`, { data: { next_login: 'user-2' } });
  await signIn(page);
  await expect(page.getByTestId('user-name')).toContainText('Grace');
  await gotoSignedIn(page, '/vault');
  await expect(page.getByTestId('empty')).toContainText('Your vault is empty');

  const intact = await (await request.get('/api/v1/vault/entries', { headers: ada })).json();
  expect(intact.items[0].quantity).toBe(3);
});
