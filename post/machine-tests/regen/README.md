# Compiler regeneration test + post-processor run, one visit

Why: `COMP\NOC` and `COMP\SPC` were not copied from the hard disk, on the assumption that the
compiler regenerates them (and `TAB`) from the source. This tests that assumption on four real programs.
The first run-sheet step (compile the ZZT programs) is part of the same visit.

`ZZR1` to `ZZR4` are unchanged copies of programs from disk H02, under new names so nothing on C: is
overwritten. Compiling them must give the same TAB, NOC and SPC files as the originals, except
possibly in fields that hold the name or the date.

| Program | File on the machine | Copy of | Why it was picked |
|---|---|---|---|
| ZZR1 | `SRG\Z\ZR1` | `Z\EL1` | plain contour (`G88`, `G1`) |
| ZZR2 | `SRG\Z\ZR2` | `Z\BJOLAN2` | `G3` arc, cutter compensation |
| ZZR3 | `SRG\Z\ZR3` | `Z\WEVER1` | rows of holes (`G183`/`G184`) and saw cut (`G85`) |
| ZZR4 | `SRG\Z\ZR4` | `Z\EL` | `G37` rounding moves, 532 bytes |

**Naming on the machine:** the first character of a program name is its folder under `SORG\SRG` and the
rest is the file name (`ZZR1` = `SRG\Z\ZR1`; index entry `AERTS1` = `SRG\A\ERTS1`). The loader does this split.

## Diskette

Build the folder, then copy its contents to the root of a diskette formatted on the Mac (label `TEST`):

    python3 -I tools/make-loader.py /tmp/testdisk post/machine-tests/regen/ZZR? post/machine-tests/ZZT*

This puts the 13 programs plus `LOAD.BAT`, `COLLECT.BAT` and two helpers (`L1.BAT`, `C1.BAT`) in `/tmp/testdisk`.
Use the same tool with other files to load any program later: `make-loader.py DIR NAME...`.

## At the machine (plain DOS prompt for 1 and 3, CNC90 for 2)

1. Hole closed, `A:LOAD`: copies the programs into `C:\CNC90\MOD1\SORG\SRG\<folder>\`. It checks first and
   never overwrites ("ALREADY EXISTS" instead). Only new files are written to C:.
2. Start `CNC90` and compile every `ZZR*` and `ZZT*` program ("Programma Kompileren"). Note any compiler message
   and whether they all appear in the program list.
3. Back at the DOS prompt: `A:COLLECT`. It copies the generated `TAB`, `NOC`, `SPC` files and `INDICE.PRG` to
   `A:\OUT\`. Reads C:, writes A: only.
4. Then continue with `RUN-SHEET.md` (air runs, timing, real cut).

## On the Mac

Image the diskette (`tools/image-disk.sh`, give it a free ID), then:

    python3 -I tools/compare-compiled.py disks/<ID>/files/OUT

"IDENTICAL" for all twelve pairs means the compiler regenerates exactly. A few differing bytes in `TAB` are
probably a date or name field (the original `Z\EL` TAB holds `08/22/06`); the script prints the offsets.
A different size, or differing bytes in `NOC`/`SPC`, means regeneration is not exact: keep the `COMP` folders
from the hard disk (the PC must then stay until they are copied).
