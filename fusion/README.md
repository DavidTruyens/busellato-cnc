# Busellato S.EASY — vacuum table model for collision checks

A Fusion script that builds the vacuum beams and pods under the panel and
sets them as fixtures, so Fusion's simulation shows the cutter in red
where it would hit a pod or beam. Spec:
`docs/superpowers/specs/2026-09-26-vacuum-table-design.md`.

## Install (once)
    ln -sfn "<repo>/fusion/busellato_table" "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/busellato_table"
Then Utilities → Scripts and Add-Ins → "busellato_table".

## Per job
1. In the job's design (with its setup: stock = the panel, origin on the top face at the G54 corner), run the script. The first time it only creates the parameters.
2. Modify → Change Parameters: set `BEAM<n>_X` and `BEAM<n>_POD<k>_Y` to the scale readings of the machine, `BEAM<n>_POD<k>_ON` to 1 for pods in use.
3. Run the script again. It builds the "Vacuum table" component and sets the bodies as fixtures in every setup.
4. Simulate the setup. Red tool = collision with a pod or beam.

The script stops and changes nothing if a beam or pod is outside its
travel, pods overlap, or a parameter is missing; it lists every problem.
Dimensions in `busellato-table.json` are **provisional** until measured
with `MEASURE.md` — until then the model is an approximation.

## Tests
`python3 -m unittest discover -s tests -p 'test_table_geometry.py'`
