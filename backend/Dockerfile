# syntax=docker/dockerfile:1.7
# Build stage: resolve and install locked, production-only dependencies.
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
# Non-editable: the package is copied into the venv, so the runtime stage needs no source tree.
RUN uv sync --frozen --no-dev --no-editable

# Runtime stage: no build tools, non-root user, nothing but the virtualenv.
FROM python:3.14-slim
# The runtime never installs packages: drop pip (and its vendored msgpack/urllib3) from the image.
RUN python -m pip uninstall -y pip \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "mtgvault.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
