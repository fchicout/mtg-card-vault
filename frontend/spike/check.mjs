// Throwaway spike for issue #3: serve the production build under a CSP, drive it in Chromium,
// report console errors, CSP violations and axe findings. Usage: node spike/check.mjs "<csp>"
import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const root = path.resolve('dist/frontend/browser');
const csp = process.argv[2] ?? '';
const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.ico': 'image/x-icon', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x').pathname;
  let file = path.join(root, url);
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, 'index.html');
  const headers = { 'content-type': types[path.extname(file)] ?? 'application/octet-stream' };
  let body = fs.readFileSync(file);
  if (csp) {
    // What the production proxy does: one random nonce per response, in the header and the page.
    const nonce = crypto.randomBytes(16).toString('hex');
    headers['content-security-policy'] = csp.replaceAll('__NONCE__', nonce);
    if (file.endsWith('.html')) body = Buffer.from(body.toString().replaceAll('__CSP_NONCE__', nonce));
  }
  res.writeHead(200, headers).end(body);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
const consoleErrors = [];
const hashes = new Set();
page.on('console', (m) => { if (!['error', 'warning'].includes(m.type())) return; consoleErrors.push(`${m.type()}: ${m.text().slice(0, 200)}`); for (const h of m.text().matchAll(/'(sha256-[^']+)'/g)) hashes.add(h[1]); });
page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message.slice(0, 200)}`));
await page.addInitScript(() => {
  window.__csp = [];
  document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.effectiveDirective} <- ${e.blockedURI || 'inline'} ${(e.sample ?? '').replace(/\s+/g, ' ')}`.slice(0, 110)));
});

const steps = [];
const ok = (name, cond) => steps.push(`${cond ? 'PASS' : 'FAIL'}  ${name}`);

await page.goto(base + '/', { waitUntil: 'networkidle' });
ok('redirects to /vault and renders the datagrid', (await page.locator('[data-testid=grid] clr-dg-row').count()) === 10);
ok('header, vertical nav and main landmark present', (await page.locator('header, clr-vertical-nav, main').count()) >= 3);

// datagrid: sort, filter, paginate
await page.getByRole('button', { name: /^Name$/ }).first().click();
await page.locator('clr-dg-pagination button.pagination-next').click();
await page.waitForFunction(() => /11 - 20 of 37/.test(document.querySelector('clr-dg-pagination')?.textContent.replace(/\s+/g, ' ') ?? ''), null, { timeout: 3000 }).catch(() => {});
const pagText = (await page.locator('clr-dg-pagination').innerText()).replace(/\s+/g, ' ');
ok(`pagination moves to page 2 (${pagText.slice(0, 60)})`, /11 - 20 of 37/.test(pagText));

// modal + form validation
await page.getByTestId('open-add').click();
await page.locator('clr-modal .modal-dialog').waitFor();
ok('modal opens', await page.locator('clr-modal .modal-dialog').isVisible());
await page.getByTestId('save').click();
await page.getByText('The name is required').waitFor({ timeout: 3000 }).catch(() => {});
ok('required validation message is shown', await page.getByText('The name is required').isVisible());
await page.getByTestId('name').fill('Black Lotus');
await page.getByLabel('Foil', { exact: true }).check();
await page.getByTestId('save').click();
await page.locator('clr-modal .modal-dialog').waitFor({ state: 'detached' }).catch(() => {});
ok('saving closes the modal and shows the alert', await page.getByTestId('added-alert').isVisible());

// keyboard: Escape closes the modal, focus returns
await page.getByTestId('open-add').focus();
await page.keyboard.press('Enter');
await page.locator('clr-modal .modal-dialog').waitFor();
await page.keyboard.press('Escape');
await page.locator('clr-modal .modal-dialog').waitFor({ state: 'detached' }).catch(() => {});
ok('Escape closes the modal', (await page.locator('clr-modal .modal-dialog').count()) === 0);

// theme toggle
await page.getByTestId('theme').click();
ok('dark theme applied', (await page.evaluate(() => document.body.getAttribute('cds-theme'))) === 'dark');
const darkAxe = await new AxeBuilder({ page }).analyze();
await page.getByTestId('theme').click();
const lightAxe = await new AxeBuilder({ page }).analyze();

const brief = (r) => r.violations.map((v) => `${v.impact} ${v.id} (${v.nodes.length}): ${v.nodes.slice(0, 2).map((n) => n.target.join(' ') + ' => ' + (n.any[0]?.message ?? '').slice(0, 140)).join(' | ')}`);
const csps = await page.evaluate(() => window.__csp);
const inlineScripts = await page.evaluate(() => [...document.scripts].filter((s) => !s.src).length);

console.log(`CSP: ${csp || '(none)'}`);
console.log(steps.join('\n'));
console.log(`inline <script> elements: ${inlineScripts}`);
console.log(`CSP violations (${csps.length}): ${JSON.stringify([...new Set(csps)])}`);
console.log(`console errors/warnings (${consoleErrors.length}): ${JSON.stringify([...new Set(consoleErrors)])}`);
console.log(`blocked hashes: ${JSON.stringify([...hashes])}`);
console.log(`axe light: ${JSON.stringify(brief(lightAxe))}`);
console.log(`axe dark : ${JSON.stringify(brief(darkAxe))}`);
await browser.close();
server.close();
