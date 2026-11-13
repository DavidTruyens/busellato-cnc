# Busellato S.EASY post-processor (TPA CNC90)

Fusion post for the CNC90 v3.0 control. Writes a program **source**
(text, TPA dialect of ISO G-code) that is copied onto the control and
compiled there. Spec: `docs/superpowers/specs/2026-09-25-fusion-post-design.md`.

## Install
Copy `busellato-cnc90.cps` to
`~/Library/Application Support/Autodesk/Fusion 360 CAM/Posts/` and pick
"Busellato S.EASY - TPA CNC90" in the NC program dialog.

## Setup rules in Fusion
- Stock = the panel. Setup origin on the **top** face (Z0 = panel top), X0 Y0 at the panel corner.
- Tools from the **"Busellato S.EASY"** tool library (Fusion local library,
  `~/Library/Application Support/Autodesk/CAM360/libraries/Local/Busellato S.EASY.json`):
  T65 router Ø18, T66 router Ø8, T1-T30 vertical drills.
- 2D contour and 2D pocket: compensation "In computer"; pocket entry **plunge** or **ramp** (helix is refused).
- Drilling: plain "drilling - rapid out" only.
- Program name = 1-8 characters A-Z 0-9 _ - ; it becomes the file name on the machine.

## One NC program per tool (Fusion Personal)
Fusion Personal **cannot post an NC program that contains a tool change**: posting fails
before the post-processor even runs (no file, no log). So make **one NC program per tool**:
the router operations (T65 or T66) in one program, the drilling operations (T1-T30) in
another, each with its own program name (e.g. `PART` and `PARTD`). Each program is copied
to the machine and compiled there separately, then run one after the other.

## Settings
| Setting | Default | Meaning |
|---|---|---|
| Feed unit | m/min | F1 = 1 m/min (confirm on the machine) |
| Origin | G54 | G55 selectable |
| Mirror Y | off | if the machine's Y runs opposite to Fusion's |
| Arc output | arcs | "lines" = emergency fallback |
| Segment length | 2 mm | chord length for arc output = lines (and for an allowed Z-changing arc) |
| Merge tolerance | 0.05 mm | collinear moves merged; also merges linearized arc chords (on R91 the chords come out ~6 mm, so set 0 to keep a short segment length) |
| Warn above N lines | 250 | largest known program ~250 lines |
| Max depth below stock | 5 mm | protects the spoilboard |
| Allowed tool numbers | 1-14,65,66 | 14 vertical drills (T1-T14: the drill head has 14 spindles and the backup programs use no vertical drill above T14) and the two routers; extend when more tools are mapped |

## Getting a program onto the machine
1. Post in Fusion; copy the file to the shuttle diskette (Mac: format first, see `hdd/COPY-PLAN.md`).
2. At the DOS prompt: the first character of the name is the folder and the **rest** is the file name:
   `COPY A:\<NAME> C:\CNC90\MOD1\SORG\SRG\<first letter>\<rest of name>` (program `PART` = `SRG\P\ART`).
   **Check first** that it does not exist (`DIR C:\CNC90\MOD1\SORG\SRG\<letter>\<rest>`), or use the loader
   batch file from `tools/make-loader.py`, which does the split and never overwrites.
3. Start CNC90 (`CNC90`), compile the program ("Programma Kompileren"), run it.

## Machine tests
`machine-tests/` holds the test programs for the first visit (unedited post output) and
`machine-tests/RUN-SHEET.md` with the order and what to watch.

## Tests
`python3 -m unittest discover -s tests` (format checker on the 118 machine
programs, post cases, machine test programs). See `post/tests/`.
