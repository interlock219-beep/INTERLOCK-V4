# Read the appendix to get ID 1000
with open("INTERLOCK_1000_CAPABILITY_MANIFEST.md", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')
for line in lines:
    if '| 1000 | DX-013 |' in line:
        parts = [p.strip() for p in line.split('|')]
        print(parts)
        break