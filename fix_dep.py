import sys
p = sys.argv[1]
with open(p, chr(114), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as fh:
    lines = fh.readlines()

target = chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(61)+chr(32)+chr(115)+chr(117)+chr(109)+chr(40)+chr(10)
found_idx = -1
for i, l in enumerate(lines):
    if l.strip() == target.strip():
        found_idx = i
        break
if found_idx >= 0:
    indent = len(lines[found_idx]) - len(lines[found_idx].lstrip())
    sp = chr(32)*indent
    sp4 = chr(32)*(indent+4)
    nb = []
    nb.append(sp + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(61)+chr(32)+chr(48)+chr(10))
    nb.append(sp + chr(102)+chr(111)+chr(114)+chr(32)+chr(97)+chr(32)+chr(105)+chr(110)+chr(32)+chr(97)+chr(99)+chr(116)+chr(105)+chr(111)+chr(110)+chr(115)+chr(58)+chr(10))
    nb.append(sp4 + chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(32)+chr(61)+chr(32)+chr(97)+chr(119)+chr(97)+chr(105)+chr(116)+chr(32)+chr(115)+chr(101)+chr(108)+chr(102)+chr(46)+chr(95)+chr(103)+chr(101)+chr(116)+chr(95)+chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(40)+chr(116)+chr(101)+chr(110)+chr(97)+chr(110)+chr(116)+chr(95)+chr(105)+chr(100)+chr(44)+chr(32)+chr(97)+chr(46)+chr(97)+chr(99)+chr(116)+chr(105)+chr(111)+chr(110)+chr(95)+chr(105)+chr(100)+chr(41)+chr(10))
    nb.append(sp4 + chr(105)+chr(102)+chr(32)+chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(32)+chr(105)+chr(115)+chr(32)+chr(110)+chr(111)+chr(116)+chr(32)+chr(78)+chr(111)+chr(110)+chr(101)+chr(58)+chr(10))
    nb.append(sp4*2 + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(43)+chr(61)+chr(32)+chr(49)+chr(10))
    nb.append(sp4*2 + chr(105)+chr(102)+chr(32)+chr(101)+chr(118)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)+chr(46)+chr(100)+chr(101)+chr(112)+chr(101)+chr(110)+chr(100)+chr(101)+chr(110)+chr(99)+chr(121)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(58)+chr(10))
    nb.append(sp4*3 + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(43)+chr(61)+chr(32)+chr(49)+chr(10))
    nb.append(sp4*2 + chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(61)+chr(32)+chr(109)+chr(105)+chr(110)+chr(40)+chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(44)+chr(32)+chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(41)+chr(10))
    nb.append(sp + chr(100)+chr(101)+chr(112)+chr(101)+chr(110)+chr(100)+chr(101)+chr(110)+chr(99)+chr(121)+chr(95)+chr(99)+chr(111)+chr(118)+chr(101)+chr(114)+chr(97)+chr(103)+chr(101)+chr(32)+chr(61)+chr(32)+chr(100)+chr(101)+chr(112)+chr(95)+chr(101)+chr(100)+chr(103)+chr(101)+chr(115)+chr(95)+chr(111)+chr(107)+chr(32)+chr(47)+chr(32)+chr(116)+chr(111)+chr(116)+chr(97)+chr(108)+chr(10))
    lines[found_idx:found_idx+5] = nb
    print(chr(70)+chr(105)+chr(120)+chr(101)+chr(100)+chr(32)+chr(115)+chr(117)+chr(109)+chr(40)+chr(41)+chr(32)+chr(103)+chr(101)+chr(110)+chr(101)+chr(114)+chr(97)+chr(116)+chr(111)+chr(114))
else:
    print(chr(115)+chr(117)+chr(109)+chr(40)+chr(41)+chr(32)+chr(110)+chr(111)+chr(116)+chr(32)+chr(102)+chr(111)+chr(117)+chr(110)+chr(100))

with open(p, chr(119), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as fh:
    fh.writelines(lines)
print(chr(68)+chr(111)+chr(110)+chr(101))
