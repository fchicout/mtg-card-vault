# syntax=docker/dockerfile:1.7
# Base images are pinned by digest (reproducible builds); Dependabot proposes the updates.
# Build stage: resolve and install locked, production-only dependencies.
FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
# Non-editable: the package is copied into the venv, so the runtime stage needs no source tree.
RUN uv sync --frozen --no-dev --no-editable

# Runtime stage: no build tools, non-root user, nothing but the virtualenv.
FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d
# Pick up OS security fixes published after the base image was built (NFR-SEC-05), then drop the
# apt lists. The runtime never installs packages: drop pip (and its vendored msgpack/urllib3) too.
# Tesseract (English data only) is the OCR engine of the scanner (ADR-004); it runs as the same
# non-root user, reads the image from stdin and writes nothing to disk.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
COPY --from=builder --chown=10001:10001 /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=10001:10001 /app/migrations /app/migrations
# BIND_HOST: the image must listen on its network interface (the proxy connects to it); outside the
# image the default is loopback only.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BIND_HOST=0.0.0.0
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
# Migrates the database, then serves; if a migration fails the process exits and never listens.
CMD ["python", "-m", "mtgvault.serve"]
