from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.domain.services.tool_security import ToolArgumentValidator, ToolSecurityError
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/tool-security", tags=["Tool Security"])

_validator = ToolArgumentValidator()


class ValidatePathRequest:
    pass


class ValidateUrlRequest:
    pass


@router.post("/validate-arguments")
async def validate_tool_arguments(
    arguments: dict[str, object],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Validate tool arguments for adversarial patterns. TOOL-001."""
    try:
        _validator.validate_schema(arguments)
        return {"valid": True, "errors": []}
    except ToolSecurityError as exc:
        return {"valid": False, "errors": [str(exc)]}


@router.post("/validate-path")
async def validate_tool_path(
    path: str,
    current_user: CurrentUser,
    allow_absolute: bool = False,
) -> dict[str, object]:
    """Validate a file path for traversal attacks. TOOL-002."""
    try:
        _validator.validate_path(path, allow_absolute=allow_absolute)
        return {"valid": True, "path": path}
    except ToolSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/validate-url")
async def validate_tool_url(
    url: str,
    current_user: CurrentUser,
    allowed_hosts: list[str] | None = None,
) -> dict[str, object]:
    """Validate a URL for SSRF and unsafe schemes. TOOL-003."""
    try:
        _validator.validate_url(url, allowed_hosts=allowed_hosts)
        return {"valid": True, "url": url}
    except ToolSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
