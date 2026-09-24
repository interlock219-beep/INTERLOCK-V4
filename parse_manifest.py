import re

# Read current manifest
with open("INTERLOCK_1000_CAPABILITY_MANIFEST.md", "r", encoding="utf-8") as f:
    content = f.read()

# Parse the main table (before the reconciliation note)
lines = content.split('\n')

# Find the main table rows
table_rows = []
for line in lines:
    if re.match(r'\|\s*\d+\s*\|', line):
        if '| ID |' in line or '|---|' in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 11:  # ID, SOURCE ID, CAPABILITY, STATUS, IMPL, TEST, SEC, VERIF, DOC, LIMITS, (empty)
            table_rows.append({
                'id': parts[1],
                'source_id': parts[2],
                'capability': parts[3],
                'status': parts[4],
                'impl_loc': parts[5],
                'test_loc': parts[6],
                'sec_val': parts[7],
                'ver_status': parts[8],
                'doc': parts[9],
                'limitations': parts[10]
            })

print(f"Parsed {len(table_rows)} rows from main table")
print(f"First row: {table_rows[0]}")
print(f"Last row: {table_rows[-1]}")

# Check for duplicates
ids = [r['id'] for r in table_rows]
print(f"Unique IDs: {len(set(ids))}")
print(f"ID range: {min(ids)} to {max(ids)}")
# Check consecutive
expected = [f"{i:03d}" for i in range(1, 1001)]
missing = set(expected) - set(ids)
extra = set(ids) - set(expected)
print(f"Missing: {sorted(missing)}")
print(f"Extra: {sorted(extra)}")

# Save parsed data
import json
with open("parsed_manifest.json", "w", encoding="utf-8") as f:
    json.dump(table_rows, f, indent=2)