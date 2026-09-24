with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 684 - f-string too long (actual line)
old_684 = '\"bundle_id\": f\"evidence:{action.action_id}:{hashlib.sha256(cls._hash_json({\"before\": before, \"after\": after, \"current\": current}).encode()).hexdigest()[:12]}\",'
new_684 = '''\"bundle_id\": (\n                f\"evidence:{action.action_id}:\"\n                f\"{hashlib.sha256(\"\n                f\"cls._hash_json({'before': before, 'after': after, 'current': current})\"
                f\".encode()).hexdigest()[:12]}\"\n            ),'''
content = content.replace(old_684, new_684)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed line 684')
