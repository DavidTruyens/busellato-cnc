# Panel Nesting and Program Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local browser tool that turns DXF outlines into templates nested on 1220 × 2440 panels and writes the CNC90 drill and cut programs plus a diskette folder.

**Architecture:** A stdlib-only Python package `nesting/` with a pure core (DXF reader → layout → operations → backend text) and a thin `http.server` UI. The preview and the emitter both read the same `Program` objects, so they cannot disagree. Backends sit behind one function signature so a LinuxCNC backend can be added later.

**Tech Stack:** Python 3.11 standard library only (no `ezdxf`), `unittest`, one HTML file with inline JS. Run tests with `python3 -m unittest discover -s tests`.

**Spec:** `docs/superpowers/specs/2026-11-08-nesting-tool-design.md` (UI reference: `docs/nesting-tool/mockup.html`; format reference: `docs/superpowers/specs/2026-09-25-fusion-post-design.md`).

## Global Constraints

- Program names: 1–8 characters of `A-Z 0-9 _ -`; first character is the `SRG` folder and must be one of `7 9 A-P R-Z` (`tools/make-loader.py` enforces 2–8 and the folder set). Scheme `N<panel number><F|S|C>`.
- Output files: CRLF, upper case, ASCII only, no extension; numbers up to 3 decimals with trailing zeros removed.
- Arcs stay arcs (`G2`/`G3` with `U<radius>`, arcs over 180° split in two); never `G41`/`G42`; cutter offset is computed by the tool.
- Warn above 250 lines per program; never split a program and never refuse for size or travel.
- Panel 1220 × 2440, unusable edge 10, gap between templates and between shapes = tool diameter + 4; shapes are not rotated, templates may turn 90°.
- Origin `G54` (left) or `G55` (right) as a setting; `P5` = top face.
- Never overwrite: generated output goes to a new folder, an existing folder is an error.
- Python 3.11 stdlib only. Every number that is a guess (tool diameters, feeds, depths, drill sizes, tool numbers) is a setting with a placeholder default, never a constant in code.

## Review Focus

1. DXF with an open outline, no outline, two outlines, or only polylines: the error names the file and the problem (Task 2).
2. A concave outline with a feature narrower than the tool: the offset fails with an error, never a silent bad path (Task 4).
3. A shape or template that does not fit a panel: the plan reports which one, the UI shows it, nothing crashes (Task 3, Task 9).
4. Zero shapes, quantity 0, or everything disabled: an empty plan and no programs, not an exception (Task 3).
5. Nonsense settings (depth per pass ≤ 0 would loop forever, tool diameter 0, negative heights): rejected with the field name (Task 1).

---

### Task 1: Package, settings and project file

**Files:**
- Create: `nesting/__init__.py`, `nesting/settings.py`, `tests/test_nesting_settings.py`

**Interfaces:**
- Produces: `Settings` (dataclass tree) with `Settings.default() -> Settings`, `to_dict() -> dict`, `Settings.from_dict(d: dict) -> Settings` (unknown keys ignored, missing keys default), `validate() -> None` raising `SettingsError(field: str, message: str)`.
  - `panel`: `length=2440, width=1220, edge=10`
  - `heights`: `scrap=18, template_stock=18, shape_thickness=18, into_template=0.3, into_scrap=0.5, fix_into_scrap=1`
  - `router`: `tool=66, diameter=8, spindle_rpm=18000, plunge_feed=1, cut_feed=3, depth_per_pass=9, clearance=4, direction='ccw'`
  - `drill_fix`: `tool=1, diameter=6, feed=1`; `drill_screw`: `tool=2, diameter=3, depth=8, feed=1`
  - `template`: `mode='auto'` (`'auto' | 'fixed' | 'none'`), `shapes_per=2, group_by='length'` (`'length' | 'order'`), `margin_end=45, margin_side=45, fix_inset=15, head_dia=14, fixed_width=0, fixed_height=0`
  - `origin='G54'`
  - property `gap = router.diameter + router.clearance`
- Tools 66 = Ø8 and 65 = Ø18 come from `post/README.md`; tool numbers 1 and 2 for the drills are placeholders.

- [ ] **Step 1: Write failing tests** `SettingsTests`: `test_defaults_roundtrip_through_dict` (`Settings.from_dict(s.to_dict()) == s`), `test_missing_keys_default`, `test_gap_is_diameter_plus_clearance` (12 → 16 when `router.diameter=12`), and `test_rejected` parametrized over: `depth_per_pass=0`, `router.diameter=0`, `heights.scrap=-1`, `origin='G56'`, `template.mode='x'`, each asserting `SettingsError` whose `.field` names the setting (e.g. `'router.depth_per_pass'`).
- [ ] **Step 2: Run to verify failure** — `python3 -m unittest tests.test_nesting_settings` can't import; use `python3 -m unittest discover -s tests -p 'test_nesting_settings.py'`. Expected: ImportError.
- [ ] **Step 3: Implement** dataclasses in `nesting/settings.py` as specified above.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `git add nesting tests/test_nesting_settings.py && git commit -m "Add nesting package and validated settings"`.

### Task 2: Geometry types and DXF reader

**Files:**
- Create: `nesting/geometry.py` (types only in this task), `nesting/dxf.py`, `tests/test_nesting_dxf.py`

**Interfaces:**
- Produces in `geometry.py`: `Pt = tuple[float, float]`; frozen dataclasses `Line(a: Pt, b: Pt)` and `Arc(a: Pt, b: Pt, center: Pt, radius: float, ccw: bool)`; `Seg = Line | Arc`; `bbox(segs: list[Seg]) -> tuple[float, float, float, float]` (exact, includes arc extremes); `translate(segs, dx, dy) -> list[Seg]`.
- Produces in `dxf.py`: `Hole(x: float, y: float, diameter: float)`; `Shape(name: str, outline: list[Seg], holes: list[Hole])` with `Shape.length`, `Shape.width` (bbox size) — outline and holes are normalised so the outline's bbox lower-left is (0, 0); `read_dxf(path: str | Path) -> Shape` (name = file stem with `_` → space left as is); `DxfError(path, message)`.
- Supports `LINE`, `ARC`, `CIRCLE`, `LWPOLYLINE` (with bulge) and `POLYLINE`/`VERTEX` in ASCII DXF. Outline = entities on layer `CONTOUR`, else the single largest closed chain. Holes = circles on layer `HOLES`, else circles inside the outline. Endpoints join within 0.01 mm.

- [ ] **Step 1: Write failing tests** `DxfTests`: `test_reads_all_exported_plates` (every `plates/*.dxf`: closed chain, 2 holes, diameter 6.6 ± 0.001, `length`/`width` equal `plates.json` `world_bbox_xy` within 0.05), `test_lwpolyline_with_bulge` (a written rectangle with one bulged edge becomes 3 `Line` + 1 `Arc`, bbox includes the arc's bulge), `test_open_outline_names_file`, `test_no_outline`, `test_two_outlines` (each asserts `DxfError` and that `str(err)` contains the file name and a word from: `open`, `no outline`, `more than one`), `test_circles_without_layers_become_holes`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** the reader; chain-order segments by endpoint matching (the throwaway `check_dxf.py` logic is the same idea); arc direction from DXF is always counter-clockwise start → end angle.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `Add DXF reader and geometry types`.

### Task 3: Layout (grouping, templates, nesting)

**Files:**
- Create: `nesting/layout.py`, `tests/test_nesting_layout.py`
- Delete after porting: `tools/nest_plates.py`, `tests/test_nest_plates.py`

**Interfaces:**
- Consumes: `Shape`, `Hole`, `Settings`.
- Produces: `ShapeEntry(shape: Shape, qty: int = 1, enabled: bool = True, thickness: float | None = None)`; dataclasses `PlacedShape(name, copy, x, y, shape, thickness)`, `PlacedTemplate(id, width, height, shapes, fix_holes: list[Hole], screw_holes: list[Hole], x, y, rotated)` (x, y, rotated = position on the panel, bottom-left of the footprint), `PanelPlan(id, templates)`, `Plan(panels: list[PanelPlan], problems: list[str])`; `build_plan(entries: list[ShapeEntry], settings: Settings) -> Plan`; `to_panel(t: PlacedTemplate, x: float, y: float) -> Pt` (template frame → panel frame, rotation 90° counter-clockwise, same maths as `tools/nest_plates.py:to_panel`); `footprint(t) -> tuple[float, float]`.
- Port the logic of `tools/nest_plates.py` (pairing by sorted length, widest shape at the bottom, `check_template` clearance of `tool_dia/2 + head_dia/2 + 3`, MaxRects BSSF) and keep every behaviour its tests check. New: `template.mode='fixed'` uses `fixed_width × fixed_height`; `'none'` = margins 0, no fixing holes, each shape its own unit (screw holes still drilled); `group_by='order'` keeps list order; shapes needing more than a panel go to `Plan.problems` and are left out.

- [ ] **Step 1: Port tests** from `tests/test_nest_plates.py` to the new API (same assertions: pairing neighbours, odd count, quantity, template size and holes, clearance, too-small margin rejected, no overlap and gap ≥ `settings.gap`, every template placed once, rotation transform, oversize is an error → now a `problems` entry). Add `test_empty_when_nothing_enabled` (`Plan.panels == []`, `problems == []`) and `test_quantity_zero_skipped`, `test_oversize_shape_reported_not_raised` (a 2500 mm shape: `problems[0]` contains its name), `test_fixed_template_size`, `test_none_mode_has_no_fixing_holes`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** `nesting/layout.py`; build shapes for the tests from the real `plates/*.dxf` via `read_dxf`.
- [ ] **Step 4: Run to verify pass**; then `git rm tools/nest_plates.py tests/test_nest_plates.py` and run the full suite (`python3 -m unittest discover -s tests`).
- [ ] **Step 5: Commit** `Move nesting into the nesting package with generic shapes and template modes`.

### Task 4: Contour offset and arc handling

**Files:**
- Modify: `nesting/geometry.py`
- Test: `tests/test_nesting_geometry.py`

**Interfaces:**
- Produces: `OffsetError(message)`; `offset_outline(segs: list[Seg], r: float, outward: bool = True) -> list[Seg]` (closed chain in, closed chain out; sharp convex corners get a tangent arc of radius `r`, concave corners are trimmed at the intersection); `set_direction(segs, ccw: bool) -> list[Seg]` (reverses if needed; orientation from signed area of a sampled polyline); `split_large_arcs(segs) -> list[Seg]` (any arc over 180° becomes two equal arcs); `sample(segs, step: float = 0.5) -> list[Pt]`; `distance_to_chain(p: Pt, segs: list[Seg]) -> float`.

- [ ] **Step 1: Write failing tests** `OffsetTests`: `test_rectangle_offset_by_4` (200 × 100 → bbox 208 × 108, four corner arcs of radius 4), `test_real_plate_offset_is_r_away` (for every `plates/*.dxf` outline and `r=4`: sample the offset chain every 0.5 mm; the distance of each sample to the original outline is within 0.01 of 4), `test_inward_offset`, `test_narrow_slot_raises_offset_error` (a 6 mm wide slot cut into a bar, `r=4` outward-of-the-slot fails with `OffsetError`), `test_direction_ccw_cw`, `test_split_large_arcs` (a 270° arc → two 135° arcs, same endpoints and total sweep), `test_offset_returns_closed_chain`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Offset each segment (line shifted along its normal; arc radius ± `r` about the same centre), join neighbours by intersection, add a tangent arc at a convex gap, drop segments that collapse, and raise `OffsetError` when the result self-intersects (check by sampling).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `Add contour offset, direction and arc splitting`.

### Task 5: Operations and programs (Z logic)

**Files:**
- Create: `nesting/program.py`, `tests/test_nesting_program.py`

**Interfaces:**
- Consumes: `Plan`, `Settings`, `offset_outline`, `set_direction`, `split_large_arcs`, `to_panel`.
- Produces: `DrillOp(x, y, depth: float, diameter: float)`; `ContourOp(segs: list[Seg], depth: float, label: str)`; `Program(name: str, tool: int, kind: str, description: str, stock: tuple[float, float, float], ops: list, spindle_rpm: int | None, plunge_feed: float, cut_feed: float, warnings: list[str])` with `kind` in `'drill'` or `'cut'`; `plan_programs(plan: Plan, settings: Settings) -> list[Program]`; `stack_top(settings, panel: PanelPlan) -> float` (= `scrap + template_stock + max shape thickness in the panel`).
- Rules: per panel `N<panel number>F` (fixing holes, `drill_fix.tool`), `N<n>S` (screw holes, `drill_screw.tool`), `N<n>C` (cut, `router.tool`). Equal drill diameters and tools merge F and S into `N<n>F`. Header stock = `(panel.length, panel.width, stack_top)`. Depths are measured **down from the stack top**; work in absolute heights above the cup top and convert with `depth = stack_top − bottom_height`. Bottom heights (defaults give stack 54): fixing hole `scrap − fix_into_scrap` (17 → depth 37); screw hole `scrap + template_stock − drill_screw.depth` (28 → depth 26); shape cut `scrap + template_stock − into_template` (35.7 → depth 18.3); template outline `scrap − into_scrap` (17.5 → depth 36.5). Passes: `ceil(total / depth_per_pass)` equal steps. Cut order: all shape outlines (offset outward by `diameter/2`, direction from settings) then all template outlines; a template outline is its rectangle in panel coordinates, offset outward. Shape and hole coordinates go through `to_panel` of their template. A program with more than 250 lines is flagged in `warnings` (line count from Task 6's emitter is passed in by the caller; here warn on estimated lines: sum over contours of `1 + segments` per pass, plus `len(drills)`, plus 3).

- [ ] **Step 1: Write failing tests** `ProgramTests`: `test_three_programs_per_panel_with_names` (names `N1F`, `N1S`, `N1C`), `test_equal_drills_merge`, `test_stack_top_uses_thickest_shape` (shapes of 18 and 22 mm in one panel → 18 + 18 + 22), `test_depths` (defaults, stack 54: assert fixing 37, screw 26, shape cut 18.3, template 36.5), `test_cut_order_shapes_before_templates`, `test_passes_equal_steps` (depth 18.3 with 9 mm passes → 3 passes of 6.1), `test_hole_coordinates_follow_rotated_template`, `test_every_name_valid` (regex `[A-Z0-9_-]{2,8}` and first character in the folder set, for 120 panels), `test_line_warning`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** `plan_programs`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `Add programs: drill and cut operations from the layout`.

### Task 6: CNC90 emitter

**Files:**
- Create: `nesting/backends/__init__.py`, `nesting/backends/cnc90.py`, `tests/test_nesting_cnc90.py`

**Interfaces:**
- Consumes: `Program`, `Settings`.
- Produces: `BACKENDS: dict[str, Callable[[Program, Settings], str]]` in `nesting/backends/__init__.py` with `"cnc90"` registered; `emit(program: Program, settings: Settings) -> str` in `cnc90.py` returning the full source, CRLF, upper case.
- Format (see the post spec, "Output rules"): header `G71X<L>Y<W>Z<stack>T00N<total lines>L<total − 3>`, `G150()`, drill `G81G90<origin>P5T01<nn>X<x>Y<y>Z<depth>`, contour start `G88G90<origin>P5T01<nn>S<rpm>F<plunge>X<x>Y<y>Z<depth>`, then for the first move a `G1G90F<cut>X<x0>Y<y0>Z<depth>` repeating the start point when the plunge and cut feeds differ and the first segment is an arc, otherwise `F<cut>` goes on the first line; lines `G1G90X<x>Y<y>Z<depth>`; arcs `G2|G3G90G17X<x>Y<y>U<r>` (`G3` = counter-clockwise); `M2`. `F` only when it changes. Drill `T01<nn>` and router `T01<nn>` use two-digit `nn` (65, 66, 01, 02).

- [ ] **Step 1: Write failing tests** `Cnc90Tests`: golden tests that rebuild three machine test programs from geometry and compare byte-for-byte with the files in `post/machine-tests/` — `test_matches_ZZT1AD` (3 drills at depth 2, stock 400 × 300 × 60), `test_matches_ZZT2A` (one line, F0.333 → F1, S18000), `test_matches_ZZT1` (rounded rectangle with `G2`/`G3` arcs, plunge F1 → cut F3, stock 400 × 300 × 18); plus `test_n_and_l_counts` (`N` = lines, `L = N − 3`), `test_number_format` (`9.15`, `13`, `0.5`, never `13.`), `test_crlf_upper_ascii`, `test_origin_g55`, `test_passes_check_cnc90` (generated programs for the 12-plate plan pass `tools/check_cnc90.py` run as a subprocess, exit 0), `test_registry_has_cnc90`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** `emit`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `Add CNC90 emitter with golden tests against the machine test programs`.

### Task 7: Preview data from the programs

**Files:**
- Create: `nesting/preview.py`, `tests/test_nesting_preview.py`

**Interfaces:**
- Consumes: `Plan`, `list[Program]`, `Settings`.
- Produces: `preview_data(plan: Plan, programs: list[Program], settings: Settings) -> dict` (JSON-serialisable): `{"panel": {"length", "width"}, "panels": [{"id", "templates": [{"id", "x", "y", "w", "h", "rotated", "shapes": [{"name", "path": "<svg path d>", "cx", "cy"}], "fix": [{"x","y"}], "screw": [{"x","y"}]}], "programs": [{"name","tool","kind","description","ops","lines","warnings"}]}], "problems": [...], "z": {"stack_top","cut_shape_bottom_depth", ...}}`. Y is flipped for SVG (`panel.width − y`). Hole positions and outline paths are taken from the **programs' ops**, not recomputed from the layout, so the preview shows what the machine will get; shape outlines drawn are the un-offset outlines from the layout, the offset cut path is a second field `cut_path`.

- [ ] **Step 1: Write failing tests** `PreviewTests`: `test_holes_equal_drill_ops` (set of `(x, y)` of `fix` and `screw` equals the `DrillOp` coordinates of the F and S programs, within 0.001), `test_cut_path_matches_contour_ops` (the `cut_path` points equal the sampled `ContourOp` segments), `test_json_serialisable` (`json.dumps` works), `test_y_flipped`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `Add preview data built from the program operations`.

### Task 8: Output folder, run sheet and project file

**Files:**
- Create: `nesting/output.py`, `tests/test_nesting_output.py`

**Interfaces:**
- Consumes: `Program`, `BACKENDS`, `preview_data`, `Settings`; `tools/make-loader.py` (called as `python3 tools/make-loader.py OUT_DIR FILE...` by subprocess; reuse, do not rewrite).
- Produces: `write_output(out_dir: Path, plan: Plan, programs: list[Program], settings: Settings, project: dict, backend: str = 'cnc90') -> list[Path]` — creates `out_dir` (error `FileExistsError` if it exists), writes one file per program named by the program name, `LOAD.BAT`/`COLLECT.BAT` via `make-loader.py`, `PROJECT.json` (settings plus shape list), and `RUNSHEET.html` (per panel: SVG of the shapes with names and positions, then the steps: drill F → screw down panel → place shapes → drill S → screw shapes → cut C, with the stack height and every Z value that was written).

- [ ] **Step 1: Write failing tests** `OutputTests`: `test_files_written_and_loader_present`, `test_existing_folder_is_an_error` (and nothing inside it changes), `test_program_files_pass_check_cnc90`, `test_project_json_roundtrips_settings`, `test_runsheet_mentions_every_program_and_shape`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `Add output folder, loader batch files, run sheet and project file`.

### Task 9: Server and page

**Files:**
- Create: `nesting/server.py`, `nesting/web/index.html`, `tests/test_nesting_server.py`

**Interfaces:**
- Produces: `make_server(project_dir: Path, port: int = 8765) -> http.server.HTTPServer` bound to `127.0.0.1` only. Routes: `GET /` the page; `GET /api/project` → `{"shapes": [{"name","length","width","qty","enabled"}], "settings": {...}}`; `PUT /api/project` replaces shape quantities and settings, saves `project.json`, returns the same; `POST /api/shapes` body `{"filename": str, "text": str}` stores the DXF in `project_dir/shapes/` and returns the shape or a 400 with the `DxfError` message; `GET /api/plan` → `preview_data(...)` for the current project, with `problems` and settings errors in the body (HTTP 200, never a stack trace); `POST /api/generate` → writes `project_dir/out/<YYYYMMDD-HHMMSS>/` and returns the file list.
- The page is `docs/nesting-tool/mockup.html` made live: same layout and styles, `DATA` replaced by `fetch('/api/plan')` after every settings change (debounced 300 ms), upload by drop or file chooser, program list from the response, problems shown in a banner, Generate calls `/api/generate` and shows the returned files and the "At the machine" steps. Settings controls cover every field in Task 1.

- [ ] **Step 1: Write failing tests** `ServerTests` (server on port 0 in a thread, `urllib`): `test_project_roundtrip`, `test_upload_valid_dxf_adds_shape`, `test_upload_open_outline_is_400_with_file_name`, `test_plan_for_12_plates` (3 panels, 9 programs, no problems), `test_plan_reports_oversize_shape_not_error`, `test_plan_with_invalid_setting_returns_field_error`, `test_generate_creates_new_folder_each_time`, `test_binds_to_localhost_only`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** the server and the page.
- [ ] **Step 4: Run to verify pass**; then load the page with headless Chrome (`--screenshot`, as used for the mockup) and look at the Layout, Drill and Cut views against `docs/nesting-tool/mockup.html`.
- [ ] **Step 5: Commit** `Add local server and live page`.

### Task 10: Command line, docs and end-to-end check

**Files:**
- Create: `nesting/__main__.py`, `nesting/README.md`
- Modify: `README.md` (one line linking `nesting/README.md`), `tests/test_repo_layout.py` only if it fails on the new folders

**Interfaces:**
- Produces: `python3 -m nesting [PROJECT_DIR] [--port N]` starts the server, prints the URL, creates `PROJECT_DIR` (default `./nesting-project`) and seeds it with the shapes from `plates/*.dxf` only when it is empty and `--seed-plates` is given.

- [ ] **Step 1: Write failing test** `test_end_to_end_12_plates` in `tests/test_nesting_server.py`: start the server on a temporary project seeded from `plates/`, `GET /api/plan` → 3 panels, `POST /api/generate` → 9 program files plus `LOAD.BAT`, `PROJECT.json`, `RUNSHEET.html`, and `tools/check_cnc90.py` passes on all nine.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** `__main__.py` and write `nesting/README.md` (how to start it, the settings, the machine steps from the spec, and the "not run on the machine" warning, plus how to add a backend).
- [ ] **Step 4: Run the whole suite** — `python3 -m unittest discover -s tests` — expected all OK.
- [ ] **Step 5: Commit** `Add command line entry, README and end-to-end test`.

## Self-review notes

- Spec coverage: generic shapes and template modes (Tasks 2, 3), nesting and rotation (3), 4 fixing and screw holes (3, 5), one program per tool (5), Z/stack convention in one place (5), settings model and validation (1), backend interface (6), same-numbers preview (7), diskette folder, run sheet, no overwrite (8), browser UI (9), start and docs (10). Hardware tests are not in this plan: the first run is the air → scrap → real sequence with the user at the machine, and nothing here is claimed as machine-tested.
- Proportion: ten tasks; signatures and assertions only, no function bodies.
