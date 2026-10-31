# MTG Card Vault — Engineering Documentation

**Docs set version:** 0.2.1
**Status:** Draft
**Last updated:** 2026-10-31

This folder is the single source of truth for **what** MTG Card Vault is, **why** it exists, **what** it must do and **how** it is built. It is written to be read by humans *and* by LLM coding assistants: an LLM that reads only this folder should be able to understand the product, its scope, the problems it solves, and the architecture it must be implemented in.

## 1. The documents

| # | Document | Template / standard | Answers |
|---|----------|--------------------|---------|
| 01 | [Project Charter](01-project-charter.md) | PMBOK Project Charter | Why does the project exist? Scope, objectives, stakeholders, constraints, risks, milestones. |
| 02 | [User Stories](02-user-stories.md) | Connextra format + INVEST + Gherkin acceptance criteria, grouped by Epic | Who needs what, and why? |
| 03 | [Requirements Specification](03-requirements-specification.md) | ISO/IEC/IEEE 29148 (SRS) | What exactly shall the system do and how well? |
| 04 | [Use Cases](04-use-cases.md) | Cockburn "fully dressed" use cases | How do actors and the system interact, step by step? |
| 05 | [Architecture Plan](05-architecture.md) | arc42 (12 sections) + ADRs, diagrams in Mermaid | How is it built and why this way? |
| 06 | [Traceability Matrix](06-traceability-matrix.md) | Requirements Traceability Matrix | How does every objective, requirement, story, use case, component and test link together? |

Reading order for a newcomer (or an LLM): 01 → 03 (sections 1-2 and Appendix A) → 02 → 04 → 05 → 06.

## 2. The synchronization mandate (NON-NEGOTIABLE)

The documents are **one logical specification split across six files**. They **must always be in full sync**. Concretely:

1. **One change set, all documents.** Any change to scope, a requirement, a story, a use case, an architecture decision or a component updates **every affected document and the traceability matrix in the same pull request / commit series**. A PR that changes one document and leaves a dependent one stale is rejected.
2. **Stable IDs.** Every artifact has a permanent ID (section 3). IDs are never reused or renumbered. Retired artifacts are marked `Status: Deprecated` and kept, never deleted.
3. **Cross-references by ID only.** Documents reference each other using IDs (`FR-VLT-01`, `US-005`, `UC-02`, `ADR-003`). Prose must not restate requirement text; it links to the ID. (DRY applied to documentation.)
4. **Shared version.** All six files carry the same `Docs set version`. It is bumped (semver: major = scope/goal change, minor = new/changed requirement, story, use case or ADR, patch = wording) on every change, and logged in the changelog below.
5. **Code follows docs.** Implementation work starts from a story (`US-xxx`). Code, tests and commits reference the story/requirement IDs they implement (for example `feat(vault): add entry endpoint [US-005, FR-VLT-01]`). If implementation reveals the docs are wrong, **fix the docs first** (or in the same PR), then the code.
6. **Mechanical enforcement.** `scripts/check_docs_sync.py` verifies the rules that can be checked automatically (section 5). It must pass locally before committing docs and will run as a required CI check (tracked by `US-031`, `NFR-DOC-01`).
7. **Definition of Done for any story** includes: docs updated, matrix updated, sync check green.

## 3. ID scheme

| Prefix | Meaning | Defined in |
|--------|---------|-----------|
| `BO-nn` | Business objective | 01 |
| `STK-nn` | Stakeholder | 01 |
| `CON-nn` | Constraint | 01 |
| `ASM-nn` | Assumption | 01 |
| `RSK-nn` | Risk | 01 |
| `OQ-nn` | Open question (to be resolved, then recorded as an ADR or requirement) | 01 |
| `EP-nn` | Epic | 02 |
| `US-nnn` | User story | 02 |
| `FR-AAA-nn` | Functional requirement (`AAA` = area: AUTH, VLT, CAT, SCN, PRC, DAT, API, OPS) | 03 |
| `NFR-AAA-nn` | Non-functional requirement (`AAA` = SEC, PRF, REL, USA, MNT, PRT, PRV, LEG, DOC, TST, CMP) | 03 |
| `UC-nn` | Use case | 04 |
| `ADR-nnn` | Architecture decision record | 05 |

Priorities use **MoSCoW**: **M**ust, **S**hould, **C**ould, **W**on't (this release).

## 4. Document map by question

| If you want to know… | Read |
|---|---|
| What problem the product solves and for whom | 01 §2-§3; 02 |
| What is in / out of scope | 01 §5 |
| The exact behaviour of a feature | 03 (requirement rows), 04 (flow), 02 (acceptance criteria) |
| Quality attributes (security, performance, …) | 03 §4, 05 §10 |
| Which component implements something and how it is tested | 06 |
| Why a technology was chosen | 05 §9 (ADRs) |
| MTG / Scryfall vocabulary | 03 Appendix A |

## 5. What the sync check verifies

Run: `python3 scripts/check_docs_sync.py` (exit code 0 = in sync).

- All six files declare the same `Docs set version`, equal to the newest changelog entry below.
- Every ID is defined in its owning document and every referenced ID exists.
- Every requirement (`FR-*`/`NFR-*`) traces to ≥ 1 story; every story to ≥ 1 requirement; every use case to ≥ 1 requirement; every business objective to ≥ 1 requirement.
- The links in the SRS (03), the story document (02), the use-case document (04) and the matrix (06) agree **exactly** (same sets in every direction).

What it cannot check (reviewers must): that the *meaning* of linked artifacts is consistent, that ADRs match the real code, and that diagrams are current.

## 6. Changelog

| Docs set version | Date | Summary |
|---|---|---|
| 0.2.1 | 2026-10-31 | SonarQube status recorded (backend project and CI secrets exist; frontend project pending) in OQ-08. |
| 0.2.0 | 2026-10-31 | Quality gates are project-owned (`scripts/quality_gate.py`, run locally and in CI); SonarQube is an analysis/issue source only: CON-07, NFR-MNT-01, ADR-011, US-030, Definition of Done, CI job table. |
| 0.1.0 | 2026-10-31 | Initial documentation set: charter, stories, SRS, use cases, architecture, traceability. |
