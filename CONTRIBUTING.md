# Contributing

Thank you for helping. The rules live in the documentation set; this page tells you where and gives the shortest path to a compliant pull request. Nothing here restates a requirement: follow the links.

## 1. Before you start
- Read [`docs/README.md`](docs/README.md): the **synchronization mandate** applies to every change (code follows docs; change stories, requirements, use cases, ADRs and [`docs/06-traceability-matrix.md`](docs/06-traceability-matrix.md) together, bump the docs set version, add a changelog row).
- Work starts from an issue. Pick or file one with the templates; it names the stories/requirements it implements.

## 2. Branches (gitflow, ADR-010)
`feature/<name>` from `develop`; `release/X.Y.Z` and `hotfix/X.Y.Z` as in [`docs/05-architecture.md`](docs/05-architecture.md) section 7.5, which also lists the release procedure. Pull requests target `develop` (or `main` for releases and hotfixes). Nobody pushes to `develop` or `main` directly.

## 3. Commits
Atomic [Conventional Commits](https://www.conventionalcommits.org) that cite the IDs they implement, for example `feat(vault): add entry endpoint [US-005, FR-VLT-01]`. Types, scopes and limits are in `docs/05` section 7.5 and are checked by `make commit-policy` and by CI. A pushed branch is never rewritten: bring it up to date by merging `develop` into it.

## 4. Definition of Done
Acceptance criteria automated and green; unit and integration tests; coverage of new code at least 80 %; project quality gates passed; security scans clean; documentation and matrix updated; sync check green; reviewed ([`docs/01-project-charter.md`](docs/01-project-charter.md) section 11).

```bash
make gates         # every gate that runs without containers (python3 scripts/run_local_gates.py for all)
make docs-check    # the documentation set is synchronized
make commit-policy # your commits and branch name follow the policy
pre-commit install # optional: docs-sync on commit, commit-message check on commit-msg
```

SonarQube's own quality gate is never used; the project's gates are decided by `scripts/quality_gate.py` locally and in CI ([`ADR-011`](docs/05-architecture.md)).

## 5. Security and secrets
The repository is public: never commit secrets, personal data or proprietary assets. Findings that cannot be fixed yet are accepted only through a time-boxed entry in `security/exceptions.yaml` (see `docs/05` section 8.2). Report vulnerabilities privately as described in [`SECURITY.md`](SECURITY.md).

## 6. Pull requests
Use the template. CI must be green: it runs the documentation sync, commit and branch policy, quality gates, tests, security scans and the end-to-end checks listed in `docs/05` section 7.4.
