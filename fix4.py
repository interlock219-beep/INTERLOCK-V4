with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 373 - function signature too long
content = content.replace(
    'def _diff_snapshots(cls, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def _diff_snapshots(\n        cls,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 376 - ternary too long
content = content.replace(
    'semantic_changes = cls._diff_values(before_semantic, after_semantic) if before_semantic is not None or after_semantic is not None else []',
    'semantic_changes = (\n                cls._diff_values(before_semantic, after_semantic)\n                if before_semantic is not None or after_semantic is not None\n                else []\n            )'
)

# Fix line 377 - dict comprehension too long
content = content.replace(
    'before_meta = (before.get(\"metadata\") if before and isinstance(before.get(\"metadata\"), dict) else {}) or {}',
    'before_meta = (\n                before.get(\"metadata\")\n                if before and isinstance(before.get(\"metadata\"), dict)\n                else {}\n            ) or {}'
)

# Fix line 378 - dict comprehension too long
content = content.replace(
    'after_meta = (after.get(\"metadata\") if after and isinstance(after.get(\"metadata\"), dict) else {}) or {}',
    'after_meta = (\n                after.get(\"metadata\")\n                if after and isinstance(after.get(\"metadata\"), dict)\n                else {}\n            ) or {}'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 373, 376, 377, 378')
