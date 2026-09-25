# Fusion post-processor for the TPA CNC90 — design

Date: 2026-09-25
Status: approved in chat, awaiting written-spec review

## Goal

Draw and set up machining in Autodesk Fusion (Manufacture workspace) and
get a program the Busellato S.EASY can run, without typing it into the
control by hand. Version 1 covers **contour routing** and **vertical
drilling** on the top face.

## Context: the CNC90 program format

Decoded from 118 real programs (`disks/H02/files/SRG/Z`, `SRG/W`, captured
2026-09-25) and the tool table `disks/H03/files/CNC90/MOD1/USER/TESTINE.PAR`.

- Program sources are **plain text** in a TPA dialect of ISO G-code, one
  file per program, no extension, stored in
  `C:\CNC90\MOD1\SORG\SRG\<first character of name>\<NAME>`.
- Each source has a binary companion in `SORG\TAB\` and compiled forms in
  `MOD1\COMP\NOC\` and `COMP\SPC\`. These are assumed to be produced on
  the machine by editing or compiling ("Programma Kompileren"). The post
  writes only the text source.
- Across 2,860 programs (1992–2008) the largest source is 7,440 bytes
  (~250 lines); 99 % are under 1,114 bytes. The control has never been
  shown to handle long programs.

Example (`SRG/Z/BJOLAN2`):

```
G71X1032Y1082Z18T00N7L4
G150(ZIJ J2 BORNINGEN)A70B45C110
G88G90G54P5T0165F1G41X45Y-30Z21
G1G90F1X45Y55Z21
G3G90G17X110Y55U32.5
G1G90X110Y-30Z21
M2
```

| Code | Meaning (as far as decoded) |
|---|---|
| `G71 X Y Z T00 N L` | Panel length, width, thickness. `N` = total lines in the file, `L` = machining lines (all lines except `G71`, `G150`, `M2`). Verified on BJOLAN2 (7/4), WEVER3 (13/10), INKEL (23/20) |
| `G150(text)` | Program description; optional variables `A…D` (not used by the post) |
| `G81 G90 G54 P5 T01nn X Y Z` | Single vertical hole, tool `nn`, depth `Z` |
| `G88 G90 G54 P5 T01nn [S] F [G41/G42] X Y Z` | Start of a routed contour at X,Y, depth Z |
| `G1 G90 [F] X Y Z` | Straight cut |
| `G2`/`G3 G90 G17 X Y U` | Arc CW/CCW to X,Y with radius `U` |
| `M2` | End of program |
| `G183`–`G186`, `G85`, `G37` | Rows of holes, saw cut, a rounding move — **not used** in version 1 |

Conventions seen in the samples:

- `Z` is **depth below the top of the panel**, positive downwards
  (`Z21` on an 18 mm panel cuts 3 mm into the spoilboard).
- `P5` = top face. `G54` (most programs) or `G55` = reference origin.
- `T01nn` = tool `nn`. `TESTINE.PAR` names include `FREES T 65 D=18.00`,
  `FREES T 66 D=8`, `BLADE X T 60`, `BLADE Y T61`, `HORIZONTAAL BOOR T 53`
  and `T 56`; vertical drills in the samples use `T0101`, `T0106`, `T0110`.
- `F1`, `F0.5`, `F2` suggest feed in m/min. `S18000` = spindle rpm.
- Lines are CRLF, upper case, no spaces except before `Y`/`Z` after a formula.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Output | Text source only, no `TAB` or compiled files | Matches existing programs; `TAB` is binary and probably generated on the machine |
| Arcs | Real `G2`/`G3` with radius; split above 180° | Keeps line count low; the control's point rate is unknown and probably low |
| Fallback | Setting to output straight lines only, with a segment length | Emergency only, if arcs misbehave |
| Cutter compensation | In Fusion ("in computer"); never `G41`/`G42` | The machine follows exactly the path shown in Fusion |
| Moves between contours | Dropped; each contour starts with `G88` | Same as the existing programs; the control handles rapids |
| Scope v1 | Contours + vertical drilling, top face (`P5`), origin `G54` | User's choice |
| Tools | Fusion tool number `nn` → `T01nn` | The user's existing Fusion tool library, renumbered to match the machine |
| Loading onto the machine | Copy a new, uniquely named file into `SORG\SRG\<letter>\` and compile on the machine; in parallel with the hard disk backup | User's choice; only new files and `INDICE.PRG` (backed up on H03) change |

## Output rules

One Fusion setup → one CNC90 source file.

1. **Header:** `G71X<stock X>Y<stock Y>Z<stock Z>T00N<total>L<machining>`,
   dimensions from the Fusion stock, rounded to 0.01 mm. `N` and `L` are
   counted after the program is complete.
2. **Description:** `G150(<comment>)` from the Fusion program comment,
   upper-cased, reduced to printable ASCII, max 30 characters. Empty
   comment → `G150()`.
3. **Drilling:** every hole of a Fusion drilling operation (plain
   drilling cycle) becomes
   `G81G90G54P5T01<nn>X<x>Y<y>Z<depth>`, depth = hole bottom below the top
   of the stock.
4. **Contours:** for each cutting pass, the first feed move after a
   plunge becomes the start line
   `G88G90G54P5T01<nn>[S<rpm>]F<feed>X<x>Y<y>Z<depth>`; the following
   moves are `G1`, `G2`, `G3`. `F` is written only when it changes. A
   retract (move up to or above the top of the stock) ends the contour;
   rapid moves are not written.
5. **Arcs:** `G2`/`G3G90G17X<x>Y<y>U<radius>`. Arcs over 180° are split
   into two equal arcs.
6. **Merging:** consecutive straight moves that are collinear within the
   merge tolerance become one move.
7. **Numbers:** mm, up to 3 decimals, trailing zeros and trailing `.`
   removed (`9.15`, `13`, `0.5`).
8. **End:** `M2`, CRLF line endings, ASCII only.
9. **File name:** the Fusion program name, upper case, 1–8 characters of
   `A–Z 0–9 _ -`, no extension. The first character is the `SRG`
   subfolder on the machine.

## Settings (post properties)

| Setting | Default | Purpose |
|---|---|---|
| Feed unit | m/min | Fusion mm/min ÷ 1000; alternative: mm/min unchanged |
| Origin | `G54` | `G55` selectable |
| Mirror Y | off | Mirror Y about the stock centre and swap `G2`/`G3` |
| Arc output | arcs | `lines` = split arcs into straight segments |
| Segment length | 2 mm | Used only when arc output = lines |
| Merge tolerance | 0.05 mm | Rule 6 |
| Line warning | 250 | Warn when the file has more lines |
| Max depth below stock | 5 mm | Deeper → error |
| Allowed tools | 1–30, 65, 66 | Tool numbers accepted; editable list. 1–30 is a provisional range for the vertical drill spindles until the full spindle map is read from `TESTINE.PAR` or the machine |

## Errors (the post stops, no file written)

- No stock, or the setup origin is not on the top surface of the stock
  (within 0.01 mm).
- Cutter compensation set to "in control", "wear" or "inverse wear".
- An arc that changes Z (helix), or an arc not in the XY plane.
- Any operation other than a 2D contour or plain drilling (e.g. pocket,
  adaptive, tapping, boring cycles, 3D, multi-axis, turning).
- Tool number not in the allowed list.
- Depth deeper than stock thickness + max depth setting.
- A contour whose first cut starts with Z above the stock top (no plunge).
- Program name not valid under rule 9.

## Things confirmed at the machine (test plan)

In order; each step only after the previous one worked. Test names are
checked against `hdd/LISTING.TXT` so no existing program is overwritten.

| # | Test | Confirms |
|---|---|---|
| 1 | Copy `ZZT1` into `SORG\SRG\Z\`, compile, check it appears in the program list | The machine accepts a copied-in text source |
| 2 | Run `ZZT1` in the air (Z well above the panel), hand on the emergency stop | Origin corner, Y direction, arc direction, order of moves |
| 3 | 500 mm straight line at `F1`, timed | Feed unit |
| 4 | Circle as one arc, then 5 / 2 / 1 mm segments, in the air, timed | Usable point rate → line warning setting |
| 5 | Test piece 2 mm deep in scrap, measured | Depth, dimensions, arcs in real cutting |

The test piece: an "L" shape with one arc corner and three holes at known
positions, asymmetric so that any mirroring or wrong origin is visible.

## Testing without the machine

1. **Checker** `tools/check-cnc90.py`: validates a CNC90 source against the
   rules above (known codes only, header counts, positive depths within
   limits, DOS name, CRLF, ASCII). It must accept all 118 programs in
   `disks/H02/files/SRG/` (with the codes the post does not generate
   allowed in "sample mode") before it is used on post output.
2. **Post tests**: Fusion's command-line post engine
   (`…/Autodesk Fusion.app/Contents/Libraries/Applications/CAM360/post`,
   version 5.413.5 on this Mac) runs `post/busellato-cnc90.cps` on fixed
   intermediate (`.cnc`) toolpaths. Each output is compared with a
   reviewed expected file and passed through the checker. Cases: contour
   with lines and arcs, drilling, several depth passes, arc over 180°,
   helix (must fail), wrong origin (must fail).
3. **Test toolpaths** come from Autodesk's sample intermediate files (from
   the Fusion post-processor VS Code extension) and from one Fusion
   document of the test piece made by David with his tool library. The
   first plan task confirms which source works; at least one of the two
   is required.

## Repository layout

```
post/
  busellato-cnc90.cps     the post-processor
  README.md               installing it in Fusion, settings, workflow
  tests/
    cases/*.cnc           intermediate toolpaths
    expected/*            reviewed outputs
    run-tests.sh          runs the post engine + checker on every case
tools/
  check-cnc90.py          format checker
```

## Out of scope for version 1

Pockets, saw cuts (`G85`), rows of holes (`G183`–`G186`), horizontal
drilling, faces other than the top, `G55` workflows, formula output
(`=l`, `=h`), generating `TAB` or compiled files, transfer over COM2.
