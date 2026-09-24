with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Revert the broken fix for line 684 and use a variable instead
old = '''\"bundle_id\": (
                f\"evidence:{action.action_id}:\"
                f\"{hashlib.sha256(\"
                f\"cls._hash_json({'before': before, 'after': after, 'current': current})\"
                f\".encode()).hexdigest()[:12]}\"
            ),'''
new = '''state_hash = cls._hash_json({'before': before, 'after': after, 'current': current})
            bundle_id_hash = hashlib.sha256(state_hash.encode()).hexdigest()[:12]
            \"bundle_id\": f\"evidence:{action.action_id}:{bundle_id_hash}\",'''
content = content.replace(old, new)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed line 684 properly')
