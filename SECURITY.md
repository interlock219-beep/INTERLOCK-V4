# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.x     | :white_check_mark: |

## Reporting a Vulnerability

Interlock takes security seriously. If you discover a security vulnerability, please report it responsibly.

### How to report

Send details to **security@interlock.io** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested remediation (if any)

### What to expect

- Acknowledgment within 5 business days
- A more detailed response within 10 business days outlining remediation plans
- Credit in the security advisory (unless you prefer anonymity)

### Scope

In-scope for reporting includes:

- Authentication and authorization bypasses
- Token forgery or replay attacks
- SQL injection, shell injection, or path traversal
- SSRF or DNS rebinding
- Prompt injection or policy bypass
- Audit log tampering
- Dependency vulnerabilities in runtime dependencies
- Docker image security issues

Out of scope:

- Social engineering of Interlock employees or users
- Physical security of data centers
- Issues in third-party dependencies that are not exploitable in Interlock
- Denial of service without a demonstrated security impact

### Safe harbor

Interlock will not pursue legal action against researchers who:

- Report vulnerabilities in good faith
- Avoid privacy violations, data destruction, or service disruption
- Do not exploit vulnerabilities beyond what is necessary to prove the issue

---

## Dependency security and auditing

### The audited installation surface

The only supported installation path is from tracked files:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,security]"
```

This resolves the runtime dependencies plus the verification tooling (`pytest`, `ruff`, `mypy`,
`bandit`, `pip-audit`, `cyclonedx-bom`, `pre-commit`). The ignored file `requirements-dev.txt`
is **stale and non-authoritative**; it is not used by CI or by these instructions and should not
be treated as an install source.

### Dependency audit

```bash
pip-audit              # against the active environment
```

The documented install path was audited on 2026-10-16 against the live advisory database:
**0 known vulnerabilities across 110 audited dependencies**, `pip check` clean. Evidence:
`logs/v6_gate_closure/v6_final_fresh_pipaudit.json`.

### Known advisories and how they are handled

- **`mcp` CVE-2026-59951 (GHSA-84m7-p3x7-pcfv)** — affects `mcp` 1.8.0–1.29.x; fixed in
  `mcp` 1.30.0 / 2.2.0. Every Semgrep release through the current latest (1.181.0) pins
  `mcp==1.29.0` exactly, so Semgrep cannot currently be installed alongside the fixed version
  (`ResolutionImpossible` verified). For this reason **Semgrep is not part of the installable
  extras**: it is a CI-side analyzer, invoked through `semgrep/semgrep-action@v1` with the
  `p/security-audit`, `p/owasp-top-ten`, and `p/python` rule packs (which bring their own
  Semgrep installation), not through the project's dependency graph. The vulnerable `mcp` code
  path (streamable-HTTP session accumulation) is not exercised by Interlock, which uses the SDK
  client side. Local Semgrep scans remain possible by installing Semgrep into a separate,
  non-audited tool environment; that environment will carry this advisory until Semgrep repins.
- **Runtime-lock accepted advisories** — `ecdsa` (PYSEC-2026-1325) and `python-jose`
  (PYSEC-2026-4298) have no upstream fix and appear only in the production runtime lock
  (`requirements.txt`), which is not part of the audited installation path. They are tracked as
  accepted risk (G-14 in the release-gate record).
- **Stale advisory from superseded tooling** — `nltk` (via `safety`, a tool no longer part of
  any supported path) appears only in long-lived local environments, not in the documented
  install.

A failed audit is treated as a failed security gate. Findings are not suppressed, ignored, or
waived to make a check pass; an exception requires an explicit, reviewed decision recorded in the
release evidence.
