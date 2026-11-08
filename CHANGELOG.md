## [0.5.0] - 2026-11-08

### Bug fixes
- **pricing:** Clear the SonarQube findings of the pricing code (c2e1ec6)
- **pricing:** Set the prices through the worker in the journeys and split assertions (3317afe)


### Build
- **deploy:** Run the worker in the default stack with a heartbeat healthcheck (a409c97)


### Documentation
- **arch:** Currency policy, money rules, pricing design and worker notes (e834c33)


### Features
- **pricing:** Line value and EUR unit price on vault entries (f0dbd20)
- **vault:** Collection summary endpoint with totals, value and unpriced count (3c9050f)
- **scryfall:** Batch lookup of up to 75 cards and a double that serves it (f024e8d)
- **db:** Select owned cards and refresh their snapshots in one statement (cf57a4c)
- **pricing:** Refresh service for the prices of all owned cards (42cea1d)
- **pricing:** Daily price refresh job with a standard-cron schedule (4f225b5)
- **pricing:** Refresh stale prices after the response with one refresh per card (9001caf)
- **ui:** Collection value summary, prices and line values with stale notes in the vault (c2bb310)
- **ui:** Price freshness for the owner and the price source on the card page (8a934fa)


### Tests
- **vault:** List, summary and stale lookup budgets at 10,000 entries (451b2cd)
- **e2e:** Pricing journeys with the real worker and the Scryfall double (d7cc143)


## [0.4.0] - 2026-11-08

### Bug fixes
- **scan:** Clear the SonarQube findings of the scan code (00eb185)
- **scan:** Rank a front-face name match above the same name on a back face (7bc3dae)
- **ui:** Fall back to any camera when the rear camera or size is refused (cade082)
- **ui:** Enable the scan button only when the camera preview has a frame (b6a5c6b)
- **ui:** Attach the camera stream once the preview exists (f430db0)
- **e2e:** Give the serial journeys the same fake camera as Chromium (60b5abc)
- **e2e:** Look for the confirmation dialog by its role (e6ad1bb)


### Build
- **deploy:** Ship Tesseract in the API image and test it for real in CI (c32f1e1)


### Documentation
- **scan:** Record the OCR decision, scan design and settings (cf65bb7)


### Features
- **scan:** Interpret OCR text into a clean title and a collector number (e076678)
- **scan:** Validate uploads by size, magic bytes and dimensions (0ad7872)
- **scan:** Limit scans per user with a sliding window behind an interface (7142d17)
- **scan:** Preprocess frames and extract the title and collector regions (fc51dce)
- **scan:** Add the TextRecognizer port and the Tesseract adapter (9c2f391)
- **scan:** Resolve candidates against Scryfall and rank by confidence (997a3fe)
- **scan:** Add the scan service and POST /api/v1/scans (e067c19)
- **ui:** Scan with the camera, pick a match, confirm and add to the vault (d3351f3)


### Tests
- **scan:** Add the OCR reference set, degradation levels and accuracy harness (d23bbe6)
- **e2e:** The scan journey through the fake camera, real API and Tesseract (766e841)
- **scan:** Accuracy and latency budgets measured every night (1eeb0d8)


## [0.3.0] - 2026-11-08

### Bug fixes
- **scryfall:** Clear the SonarQube new-code issues of the adapter work (5fc54b8)
- **catalog:** Clear the SonarQube new-code issues of the catalogue API (432199a)
- **catalog:** Name the repeated message of the stand-in card source (6ba1f7e)
- **auth:** A completed sign-in lets later reloads restore the session again (a97b9d4)
- **ui:** Read form values as strings only (d074d0a)
- **ui:** Render the side menu with Clarity's vertical navigation and polish the catalogue (1f6c64a)
- **vault:** Clear the SonarQube new-code issues of the vault backend (37b7c28)
- **ui:** Register Clarity's core global before @clr/angular creates its own (3189e32)


### CI
- **github:** Allow the commit scopes scryfall and resilience (ec0f938)


### Documentation
- **catalog:** Document the card model and the Scryfall adapter (fd10a1b)
- **catalog:** Document the catalogue API and the query rules (f66bfe6)
- **catalog:** Document the catalogue pages and journeys (cb46ba1)
- **arch:** Record the navigation fix, admin enforcement and Dependabot decision (5a13da7)
- **vault:** Document persistence, rules, endpoints, isolation and outage behaviour (2d8fb3d)
- **vault:** Document the vault pages, dialogs and journeys (f715b3f)


### Features
- **catalog:** Card domain model, provider and cache ports, in-memory fake (1aa5bd5)
- **resilience:** Circuit breaker with half-open probe (7c6d5e5)
- **catalog:** Bounded TTL cache with single-flight loading (d0b6a0f)
- **scryfall:** Compliant client with spacing, allow-list, backoff and typed errors (cc60497)
- **scryfall:** Mapper, provider and recorded fixtures for every card layout (52e6958)
- **scryfall:** Settings, composition root wiring and the double in the E2E overlay (72d1436)
- **catalog:** Safe query translation with strict filter validation (5aba0a1)
- **catalog:** Catalogue service and the search, detail and printings endpoints (7ddbada)
- **frontend:** Generated client gains the catalogue operations (0c41739)
- **ui:** Catalogue search page with filters kept in the address (8d6ec1f)
- **ui:** Card detail page with printings and a disabled Add-to-vault entry point (5fb8379)
- **scryfall:** Configurable circuit-breaker open time (a6d9cbe)
- **db:** Cards and vault_entries tables, rules in the database, snapshot repository (2632cb3)
- **vault:** User-scoped vault repository and validated list queries (20f98a7)
- **vault:** Vault service and the add, list, edit and remove endpoints (e1382b4)
- **frontend:** Generated client gains the vault operations (c1175f9)
- **ui:** Vault page with paging, search, filters and sorting kept in the address (086267f)
- **ui:** Add to vault from the card page with a shared entry form (f7aac2b)


### Refactoring
- **catalog:** Use the ResultPage name in the catalogue API (eff4060)


### Tests
- **e2e:** Catalogue journeys and the Scryfall outage and throttling journeys (6c39a3b)
- **security:** Vault isolation suite, outage behaviour and the 10,000-entry benchmark (6b685cd)
- **e2e:** Vault journeys and the privacy journey; serial specs chained as projects (6f326d4)
- **auth:** The OIDC double keeps a single-sign-on-like session (4a56e39)
- **db:** Migration round-trip tests follow the newest revision (d0331ca)
- **ui:** Install the ResizeObserver stub in beforeAll (f1c0cc9)
- **ui:** One setup file for Clarity's global and the ResizeObserver stub (41bf179)

# Changelog

All notable changes, generated from Conventional Commits.

## [0.2.0] - 2026-11-08

### Bug fixes
- **ci:** Publish SHA-tagged images from a final ci.yml job (3fdce99)
- **auth:** Clear the SonarQube new-code issues of the JWT work (b893d91)
- **auth:** Clear the SonarQube new-code issues of the identity work (c533526)
- **frontend:** Clear the SonarQube new-code issues of the sign-in work (97cdbaf)
- **e2e:** Shared writable certificate volume and a modern TLS context for the OIDC double (a87d0c2)
- **frontend:** Restore the session at start-up on every page, not only behind the guard (2e9f067)
- **ci:** Publish images on pushes although the pull-request-only commit-policy job is skipped (c182321)


### Documentation
- **arch:** Align stories and architecture with the external identity provider (b8023b0)
- **auth:** Document JWT validation, OIDC settings and the removed skeleton route (5798e50)
- **auth:** Document the principal and claim mapping (b050d6c)
- **db:** Document the users table and provisioning rules (eb43a63)
- **auth:** Document GET /api/v1/me and provisioning (12854aa)
- **arch:** Document the OIDC test double and the E2E overlay (24c1875)
- **auth:** Document the SPA sign-in design and run-time settings (27368ac)
- **auth:** Document renewal, the identity journeys and the operator guide for the identity provider (7b928a2)


### Features
- **auth:** Validate bearer JWTs against the provider's JWKS and protect /api/v1 (e12e684)
- **deploy:** Post-deploy smoke check script (5c91820)
- **auth:** Principal built from verified claims with data minimisation (89fb0a2)
- **db:** Users table and race-safe user repository (dc38b4f)
- **auth:** Provision the user on the first authenticated request and expose GET /api/v1/me (2e3a6ff)
- **frontend:** Generated client gains getMe; E2E checks the 401 challenge (c61b0c3)
- **frontend:** Sign in with authorization code and PKCE, tokens in memory only (9778549)
- **frontend:** Route guard, sign-in page with retry, user menu and sign-out (5f11127)
- **security:** Allow only the identity provider's origin in connect-src (076fea1)
- **frontend:** Silent renewal with refresh rotation, single-flight refresh and one retry on 401 (e4c18dd)


### Refactoring
- **frontend:** Drop the skeleton greeting, regenerate the API client (f0d8a8f)


### Tests
- **auth:** Deterministic OIDC provider for unit, integration and E2E tests (87c2f28)
- **e2e:** Add the OIDC double to the E2E stack and call the API with its tokens (221649f)
- **e2e:** Sign-in and sign-out journeys, CSP and CORS assertions (b731a14)
- **auth:** OIDC double reports grant counts and can fail the next login (3a52da0)
- **e2e:** Identity journeys for sign-in, renewal, revoked or failing refresh, cancel and sign-out (5e4fdea)
- **auth:** The OIDC double issues an id_token with the nonce, like a real provider (975601f)
- **e2e:** Wait for the provider round trip after a full page load (eecc029)
- **e2e:** Serve the OIDC double over HTTPS with a generated certificate (30798c4)

# Changelog

All notable changes, generated from Conventional Commits.
## [0.1.0] - 2026-11-08

### Bug fixes
- **deploy:** Remove pip and upgrade OS packages in runtime images (e8461c4)
- **deploy:** Upgrade OS packages in the backend runtime image (5930a4c)
- **deploy:** Bind to loopback by default; the image opts in to all interfaces via BIND_HOST (a9eedb2)
- **deploy:** Store the dev Authelia state in a named volume so it also starts under rootful Docker (288c05d)
- **ui:** Make the theme switch respond to the Space key like a button (4926951)
- **api:** Clear the SonarQube new-code issues in the backend (f6076b3)
- **frontend:** Clear the SonarQube new-code issues in the frontend (55abd49)


### Build
- **deploy:** Non-root images and minimal compose stack for the skeleton (847b9fd)
- **frontend:** Bump Clarity to 18.5.0 (supports Angular 21.1 and 22) (3f29235)
- **arch:** Stricter import contracts for adapters, cross-cutting helpers and the composition root (4eb4707)
- **deploy:** Ship migrations in the API image and start through mtgvault.serve (30509e9)
- **frontend:** Do not inline critical CSS so the production page has no inline code (d4417f7)
- **repo:** Declare the MIT licence in the package metadata (8ba2305)
- **frontend:** Add Angular i18n, the localize polyfill, Playwright axe and an extract target (047f489)
- **deps:** Bump the npm-minor-and-patch group across 1 directory with 4 updates (2276fed)
- **deps-dev:** Bump the npm-minor-and-patch group (341f55a)


### CI
- Add documentation sync check script (5349986)
- **gates:** Project-owned quality gate and local gate runner (d48f833)
- **github:** CI workflow and SonarQube project configuration (db56880)
- **sonar:** Use the official scan action with pinned SHAs; show Sonar's own gate as information only (f1800a4)
- **sonar:** Sonar-frontend job uses its own project token SONAR_FRONTEND_TOKEN (c162e7e)
- **gates:** Explain why an optional SonarQube read is SKIPPED (HTTP status and message) (0a2e6d8)
- **deploy:** Publish SHA-tagged images and deploy develop to staging and main to production (5ae6258)
- **gates:** List the offending SonarQube issues when the gate fails (42c0a3d)
- **deploy:** Publish images only, never deploy; ADR-015 amended (docs set 0.3.1) (d6bdbad)
- **docs:** Scan pull-request commits and code markers; enforce 90 % coverage of the sync script (8755ae8)
- **ci:** Commit-policy job, commit-msg hook and git-cliff dry-run targets (5f7089a)
- **ci:** Pinned scanners, exceptions, SARIF upload, CodeQL, nightly rescan and SBOMs (31501bb)
- **release:** Tag-triggered release with scanned multi-arch images, notes and SBOMs (01d93da)
- **ci:** Run the Authelia round trip so the token contract is checked on every change (daf83a2)
- **ci:** Fail when the extracted i18n messages are stale, in CI and in the local gates (8f2de1a)
- **ci:** Use the i18n message comparison in CI and in the local gates (2386eb4)
- **ci:** Run the e2e suite on three browsers against the ci profile and keep failure artifacts (826dbf3)
- **ci:** Run e2e through the HTTPS proxy and scan the stack's third-party images (3b478f3)
- **ci:** Scan every third-party image of the stack before failing (164726c)
- **ci:** Report third-party image findings as warnings; keep the gate on our own images (b39ec9b)
- **deps:** Bump SonarSource/sonarqube-scan-action from 8.1.0 to 8.4.1 (d971557)
- **deps:** Bump actions/checkout from 4.3.1 to 7.0.1 (246981a)
- **deps:** Bump actions/download-artifact from 4 to 8 (9597178)
- **deps:** Bump setup-node, upload-artifact and setup-uv in every workflow (cebde1f)
- **deps:** Keep Node on LTS and TypeScript with Angular; maintain the compose image pins (c849c16)


### Chores
- Initialize repository (fe58a05)
- **repo:** Add .gitignore for Python, Node and local tooling (181fa3e)
- **dev:** Make docs-check, make docs-coverage and a pre-commit hook for the docs sync (3bea7f1)
- **repo:** Add the MIT licence, README and editor config (a6fa4fe)
- **repo:** Add issue and pull-request templates, CODEOWNERS and Dependabot (64aee5a)
- **ui:** Refresh the recorded source locations of the extracted messages (65e9d36)
- **security:** Time-box the Go toolchain findings of the dev Authelia image until 2027-01-06 (a153a6d)


### Documentation
- Add synchronized engineering documentation set (172e367)
- Quality gates are project-owned; document CI jobs (docs set 0.2.0) (81a676a)
- Record verified Sonar CI status in OQ-08 (docs set 0.2.3) (4d31f3b)
- ADR-015 staging and production environments over HTTPS (docs set 0.3.0) (07b5222)
- Document backend foundations and LOG_LEVEL (docs set 0.3.2) (c28abd8)
- ADR-005 notes and backup/restore stub (docs set 0.3.3) (6ad85ee)
- Keep docs set 0.3.2 after merging develop (changelog order) (ea16fa8)
- Pin Angular 22.2 + Clarity 18.5 (ADR-009), CSP recipe, resolve OQ-01 (docs set 0.3.4) (ec42fe4)
- Docs-sync gate hardening (docs set 0.3.5) (e06347f)
- Release tooling decided - git-cliff with manual tags; policy conventions (docs set 0.3.6) (5280568)
- DevSecOps policy, exceptions process and CI table (docs set 0.3.7) (0af4485)
- Release pipeline behaviour and the gitflow release procedure (docs set 0.3.8) (f84fb1b)
- Authelia spike results - ADR-003 verified, sign-out without end-session (docs set 0.3.9) (4bfdb6a)
- **repo:** Add CONTRIBUTING, SECURITY and CODE_OF_CONDUCT as signposts into the docs set (8ec13ed)
- Resolve OQ-06 (MIT) and define the role of root files (docs set 0.3.10) (5c6019c)
- Application shell, error patterns, i18n and accessibility checks (docs set 0.3.11) (464c9b2)
- I18n drift compares messages, not line numbers (4b30247)
- E2E harness and the single dev Authelia definition (docs set 0.3.12) (458a568)
- ADR-016 Caddy edge, OQ-03 resolved, operator quickstart (docs set 0.3.13) (7507480)
- Sign-in uses the homelab Authelia and its per-environment clients (docs set 0.3.13) (af72388)
- SonarQube topology final, OQ-08 resolved, hotspot follow-up recorded (3625877)
- The gate follows SonarQube's retirement of hotspots (docs set 0.3.15) (71a4032)
- **gates:** Amend ADR-011, SonarQube's own gate decides (a634ab9)


### Features
- **skeleton:** Backend hello-world slice with health endpoints (1002fd8)
- **skeleton:** Angular + Clarity hello page with generated API client (7f9f61c)
- **core:** Fail-fast settings, correlation id, redacting JSON logs and RFC 9457 errors (991da0d)
- **db:** SQLAlchemy base, unit of work, Alembic baseline and migrate-then-serve entry point (ab73baf)
- **ci:** Commit-message, branch-name and tag policy checker with unit tests (f10040f)
- **docs-sync:** Warn on unknown IDs in commits and Implements markers; unit tests at 96 % coverage (0e93a44)
- **ci:** Time-boxed security exceptions with a fail-on-expiry checker (99 % covered) (9622f6d)
- **deploy:** Development Authelia with an SPA client and a PKCE round-trip verifier (a9409a3)
- **ui:** Error interceptor with plain-language alerts, notifications, theme and state patterns (852a246)
- **ui:** Clarity application shell with lazy routes, legal footer and extracted messages (261c96b)
- **ci:** Compare i18n messages ignoring source line numbers, with unit tests (20b7660)
- **deploy:** Ci compose profile with the dev Authelia and a seeded-user sign-in sample (cdd2130)
- **deploy:** Idle worker process for the scheduled-jobs slot (eb1f629)
- **deploy:** Nonce-based CSP and security headers in nginx, digest-pinned bases (1792762)
- **deploy:** Caddy HTTPS edge, internal database network, hardened services and complete env (7546a98)
- **gates:** Count open issues by security impact and drop the deprecated hotspot condition (918ccca)
- **gates:** Print the conditions SonarQube's own gate has in error, for information (ee94e66)
- **gates:** SonarQube's own quality gate decides too (9d695f1)


### Refactoring
- **deploy:** Use the homelab Authelia, remove the bundled dev identity provider (fdac824)


### Tests
- **e2e:** Playwright hello-world journey against the compose stack (c88f453)
- **e2e:** Axe on every route in both themes, 768 px, keyboard, theme and API error alerts (27267d8)
- **e2e:** Browser matrix, fake camera, Scryfall record/replay, shared axe helper and artifacts (23bff94)
- **e2e:** Security headers, nonce, redirect and CSP-violation checks over HTTPS (42288d6)

