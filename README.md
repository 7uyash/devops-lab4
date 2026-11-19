# DevOps Lab 4 — Advanced Deployment Strategies & Enterprise DevOps

Suyash Sahu — Roll No. 2301010476 — K R Mangalam University

An enterprise-style delivery toolkit around **ShopLite**, a small Flask web shop (`app/`) backed by PostgreSQL.
Every task is a GitHub Actions workflow in `.github/workflows/` that builds, deploys, breaks and recovers the
system and records the evidence.

| # | Task | Files | Workflow |
|---|------|-------|----------|
| 1 | **Disaster recovery** — backup, restore, failover, RTO/RPO | `dr/` (primary + streaming replica, nginx failover, `backup.sh`, `restore.sh`, `failover.sh`, `objectives.py`) | `dr.yml` |
| 2 | **Automated testing as CI/CD gates** | `tests/unit`, `tests/integration` (real PostgreSQL), lint → unit+coverage → build → integration → deploy | `ci.yml` |
| 3 | **Blue-green deployment** with zero-downtime switch | `deploy/bluegreen/` (nginx router, `switch.sh` with smoke test + rollback) | `bluegreen.yml` |
| 4 | **GitOps** with Argo CD, automated reconciliation | `gitops/` (kind cluster, in-cluster Gitea repo, Argo CD `Application` with prune + self-heal) | `gitops.yml` |
| 5 | Advanced deployment strategies **report** | (PDF, built from the evidence of tasks 1–4, 6, 7) | — |
| 6 | **Secret management** with HashiCorp Vault | `vault/` (Shamir unseal, audit log, AppRole + wrapped secret_id, dynamic DB credentials, policies) | `secrets.yml` |
| 7 | **Canary deployment** with metric-based rollback | `deploy/canary/` (user-sticky traffic split, Prometheus, `canary.py` analysis 10→25→50→100 %) | `canary.yml` |

## Application — `app/`
- `GET /health`, `/version`, `/api/products`, `POST /api/orders`, `GET /api/orders`, `/api/config`, `/metrics`
- Responses carry `X-App-Version` / `X-App-Track`, so every request can be attributed to a release
- `DATABASE_URL` → orders in PostgreSQL; or `VAULT_ADDR` + AppRole files → credentials fetched from Vault at start-up
- `ERROR_RATE` / `EXTRA_LATENCY_MS` inject faults to build deliberately bad releases for the canary demo
- Docker image: non-root user, health check, gunicorn with graceful shutdown

## Running a workflow locally
`python3 scripts/run_local.py .github/workflows/<name>.yml --out runs/<name>` executes the workflow steps in
order (bash `-eo pipefail`, same env/working directories) and stores every step's output plus a `summary.json`.

## Tools
Docker Compose, nginx 1.27, PostgreSQL 16, Prometheus 2.55, HashiCorp Vault 1.18, kind 0.25 (Kubernetes 1.31),
Argo CD 2.13, Gitea 1.22, pytest, ruff, gitleaks, Playwright.
