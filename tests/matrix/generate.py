#!/usr/bin/env python3
"""Independent conventional i,j,k integer oracle; no mesh schedule knowledge."""
import random
from pathlib import Path
import sys
rng = random.Random(0x4d415431)
dest = Path(sys.argv[1])
words = []
cases = 256
for t in range(cases):
    k = [0,1,3,4,7,8,15,16][t % 8]
    a = [[rng.randrange(-128,128) if p<k else 0 for p in range(16)] for i in range(4)]
    b = [[rng.randrange(-128,128) if p<k else 0 for j in range(4)] for p in range(16)]
    c = [[rng.randrange(1<<32) for j in range(4)] for i in range(4)]
    if t < 4:
        a = [[[-128,127,-1,0][t] for p in range(16)] for i in range(4)]
        b = [[[-128,127,1,0][t] for j in range(4)] for p in range(16)]
    expected = [[(c[i][j] + sum(a[i][p]*b[p][j] for p in range(16))) & 0xffffffff
                 for j in range(4)] for i in range(4)]
    for matrix in (a, [[b[p][j] for p in range(16)] for j in range(4)]):
        for row in matrix:
            for p in range(0,16,4):
                words.append(sum((row[p+x]&255) << (8*x) for x in range(4)))
    words += sum(c, []) + sum(expected, [])
dest.write_text(''.join(f'{x:08x}\n' for x in words))
print(f'Generated {cases} independently computed tile cases, seed 0x4d415431')
