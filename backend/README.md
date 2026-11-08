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

Every route under `/api/v1` requires a bearer JWT issued by the configured OIDC provider (issue #15, US-026); only `/healthz` and `/readyz` are public. The skeleton `/hello` route is gone. Required settings: `OIDC_ISSUER_URL`, `OIDC_AUDIENCE` (see docs/05 section 7.2).
