with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\recovery_score_service.py', 'r') as f:
    lines = f.readlines()

# Fix line 584 (0-indexed: 583)
for i, line in enumerate(lines):
    if 'conflict_status = getattr(evidence' in line and 'conflict_status' in line:
        lines[i] = '                conflict_status = getattr(evidence, \"conflict_status\", None)\n                if conflict_status and conflict_status != ConflictStatus.NO_CONFLICT:\n'
        print(f'Fixed line {i+1}')
        break

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\recovery_score_service.py', 'w') as f:
    f.writelines(lines)
print('Done')
