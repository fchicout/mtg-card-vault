# MTG Card Vault

> **Self-hosted, hardened multi-user web application for *Magic: The Gathering* card inventory with webcam OCR and automated market valuation.**

MTG Card Vault allows collectors to maintain a private, real-time valued inventory of their physical card collections. Cards can be scanned via webcam using computer vision/OCR, matched against Scryfall's database with circuit-breaker resilience, and tracked under isolated multi-tenant vaults protected by OpenID Connect (OIDC).

Built with **FastAPI**, **Angular + Clarity Design System**, **PostgreSQL**, **Caddy**, and **Authelia**, running as a defense-in-depth, hardened container stack.

---

## 🏛️ System Architecture

```text
                  HTTPS / TLS (Port 8443)
                            │
                            ▼
               ┌─────────────────────────┐
               │   Caddy Edge Reverse    │  ◄── HSTS, Strict TLS Termination,
               │          Proxy          │      Non-root (Port 8443 / 8080)
               └────────────┬────────────┘
                            │ [edge network]
             ┌──────────────┴──────────────┐
             ▼                             ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│     Angular Frontend    │   │       FastAPI API       │ ◄── OIDC JWT Bearer Validation
│   (Clarity Design, PWA) │   │  (Python 3.12, Read-only│     (Authelia Integration)
└─────────────────────────┘   │       Container)        │
                              └────────────┬────────────┘
                                           │ [backend network (internal)]
                             ┌─────────────┴─────────────┐
                             ▼                           ▼
               ┌─────────────────────────┐ ┌─────────────────────────┐
               │    PostgreSQL 17 DB     │ │  Background Task Worker │
               │ (Isolated, No Outbound) │ │ (Price Sync & Cron Jobs)│
               └─────────────────────────┘ └─────────────────────────┘
```

---

## 🛡️ DevSecOps & Security Highlights

This repository serves as a reference implementation for **container hardening** and **automated supply chain security**:

- **Least-Privilege Containers**:
  - `cap_drop: ALL` across every service container.
  - `security_opt: no-new-privileges:true`.
  - `read_only: true` root filesystems on API, worker, frontend, and proxy with minimal `/tmp` tmpfs mounts.
- **Zero-Trust Network Segmentation**:
  - PostgreSQL database resides on an `internal: true` bridge network with no egress route to the internet.
  - Only the Caddy reverse proxy publishes ports to the host.
- **Supply-Chain Immutability**:
  - Base container images pinned with strict **SHA-256 content digests**.
- **Automated Quality & Security Gates (`make gates`)**:
  - **Secret Detection**: `gitleaks` scanning in pre-commit and CI.
  - **Vulnerability Assessment**: Container scanning via `trivy`.
  - **Software Bill of Materials (SBOM)**: Manifest generation via `syft`.
  - **Documentation Sync**: Python verification suite enforcing consistency between architecture ADRs, user stories, and requirements.
  - **Conventional Commits & Semantic Releases**: Managed via `git-cliff`.

---

## 🚀 Quickstart

### Prerequisites
- Docker or Podman with Compose support
- Python 3.12+ (for local development and gate validation)

### 1. Run Local Quality Gates
Verify linting, typing, documentation sync, and pre-commit checks:
```bash
make gates
make docs-check
```

### 2. Launch the Hardened Container Stack
```bash
# Clone and enter the repository
cd deploy

# Configure environment variables (set POSTGRES_PASSWORD and OIDC provider)
cp .env.example .env

# Start the full stack (Edge proxy, API, Worker, Frontend, Database)
docker compose up -d --build
```

Access the application at `https://localhost:8443` (or your configured `APP_HOST`).

---

## 📚 Documentation

Detailed architecture decision records (ADRs), user stories, threat modeling, and trace matrices live in the synchronized documentation set:
- **Project Charter & Scope**: [`docs/01-project-charter.md`](docs/01-project-charter.md)
- **User Stories & Workflows**: [`docs/02-user-stories.md`](docs/02-user-stories.md)
- **System Requirements**: [`docs/03-requirements-specification.md`](docs/03-requirements-specification.md)
- **Detailed Architecture (arc42)**: [`docs/05-architecture.md`](docs/05-architecture.md)
- **Traceability Matrix**: [`docs/06-traceability-matrix.md`](docs/06-traceability-matrix.md)

---

## 🤝 Contributing & Security

- **Contribution Guidelines**: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Vulnerability Reporting**: [`SECURITY.md`](SECURITY.md)
- **Code of Conduct**: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

---

## 📄 License & Legal Notice

- **Code License**: [MIT](LICENSE)
- **Fan Content Notice**: MTG Card Vault is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It is not approved or endorsed by Wizards of the Coast. *Magic: The Gathering* is a trademark of Wizards of the Coast LLC. Card data and images are provided by [Scryfall](https://scryfall.com).
