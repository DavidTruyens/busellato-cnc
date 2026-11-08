# Panel nesting and program generator — design

Date: 2026-11-08
Status: UI mockup approved in chat (`docs/nesting-tool/mockup.html`); written spec awaiting review

## Goal

Cut many flat 2D parts (first use: 50+ MDF classroom plates, 18 mm, 1.0–2.1 m long) on the
Busellato S.EASY / TPA CNC90 without drawing a CAM setup per part. The user drops in DXF
outlines. The tool builds a **template** for each group of parts, **nests** the templates on
1220 × 2440 stock panels, and **writes the programs** the machine runs, so the person at the
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
- `tools/nest_plates.py` + `tests/test_nest_plates.py` — pairing by length, template with 4 fixing
  holes and one screw hole under each part hole, MaxRects nesting with 90° turns,
  `nest/nest.json`. On the 12 plates: 6 templates on 3 panels. All dimensions are `Config` defaults.
- `post/busellato-cnc90.cps` and `docs/superpowers/specs/2026-09-25-fusion-post-design.md` — the
  CNC90 source format: header `G71X<stock X>Y<stock Y>Z<stock Z>…`, `G81` single holes, `G88`
  contour start, `G1`, `G2`/`G3` arcs with radius `U`, `P5` = top face, `G54`/`G55`, `F` in
  m/min, arcs kept as arcs, compensation computed by the program (never `G41`/`G42`), one program
  per tool.
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
   plates are only the first data set. The tool generates the template too (modes: automatic per
   group, fixed rectangle, none = cut straight from the panel).
3. **Template per group, nested on panels.** The template is the bounding box of the group plus a
   margin, rotation of shapes is not used (bounding box is enough). Templates are nested on
   panels, 90° turns allowed.
4. **Two kinds of fixing.** 4 fixing holes per template (outside the shapes) screw the template
   to a scrap plate on the vacuum cups. Each shape's own holes (2 on the plates) get a screw hole
   in the template, so the shape is screwed down before it is cut loose. Everything stays fixed
   when the outlines are cut.
5. **Several programs per panel, one per tool** (as the machine works): fixing holes, screw
   holes, then the cut. Drill programs split by drill diameter; if two hole kinds use the same drill
   they may be one program. The operator screws parts down between the drill and the cut
   programs. Cut order: shape outlines first, template outlines last.
6. **Settings live in the tool, not on the machine.** The user does not know whether the control
   can take parameters, so the model is: change a value on the laptop, regenerate, copy to
   diskette, register, open-and-save, compile. (Your call to revisit if parameters turn out to
   exist.) All settings are saved in one project file (`PROJECT.json`) next to the output.
7. **Output goes through a backend interface.** First backend: CNC90 source on a diskette folder
   (+ loader batch file + printable run sheet). Later backend: LinuxCNC G-code, where no diskette
   is needed. Nesting, templates and the preview must not depend on the backend.
8. **Format knowledge is shared, not copied.** A Python emitter writes the CNC90 format. It is
   tested against the existing post-processor output (machine test programs ZZT*, same geometry,
   same lines) so the two cannot drift apart. (My call.)

## Settings the user changes (all with placeholder defaults)

- Heights, in mm: scrap plate under the template, template stock, shape thickness, skin left in
  the template when shapes are cut, how far the template cut goes into the scrap.
- Router: tool (T65 Ø18 left, T66 Ø8 right — the "Busellato S.EASY" library), feed (m/min), depth
  per pass, gap between shapes.
- Drills: fixing-hole diameter, screw-hole diameter, depth, feed.
- Template: shapes per template, group by (similar length, list order, manual), margins, hole inset.
- Panel: size 1220 × 2440, unusable edge, gap between templates.
- Per shape: quantity, on/off.

## Z (the point that needs care)

In the CNC90 source the stock height is in the header (`G71…Z<stock Z>`) and moves are depths
below the top of the stock (`P5`, top face). My reading, **not verified on the machine**: for this
job the stock Z is the whole stack on the cups (scrap + template stock + shape), and depths are
counted from the top of the shapes. The mockup shows absolute Z values for readability; the real
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
  (`SRG\<first>\<rest>`). Proposed scheme `N<panel><F|S|C>` (`N1F`, `N1S`, `N1C`) — my call, open
  to change.
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
  a small reader for LINE, ARC, CIRCLE, LWPOLYLINE is enough), packing details beyond
  MaxRects, how templates are split when a group does not fit, the run sheet layout.
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
7. Machine area limits (the table is larger than a panel, but travel limits are not recorded here).

## Testing

- Unit tests: DXF reading, grouping, template geometry and clearance, nesting without overlap,
  rotation transform, program emitter against the post-processor's known output, name rules.
- `tools/check_cnc90.py` on every generated program.
- The preview and the emitter read the same model; a test compares the hole and contour
  coordinates in both.
- Hardware: only after the above, with the air → scrap → real sequence from the machine run sheet.

## Calls made in review (mine; change any of them)

- **Shape cut:** the cutter path is the outline offset **outward** by the tool radius, computed by
  the program (no `G41`/`G42`). It cuts through the shape and a little into the template
  (default 0.3 mm, a setting), with no skin and no tabs: the screws hold the part until it is cut
  free. Template outlines are offset outward too and cut into the scrap by a setting. Lead-in is a
  plain straight approach from outside the outline; refine later.
- **Z:** one function maps "depth below the top of the stack" to the numbers written; the stack
  height goes in the header. If the convention turns out wrong it is a change to that function and
  the setting, not to the emitter. The same reference serves drills, shape cut and template cut.
- **Drills:** one program per distinct drill diameter. Equal diameters merge into one program.
- **Program size:** only a warning above about 250 lines, no splitting. With 9 mm passes the cut
  program of a 4-shape panel is roughly 250 lines (17 per shape pass, 5 per template pass), so it sits at
  the limit; the line count is shown and depth per pass is the lever. Travel limits are unknown:
  warn, never refuse.
- **Cut direction:** a setting, default counter-clockwise; climb or conventional depends on the
  spindle direction, which is not recorded here, so check it at the machine.
- **Emitter tests:** reference programs are the ZZT machine tests and the post-processor's
  regenerated output where they cover `G88` contours, arcs with `U`, and `G81` holes. Anything they
  do not cover gets a new reference file reviewed by the user before it is trusted.
- **Whole panel on the scrap:** confirmed, see "Physical set-up".

## Physical set-up (confirmed by the user, 2026-11-08)

- The whole 1220 × 2440 panel, with all its templates, lies on **one scrap plate** on the vacuum
  cups for the entire job. Templates and shapes are cut loose as the last step and stay screwed
  down until the operator removes them.
- The scrap plate is aligned by the machine's **X and Y alignment pins**. The panel goes on top,
  loose or with a clamp, until the holes are drilled; then the screws go in and the clamps come
  off. The 4 fixing holes per template are screwed into the scrap; each shape is screwed to its
  template through its own holes (drilled through the shape's existing holes).
- The shapes are placed on the panel by the operator and located by their own holes when drilled
  (tolerance about ±1.8 mm: 3 mm screw hole under a 6.6 mm part hole). The run sheet (my call)
  prints each panel with every shape's position so placement needs no measuring.
- The machine only knows its **two machine origins (left and right)** and the **top of the cups**.
  Everything else is an offset: the thickness of the scrap plate is a **Z offset** (the "scrap plate"
  height setting), and the panel's position comes from the pins, not from a measured origin. My
  reading, to be checked with the post's `G54`/`G55` setting: left origin = `G54`, right origin =
  `G55`; the tool has an "origin: left / right" setting, default as the post's default.
