"""Every API route must be authenticated (API-AUTH-01).

A route without an auth dependency is reachable by anyone who can open a
socket. This test walks the route modules and fails when an endpoint is
added without one, so the property is enforced continuously instead of being
re-checked by hand.

Endpoints that are public BY DESIGN are listed explicitly below with the
mechanism that makes them safe. Adding a new public route fails the test
until it is justified here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_DIR = REPO_ROOT / "app" / "presentation" / "api" / "v1" / "routes"

# Endpoints that are intentionally unauthenticated, with the reason they are
# safe. A new public route must be added here deliberately.
PUBLIC_ENDPOINTS: dict[tuple[str, str], str] = {
    ("health.py", "health_check"): "container liveness probe - exposes no data",
    ("health.py", "readiness_check"): "container readiness probe - exposes no data",
    ("auth.py", "register"): "registration: the caller has no identity yet",
    ("auth.py", "login"): "login: the caller has no identity yet",
    ("auth.py", "refresh"): "token refresh: the refresh token is the credential",
    ("mfa.py", "request_password_reset"): "password reset request: no session exists yet",
    ("mfa.py", "confirm_password_reset"): "password reset confirmation: the reset token is the credential",
    ("mfa.py", "request_email_verification"): "email verification request",
    ("mfa.py", "confirm_email_verification"): "email verification: the emailed token is the credential",
    ("sso.py", "list_providers"): "OIDC provider discovery: public metadata",
    ("sso.py", "authorize"): "OIDC redirect endpoint",
    ("sso.py", "callback"): "OIDC callback: the provider's assertion is the credential",
    ("discovery.py", "jwks"): "public key set for token verification",
    ("billing.py", "list_plans"): "public pricing information",
    ("billing.py", "get_publishable_key"): "publishable key: public by definition",
    ("billing.py", "billing_webhook"): "Stripe webhook: the signature is verified (Stripe-Signature)",
    ("webhook.py", "ingest_webhook"): "ingest webhook: the HMAC signature is verified (X-Hub-Signature-256)",
}

AUTH_MARKERS = (
    "CurrentUser",
    "current_user",
    "require_role",
    "require_hitl_approver",
    "require_recovery_executor",
    "get_current_user",
    "require_tenant",
    "get_api_key",
    "verify_signature",
    "api_key",
)


def _alias_definitions(tree: ast.Module) -> dict[str, str]:
    """Resolve ``X = Annotated[...]`` aliases to their definition text."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        value: ast.expr | None = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        if value is None:
            continue
        is_annotated = (
            isinstance(value, ast.Subscript)
            and isinstance(value.value, ast.Name)
            and value.value.id == "Annotated"
        ) or (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Annotated"
        )
        if not is_annotated:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                aliases[target.id] = ast.unparse(value)
    return aliases


def _route_endpoints(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    endpoints = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
            ):
                endpoints.append(node)
                break
    return endpoints


def _auth_evidence(node: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, str]) -> str:
    parts: list[str] = []
    args = node.args
    for arg in list(args.args) + list(args.kwonlyargs):
        if arg.annotation is not None:
            text = ast.unparse(arg.annotation)
            parts.append(text)
            for name, definition in aliases.items():
                if name in text:
                    parts.append(definition)
    for default in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
        parts.append(ast.unparse(default))
    return " ".join(parts)


def test_every_route_requires_authentication() -> None:
    unauthenticated: list[str] = []
    total = 0
    for file in sorted(ROUTES_DIR.glob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        aliases = _alias_definitions(tree)
        for node in _route_endpoints(tree):
            total += 1
            evidence = _auth_evidence(node, aliases)
            if any(marker in evidence for marker in AUTH_MARKERS):
                continue
            if (file.name, node.name) in PUBLIC_ENDPOINTS:
                continue
            unauthenticated.append(f"{file.name}:{node.name}")
    assert total > 100, "the route scan should find the whole API surface"
    assert not unauthenticated, f"routes without an authentication dependency: {unauthenticated}"


def test_the_public_endpoint_list_stays_explicit() -> None:
    """A public endpoint must be justified in this file, not added silently."""
    declared = set(PUBLIC_ENDPOINTS)
    found = {
        (file.name, node.name)
        for file in sorted(ROUTES_DIR.glob("*.py"))
        for node in _route_endpoints(ast.parse(file.read_text(encoding="utf-8")))
    }
    missing = declared - found
    assert not missing, f"declared public endpoints that no longer exist: {missing}"
    assert all(reason for reason in PUBLIC_ENDPOINTS.values()), (
        "every public endpoint must state why it is safe"
    )


def test_route_modules_are_importable() -> None:
    """The route modules the scan walks must also import cleanly."""
    import importlib

    for file in sorted(ROUTES_DIR.glob("*.py")):
        if file.name == "__init__.py":
            continue
        module_name = (
            "app.presentation.api.v1.routes." + file.stem
        )
        importlib.import_module(module_name)
