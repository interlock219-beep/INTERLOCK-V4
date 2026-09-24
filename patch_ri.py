import re

with open('app/domain/services/recovery_intelligence.py', 'r') as f:
    content = f.read()

# 1. Add FeasibilityReport dataclass after CascadingImpactAnalysis
old = """@dataclass(frozen=True, slots=True)
class CascadingImpactAnalysis:
    root_action_id: str
    cascade_depth: int
    affected_resources: list[str]
    cross_system_impacts: dict[str, list[str]] = field(default_factory=dict)
    blast_radius_estimate: int = 0
    containment_options: list[str] = field(default_factory=list)"""

new = """@dataclass(frozen=True, slots=True)
class CascadingImpactAnalysis:
    root_action_id: str
    cascade_depth: int
    affected_resources: list[str]
    cross_system_impacts: dict[str, list[str]] = field(default_factory=dict)
    blast_radius_estimate: int = 0
    containment_options: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FeasibilityReport:
    feasible: bool
    feasibility_score: float
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    recommended_strategy: RecoveryStrategy | None = None
    evidence_completeness: float = 0.0
    dependency_coverage: float = 0.0
    risk_level: str = "unknown\""""

content = content.replace(old, new)

with open('app/domain/services/recovery_intelligence.py', 'w') as f:
    f.write(content)

print('Step 1 done: FeasibilityReport dataclass added')
