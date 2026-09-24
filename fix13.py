with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 408 - generator expression too long
old_408 = 'last_before = next(\n                (index for index in range(common - 1, first - 1, -1) if before_bytes[index] != after_bytes[index]),\n                first - 1,\n            )'
new_408 = '''last_before = next(
                (
                    index
                    for index in range(common - 1, first - 1, -1)
                    if before_bytes[index] != after_bytes[index]
                ),
                first - 1,
            )'''
content = content.replace(old_408, new_408)

# Fix line 680 - f-string too long
old_680 = 'bundle_id\": f\"evidence:{action.action_id}:{hashlib.sha256(cls._hash_json({\"before\": before, \"after\": after, \"current\": current}).encode()).hexdigest()[:12]}\",'
new_680 = '''bundle_id\": (\n                f\"evidence:{action.action_id}:\"\n                f\"{hashlib.sha256(\"\n                f\"cls._hash_json({'before': before, 'after': after, 'current': current})\"
                f\".encode()).hexdigest()[:12]}\"\n            ),'''
content = content.replace(old_680, new_680)

# Fix line 946 - f-string too long
old_946 = 'evidence_hash = hashlib.sha256(f\"{action.action_id}:{payload_str}:{self._hash_json({\"before\": before_snapshot, \"after\": after_snapshot, \"current\": current_snapshot})}\").encode()).hexdigest()'
new_946 = '''evidence_hash = hashlib.sha256(
            f\"{action.action_id}:{payload_str}:\"
            f\"{self._hash_json({'before': before_snapshot, 'after': after_snapshot, 'current': current_snapshot})}\"
            .encode()
        ).hexdigest()'''
content = content.replace(old_946, new_946)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 408, 680, 946')
