# Allwinner Image Tools
Utility to modify Allwinner firmware images. This set of tools can be used to modify wallpapers, boot logos and other firmware assets in F133 / D1s based car radios such as those from SJoyBring, MELIS and PLZ.

It now also handles the **LZMA-compressed Melis modules** (`init.axf`, `*.mod`, `*.drv`, `*.plg`) that the basic tools can't touch — so you can decompress, disassemble, **binary-patch and repack** the actual application code, not just swap assets. See *[Decompressing & patching Melis modules](#decompressing--patching-melis-modules)* below.

## The tools are as follows:
**allwinner_imagewty.py** - Extract and replace disk images from ImageWTY firmware bundles.

**allwinner_minfs.py** - List, extract and replace *uncompressed* files in a MinFS disk image.

**checksum_tool.py** - Re-calculates CRC32 for a file

**image_tool.py** - Re-encode jpg images into a known-compatible format.

**melis_minfs.py** - Read/decompress/repack MinFS images including the LZMA-compressed ELF modules. Reconstructs loadable RISC-V ELFs and applies in-place instruction patches. *(stdlib only)*

**rvxref.py / rvcalls.py** - RISC-V (RV64GC) cross-reference / caller helpers for analysing decompressed modules. *(needs `capstone`)*

**ghidra_scripts/** - Ghidra headless scripts (`DumpDecomp.java`, `FindDataRefs.java`) to batch-decompile functions and find data references.

## The following steps demonstrate how to use the tools:

### Step 1: Extract the user data disk image from your firmware bundle.
`python ./allwinner_imagewty.py update/LTTF133.img --list`

`python ./allwinner_imagewty.py update/LTTF133.img --extract data_udisk.fex --verbose`

`python ./allwinner_imagewty.py update/LTTF133.img --extract Vdata_udisk.fex --verbose`

### Step 2: Identify and optionally extract your files to replace.
`python ./allwinner_minfs.py data_udisk.fex --list`

`python ./allwinner_minfs.py data_udisk.fex --extract 0.jpg`

### Step 3: Re-encode each jpg image into a compatible format.
Do not skip this step as you can cause your radio to not boot if it cannot read the boot logo image.
`python ./image_tool.py logo0.jpg logo0.jpg`

### Step 4: Replace a file in the disk image.
`python ./allwinner_minfs.py data_udisk.fex --replace 0.jpg 0.jpg --output data_udisk.fex`

### Step 5: Re-calculate CRC32
`python ./checksum_tool.py data_udisk.fex Vdata_udisk.fex`

### Step 6: Repackage the disk image into the firmware bundle.
`python ./allwinner_imagewty.py update/LTTF133.img --verbose --replace data_udisk.fex data_udisk.fex --output update/LTTF133.img`

`python ./allwinner_imagewty.py update/LTTF133.img --verbose --replace Vdata_udisk.fex Vdata_udisk.fex --output update/LTTF133.img`

## Additional notes

- It is recommended to replace images with images of the exact same resolution.
- When setting boot images (called logos in some cases), these are read and interpreted by the MCU, not the application. The expected format for the jpeg is very strict, otherwise the image will fail to load. Use image_tool.py to re-encode these and make them work.

## Decompressing & patching Melis modules

The application code on these radios lives in **compressed** MinFS entries — `init.axf`
(the main app) plus a pile of `*.mod`/`*.drv`/`*.plg` modules. `allwinner_minfs.py` can
only round-trip *uncompressed* entries (jpegs, `Config.ini`, etc.); it errors on the rest.
`melis_minfs.py` understands the real format and lets you get at the code.

### The format (so you trust the tool)
A MinFS entry's `Attribute` bits are `DIR=1`, `MODULE=2`, `COMPRESS=4` (so a compressed
module is `Attr=6`). A module is an **ELF stored as independently-LZMA'd sections**: the
dentry's *extent* is an array of 32-byte section headers
(`Offset, RecSize, RecUnPackSize, Size, VAddr, Type, Flags, Attribute`), and each
compressed section is `[5-byte LZMA1 props][raw LZMA1 stream]` decoded to `RecUnPackSize`
(plain 7-zip `LzmaDecode`). The dentry meta is laid out `|name| pad-to-4 |extent|`.
*(Format confirmed against the Melis source: `DongshanPI/D1s-Melis`,
`ekernel/filesystem/fs/minfs`.)* The SoC is **RISC-V RV64GC (XuanTie C906)**.

### CLI usage
```bash
# list entries (marks which are compressed MODULEs)
python ./melis_minfs.py data_udisk.fex --list

# decompress a module to flat bytes (all sections concatenated — good for `strings`)
python ./melis_minfs.py data_udisk.fex --extract init.axf --output init.axf.bin

# reconstruct a loadable RISC-V ELF64 (each section mapped at its VAddr) for Ghidra/objdump
python ./melis_minfs.py data_udisk.fex --elf init.axf --output init.axf.elf
```

### Patching code (library API)
Patching is inherently scripted — use the Python API. `patch_image` decompresses the
target section, applies your bytes (same length — in-place instruction patch), recompresses
to a firmware-decodable stream, and rebuilds the MinFS. A **no-op repack reproduces the
input byte-for-byte**, so the only delta in a real patch is your instruction(s).

```python
import melis_minfs as m
b = open('data_udisk.fex', 'rb').read()
# replace the instruction(s) at one or more virtual addresses (found via Ghidra/rvxref)
out = m.patch_image(b, 'init.axf', [(0xe91e5412, bytes.fromhex('13057006'))])
open('data_udisk.fex', 'wb').write(out)
```
Then regenerate the `Vdata` checksum and repackage exactly like the asset workflow
(Step 5 → Step 6 above). Useful library functions: `parse`, `decompress_file`,
`build_elf`, `repack_image`, `patch_image`, `lz_decode`, `lz_encode`.

### Reverse-engineering helpers
`rvxref.py` / `rvcalls.py` (need `capstone`) disassemble a decompressed module and find
address materializations / direct callers — handy for locating a config-key read or a
command handler. The `ghidra_scripts/` Java scripts run under Ghidra **headless**
(`analyzeHeadless <proj_dir> <proj> -import init.axf.elf -scriptPath ghidra_scripts
-postScript DumpDecomp.java`); they read targets from `ghidra_targets.txt` /
`ghidra_data_targets.txt` in the working dir and write decompiled C / xrefs to
`ghidra_out.txt`.

## Command line arguments

### allwinner_imagewty.py

`allwinner_imagewty.py <file> <actions>`

|||
|--------|-------|
|`--list`| Lists all disk images in the firmware bundle. |
|`--verbose`| Enables verbose output. |
|`--extract <name>`| Extracts disk image by name. Filename will be same as internal disk name. |
|`--replace <name> <filename>`| Replaces disk image by name with the contents of file. File length must match original.|
|`--output <filename>`| Optionally specify the output of extract function. When used with replace function, it overrides the default naming (\<original name\>.modified) of the new firmware bundle. |

### allwinner_minfs.py

`allwinner_minfs.py <file> <actions>`

|||
|--------|-------|
|`--list`| Lists all files in the disk image. |
|`--verbose`| Enables verbose output. |
|`--extract <name>`| Extracts file name. Filename will be same as internal file name. |
|`--replace <name> <filename>`| Replaces file by name with the contents of file. |
|`--output <filename>`| Optionally specify the filename of the modified disk image when using replace function. The default is (\<original name\>.modified). |

### melis_minfs.py

`melis_minfs.py <file> [actions]`

|||
|--------|-------|
|`--list`| Lists entries and marks which are compressed MODULEs (default action). |
|`--extract <name>`| Decompresses an entry to flat bytes (module sections concatenated). |
|`--elf <name>`| Reconstructs a module as a loadable RISC-V ELF64 for Ghidra/objdump. |
|`--output <filename>`| Output filename for `--extract` / `--elf`. |

Repacking / instruction-patching is done via the library API (`patch_image`, `repack_image`) — see *[Decompressing & patching Melis modules](#decompressing--patching-melis-modules)*.

## Note

This tool is provided without warranty. You are on your own if you brick your device. Backing up the SPI EEPROM before attempting is recommended, I used a CH341A and a 16 pin chip clip to do this without any soldering necessary.