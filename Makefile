# Developer shortcuts. The real gates live in scripts/ and .github/workflows/ci.yml.
.PHONY: docs-check docs-coverage gates

docs-check: ## Documentation set is synchronized (also run by the pre-commit hook)
	python3 scripts/check_docs_sync.py

docs-coverage: ## Unit tests of the sync script with a 90 % coverage floor
	uvx coverage run --branch --include=scripts/check_docs_sync.py -m unittest discover -s scripts/tests -p test_check_docs_sync.py
	uvx coverage report --include=scripts/check_docs_sync.py --fail-under=90

gates: ## Every quality gate that runs without containers
	python3 scripts/run_local_gates.py --skip e2e,container-scan
