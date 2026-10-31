# 02 — User Stories

**Docs set version:** 0.1.0
**Document:** 02 User Stories (Connextra format, INVEST, Gherkin acceptance criteria)
**Status:** Draft
**Last updated:** 2026-10-31

How to read this document: each story states **who** wants **what** and **why**, with its priority (MoSCoW), target release, the requirements it realises (`FR-*`/`NFR-*`, defined in `03-requirements-specification.md`) and the use cases that describe its flows (`UC-*`, `04-use-cases.md`). Acceptance criteria are written as Gherkin scenarios and become automated tests. Each `Requirements:` line must exactly match the traceability matrix (`06`) — the sync check enforces this.

## 1. Personas and actors

| Persona | Description |
|---|---|
| **Collector** | A person who owns physical MTG cards and wants a private, accurate, priced inventory. Comfortable with a browser; may have thousands of cards. Primary user. |
| **Operator** | The person who deploys and runs the stack (docker compose, Authelia, SonarQube). |
| **Maintainer** | A developer working on this repository (writes code, docs, tests, pipelines). |
| **Scheduler** | Non-human actor (a timed job in the worker) that refreshes prices. |

## 2. Glossary shortcuts

*Printing* = a specific card in a specific set, collector number and language (one Scryfall id). *Finish* = nonfoil / foil / etched. *Condition* = NM, LP, MP, HP, DMG. *Vault* = the collector's set of entries. Full glossary: `03` Appendix A.

## 3. Epics

| ID | Epic | Goal | Stories |
|---|---|---|---|
| EP-01 | Identity & Access | Only authenticated people use the app; each has an isolated account. | US-001 … US-004, US-032 |
| EP-02 | Vault Management | Maintain the private inventory of owned cards. | US-005 … US-011 |
| EP-03 | Catalogue | Find any MTG card/printing from Scryfall data. | US-012 … US-014 |
| EP-04 | Card Scanning | Add cards by showing them to a webcam. | US-015 … US-019 |
| EP-05 | Pricing & Valuation | Know what the collection is worth, with fresh prices. | US-020 … US-023 |
| EP-06 | Platform, Quality & Experience | Secure, observable, deployable, well-engineered product with a consistent UI. | US-024 … US-031, US-033 |

## 4. Story format and conventions

- Statement: *As a \<persona\>, I want \<capability\>, so that \<benefit\>.*
- Stories follow **INVEST** (Independent, Negotiable, Valuable, Estimable, Small, Testable).
- Scenarios use `Given / When / Then`. "the API" always means the back end under `/api/v1`.
- Every user-facing story also inherits the cross-cutting criteria in section 11.

---

## 5. EP-01 — Identity & Access

### US-001 — Sign in with Authelia
- **Epic:** EP-01
- **Priority:** Must
- **Release:** 0.2.0
- **Requirements:** FR-AUTH-01, NFR-SEC-01
- **Use cases:** UC-01

**As a** Collector, **I want** to sign in through my Authelia account, **so that** I access my private vault without creating yet another password.

Acceptance criteria:
```gherkin
Scenario: Unauthenticated visitor is sent to Authelia
  Given I am not signed in
  When I open the application
  Then I am redirected to the Authelia login page using the authorization code flow with PKCE

Scenario: Successful sign in
  Given I authenticated successfully at Authelia
  When I am redirected back to the application
  Then I see my vault page and my display name
  And the access token is not stored in localStorage

Scenario: Failed or cancelled sign in
  Given I cancel or fail authentication at Authelia
  When I return to the application
  Then I see a sign-in-required page with a button to retry
```

### US-002 — Sign out
- **Epic:** EP-01
- **Priority:** Must
- **Release:** 0.2.0
- **Requirements:** FR-AUTH-02
- **Use cases:** UC-09

**As a** Collector, **I want** to sign out, **so that** nobody using my computer afterwards can see my vault.

```gherkin
Scenario: Sign out ends the session
  Given I am signed in
  When I choose "Sign out"
  Then the application discards my tokens
  And my Authelia session is ended
  And opening a protected page sends me to the sign-in flow again
```

### US-003 — Stay signed in while I work
- **Epic:** EP-01
- **Priority:** Should
- **Release:** 0.2.0
- **Requirements:** FR-AUTH-03
- **Use cases:** UC-01

**As a** Collector, **I want** my session renewed automatically while I am active, **so that** I am not interrupted in the middle of scanning a pile of cards.

```gherkin
Scenario: Token renewed silently
  Given my access token is about to expire and my session is still valid
  When I continue using the application
  Then a new access token is obtained without a visible login
  And the interrupted request is retried once

Scenario: Session really expired
  Given my Authelia session or refresh token has expired
  When a request needs a new token
  Then I am sent to sign in again and returned to the page I was on
```

### US-004 — My account is created automatically on first login
- **Epic:** EP-01
- **Priority:** Must
- **Release:** 0.2.0
- **Requirements:** FR-AUTH-04
- **Use cases:** UC-01

**As a** Collector, **I want** the application to create my account the first time I sign in, **so that** I need no registration step.

```gherkin
Scenario: First login provisions a user
  Given my Authelia identity (subject) is unknown to the application
  When I make my first authenticated API call
  Then a user record keyed by my subject claim is created
  And later calls reuse it without creating duplicates

Scenario: Concurrent first calls
  Given two first requests arrive at the same time
  Then exactly one user record exists afterwards
```

### US-032 — Delete my account and all my data
- **Epic:** EP-01
- **Priority:** Should
- **Release:** 1.0.0
- **Requirements:** FR-AUTH-08, NFR-PRV-01
- **Use cases:** UC-11

**As a** Collector, **I want** to delete my account together with my vault, **so that** I stay in control of my personal data.

```gherkin
Scenario: Account deletion
  Given I am signed in
  When I confirm "Delete my account" by typing my username
  Then all my vault entries and my user record are permanently deleted
  And I am signed out
  And shared cached card data is kept because it is not personal data
```

---

## 6. EP-02 — Vault Management

### US-005 — Add a card to my vault
- **Epic:** EP-02
- **Priority:** Must
- **Release:** 0.4.0
- **Requirements:** FR-VLT-01, FR-CAT-04, FR-DAT-02
- **Use cases:** UC-03, UC-02

**As a** Collector, **I want** to add a specific printing with quantity, condition and finish to my vault, **so that** my inventory mirrors my physical cards.

```gherkin
Scenario: Add by choosing a printing
  Given I selected a printing of "Lightning Bolt" in the catalogue
  When I add it with quantity 2, condition "NM" and finish "foil"
  Then my vault contains one entry for that printing with quantity 2, NM, foil
  And the card's data is cached locally

Scenario: Finish not available for the printing
  Given the printing exists only as nonfoil
  When I try to add it as foil
  Then the API rejects the request with a validation error naming the allowed finishes

Scenario: Invalid quantity
  When I add a card with quantity 0 or above 9999
  Then the request is rejected with a validation error
```

### US-006 — See my vault
- **Epic:** EP-02
- **Priority:** Must
- **Release:** 0.4.0
- **Requirements:** FR-VLT-02, NFR-PRF-01, NFR-PRF-03
- **Use cases:** UC-06

**As a** Collector, **I want** to see a paginated list of everything I own, **so that** I know my collection at a glance.

```gherkin
Scenario: Paginated list
  Given my vault has 250 entries
  When I open the vault with page size 50
  Then I see the first 50 entries with image, name, set, collector number, finish, condition, quantity and unit price
  And pagination controls show 5 pages

Scenario: Empty vault
  Given my vault has no entries
  When I open the vault
  Then I see an empty state offering "Scan a card" and "Search the catalogue"
```

### US-007 — Edit an entry
- **Epic:** EP-02
- **Priority:** Must
- **Release:** 0.4.0
- **Requirements:** FR-VLT-03
- **Use cases:** UC-04

**As a** Collector, **I want** to change the quantity, condition or finish of an entry, **so that** corrections and new purchases are reflected.

```gherkin
Scenario: Change quantity
  Given an entry with quantity 1
  When I set the quantity to 3
  Then the entry shows quantity 3 and its updated timestamp changes

Scenario: Edit would duplicate another entry
  Given I own the same printing as NM and as LP
  When I change the LP entry to NM
  Then the two entries merge into one whose quantity is the sum (see US-010)
```

### US-008 — Remove an entry
- **Epic:** EP-02
- **Priority:** Must
- **Release:** 0.4.0
- **Requirements:** FR-VLT-04
- **Use cases:** UC-05

**As a** Collector, **I want** to remove an entry, **so that** cards I sold or gave away leave my inventory.

```gherkin
Scenario: Remove with confirmation
  Given an entry in my vault
  When I choose remove and confirm
  Then the entry is deleted and the list and value update

Scenario: Remove something already removed
  Given the entry no longer exists
  When I try to remove it
  Then I get a "not found" message and the list refreshes
```

### US-009 — Find cards inside my vault
- **Epic:** EP-02
- **Priority:** Should
- **Release:** 0.4.0
- **Requirements:** FR-VLT-05
- **Use cases:** UC-06

**As a** Collector, **I want** to search, filter and sort my vault, **so that** I can find a card or a group of cards fast.

```gherkin
Scenario: Search by name
  Given my vault contains "Lightning Bolt" and "Lightning Helix"
  When I search "bolt"
  Then only "Lightning Bolt" entries are listed

Scenario: Filter and sort
  When I filter by set "MH2" and rarity "mythic" and sort by price descending
  Then only matching entries are listed, most valuable first
```

### US-010 — Duplicate entries merge
- **Epic:** EP-02
- **Priority:** Must
- **Release:** 0.4.0
- **Requirements:** FR-VLT-06
- **Use cases:** UC-03, UC-02

**As a** Collector, **I want** adding a card I already track (same printing, condition and finish) to increase its quantity, **so that** my vault has no duplicate rows.

```gherkin
Scenario: Adding an existing combination
  Given I own 2 × "Sol Ring" (printing X, NM, nonfoil)
  When I add 1 more of the same printing, NM, nonfoil
  Then there is still one entry with quantity 3

Scenario: Different condition is a different entry
  When I add the same printing as LP
  Then a second entry is created
```

### US-011 — My vault is private
- **Epic:** EP-02
- **Priority:** Must
- **Release:** 0.4.0
- **Requirements:** FR-VLT-07
- **Use cases:** —

**As a** Collector, **I want** my vault invisible and unmodifiable to everyone else, **so that** my collection stays confidential.

```gherkin
Scenario: Cannot read another user's entry
  Given user B owns entry E
  When user A requests E by id
  Then the API answers 404 Not Found

Scenario: Lists only contain my entries
  Given users A and B both have entries
  When A lists the vault
  Then only A's entries are returned
```

---

## 7. EP-03 — Catalogue

### US-012 — Search for cards
- **Epic:** EP-03
- **Priority:** Must
- **Release:** 0.3.0
- **Requirements:** FR-CAT-01
- **Use cases:** UC-10

**As a** Collector, **I want** to search all MTG cards by name, **so that** I can find a card I want to add or look up.

```gherkin
Scenario: Search by partial name
  When I search "black lotus"
  Then results list matching cards with image, name, type line and set count

Scenario: No results
  When I search for a nonsense string
  Then I see a "no cards found" empty state
```

### US-013 — Narrow search with filters
- **Epic:** EP-03
- **Priority:** Should
- **Release:** 0.3.0
- **Requirements:** FR-CAT-02
- **Use cases:** UC-10

**As a** Collector, **I want** to filter by set, colour, type and rarity, **so that** I can narrow large result sets.

```gherkin
Scenario: Combine filters
  When I search "dragon" with colour "red" and rarity "rare"
  Then every result is a red rare card whose name matches "dragon"
```

### US-014 — See card details and all printings
- **Epic:** EP-03
- **Priority:** Must
- **Release:** 0.3.0
- **Requirements:** FR-CAT-03, FR-CAT-04
- **Use cases:** UC-10

**As a** Collector, **I want** a detail page with every printing of a card, **so that** I can pick the exact version I own.

```gherkin
Scenario: Card detail
  When I open a card
  Then I see its image, name, mana cost, type line, oracle text, rarity, set, collector number and prices

Scenario: Choose among printings
  Given a card has 40 printings
  Then I can list them with set, collector number, language and finishes
  And select one to add to my vault
```

---

## 8. EP-04 — Card Scanning

### US-015 — Open my camera
- **Epic:** EP-04
- **Priority:** Must
- **Release:** 0.5.0
- **Requirements:** FR-SCN-01, NFR-CMP-01
- **Use cases:** UC-02

**As a** Collector, **I want** to start my webcam from the app, **so that** I can show a card to it.

```gherkin
Scenario: Permission granted
  When I open the Scan page and allow the camera
  Then I see a live preview with a card-shaped guide overlay

Scenario: Permission denied or no camera
  When the camera cannot be used
  Then I see an explanation and a link to manual search (US-019)

Scenario: Several cameras
  Given more than one camera is present
  Then I can choose the device and my choice is remembered in the browser
```

### US-016 — Recognise a card from the camera
- **Epic:** EP-04
- **Priority:** Must
- **Release:** 0.5.0
- **Requirements:** FR-SCN-02, FR-SCN-03, FR-SCN-04, NFR-PRF-02
- **Use cases:** UC-02

**As a** Collector, **I want** to capture the card in the guide and get the likely matches, **so that** I do not type its name.

```gherkin
Scenario: Clear capture
  Given a card is aligned in the guide
  When I press "Scan"
  Then within 5 seconds (p90) I see up to 5 candidate printings ordered by confidence
  And the text the OCR read (title, set code, collector number) is shown

Scenario: Unreadable capture
  When OCR cannot read a title
  Then I am told the card could not be read and can retry or search manually

Scenario: Collector number and set code improve the match
  Given OCR also read set code and collector number
  Then the exact printing is ranked first
```

### US-017 — Confirm the scanned card before it is added
- **Epic:** EP-04
- **Priority:** Must
- **Release:** 0.5.0
- **Requirements:** FR-SCN-05
- **Use cases:** UC-02

**As a** Collector, **I want** to review and confirm the match (and set condition, finish, quantity), **so that** wrong OCR never pollutes my vault.

```gherkin
Scenario: Confirm a candidate
  Given candidates are displayed
  When I select one, choose condition NM, finish foil, quantity 1 and confirm
  Then it is added (or merged, per US-010) and the camera is ready for the next card

Scenario: Nothing is added without confirmation
  When I leave the page without confirming
  Then my vault is unchanged
```

### US-018 — Scanning is private and bounded
- **Epic:** EP-04
- **Priority:** Must
- **Release:** 0.5.0
- **Requirements:** FR-SCN-06, FR-SCN-08, NFR-SEC-07, NFR-PRV-01
- **Use cases:** UC-02

**As a** Collector, **I want** my camera images never stored, **so that** my privacy is protected; **as an** Operator, **I want** uploads limited, **so that** the service cannot be abused.

```gherkin
Scenario: Image is not persisted
  When a scan is processed
  Then no image bytes are written to disk, database, logs or caches
  And only the recognised text and chosen card are retained if I confirm

Scenario: Oversized or invalid upload
  When a file larger than 2 MB, not a JPEG/PNG/WebP, or larger than 4096 px in any dimension is sent
  Then the API rejects it with 413 or 415 or 422 before any OCR runs

Scenario: Scan rate limit
  When I send more than 30 scans in one minute
  Then the API answers 429 with a Retry-After header
```

### US-019 — Fall back to manual search while adding
- **Epic:** EP-04
- **Priority:** Must
- **Release:** 0.5.0
- **Requirements:** FR-SCN-07
- **Use cases:** UC-02, UC-03

**As a** Collector, **I want** a manual search whenever the scan fails or is wrong, **so that** I can always finish adding a card.

```gherkin
Scenario: Switch to manual from the candidate list
  Given none of the candidates is my card
  When I choose "None of these — search manually"
  Then the catalogue search opens pre-filled with the text OCR read
```

---

## 9. EP-05 — Pricing & Valuation

### US-020 — See current prices
- **Epic:** EP-05
- **Priority:** Must
- **Release:** 0.6.0
- **Requirements:** FR-PRC-01, FR-PRC-02
- **Use cases:** UC-06, UC-08

**As a** Collector, **I want** each card to show its current market price, **so that** I know which cards matter.

```gherkin
Scenario: Price matches finish
  Given an entry is foil and Scryfall lists a foil price
  Then the entry shows the foil unit price and the price timestamp

Scenario: No price available
  Given Scryfall has no price for that finish
  Then the entry shows "no price" and is flagged as unpriced
```

### US-021 — Know my collection's total value
- **Epic:** EP-05
- **Priority:** Must
- **Release:** 0.6.0
- **Requirements:** FR-PRC-03
- **Use cases:** UC-07

**As a** Collector, **I want** a summary of my collection's value and size, **so that** I understand what I own.

```gherkin
Scenario: Totals
  Given entries with known prices
  Then the summary shows total cards, distinct printings and total value (USD and EUR)
  And value = sum(unit price for the entry's finish × quantity)

Scenario: Incomplete data is disclosed
  Given 12 entries have no price
  Then the summary says "12 entries unpriced — total is a lower bound"
```

### US-022 — Prices refresh daily by themselves
- **Epic:** EP-05
- **Priority:** Must
- **Release:** 0.6.0
- **Requirements:** FR-PRC-04
- **Use cases:** UC-08

**As an** Operator, **I want** a scheduled job to refresh prices of all cached cards each day, **so that** values stay current with no manual work.

```gherkin
Scenario: Scheduled refresh
  Given the schedule is daily at 04:00 UTC (configurable)
  When the Scheduler runs
  Then all cached cards owned by at least one user are refreshed in batches of up to 75 identifiers
  And the Scryfall rate limit is respected
  And a log line reports counts of updated, unchanged and failed cards

Scenario: Partial failure
  When some batches fail
  Then successful batches are kept, failures are retried with backoff and reported in the log
```

### US-023 — Stale prices refresh when I look at them
- **Epic:** EP-05
- **Priority:** Should
- **Release:** 0.6.0
- **Requirements:** FR-PRC-05
- **Use cases:** UC-07, UC-10

**As a** Collector, **I want** prices older than 24 hours refreshed when I view them, **so that** I never act on stale data.

```gherkin
Scenario: Lazy refresh
  Given a card's prices are older than 24 hours
  When I open its detail or the vault summary
  Then the API refreshes the stale cards in the background
  And the page shows the latest data on next load without blocking
```

---

## 10. EP-06 — Platform, Quality & Experience

### US-024 — The app obeys Scryfall's rules
- **Epic:** EP-06
- **Priority:** Must
- **Release:** 0.3.0
- **Requirements:** FR-DAT-01, FR-DAT-02, NFR-LEG-01
- **Use cases:** UC-02, UC-08, UC-10

**As an** Operator, **I want** all Scryfall calls to go through one compliant client, **so that** the service is never banned and the legal terms are respected.

```gherkin
Scenario: Compliant requests
  Then every Scryfall request carries a descriptive User-Agent and an Accept header
  And consecutive requests are spaced by at least 100 ms
  And HTTP 429 responses trigger exponential backoff honouring Retry-After

Scenario: Attribution
  Then the UI footer states that card data is provided by Scryfall and that the app is unofficial Fan Content
```

### US-025 — The app keeps working when Scryfall is down
- **Epic:** EP-06
- **Priority:** Should
- **Release:** 0.3.0
- **Requirements:** FR-DAT-03, NFR-REL-01
- **Use cases:** UC-06, UC-10

**As a** Collector, **I want** to keep viewing my vault when Scryfall is unavailable, **so that** outages elsewhere do not lock me out.

```gherkin
Scenario: Vault readable during outage
  Given Scryfall is unreachable
  When I open my vault
  Then entries are shown from the local cache with the last known prices marked as stale

Scenario: Catalogue search during outage
  Then search shows a clear "catalogue temporarily unavailable" message, not a stack trace
```

### US-026 — Every API call is authenticated, and only my front end may call it
- **Epic:** EP-06
- **Priority:** Must
- **Release:** 0.2.0
- **Requirements:** FR-AUTH-05, FR-AUTH-06, FR-AUTH-07, NFR-SEC-01, NFR-SEC-06
- **Use cases:** —

**As an** Operator, **I want** the API to reject any request without a valid Authelia-issued JWT and to allow browser calls only from the configured front-end origin, **so that** the data is protected.

```gherkin
Scenario: Missing token
  When a request to /api/v1/vault/entries has no Authorization header
  Then the API answers 401 with a WWW-Authenticate: Bearer header

Scenario Outline: Invalid token
  When the token <defect>
  Then the API answers 401
  Examples:
    | defect                              |
    | is expired                          |
    | has a wrong issuer                  |
    | has an audience other than the API  |
    | has an invalid signature            |
    | uses alg "none" or a disallowed alg |

Scenario: Foreign origin
  When a browser on an origin not in the allow-list calls the API
  Then the CORS preflight is refused

Scenario: Public endpoints are only health checks
  Then only /healthz and /readyz (and the OpenAPI docs in non-production) are reachable without a token
```

### US-027 — A typed, documented API contract
- **Epic:** EP-06
- **Priority:** Must
- **Release:** 0.1.0
- **Requirements:** FR-API-01, FR-API-02
- **Use cases:** —

**As a** Maintainer, **I want** a versioned REST API with an OpenAPI document and uniform errors, **so that** the Angular client is generated, not hand-written, and failures are predictable.

```gherkin
Scenario: Contract is published
  Then GET /api/v1/openapi.json describes every endpoint and schema
  And the front-end API client is generated from it in CI and drift fails the build

Scenario: Uniform error body
  When any request fails
  Then the response is application/problem+json (RFC 9457) with type, title, status, detail and a correlation id
```

### US-028 — Observable and health-checked
- **Epic:** EP-06
- **Priority:** Should
- **Release:** 0.1.0
- **Requirements:** FR-OPS-01, FR-OPS-02
- **Use cases:** —

**As an** Operator, **I want** health endpoints and structured logs, **so that** I can monitor and debug the service.

```gherkin
Scenario: Liveness and readiness
  Then GET /healthz returns 200 when the process is up
  And GET /readyz returns 200 only when the database is reachable, else 503

Scenario: Safe logs
  Then logs are JSON with a correlation id per request
  And never contain tokens, passwords, image data or full email addresses
```

### US-029 — Deploy everything with one command
- **Epic:** EP-06
- **Priority:** Must
- **Release:** 0.1.0
- **Requirements:** FR-OPS-03, NFR-SEC-02, NFR-SEC-05, NFR-REL-02, NFR-PRT-01
- **Use cases:** —

**As an** Operator, **I want** `docker compose up` to start the proxy, Authelia, API, worker, front end and database with configuration from environment files, **so that** I can deploy and upgrade safely.

```gherkin
Scenario: Fresh deployment
  Given a copied .env from .env.example with secrets filled in
  When I run docker compose up -d
  Then all services become healthy, database migrations run automatically, and the app is served over HTTPS

Scenario: Hardened containers
  Then images run as non-root, have no known High/Critical vulnerabilities and contain no secrets
```

### US-030 — Quality and security gates block bad changes
- **Epic:** EP-06
- **Priority:** Must
- **Release:** 0.1.0
- **Requirements:** NFR-SEC-03, NFR-SEC-04, NFR-SEC-05, NFR-MNT-01, NFR-MNT-02, NFR-MNT-03, NFR-MNT-04, NFR-TST-01
- **Use cases:** —

**As a** Maintainer, **I want** the CI pipeline to run tests, linters, SonarQube and security scans on every pull request and refuse to merge on failure, **so that** quality is not optional.

```gherkin
Scenario: Pull request checks
  When I open a pull request to develop or main
  Then CI runs lint, type checks, unit, integration, contract and end-to-end tests
  And SonarQube analysis, dependency audits (pip-audit, npm audit), secret scanning and container scanning
  And merging is blocked unless every required check passes

Scenario: Commit and branch policy
  Then commit messages follow Conventional Commits and branch names follow gitflow, else the check fails
```

### US-031 — Documentation can never drift
- **Epic:** EP-06
- **Priority:** Must
- **Release:** 0.1.0
- **Requirements:** NFR-DOC-01
- **Use cases:** —

**As a** Maintainer (or an LLM assistant), **I want** the documentation set mechanically checked for consistency, **so that** it stays a trustworthy specification.

```gherkin
Scenario: Sync check
  When CI runs scripts/check_docs_sync.py
  Then it fails if IDs are undefined, links are asymmetric across documents, or versions differ
```

### US-033 — A consistent, accessible interface
- **Epic:** EP-06
- **Priority:** Should
- **Release:** 1.0.0
- **Requirements:** NFR-USA-01, NFR-USA-02, NFR-USA-03, NFR-USA-04
- **Use cases:** —

**As a** Collector, **I want** an interface that follows the Clarity design language and is accessible, **so that** it is familiar, usable by everyone and works on my tablet.

```gherkin
Scenario: Design compliance
  Then only Clarity components, tokens and layouts are used; custom styling does not override Clarity semantics

Scenario: Accessibility
  Then pages pass automated axe checks with no serious or critical violations
  And all functions are keyboard-operable with visible focus
  And the layout works from 768 px width upward (phones best effort)
```

---

## 11. Cross-cutting acceptance criteria (apply to every story)

- Every UI state has loading, empty and error views using Clarity patterns.
- Errors are displayed in plain language; technical details only in logs with the correlation id.
- No story is done until: automated tests exist for each scenario, coverage gate on new code passes, SonarQube gate passes, docs and traceability are updated, and `scripts/check_docs_sync.py` passes.

## 12. Backlog ordering rule

Order by release in each story. Within a release, take **Must** before **Should** before **Could**. Anything not listed is out of scope (`01` §5.2).
