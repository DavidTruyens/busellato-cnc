# Machine test run sheet (first visit with the post-processor)

Rules at the machine: never type FORMAT, DEL, CHKDSK /F, or SALVAINC; the only
writes to C: are the new ZZT* files below. Photograph anything unexpected.
Hand on the emergency stop for every run. Feed override at minimum for the first run.
Z reference check: in step 2 the tool must stay ~58 mm above the table.

Fusion Personal cannot post a program with a tool change, so every test is split per
tool: the router contour (T65) and the drilling (T1) are separate programs. Copy and
compile both, then run them one after the other (router first, then drills).

Before copying, check that the name is free (none of the ZZT* names is in
`C:\CNC90\MOD1\SORG\SRG\Z` according to `hdd/LISTING.TXT`):

    DIR C:\CNC90\MOD1\SORG\SRG\Z\ZZT1A

Copy (per program, from the shuttle diskette), then compile it in CNC90:

    COPY A:\ZZT1A  C:\CNC90\MOD1\SORG\SRG\Z\ZZT1A
    COPY A:\ZZT1AD C:\CNC90\MOD1\SORG\SRG\Z\ZZT1AD

| Program | Tool | Stock (G71 Z) | Content | Lines |
|---|---|---|---|---|
| ZZT1A  | T65 router | 60 (air) | L-shape contour, 2 mm deep, G2/G3 arcs | 18 |
| ZZT1AD | T1 drill   | 60 (air) | 3 holes G81, 2 mm deep | 6 |
| ZZT2A  | T65 router | 60 (air) | one 500 mm line along X at Y159, F1 | 5 |
| ZZT3A  | T65 router | 60 (air) | Ø200 circle, inside (tool path R91), F3, two G3 arcs | 7 |
| ZZT3B  | T65 router | 60 (air) | same circle as 5 mm lines | 120 |
| ZZT3C  | T65 router | 60 (air) | same circle as 2 mm lines | 290 |
| ZZT3D  | T65 router | 60 (air) | same circle as 1 mm lines | 576 |
| ZZT1   | T65 router | 18 (real) | L-shape contour, 2 mm deep (same XY as ZZT1A) | 18 |
| ZZT1D  | T1 drill   | 18 (real) | 3 holes G81, 2 mm deep | 6 |

| # | Program | Panel on table | Watch / measure | Result |
|---|---|---|---|---|
| 1 | ZZT1A, ZZT1AD | none | Copy and compile both. Do they compile and appear in the program list? Note any compiler message. | |
| 2 | ZZT1A then ZZT1AD | none | Origin corner, Y direction, arc direction, order. Tool must stay ~58 mm above the table. If it goes lower, STOP: the Z reference is not "table + G71 thickness". ZZT1AD: hole positions and drill T1 selected | |
| 3 | ZZT2A | none | Stopwatch over the 500 mm line (X0 → X500, beyond the 400 mm stock: check the travel is free): 30 s → F is m/min. If it barely moves (F1 = 1 mm/min would take 500 min), F is mm/min: STOP | |
| 4 | ZZT3A–D | none | Time each circle (tool path Ø182 = 571.8 mm at F3 = 3 m/min → 11.4 s). Listen for stutter. Note the finest segment that still runs smoothly. ZZT3C (290 lines) and ZZT3D (576 lines) are longer than the largest known machine program (~250 lines): note whether they compile and load at all | |
| 5 | ZZT3A | none | The line `G1G90F3X291Y150Z2` immediately before the G3 arcs is a zero-length feed-change line (the machine's own programs never put F on arcs). Confirm the control accepts it and the circle runs at the new feed; if it errors, note the message. | |
| 6 | ZZT1 then ZZT1D | 18 mm scrap | Copy and compile both, run one after the other. Measure: L outline, arc R, hole positions (320,220) (352,220) (320,260), depth 2 | |

After the visit: set the post settings from the results (mirror Y, feed unit,
origin, line warning) and record them in post/README.md.
