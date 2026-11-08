# Developer shortcuts. The real gates live in scripts/ and .github/workflows/ci.yml.
.PHONY: smoke docs-check docs-coverage gates commit-policy next-version changelog-preview

smoke: ## Post-deploy smoke check: make smoke URL=https://staging.mtg.fchicout.dev
	python3 scripts/smoke_check.py "$(URL)"

docs-check: ## Documentation set is synchronized (also run by the pre-commit hook)
	python3 scripts/check_docs_sync.py

docs-coverage: ## Unit tests of the sync script with a 90 % coverage floor
	uvx coverage run --branch --include=scripts/check_docs_sync.py -m unittest discover -s scripts/tests -p test_check_docs_sync.py
	uvx coverage report --include=scripts/check_docs_sync.py --fail-under=90

gates: ## Every quality gate that runs without containers
	python3 scripts/run_local_gates.py --skip e2e,container-scan

commit-policy: ## Commits of this branch follow the policy (against origin/develop)
	python3 scripts/check_commit_policy.py --range origin/develop..HEAD --branch "$(shell git branch --show-current)"

next-version: ## The version the commits since the last tag would produce (git-cliff dry run)
	uvx git-cliff --bumped-version

changelog-preview: ## Unreleased changes as the next release's changelog (git-cliff dry run)
	uvx git-cliff --unreleased --bump
