with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 593 - function signature too long
content = content.replace(
    'def capture_snapshot(self, resource: str, execution_context: dict[str, Any] | None = None) -> dict[str, Any] | None:',
    'def capture_snapshot(\n        self,\n        resource: str,\n        execution_context: dict[str, Any] | None = None,\n    ) -> dict[str, Any] | None:'
)

# Fix line 611 - function signature too long
content = content.replace(
    'def diff_snapshots(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def diff_snapshots(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 616 - function signature too long
content = content.replace(
    'def structural_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def structural_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 619 - function signature too long
content = content.replace(
    'def semantic_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:',
    'def semantic_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> list[dict[str, Any]]:'
)

# Fix line 622 - function signature too long
content = content.replace(
    'def binary_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def binary_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 625 - function signature too long
content = content.replace(
    'def metadata_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def metadata_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 628 - function signature too long
content = content.replace(
    'def permission_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def permission_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 631 - function signature too long
content = content.replace(
    'def ownership_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def ownership_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 634 - function signature too long
content = content.replace(
    'def acl_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def acl_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 637 - function signature too long
content = content.replace(
    'def schema_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:',
    'def schema_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> dict[str, Any]:'
)

# Fix line 640 - function signature too long
content = content.replace(
    'def invariant_diff(self, before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:',
    'def invariant_diff(\n        self,\n        before: dict[str, Any] | None,\n        after: dict[str, Any] | None,\n    ) -> list[dict[str, Any]]:'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 593, 611, 616, 619, 622, 625, 628, 631, 634, 637, 640')
