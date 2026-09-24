import sys

with open(sys.argv[1], chr(114), encoding=chr(39)+chr(117)+chr(116)+chr(102)+chr(45)+chr(56)+chr(39)) as fh:
    lines = fh.readlines()

# Fix 1: add asdict import
has_asdict = False
for l in lines:
    if l.startswith(chr(102)+chr(114)+chr(111)+chr(109)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(101)+chr(115)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(44)+chr(32)+chr(102)+chr(105)+chr(101)+chr(108)+chr(100)):
        has_asdict = any(chr(102)+chr(114)+chr(111)+chr(109)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(101)+chr(115)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116) in ll for ll in lines)
        if not has_asdict:
            lines.insert(lines.index(l)+1, chr(102)+chr(114)+chr(111)+chr(109)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(101)+chr(115)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116)+chr(44)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116)+chr(10))
            print(chr(65)+chr(100)+chr(100)+chr(101)+chr(100)+chr(32)+chr(97)+chr(115)+chr(100)+chr(105)+chr(99)+chr(116)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116))
        break

with open(sys.argv[1], chr(119), encoding=chr(39)+chr(117)+chr(116)+chr(102)+chr(45)+chr(56)+chr(39)) as fh:
    fh.writelines(lines)
print(chr(68)+chr(111)+chr(110)+chr(101))
