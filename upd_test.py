import sys
f=open(sys.argv[1],chr(114),encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56))
lines=f.readlines()
f.close()
old=chr(39)+chr(104)+chr(105)+chr(103)+chr(104)+chr(39)+chr(44)+chr(32)+chr(39)+chr(99)+chr(114)+chr(105)+chr(116)+chr(105)+chr(99)+chr(97)+chr(108)+chr(39)
new=chr(39)+chr(109)+chr(101)+chr(100)+chr(105)+chr(117)+chr(109)+chr(39)+chr(44)+chr(32)+chr(39)+chr(104)+chr(105)+chr(103)+chr(104)+chr(39)+chr(44)+chr(32)+chr(39)+chr(99)+chr(114)+chr(105)+chr(116)+chr(105)+chr(99)+chr(97)+chr(108)+chr(39)
for i,line in enumerate(lines):
    if old in line:
        lines[i]=line.replace(old,new)
        print(chr(70)+chr(105)+chr(120)+chr(101)+chr(100)+chr(32)+chr(108)+chr(105)+chr(110)+chr(101),i+1)
        break
f=open(sys.argv[1],chr(119),encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56))
f.writelines(lines)
f.close()
print(chr(100)+chr(111)+chr(110)+chr(101))