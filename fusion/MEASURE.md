# Vacuum table — measurement sheet

Fill in at the machine with a tape measure; photograph every scale and
reference edge. Then copy the values into `fusion/busellato-table.json`
and remove each measured key from `provisional`.

Reference edges (keep consistent): a beam's X value = its **left edge
(min X)** on the X scale; a pod's Y value = its **front edge (min Y)** on
the Y scale. G54 corner = the origin corner found in run-sheet step 2.

| Key | What to measure | Value (mm) | Photo |
|---|---|---|---|
| `beams` | Number of beams (cross bars) | | |
| `pods_per_beam` | Pods available per beam | | |
| `beam_width` | Beam width along X | | |
| `beam_height` | Beam height (table surface to top of beam) | | |
| `beam_length` | Beam length along Y | | |
| `beam_y_start` | Y scale reading at the beam's front end | | |
| `beam_x_min` | X scale reading of a beam's left edge, beam fully left | | |
| `beam_x_max` | X scale reading of a beam's left edge, beam fully right | | |
| `pod_x_size` | Pod footprint along X | | |
| `pod_y_size` | Pod footprint along Y | | |
| `pod_height` | Pod height (top of beam to top of pod) | | |
| `pod_y_min` | Y scale reading of a pod's front edge, pod fully to the front | | |
| `pod_y_max` | Y scale reading of a pod's front edge, pod fully to the back | | |
| `scale_to_g54_x` | X scale reading at the G54 panel corner | | |
| `scale_to_g54_y` | Y scale reading at the G54 panel corner | | |

Also note: pod shape if not rectangular (sketch with dimensions); any
clamps or stops that stick up above the pods; where the scales are
fixed to the machine.
