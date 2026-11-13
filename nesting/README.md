# Nesting tool

A local tool (Python 3.11, standard library only) that takes part outlines (DXF), groups them
into rectangular **blanks**, plans how a **panel saw** cuts those blanks from 1220 x 2440 panels,
and writes, per blank, one CNC90 drill program, one cut program and, when the shapes have pockets,
one pocket program for the Busellato S.EASY. Design:
`docs/superpowers/specs/2026-11-08-nesting-tool-design.md` (see its "Revision 2026-11-09").

The machine's work frame is smaller than a panel, so a whole panel is never machined at once.
The panel saw cuts each panel into blanks; one blank at a time is screwed to the scrap plate on
the vacuum cups, the shapes are cut out of it, and the blank's leftover frame is never cut.

**Nothing this tool writes has been run on the machine.** The programs are format-checked,
not run on the machine: the emitter reproduces the machine test programs ZZT1, ZZT1AD and ZZT2A
byte for byte (those files are in `post/machine-tests/`, written by the Fusion post-processor),
and generated programs pass `tools/check_cnc90.py`. See "Safety" before the first run.

## Start it

```
python -m nesting [PROJECT_DIR] [--port N] [--seed-plates] [--open]
```

Run it from the busellato-cnc folder (the repo folder that holds `nesting/` and `plates/`).
On Windows, python.org installs `python` and `py`: use `python -m nesting` or `py -m nesting`,
not `python3` (on Windows that opens the Microsoft Store). On macOS or Linux, where `python` may
be missing, use `python3` in its place.

- `PROJECT_DIR` defaults to `./nesting-project` and is created if missing. It holds `shapes/*.dxf`
  (the parts), `project.json` (quantities, on/off flags, settings) and `out/` (generated jobs).
- `--port N` defaults to 8765. The server listens on 127.0.0.1 only.
- `--seed-plates` copies the 12 `plates/*.dxf` into the project's `shapes/`, but only when `shapes/`
  is empty; otherwise it copies nothing and says so.
- `--open` opens the page in the default browser once the server listens.

It prints the project folder and the URL (`http://127.0.0.1:8765/`). Open it in a browser, add
shapes, set quantities and settings, check the preview (it shows the same numbers that are
written), then Generate. Each Generate writes a new folder `out/<YYYYMMDD-HHMMSS>/`; an existing
folder is never overwritten and a failed run leaves nothing behind.

## Windows

`WINDOWS.md` (repo root) is the step-by-step for a Windows PC: `start.bat` updates from GitHub,
starts the tool on port 8800 with project `%USERPROFILE%\nesting-project` and opens the page;
`copy-to-diskette.bat` writes the newest job's `DISKETTE` folder to the diskette
(`python -m nesting.diskette [JOB_OR_PROJECT] [A:] [--keep]`: removable drives only, nothing
larger than a diskette, asks `YES` before erasing, reads every file back). Not tested on Windows.

Every job folder has a `DISKETTE` folder holding exactly what goes on the diskette: the loader
(`LOAD.BAT`, `L1.BAT`, `COLLECT.BAT`, `C1.BAT`) and the programs flat in its root, and
`SORG\INDICE.PRG` plus `SORG\SRG\<first char>\<rest of name>`, the import format CNC90 file
management writes itself (for Programma Kopie, which registers the programs;
`nesting/importdisk.py`). Generate warns when it would not fit a 1.44 MB diskette.

## Settings

All numbers are **placeholders**, not measured values. Change them in the page and regenerate.
Lengths in mm, feeds in m/min (as the machine's programs use them), spindle speed in rpm.

| Group | Setting (default) | Meaning |
|---|---|---|
| panel | length 2440, width 1220 | Panel size. |
| | thickness 18 | Panel thickness; the blanks and so the shapes have this thickness. |
| | edge 10 | Saw trim at every panel border; nothing is placed there. Must be 0 (no trim) or at least the kerf. |
| | kerf 4 | Panel saw blade width; there is one kerf between every two pieces. |
| machine | frame_x 3072, frame_y 787 | Work frame a blank must fit in, long side along machine X. **Placeholders** decoded from a control config file, not measured: to verify on the machine's axis parameter screens. |
| | y_toward front | Which way program Y grows (see "Program coordinates"). `front`: X0 Y0 is the blank's back-left corner (top left of the drawing), Y grows toward the front of the machine. `back`: X0 Y0 is the front-left corner (bottom left of the drawing), Y grows toward the back (the behaviour before 2026-11-13). Project files without it load as `front`. **Not verified on the machine.** |
| heights | scrap 18 | Thickness of the scrap plate on the cups, under the blank. |
| | into_scrap 0.5 | How far a shape cut goes below the blank into the scrap. |
| | fix_into_scrap 1 | How far the fixing holes go into the scrap. |
| router | tool 66, diameter 8 | Cutter tool number and diameter; the contour is offset outward by half the diameter. |
| | spindle_rpm 18000, plunge_feed 1, cut_feed 3 | Spindle speed and feeds. |
| | depth_per_pass 9 | Maximum cut per pass. Passes are counted over the material (panel thickness + `into_scrap`) and are equal steps. |
| | clearance 4 | Extra space between neighbours; the gap between shapes is diameter + clearance. |
| | direction ccw | Cutting direction of the contours (`ccw` or `cw`, default counter-clockwise), as seen from above in the drawing with the operator at the bottom, whatever `machine.y_toward` is. With Y toward the front that sense is clockwise in the program's numbers, so the corner arcs come out as G2 (they were G3 with Y toward the back). Whether that is climb or conventional milling depends on the spindle direction, which is not recorded anywhere in this repo: check it at the machine before cutting real parts. |
| drill_fix | tool 1, diameter 6, feed 1 | The 4 fixing holes per blank, in its margin, through the blank into the scrap. `feed`: not written to the program (the control uses the tool's own feed). `diameter`: not written to the program (the tool number picks the drill); listed per tool on the run sheet. |
| drill_screw | tool 2, diameter 3, depth 8, feed 1 | Screw holes at each shape's own holes, through the blank; `depth` is how far below the blank, into the scrap. `feed`: not written to the program (the control uses the tool's own feed). `diameter`: not written to the program (the tool number picks the drill); listed per tool on the run sheet. Fixing and screw holes always go into the same drill program (`BnnD`), also with different tools. |
| blank | shapes_per 2, group_by length | How many shapes share a blank, and how they are grouped (`length` or `order`). A group whose blank does not fit the work frame or the panel is split, down to one shape; a blank never takes more shapes than `shapes_per`. |
| | margin_end 45, margin_side 45 | Blank margin around the group. The blank size is rounded up to whole mm (the extra goes to the far margins). |
| | fix_inset 15, head_dia 14 | Fixing hole inset from the blank edge, and screw head diameter. Clearance checks: a fixing hole must be at least router diameter + `head_dia`/2 + 3 from every shape (the cutter edge runs a full diameter outside the shape), and `fix_inset` at least `head_dia`/2 + 3 (the head stays inside the blank). |
| origin | G54 | Which origin the programs use, `G54` or `G55`. The post-processor's default is G54. Left = G54 / right = G55 is an assumption: which machine origin each one maps to has not been confirmed on the machine. Check which origin the machine uses before the first run. |

The pocket settings (`pockets.*`) are in the "Pockets" section below.

The tool numbers 1 and 2 for the drills are placeholders: set the real tool numbers.
Quantities are capped at 500 per shape.

A shape that does not fit a blank on its own (work frame, trimmed panel, or a clearance rule)
is an error that names it: nothing is planned or generated until it is fixed.

The shapes' own holes are not made at their drawn diameter: only a screw hole
(`drill_screw.diameter`) is drilled at each hole centre, so the shape stays screwed down while it
is cut free.

Settings saved by the earlier template version are read with `template.*` as `blank.*` and
`heights.shape_thickness` as `panel.thickness`; the template-only settings are dropped.

## Pockets

A pocket is a recess cut part-way into a shape from its top face (first case: the long slot for
the curtain rail in the curtain planks). **Pocket programs are format-checked and simulated only:
nothing here has run on the machine. Tool, diameter, depth, feeds, spindle speed and direction
are placeholders; the first run is an air cut.**

**Detection** (`nesting/dxf.py`, no tags needed). The outline is layer `CONTOUR`. Inside it:

- a closed loop of lines and arcs on layer `POCKET` is a pocket; when the file has a `POCKET`
  layer only those loops count (a `POCKET` loop that is open, crosses or lies outside the outline
  is an error);
- with no `POCKET` layer, any other closed inner loop (a layer other than `CONTOUR`) is a pocket;
  one that crosses the outline is an error;
- a circle is a pocket when its diameter is **greater** than `pockets.min_circle_diameter`
  (default 8 mm); at or under it, it stays a hole (screw hole). A circle on layer `POCKET` is a
  pocket whatever its size. The page lists such a circle as a pocket: raise the minimum above its
  diameter to make it a hole.

Reading a DXF again after `pockets.min_circle_diameter` changes happens by itself.

**Groups.** Pockets of the same shape at the same position in the plate's own frame (every
coordinate within 0.05 mm, same segment kinds and turning sense; mirrored or moved pockets are a
different group) share a group, a colour and an id `G1`, `G2`, ... Ids and colours are numbered
over all shapes of the project (also those switched off) in first-seen order over the shapes
sorted by name, so they do not depend on the order of the list. The palette has 15 colours,
distinct from the page's blank, shape, hole and saw colours; the 12 plates have 10 groups; beyond 15
groups the colours repeat. Each group has its settings in
the page; they are stored in `project.json` under `pockets`, **keyed by the group key** (a text
made from the pocket's position and vertices, not by `G<n>`). A field is kept when a value is
typed in the group's row, even one equal to the default; an empty field uses the default in
`settings.pockets`. A group can be switched off (not cut, shown dimmed and dashed). Stored
settings whose key matches no current group (a DXF edit or a rename changed the key) stay in
`project.json` but are not used; the plan lists how many with one warning line.

| Setting (default) | Meaning |
|---|---|
| `min_circle_diameter` 8 | Circles above this Ø are pockets. |
| `min_floor` 2 | Material that must stay under a pocket: depth may not exceed panel thickness minus this (hard error). |
| `tool` 66, `diameter` 8 | Pocket cutter number and diameter. One tool number has one diameter: the router, both drills and every switched-on pocket group with a pocket on the plan must agree, or saving and planning stop with an error naming the tool and both diameters. |
| `depth` 8, `depth_per_pass` 4 | Depth from the top face of the blank, in equal passes. |
| `plunge_feed` 1, `cut_feed` 3, `spindle_rpm` 18000 | m/min, m/min, rpm. |
| `stepover_pct` 40 | Maximum stepover between rings, % of the tool diameter, from 10 to 100; **capped at 70** when used. |
| `direction` cw | Turning sense of the rings seen from above (`cw` or `ccw`). Climb or conventional is not verified: depends on the spindle direction, check at the machine. |

The page's group rows offer `enabled`, `tool`, `diameter`, `depth`, `depth_per_pass`,
`plunge_feed`, `cut_feed` and `stepover_pct`; the spindle speed and the direction come from the
defaults. `project.json` (and the API) also accepts `spindle_rpm` and `direction` per group. The
server checks the values and names the group and field that is wrong.

**How a pocket is cut** (`nesting/pockets.py`, `pocket_rings`). The tool path is the tool
centre; arcs stay arcs; no G41/G42; entry is a plunge at the start of each ring.

- A pocket exactly as wide as the tool (within 0.01 mm): one pass along the centre line, out and
  back.
- Wider: closed rings from the inside out, the wall ring (the outline offset inward by the tool
  radius) **last**. The stepover is a maximum, capped at 70 % of the tool diameter (a larger
  stepover would leave material at sharp corners). For every depth pass all the group's pockets
  of the blank are cut, each ring after the other. A ring whose arcs would have a radius under
  0.001 mm (written as `U0`) is cut as a straight line instead (the middle of a slot just wider
  than a whole number of stepovers); the CNC90 writer refuses any arc it would write as `U0`.
- Convex pockets (slots, rectangles, circles) are cleared by construction. A pocket that is not
  convex is checked over its whole interior and **refused with an error** that names the blank,
  shape and group when material would be left standing; clearing general concave pockets is out
  of scope. Sharp convex corners are left rounded by the cutter, as always.
- A pocket narrower than the tool, or with a part (finger, neck) narrower than it, is an error,
  as is one about as wide as the tool that is not a straight slot.
- Depth: measured from the top face (the top of the stack), in equal passes of at most
  `depth_per_pass`. Deeper than thickness minus `min_floor`, or reaching the vacuum cups, is an
  error.

**Program `B<nn>P`.** One per blank that has an enabled pocket. Pockets are ordered by tool (first appearance), within a tool by group, and every operation
names its own tool, spindle speed and feeds (the file header takes the first). Run sequence per
blank: drill `B<nn>D` -> screw the blank and shapes down -> pockets `B<nn>P` -> cut `B<nn>C`.
The programs are in the job's folder and `DISKETTE`; the preview shows `B<nn>P` in its Cut view,
which also draws the pocket cutter path, and the run sheet (a pocket table per blank: group,
colour, size, count, tool, tool diameter, depth, passes). The server remembers pocket rings between plans (a
long pocket takes about half a second to compute).

**Warnings** (a warning, not a stop): a screw or fixing hole whose centre is inside a pocket or
closer than the screw-head clearance (`head_dia`/2 + 3) to its edge; two pockets closer than the
tool diameter; the cutter reaching outside the blank; more than 250 lines in a program.

**Limits.** No through-slots (a pocket never goes through), no islands inside a pocket, no
ramps or helical entry (plunge), no flipping of a plate, no automatic tool choice.

**The page.** The settings have a Pockets section (defaults for every group) and one row per
group below it: colour swatch, number of pockets, on/off and the overrides (an empty field uses
the default). The drawings colour each pocket with its group's colour; the Cut view also draws
the cutter path.

### Fusion export and the bottom face

`fusion/export_plates.py` runs inside Fusion:

```
OUT_DIR = '<repo>/plates'; exec(open('<repo>/fusion/export_plates.py').read())
```

(optionally `FACE = 'top'` before the `exec`). It now exports each plate **from its bottom face**
(`FACE = 'bottom'`, the default): the face whose normal points down, seen from below, is the face
that ends up on top on the machine. The plate is turned over about its vertical axis (x becomes
-x, y stays) and then shifted so the lower-left of the outline is at 0,0; `FACE = 'top'` gives the
old behaviour (face normal up, seen from above, no mirroring). The outline goes on layer
`CONTOUR`, circular inner loops on `HOLES` and every other closed inner loop (a slot) on layer
`POCKET`. The 12 plates in `plates/` were re-exported this way and `plates/plates.json` has, per
plate, `face` and `pocket_loops`. Hole and outline coordinates changed (mirrored) with it. The
script is not run by tests, and the orientation on the machine is confirmed only after a real
plate has been cut.

## Panel saw plan

Each panel is cut in a two-stage guillotine plan: stage 1 cuts go right across the panel and make
strips, stage 2 cuts go across a strip and free the blanks, and a stage 3 cut trims a blank that
is narrower than its strip. There is a kerf between every two pieces and the edge trim at the
panel borders. A blank may lie turned 90 degrees on the panel; its programs are still written in
the blank's own program coordinates. The panel view (Layout) is the saw plan, with the panel's
origin corner bottom left; it is not in machine coordinates. Both strip directions are tried; the plan with the fewest panels wins, then the
one with the least waste inside the strips (kerf and slivers), then strips along the length.

The cut list gives, per cut, its order, stage, direction, position (the near side of the kerf, in
mm from the panel's origin corner), its extent, what it frees and that piece's size. Blanks are
numbered `B01`, `B02`, ... in cut order.

## Z convention

Depths are measured **below the top of the stack**. The stack is scrap + blank (panel thickness),
and its height is what the program header carries as the stock Z.
That makes the scrap thickness one number to change: edit `heights.scrap`, regenerate, and every
depth follows. This reading of the CNC90 convention is not verified on the machine.

## Program coordinates

Every program of a blank is written in one frame, seen from above with the operator at the
bottom of the drawing (the Drill job / Cut job views and the run sheet drawings):

- X0 Y0 is the blank's corner against the pins; X grows to the right along the long side.
- With `machine.y_toward` `front` (default) X0 Y0 is the **back-left** corner (top left of the
  drawing) and **Y grows toward the front** (down in the drawing). The Drill job / Cut job views
  then draw the program numbers as they are, Y down.
- With `back`, X0 Y0 is the front-left corner (bottom left of the drawing) and Y grows toward
  the back; the views draw it with Y up. The drawing itself is the same in both; only the numbers
  and the origin mark change.

`front` is the user's statement (2026-11-13), **not yet verified on the machine**. Mirroring Y
also swaps G2 and G3 for the same physical turn: check where X0 Y0 is and the arc direction with
an air cut before cutting. Inside the code, the layout works y-up from the blank's lower-left
corner; `nesting/program.py` (`to_program`, `segs_to_program`) is the one place that maps it to
the program frame.

## At the machine

The scrap plate lies on the vacuum cups, aligned by the machine's X and Y pins. One blank at a
time goes on top of it, its origin corner (see "Program coordinates") against the pins, long side
along machine X. That the origin sits at the pins is an assumption to check at the machine.

Per blank `Bnn`, the programs are `BnnD` (drill: the 4 fixing holes and every screw hole),
`BnnP` (the pockets; only when the blank's shapes have an enabled pocket) and
`BnnC` (cut the shape outlines). `BnnD` holds both hole kinds even when they use different tools:
every `G81` line names its own tool (`T01nn`), as in many of the machine's own programs (on the H05
backup 203 of the 717 programs name more than one tool, 63 of them in `G81` drill lines). The holes are grouped by tool, in
the order fixing tool, screw tool, so the tool changes only once; with one tool it is a single
group, fixing holes first. Whether the machine changes between these particular drill tools
inside one program has not been tried. The first character `B` is the machine folder
(`SRG\B\nnD`). The number has 2 digits, or more when there are more than 99 blanks (all names
then get the same width, for example `B100C`). Every blank gets its own programs, even when two
blanks have the same shapes in the same layout (sharing them is possible but not done).

1. Write the job's `DISKETTE` folder to the diskette (`copy-to-diskette.bat`, or
   `python -m nesting.diskette JOB TARGET`). In CNC90 file management, Programma Kopie from the
   diskette. If the programs do not appear in the compiler list: in DOS run `A:LOAD` (copies
   each program to its folder without overwriting), then register each program in file
   management, open it in the editor and save it once.
2. Compile.
3. Saw each panel into blanks as the run sheet's cut list says (`RUNSHEET.html`: per panel the
   cut list and which blank is which, then a page per blank).
4. Lay a blank on the scrap against the pins and clamp it; run the drill program (`BnnD`): all
   holes, the blank still clamped.
5. Screw the blank to the scrap through the fixing holes, and each shape down through its screw
   holes; take the clamps off.
6. If the blank has a `BnnP`, run it now: it cuts the pockets into the shapes from the top face,
   while they are still screwed down.
7. Run the cut (`BnnC`): it cuts the shapes out of the blank; the blank's frame is not cut.
8. Unscrew the shapes and the frame; next blank.

## Safety

Nothing generated has run on the machine. The first run is in air, with the user watching, then
on scrap, then on real parts. Check the heights and tool numbers against the machine before each
step; every default is a placeholder.

## Add a backend

A backend is a function `(Program, Settings) -> str` registered in `BACKENDS`
(`nesting/backends/__init__.py`), next to `BACKENDS['cnc90']`. Blanks, the saw plan and the preview
only produce `Program` objects (`nesting/program.py`); the backend turns them into the machine's
source text. `write_output` takes the backend name; today the diskette loader it builds is
CNC90-specific.

## Tests

From the repo root (`tests` is not a package):

```
python -m unittest discover -s tests
```

One file: `python -m unittest discover -s tests -p 'test_nesting_server.py'`.
