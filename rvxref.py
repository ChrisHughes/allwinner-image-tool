#!/usr/bin/env python3
"""Lightweight RISC-V xref/address-materialization finder for melis modules.
Requires capstone (`pip3 install capstone`)."""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import melis_minfs as m
from capstone import *

def load(image, name):
    b = open(image, 'rb').read()
    e = next(x for x in m.parse(b) if x['name'] == name)
    flat, segs = m.decompress_file(b, e)
    mem = [(v, d) for (v, d, t) in segs if d]
    return mem

def reader(mem):
    def read(va, n):
        for base, data in mem:
            if base <= va < base + len(data):
                return data[base <= va and va - base:va - base + n]
        return None
    return read

def disasm_all(mem):
    md = Cs(CS_ARCH_RISCV, CS_MODE_RISCV64 | CS_MODE_RISCVC)
    md.detail = False
    insns = {}        # addr -> (mnemonic, op_str, size)
    order = []
    for base, data in mem:
        off = 0; n = len(data)
        while off < n:
            advanced = False
            for ins in md.disasm(data[off:], base + off):
                insns[ins.address] = (ins.mnemonic, ins.op_str, ins.size)
                order.append(ins.address)
                off = ins.address - base + ins.size
                advanced = True
            if not advanced:
                off += 2   # skip undecodable halfword, resume (RVC is 2-byte aligned)
    return insns, order

def imm(op):
    op = op.strip()
    try:
        return int(op, 0)
    except ValueError:
        return None

def find_addr_materializations(insns, order, targets):
    """Find auipc+addi / lui+addi pairs that compute any target address."""
    tgtset = set(targets)
    hits = []  # (final_addr, auipc_addr, completing_addr)
    for idx, a in enumerate(order):
        mn, ops, sz = insns[a]
        base = None; reg = None
        if mn == 'auipc':
            parts = ops.split(',')
            reg = parts[0].strip()
            hi = imm(parts[1])
            if hi is not None: base = (a + (hi << 12)) & 0xFFFFFFFFFFFFFFFF
        elif mn in ('lui', 'c.lui'):
            parts = ops.split(',')
            reg = parts[0].strip()
            hi = imm(parts[1])
            if hi is not None:
                v = (hi << 12) & 0xFFFFFFFF
                base = v | (0xFFFFFFFF00000000 if v & 0x80000000 else 0)
        if base is None:
            continue
        # look ahead for addi rd, reg, lo  (rd usually == reg)
        for j in range(idx + 1, min(idx + 8, len(order))):
            b2 = order[j]; m2, o2, s2 = insns[b2]
            if m2 in ('addi', 'c.addi', 'addiw', 'c.addiw', 'mv', 'c.mv'):
                p = o2.split(',')
                if len(p) >= 2 and p[1].strip() == reg:
                    lo = imm(p[-1]) if m2 not in ('mv', 'c.mv') else 0
                    if lo is None: continue
                    final = (base + lo) & 0xFFFFFFFFFFFFFFFF
                    if final in tgtset:
                        hits.append((final, a, b2))
                    if p[0].strip() == reg:  # reg overwritten, stop chain
                        break
            # also handle ld/lw with offset (GOT-style) -> pointer load
            if m2 in ('ld', 'lw') and ('(' + reg + ')') in o2:
                pass
        # bare base match (some refs are just lui to a page then used directly)
        if base in tgtset:
            hits.append((base, a, a))
    return hits

if __name__ == '__main__':
    image, name = sys.argv[1], sys.argv[2]
    targets = [int(x, 0) for x in sys.argv[3:]]
    mem = load(image, name)
    insns, order = disasm_all(mem)
    print(f"disassembled {len(order)} instructions")
    hits = find_addr_materializations(insns, order, targets)
    print(f"found {len(hits)} materializations of {[hex(t) for t in targets]}")
    for final, a, comp in hits:
        print(f"  ref to 0x{final:x} at code 0x{a:x} (completed 0x{comp:x})")
