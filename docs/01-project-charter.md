# 01 — Project Charter

**Docs set version:** 0.2.0
**Document:** 01 Project Charter (PMBOK template)
**Status:** Draft
**Last updated:** 2026-10-31
**Owner:** fchicout (Sponsor, Product Owner, Lead Developer)
**Repository:** https://github.com/fchicout/mtg-card-vault

---

## 1. Project identification

| Field | Value |
|---|---|
| Project name | MTG Card Vault |
| Working title / repo | `mtg-card-vault` |
| One-line description | A self-hosted, multi-user web application in which *Magic: The Gathering* collectors keep a private, accurate and priced inventory of their cards, adding cards by showing them to a webcam. |
| Project type | Greenfield software product (also a showcase of engineering practice) |
| Start date | 2026-10-31 |
| Target v1.0 | Not date-bound; milestone-driven (section 10) |
| Budget | None (personal / open-source effort; only self-hosted infrastructure the owner already has) |
| Methodology | Iterative; scope driven by user stories; documentation-first (see `docs/README.md` synchronization mandate) |

## 2. Business case and problem statement

### 2.1 Background

*Magic: The Gathering* (MTG) is a collectible card game with more than 25,000 distinct cards and ~100,000 printings (the same card printed in different sets, languages and finishes). Serious collectors own hundreds to tens of thousands of physical cards. Each physical card is identified by its **printing** (set + collector number + language), its **finish** (nonfoil, foil, etched) and its **condition** (Near Mint … Damaged); its market value depends on all of these and changes daily.

### 2.2 Problems this project solves

| # | Problem | Consequence today |
|---|---|---|
| P1 | Collectors track inventory in spreadsheets, notebooks or memory. | Duplicate purchases, no overview, no insurance-grade inventory. |
| P2 | Entering cards by hand is slow and error-prone (wrong printing, typos, wrong finish). | People give up cataloguing; data is inaccurate. |
| P3 | Card data (names, sets, legalities, images) and prices go stale in a static list. | Collection value is unknown or wrong. |
| P4 | Hosted collection managers require trusting a third party with the whole collection and an account. | Privacy concern; vendor lock-in; recurring cost; features behind paywalls. |
| P5 | Many hobby tools lack engineering rigor (no tests, no security checks). | Fragile, insecure, unmaintainable software. |

### 2.3 Proposed solution (summary)

A web application (Angular + VMware Clarity front end, Python/FastAPI REST back end, PostgreSQL) that:

1. lets an authenticated collector (Authelia single sign-on) maintain a **private vault** of owned cards (printing, quantity, condition, finish);
2. lets the collector **add a card by holding it in front of a webcam**: the back end reads the printed text with OCR, matches it against **Scryfall** (the public MTG database/API) using fuzzy search, and the user confirms the exact printing;
3. keeps card data and **prices** accurate by refreshing from Scryfall (scheduled and on demand);
4. is delivered with **full test suite, project-owned quality gates (run locally and in CI; SonarQube supplies analysis only), security scanning in CI/CD**, GitHub-hosted git with gitflow, semantic versioning and atomic commits.

### 2.4 Business objectives

Objectives are SMART where possible. They are traced to requirements in `06-traceability-matrix.md`.

| ID | Objective | Measure of success |
|---|---|---|
| BO-01 | Give a collector one authoritative digital inventory of the physical collection. | A user can add, edit, remove, list, filter and sort cards; vault of ≥ 10,000 entries remains usable (list p95 ≤ 300 ms). |
| BO-02 | Drastically cut the effort to catalogue cards by using the webcam. | On a reference set of 100 English cards photographed under normal indoor light, the correct printing is within the **top 3 candidates for ≥ 90 %** of scans and a scan-to-confirmed-entry takes ≤ 15 s for the user. |
| BO-03 | Keep card data and collection value accurate and current using remote APIs. | Prices never older than 24 h when viewed; total collection value shown with a count of unpriced cards; all catalogue data sourced from Scryfall. |
| BO-04 | Guarantee private, secure multi-user use. | A user can never read or change another user's vault; every API call requires a valid Authelia-issued JWT; zero High/Critical known vulnerabilities at release. |
| BO-05 | Demonstrate professional engineering practice end-to-end. | project quality gates (`scripts/quality_gate.py`) green on every merge, locally and in CI; ≥ 80 % coverage on new code; security scans in CI; gitflow + semver + atomic commits; documentation set always in sync. |

## 3. Stakeholders

| ID | Stakeholder | Role / interest | Influence |
|---|---|---|---|
| STK-01 | fchicout | Sponsor, product owner, lead developer. Wants a useful tool and a showcase of engineering practice. | High |
| STK-02 | Collectors (end users) | Maintain private card vaults; want speed, accuracy, privacy. Primary actor type "Collector". | High |
| STK-03 | Operator | Person who self-hosts and runs the stack (initially STK-01). Wants simple deployment, health checks, safe upgrades. | Medium |
| STK-04 | Scryfall | External data/pricing provider. Imposes API rules and usage policy (see `CON-09`). Not a project member. | High (constraint) |
| STK-05 | Authelia | External identity provider (OIDC). Not a project member; its configuration is part of the deployment. | High (constraint) |
| STK-06 | Contributors and reviewers | Anyone reading or contributing to the public repository; need clear docs and contribution rules. | Low |

## 4. Objectives, deliverables and success criteria

### 4.1 Deliverables

1. Source code monorepo: `backend/` (Python), `frontend/` (Angular), `docs/`, `deploy/` (docker compose + Authelia/proxy config), `scripts/`, `.github/workflows/`.
2. A working application satisfying the MVP requirements (section 5.1).
3. Automated test suites (unit, integration, contract, end-to-end).
4. CI/CD pipeline on GitHub Actions with quality and security gates.
5. Container images and a docker-compose deployment.
6. This documentation set, in sync with the code.

### 4.2 Acceptance criteria for v1.0

- All **Must** and **Should** stories in `02-user-stories.md` are implemented and their acceptance criteria pass as automated tests.
- All **Must** requirements in `03-requirements-specification.md` are verified by the method stated per requirement.
- The project quality gates pass on `main` (`scripts/run_local_gates.py` locally, `ci.yml` in GitHub); no open Blocker/Critical issues; all security hotspots reviewed.
- CI security scans (dependency audit, secret scan, container scan) report no unaddressed High/Critical findings.
- `scripts/check_docs_sync.py` exits 0.
- A fresh clone can be deployed with documented commands and a first user can sign in, scan a card and see the vault value.

## 5. Scope

### 5.1 In scope (v1.0 MVP)

| Area | Included capabilities |
|---|---|
| Identity | Sign-in/out via Authelia (OIDC, PKCE); per-user private data; session renewal; delete my account and data. |
| Vault | Add, view, edit, remove card entries (printing, quantity, condition, finish); filter/sort/search; duplicate entries merge. |
| Catalogue | Search Scryfall cards by name and filters; card detail with all printings. |
| Scanning | Webcam capture in the browser; OCR on the back end; fuzzy match to Scryfall; user confirms; manual-search fallback; scan images never stored. |
| Pricing | Latest Scryfall prices per card; collection total value; daily scheduled refresh + lazy refresh when stale. |
| Platform | REST API with OpenAPI; JWT validation on every call; health checks; structured logs; docker-compose deployment. |
| Engineering | Test suite, project-owned quality gates, security scans, gitflow/semver/atomic commits, synchronized docs. |

### 5.2 Out of scope (v1.0) — explicit non-goals

| Excluded | Reason |
|---|---|
| Price *history* and charts | YAGNY — only latest price kept; may come later. |
| Deck building, deck legality validation, play simulation | Different product; vault is inventory only. |
| Trading, marketplace, buying/selling, wishlists, sharing or public vaults | Privacy-first v1; avoids permission model complexity. |
| Importing/exporting CSV from other tools | Candidate for v1.x. |
| Mobile native apps | Web only (responsive, but desktop/tablet first). |
| Bulk Scryfall dataset import | v1 caches only cards a user owns (see ADR-007). |
| Continuous multi-card batch scanning | Single card per capture in v1. |
| Non-Latin-script OCR (e.g. Japanese cards) | v1 targets Latin-script cards; manual search is the fallback. |
| Storing user card photos | Privacy decision (ADR-008). |
| DAST scanning in CI | Planned for after v1.0. |
| Multi-instance / horizontally scaled deployment | Single instance is sufficient. |

## 6. High-level requirements (summary)

Detailed, testable requirements live in `03-requirements-specification.md`. Highlights:

- Web app only; REST architecture; front end and back end in separate folders of one git repository.
- Every REST call is authenticated with a JWT issued through Authelia and validated by the API; CORS restricts browsers to the front-end origin.
- Front end is Angular (latest) using the VMware Clarity design system in full compliance with its design code.
- Back end is Python, following OO and architectural best practices: SOLID, DRY, KISS, YAGNY.
- Card identification uses OCR plus Scryfall fuzzy matching, confirmed by the user.

## 7. Constraints

| ID | Constraint |
|---|---|
| CON-01 | Back end is written in Python (FastAPI). |
| CON-02 | Front end is Angular (latest stable) with VMware Clarity, in full compliance with the Clarity design code. |
| CON-03 | Architecture is REST; front end and back end live in separate folders of the same git repository (monorepo). |
| CON-04 | Authentication through Authelia (OIDC); every API transaction carries a JWT validated by the back end. |
| CON-05 | Git is mandatory; gitflow branching, semantic versioning, atomic commits (Conventional Commits). |
| CON-06 | GitHub hosts the public remote repository and runs CI/CD (GitHub Actions). |
| CON-07 | SonarQube (self-hosted Community Edition) provides analysis and issue data. Quality gates are evaluated by project-owned scripts, locally and in GitHub Actions, and never by SonarQube's own quality gate. |
| CON-08 | Code quality principles: SOLID, DRY, KISS, YAGNY; full automated test suite. |
| CON-09 | Scryfall terms apply: send `User-Agent` and `Accept` headers, keep ≥ 100 ms between requests (≤ 10 req/s), cache data, do not paywall Scryfall data, do not crop or distort card images, do not imply endorsement by Scryfall or Wizards of the Coast. |
| CON-10 | Deployment is self-hosted via docker compose; PostgreSQL is the database. |
| CON-11 | Browsers only expose the webcam (`getUserMedia`) on secure origins, so the deployment must serve HTTPS. |
| CON-12 | Webcam images are never persisted (privacy). |
| CON-13 | The repository is public; no secrets, personal data or proprietary assets may be committed. |

## 8. Assumptions

| ID | Assumption | If false |
|---|---|---|
| ASM-01 | An Authelia instance is available and can be configured with an OIDC client for this app, issuing signed JWT access tokens (see `OQ-05`). | Auth design must change (ADR-003). |
| ASM-02 | Users have a webcam (or phone camera through the browser) and grant permission. | Manual search fallback covers adding cards. |
| ASM-03 | Most scanned cards are Latin-script, undamaged and printed since the modern card frame; lighting is reasonable. | OCR accuracy objective (BO-02) is missed on those cards. |
| ASM-04 | Scryfall API stays free, available and compatible with its documented rules. | Local cache keeps the vault readable; price refresh degrades (NFR-REL-01). |
| ASM-05 | The self-hosted SonarQube is reachable by the CI runner that executes the analysis (self-hosted runner or tunnel). | Fall back to SonarCloud (public repo is free). |
| ASM-06 | One deployed instance serves a small user group (tens of users, tens of thousands of entries each). | Scaling work becomes necessary (out of scope). |
| ASM-07 | The owner has time for steady, incremental delivery. | Milestones slip; scope is cut by MoSCoW priority. |

## 9. Risks

Probability (P) and impact (I): L/M/H.

| ID | Risk | P | I | Mitigation | Owner |
|---|---|---|---|---|---|
| RSK-01 | OCR accuracy on real webcam frames is too low (glare, foil, angle, low resolution). | H | H | Card-shaped guide overlay in the UI; fixed regions of interest; fuzzy match returns top-N candidates; user always confirms; manual fallback (FR-SCN-07); build a 100-card reference test set early; engine choice kept behind a port (ADR-004). | STK-01 |
| RSK-02 | Scryfall rate limits or policy changes block the app. | M | H | Central rate-limited client (FR-DAT-01); batch endpoint `/cards/collection` for refreshes; local cache of owned cards (FR-DAT-02); graceful degradation (FR-DAT-03). | STK-01 |
| RSK-03 | Latest Angular is not yet supported by the Clarity release. | M | M | Verify support matrix before bootstrapping (`OQ-01`); pin the newest Angular version Clarity supports and record it as an ADR. | STK-01 |
| RSK-04 | GitHub-hosted CI runners cannot reach a homelab SonarQube. | H | M | Self-hosted runner, secure tunnel, or fall back to SonarCloud (`ASM-05`). | STK-03 |
| RSK-05 | Authelia does not issue JWT-format access tokens with the needed `aud`. | M | H | Early spike (`OQ-05`); alternative is validating via token introspection (adapter behind the same port). | STK-01 |
| RSK-06 | Documentation drifts from the code. | H | M | Synchronization mandate, `check_docs_sync.py` as a CI gate, docs in Definition of Done (US-031). | STK-01 |
| RSK-07 | Scope creep (price history, trading, decks…). | M | M | Explicit non-goals (5.2); YAGNY; MoSCoW. | STK-01 |
| RSK-08 | Camera behaviour differs across browsers/devices. | M | M | Supported-browser policy (NFR-CMP-01); device selection UI; manual fallback. | STK-01 |
| RSK-09 | Single maintainer bandwidth. | M | M | Small vertical slices; automation of every check. | STK-01 |
| RSK-10 | Public repository leaks a secret. | L | H | gitleaks in CI (NFR-SEC-03); `.env` files git-ignored; only `.env.example` committed. | STK-01 |

## 10. Milestones and release plan

Versions follow semantic versioning. Pre-1.0 versions may change anything. Each milestone is released from a `release/*` branch merged to `main` and tagged `vX.Y.Z` (gitflow).

| Milestone | Version | Content | Epics / stories |
|---|---|---|---|
| M0 Foundation | 0.1.0 | Repo scaffolding, docs set, CI skeleton, quality gates, security scans, compose stack with Authelia, empty Angular/Clarity shell, FastAPI skeleton with health. | EP-06 (US-027..US-031, US-033 partial) |
| M1 Identity | 0.2.0 | Sign in/out, JWT validation, user provisioning, CORS. | EP-01 (US-001..US-004), US-026 |
| M2 Catalogue | 0.3.0 | Scryfall integration, search, card detail, printings, rate-limited client, resilience. (Needed first: adding to the vault requires choosing a printing.) | EP-03, US-024, US-025 |
| M3 Vault | 0.4.0 | Vault CRUD, filtering, privacy, duplicate merge, card cache. | EP-02 (US-005..US-011) |
| M4 Scan | 0.5.0 | Camera, OCR, candidates, confirm, fallback, privacy limits. | EP-04 |
| M5 Pricing | 0.6.0 | Prices, vault value, scheduled and lazy refresh. | EP-05 |
| M6 Hardening | 1.0.0 | Account deletion, accessibility pass, E2E suite, security review, performance checks, docs final. | US-032, US-033, remaining NFRs |

The order may change, but each milestone must leave `develop` releasable.

## 11. Governance and ways of working

- **Branching (gitflow):** `main` = released; `develop` = integration; `feature/<short-name>`, `release/<x.y.z>`, `hotfix/<x.y.z>`. Pull requests into `develop`/`main` are mandatory, with required checks.
- **Commits:** atomic (one logical change that builds and passes tests), Conventional Commits (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `build`, `perf`), referencing story/requirement IDs. Commit types drive the semantic version bump.
- **Versioning:** Semantic Versioning 2.0.0; git tags `vMAJOR.MINOR.PATCH`; changelog generated from commits (tooling per `OQ-04`).
- **Definition of Done (per story):** acceptance criteria automated and green; unit + integration tests; coverage gate on new code; project quality gates passed (locally and in CI); security scans clean; docs and traceability updated; sync check green; PR reviewed.
- **Decision records:** architectural decisions are ADRs in `05-architecture.md` §9.
- **Documentation:** governed by the mandate in `docs/README.md`.

## 12. Open questions

Resolved questions become requirements, ADRs or assumptions, and the row is marked *Resolved* (never deleted).

| ID | Question | Needed by | Status |
|---|---|---|---|
| OQ-01 | Which Angular version is the latest one officially supported by the current Clarity release? | M0 | Open |
| OQ-02 | Which OCR engine (Tesseract via `pytesseract`/`tesserocr`, EasyOCR, PaddleOCR) gives the best accuracy/footprint on the 100-card reference set? | M4 | Open |
| OQ-03 | Which reverse proxy (Traefik or Caddy) fronts the stack and terminates TLS? | M0 | Open |
| OQ-04 | Which release automation fits gitflow (release-please, semantic-release, or `git-cliff` + manual tags)? | M0 | Open |
| OQ-05 | Can the Authelia OIDC client be configured to issue RS256-signed JWT access tokens with the API as audience? Else use introspection. | M1 | Open |
| OQ-06 | Which open-source licence (MIT vs Apache-2.0) for the public repository? | M0 | Open |
| OQ-07 | Should prices be shown in USD only, or USD + EUR? (Docs currently assume both are shown.) | M5 | Open |
| OQ-08 | Which self-hosted CI runner / tunnel strategy gives GitHub Actions access to SonarQube, and does the current SonarQube Community Build support branch / pull-request analysis (this only decides where analysis is published, since the gate is project-owned)? Also pending: a Sonar admin creates projects `mtg-vault-backend` and `mtg-vault-frontend` and a scan token. | M0 | Open |

## 13. Approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Sponsor / Product owner | fchicout | Pending review of this draft | — |

## 14. Legal notice

MTG Card Vault is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It is not approved or endorsed by Wizards of the Coast. Magic: The Gathering is a trademark of Wizards of the Coast LLC. Card data and images are provided by Scryfall (not affiliated with this project). See `NFR-LEG-01`.
