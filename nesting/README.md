# Nesting tool

A local tool (Python 3.11, standard library only) that takes part outlines (DXF), groups them
into rectangular **blanks**, plans how a **panel saw** cuts those blanks from 1220 x 2440 panels,
and writes, per blank, one CNC90 drill program and one cut program for the Busellato S.EASY. Design:
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
python -m nesting [PROJECT_DIR] [--port N] [--seed-plates]
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

It prints the project folder and the URL (`http://127.0.0.1:8765/`). Open it in a browser, add
shapes, set quantities and settings, check the preview (it shows the same numbers that are
written), then Generate. Each Generate writes a new folder `out/<YYYYMMDD-HHMMSS>/`; an existing
folder is never overwritten and a failed run leaves nothing behind.

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

The tool numbers 1 and 2 for the drills are placeholders: set the real tool numbers.
Quantities are capped at 500 per shape.

A shape that does not fit a blank on its own (work frame, trimmed panel, or a clearance rule)
is an error that names it: nothing is planned or generated until it is fixed.

The shapes' own holes are not made at their drawn diameter: only a screw hole
(`drill_screw.diameter`) is drilled at each hole centre, so the shape stays screwed down while it
is cut free.

Settings saved by the earlier template version are read with `template.*` as `blank.*` and
`heights.shape_thickness` as `panel.thickness`; the template-only settings are dropped.

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

Per blank `Bnn`, the programs are `BnnD` (drill: the 4 fixing holes and every screw hole) and
`BnnC` (cut the shape outlines). `BnnD` holds both hole kinds even when they use different tools:
every `G81` line names its own tool (`T01nn`), as in many of the machine's own programs (on the H05
backup 203 of the 717 programs name more than one tool, 63 of them in `G81` drill lines). The holes are grouped by tool, in
the order fixing tool, screw tool, so the tool changes only once; with one tool it is a single
group, fixing holes first. Whether the machine changes between these particular drill tools
inside one program has not been tried. The first character `B` is the machine folder
(`SRG\B\nnD`). The number has 2 digits, or more when there are more than 99 blanks (all names
then get the same width, for example `B100C`). Every blank gets its own programs, even when two
blanks have the same shapes in the same layout (sharing them is possible but not done).

1. Copy the generated folder's contents to the diskette. In the control, run `A:LOAD`; it copies
   each program to its folder without overwriting.
2. Register each program in file management, open it in the editor and save it once, then
   compile.
3. Saw each panel into blanks as the run sheet's cut list says (`RUNSHEET.html`: per panel the
   cut list and which blank is which, then a page per blank).
4. Lay a blank on the scrap against the pins and clamp it; run the drill program (`BnnD`): all
   holes, the blank still clamped.
5. Screw the blank to the scrap through the fixing holes, and each shape down through its screw
   holes; take the clamps off.
6. Run the cut (`BnnC`): it cuts the shapes out of the blank; the blank's frame is not cut.
7. Unscrew the shapes and the frame; next blank.

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
