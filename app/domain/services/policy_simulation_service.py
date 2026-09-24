from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.observability.metrics import metrics

logger = logging.getLogger("intentlock.policy_simulation")


class PolicySimulationResult:
    """Result of a policy simulation."""

    def __init__(
        self,
        simulation_id: str,
        policies: list[dict[str, Any]],
        test_texts: list[str],
        results: list[dict[str, Any]],
    ) -> None:
        self.simulation_id = simulation_id
        self.policies = policies
        self.test_texts = test_texts
        self.results = results


class PolicySimulationService:
    """Policy simulation before deployment.

    AUTH-020: Policy simulation before deployment.
    Allows testing policy changes against historical traffic or
    test scenarios before committing to production.
    """

    def __init__(self) -> None:
        self._simulations: dict[str, PolicySimulationResult] = {}
        self._simulation_log: list[dict[str, Any]] = []

    def simulate_policy(
        self,
        policies: list[dict[str, Any]],
        test_texts: list[str],
    ) -> PolicySimulationResult:
        """Simulate policy evaluation against test texts.

        Returns detailed results for each text/policy combination.
        """
        import hashlib

        key = f"{policies}-{test_texts}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:12]
        simulation_id = f"sim-{digest}"

        results: list[dict[str, Any]] = []
        for text in test_texts:
            text_results: list[dict[str, Any]] = []
            for policy in policies:
                result = self._evaluate_single_policy(policy, text)
                text_results.append(result)
            results.append({
                "text": text[:500],
                "results": text_results,
            })

        blocked_count = sum(
            1 for r in results for pr in r["results"] if pr["blocked"]
        )
        total_checks = len(results) * len(policies)

        simulation = PolicySimulationResult(
            simulation_id=simulation_id,
            policies=policies,
            test_texts=test_texts,
            results=results,
        )
        self._simulations[simulation_id] = simulation

        log_entry = {
            "simulation_id": simulation_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "policy_count": len(policies),
            "test_text_count": len(test_texts),
            "blocked_count": blocked_count,
            "total_checks": total_checks,
            "block_rate": round(blocked_count / max(total_checks, 1), 4),
        }
        self._simulation_log.append(log_entry)
        metrics.increment_policy_decision("simulated")

        return simulation

    def _evaluate_single_policy(
        self, policy: dict[str, Any], text: str,
    ) -> dict[str, Any]:
        """Evaluate a single policy against a single text."""
        import re

        blocked_patterns = policy.get("blocked_patterns", [])
        score_threshold = policy.get("score_threshold", 0.5)
        normalized = (text or "").lower()
        matched_patterns: list[str] = []
        score = 0.0

        for pattern in blocked_patterns:
            try:
                escaped = re.escape(pattern)
                flexible = escaped.replace(r"\ ", r"\s+")
                compiled = re.compile(
                    rf"(?<!\w){flexible}(?!\w)", flags=re.IGNORECASE,
                )
                if compiled.search(normalized):
                    score += 0.35
                    matched_patterns.append(pattern)
            except re.error:
                continue

        if not matched_patterns:
            if "zero-width" in str(policy.get("name", "")).lower():
                for char in {"\u200b", "\u200c", "\u200d", "\ufeff"}:
                    if char in normalized:
                        score += 0.35
                        matched_patterns.append("zero-width-detected")
                        break

        blocked = score >= score_threshold or bool(matched_patterns)
        return {
            "policy_name": policy.get("name", "unnamed"),
            "blocked": blocked,
            "score": round(score, 4),
            "threshold": score_threshold,
            "matched_patterns": matched_patterns,
            "requires_approval": blocked or score >= score_threshold,
        }

    def compare_policies(
        self,
        old_policies: list[dict[str, Any]],
        new_policies: list[dict[str, Any]],
        test_texts: list[str],
    ) -> dict[str, Any]:
        """Compare policy versions — diff simulation results.

        Shows what would change if new policies were deployed.
        """
        old_sim = self.simulate_policy(old_policies, test_texts)
        new_sim = self.simulate_policy(new_policies, test_texts)

        changes: list[dict[str, Any]] = []
        for old_result, new_result in zip(
            old_sim.results, new_sim.results, strict=False,
        ):
            for old_pr, new_pr in zip(
                old_result["results"], new_result["results"], strict=False,
            ):
                if old_pr["blocked"] != new_pr["blocked"]:
                    changes.append({
                        "text": old_result["text"][:200],
                        "policy": old_pr["policy_name"],
                        "old_decision": old_pr["blocked"],
                        "new_decision": new_pr["blocked"],
                        "old_score": old_pr["score"],
                        "new_score": new_pr["score"],
                        "type": "decision_change",
                    })
                elif old_pr["score"] != new_pr["score"]:
                    changes.append({
                        "text": old_result["text"][:200],
                        "policy": old_pr["policy_name"],
                        "old_score": old_pr["score"],
                        "new_score": new_pr["score"],
                        "type": "score_change",
                    })

        return {
            "old_simulation_id": old_sim.simulation_id,
            "new_simulation_id": new_sim.simulation_id,
            "changes": changes,
            "change_count": len(changes),
            "old_block_count": sum(
                1 for r in old_sim.results for pr in r["results"] if pr["blocked"]
            ),
            "new_block_count": sum(
                1 for r in new_sim.results for pr in r["results"] if pr["blocked"]
            ),
            "summary": (
                f"Deploying new policies would change {len(changes)} outcomes: "
                f"block rate {old_sim.results and 'old'} → "
                f"{sum(1 for r in new_sim.results for pr in r['results'] if pr['blocked'])} new blocks"
            ),
        }

    def get_simulation(self, simulation_id: str) -> PolicySimulationResult | None:
        """Retrieve a simulation result."""
        return self._simulations.get(simulation_id)

    def get_simulation_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get policy simulation audit log."""
        return list(self._simulation_log[-limit:])
