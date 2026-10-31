# MTG Card Vault — frontend

Angular (latest) + VMware Clarity. Architecture: `docs/05-architecture.md` §5.3.

```bash
npm ci                    # install locked dependencies
npm run api:generate      # regenerate src/app/api from ../backend/openapi.json (never hand-edit)
npm start                 # dev server on :4200, proxies API paths to localhost:8000
npm run lint
npm run test:coverage     # unit tests (Vitest) + coverage/frontend/lcov.info
npm run build
npm run e2e               # Playwright against a running stack (E2E_BASE_URL, default http://127.0.0.1:8080)
```

The API client in `src/app/api/` is generated from the backend's OpenAPI document; CI regenerates it and fails when it differs from what is committed (FR-API-01).

## Skeleton status

The page only shows the greeting from the temporary `GET /hello` route (issue #1). It is replaced by the real shell in issue #9.
