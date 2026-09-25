# Disk capture — design

Date: 2026-09-25
Status: approved in chat, awaiting written-spec review

## Goal

Get every piece of software and data from the Busellato S.EASY's TPA
Compact 90 control into this repo, byte-exact, before any of it is lost.
If the control PC dies, a replacement can be rebuilt from what is here.

This is Part A of the safeguarding work. Part B (photo documentation of
the current state in Proton Drive) gets its own design later.

## Context

- The control is an Olivetti-based PC running MS-DOS 5.0 (Italian),
  booting from an internal hard disk (C:) into CNC90 v3.0 "for Super
  Easy".
- It has one 3.5" floppy drive, a working COM2 port, and a dead printer
  port.
- Seven original 3.5" HD (1.44 MB) diskettes exist. Their labels (as read
  from a photo, to be confirmed with each disk in hand):

  | ID | Label | Files on label |
  |---|---|---|
  | D01 | CNC 90 — 1 | 28 |
  | D02 | CNC 90 — 2 | 11 |
  | D03 | CNC 90 — 3 | 7 |
  | D04 | PTPSYS | 4 |
  | D05 | PTP0 (top line possibly "CASCHR 20772") | 39 |
  | D06 | PTP1000 | 40 |
  | D07 | LINGUE — 1/1 | 75 |

- The diskettes look like installation media. The machine-specific
  state (parameters, tool tables, programs) most likely lives only on C:.
  So C: is the priority. The diskettes are imaged as well, because
  they are the only copy of the installation software.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Reading diskettes | USB floppy drive on the Mac | No other hardware needed |
| Imaging tool | `ddrescue` | Reads a weak disk once, retries only bad sectors, logs which sectors failed |
| File extraction | `mtools` (`mcopy`) from the image | Does not mount the disk, so macOS can't write to it; keeps DOS timestamps |
| Hard-disk backup | `XCOPY` on the machine onto blank diskettes, which are then imaged like the originals | No hardware, cabinet stays closed, only reads from C: |
| Exact hard-disk image | Not now | Possible later over COM2; pulling the drive is ruled out unless it is already failing |
| Storage | Plain git, no LFS | ~30 disks × 1.44 MB ≈ 45 MB |
| Blank diskette formatting | On the Mac | `FORMAT` is never typed on the machine |

## Repository layout

```
disks/
  README.md          index, one row per diskette
  .gitattributes     "* -text": git must never touch line endings
  D01/ … D07/        original diskettes
  H01/ … Hnn/        diskettes written from C:
    <ID>.img           raw sector image, byte-exact
    <ID>.map           ddrescue map
    label-front.jpg    label photo (label-back.jpg if written on)
    files/             files extracted from the image
hdd/
  CHKDSK.TXT         size, free space, errors on C:
  LISTING.TXT        output of DIR C:\ /S
  ATTRIB.TXT         output of ATTRIB C:\*.* /S (reveals hidden files)
  files/             C: rebuilt from H-disks, in the original folder layout
tools/
  image-disk.sh      images one diskette end to end
  verify-hdd.sh      checks hdd/files/ against LISTING.TXT
```

`D` = original diskette, `H` = diskette written from the hard disk.

Files are stored byte-exact: no CP437/CP850 → UTF-8 conversion, no
line-ending changes. Any readable conversion goes next to the original,
never in its place.

### Index (`disks/README.md`)

One row per disk:

| Column | Content |
|---|---|
| ID | D01, H03, … |
| Label | Handwritten text, verbatim |
| Imaged | Date |
| SHA-256 | Of `<ID>.img` |
| Bad sectors | Count from the map; 0 if clean |
| Files expected / found | Expected from the label (D-disks) or the copy plan (H-disks) |
| Contents | One line |

## Procedure

### Step 0 — Mac setup (once)

- `brew install ddrescue mtools`
- Write `tools/image-disk.sh`.

### Step 1 — Original diskettes (Mac only)

For each of D01–D07:

1. Set the write-protect tab to locked **before** the disk enters any
   drive.
2. Photograph the label (front, and back if written on).
3. Run `tools/image-disk.sh <ID>`. The script:
   1. finds the USB floppy device and unmounts it without ejecting;
   2. runs `ddrescue -d -n` (fast pass, no retries), then
      `ddrescue -d -r3` (retry bad sectors up to 3 times);
   3. writes `<ID>.img` and `<ID>.map`, and prints the SHA-256;
   4. extracts all files with `mcopy -s -m` into `files/`;
   5. prints the extracted file count and the number of bad sectors.
4. Fill in the index row, compare the file count with the label, and
   commit the disk.

If a disk has bad sectors: keep the partial image and map, record the
count, and do not retry in a loop. A second USB floppy drive may read
what the first can't.

### Step 2 — Hard disk, first visit (listing)

1. On the Mac, format a blank HD diskette as FAT12 1.44 MB and label it
   H01.
2. At the machine, get to the DOS prompt. How to exit CNC90 to DOS is
   still unknown and must be found out first.
3. With H01 in the drive:
   ```
   CHKDSK C: > A:\CHKDSK.TXT
   DIR C:\ /S > A:\LISTING.TXT
   ATTRIB C:\*.* /S > A:\ATTRIB.TXT
   COPY C:\CONFIG.SYS A:\
   COPY C:\AUTOEXEC.BAT A:\
   ```
4. At the Mac, image H01 with `tools/image-disk.sh H01`, and copy the
   three `.TXT` files into `hdd/`.

### Step 3 — Copy plan (Mac)

From `LISTING.TXT`, write a command sheet that lists:

- every H-disk (H02 onward) with the exact `XCOPY` lines for it, keeping
  each disk under 1.44 MB;
- the number of blank diskettes needed;
- any file larger than 1.44 MB (`XCOPY` can't span disks), which needs
  a separate method;
- any hidden or system files from `ATTRIB.TXT` (`XCOPY` skips them),
  other than the DOS system files.

### Step 4 — Hard disk, second visit (copy)

1. Follow the command sheet line by line:
   `XCOPY C:\<folder> A:\<folder> /S /E /V`, one disk at a time.
2. At the Mac, image each H-disk with `tools/image-disk.sh`.
3. Rebuild the folder layout of C: in `hdd/files/`.
4. Run `tools/verify-hdd.sh`.

### Rules at the machine

These go at the top of every command sheet:

- Never type `FORMAT`, `DEL`, `CHKDSK /F`, or any command with `C:` as
  its destination.
- Don't restart the machine with a diskette in the drive.
- If anything unexpected shows up on screen, stop and take a photo.

## Verification

- Per disk: extracted file count equals the expected count, bad sectors
  are 0 (or recorded), SHA-256 is in the index.
- Hard disk: `tools/verify-hdd.sh` confirms that every file in
  `LISTING.TXT` exists in `hdd/files/` with the same size, and lists
  any that don't.

## Out of scope

- An exact, sector-level image of C:.
- Converting DOS text files to a readable form.
- Transcribing parameters from screens (`axis-parameters.md`).
- Part B: photo documentation in Proton Drive.

## Related changes

- README "Where things live": replace Google Drive with Proton Drive as
  the home for photos, video, scans and vendor PDFs.
- Add a `.gitignore` for `.DS_Store`.
