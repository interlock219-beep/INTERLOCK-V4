with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 551 - ternary too long
content = content.replace(
    '\"warnings\": [\"current state differs from captured post-action state\"] if concurrent[\"detected\"] else [],',
    '\"warnings\": [\n                \"current state differs from captured post-action state\"\n            ]\n            if concurrent[\"detected\"]\n            else [],'
)

# Fix line 555 - function signature too long
content = content.replace(
    'def _evidence_bundle(cls, action: ProtectedAction, before: dict[str, Any] | None, after: dict[str, Any] | None, current: dict[str, Any] | None, preview: dict[str, Any] | None = None) -> dict[str, Any]:',
    'def _evidence_bundle(\n        cls,\n        action: ProtectedAction,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n        preview: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:'
)

# Fix line 558 - long f-string
old_558 = '\"bundle_id\": f\"evidence:{action.action_id}:{hashlib.sha256(cls._hash_json({\"before\": before, \"after\": after, \"current\": current}).encode()).hexdigest()[:12]}\",'
new_558 = '''\"bundle_id\": (
                f\"evidence:{action.action_id}:\"
                f\"{hashlib.sha256(\"
                f\"cls._hash_json({'before': before, 'after': after, 'current': current})\"
                f\".encode()).hexdigest()[:12]}\"
            ),'''
content = content.replace(old_558, new_558)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 551, 555, 558')
