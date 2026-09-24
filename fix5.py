with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 411 - boolean expression too long
content = content.replace(
    'changed\": bool(structural_changes or semantic_changes or binary[\"changed\"] or metadata_changes or permission_changes or ownership_changes or acl_changes[\"changed\"]),',
    'changed\": bool(\n                structural_changes\n                or semantic_changes\n                or binary[\"changed\"]\n                or metadata_changes\n                or permission_changes\n                or ownership_changes\n                or acl_changes[\"changed\"]\n            ),'
)

# Fix line 420 - dict literal too long
content = content.replace(
    '\"invariants\": [{\"name\": \"snapshot_integrity\", \"passed\": bool(before and before.get(\"snapshot_hash\")), \"details\": \"snapshot hash present\"}],',
    '\"invariants\": [\n                {\n                    \"name\": \"snapshot_integrity\",\n                    \"passed\": bool(before and before.get(\"snapshot_hash\")),\n                    \"details\": \"snapshot hash present\",\n                }\n            ],'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 411, 420')
