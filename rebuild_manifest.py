import json

# Load parsed manifest
with open("parsed_manifest.json", "r", encoding="utf-8") as f:
    rows = json.load(f)

# Add missing ID 1000
rows.append({
    'id': '1000',
    'source_id': 'DX-013',
    'capability': 'Interactive API docs',
    'status': 'PLANNED',
    'impl_loc': 'app/',
    'test_loc': 'tests/',
    'sec_val': 'STANDARD',
    'ver_status': 'PENDING',
    'doc': 'PLANNED',
    'limitations': 'Not implemented'
})

print(f"Total rows: {len(rows)}")
ids = [r['id'] for r in rows]
print(f"Unique IDs: {len(set(ids))}")
expected = [f"{i:03d}" for i in range(1, 1001)]
missing = set(expected) - set(ids)
print(f"Missing: {sorted(missing)}")

# Now generate the new manifest without SOURCE ID column
output = []
output.append("# Interlock V4 - 1000 Capability Manifest")
output.append("")
output.append("**Generated:** 2026-09-19")
output.append("**Source:** INTERLOCK_1000_CAPABILITY_ROADMAP.md (authoritative capability-name source, first 1000 entries in roadmap order)")
output.append("**Status model:** IMPLEMENTED = code + tests demonstrably satisfy behavior; PARTIAL = scaffold exists; PLANNED = no evidence of implementation; MISSING = capability gap identified; BLOCKED = external dependency unavailable.")
output.append("")
output.append("## Required Table (IDs 001-1000)")
output.append("")
output.append("| ID | CAPABILITY | STATUS | IMPLEMENTATION LOCATION | TEST LOCATION | SECURITY VALIDATION | VERIFICATION STATUS | DOCUMENTATION | KNOWN LIMITATIONS |")
output.append("|---|---|---|---|---|---|---|---|---|")

for r in rows:
    output.append(f"| {r['id']} | {r['capability']} | {r['status']} | {r['impl_loc']} | {r['test_loc']} | {r['sec_val']} | {r['ver_status']} | {r['doc']} | {r['limitations']} |")

# Add reconciliation section
output.append("")
output.append("## Reconciliation")
output.append("")
output.append("| Metric | Count |")
output.append("|---|---|")

# Count statuses
from collections import Counter
status_counts = Counter(r['status'] for r in rows)
ver_counts = Counter(r['ver_status'] for r in rows)
sec_counts = Counter(r['sec_val'] for r in rows)

output.append(f"| Total Capabilities | {len(rows)} |")
output.append(f"| Unique Consecutive IDs (001-1000) | {len(set(ids))} |")
output.append(f"| IMPLEMENTED | {status_counts.get('IMPLEMENTED', 0)} |")
output.append(f"| PARTIAL | {status_counts.get('PARTIAL', 0)} |")
output.append(f"| PLANNED | {status_counts.get('PLANNED', 0)} |")
output.append(f"| MISSING | {status_counts.get('MISSING', 0)} |")
output.append(f"| BLOCKED | {status_counts.get('BLOCKED', 0)} |")
output.append(f"| VERIFIED | {ver_counts.get('VERIFIED', 0)} |")
output.append(f"| PARTIAL (verification) | {ver_counts.get('PARTIAL', 0)} |")
output.append(f"| PENDING | {ver_counts.get('PENDING', 0)} |")
output.append(f"| CRYPTO_VERIFIED | {sec_counts.get('CRYPTO_VERIFIED', 0)} |")
output.append(f"| ISOLATION_ENFORCED | {sec_counts.get('ISOLATION_ENFORCED', 0)} |")
output.append(f"| PATTERN_BASED | {sec_counts.get('PATTERN_BASED', 0)} |")
output.append(f"| STANDARD | {sec_counts.get('STANDARD', 0)} |")

# Write new manifest
with open("INTERLOCK_1000_CAPABILITY_MANIFEST.md", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("Manifest rebuilt successfully")