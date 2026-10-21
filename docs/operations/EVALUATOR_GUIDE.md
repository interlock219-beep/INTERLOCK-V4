# Interlock — Evaluator Guide

This guide gives a technical evaluator a complete, honest path from a clean checkout to a
verified running instance, an end-to-end recovery example, inspectable evidence, and safe
shutdown. Every command and output shown here was executed on 2026-10-16 (Windows 11,
Python 3.11, SQLite) unless stated otherwise.

## 1. Understand the product

Interlock is a **control plane for AI coding-agent actions**: agents ask the gateway to verify
an intent before executing a tool, high-risk actions require human approval, and every action
is recorded as tamper-evident audit evidence that can drive automated recovery
(observe → plan → compensate → verify). It is a FastAPI application (`app/`), a Python SDK
(`sdk/`), and an Alembic-managed database.

What it is **not** is listed in the README's "Limitations" and "What is not claimed" sections;
read those first. SSO, KMS/HSM, and the web dashboard are explicitly not finished features.

## 2. Install from a clean checkout (verified)

```bash
git clone <repository-url>
cd interlock-v4
python -m venv .venv
.venv\Scripts\activate          # Windows (source .venv/bin/activate on POSIX)
pip install -e ".[dev,security]"
```

This is the **only supported install path**. Interlock is not published to any package index,
and the gitignored `requirements-dev.txt` is stale and non-authoritative. Supported Python:
3.11–3.14 (`Requires-Python: >=3.11,<3.15`).

## 3. Configure the minimum (verified)

```bash
cp .env.example .env
```

- SQLite is the default database (`DATABASE_URL=sqlite:///./intentlock.db`) — zero external
  services required for evaluation.
- Set a unique `JWT_SECRET_KEY` (≥32 chars) in every non-development environment.
- `CORS_ORIGINS` in `.env` uses a **JSON array**, e.g. `CORS_ORIGINS=["http://localhost:3000"]`.
- Redis is optional **for development and evaluation**: replay protection then uses an
  in-process memory nonce store (L1) — correct for a single process, explicitly **not**
  sufficient for distributed/multi-instance deployments. Readiness reports
  `"redis":"disabled"`. **Production mode refuses to start** without Redis, requires a
  PostgreSQL `DATABASE_URL`, and requires tenant enforcement (fail-closed startup
  validators in `app/infrastructure/config/settings.py`).

## 4. Start and verify (measured output)

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok"}
curl http://localhost:8000/api/v1/ready
# {"status":"ready","db":"ok","redis":"disabled"}
```

The application auto-migrates a fresh SQLite database on first startup.

## 5. Supported-configuration matrix

| Dimension | Supported (verified here) | Supported (implemented, CI-verified when CI runs) | Not supported / placeholder |
|-----------|---------------------------|--------------------------------------------------|-----------------------------|
| OS | Windows 11 (this evaluation) | Linux (GitHub runners) | — |
| Python | 3.11 (this evaluation) | 3.11–3.14 | <3.11 |
| Database | SQLite (full suite + migrations) | PostgreSQL 14 (CI service; migration workflow) | MySQL |
| Cache/replay | In-process memory nonces (L1, single-process evaluation, verified) | Redis 6/7 as L2 distributed nonce store (CI service; `redis>=4` pinned); **required in production** | Redis Cluster |
| Frontend | — | — | `web/` dashboard: removed in working tree, unbuildable here |
| SSO (OIDC/SAML) | — | — | Architectural placeholder, returns mock data |
| KMS/HSM | — | — | Interface placeholder |
| Payments (Stripe) | — | — | Mock mode only |
| Email (SMTP) | — | — | Logging backend only |
| Package install | `pip install -e .` from clone | — | PyPI (unpublished) |

## 6. Run a safe end-to-end recovery example

```bash
python examples/demo_agent_defense.py
```

or follow the SDK flow in [docs/developer/QUICKSTART.md](../developer/QUICKSTART.md)
(register → token → `verify_intent` → `consume_execution_token` → guarded tool). All of these
paths are also exercised by the automated suite (`tests/`, 2860 tests).

## 7. Inspect the evidence

- **Audit trail**: two stores exist. (1) The database `audit_events` table, queryable through
  the API (`/api/v1/activity` audit-search route and authorization routes) — this is what the
  application reads back. (2) The JSONL file sink `logs/audit_trail.jsonl`
  (`app/infrastructure/logging/audit_logger.py`), where compliance-event records carry a
  SHA-256 hash chain (`previous_hash`/`hash`, verifiable via `export_audit_log`). That logger
  also mirrors records to the `intentlock.audit` stdout logger, so audit JSON appears in
  process output as well as the file.
- **Recovery evidence**: `/api/v1/evidence` routes; schema in
  `docs/recovery/recovery-model.md`. Evidence records are append-only rows; a verification
  pass confirms actual resource state matches the expected recovered state before any
  recovery is reported successful.
- Evidence limitations: evidence is only as good as the adapter that produced it; adapters
  that cannot verify (simulation/reference adapters) return `REQUIRES_MANUAL_ACTION` and
  never claim success.

## 8. Run the verification suite (verified commands)

```bash
pytest tests -q                     # full suite
ruff check app sdk                  # lint
mypy app sdk                        # types
bandit -r app -ll                   # security (CI parity)
pip-audit                           # dependency audit (0 known vulnerabilities)
git diff --check                    # whitespace/errors
```

Semgrep is CI-side (via `semgrep/semgrep-action@v1`); for local scans install Semgrep into a
separate tool environment (see [SECURITY.md](../../SECURITY.md) for the known upstream
advisory context).

## 9. Backup, restore, and migrations

- **SQLite**: stop the app, copy the database file (plus any `-wal`/`-shm` files), restart.
  Verified: file-copy backups pass `PRAGMA integrity_check`, report the correct Alembic
  revision, and restore losslessly (evidence: `logs/v6_gate_closure/v6_mig_data_safety.txt`).
- **PostgreSQL**: `pg_dump` / `pg_restore` (not exercised in this environment).
- **Migrations**: forward-only heads; `alembic check` enforces model↔migration parity.
  If `alembic check` reports drift, do not weaken or skip it — see the migration review
  (`INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md`) for the approved reconciliation path and the
  failed-downgrade recovery runbook.

## 10. Troubleshoot and shut down

| Symptom | Meaning / action |
|---------|------------------|
| readiness `"redis":"disabled"` | Expected without Redis; replay protection uses DB nonces |
| `alembic check` fails with "new upgrade operations" | Schema drift (models ≠ migrations) — a release blocker, not noise; see §9 |
| 503 on writes | Circuit-breaker/rate-limit engaged; see `/api/v1/circuit-breaker` and metrics routes |
| Startup fails on `JWT_SECRET_KEY` | Set a ≥32-char secret in `.env` |
| `CORS_ORIGINS` parse error | Must be a JSON array, e.g. `["http://localhost:3000"]` |
| Shutdown | Stop the ASGI server (SIGTERM/CTRL-C). Recovery plans, leases, and quota state are persisted in the database; interrupted plans survive restart and can be resumed via the recovery-plan resume endpoint. Nonce replay protection is in-process and does not survive restart (evaluation mode) |

Logs are structured JSON; audit events are separate from application logs and are never
written to stdout.
