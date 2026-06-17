#!/usr/bin/env python3
"""Find direct callers (jal/c.jal/c.j) of a target address in a melis module.
Requires capstone (`pip3 install capstone`)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rvxref

def parse_off(ops):
    p = ops.split(',')[-1].strip()
    try:
        return int(p, 0)
    except ValueError:
        return None

def callers(insns, order, targets):
    tgt = set(targets)
    out = []
    for a in order:
        mn, ops, sz = insns[a]
        if mn in ('jal', 'c.jal', 'c.j', 'j'):
            off = parse_off(ops)
            if off is None:
                continue
            target = (a + off) & 0xFFFFFFFFFFFFFFFF
            if target in tgt:
                out.append((a, mn, target))
    return out

if __name__ == '__main__':
    image, name = sys.argv[1], sys.argv[2]
    targets = [int(x, 0) for x in sys.argv[3:]]
    mem = rvxref.load(image, name)
    insns, order = rvxref.disasm_all(mem)
    cs = callers(insns, order, targets)
    print(f"{len(cs)} direct callers of {[hex(t) for t in targets]}")
    for a, mn, t in cs:
        print(f"  call 0x{t:x} from 0x{a:x} ({mn})")
