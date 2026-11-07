import { expect, test } from '@playwright/test';

import { expectNoSeriousViolations, seriousViolations } from './support/axe';
import {
  BACKGROUND_LUMA,
  CARD,
  CARD_LUMA,
  CAMERA_HEIGHT,
  CAMERA_WIDTH,
} from './support/fake-camera';
import { expectNoUnmockedScryfall, mockScryfall } from './support/scryfall';

/** Proves the shared E2E tooling itself (issue #12): each helper works, and fails when it should. */
test.beforeEach(async ({ page }) => {
  await page.route('**/hello', (route) =>
    route.fulfill({ json: { message: 'Hello, MTG Vault!' } }),
  );
});

test.describe('axe helper', () => {
  test('passes on the clean shell', async ({ page }) => {
    await page.goto('/vault');
    await expect(page.locator('h1')).toBeVisible();
    await expectNoSeriousViolations(page);
  });

  test('fails on a seeded violation and names the rule', async ({ page }) => {
    await page.goto('/vault');
    await page.evaluate(() =>
      document
        .querySelector('main')!
        .insertAdjacentHTML('beforeend', '<img src="x.png"><button></button>'),
    );
    const found = await seriousViolations(page);
    expect(found.join('\n')).toContain('image-alt');
    expect(found.join('\n')).toContain('button-name');
    await expect(expectNoSeriousViolations(page)).rejects.toThrow(/Accessibility violations/);
  });
});

test.describe('Scryfall record/replay', () => {
  test('replays a recorded response, and the real service is never contacted', async ({ page }) => {
    const scryfall = await mockScryfall(page);
    await page.goto('/');
    const card = await page.evaluate(async () => {
      const response = await fetch('https://api.scryfall.com/cards/named?fuzzy=lightning+bolt');
      return (await response.json()) as { name: string; object: string };
    });
    expect(card).toMatchObject({ object: 'card', name: 'Lightning Bolt' });
    expect(scryfall.served).toHaveLength(1);
    expectNoUnmockedScryfall(scryfall);
  });

  test('a request without a fixture is blocked and reported', async ({ page }) => {
    const scryfall = await mockScryfall(page);
    await page.goto('/');
    const outcome = await page.evaluate(() =>
      fetch('https://api.scryfall.com/cards/named?fuzzy=not-recorded').then(
        () => 'reached',
        () => 'blocked',
      ),
    );
    expect(outcome).toBe('blocked');
    expect(scryfall.unexpected).toEqual([
      'https://api.scryfall.com/cards/named?fuzzy=not-recorded',
    ]);
    expect(() => expectNoUnmockedScryfall(scryfall)).toThrow(/without a fixture/);
  });
});

test.describe('fake camera (Chromium)', () => {
  test.skip(
    ({ browserName }) => browserName !== 'chromium',
    'the fake-device flags exist only in Chromium',
  );

  test('delivers real, changing frames of the fixture card to getUserMedia', async ({ page }) => {
    await page.goto('/');
    const result = await page.evaluate(
      async ({ card, size }) => {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        const video = document.createElement('video');
        video.muted = true;
        video.srcObject = stream;
        await video.play();

        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d', { willReadFrequently: true })!;
        const markers = new Set<string>();
        let centre = 0;
        let corner = 0;
        for (let i = 0; i < 12; i++) {
          await new Promise((resolve) => setTimeout(resolve, 90));
          context.drawImage(video, 0, 0);
          const px = (x: number, y: number) => context.getImageData(x, y, 1, 1).data[0];
          centre = px(card.x + card.width / 2, card.y + card.height / 2);
          corner = px(size.width - 6, size.height - 6);
          // The marker steps right each frame: record its leading edge to see frames change.
          for (let x = 0; x < 80; x++) {
            if (px(x, 10) > 100) {
              markers.add(String(x));
              break;
            }
          }
        }
        const settings = stream.getVideoTracks()[0].getSettings();
        stream.getTracks().forEach((track) => track.stop());
        return {
          width: video.videoWidth,
          height: video.videoHeight,
          settings,
          centre,
          corner,
          distinctFrames: markers.size,
        };
      },
      { card: CARD, size: { width: CAMERA_WIDTH, height: CAMERA_HEIGHT } },
    );

    expect(result.width).toBe(CAMERA_WIDTH);
    expect(result.height).toBe(CAMERA_HEIGHT);
    expect(result.centre).toBeGreaterThan(CARD_LUMA - 40); // the bright card is in the middle
    expect(result.corner).toBeLessThan(BACKGROUND_LUMA + 40); // and the dark scene around it
    expect(result.distinctFrames).toBeGreaterThan(1); // successive frames differ: it is a live stream
  });
});
