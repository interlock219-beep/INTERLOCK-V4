with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 490 - function signature too long
content = content.replace(
    'def _human_change_analysis(cls, before: dict[str, Any] | None, after: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:',
    'def _human_change_analysis(\n        cls,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 497 - boolean expression too long
content = content.replace(
    '\"human_or_concurrent_change_detected\": not current_matches_after and not current_matches_before,',
    '\"human_or_concurrent_change_detected\": (\n                not current_matches_after\n                and not current_matches_before\n            ),'
)

# Fix line 506 - function signature too long
content = content.replace(
    'def _concurrent_modification(cls, expected: dict[str, Any] | None, current: dict[str, Any] | None, operation: str) -> dict[str, Any]:',
    'def _concurrent_modification(\n        cls,\n        expected: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n        operation: str,\n    ) -> dict[str, Any]:'
)

# Fix line 527 - function signature too long
content = content.replace(
    'def _preview_from_snapshots(cls, action_type: str, before: dict[str, Any] | None, after: dict[str, Any] | None, current: dict[str, Any] | None, target: str) -> dict[str, Any]:',
    'def _preview_from_snapshots(\n        cls,\n        action_type: str,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n        target: str,\n    ) -> dict[str, Any]:'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 490, 497, 506, 527')
