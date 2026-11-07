import http from 'node:http'; import crypto from 'node:crypto'; import fs from 'node:fs'; import path from 'node:path';
import { chromium } from 'playwright';
const root = path.resolve('dist/frontend/browser'); const csp = process.argv[2] ?? '';
const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' };
const server = http.createServer((req, res) => {
  let file = path.join(root, new URL(req.url, 'http://x').pathname);
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, 'index.html');
  let body = fs.readFileSync(file); const headers = { 'content-type': types[path.extname(file)] ?? 'application/octet-stream' };
  if (csp) { const n = crypto.randomBytes(16).toString('hex'); headers['content-security-policy'] = csp.replaceAll('__NONCE__', n); if (file.endsWith('.html')) body = Buffer.from(body.toString().replaceAll('__CSP_NONCE__', n)); }
  res.writeHead(200, headers).end(body);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch(); const page = await (await browser.newContext()).newPage();
await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: 'networkidle' });
await page.getByTestId('open-add').click(); await page.locator('clr-modal .modal-dialog').waitFor();
await page.getByTestId('save').click(); await page.waitForTimeout(800);
const info = await page.evaluate(() => { const e = document.querySelector('clr-control-error'); if (!e) return 'no clr-control-error element'; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return { text: e.textContent.trim().slice(0, 50), display: cs.display, visibility: cs.visibility, opacity: cs.opacity, h: r.height, w: r.width, parentClass: e.parentElement?.className }; });
console.log(csp ? 'WITH CSP' : 'NO CSP', JSON.stringify(info));
await browser.close(); server.close();
