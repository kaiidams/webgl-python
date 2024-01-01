import re
with open('webgl.idl') as fp:
    x = fp.read()
x = re.sub(r'//.*\n', '', x)
x = re.sub(r'/\*.*\*/', '', x)
x = re.sub(r'\[[^]]*\]', '', x)
x = re.sub(r'\([^\)]*\)', '()', x)
x = re.sub(r'typedef[^;]*;', '', x)

for m in re.finditer(r'interface\s+(mixin\s+)?(\S+)\s.*\{([^\}]*)\}', x):
    y = m.group(2)
    z = m.group(3)
    print(y)
    for w in z.split(';'):
        print('-', w.strip())

with open('a.idl', 'w') as fp:
    fp.write(x)
