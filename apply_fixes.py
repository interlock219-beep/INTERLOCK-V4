import sys
p = sys.argv[1]
with open(p, chr(114), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as fh:
    lines = fh.readlines()

# Fix 1: add asdict import if missing
prefix = chr(102)+chr(114)+chr(111)+chr(109)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(101)+chr(115)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(44)+chr(32)+chr(102)+chr(105)+chr(101)+chr(108)+chr(100)+chr(10)
asimp = chr(102)+chr(114)+chr(111)+chr(109)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(101)+chr(115)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116)+chr(44)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116)+chr(10)
if not any(asimp in l for l in lines):
    for i, l in enumerate(lines):
        if l.startswith(prefix):
            lines.insert(i+1, asimp)
            print(chr(65)+chr(100)+chr(100)+chr(101)+chr(100)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116))
            break

# Fix 2: replace async sum() generator with regular for loop
# Find dep_edges_ok = sum( ... )  line and replace with for loop
target = chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(61)+chr(32)+chr(115)+chr(117)+chr(109)+chr(40)
found_idx = -1
for i, l in enumerate(lines):
    if target in l and chr(102)+chr(111)+chr(114)+chr(32)+chr(97) in l:
        found_idx = i
        break
if found_idx >= 0:
    indent = len(lines[found_idx]) - len(lines[found_idx].lstrip())
    sp = chr(32)*indent
    sp4 = chr(32)*(indent+4)
    new_block = []
    new_block.append(sp + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(61)+chr(32)+chr(48)+chr(10))
    new_block.append(sp + chr(102)+chr(111)+chr(114)+chr(32)+chr(97)+chr(32)+chr(105)+chr(110)+chr(32)+chr(97)+chr(99)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115)+chr(58)+chr(10))
    new_block.append(sp4 + chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(32)+chr(61)+chr(32)+chr(97)+chr(119)+chr(97)+chr(105)+chr(116)+chr(32)+chr(115)+chr(101)+chr(108)+chr(102)+chr(46)+chr(95)+chr(103)+chr(101)+chr(116)+chr(95)+chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(40)+chr(116)+chr(101)+chr(110)+chr(97)+chr(110)+chr(116)+chr(95)+chr(105)+chr(100)+chr(44)+chr(32)+chr(97)+chr(46)+chr(97)+chr(99)+chr(116)+chr(105)+chr(111)+chr(110)+chr(95)+chr(105)+chr(100)+chr(41)+chr(10))
    new_block.append(sp4 + chr(105)+chr(102)+chr(32)+chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(32)+chr(105)+chr(115)+chr(32)+chr(110)+chr(111)+chr(116)+chr(32)+chr(78)+chr(111)+chr(110)+chr(101)+chr(58)+chr(10))
    new_block.append(sp4*2 + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(43)+chr(61)+chr(32)+chr(49)+chr(10))
    new_block.append(sp4*2 + chr(105)+chr(102)+chr(32)+chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(46)+chr(100)+chr(101)+chr(112)+chr(101)+chr(110)+chr(100)+chr(101)+chr(110)+chr(99)+chr(121)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(58)+chr(10))
    new_block.append(sp4*3 + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(43)+chr(61)+chr(32)+chr(49)+chr(10))
    new_block.append(sp4*2 + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(61)+chr(32)+chr(109)+chr(105)+chr(110)+chr(40)+chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(44)+chr(32)+chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(41)+chr(10))
    new_block.append(sp + chr(100)+chr(101)+chr(112)+chr(101)+chr(110)+chr(100)+chr(101)+chr(110)+chr(99)+chr(121)+chr(95)+chr(99)+chr(111)+chr(118)+chr(101)+chr(114)+chr(97)+chr(103)+chr(101)+chr(32)+chr(61)+chr(32)+chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(47)+chr(32)+chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(10))
    lines[found_idx:found_idx+1] = new_block
    print(chr(70)+chr(105)+chr(120)+chr(101)+chr(100)+chr(32)+chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(103)+chr(101)+chr(110)+chr(101)+chr(114)+chr(97)+chr(116)+chr(111)+chr(114))

with open(p, chr(119), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as fh:
    fh.writelines(lines)
print(chr(68)+chr(111)+chr(110)+chr(101))
