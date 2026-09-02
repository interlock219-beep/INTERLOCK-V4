# Interlock V4 Documentation

Interlock V4 is an enterprise-grade control plane for AI-agent actions. It controls what AI agents can do, observes what they actually do, contains compromised sessions, determines what changed, recovers what can safely be recovered, and independently verifies the resulting state.

**Tagline:** Control. Contain. Recover. Verify.

## Documentation index

- [README](../README.md) — product overview, quickstart, API reference, project status
- [Documentation index](INDEX.md) — this document

## Getting started

- [Developer Quickstart](developer/QUICKSTART.md) — 5-minute local setup
- [Developer Examples](developer/EXAMPLES.md) — multi-agent, LangChain, HITL, Docker
- [Developer Onboarding](developer/ONBOARDING.md) — week-one checklist for new engineers
- [SDK Reference](../sdk/README.md) — Python SDK and LangChain wrapper

## Architecture

- [Architecture](architecture/ARCHITECTURE.md) — layers, trust boundaries, request flow, failure behavior
- [Recovery Engine](architecture/recovery-engine.md) — observe → attribute → discover → plan → recover → verify
- [Causal Recovery](architecture/causal-recovery.md) — causal attribution and conflict preservation
- [Security Model](architecture/security-model.md) — authorization, tokens, tenant isolation, key management

## Recovery

- [Recovery Model](recovery/recovery-model.md) — reversibility classifications, compensation types, execution states
- [Adapter Model](recovery/adapter-model.md) — adapter protocol, production-validated adapters, capability levels
- [Conflict Resolution](recovery/conflict-resolution.md) — drift and conflict detection
- [Recovery Coverage](recovery/recovery-coverage.md) — measurement methodology and honest reporting

## Security

- [Security Assurance Report](security/SECURITY_ASSURANCE_REPORT.md) — controls, test evidence, findings, remediation
- [Threat Model](security/THREAT_MODEL.md) — STRIDE analysis, trust boundaries, residual risk
- [Authorization Architecture](security/AUTHZ_ARCHITECTURE.md) — RBAC, session security, identity management
- [Tenant Isolation](security/TENANT_ISOLATION.md) — multi-tenant data model and isolation enforcement
- [Security Hardening Roadmap](security/SECURITY_HARDENING_ROADMAP.md) — P0–P3 security roadmap
- [Final Independent Audit](security/FINAL_INDEPENDENT_AUDIT.md) — adversarial test results and evidence matrix
- [High-Assurance Gap Analysis](security/HIGH_ASSURANCE_GAP_ANALYSIS.md) — defense-oriented deployment readiness

## Compliance

- [Compliance Readiness Matrix](compliance/COMPLIANCE_READINESS_MATRIX.md) — SOC 2 / ISO 27001 / HIPAA / PCI-DSS evidence preparation

## Operations

- [Release Baseline](operations/RELEASE_BASELINE.md) — V4 architecture, adapters, guarantees, limitations
- [Recovery Validation Report](operations/RECOVERY_VALIDATION_REPORT.md) — chaos engineering and recovery test results
- [Production Readiness Plan](operations/PRODUCTION_READINESS_PLAN.md) — verification matrix and evidence
- [Incident Response](operations/INCIDENT_RESPONSE.md) — containment, key compromise, tenant incident handling
- [Final Status](operations/FINAL_STATUS.md) — security hardening summary and release determination

## Repository layout

```
README.md            — product overview and quickstart
LICENSE              — license terms
CONTRIBUTING.md      — development workflow
SECURITY.md          — vulnerability reporting
docs/
  INDEX.md           — this document
  architecture/      — system architecture and security model
  recovery/          — recovery model, adapters, conflict handling
  security/          — threat model, assurance reports, audit
  compliance/        — compliance readiness matrix
  operations/        — release baseline, validation, incident response
  developer/         — quickstart, examples, onboarding
sdk/                 — Python SDK and LangChain wrapper
  README.md
app/                 — FastAPI application (presentation, application, domain, infrastructure)
tests/               — unit, integration, adversarial, performance, recovery_lab
config/              — policy configuration
alembic/             — database migrations
web/                 — Next.js dashboard
```
