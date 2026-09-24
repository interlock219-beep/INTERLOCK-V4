import sys
f=open(sys.argv[1],chr(114),encoding=chr(39)+chr(117)+chr(116)+chr(102)+chr(45)+chr(56)+chr(39))
lines=f.readlines()
f.close()
target=chr(39)+chr(97)+chr(108)+chr(116)+chr(46)+chr(95)+chr(95)+chr(100)+chr(105)+chr(99)+chr(116)+chr(95)+chr(95)+chr(46)+chr(99)+chr(111)+chr(112)+chr(121)+chr(40)+chr(41)+chr(39)
print(repr(target))
for i,line in enumerate(lines):
    if target in line:
        lines[i]=line.replace(target,sys.argv[2])
        print(chr(70)+chr(105)+chr(120)+chr(101)+chr(100),i+1)
f=open(sys.argv[1],chr(119),encoding=chr(39)+chr(117)+chr(116)+chr(102)+chr(45)+chr(56)+chr(39))
f.writelines(lines)
f.close()
print(chr(100)+chr(111)+chr(110)+chr(101))
