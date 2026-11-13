# Pockets in the nesting tool — design

Date: 2026-11-13
Status: written, builder check done, awaiting the user's approval. Builds on the nesting tool (`nesting/`, PRs #5 and #6).

## Goal

Cut blind pockets (first case: the long slot for the curtain rail in the curtain planks) as part
of the existing flow. The tool finds the pockets in the DXF by itself, shows them in their own
colour, and lets the person at the shop pick a tool, depth, depth per pass and feed for each
group of identical pockets. It writes the pocket program with the other programs of a blank.

Why: the plates now have a feature the outline-and-holes tool cannot make. The shop operator
changes values on a laptop; no Fusion round trip and no hand-written G-code.

## What exists (build on it)

- `nesting/dxf.py` reads a DXF into `Shape(name, outline, holes)`: layer `CONTOUR` = outline,
  circles (layer `HOLES`, or circles inside the outline when there is no such layer) = holes.
  More than one closed loop on `CONTOUR` is an error today.
- `fusion/export_plates.py` runs in Fusion. It takes the face whose normal points up, writes the
  outer loop to `CONTOUR`, circular inner loops to `HOLES`, and counts any other inner loop as
  `ignored_loops` without exporting it. Coordinates are seen from above, lower-left of the outline
  at 0,0. It also writes `plates/plates.json`.
- `nesting/program.py` builds drill and cut programs per blank; the cut contour is the outline
  offset outward by the tool radius, in passes of `depth_per_pass`. `nesting/backends/cnc90.py`
  writes CNC90 source (one contour = a `G88` start, `G1`, `G2`/`G3` moves; arcs stay arcs).
  Program names are `B<nn>D` (drill) and `B<nn>C` (cut). More than 250 lines per program is a
  warning. A depth that reaches the vacuum cups is a hard error.
- The preview, the run sheet, `PROJECT.json` and the page (`nesting/web/index.html`) all read the
  same program model.

## Decisions (the user's, unless marked "my call")

1. **Export from the bottom side.** The slot is on the underside of the plank. The Fusion export
   looks at each plate from its bottom side, so the face with the pocket is the face that ends up
   on top on the machine. The outline is mirrored accordingly (like turning a page over), then the
   lower-left of the outline is put at 0,0. The face used is the planar face with its normal
   pointing down. This is a change to the existing export for all plates (my call: every plate is
   exported this way, so the DXFs are consistent). The 12 DXFs in `plates/` and `plates.json` get
   re-exported.
2. **The export writes every inner loop.** Circles go on `HOLES` as today. Any other closed inner
   loop (made of lines and arcs, like a slot) goes on a new layer `POCKET`. No tags or depths come
   from Fusion.
3. **The tool detects pockets, no tags.** A closed inner loop that is not a circle is a pocket. A
   circle is a pocket only when its diameter is greater than a parameter, default 8 mm
   (`pocket.min_circle_diameter`); a smaller circle stays a hole. Detection also works for DXFs not
   made by the export script: any closed loop inside the outline on a layer other than
   `CONTOUR` is an inner loop (a pocket unless it is a circle at or under the minimum).
4. **Colours and groups.** Pockets with the same shape and size (same loop, same placement rule
   in the plate) share a colour and a group, so settings are made once per group. The preview
   draws pockets in their group's colour, distinct from holes and outlines.
5. **Settings per group.** Tool (number and diameter), cut depth, depth per pass, feed (plunge and
   cut), and stepover. There is a default pocket tool and default values in the settings (all
   placeholders until measured), so the common case needs no clicks. The depth is entered in the
   tool; it does not come from the DXF.
6. **How a pocket is cut (my calls).**
   - Slot or pocket exactly as wide as the tool: one pass along the centre line.
   - Wider: the area is cleared with offset passes from the outside inward, last the
     finishing pass along the outline. The stepover is a setting, default 40% of the tool diameter.
     The tool computes the path; arcs stay arcs; no G41/G42.
   - Narrower than the tool: error, as for narrow shape features today (names the shape and the
     pocket).
   - Depth is measured from the top face of the blank and is cut in passes of the depth per pass.
     A pocket deeper than the blank thickness minus a minimum floor, or that reaches the cups, is a
     hard error. Through-slots are a non-goal for now.
7. **Own program (my call).** The pockets of a blank go in `B<nn>P`, run after the screws are in
   and before the cut `B<nn>C`. This keeps each program under the 250-line warning and allows a
   different tool from the outline router. Several tools inside `B<nn>P` are allowed, as in the
   drill programs.

## Settings the user changes

- Default pocket tool, cutter diameter, depth, depth per pass, plunge and cut feed, stepover.
- Minimum circle diameter that counts as a pocket (default 8 mm).
- Per pocket group: tool, depth, depth per pass, feeds, stepover; each group can override the
  default. A group can be switched off (the pocket is then not cut and shown dimmed).

## Constraints

- Nothing generated has run on the machine. Pocket programs, like all others, are format-checked
  and simulated, not tested; the first run is air, then scrap.
- The preview and the program must stay the same numbers (the existing rule).
- The CNC90 emitter must still reproduce the golden programs byte for byte; pocket moves use only
  the line and arc moves it already writes.
- Preview, run sheet, `PROJECT.json` and README must show the pocket program and its settings.
- The Fusion export script is not run by tests; it is checked by running it in Fusion on the
  current design and reading the DXFs with the tool. Fusion units are cm internally (mm in the
  DXF), as in the current script.

## Non-goals

- Through-cuts of inner loops (through-slots, large through holes). A round hole bigger than the
  minimum diameter is a pocket by the rule above; if it is a through hole it must stay at or under
  the minimum diameter, or be handled in a later change.
- Islands inside pockets, 3D or sloped floors, pocket ramps and helical entries (plunge entry is
  used; refine later).
- Cutting from the top face and the bottom face in one job; flipping a plate.
- Automatic tool selection.

## Anti-goals

- A pocket cut at the wrong place or mirrored because the export and the machine frame disagree.
  The mirroring must be proven with a plate whose features are not symmetric.
- A pocket cut into the screw holes or fixing holes without a warning (the screw hole and the
  pocket must not touch; warn if the pocket path comes closer than the screw-head clearance).
- A depth that silently cuts into the scrap or the cups.

## Left to the builder

- Data model and file layout (a `Pocket` record on `Shape`, a pocket module for the toolpath).
- The offset-clearing algorithm details, the entry move, the order of passes between groups.
- The page layout for the group settings, within the existing look.
- How the "same shape and size" signature is computed (tolerance).

## Calls made in review (mine; change any of them)

- **Where the mirror happens:** in the Fusion export, not in the tool. The DXF always means "seen
  from above, the face that will be on top on the machine". The tool, the layout, the Y-axis
  setting and the emitter are unchanged and know nothing about the bottom side. The turn-over is
  about the plate's vertical axis (x becomes -x, then shifted so the outline's lower-left is 0,0).
  The golden-program tests feed the emitter fixed programs, so they are not affected; the 12 DXFs
  and `plates.json` are re-exported and drill and cut coordinates change with them (mirrored
  holes and outline), which is intended. Proof: a test with an asymmetric plate (reading a mirrored
  DXF gives the mirrored outline and holes) and a check of the re-exported plates against the
  Fusion model.
- **Through holes over the minimum diameter:** the 12 current plates only have 6.6 mm holes, so
  none changes. A circle over the minimum is a pocket with a visible warning in the preview and
  the problem list ("circle of 10 mm is treated as a pocket; raise the minimum above it to make it
  a hole").
- **Depth limits:** the thickness comes from the settings (`panel.thickness`, as for the cut). The
  pocket depth must leave a floor: new setting `pocket.min_floor`, default 2 mm (placeholder);
  deeper is a hard error, as is a depth that reaches the cups.
- **Groups:** nesting does not rotate shapes, so the group signature is computed in the plate's
  own frame, sensitive to orientation and mirroring, tolerance 0.05 mm on the loop's vertices and
  radii.
- **Collisions:** a pocket path (the cutter path) that would leave the
  plate outline is a hard error; a pocket path closer than the screw-head clearance to a screw or
  fixing hole, or touching another pocket, is a warning.
- **Order in `B<nn>P`:** grouped by tool, in group order within a tool. Tool changes are by tool
  number in each block, as in the real programs that mix tools (203 of 717 in the H05 backup);
  that the machine handles the chosen tool numbers is not verified.

## Open items (need the machine or the user)

1. Real pocket tool, diameter, depth, feeds and stepover; the rail slot width and depth.
2. Whether the plunge entry and the feed values are fine for MDF on this machine.
3. Whether the mirrored export (turn over about the vertical axis) gives the orientation the
   operator expects on the machine; confirmed only after a real plate has been cut.
