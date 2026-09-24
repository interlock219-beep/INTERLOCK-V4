import sys
target=sys.argv[1]
with open(target,chr(114),encoding=chr(39)+chr(117)+chr(116)+chr(102)+chr(45)+chr(56)+chr(39)) as fh:
    lines=fh.readlines()
imports_line=-1
for i,line in enumerate(lines):
    if line.startswith(chr(102)+chr(114)+chr(111)+chr(109)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+chr(101)+chr(115)+chr(32)+chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(100)+chr(97)+chr(116)+chr(97)+chr(99)+chr(108)+chr(97)+chr(115)+chr(115)+" field\):
