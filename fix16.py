with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 684 - f-string too long - use exact match
old = '''\"bundle_id\": f\"evidence:{action.action_id}:{hashlib.sha256(cls._hash_json({'before': before, 'after': after, 'current': current}).encode()).hexdigest()[:12]}\",'''
new = '''\"bundle_id\": (\n                f\"evidence:{action.action_id}:\"\n                f\"{hashlib.sha256(\"\n                f\"cls._hash_json({'before': before, 'after': after, 'current': current})\"
                f\".encode()).hexdigest()[:12]}\"\n            ),'''
content = content.replace(old, new)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed line 684 - exact match')
