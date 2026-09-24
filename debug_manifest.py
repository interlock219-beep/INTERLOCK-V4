with open('INTERLOCK_1000_CAPABILITY_MANIFEST.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the reconciliation section
idx = content.find('## Reconciliation')
print('Reconciliation at index:', idx)

# Show content around that area
main_table = content[:idx]
lines = main_table.split('\n')
table_lines = [l for l in lines if l.startswith('|') and not '|---|' in l and not '| ID |' in l]
print('Table lines in main:', len(table_lines))
print('Last table line:', table_lines[-1] if table_lines else 'NONE')

# Check if 1000 is in main table
for l in table_lines:
    if '| 1000 |' in l:
        print('Found 1000 in main:', l)
        break
else:
    print('1000 NOT in main table lines')

# Check reconciliation section
recon = content[idx:]
recon_lines = [l for l in recon.split('\n') if l.startswith('|') and not '|---|' in l and not '| Metric |' in l]
print('Reconciliation table lines:', len(recon_lines))
for l in recon_lines[:5]:
    print('  ', l)