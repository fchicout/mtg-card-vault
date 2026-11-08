import { expect, test } from '@playwright/test';

/**
 * Transport and browser security of the stack (issue #10, NFR-SEC-06, ADR-009, ADR-016).
 * Runs against the real stack: TLS and HSTS come from the proxy, the other headers and the CSP
 * nonce from the front-end server. Skipped when the target is a plain dev server (no TLS).
 */
const HTTP_URL = process.env['E2E_HTTP_URL'] ?? 'http://localhost:8080';

test.describe('security headers', () => {
  test.beforeEach(({ baseURL }, testInfo) => {
    testInfo.skip(!baseURL?.startsWith('https://'), 'needs the HTTPS stack (proxy in front)');
  });

  test('the page carries the complete set', async ({ request }) => {
    const response = await request.get('/vault');
    const h = response.headers();

    const csp = h['content-security-policy'] ?? '';
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain('https://cards.scryfall.io');
    expect(csp).not.toContain('unsafe-inline');
    expect(csp).not.toContain('unsafe-eval');

    expect(h['x-content-type-options']).toBe('nosniff');
    expect(h['x-frame-options']).toBe('DENY');
    expect(h['referrer-policy']).toBe('strict-origin-when-cross-origin');
    expect(h['permissions-policy']).toContain('camera=(self)');
    expect(h['strict-transport-security']).toMatch(/max-age=\d+/);
    expect(h['cache-control']).toBe('no-store');
    expect(h['server']).toBeUndefined();
  });

  test('static files and API answers carry the headers too', async ({ request }) => {
    const page = await (await request.get('/')).text();
    const script = /src="(main-[^"]+\.js)"/.exec(page)?.[1];
    expect(script).toBeTruthy();
    for (const path of [`/${script}`, '/healthz']) {
      const h = (await request.get(path)).headers();
      expect(h['x-content-type-options'], path).toBe('nosniff');
      expect(h['content-security-policy'], path).toContain("default-src 'self'");
    }
  });

  test('every response gets its own nonce, written into the page and the header alike', async ({
    request,
  }) => {
    const nonces = new Set<string>();
    for (let i = 0; i < 3; i++) {
      const response = await request.get('/');
      const headerNonce = /'nonce-([a-f0-9]+)'/.exec(
        response.headers()['content-security-policy'] ?? '',
      )?.[1];
      const pageNonce = /ngcspnonce="([^"]+)"/i.exec(await response.text())?.[1];
      expect(headerNonce).toBeTruthy();
      expect(pageNonce).toBe(headerNonce);
      nonces.add(headerNonce!);
    }
    expect(nonces.size).toBe(3);
  });

  test('plain HTTP only redirects to HTTPS and keeps the path', async ({ request, baseURL }) => {
    const response = await request.get(`${HTTP_URL}/vault?x=1`, { maxRedirects: 0 });
    expect([301, 302, 307, 308]).toContain(response.status());
    const location = response.headers()['location'] ?? '';
    expect(location.startsWith('https://')).toBe(true);
    expect(location).toContain('/vault?x=1');
    expect(new URL(location).port).toBe(new URL(baseURL!).port);
  });
});

test.describe('the content security policy in a real browser', () => {
  test.beforeEach(({ baseURL }, testInfo) => {
    testInfo.skip(!baseURL?.startsWith('https://'), 'needs the HTTPS stack (proxy in front)');
  });

  for (const theme of ['light', 'dark'] as const) {
    test(`no route violates the policy (${theme} theme)`, async ({ page }) => {
      const violations: string[] = [];
      const problems: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error' || /content security policy/i.test(message.text())) {
          problems.push(message.text().slice(0, 200));
        }
      });
      await page.addInitScript((value) => {
        localStorage.setItem('mtgvault.theme', value);
        document.addEventListener('securitypolicyviolation', (event) => {
          (window as unknown as { __csp: string[] }).__csp = [
            ...((window as unknown as { __csp?: string[] }).__csp ?? []),
            `${event.effectiveDirective} <- ${event.blockedURI || 'inline'}`,
          ];
        });
      }, theme);

      for (const route of [
        '/',
        '/vault',
        '/catalogue',
        '/scan',
        '/account',
        '/signin-required',
        '/missing',
      ]) {
        await page.goto(route);
        await expect(page.locator('h1')).toBeVisible();
        violations.push(
          ...((await page.evaluate(
            () => (window as unknown as { __csp?: string[] }).__csp ?? [],
          )) as string[]),
        );
      }
      expect(violations).toEqual([]);
      expect(problems).toEqual([]);
    });
  }
});
