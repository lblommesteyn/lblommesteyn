import sys, os
sys.path.insert(0,'/home/user/lblommesteyn/pcbgolf/tools')
from pcb import load_board
from collections import defaultdict
b = load_board()
groups = defaultdict(list)
for f in b['fps']:
    groups[(f.lib.split(':')[-1], f.value, f.mpn)].append(f.ref)
print(f"{'FOOTPRINT':<28}{'VALUE':<24}{'MPN':<26}{'QTY':>4}  REFS")
print('-'*130)
rows = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0]))
for (lib,val,mpn),refs in rows:
    refs_s = ','.join(sorted(refs)[:8]) + ('...' if len(refs)>8 else '')
    print(f"{lib:<28}{val[:23]:<24}{mpn[:25]:<26}{len(refs):>4}  {refs_s}")
print('-'*130)
print('distinct line items:', len(rows), ' total parts:', len(b['fps']))
