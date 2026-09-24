with open('app/domain/services/recovery_intelligence.py', 'r') as f:
    content = f.read()

# Verify FeasibilityReport was added
assert 'class FeasibilityReport:' in content, 'FeasibilityReport not found'
print('FeasibilityReport confirmed')

# 2. Add new methods before _get_action
insertion_point = '''    async def _get_action(self, tenant_id: str, action_id: str) -> ProtectedAction | None:'''

new_methods = '''    async def analyze_recovery_feasibility(
        self,
        tenant_id: str,
        actions: list[ProtectedAction],
        conflicts: list[ConflictAnalysis],
        prerequisites: list[PrerequisiteCheck],
        boundaries: BoundaryDefinition,
    ) -> FeasibilityReport:
        blockers: list[str] = []
        warnings: list[str] = []
        mitigations: list[str] = []

        blocking_conflicts = [c for c in conflicts if c.blocking]
        failed_prereqs = [p for p in prerequisites if not p.satisfied]
        irreversible_actions = [
            a.action_id for a in actions
            if Reversibility.normalize(a.reversibility) == Reversibility.IRREVERSIBLE
        ]
        unknown_rev_actions = [
            a.action_id for a in actions
            if Reversibility.normalize(a.reversibility) == Reversibility.UNKNOWN
        ]

        if not actions:
            blockers.append("No actions to recover")
            return FeasibilityReport(
                feasible=False,
                feasibility_score=0.0,
                blockers=blockers,
                warnings=warnings,
                mitigations=mitigations,
                risk_level="critical",
            )

        total = len(actions)

        for c in blocking_conflicts:
            blockers.append(f"Blocking conflict on {c.action_id}: {c.conflict_status.value}")
            mitigations.extend(c.resolution_hints)

        for p in failed_prereqs:
            blockers.append(f"Unsatisfied prerequisite on {p.action_id}: {p.failed_checks}")

        if irreversible_actions:
            blockers.append(f"Irreversible actions cannot auto-recover: {irreversible_actions}")
            mitigations.append("Manual recovery required for irreversible actions")

        if unknown_rev_actions:
            warnings.append(f"Unknown reversibility (fail closed): {unknown_rev_actions}")

        if not boundaries.rollback_boundary and total > 0:
            warnings.append("Empty rollback boundary — no auto-recoverable actions")

        evidence_count = 0
        for action in actions:
            evidence = await self._get_evidence(tenant_id, action.action_id)
            if evidence is not None and evidence.before_state_reference:
                evidence_count += 1

        evidence_completeness = evidence_count / total if total > 0 else 0.0
        if evidence_completeness < 0.5:
            warnings.append(f"Low evidence completeness: {evidence_completeness:.2f}")
            mitigations.append("Capture before-state references for all actions")

        dep_coverage = 0.0
        dep_checked = 0
        for action in actions:
            evidence = await self._get_evidence(tenant_id, action.action_id)
            if evidence is not None:
                dep_checked += 1
                if evidence.dependency_edges:
                    pass
        dependency_coverage = dep_checked / total if total > 0 else 0.0

        if total > 0:
            dep_edges_ok = sum(
                1 for a in actions
                if (await self._get_evidence(tenant_id, a.action_id)) is not None
                and (await self._get_evidence(tenant_id, a.action_id)).dependency_edges
            )
            dependency_coverage = dep_edges_ok / total
        else:
            dependency_coverage = 0.0

        penalty = (
            len(blocking_conflicts) * 0.2
            + len(failed_prereqs) * 0.15
            + len(irreversible_actions) * 0.1
            + len(unknown_rev_actions) * 0.05
            + (1.0 - evidence_completeness) * 0.2
            + (1.0 - dependency_coverage) * 0.1
        )
        feasibility_score = max(0.0, min(1.0, 1.0 - penalty))

        if feasibility_score >= 0.7:
            risk_level = "low"
        elif feasibility_score >= 0.4:
            risk_level = "medium"
        else:
            risk_level = "high"

        if feasibility_score < 0.3 or len(irreversible_actions) > total * 0.5:
            recommended = RecoveryStrategy.MAX_SAFETY
        elif feasibility_score < 0.6:
            recommended = RecoveryStrategy.MINIMAL_CHANGE
        else:
            recommended = RecoveryStrategy.MIN_DOWNTIME

        feasible = len(blockers) == 0 and feasibility_score >= 0.3

        return FeasibilityReport(
            feasible=feasible,
            feasibility_score=round(feasibility_score, 4),
            blockers=blockers,
            warnings=warnings,
            mitigations=mitigations,
            recommended_strategy=recommended,
            evidence_completeness=round(evidence_completeness, 4),
            dependency_coverage=round(dependency_coverage, 4),
            risk_level=risk_level,
        )

    def compute_recovery_ordering(
        self,
        graph: DependencyGraph,
        mode: str = "standard",
    ) -> list[str]:
        order = list(graph.topological_order)

        if graph.cycles:
            cycle_nodes: set[str] = set()
            for cycle in graph.cycles:
                cycle_nodes.update(cycle)
            order = [nid for nid in order if nid not in cycle_nodes]

        missing = [nid for nid in order if nid not in graph.nodes]
        order = [nid for nid in order if nid in graph.nodes]

        if mode == "leaves_first":
            order = list(reversed(order))
        elif mode == "roots_first":
            order = list(order)
        elif mode == "reversibility_first":
            rev_norm = Reversibility.normalize
            auto_rev = Reversibility.AUTOMATICALLY_REVERSIBLE
            cond_rev = Reversibility.CONDITIONALLY_REVERSIBLE
            auto = [n for n in order if graph.nodes[n].reversibility == auto_rev]
            cond = [n for n in order if graph.nodes[n].reversibility == cond_rev]
            other = [n for n in order if graph.nodes[n].reversibility not in (auto_rev, cond_rev)]
            order = auto + cond + other

        if missing:
            logger.warning("Removed missing nodes from ordering: %s", missing)

        return order

    def compute_boundary_risk(
        self,
        boundaries: BoundaryDefinition,
        actions: list[ProtectedAction],
        conflicts: list[ConflictAnalysis],
        prerequisites: list[PrerequisiteCheck],
    ) -> dict[str, Any]:
        total = len(actions) if actions else 0
        if total == 0:
            return {"overall_risk": 0.0, "risk_level": "low", "details": {}}

        rollback_count = len(boundaries.rollback_boundary)
        comp_count = len(boundaries.compensation_boundary)
        human_count = len(boundaries.human_approval_boundary)
        verify_count = len(boundaries.verification_boundary)

        blocking_conflicts = [c for c in conflicts if c.blocking]
        failed_prereqs = [p for p in prerequisites if not p.satisfied]

        rollback_risk = 1.0 - (rollback_count / total)
        comp_risk = 1.0 - (comp_count / total)
        human_risk = human_count / total
        verify_risk = 1.0 - (verify_count / total)
        conflict_risk = len(blocking_conflicts) / total
        prereq_risk = len(failed_prereqs) / total

        overall = (
            rollback_risk * 0.2
            + comp_risk * 0.2
            + human_risk * 0.15
            + verify_risk * 0.15
            + conflict_risk * 0.15
            + prereq_risk * 0.15
        )
        overall = max(0.0, min(1.0, overall))

        if overall >= 0.7:
            risk_level = "critical"
        elif overall >= 0.4:
            risk_level = "high"
        elif overall >= 0.2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "overall_risk": round(overall, 4),
            "risk_level": risk_level,
            "details": {
                "rollback_risk": round(rollback_risk, 4),
                "compensation_risk": round(comp_risk, 4),
                "human_approval_risk": round(human_risk, 4),
                "verification_risk": round(verify_risk, 4),
                "conflict_risk": round(conflict_risk, 4),
                "prerequisite_risk": round(prereq_risk, 4),
                "rollback_count": rollback_count,
                "compensation_count": comp_count,
                "human_approval_count": human_count,
                "verification_count": verify_count,
                "blocking_conflicts": len(blocking_conflicts),
                "failed_prerequisites": len(failed_prereqs),
            },
        }

    def _augment_alternatives(
        self,
        alternatives: list[RecoveryAlternative],
        comparison: PlanComparison,
    ) -> list[RecoveryAlternative]:
        augmented: list[RecoveryAlternative] = []
        selected_id = comparison.selection

        for alt in alternatives:
            is_selected = alt.plan_id == selected_id
            rank_idx = comparison.ranking.index(alt.plan_id) if alt.plan_id in comparison.ranking else -1
            explanations = list(alt.explanations)
            if is_selected:
                explanations.append(f"Selected as best plan by {comparison.ranked_by.value}")
            elif rank_idx >= 0:
                explanations.append(
                    f"Ranked #{rank_idx + 1} by {comparison.ranked_by.value}"
                )

            alt_dict = alt.__dict__.copy()
            alt_dict["explanations"] = explanations
            try:
                augmented.append(RecoveryAlternative(**alt_dict))
            except Exception:
                augmented.append(alt)

        return augmented

    def compare_alternatives_with_evidence(
        self,
        alternatives: list[RecoveryAlternative],
        criterion: PlanComparisonCriterion = PlanComparisonCriterion.SAFETY,
        confidence_weight: float = 0.3,
        safety_weight: float = 0.4,
        evidence_weight: float = 0.3,
    ) -> PlanComparison:
        if not alternatives:
            return PlanComparison(alternatives=[], ranked_by=criterion, ranking=[])

        def combined_score(alt: RecoveryAlternative) -> float:
            m = alt.metrics
            if criterion == PlanComparisonCriterion.SAFETY:
                criterion_score = m.safety_score
            elif criterion == PlanComparisonCriterion.COST:
                criterion_score = -m.estimated_cost
            elif criterion == PlanComparisonCriterion.TIME:
                criterion_score = -m.estimated_time_seconds
            elif criterion == PlanComparisonCriterion.COLLATERAL_DAMAGE:
                criterion_score = -m.collateral_damage_score
            elif criterion == PlanComparisonCriterion.UNCERTAINTY:
                criterion_score = -m.uncertainty_score
            elif criterion == PlanComparisonCriterion.COMPLETENESS:
                criterion_score = m.completeness_score
            elif criterion == PlanComparisonCriterion.HUMAN_IMPACT:
                criterion_score = -m.human_impact_score
            else:
                criterion_score = m.safety_score

            has_blocking = any(c.blocking for c in alt.conflicts)
            has_unsatisfied = any(not p.satisfied for p in alt.prerequisites)
            safety_penalty = 0.0
            if has_blocking:
                safety_penalty -= 0.5
            if has_unsatisfied:
                safety_penalty -= 0.3

            evidence_score = m.completeness_score
            if not alt.boundaries.verification_boundary:
                evidence_score -= 0.2

            return (
                confidence_weight * criterion_score
                + safety_weight * (m.safety_score + safety_penalty)
                + evidence_weight * evidence_score
            )

        ranked = sorted(alternatives, key=combined_score, reverse=True)
        ranking = [a.plan_id for a in ranked]
        selection = ranking[0] if ranking else None

        rationale_parts = [f"Selected {selection} by {criterion.value} (evidence-aware)"]
        if selection:
            selected = next(a for a in ranked if a.plan_id == selection)
            rationale_parts.append(f"combined_score={combined_score(selected):.2f}")
            rationale_parts.append(f"safety={selected.metrics.safety_score:.2f}")
            rationale_parts.append(f"evidence_completeness={selected.metrics.completeness_score:.2f}")

        comparison = PlanComparison(
            alternatives=alternatives,
            ranked_by=criterion,
            ranking=ranking,
            selection=selection,
            selection_rationale="; ".join(rationale_parts),
        )

        return PlanComparison(
            alternatives=alternatives,
            ranked_by=criterion,
            ranking=ranking,
            selection=selection,
            selection_rationale="; ".join(rationale_parts),
        )

    async def _get_action(self, tenant_id: str, action_id: str) -> ProtectedAction | None:'''

content = content.replace(insertion_point, new_methods)

with open('app/domain/services/recovery_intelligence.py', 'w') as f:
    f.write(content)

print('Step 2 done: All new methods added')
