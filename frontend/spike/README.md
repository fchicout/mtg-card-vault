# Clarity compatibility spike (issue #3) - throwaway, never merged

Evidence branch for ADR-009. Sample: Clarity shell (header, vertical nav, theme toggle), datagrid
(sort, filter, pagination), modal, validated reactive form, alert, icons.

```bash
npm ci
npm i --no-save @axe-core/playwright && npx playwright install chromium
npm run build
node spike/check.mjs "<csp with __NONCE__ placeholder>"
```

`check.mjs` serves `dist/` like the production proxy would (a fresh nonce per response replaces
`__CSP_NONCE__` in the HTML and `__NONCE__` in the header), drives the page in Chromium and reports
functional steps, CSP violations, console messages and axe findings in both themes.
The CSP that passes with zero violations is recorded in docs/05 section 8.2.
