# 06 — Traceability Matrix

**Docs set version:** 0.1.0
**Document:** 06 Requirements Traceability Matrix
**Status:** Draft
**Last updated:** 2026-10-31

This matrix is the hub that ties the documentation set together. It is parsed by `scripts/check_docs_sync.py`: the *Stories* and *Use cases* columns must equal the corresponding links in `02`, `03` and `04` (same sets, both directions). Always use explicit IDs (no ranges) in this file.

Legend — Tests: **U** unit · **I** integration · **C** contract · **E** end-to-end · **S** static/CI check · **M** manual/review. Component codes: `05` §5.6.

## A. Business objective → requirements

| Objective | Requirements |
|---|---|
| BO-01 | FR-VLT-01, FR-VLT-02, FR-VLT-03, FR-VLT-04, FR-VLT-05, FR-VLT-06, FR-VLT-07, NFR-PRF-01 |
| BO-02 | FR-SCN-01, FR-SCN-02, FR-SCN-03, FR-SCN-04, FR-SCN-05, FR-SCN-06, FR-SCN-07, FR-SCN-08, NFR-PRF-02, NFR-CMP-01 |
| BO-03 | FR-CAT-01, FR-CAT-02, FR-CAT-03, FR-CAT-04, FR-PRC-01, FR-PRC-02, FR-PRC-03, FR-PRC-04, FR-PRC-05, FR-DAT-01, FR-DAT-02, FR-DAT-03, NFR-REL-01 |
| BO-04 | FR-AUTH-01, FR-AUTH-02, FR-AUTH-03, FR-AUTH-04, FR-AUTH-05, FR-AUTH-06, FR-AUTH-07, FR-AUTH-08, NFR-SEC-01, NFR-SEC-02, NFR-SEC-03, NFR-SEC-04, NFR-SEC-05, NFR-SEC-06, NFR-SEC-07, NFR-PRV-01 |
| BO-05 | FR-API-01, FR-API-02, FR-OPS-01, FR-OPS-02, FR-OPS-03, NFR-PRF-03, NFR-REL-02, NFR-USA-01, NFR-USA-02, NFR-USA-03, NFR-USA-04, NFR-MNT-01, NFR-MNT-02, NFR-MNT-03, NFR-MNT-04, NFR-TST-01, NFR-PRT-01, NFR-LEG-01, NFR-DOC-01 |

## B. Requirement → stories → use cases → components → tests

### B.1 Functional requirements

| Requirement | Stories | Use cases | Components | Tests |
|---|---|---|---|---|
| FR-AUTH-01 | US-001 | UC-01 | FE-AUTH | E, U |
| FR-AUTH-02 | US-002 | UC-09 | FE-AUTH | E |
| FR-AUTH-03 | US-003 | UC-01 | FE-AUTH, FE-CORE | U, E |
| FR-AUTH-04 | US-004 | UC-01 | API-AUTH, ADP-DB | I |
| FR-AUTH-05 | US-026 | UC-01 | ADP-JWT, API-AUTH | U, I, C |
| FR-AUTH-06 | US-026 | — | API-CORE, API-AUTH | I, C |
| FR-AUTH-07 | US-026 | — | API-CORE, INF-DEPLOY | I |
| FR-AUTH-08 | US-032 | UC-11 | API-AUTH, ADP-DB, FE-ACCOUNT | I, E |
| FR-VLT-01 | US-005 | UC-02, UC-03 | API-VAULT, ADP-DB, FE-VAULT | U, I, C |
| FR-VLT-02 | US-006 | UC-06 | API-VAULT, ADP-DB, FE-VAULT | I, C |
| FR-VLT-03 | US-007 | UC-04 | API-VAULT, ADP-DB, FE-VAULT | U, I |
| FR-VLT-04 | US-008 | UC-05 | API-VAULT, ADP-DB, FE-VAULT | I |
| FR-VLT-05 | US-009 | UC-06 | API-VAULT, ADP-DB, FE-VAULT | I |
| FR-VLT-06 | US-010 | UC-02, UC-03 | API-VAULT, ADP-DB | U, I |
| FR-VLT-07 | US-011 | — | API-VAULT, API-AUTH, ADP-DB | I, E |
| FR-CAT-01 | US-012 | UC-10 | API-CATALOG, ADP-SCRYFALL, FE-CATALOG | U, I |
| FR-CAT-02 | US-013 | UC-10 | API-CATALOG, FE-CATALOG | U, I |
| FR-CAT-03 | US-014 | UC-10 | API-CATALOG, FE-CATALOG | I, C |
| FR-CAT-04 | US-005, US-014 | UC-03, UC-10 | API-CATALOG, ADP-SCRYFALL, FE-CATALOG | I |
| FR-SCN-01 | US-015 | UC-02 | FE-SCAN | E, M |
| FR-SCN-02 | US-016 | UC-02 | FE-SCAN | U, E |
| FR-SCN-03 | US-016 | UC-02 | API-SCAN, ADP-OCR | U, I |
| FR-SCN-04 | US-016 | UC-02 | API-SCAN, ADP-SCRYFALL | U, I |
| FR-SCN-05 | US-017 | UC-02 | FE-SCAN, API-SCAN, API-VAULT | E, I |
| FR-SCN-06 | US-018 | UC-02 | API-SCAN, API-CORE | I, M |
| FR-SCN-07 | US-019 | UC-02, UC-03 | FE-SCAN, FE-CATALOG | E |
| FR-SCN-08 | US-018 | UC-02 | API-SCAN | U, I |
| FR-PRC-01 | US-020 | UC-08 | API-PRICING, ADP-DB, WRK | I |
| FR-PRC-02 | US-020 | UC-06, UC-10 | API-PRICING, API-VAULT, FE-VAULT | U, I |
| FR-PRC-03 | US-021 | UC-07 | API-PRICING, FE-VAULT | U, I |
| FR-PRC-04 | US-022 | UC-08 | WRK, API-PRICING, ADP-SCRYFALL | I |
| FR-PRC-05 | US-023 | UC-07, UC-10 | API-PRICING | U, I |
| FR-DAT-01 | US-024 | UC-02, UC-08, UC-10 | ADP-SCRYFALL | U, I |
| FR-DAT-02 | US-005, US-024 | UC-02, UC-03 | ADP-DB, API-VAULT | I |
| FR-DAT-03 | US-025 | UC-06, UC-10 | API-CORE, API-CATALOG, API-VAULT | I |
| FR-API-01 | US-027 | — | API-CORE, FE-CORE, INF-CI | C, S |
| FR-API-02 | US-027 | — | API-CORE, FE-CORE | C, I |
| FR-OPS-01 | US-028 | — | API-CORE | I |
| FR-OPS-02 | US-028 | — | API-CORE, WRK | U, M |
| FR-OPS-03 | US-029 | — | API-CORE, ADP-DB, INF-DEPLOY | I, M |

### B.2 Non-functional requirements

| Requirement | Stories | Use cases | Components | Tests |
|---|---|---|---|---|
| NFR-SEC-01 | US-001, US-026 | — | ADP-JWT, API-AUTH, FE-AUTH | I, M |
| NFR-SEC-02 | US-029 | — | INF-DEPLOY | M |
| NFR-SEC-03 | US-030 | — | INF-CI | S |
| NFR-SEC-04 | US-030 | — | INF-CI | S |
| NFR-SEC-05 | US-029, US-030 | — | INF-CI, INF-DEPLOY | S |
| NFR-SEC-06 | US-026 | — | INF-DEPLOY, FE-CORE | I, M |
| NFR-SEC-07 | US-018 | — | API-SCAN, API-CORE | U, I |
| NFR-PRF-01 | US-006 | UC-06 | API-VAULT, ADP-DB | I |
| NFR-PRF-02 | US-016 | UC-02 | API-SCAN, ADP-OCR | I, M |
| NFR-PRF-03 | US-006 | — | FE-CORE | M |
| NFR-REL-01 | US-025 | UC-06 | API-VAULT, ADP-SCRYFALL | I |
| NFR-REL-02 | US-029 | — | ADP-DB, INF-DEPLOY | I, M |
| NFR-USA-01 | US-033 | — | FE-CORE, FE-VAULT, FE-CATALOG, FE-SCAN, FE-ACCOUNT | M, S |
| NFR-USA-02 | US-033 | — | FE-CORE | E, M |
| NFR-USA-03 | US-033 | — | FE-CORE | E, M |
| NFR-USA-04 | US-033 | — | FE-CORE | S |
| NFR-MNT-01 | US-030 | — | INF-CI | S |
| NFR-MNT-02 | US-030 | — | INF-CI | S |
| NFR-MNT-03 | US-030 | — | INF-CI | S |
| NFR-MNT-04 | US-030 | — | INF-CI | S, M |
| NFR-TST-01 | US-030 | — | INF-CI | S |
| NFR-PRT-01 | US-029 | — | INF-DEPLOY | M |
| NFR-PRV-01 | US-018, US-032 | — | API-SCAN, API-AUTH, ADP-DB | I, M |
| NFR-LEG-01 | US-024 | — | FE-CORE | M |
| NFR-DOC-01 | US-031 | — | DOCS, INF-CI | S |
| NFR-CMP-01 | US-015 | UC-02 | FE-SCAN | E, M |

## C. Story → epic → release → use cases

| Story | Epic | Release | Priority | Use cases |
|---|---|---|---|---|
| US-001 | EP-01 | 0.2.0 | Must | UC-01 |
| US-002 | EP-01 | 0.2.0 | Must | UC-09 |
| US-003 | EP-01 | 0.2.0 | Should | UC-01 |
| US-004 | EP-01 | 0.2.0 | Must | UC-01 |
| US-005 | EP-02 | 0.4.0 | Must | UC-02, UC-03 |
| US-006 | EP-02 | 0.4.0 | Must | UC-06 |
| US-007 | EP-02 | 0.4.0 | Must | UC-04 |
| US-008 | EP-02 | 0.4.0 | Must | UC-05 |
| US-009 | EP-02 | 0.4.0 | Should | UC-06 |
| US-010 | EP-02 | 0.4.0 | Must | UC-02, UC-03 |
| US-011 | EP-02 | 0.4.0 | Must | — |
| US-012 | EP-03 | 0.3.0 | Must | UC-10 |
| US-013 | EP-03 | 0.3.0 | Should | UC-10 |
| US-014 | EP-03 | 0.3.0 | Must | UC-10 |
| US-015 | EP-04 | 0.5.0 | Must | UC-02 |
| US-016 | EP-04 | 0.5.0 | Must | UC-02 |
| US-017 | EP-04 | 0.5.0 | Must | UC-02 |
| US-018 | EP-04 | 0.5.0 | Must | UC-02 |
| US-019 | EP-04 | 0.5.0 | Must | UC-02, UC-03 |
| US-020 | EP-05 | 0.6.0 | Must | UC-06, UC-08 |
| US-021 | EP-05 | 0.6.0 | Must | UC-07 |
| US-022 | EP-05 | 0.6.0 | Must | UC-08 |
| US-023 | EP-05 | 0.6.0 | Should | UC-07, UC-10 |
| US-024 | EP-06 | 0.3.0 | Must | UC-02, UC-08, UC-10 |
| US-025 | EP-06 | 0.3.0 | Should | UC-06, UC-10 |
| US-026 | EP-06 | 0.2.0 | Must | — |
| US-027 | EP-06 | 0.1.0 | Must | — |
| US-028 | EP-06 | 0.1.0 | Should | — |
| US-029 | EP-06 | 0.1.0 | Must | — |
| US-030 | EP-06 | 0.1.0 | Must | — |
| US-031 | EP-06 | 0.1.0 | Must | — |
| US-032 | EP-01 | 1.0.0 | Should | UC-11 |
| US-033 | EP-06 | 1.0.0 | Should | — |

## D. Architecture decisions → what they govern

| ADR | Governs requirements |
|---|---|
| ADR-001 | NFR-PRT-01, NFR-MNT-04 |
| ADR-002 | FR-API-01, NFR-MNT-02 |
| ADR-003 | FR-AUTH-01, FR-AUTH-03, FR-AUTH-05, FR-AUTH-06, FR-AUTH-07, NFR-SEC-01 |
| ADR-004 | FR-SCN-03, FR-SCN-04, FR-SCN-05, FR-SCN-07 |
| ADR-005 | FR-VLT-06, FR-OPS-03, NFR-REL-02 |
| ADR-006 | NFR-MNT-01, NFR-MNT-03, NFR-TST-01 |
| ADR-007 | FR-DAT-02, FR-DAT-03, FR-PRC-01 |
| ADR-008 | FR-SCN-06, NFR-PRV-01 |
| ADR-009 | FR-API-01, NFR-USA-01 |
| ADR-010 | NFR-MNT-04 |
| ADR-011 | NFR-MNT-01 |
| ADR-012 | FR-PRC-04, FR-PRC-05 |
| ADR-013 | FR-API-02 |
| ADR-014 | NFR-DOC-01 |

## E. Maintenance checklist (apply on every change)

1. Added/changed a story? Update `02`, the requirement rows in `03`, the use-case lines in `04`, sections B and C here, and bump the docs-set version everywhere.
2. Added/changed a requirement? Update `03`, the stories' `Requirements:` lines in `02`, use-case `Requirements:` lines in `04`, sections A and B here, and any ADR in section D.
3. Added/changed a use case? Update `04`, the stories' `Use cases:` lines in `02`, sections B and C here.
4. Added/changed an architecture decision or component? Update `05` (ADR, §5.6 component codes), section D here, and affected requirements.
5. Changed scope, objectives, risks, constraints? Update `01`, then re-check everything it constrains.
6. Run `python3 scripts/check_docs_sync.py`; add a changelog row in `docs/README.md`.
