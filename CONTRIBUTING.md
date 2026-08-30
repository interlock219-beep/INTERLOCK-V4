# Contributing to Interlock

Thank you for your interest in contributing to Interlock. This guide explains how to set up your development environment, run tests and quality checks, and submit changes.

## Development setup

```bash
# 1. Clone the repository
git clone <repository-url>
cd interlock-v4

# 2. Create and activate a virtual environment (Python 3.11+)
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -e ".[dev,security]"

# 4. Configure environment
cp .env.example .env
```

## Running tests

```bash
pytest -q
```

## Quality checks

```bash
# Lint
ruff check app sdk tests

# Type check
mypy app

# Security scan
python -m bandit -r app sdk

# Dependency audit
pip-audit

# Compile check
python -m compileall app sdk tests

# Database migrations
alembic upgrade head
alembic check
alembic current
```

## Before submitting a pull request

- [ ] Run `pytest -q` and confirm all tests pass
- [ ] Run `ruff check app sdk tests` and confirm no errors
- [ ] Run `mypy app` and confirm no issues
- [ ] Consider security implications of your change
- [ ] Update documentation if you change behavior or add features
- [ ] Do not commit secrets, tokens, or credentials
- [ ] Do not commit runtime data (`*.db`, `logs/`, `keys/`, `.env`)

## Code of conduct

Be respectful and constructive. We are building security software for AI agents; rigor and courtesy matter.
