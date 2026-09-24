with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 738 - f-string too long
old_738 = 'evidence_hash = hashlib.sha256(f\"{action.action_id}:{payload_str}:{self._hash_json({\"before\": before_snapshot, \"after\": after_snapshot, \"current\": current_snapshot})}\").encode()).hexdigest()'
new_738 = '''evidence_hash = hashlib.sha256(
            f\"{action.action_id}:{payload_str}:\"
            f\"{self._hash_json({'before': before_snapshot, 'after': after_snapshot, 'current': current_snapshot})}\"
            .encode()
        ).hexdigest()'''
content = content.replace(old_738, new_738)

# Fix line 985 - dict literal too long
content = content.replace(
    'details={\"reason\": \"Current filesystem state matches the captured after-agent state\"},',
    'details={\n                    \"reason\": \"Current filesystem state matches the captured after-agent state\"\n                },'
)

# Fix line 991 - expression too long
content = content.replace(
    'evidence_version=(after_snapshot or {}).get(\"snapshot_hash\") or (after_snapshot or {}).get(\"hash\"),',
    'evidence_version=(\n                (after_snapshot or {}).get(\"snapshot_hash\")\n                or (after_snapshot or {}).get(\"hash\")\n            ),'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 738, 985, 991')
