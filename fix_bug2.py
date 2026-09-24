with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\recovery_score_service.py', 'r') as f:
    content = f.read()

# The actual content has literal backslash-n, not newline
old = 'conflict_status = getattr(evidence, \" conflict_status\\, None)\n if conflict_status and conflict_status != ConflictStatus.NO_CONFLICT:'
new = 'conflict_status = getattr(evidence, \"conflict_status\", None)\n                if conflict_status and conflict_status != ConflictStatus.NO_CONFLICT:'
content = content.replace(old, new)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\recovery_score_service.py', 'w') as f:
    f.write(content)
print('Fixed')
