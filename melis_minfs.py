#!/usr/bin/env python3
"""
melis_minfs.py — extract & decompress AllWinner Melis MinFS images.

The stock allwinner-image-tool cannot read compressed entries. This implements
the real format (per DongshanPI/D1s-Melis ekernel/filesystem/fs/minfs):

  dentry attribute bits:  DIR=1, MODULE=2, COMPRESS=4
  meta layout:            |name| pad(align4) |extent|
  modules (MODULE|COMPRESS) store ELF data as an array of 32-byte section
  headers (the extent). Each section: Offset,RecSize,RecUnPackSize,Size,
  VAddr,Type,Flags,Attribute. Section attr bit1=MAGIC, bit2=COMPRESS.
  compressed payload = [5-byte LZMA props][raw LZMA1 stream] -> RecUnPackSize.
"""
import struct, lzma, sys

def align4(x): return (x + 3) & ~3

def lz_decode(blob, outlen):
    """7-zip LzmaUncompress equivalent: 5 prop bytes + raw LZMA1 stream."""
    props = blob[0]
    pb = props // 45; rem = props % 45; lp = rem // 9; lc = rem % 9
    dict_size = struct.unpack('<L', blob[1:5])[0]
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1,
                  "dict_size": max(dict_size, 1 << 12),
                  "lc": lc, "lp": lp, "pb": pb}])
    out = dec.decompress(blob[5:], outlen)
    if len(out) != outlen:
        raise ValueError(f"short decode {len(out)}/{outlen}")
    return out

def lz_encode(data, props5):
    """Inverse of lz_decode: produce [5-byte props][raw LZMA1 stream] that the
    firmware's 7-zip LzmaDecode accepts. Reuse the original section's exact 5 props
    bytes (lc/lp/pb + dict_size) so the on-device decoder behaves identically.
    Verified by decoding back to the original."""
    props = props5[0]
    pb = props // 45; rem = props % 45; lp = rem // 9; lc = rem % 9
    dict_size = struct.unpack('<L', props5[1:5])[0]
    filt = [{"id": lzma.FILTER_LZMA1, "dict_size": max(dict_size, 1 << 12),
             "lc": lc, "lp": lp, "pb": pb}]
    raw = lzma.compress(data, format=lzma.FORMAT_RAW, filters=filt)
    out = bytes(props5) + raw
    if lz_decode(out, len(data)) != data:        # self-check: firmware will decode this
        raise RuntimeError("lz_encode round-trip failed")
    return out

def _align(x, a):
    return (x + a - 1) & ~(a - 1)

def repack_image(image_bytes, name, new_sections):
    """Rebuild a MinFS image with compressed module `name` patched. `new_sections`
    maps section-index -> new uncompressed bytes (same length as original = in-place
    instruction patch). Only stored (compressed) bytes, section offsets, and the
    data-area layout change. Returns new image bytes (same total size).
    repack_image(img, name, {}) is a no-op and reproduces `img` byte-for-byte."""
    src = bytes(image_bytes)
    ents = parse(src)
    tgt = next(e for e in ents if e['name'] == name)
    if not (tgt['Attr'] & 4):
        raise ValueError("target is not a compressed module")

    # 1) rebuild target's data blob + extent (section table)
    fdata = src[tgt['Offset']:tgt['Offset'] + tgt['Size']]
    new_ext = bytearray(tgt['extent'])
    blob = bytearray()
    for i, s in enumerate(sections(tgt)):
        orig = fdata[s['Off']:s['Off'] + s['RecSize']]
        if i in new_sections:
            payload = new_sections[i]
            if len(payload) != s['RecUnPack']:
                raise ValueError(f"section {i} length changed {len(payload)}!={s['RecUnPack']}")
            stored = lz_encode(payload, orig[:5]) if (s['Attr'] & 2) else payload
        else:
            stored = orig
        if s['RecSize'] == 0:                       # bss / empty section: keep as-is
            noff, nrec = s['Off'], 0
        else:
            blob += b'\x00' * ((-len(blob)) % 4)    # sections are 4-byte aligned
            noff, nrec = len(blob), len(stored)
            blob += stored
        struct.pack_into('<8L', new_ext, i * 32, noff, nrec, s['RecUnPack'],
                         s['Size'], s['VAddr'], s['Type'], s['Flags'], s['Attr'])
    new_blob = bytes(blob); new_size = len(new_blob)

    # 2) compute new data-area offsets for non-dir files (stock writer alignment)
    table_end = ents[-1]['toff'] + ents[-1]['RecLen']
    image_size = struct.unpack('<L', src[28:32])[0]
    new_off = {}
    off = table_end + 24
    for e in ents:
        if e['Attr'] & 1:                           # dir data lives in the table
            continue
        new_off[e['toff']] = off
        rsize = new_size if e is tgt else e['Size']
        end = off + rsize
        nxt = end + (rsize % 2)
        nxt += nxt % 4
        off = nxt
    if off > image_size:
        raise RuntimeError(f"data overflow {off} > {image_size}")

    # 3) emit: header+table (verbatim) with patched Offsets/Size/extent
    out = bytearray(src[:table_end])
    for e in ents:
        if not (e['Attr'] & 1):
            struct.pack_into('<L', out, e['toff'], new_off[e['toff']])      # dentry.Offset
    struct.pack_into('<L', out, tgt['toff'] + 4, new_size)                  # dentry.Size
    ext_pos = tgt['toff'] + 20 + _align(tgt['NameLen'], 4)
    out[ext_pos:ext_pos + tgt['ExtLen']] = new_ext
    out += b'\x00' * 24                                                     # gap before data

    # 4) data area
    off = table_end + 24
    for e in ents:
        if e['Attr'] & 1:
            continue
        content = new_blob if e is tgt else src[e['Offset']:e['Offset'] + e['Size']]
        out += content
        end = off + len(content)
        nxt = end + (len(content) % 2)
        nxt += nxt % 4
        out += b'\x00' * (nxt - end)
        off = nxt
    out += b'\x00' * (image_size - off)
    struct.pack_into('<L', out, 24, off - (table_end + 24))                 # header FDataLen
    return bytes(out)

def patch_image(image_bytes, name, patches):
    """Apply instruction patches to a module and repack. `patches` = list of
    (vaddr, new_bytes). Each must lie wholly within one section and not change
    its length. Returns new image bytes."""
    src = bytes(image_bytes)
    ent = next(e for e in parse(src) if e['name'] == name)
    _, segs = decompress_file(src, ent)              # segs: (vaddr, data, type) in section order
    # map section index -> mutable payload (only PROGBITS-with-data sections)
    secs = list(sections(ent))
    # align segs (data-bearing) to their section indices
    data_secs = [i for i, s in enumerate(secs) if s['RecSize'] > 0]
    seg_by_sec = {data_secs[k]: segs[k][1] for k in range(len(segs)) if k < len(data_secs)}
    bufs = {i: bytearray(d) for i, d in seg_by_sec.items()}
    changed = set()
    for vaddr, data in patches:
        placed = False
        for i, s in enumerate(secs):
            if i in bufs and s['VAddr'] <= vaddr < s['VAddr'] + len(bufs[i]):
                off = vaddr - s['VAddr']
                if off + len(data) > len(bufs[i]):
                    raise ValueError("patch crosses section end")
                bufs[i][off:off+len(data)] = data
                changed.add(i); placed = True; break
        if not placed:
            raise ValueError(f"vaddr 0x{vaddr:x} not in any section of {name}")
    return repack_image(src, name, {i: bytes(bufs[i]) for i in changed})

def parse(image_bytes):
    b = image_bytes
    if b[0:5] != b'MINFS':
        raise ValueError("not a MINFS image")
    RootDirOffset = struct.unpack('<L', b[8:12])[0]
    DEntryNum     = struct.unpack('<L', b[16:20])[0]
    o = RootDirOffset; ents = []
    for _ in range(DEntryNum):
        Offset  = struct.unpack('<L', b[o:o+4])[0]
        Size    = struct.unpack('<L', b[o+4:o+8])[0]
        UnPack  = struct.unpack('<L', b[o+8:o+12])[0]
        RecLen  = struct.unpack('<H', b[o+12:o+14])[0]
        Attr    = struct.unpack('<H', b[o+14:o+16])[0]
        NameLen = struct.unpack('<H', b[o+16:o+18])[0]
        ExtLen  = struct.unpack('<H', b[o+18:o+20])[0]
        meta    = b[o+20:o+RecLen]
        name    = meta[:NameLen].decode('utf-8', 'replace')
        es      = align4(NameLen)
        extent  = meta[es:es+ExtLen]
        ents.append(dict(name=name, Offset=Offset, Size=Size, UnPack=UnPack,
                         Attr=Attr, NameLen=NameLen, ExtLen=ExtLen, extent=extent,
                         toff=o, RecLen=RecLen))
        o += RecLen
    return ents

def sections(ent):
    ext = ent['extent']
    for i in range(len(ext)//32):
        f = struct.unpack('<8L', ext[i*32:i*32+32])
        yield dict(Off=f[0], RecSize=f[1], RecUnPack=f[2], Size=f[3],
                   VAddr=f[4], Type=f[5], Flags=f[6], Attr=f[7])

def decompress_file(b, ent):
    """Return (flat_bytes, segments) where segments=[(vaddr,bytes,type)].
    flat_bytes = all section payloads concatenated (good for strings)."""
    fdata = b[ent['Offset']:ent['Offset']+ent['Size']]
    if not (ent['Attr'] & 4):           # not compressed -> raw file
        return fdata, [(0, fdata, 0)]
    if not (ent['Attr'] & 2):           # compressed simple file (single stream)
        return lz_decode(fdata, ent['UnPack']), [(0, b'', 0)]
    flat = bytearray(); segs = []
    for s in sections(ent):
        seg = fdata[s['Off']:s['Off']+s['RecSize']]
        if s['Attr'] & 2 and s['RecSize']:
            data = lz_decode(seg, s['RecUnPack'])
        else:
            data = seg
        if data:
            flat += data
            segs.append((s['VAddr'], data, s['Type']))
    return bytes(flat), segs

def build_elf(b, ent):
    """Reconstruct a RISC-V ELF64 from a module's sections (PT_LOAD per section),
    so Ghidra/objdump load it at the correct virtual addresses."""
    fdata = b[ent['Offset']:ent['Offset']+ent['Size']]
    loads = []  # (vaddr, data, memsz)
    for s in sections(ent):
        if s['Attr'] & 1:            # skip melis MAGIC metadata section
            continue
        if s['Type'] == 8:           # NOBITS / bss
            if s['Size']:
                loads.append((s['VAddr'], b'', s['Size']))
            continue
        seg = fdata[s['Off']:s['Off']+s['RecSize']]
        data = lz_decode(seg, s['RecUnPack']) if (s['Attr'] & 2 and s['RecSize']) else seg
        if data or s['Size']:
            loads.append((s['VAddr'], data, max(s['Size'], len(data))))
    loads.sort(key=lambda x: x[0])
    entry = loads[0][0] if loads else 0
    EHSZ, PHSZ = 64, 56
    nph = len(loads)
    # lay out file: [ehdr][phdrs][segment data...]
    body = b''; phdrs = b''; foff = EHSZ + nph * PHSZ
    for vaddr, data, memsz in loads:
        pad = (-foff) % 16
        body += b'\0' * pad; foff += pad
        phdrs += struct.pack('<IIQQQQQQ', 1, 7, foff, vaddr, vaddr,
                             len(data), memsz, 0x1000)  # PT_LOAD, RWX
        body += data; foff += len(data)
    ehdr = b'\x7fELF' + bytes([2,1,1,0]) + b'\0'*8
    ehdr += struct.pack('<HHIQQQIHHHHHH',
        2, 243, 1, entry, EHSZ, 0, 0, EHSZ, PHSZ, nph, 0, 0, 0)  # ET_EXEC, EM_RISCV
    return ehdr + phdrs + body

def _main():
    import argparse
    ap = argparse.ArgumentParser(
        prog='melis_minfs',
        description='Read/decompress AllWinner Melis MinFS images, including the '
                    'LZMA-compressed ELF modules the stock tool cannot handle. '
                    'For patching/repacking use the library API (see repo README).')
    ap.add_argument('file', help='a MinFS image, e.g. data_udisk.fex')
    ap.add_argument('--list', action='store_true', help='list all entries (default)')
    ap.add_argument('--extract', metavar='NAME',
                    help='decompress NAME to flat bytes (modules: all sections concatenated)')
    ap.add_argument('--elf', metavar='NAME',
                    help='reconstruct NAME as a loadable RISC-V ELF64 (for Ghidra/objdump)')
    ap.add_argument('--output', metavar='FILE', help='output filename for --extract/--elf')
    args = ap.parse_args()

    b = open(args.file, 'rb').read()
    ents = parse(b)

    if args.elf:
        ent = next(e for e in ents if e['name'] == args.elf)
        out = args.output or args.elf + '.elf'
        open(out, 'wb').write(build_elf(b, ent))
        print(f"{args.elf} -> {out}")
    elif args.extract:
        ent = next(e for e in ents if e['name'] == args.extract)
        flat, segs = decompress_file(b, ent)
        out = args.output or args.extract + '.bin'
        open(out, 'wb').write(flat)
        print(f"{args.extract}: Attr={ent['Attr']} -> {len(flat)} bytes, {len(segs)} segs -> {out}")
        for v, d, t in segs[:20]:
            print(f"  VAddr=0x{v:08x} len={len(d):>8} type={t}")
    else:
        comp = [e for e in ents if e['Attr'] & 4]
        print(f"{len(ents)} entries, {len(comp)} compressed:")
        for e in comp:
            tag = 'MODULE' if e['Attr'] & 2 else 'file'
            print(f"  {e['name']:18s} {tag:6s} stored={e['Size']:>9} unpack={e['UnPack']:>9}")

if __name__ == '__main__':
    _main()
