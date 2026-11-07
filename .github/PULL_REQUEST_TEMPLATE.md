## What and why
<!-- One or two sentences. Link the issue: "Closes #n" when this finishes it, "Refs #n" otherwise. -->

## Traceability
- Stories / requirements / ADRs touched: <!-- e.g. US-005, FR-VLT-01, ADR-005 -->

## Checklist (Definition of Done, see CONTRIBUTING.md)
- [ ] Tests added or updated; acceptance criteria are automated
- [ ] `make gates` is green locally (or the reason it cannot be run is stated)
- [ ] Documentation and `docs/06-traceability-matrix.md` updated in this PR; `make docs-check` passes; docs set version and changelog bumped
- [ ] Commits are atomic Conventional Commits with story/requirement IDs (`make commit-policy`)
- [ ] No secret, personal data or proprietary asset is added (the repository is public)
- [ ] Branch is `feature/*`, `release/X.Y.Z` or `hotfix/X.Y.Z`; the PR targets `develop` (or `main` for releases and hotfixes)
