from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, status

from app.domain.services.policy_simulation_service import PolicySimulationService
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/policy", tags=["Policy"])
_policy_service = PolicySimulationService()


@router.post("/simulate")
async def simulate_policy(
    policies: list[dict[str, object]],
    test_texts: list[str],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Simulate policy evaluation against test texts. AUTH-020."""
    if not policies or not test_texts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="policies and test_texts must be non-empty",
        )
    result = _policy_service.simulate_policy(policies, test_texts)
    return {
        "simulation_id": result.simulation_id,
        "policy_count": len(result.policies),
        "test_text_count": len(result.test_texts),
        "results": result.results,
    }


@router.post("/diff")
async def diff_policies(
    old_policies: list[dict[str, object]],
    new_policies: list[dict[str, object]],
    test_texts: list[str],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Compare old vs new policy versions. AUTH-023."""
    if not old_policies or not new_policies or not test_texts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="old_policies, new_policies, and test_texts must be non-empty",
        )
    comparison = _policy_service.compare_policies(
        old_policies,
        new_policies,
        test_texts,
    )
    return comparison


@router.get("/simulation/{simulation_id}")
async def get_simulation(
    simulation_id: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Retrieve a previous policy simulation result."""
    result = _policy_service.get_simulation(simulation_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation not found",
        )
    return {
        "simulation_id": result.simulation_id,
        "policy_count": len(result.policies),
        "test_text_count": len(result.test_texts),
        "results": result.results,
    }


@router.post("/lint")
async def lint_policy(
    policies: list[dict[str, object]],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Lint policies for common issues. AUTH-025."""
    if not policies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="policies must be non-empty",
        )

    issues: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    for policy in policies:
        policy_name = policy.get("name", "unnamed")
        blocked_patterns: list[str] = cast(list[str], policy.get("blocked_patterns", []))
        score_threshold = policy.get("score_threshold")

        if not policy_name or policy_name == "unnamed":
            issues.append(
                {
                    "policy": policy_name,
                    "severity": "error",
                    "message": "Policy must have a non-empty name",
                    "code": "MISSING_NAME",
                }
            )

        if not blocked_patterns:
            warnings.append(
                {
                    "policy": policy_name,
                    "severity": "warning",
                    "message": "Policy has no blocked patterns defined",
                    "code": "NO_BLOCKED_PATTERNS",
                }
            )

        if score_threshold is None:
            warnings.append(
                {
                    "policy": policy_name,
                    "severity": "warning",
                    "message": "Policy has no score_threshold defined",
                    "code": "NO_SCORE_THRESHOLD",
                }
            )

        if score_threshold is not None:
            if not isinstance(score_threshold, (int, float)):
                issues.append(
                    {
                        "policy": policy_name,
                        "severity": "error",
                        "message": "score_threshold must be a number",
                        "code": "INVALID_SCORE_THRESHOLD",
                    }
                )
            elif score_threshold < 0 or score_threshold > 1:
                warnings.append(
                    {
                        "policy": policy_name,
                        "severity": "warning",
                        "message": "score_threshold should be between 0 and 1",
                        "code": "SCORE_THRESHOLD_OUT_OF_RANGE",
                    }
                )

        pattern_counts: dict[str, int] = {}
        for pattern in blocked_patterns:
            if not isinstance(pattern, str) or not pattern.strip():
                issues.append(
                    {
                        "policy": policy_name,
                        "severity": "error",
                        "message": "blocked_patterns must contain non-empty strings",
                        "code": "INVALID_PATTERN",
                    }
                )
                continue
            normalized = pattern.strip().lower()
            pattern_counts[normalized] = pattern_counts.get(normalized, 0) + 1

        for normalized, count in pattern_counts.items():
            if count > 1:
                warnings.append(
                    {
                        "policy": policy_name,
                        "severity": "warning",
                        "message": f"Duplicate pattern '{normalized}' appears {count} times",
                        "code": "DUPLICATE_PATTERN",
                    }
                )

    has_errors = any(i["severity"] == "error" for i in issues)
    return {
        "policy_count": len(policies),
        "issues": issues,
        "warnings": warnings,
        "passed": not has_errors,
        "issue_count": len(issues),
        "warning_count": len(warnings),
    }
