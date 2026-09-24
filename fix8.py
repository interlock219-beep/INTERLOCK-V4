with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 568 - dict literal too long
content = content.replace(
    '\"integrity\": {\"algorithm\": \"sha256\", \"hash\": cls._hash_json({\"before\": before, \"after\": after, \"current\": current})},',
    '\"integrity\": {\n                \"algorithm\": \"sha256\",\n                \"hash\": cls._hash_json({\"before\": before, \"after\": after, \"current\": current}),\n            },'
)

# Fix line 574 - function signature too long
content = content.replace(
    'def _restoration_proof(cls, action: ProtectedAction, before: dict[str, Any] | None, after: dict[str, Any] | None, current: dict[str, Any] | None, verification: VerificationResult) -> dict[str, Any]:',
    'def _restoration_proof(\n        cls,\n        action: ProtectedAction,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n        verification: VerificationResult,\n    ) -> dict[str, Any]:'
)

# Fix line 588 - dict literal too long
content = content.replace(
    '\"integrity\": {\"algorithm\": \"sha256\", \"hash\": cls._hash_json({\"before\": before, \"after\": after, \"current\": current, \"verification\": verification.to_dict()})},',
    '\"integrity\": {\n                \"algorithm\": \"sha256\",\n                \"hash\": cls._hash_json({\n                    \"before\": before,\n                    \"after\": after,\n                    \"current\": current,\n                    \"verification\": verification.to_dict(),\n                }),\n            },'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 568, 574, 588')
