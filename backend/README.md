# MTG Card Vault — backend

FastAPI REST API. Architecture: `docs/05-architecture.md` §5.2 (layers `api → application → domain`, adapters implement ports, composition root in `main.py`).

## Develop

```bash
uv sync                      # create .venv and install locked dependencies
uv run pytest                # unit + contract tests (integration tests need Docker)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports          # architecture contracts
uv run python -m mtgvault.export_openapi openapi.json
```

## Skeleton status

`GET /hello` is a **temporary, unauthenticated** route that exists only to validate the CI/CD harness (issue #1). It is removed when JWT validation lands (issue #15), because only `/healthz` and `/readyz` may be public (US-026).
