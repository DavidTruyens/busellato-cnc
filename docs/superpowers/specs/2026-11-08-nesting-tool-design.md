# Panel nesting and program generator — design

Date: 2026-11-08
Status: approved; implemented on branch nesting-tool (plan 2026-11-08-nesting-tool.md); revised
2026-11-09 (see "Revision 2026-11-09"); not yet run on the machine

## Revision 2026-11-09 (the physical model was corrected by the user)

The first version assumed the whole 1220 × 2440 panel lies on the scrap plate and that a
"template" is cut loose around each group of shapes. That is wrong:

- The machine's Y travel is limited, so a whole panel cannot be machined at once. A **panel
  saw** first cuts each panel into rectangular **blanks**, each holding a group of shapes
  (default 2) and fitting the machine's **work frame** (long side along machine X).
- One blank at a time lies on the scrap plate on the vacuum cups, screwed down through **4
  fixing holes** in its margin. Each shape's own holes get a **screw hole** drilled through the
  blank into the scrap, so the shape stays fixed. Then the shape outlines are cut out of the
  blank; the blank's leftover frame is **never cut** (there is no template outline cut).
- The stack on the cups is scrap + blank; the stock Z is scrap + panel thickness, shape cuts go
  through the blank and a little into the scrap (what the old template mode `none` did).
- Work frame settings `machine.frame_x` 3072 and `machine.frame_y` 787 mm are **unverified
  placeholders** decoded from a control config file, to verify on the machine's axis parameter
  screens. A group whose blank does not fit is split, down to one shape; a shape that does not fit
  alone is an error naming it.
- Nesting is a **panel-saw guillotine plan**: stage 1 cuts make strips across the panel, stage 2
  cuts free the blanks from a strip, a stage 3 cut trims a blank narrower than its strip; kerf
  (default 4 mm) between every two pieces, edge trim at the borders, blanks may turn 90° on the
  panel. Both strip directions are tried (fewest panels, then least waste inside the strips). The
  run sheet prints the ordered cut list per panel.
- Programs are **per blank**, in blank coordinates: `B<nn>D` (drill), `B<nn>C` (cut) (more
  digits past 99 blanks; until 2026-11-13 the drills were split into `B<nn>F` / `B<nn>S`, see
  below). Settings `template.*` became `blank.*`; template stock, into-template, template
  mode and fixed template size were removed.

- **Program coordinates (added 2026-11-13, the user's statement, NOT yet verified on the
  machine).** The user, who runs the machine: "This looks like the Y axis goes + to the back. The
  origin should be the top left." So a blank's programs use: X0 Y0 = the blank's back-left corner
  (top left of the picture, operator at the bottom, against the pins), X to the right, **Y toward
  the front**. Setting `machine.y_toward` `front` (default) / `back` (the earlier behaviour, Y up
  from the front-left corner); project files without it load as `front`. The layout stays y-up
  internally; `program.py` maps it (Y = blank height - y) for drill positions and contours (the
  cutter offset is made before the mirror, so it stays outward). The direction setting
  (`ccw` default) is the sense seen from above in the picture; under the mirrored Y it is written
  as the opposite sense in the numbers (G2 for the default, where it was G3). Whether the machine
  reads G2/G3 that way with Y toward the front is **not verified: check with an air cut first**,
  together with where X0 Y0 really is. The Drill job / Cut job views draw the program numbers
  with Y down; the panel Layout view (saw plan) is unchanged.

- **One drill program per blank (merged by the user's decision, 2026-11-13).** The user, who
  runs the machine: the fixing holes and the screw holes can always go into one drill program,
  even with different tools. Evidence: of the 717 programs under
  `disks/H05/files/CNC90/MOD1/SORG/SRG/*`, 203 name more than one tool (`T01nn`), and 63 have
  `G81` lines with different tools in one program (for example `A/ERTS140`: `T0104` and `T0101`
  drills); every block carries its own tool. The "one program per tool" rule came from the Fusion
  post, not from the machine. So per blank: `B<nn>D` holds the 4 fixing holes and every screw
  hole, each `G81` line with its own tool and depth; ops are grouped by tool (fixing tool first,
  stable, so fixing holes come before screw holes when both use one tool); `B<nn>C` is the cut,
  single tool. `Program.tool` of a drill program is the tool of its first op, `Program.tools`
  lists all. The settings are unchanged (`drill_fix` / `drill_screw` each keep tool, diameter,
  feed, depth); diameter and feed are still not written, the run sheet lists them per tool.
  Sequence per blank: clamp, run `B<nn>D` (all holes), screw the blank down through the fixing
  holes and each shape through its screw holes, take the clamps off, run `B<nn>C`, unscrew.
  **Whether the machine runs these particular drill tools mixed in one program is unverified.**

Statements below that this revision changes are marked *(revised 2026-11-09)*.

## Goal

Cut many flat 2D parts (first use: 50+ MDF classroom plates, 18 mm, 1.0–2.1 m long) on the
Busellato S.EASY / TPA CNC90 without drawing a CAM setup per part. The user drops in DXF
outlines. The tool groups parts into **blanks**, plans how a panel saw cuts the blanks from
1220 × 2440 stock panels *(revised 2026-11-09; was: templates nested on panels)*, and **writes the
programs** the machine runs, so the person at the
shop (Yureck) can change heights, tools, feeds and depths on his own laptop and regenerate in
seconds.

Why: the machine has no easy way to set an origin (it was built for panel processing), the router
diameters, depths and feeds are not known yet, and every program has to travel on a diskette. A
Fusion round trip for each tweak is too slow. The tool replaces it for this kind of work.

## What exists (build on it)

- `fusion/export_plates.py` — runs in Fusion; writes `plates/<name>.dxf` (layer `CONTOUR` = outline
  as lines and arcs, layer `HOLES` = circles, mm, lower-left of the outline at 0,0) and
  `plates/plates.json` (name, thickness, bounding box, hole centres and diameters). Verified closed
  outlines and bounding boxes against Fusion for the 12 current plates.
- `tools/nest_plates.py` + `tests/test_nest_plates.py` and their output `nest/nest.json` (pairing by
  length, template with 4 fixing holes and one screw hole under each part hole, MaxRects nesting
  with 90° turns) were the starting point. They have been replaced by the `nesting` package
  (`nesting/layout.py` and `tests/test_nesting_layout.py`, started with `python -m nesting`; see
  `nesting/README.md`) and are no longer in the repo.
- `post/busellato-cnc90.cps` and `docs/superpowers/specs/2026-09-25-fusion-post-design.md` — the
  CNC90 source format: header `G71X<stock X>Y<stock Y>Z<stock Z>…`, `G81` single holes, `G88`
  contour start, `G1`, `G2`/`G3` arcs with radius `U`, `P5` = top face, `G54`/`G55`, `F` in
  m/min, arcs kept as arcs, compensation computed by the program (never `G41`/`G42`), one program
  per tool (a Fusion post rule, not the machine's: the machine's own programs mix tools, see the
  2026-11-13 note in the Revision).
- `tools/check_cnc90.py` — format checker used on 118 real machine programs; reuse it on the
  generated output.
- `tools/make-loader.py`, `tools/make-import-disk.py` — put programs on a diskette the machine can
  load. Machine facts (2026-10-30, user's reports, not independently verified): a program copied
  to the control is not in the compiler list until registered in file management; each new
  program must be opened and saved once in the editor before compiling; the largest known source
  is about 250 lines; 2 mm line segments ran slow and shaky, arcs ran well.

## Decisions (the user's, unless marked)

1. **Browser app, run locally.** A small Python program serves a local page; works on Windows and
   Mac with no install beyond Python (a single Windows `.exe` is a later nicety). The UI is
   `docs/nesting-tool/mockup.html` — keep its layout: shapes on the left, panel preview in the
   centre with Layout / Drill job / Cut job views, settings on the right, program list under the
   panel.
2. **Generic input.** Any 2D shape as a DXF with an outline and optional circles. The 12 Fusion
   plates are only the first data set. *(revised 2026-11-09: no template modes; the blank is
   built automatically per group.)*
3. **Blank per group, sawn from the panels** *(revised 2026-11-09)*. The blank is the bounding box
   of the group plus a margin, rotation of shapes is not used (bounding box is enough). Blanks
   must fit the machine work frame and are laid out on panels in a panel-saw guillotine plan,
   90° turns allowed.
4. **Two kinds of fixing.** 4 fixing holes per blank (in its margin, outside the shapes) screw
   the blank to a scrap plate on the vacuum cups. Each shape's own holes (2 on the plates) get a
   screw hole through the blank into the scrap, so the shape is screwed down before it is cut
   free. Everything stays fixed when the outlines are cut.
5. **Two programs per blank: drill, then cut** *(revised 2026-11-13; was one per tool, and
   before 2026-11-09 per panel)*: one drill program with every hole (fixing and screw, each `G81`
   line with its own tool), then the cut. The operator screws the blank and the parts down between
   the drill and the cut programs. Only shape outlines are cut; the blank's frame is never cut.
6. **Settings live in the tool, not on the machine.** The user does not know whether the control
   can take parameters, so the model is: change a value on the laptop, regenerate, copy to
   diskette, register, open-and-save, compile. (Your call to revisit if parameters turn out to
   exist.) All settings are saved in one project file (`PROJECT.json`) next to the output.
7. **Output goes through a backend interface.** First backend: CNC90 source on a diskette folder
   (+ loader batch file + printable run sheet). Later backend: LinuxCNC G-code, where no diskette
   is needed. Blanks, the saw plan and the preview must not depend on the backend.
8. **Format knowledge is shared, not copied.** A Python emitter writes the CNC90 format. It is
   tested against the existing post-processor output (machine test programs ZZT*, same geometry,
   same lines) so the two cannot drift apart. (My call.)

## Settings the user changes (all with placeholder defaults)

- Heights, in mm: scrap plate under the blank, panel (blank) thickness, how far the shape cut and
  the fixing holes go into the scrap *(revised 2026-11-09)*.
- Router: tool (T65 Ø18 left, T66 Ø8 right — the "Busellato S.EASY" library), feed (m/min), depth
  per pass, gap between shapes.
- Drills: fixing-hole diameter, screw-hole diameter, depth, feed.
- Blank: shapes per blank, group by (similar length, list order), margins, hole inset.
- Panel: size 1220 × 2440, thickness, saw trim per edge, saw kerf. Machine: work frame X × Y
  (placeholders) *(revised 2026-11-09)*.
- Per shape: quantity, on/off.

## Z (the point that needs care)

In the CNC90 source the stock height is in the header (`G71…Z<stock Z>`) and moves are depths
below the top of the stock (`P5`, top face). My reading, **not verified on the machine**: for this
job the stock Z is the whole stack on the cups (scrap + blank; *revised 2026-11-09*, was scrap +
template stock + shape), and depths are counted from the top of the blank. The mockup shows absolute Z values for readability; the real
output follows the post-processor's convention. The one number the operator must be able to change
fast is therefore the stack height. The machine-test notes say the tip height is within about 1 mm
of "stock − depth" in air for T65, and T66 sat about 3 mm lower than T65 (tool length not checked).
The tool must show the numbers it will write before writing.

## Constraints

- Nothing generated has run on the machine yet. Every output is "format-checked and simulated",
  not "tested"; the first run is air, then scrap, then real parts, with the user watching.
- Program size and speed: keep arcs as arcs, do not segment; warn above about 250 lines per
  program (the existing post setting) and refuse nothing silently.
- Program names are 1–8 characters `A-Z 0-9 _ -`; the first character is the folder on the machine
  (`SRG\<first>\<rest>`). Scheme `B<blank><D|C>` (`B01D`, `B01C`) *(revised
  2026-11-13; was `B<blank><F|S|C>`, before 2026-11-09 `N<panel><F|S|C>`)*.
- The control's date and the diskette workflow are the user's; the tool writes a folder and a
  batch file and never formats or overwrites a diskette.
- Fusion Personal limits do not apply (this tool does not use Fusion CAM), but the Fusion
  export script stays the source of DXFs for parts drawn in Fusion.

## Non-goals

- A general CAM system: no 3D, no pockets, no toolpath optimisation beyond cut order.
- Rotating shapes to save material (bounding box is enough, user's decision).
- Running or monitoring the machine; the LinuxCNC operator panel is separate work.
- Editing the programs on the machine's own control.

## Anti-goals (would make it a failure even if it "works")

- A program that cuts the wrong place because the preview and the output disagree: the preview
  must be drawn from the same numbers the emitter writes.
- Silent overwrites of an existing program on the machine or of a project file.
- Fixing holes or screw heads in the path of the cutter without a warning.
- Claiming machine behaviour that has not been seen at the machine.

## Left to the builder

- Project layout of the code (suggested: `tools/` package or `nesting/`, local `http.server` plus
  one HTML file, no heavy dependencies), how the DXF reader is written (the repo has no `ezdxf`;
  a small reader for LINE, ARC, CIRCLE, LWPOLYLINE is enough), packing details of the guillotine
  plan, how groups are split when a blank does not fit, the run sheet layout.
- The visual details of the page beyond the mockup.

## Open items (need the machine or the user)

1. Router diameters in use, real feeds, depths per pass, drill sizes — placeholders until measured.
2. Whether the Z convention above is right (stack in the header, depth from the top of the shapes).
3. Which of the machine's two origins (left/right) maps to `G54` and `G55`, and the pin positions
   (not needed by the programs, which are written in panel coordinates).
4. Whether fixing and screw holes use the same drill (one program) or two (two programs).
5. Confirm the cut defaults in "Calls made in review" below.
6. Whether panels have a minimum size for staying on the vacuum, and whether the scrap plate is
   re-used or re-surfaced.
7. Machine work frame: `machine.frame_x` / `frame_y` (3072 × 787) are placeholders from a control
   config file; verify them on the machine's axis parameter screens. Also check where X0 Y0 of a
   blank program lands: the back-left corner against the pins with Y toward the front
   (`machine.y_toward` `front`, the user's statement 2026-11-13) is assumed, and with it the
   G2/G3 sense of the arcs. Air cut first.
8. Panel saw kerf (default 4 mm) and trim (10 mm) are guesses; set them to the real saw.

## Testing

- Unit tests: DXF reading, grouping, blank geometry and clearance, guillotine plan validity,
  rotation transform, program emitter against the post-processor's known output, name rules.
- `tools/check_cnc90.py` on every generated program.
- The preview and the emitter read the same model; a test compares the hole and contour
  coordinates in both.
- Hardware: only after the above, with the air → scrap → real sequence from the machine run sheet.

## Calls made in review (mine; change any of them)

- **Shape cut:** the cutter path is the outline offset **outward** by the tool radius, computed by
  the program (no `G41`/`G42`). It cuts through the blank and a little into the scrap (default
  0.5 mm, a setting) *(revised 2026-11-09; was into the template, with a template outline cut
  last)*, with no skin and no tabs: the screws hold the part until it is cut free. Lead-in is a
  plain straight approach from outside the outline; refine later.
- **Z:** one function maps "depth below the top of the stack" to the numbers written; the stack
  height goes in the header. If the convention turns out wrong it is a change to that function and
  the setting, not to the emitter. The same reference serves drills and shape cuts.
- **Drills:** one program per distinct drill diameter. Equal diameters merge into one program.
- **Program size:** only a warning above about 250 lines, no splitting. With 9 mm passes the cut
  program of a 2-shape blank is about 125 lines (per blank since 2026-11-09); the line count is
  shown and depth per pass is the lever.
- **Cut direction:** a setting, default counter-clockwise; climb or conventional depends on the
  spindle direction, which is not recorded here, so check it at the machine.
- **Emitter tests:** reference programs are the ZZT machine tests and the post-processor's
  regenerated output where they cover `G88` contours, arcs with `U`, and `G81` holes. Anything they
  do not cover gets a new reference file reviewed by the user before it is trusted.
- **Whole panel on the scrap:** superseded 2026-11-09: one blank at a time, see the Revision.

## Physical set-up (confirmed by the user, 2026-11-08; corrected 2026-11-09)

- *(Superseded 2026-11-09.)* ~~The whole 1220 × 2440 panel, with all its templates, lies on one
  scrap plate on the vacuum cups for the entire job.~~ A panel saw cuts the panel into blanks;
  one blank at a time lies on the scrap plate on the vacuum cups. The shapes are cut out of the
  blank and stay screwed down until the operator removes them; the blank's frame is not cut.
- The scrap plate is aligned by the machine's **X and Y alignment pins**. The blank goes on top,
  loose or with a clamp, until the holes are drilled; then the screws go in and the clamps come
  off. The 4 fixing holes per blank are screwed into the scrap; each shape is screwed to the
  scrap through a screw hole drilled at each of its holes *(revised 2026-11-09)*.
- *(Superseded 2026-11-09: shapes are not placed separately; they are part of the blank.)* The
  run sheet prints each panel's saw cut list and each blank with its shapes and holes.
- The machine only knows its **two machine origins (left and right)** and the **top of the cups**.
  Everything else is an offset: the thickness of the scrap plate is a **Z offset** (the "scrap plate"
  height setting), and the panel's position comes from the pins, not from a measured origin. My
  reading, to be checked with the post's `G54`/`G55` setting: left origin = `G54`, right origin =
  `G55`; the tool has an "origin: left / right" setting, default as the post's default.
