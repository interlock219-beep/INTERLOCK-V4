with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 643 - function signature too long
content = content.replace(
    'def detect_concurrent_modification(self, expected: dict[str, Any] | None, current: dict[str, Any] | None, operation: str = \"restore\") -> dict[str, Any]:',
    'def detect_concurrent_modification(\n        self,\n        expected: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n        operation: str = \"restore\",\n    ) -> dict[str, Any]:'
)

# Fix line 646 - function signature too long
content = content.replace(
    'def preserve_human_changes(self, before: dict[str, Any] | None, after: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:',
    'def preserve_human_changes(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 649 - function signature too long
content = content.replace(
    'def build_evidence_bundle(self, action: ProtectedAction, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None, current: dict[str, Any] | None = None, preview: dict[str, Any] | None = None) -> dict[str, Any]:',
    'def build_evidence_bundle(\n        self,\n        action: ProtectedAction,\n        before: dict[str, Any] | None = None,\n        after: dict[str, Any] | None = None,\n        current: dict[str, Any] | None = None,\n        preview: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:'
)

# Fix line 652 - function signature too long
content = content.replace(
    'def create_restoration_proof(self, action: ProtectedAction, before: dict[str, Any] | None, after: dict[str, Any] | None, current: dict[str, Any] | None, verification: VerificationResult) -> dict[str, Any]:',
    'def create_restoration_proof(\n        self,\n        action: ProtectedAction,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n        current: dict[str, Any] | None,\n        verification: VerificationResult,\n    ) -> dict[str, Any]:'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 643, 646, 649, 652')
