# Machine checklist: hard disk copy

Real diskettes in the PC's own drive (the Gotek does not work yet: DOS gets "sector not found").
One batch = one diskette, label `H<nn>` as in the table. Nothing is written to C:.
`/V` is left out of the XCOPY lines on purpose (it doubles the time); the Mac check after each
batch (clean ddrescue read, counts against `LISTING.TXT`) replaces it.

**Rules:** never type `FORMAT`, `DEL`, `CHKDSK /F`, a command with `C:` as destination, or `SALVAINC`.
If XCOPY asks "F = file, D = directory", answer **D**. Photograph anything unexpected.
Do the irreplaceable batches first (2 to 8). Batches 9 to 19 (compiled output, DOS) can be regenerated.
Drive letter is `A:`. Run from the plain DOS prompt (CNC90: "exit system"), not the DOS shell.

**Per batch**
1. Mac: format a blank diskette: `diskutil unmountDisk /dev/diskN && sudo newfs_msdos -F 12 -f 1440 -v H<nn> /dev/rdiskN`.
   Find `diskN` with `diskutil list external physical` every time. Never reuse a number from an old note.
2. Mac: copy the batch file onto it: `cp hdd/batches/H<nn>.BAT /Volumes/H<nn>/COPY.BAT`
   (regenerate with `python3 -I tools/make-batches.py` if `COPY-PLAN.md` changes).
3. Machine: write-protect hole closed, plain DOS prompt, type `A:COPY`. It shows the label, waits for a key,
   runs the XCOPY lines below, then `DIR A: /S`. Compare the file count (batch files + 1 for COPY.BAT).
   If it does not run, type the XCOPY lines by hand.
4. Mac: hole open, `tools/image-disk.sh H<nn> "batch <n>" <files + 1>`. It must report 0 bad sectors and a matching count.

Tick each box when done.

| Batch | Label | Files | Priority | Copied on machine | Imaged on Mac (0 bad sectors) | Notes |
|---|---|---|---|---|---|---|
| 1 | H03 | 93 | done | [x] | [x] | captured 2026-09-25 |
| 2 | H04 | 81 | irreplaceable | [x] | [x] | imaged 2026-10-23, 81/81 match LISTING.TXT (name, size); extra 0-byte file `H04` in root, unexplained |
| 3 | H05 | 793 | irreplaceable | [ ] | [ ] | diskette prepared 2026-10-23 (physical D17 erased, image kept); `COPY.BAT` on it |
| 4 | H06 | 1302 | irreplaceable | [ ] | [ ] | diskette prepared 2026-10-23 (reused H04 after imaging); `COPY.BAT` on it |
| 5 | H07 | 1147 | irreplaceable | [ ] | [ ] |  |
| 6 | H08 | 1132 | irreplaceable | [ ] | [ ] |  |
| 7 | H09 | 1014 | irreplaceable | [ ] | [ ] |  |
| 8 | H10 | 786 | irreplaceable | [ ] | [ ] |  |
| 9 | H11 | 1058 | regenerable | [ ] | [ ] |  |
| 10 | H12 | 1011 | regenerable | [ ] | [ ] |  |
| 11 | H13 | 786 | regenerable | [ ] | [ ] |  |
| 12 | H14 | 1058 | regenerable | [ ] | [ ] |  |
| 13 | H15 | 1011 | regenerable | [ ] | [ ] |  |
| 14 | H16 | 436 | regenerable | [ ] | [ ] |  |
| 15 | H17 | 8 | regenerable | [ ] | [ ] |  |
| 16 | H18 | 13 | regenerable | [ ] | [ ] |  |
| 17 | H19 | 26 | regenerable | [ ] | [ ] |  |
| 18 | H20 | 39 | regenerable | [ ] | [ ] |  |
| 19 | H21 | 47 | regenerable | [ ] | [ ] |  |

## Batch 1 → H03  (93 files, ~1147 KB)

```
XCOPY C:\CNC90\MOD1\USER\*.* A:\CNC90\MOD1\USER\
```

## Batch 2 → H04  (81 files, ~1242 KB)

```
XCOPY C:\PTP0\*.* A:\PTP0\
XCOPY C:\PTPSYS\*.* A:\PTPSYS\
XCOPY C:\PTP1000\*.* A:\PTP1000\
```

## Batch 3 → H05  (793 files, ~1328 KB)

```
XCOPY C:\CNC90\LINGUE\*.* A:\CNC90\LINGUE\
XCOPY C:\CNC90\MOD1\SORG\*.* A:\CNC90\MOD1\SORG\
XCOPY C:\CNC90\MOD1\SORG\SRG\00\*.* A:\CNC90\MOD1\SORG\SRG\00\
XCOPY C:\CNC90\MOD1\SORG\SRG\7\*.* A:\CNC90\MOD1\SORG\SRG\7\
XCOPY C:\CNC90\MOD1\SORG\SRG\9\*.* A:\CNC90\MOD1\SORG\SRG\9\
XCOPY C:\CNC90\MOD1\SORG\SRG\A\*.* A:\CNC90\MOD1\SORG\SRG\A\
XCOPY C:\CNC90\MOD1\SORG\SRG\B\*.* A:\CNC90\MOD1\SORG\SRG\B\
XCOPY C:\CNC90\MOD1\SORG\SRG\C\*.* A:\CNC90\MOD1\SORG\SRG\C\
XCOPY C:\CNC90\MOD1\SORG\SRG\D\*.* A:\CNC90\MOD1\SORG\SRG\D\
```

## Batch 4 → H06  (1302 files, ~1195 KB)

```
XCOPY C:\CNC90\MOD1\SORG\SRG\E\*.* A:\CNC90\MOD1\SORG\SRG\E\
XCOPY C:\CNC90\MOD1\SORG\SRG\F\*.* A:\CNC90\MOD1\SORG\SRG\F\
XCOPY C:\CNC90\MOD1\SORG\SRG\G\*.* A:\CNC90\MOD1\SORG\SRG\G\
XCOPY C:\CNC90\MOD1\SORG\SRG\H\*.* A:\CNC90\MOD1\SORG\SRG\H\
XCOPY C:\CNC90\MOD1\SORG\SRG\I\*.* A:\CNC90\MOD1\SORG\SRG\I\
XCOPY C:\CNC90\MOD1\SORG\SRG\J\*.* A:\CNC90\MOD1\SORG\SRG\J\
XCOPY C:\CNC90\MOD1\SORG\SRG\K\*.* A:\CNC90\MOD1\SORG\SRG\K\
XCOPY C:\CNC90\MOD1\SORG\SRG\L\*.* A:\CNC90\MOD1\SORG\SRG\L\
XCOPY C:\CNC90\MOD1\SORG\SRG\M\*.* A:\CNC90\MOD1\SORG\SRG\M\
XCOPY C:\CNC90\MOD1\SORG\SRG\N\*.* A:\CNC90\MOD1\SORG\SRG\N\
XCOPY C:\CNC90\MOD1\SORG\SRG\O\*.* A:\CNC90\MOD1\SORG\SRG\O\
XCOPY C:\CNC90\MOD1\SORG\SRG\P\*.* A:\CNC90\MOD1\SORG\SRG\P\
```

## Batch 5 → H07  (1147 files, ~1309 KB)

```
XCOPY C:\CNC90\MOD1\SORG\SRG\R\*.* A:\CNC90\MOD1\SORG\SRG\R\
XCOPY C:\CNC90\MOD1\SORG\SRG\S\*.* A:\CNC90\MOD1\SORG\SRG\S\
XCOPY C:\CNC90\MOD1\SORG\SRG\T\*.* A:\CNC90\MOD1\SORG\SRG\T\
XCOPY C:\CNC90\MOD1\SORG\SRG\V\*.* A:\CNC90\MOD1\SORG\SRG\V\
XCOPY C:\CNC90\MOD1\SORG\SRG\W\*.* A:\CNC90\MOD1\SORG\SRG\W\
XCOPY C:\CNC90\MOD1\SORG\SRG\X\*.* A:\CNC90\MOD1\SORG\SRG\X\
XCOPY C:\CNC90\MOD1\SORG\SRG\Y\*.* A:\CNC90\MOD1\SORG\SRG\Y\
XCOPY C:\CNC90\MOD1\SORG\SRG\Z\*.* A:\CNC90\MOD1\SORG\SRG\Z\
XCOPY C:\CNC90\MOD1\SORG\TAB\00\*.* A:\CNC90\MOD1\SORG\TAB\00\
XCOPY C:\CNC90\MOD1\SORG\TAB\7\*.* A:\CNC90\MOD1\SORG\TAB\7\
XCOPY C:\CNC90\MOD1\SORG\TAB\9\*.* A:\CNC90\MOD1\SORG\TAB\9\
XCOPY C:\CNC90\MOD1\SORG\TAB\A\*.* A:\CNC90\MOD1\SORG\TAB\A\
XCOPY C:\CNC90\MOD1\SORG\TAB\B\*.* A:\CNC90\MOD1\SORG\TAB\B\
```

## Batch 6 → H08  (1132 files, ~1172 KB)

```
XCOPY C:\CNC90\MOD1\SORG\TAB\C\*.* A:\CNC90\MOD1\SORG\TAB\C\
XCOPY C:\CNC90\MOD1\SORG\TAB\D\*.* A:\CNC90\MOD1\SORG\TAB\D\
XCOPY C:\CNC90\MOD1\SORG\TAB\E\*.* A:\CNC90\MOD1\SORG\TAB\E\
XCOPY C:\CNC90\MOD1\SORG\TAB\F\*.* A:\CNC90\MOD1\SORG\TAB\F\
XCOPY C:\CNC90\MOD1\SORG\TAB\G\*.* A:\CNC90\MOD1\SORG\TAB\G\
XCOPY C:\CNC90\MOD1\SORG\TAB\H\*.* A:\CNC90\MOD1\SORG\TAB\H\
XCOPY C:\CNC90\MOD1\SORG\TAB\I\*.* A:\CNC90\MOD1\SORG\TAB\I\
XCOPY C:\CNC90\MOD1\SORG\TAB\J\*.* A:\CNC90\MOD1\SORG\TAB\J\
XCOPY C:\CNC90\MOD1\SORG\TAB\K\*.* A:\CNC90\MOD1\SORG\TAB\K\
```

## Batch 7 → H09  (1014 files, ~1102 KB)

```
XCOPY C:\CNC90\MOD1\SORG\TAB\L\*.* A:\CNC90\MOD1\SORG\TAB\L\
XCOPY C:\CNC90\MOD1\SORG\TAB\M\*.* A:\CNC90\MOD1\SORG\TAB\M\
XCOPY C:\CNC90\MOD1\SORG\TAB\N\*.* A:\CNC90\MOD1\SORG\TAB\N\
XCOPY C:\CNC90\MOD1\SORG\TAB\O\*.* A:\CNC90\MOD1\SORG\TAB\O\
XCOPY C:\CNC90\MOD1\SORG\TAB\P\*.* A:\CNC90\MOD1\SORG\TAB\P\
XCOPY C:\CNC90\MOD1\SORG\TAB\R\*.* A:\CNC90\MOD1\SORG\TAB\R\
XCOPY C:\CNC90\MOD1\SORG\TAB\S\*.* A:\CNC90\MOD1\SORG\TAB\S\
XCOPY C:\CNC90\MOD1\SORG\TAB\T\*.* A:\CNC90\MOD1\SORG\TAB\T\
```

## Batch 8 → H10  (786 files, ~1116 KB)

```
XCOPY C:\CNC90\MOD1\SORG\TAB\V\*.* A:\CNC90\MOD1\SORG\TAB\V\
XCOPY C:\CNC90\MOD1\SORG\TAB\W\*.* A:\CNC90\MOD1\SORG\TAB\W\
XCOPY C:\CNC90\MOD1\SORG\TAB\X\*.* A:\CNC90\MOD1\SORG\TAB\X\
XCOPY C:\CNC90\MOD1\SORG\TAB\Y\*.* A:\CNC90\MOD1\SORG\TAB\Y\
XCOPY C:\CNC90\MOD1\SORG\TAB\Z\*.* A:\CNC90\MOD1\SORG\TAB\Z\
XCOPY C:\CNC90\MOD1\COMP\NOC\00\*.* A:\CNC90\MOD1\COMP\NOC\00\
XCOPY C:\CNC90\MOD1\COMP\NOC\7\*.* A:\CNC90\MOD1\COMP\NOC\7\
XCOPY C:\CNC90\MOD1\COMP\NOC\9\*.* A:\CNC90\MOD1\COMP\NOC\9\
XCOPY C:\CNC90\MOD1\COMP\NOC\A\*.* A:\CNC90\MOD1\COMP\NOC\A\
XCOPY C:\CNC90\MOD1\COMP\NOC\B\*.* A:\CNC90\MOD1\COMP\NOC\B\
XCOPY C:\CNC90\MOD1\COMP\NOC\C\*.* A:\CNC90\MOD1\COMP\NOC\C\
```

## Batch 9 → H11  (1058 files, ~1303 KB)

```
XCOPY C:\CNC90\MOD1\COMP\NOC\D\*.* A:\CNC90\MOD1\COMP\NOC\D\
XCOPY C:\CNC90\MOD1\COMP\NOC\E\*.* A:\CNC90\MOD1\COMP\NOC\E\
XCOPY C:\CNC90\MOD1\COMP\NOC\F\*.* A:\CNC90\MOD1\COMP\NOC\F\
XCOPY C:\CNC90\MOD1\COMP\NOC\G\*.* A:\CNC90\MOD1\COMP\NOC\G\
XCOPY C:\CNC90\MOD1\COMP\NOC\H\*.* A:\CNC90\MOD1\COMP\NOC\H\
XCOPY C:\CNC90\MOD1\COMP\NOC\I\*.* A:\CNC90\MOD1\COMP\NOC\I\
XCOPY C:\CNC90\MOD1\COMP\NOC\J\*.* A:\CNC90\MOD1\COMP\NOC\J\
XCOPY C:\CNC90\MOD1\COMP\NOC\K\*.* A:\CNC90\MOD1\COMP\NOC\K\
```

## Batch 10 → H12  (1011 files, ~1298 KB)

```
XCOPY C:\CNC90\MOD1\COMP\NOC\L\*.* A:\CNC90\MOD1\COMP\NOC\L\
XCOPY C:\CNC90\MOD1\COMP\NOC\M\*.* A:\CNC90\MOD1\COMP\NOC\M\
XCOPY C:\CNC90\MOD1\COMP\NOC\N\*.* A:\CNC90\MOD1\COMP\NOC\N\
XCOPY C:\CNC90\MOD1\COMP\NOC\O\*.* A:\CNC90\MOD1\COMP\NOC\O\
XCOPY C:\CNC90\MOD1\COMP\NOC\P\*.* A:\CNC90\MOD1\COMP\NOC\P\
XCOPY C:\CNC90\MOD1\COMP\NOC\R\*.* A:\CNC90\MOD1\COMP\NOC\R\
XCOPY C:\CNC90\MOD1\COMP\NOC\S\*.* A:\CNC90\MOD1\COMP\NOC\S\
XCOPY C:\CNC90\MOD1\COMP\NOC\T\*.* A:\CNC90\MOD1\COMP\NOC\T\
```

## Batch 11 → H13  (786 files, ~1192 KB)

```
XCOPY C:\CNC90\MOD1\COMP\NOC\V\*.* A:\CNC90\MOD1\COMP\NOC\V\
XCOPY C:\CNC90\MOD1\COMP\NOC\W\*.* A:\CNC90\MOD1\COMP\NOC\W\
XCOPY C:\CNC90\MOD1\COMP\NOC\X\*.* A:\CNC90\MOD1\COMP\NOC\X\
XCOPY C:\CNC90\MOD1\COMP\NOC\Y\*.* A:\CNC90\MOD1\COMP\NOC\Y\
XCOPY C:\CNC90\MOD1\COMP\NOC\Z\*.* A:\CNC90\MOD1\COMP\NOC\Z\
XCOPY C:\CNC90\MOD1\COMP\SPC\00\*.* A:\CNC90\MOD1\COMP\SPC\00\
XCOPY C:\CNC90\MOD1\COMP\SPC\7\*.* A:\CNC90\MOD1\COMP\SPC\7\
XCOPY C:\CNC90\MOD1\COMP\SPC\9\*.* A:\CNC90\MOD1\COMP\SPC\9\
XCOPY C:\CNC90\MOD1\COMP\SPC\A\*.* A:\CNC90\MOD1\COMP\SPC\A\
XCOPY C:\CNC90\MOD1\COMP\SPC\B\*.* A:\CNC90\MOD1\COMP\SPC\B\
XCOPY C:\CNC90\MOD1\COMP\SPC\C\*.* A:\CNC90\MOD1\COMP\SPC\C\
```

## Batch 12 → H14  (1058 files, ~1303 KB)

```
XCOPY C:\CNC90\MOD1\COMP\SPC\D\*.* A:\CNC90\MOD1\COMP\SPC\D\
XCOPY C:\CNC90\MOD1\COMP\SPC\E\*.* A:\CNC90\MOD1\COMP\SPC\E\
XCOPY C:\CNC90\MOD1\COMP\SPC\F\*.* A:\CNC90\MOD1\COMP\SPC\F\
XCOPY C:\CNC90\MOD1\COMP\SPC\G\*.* A:\CNC90\MOD1\COMP\SPC\G\
XCOPY C:\CNC90\MOD1\COMP\SPC\H\*.* A:\CNC90\MOD1\COMP\SPC\H\
XCOPY C:\CNC90\MOD1\COMP\SPC\I\*.* A:\CNC90\MOD1\COMP\SPC\I\
XCOPY C:\CNC90\MOD1\COMP\SPC\J\*.* A:\CNC90\MOD1\COMP\SPC\J\
XCOPY C:\CNC90\MOD1\COMP\SPC\K\*.* A:\CNC90\MOD1\COMP\SPC\K\
```

## Batch 13 → H15  (1011 files, ~1298 KB)

```
XCOPY C:\CNC90\MOD1\COMP\SPC\L\*.* A:\CNC90\MOD1\COMP\SPC\L\
XCOPY C:\CNC90\MOD1\COMP\SPC\M\*.* A:\CNC90\MOD1\COMP\SPC\M\
XCOPY C:\CNC90\MOD1\COMP\SPC\N\*.* A:\CNC90\MOD1\COMP\SPC\N\
XCOPY C:\CNC90\MOD1\COMP\SPC\O\*.* A:\CNC90\MOD1\COMP\SPC\O\
XCOPY C:\CNC90\MOD1\COMP\SPC\P\*.* A:\CNC90\MOD1\COMP\SPC\P\
XCOPY C:\CNC90\MOD1\COMP\SPC\R\*.* A:\CNC90\MOD1\COMP\SPC\R\
XCOPY C:\CNC90\MOD1\COMP\SPC\S\*.* A:\CNC90\MOD1\COMP\SPC\S\
XCOPY C:\CNC90\MOD1\COMP\SPC\T\*.* A:\CNC90\MOD1\COMP\SPC\T\
```

## Batch 14 → H16  (436 files, ~1231 KB)

```
XCOPY C:\CNC90\MOD1\COMP\SPC\V\*.* A:\CNC90\MOD1\COMP\SPC\V\
XCOPY C:\CNC90\MOD1\COMP\SPC\W\*.* A:\CNC90\MOD1\COMP\SPC\W\
XCOPY C:\CNC90\MOD1\COMP\SPC\X\*.* A:\CNC90\MOD1\COMP\SPC\X\
XCOPY C:\CNC90\MOD1\COMP\SPC\Y\*.* A:\CNC90\MOD1\COMP\SPC\Y\
XCOPY C:\CNC90\MOD1\COMP\SPC\Z\*.* A:\CNC90\MOD1\COMP\SPC\Z\
XCOPY C:\CNC90\MOD1\TEMPOR\*.* A:\CNC90\MOD1\TEMPOR\
XCOPY C:\CNC90\F*.* A:\CNC90\
XCOPY C:\CNC90\W*.* A:\CNC90\
XCOPY C:\CNC90\D*.* A:\CNC90\
XCOPY C:\CNC90\I*.* A:\CNC90\
XCOPY C:\CNC90\S*.* A:\CNC90\
XCOPY C:\CNC90\B*.* A:\CNC90\
XCOPY C:\CNC90\C*.* A:\CNC90\
```

## Batch 15 → H17  (8 files, ~1467 KB)

```
XCOPY C:\CNC90\E*.* A:\CNC90\
```

## Batch 16 → H18  (13 files, ~763 KB)

```
XCOPY C:\CNC90\M*.* A:\CNC90\
XCOPY C:\CNC90\T*.* A:\CNC90\
XCOPY C:\CNC90\L*.* A:\CNC90\
XCOPY C:\CNC90\P*.* A:\CNC90\
XCOPY C:\CNC90\V*.* A:\CNC90\
XCOPY C:\CNC90\G*.* A:\CNC90\
XCOPY C:\CNC90\A*.* A:\CNC90\
```

## Batch 17 → H19  (26 files, ~1113 KB)

```
XCOPY C:\CHECKIT\*.* A:\CHECKIT\
XCOPY C:\DOS5\C*.* A:\DOS5\
XCOPY C:\DOS5\E*.* A:\DOS5\
XCOPY C:\DOS5\F*.* A:\DOS5\
XCOPY C:\DOS5\K*.* A:\DOS5\
```

## Batch 18 → H20  (39 files, ~1190 KB)

```
XCOPY C:\DOS5\N*.* A:\DOS5\
XCOPY C:\DOS5\D*.* A:\DOS5\
XCOPY C:\DOS5\H*.* A:\DOS5\
XCOPY C:\DOS5\M*.* A:\DOS5\
XCOPY C:\DOS5\S*.* A:\DOS5\
```

## Batch 19 → H21  (47 files, ~1226 KB)

```
XCOPY C:\DOS5\A*.* A:\DOS5\
XCOPY C:\DOS5\R*.* A:\DOS5\
XCOPY C:\DOS5\U*.* A:\DOS5\
XCOPY C:\DOS5\X*.* A:\DOS5\
XCOPY C:\DOS5\P*.* A:\DOS5\
XCOPY C:\DOS5\Q*.* A:\DOS5\
XCOPY C:\DOS5\G*.* A:\DOS5\
XCOPY C:\DOS5\4*.* A:\DOS5\
XCOPY C:\DOS5\5*.* A:\DOS5\
XCOPY C:\DOS5\B*.* A:\DOS5\
XCOPY C:\DOS5\L*.* A:\DOS5\
XCOPY C:\DOS5\J*.* A:\DOS5\
XCOPY C:\DOS5\T*.* A:\DOS5\
XCOPY C:\DOS5\Z*.* A:\DOS5\
XCOPY C:\*.* A:\ROOT\
```

## Gotek (USB floppy emulator): status 2026-10-23

Not working yet. Do not rely on it. Findings so far:
- Stick `GOTEK` (FAT32): `DSKA0000.IMG` = old ZZTEST, `DSKA0001` to `DSKA0019` = blank FAT12 images labelled H03 to H21.
  `FF.CFG` on the stick: `interface = ibmpc`.
- Board `SFRKC30AT3`, no display and no buttons (footprints empty), so the slot cannot be chosen; jumper cap on S1, JC open.
- PC: BIOS drive A: = 1.4M, B: = none. `dir a:` with the Gotek gives "Settore non trovato"; the boot sector is read at power-up.
- The PC's own drive reads a known-good diskette (D13) fine, so the PC side works.
- Untried: a jumper cap on JC; Gotek on the middle cable connector as B: (needs BIOS "Diskette 2" = 1.4M);
  checking which firmware is on it (no display, so only by reflashing with FlashFloppy).

## Other notes
- Diskette device numbers change between sessions: always check `diskutil list external physical`.
- Do not format an unknown diskette: an MBR + FAT16 layout on a 1.44 MB disk means an original CNC90 diskette.
  Image it and compare with `disks/` first (D17 was reused as H05 only after checking it was byte-identical to its capture).
