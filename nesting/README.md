# Nesting tool

A local tool (Python 3.11, standard library only) that takes part outlines (DXF), nests them on
panels, optionally builds a template around groups of parts, and writes one CNC90 program per
tool for the Busellato S.EASY. Design: `docs/superpowers/specs/2026-11-08-nesting-tool-design.md`.

**Nothing this tool writes has been run on the machine.** The programs are format-checked,
not run on the machine: the emitter reproduces the machine test programs ZZT1, ZZT1AD and ZZT2A
byte for byte (those files are in `post/machine-tests/`, written by the Fusion post-processor),
and generated programs pass `tools/check_cnc90.py`. See "Safety" before the first run.

## Start it

```
python3 -m nesting [PROJECT_DIR] [--port N] [--seed-plates]
```

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
| | edge 10 | Unusable border; nothing is placed there. |
| heights | scrap 18 | Thickness of the scrap plate under the panel. |
| | template_stock 18 | Thickness of the template material (0 is used when template mode is `none`). |
| | shape_thickness 18 | Default thickness of a shape (a shape can carry its own). |
| | into_template 0.3 | How far a shape cut goes below the shape into the template. |
| | into_scrap 0.5 | How far the template outline (or a shape cut without template) goes into the scrap. |
| | fix_into_scrap 1 | How far the fixing holes go into the scrap. |
| router | tool 66, diameter 8 | Cutter tool number and diameter; the contour is offset outward by half the diameter. |
| | spindle_rpm 18000, plunge_feed 1, cut_feed 3 | Spindle speed and feeds. |
| | depth_per_pass 9 | Maximum cut per pass. Passes are counted over the material (shape contours: shape thickness + `into_template`; template outlines: template stock + `into_scrap`) and are equal steps. |
| | clearance 4 | Extra space between neighbours; the gap between shapes is diameter + clearance. |
| | direction ccw | Cutting direction of the contours (`ccw` or `cw`, default counter-clockwise). Whether that is climb or conventional milling depends on the spindle direction, which is not recorded anywhere in this repo: check it at the machine before cutting real parts. |
| drill_fix | tool 1, diameter 6, feed 1 | The 4 fixing holes per template, screwed into the scrap. |
| drill_screw | tool 2, diameter 3, depth 8, feed 1 | Screw holes drilled through each shape's own holes into the template. |
| template | mode auto | `auto` builds a template per group, `fixed` uses `fixed_width` x `fixed_height`, `none` cuts shapes straight on the scrap, with no template and no fixing holes. |
| | shapes_per 2, group_by length | How many shapes share a template, and how they are grouped (`length` or `order`). |
| | margin_end 45, margin_side 45 | Template margin around the group. |
| | fix_inset 15, head_dia 14 | Fixing hole inset from the template edge, and screw head diameter. Clearance checks: a fixing hole must be at least router diameter + `head_dia`/2 + 3 from every shape (the cutter edge runs a full diameter outside the shape), and `fix_inset` at least `head_dia`/2 + 3 (the head stays inside the template). A failure is reported as a plan problem. |
| origin | G54 | Which origin the programs use, `G54` or `G55`. The post-processor's default is G54. Left = G54 / right = G55 is an assumption: which machine origin each one maps to has not been confirmed on the machine. Check which origin the machine uses before the first run. |

The tool numbers 1 and 2 for the drills are placeholders: set the real tool numbers.
Quantities are capped at 500 per shape.

## Z convention

Depths are measured **below the top of the stack**. The stack is scrap + template stock + the
thickest shape on that panel, and its height is what the program header carries as the stock Z.
That makes the scrap thickness one number to change: edit `heights.scrap`, regenerate, and every
depth follows. This reading of the CNC90 convention is not verified on the machine.

## At the machine

The whole panel with all its templates lies on one scrap plate on the vacuum cups for the entire
job, aligned by the machine's X and Y pins. Templates and shapes are cut loose as the last step.

Per panel `n`, the programs are `N<n>F` (fixing holes), `N<n>S` (screw holes) and `N<n>C` (cuts);
`N<n>S` is not written when fixing and screw holes use the same tool and diameter, and then
`N<n>F` carries both.

1. Copy the generated folder's contents to the diskette. In the control, run `A:LOAD`; it copies
   each program to its folder without overwriting.
2. Register each program in file management, open it in the editor and save it once, then
   compile.
3. Run the fixing holes (`N<n>F`).
4. Screw the panel down onto the scrap through the fixing holes; take the clamps off.
5. Place the shapes on their templates (the run sheet `RUNSHEET.html` draws each panel with
   every shape's position).
6. Run the screw-hole drill (`N<n>S`).
7. Screw each shape to its template.
8. Run the cut (`N<n>C`): shape outlines first, template outlines last.

## Safety

Nothing generated has run on the machine. The first run is in air, with the user watching, then
on scrap, then on real parts. Check the heights and tool numbers against the machine before each
step; every default is a placeholder.

## Add a backend

A backend is a function `(Program, Settings) -> str` registered in `BACKENDS`
(`nesting/backends/__init__.py`), next to `BACKENDS['cnc90']`. Nesting, templates and the preview
only produce `Program` objects (`nesting/program.py`); the backend turns them into the machine's
source text. `write_output` takes the backend name; today the diskette loader it builds is
CNC90-specific.

## Tests

From the repo root (`tests` is not a package):

```
python3 -m unittest discover -s tests
```

One file: `python3 -m unittest discover -s tests -p 'test_nesting_server.py'`.
