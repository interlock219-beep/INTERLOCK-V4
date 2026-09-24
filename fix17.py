with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 955 - f-string too long - use exact match
old = '''evidence_hash = hashlib.sha256(
            f\"{action.action_id}:{payload_str}:{self._hash_json({'before': before_snapshot, 'after': after_snapshot, 'current': current_snapshot})}\".encode()
        ).hexdigest()'''
new = '''evidence_hash = hashlib.sha256(
            f\"{action.action_id}:{payload_str}:\"
            f\"{self._hash_json({'before': before_snapshot, 'after': after_snapshot, 'current': current_snapshot})}\"
            .encode()
        ).hexdigest()'''
content = content.replace(old, new)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed line 955 - exact match')
