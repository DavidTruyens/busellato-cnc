# Tool Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One table of bits and one table of machine toolheads; the router, the drills and the pocket groups name a head and take diameter, spindle speed, feeds, depth per pass and stepover from the bit in it.

**Architecture:** A new module `nesting/tools.py` holds the fixed head list, `Bit`, `ToolTable` (load, save, check) and the migration from old settings. `Settings` carries a `tools: ToolTable` and resolves each operation's head to its bit (`router_bit`, `fix_bit`, `screw_bit`); pocket groups resolve their head in `pockets.effective`. `project.json` stores the table under a top-level `tools` key; a project without it is migrated on load and written in the new form on the first save. The CNC90 emitter is not touched.

**Tech Stack:** Python 3.11 standard library, `unittest`; the page is plain HTML/JS in `nesting/web/index.html`.

**Spec:** `docs/superpowers/specs/2026-11-13-tool-table-design.md` (binding). Background: `nesting/README.md`, `docs/superpowers/specs/2026-11-13-pockets-design.md` ("As built").

## Global Constraints

- `nesting/backends/` does not change: `git diff windows-start -- nesting/backends/` is empty at the end. The golden programs ZZT1, ZZT1AD, ZZT2A stay byte for byte identical (their tests are not edited).
- Output for a consistent project does not change: the baseline test of Task 1 must pass unchanged after every task.
- Full suite: `python -m unittest discover -s tests` from the worktree root (469 tests on the base). Tests that read removed settings fields are rewritten to the new ones, not deleted, unless they test the removed "one tool number two diameters" rule.
- Heads (fixed in code): T65, T66 (big spindles, router bits); T1 to T30 (drill cross, vertical, drill bits); T53, T56 (drill cross, horizontal, drill bits); T60 (blade/drill in X), T61 (blade/drill in Y) (drill or blade bits).
- Bit types `router`, `drill`, `blade`. Router: diameter, spindle_rpm, plunge_feed, cut_feed, depth_per_pass, stepover_pct (all required). Drill: diameter, plunge_feed required, spindle_rpm optional. Blade: diameter required, spindle_rpm and cut_feed optional.
- Stays on the operation: `router.tool`, `router.clearance`, `router.direction`, `drill_fix.tool`, `drill_screw.tool`, `drill_screw.depth`, `pockets.tool`, `pockets.depth`, `pockets.direction`, `pockets.min_circle_diameter`, `pockets.min_floor`; per group: `enabled`, `tool`, `depth`, `direction`.
- Removed: `router.diameter/spindle_rpm/plunge_feed/cut_feed/depth_per_pass`, `drill_fix.diameter/feed`, `drill_screw.diameter/feed`, `pockets.diameter/depth_per_pass/plunge_feed/cut_feed/spindle_rpm/stepover_pct`, and the same per-group override fields.
- Every error about a head names the operation and the head. No silent default for an empty or wrong head.
- Public repo: never name the shop operator ("the shop operator"); no hostnames, emails, IPs, customer names in files or commits. No mention of Claude or AI in commit messages.
- Nothing has run on the machine: docs say "format-checked and tested", never "works".

## Rulings made while planning (the spec leaves these open)

- R1. Programs use only these heads: router and pockets T65/T66, fixing and screw drills T1 to T30. T53, T56, T60, T61 are listed and can hold a bit; an operation naming one is refused ("programs do not use T53"). Spec non-goals: horizontal drills and X/Y heads.
- R2. The pocket default head (`pockets.tool`) is checked to be T65/T66 in `Settings.validate`; that it holds a router bit is checked only for an enabled pocket group with a pocket on the plan (as the old diameter conflict was), so a project without pockets still plans with an empty default head.
- R3. Migration order for one head: router, pocket default, fixing drill, screw drill; the first one wins on any number that differs; one note per head lists what was taken and what was dropped. A migrated operation whose head is not usable for it (not in the list, or the wrong kind, e.g. old `pockets.tool` 7) gets its bit created but not placed, plus a note; planning then stops with the head error. The spec's "router's wins" is the first rule of this order.
- R4. The default (seed) table equals the migration of the old default settings: bit `b1` "Router 8" (router, 8, 18000, 1, 3, depth_per_pass 9, stepover 40) in T66; `b2` "Drill 6" (drill, 6, plunge 1) in T1; `b3` "Drill 3" (drill, 3, plunge 1) in T2. Old defaults disagreed on T66's depth per pass (router 9, pocket 4): per the spec the router's 9 is taken, so pocket programs of a project on old default settings now cut in 9 mm passes, not 4 (the spec's "byte for byte covers projects whose settings agree").
- R5. Drill and blade spindle speed: optional, seeded empty (not written by any program).
- R6. Migration notes are shown in the plan's problem list and returned by `/api/project` as `tools_notes`; the first save writes the new form and strips the obsolete per-group override fields, so the notes disappear.
- R7. A `PUT /api/project` without a `tools` key keeps the stored table (no reset to defaults).

## Review Focus

1. A hand-edited `tools` in `project.json` (head naming a missing bit id, a router bit in T1, an unknown head `T70`, `bits` not a list): refused with the head or bit named, never a silent default. Test: Task 2 `test_bad_tables_are_refused_naming_the_head`.
2. A PUT without `tools` (a page from before the upgrade still open): the stored table survives. Test: Task 6 `test_save_without_tools_keeps_the_stored_table`.
3. An old project whose pocket group override has `tool: 65` and T65 is empty: the enabled group is an error naming group and head; switched off, it is not an error. Test: Task 5 `test_group_head_errors_only_when_enabled`.
4. A project with no pockets whose default pocket head is empty still plans. Test: Task 5 `test_empty_pocket_head_without_pockets_plans`.
5. Load an old project, save it, load again: no notes, same programs, same bit ids. Test: Task 6 `test_migration_then_save_is_stable`.

---

### Task 1: Baseline of a consistent project

Proof that output does not change: capture today's programs for a consistent old-form project before anything changes.

**Files:**
- Create: `tests/data/tool_table/consistent/project.json`, `tests/data/tool_table/consistent/programs.json`
- Create: `tests/test_nesting_tool_baseline.py`

**Interfaces:**
- Produces: `tests/test_nesting_tool_baseline.py::BaselineTests.test_consistent_project_programs_unchanged`, used as a gate by every later task.

- [ ] **Step 1: Write the fixture `project.json`** (old form, no `tools`): all 12 `plates/*.dxf` by name, qty 1 each, `klas_1-1` qty 2; settings = old defaults except `pockets.depth_per_pass` 9 (so router and pocket default agree on T66), `drill_fix` tool 1 diameter 6 feed 1, `drill_screw` tool 2 diameter 3 feed 1. `pockets` overrides: the first group (by id, `G1`) `{"depth": 6}`, the second `{"enabled": false}`; get the keys by running `find_groups` over the 12 plates read with `read_dxf`.
- [ ] **Step 2: Capture `programs.json`** = `{program name: CNC90 text}` with the current code: copy the plates to a temp `shapes/`, copy the fixture, `p = Project(tmp)`, `settings, _, programs, _, _ = p.compute(p.snapshot())`, text = `BACKENDS['cnc90'](prog, settings)`. Do this with a one-off command, not a script in the repo.
- [ ] **Step 3: Write the test** `test_consistent_project_programs_unchanged`: same steps through `Project`, assert the set of names and each text equal `programs.json` (`assertEqual` per name, `msg=name`). Also `test_fixture_is_old_form`: the fixture has no `tools` key.
- [ ] **Step 4: Run** `python -m unittest discover -s tests -p 'test_nesting_tool_baseline.py' -v` → 2 tests OK; full suite → 471 OK.
- [ ] **Step 5: Commit** `git add tests/data/tool_table tests/test_nesting_tool_baseline.py && git commit -m "Pin the programs of a consistent project before the tool table"`

### Task 2: `nesting/tools.py`: heads, bits, table

**Files:**
- Create: `nesting/tools.py`
- Test: `tests/test_nesting_tools.py`

**Interfaces:**
- Produces:
  - `Head(number: int, label: str, allows: tuple[str, ...])`; `HEADS: dict[int, Head]` (labels: "big spindle" for T65/T66, "drill cross, vertical", "drill cross, horizontal", "blade/drill in X", "blade/drill in Y").
  - `ROUTER_HEADS = (65, 66)`, `DRILL_HEADS = tuple(range(1, 31))` (R1).
  - `BIT_TYPES = ('router', 'drill', 'blade')`; `REQUIRED: dict[str, tuple[str, ...]]`, `OPTIONAL: dict[str, tuple[str, ...]]` per the Global Constraints.
  - `@dataclass Bit(id: str, name: str, type: str, diameter, spindle_rpm=None, plunge_feed=None, cut_feed=None, depth_per_pass=None, stepover_pct=None)`.
  - `@dataclass ToolTable(bits: list[Bit], heads: dict[int, str])` (head number -> bit id; an empty head is absent) with:
    `default() -> ToolTable` (R4); `from_dict(d) -> ToolTable` (lenient on values; `SettingsError('tools', ...)`, `('tools.bits', ...)`, `('tools.heads', ...)` on wrong structure; JSON head keys `"T66"`, value bit id or `null`; fields a type does not use are dropped); `to_dict() -> dict` (applicable fields only, optional ones only when set; heads as `{"T66": "b1"}` sorted by number); `bit(id) -> Bit | None`; `bit_in(head) -> Bit | None`; `heads_of(bit_id) -> list[int]`; `new_id() -> str` (`b<n>`, first free); `label(head) -> str` (`"T66 Router 8"`, `"T66 (empty)"`); `validate() -> None` raising `SettingsError`; `resolve(head: int, who: str, field: str, kind: str) -> Bit` with `kind` `'router'` or `'drill'`.
  - `class HeadError(SettingsError)` raised by `resolve`.
- Consumes: `SettingsError`, `STEPOVER_MESSAGE`, `MIN_STEPOVER_PCT` from `nesting/settings.py` (import from there; `settings.py` imports `tools.py` only inside functions or `tools.py` defines them and `settings.py` re-exports: pick one, no import cycle).

- [ ] **Step 1: Write the failing tests** (`tests/test_nesting_tools.py`):
  - `test_heads_list`: `sorted(HEADS) == [1..30, 53, 56, 60, 61, 65, 66]`; `HEADS[66].allows == ('router',)`, `HEADS[1].allows == ('drill',)`, `HEADS[60].allows == ('drill', 'blade')`.
  - `test_default_table`: bits `b1`, `b2`, `b3` with the R4 numbers; `heads == {66: 'b1', 1: 'b2', 2: 'b3'}`; `b2.spindle_rpm is None`; `default().validate()` passes.
  - `test_roundtrip`: `ToolTable.from_dict(t.to_dict()) == t`; `to_dict()['heads'] == {'T1': 'b2', 'T2': 'b3', 'T66': 'b1'}`; a drill bit's dict has no `cut_feed`, `depth_per_pass`, `stepover_pct` keys.
  - `test_bad_tables_are_refused_naming_the_head` (Review Focus 1): each case and its `SettingsError.field`: head `T66` -> `b9` missing: `tools.heads.T66` and message contains `b9`; router bit in `T1`: `tools.heads.T1`, message contains `T1` and `router`; `"T70": "b1"`: `tools.heads.T70`, "not a machine head"; `bits: {}`: `tools.bits`; `tools: []`: `tools`; two bits with id `b1`: `tools.bits`.
  - `test_bit_values_checked`: router bit diameter 0 -> `tools.bits.b1.diameter`; stepover 5 -> `tools.bits.b1.stepover_pct` with `STEPOVER_MESSAGE`; drill without plunge_feed -> `tools.bits.b2.plunge_feed`; drill `spindle_rpm` None is fine, 0 is refused; name `''` -> `tools.bits.b1.name`; type `'saw'` -> `tools.bits.b1.type`; `True` or `float('nan')` as a number refused.
  - `test_resolve`: `resolve(66, 'router', 'router.tool', 'router')` returns `b1`; empty head T65 -> `HeadError` with field `router.tool`, message `'router: head T65 holds no bit'`; `resolve(1, 'router', 'router.tool', 'router')` -> message contains `T1` and "router uses T65 or T66"; `resolve(53, 'fixing drill', 'drill_fix.tool', 'drill')` -> message contains "programs do not use T53"; `resolve(40, ...)` -> "T40 is not a machine head".
  - `test_label_and_used_in`: `label(66) == 'T66 Router 8'`, `label(65) == 'T65 (empty)'`; `heads_of('b1') == [66]`; `new_id() == 'b4'`.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_nesting_tools.py'` → fails (no module).
- [ ] **Step 3: Implement `nesting/tools.py`.** Bit id: `[A-Za-z0-9_-]{1,20}`; name 1 to 40 characters after strip. `resolve` order of checks: not in `HEADS` -> not a machine head; not in the operation's allowed heads -> "programs do not use T53" (horizontal/X/Y) or "the router uses T65 or T66" / "drills use T1 to T30"; empty -> "holds no bit"; bit type != kind -> "holds drill bit Drill 6; the router needs a router bit". Message prefix is `who + ': '`.
- [ ] **Step 4: Run** the file → OK; full suite → OK.
- [ ] **Step 5: Commit** `git commit -m "Add the tool table: machine heads, bits and their checks"`

### Task 3: Migration from old settings

**Files:**
- Modify: `nesting/tools.py`
- Test: `tests/test_nesting_tools.py`

**Interfaces:**
- Produces: `migrate(settings: dict, pockets) -> tuple[ToolTable, list[str], list[tuple[str, str, object]]]` — the table, one note per merged or unplaced head, and the ignored old override values as `(group key, field, value)` (the server words those lines, it knows the group ids). `OBSOLETE_GROUP_FIELDS = ('diameter', 'depth_per_pass', 'plunge_feed', 'cut_feed', 'spindle_rpm', 'stepover_pct')`.
- Consumes: Task 2.

- [ ] **Step 1: Write the failing tests:**
  - `test_old_defaults_give_the_default_table`: `migrate({}, {})[0] == ToolTable.default()`; the notes list one line for T66 containing `depth per pass`, `9` and `4` (R4).
  - `test_real_project_shape`: router T66 d8 rpm 18000 plunge 1 cut 2 dpp 9; pockets T66 d8 cut 3 dpp 4 stepover 40; both drills T10 d5 feed 1 → bits: `Router 8` (cut 2, dpp 9, stepover 40) in T66, one `Drill 5` in T10, nothing in T1/T2; exactly one note, for T66, naming cut feed 2 taken / 3 dropped and depth per pass 9 taken / 4 dropped.
  - `test_pocket_default_on_its_own_head`: pockets.tool 65 d18 → a second router bit `Router 18` in T65 with the pocket's numbers; no note.
  - `test_two_drills_one_head_disagree`: fix T3 d6, screw T3 d4 → one bit `Drill 6` in T3, a note naming T3, diameter 6 taken, 4 dropped.
  - `test_unusable_head_is_not_placed` (R3): pockets.tool 7 → a `Router 8`-like bit exists but `bit_in(7)` is None and a note says the pocket default's head T7 cannot hold a router bit; drill_fix.tool 40 → its bit unplaced, note names T40.
  - `test_ignored_overrides`: `pockets = {'k1': {'diameter': 12, 'depth': 6, 'tool': 65}}` → ignored == `[('k1', 'diameter', 12)]`; `depth` and `tool` are not reported; a non-dict override is skipped, no crash.
  - `test_migration_is_deterministic`: same input twice → equal outputs.
- [ ] **Step 2: Run** → fails.
- [ ] **Step 3: Implement `migrate`.** Read the old values from the raw dict with the old defaults for missing keys (old defaults are the R4 numbers plus pocket dpp 4, stepover 40, pocket feeds 1/3, rpm 18000). Candidates in R3 order; one bit per head; merge rules R3; bit names `Router {d:g}` / `Drill {d:g}`; ids `b1..` in creation order. Non-numeric old values: take the default and say so in a note (no crash).
- [ ] **Step 4: Run** → OK; full suite OK.
- [ ] **Step 5: Commit** `git commit -m "Build a tool table from the settings of an old project"`

### Task 4: Settings carry the table; router and drills read their bits

Switches the router and the drills. Pocket numbers still come from `Pockets` until Task 5.

**Files:**
- Modify: `nesting/settings.py`, `nesting/layout.py:163-177`, `nesting/program.py` (`_contour`, `_finish`, `_pass_ops`, `blank_programs`, `tool_diameter_conflict`), `nesting/preview.py` (`_drill_tools`), `nesting/server.py` (`validate`)
- Test: `tests/test_nesting_settings.py`, `tests/helpers.py`, and every test reading `router.diameter/spindle_rpm/plunge_feed/cut_feed/depth_per_pass`, `drill_fix.diameter/feed`, `drill_screw.diameter/feed` (program, layout, yframe, preview, output, server, cnc90 tests)

**Interfaces:**
- Consumes: `ToolTable`, `HeadError`, `ROUTER_HEADS`, `DRILL_HEADS` (Task 2).
- Produces:
  - `Settings.tools: ToolTable` (default `ToolTable.default()`); `Settings.from_dict(d: dict, tools: ToolTable | None = None)` (None → default table); `to_dict()` has no `tools` key.
  - Properties `Settings.router_bit`, `fix_bit`, `screw_bit` → `Bit` via `tools.resolve` with `who` `'router'`, `'fixing drill'`, `'screw drill'` and fields `router.tool`, `drill_fix.tool`, `drill_screw.tool`.
  - `Settings.gap` = `router_bit.diameter + router.clearance`.
  - `Settings.validate()` also runs `tools.validate()`, resolves the three bits (raising their `HeadError`) and checks `pockets.tool in ROUTER_HEADS` (`SettingsError('pockets.tool', 'pocket default: head T7 ... the router uses T65 or T66')`, R2).
  - Test helper `put_bit(settings, head: int, **numbers) -> Bit` in `tests/helpers.py`: a copy of the bit now in `head` (or of the default bit of the head's first allowed type), with `numbers` applied, a new id and name `f'{Type} {diameter:g}'`, placed in `head` only.
- Old fields are removed from `Router`, `DrillFix`, `DrillScrew`; `Pockets` keeps its fields in this task.

- [ ] **Step 1: Write the failing tests** in `tests/test_nesting_settings.py`:
  - `test_settings_carry_the_default_table`: `Settings().router_bit.diameter == 8`, `.depth_per_pass == 9`, `fix_bit.diameter == 6`, `screw_bit.diameter == 3`; `'tools' not in Settings().to_dict()`; `'diameter' not in Settings().to_dict()['router']`.
  - `test_old_router_fields_are_ignored`: `Settings.from_dict({'router': {'diameter': 12, 'tool': 66}}).router_bit.diameter == 8` (the table, not the old field).
  - `test_router_head_errors`: `router.tool = 65` → validate raises field `router.tool`, message `router: head T65 holds no bit`; `drill_fix.tool = 60` → field `drill_fix.tool`, "programs do not use T60"; `pockets.tool = 1` → field `pockets.tool`.
  - `test_gap_follows_the_bit`: `put_bit(s, 66, diameter=12)` → `s.gap == 16`.
  Rewrite the existing tests that set or read the removed router and drill fields to `put_bit` / `s.router_bit...`; `test_rejected` entries for removed fields move to `tests/test_nesting_tools.py::test_bit_values_checked`.
- [ ] **Step 2: Run** the settings tests → fail.
- [ ] **Step 3: Implement.** `_build` skips the `tools` field. Remove the moved fields from the `positive` list. Consumers: `layout.py` screw/fix hole diameter from `screw_bit`/`fix_bit`, clearance rule `router_bit.diameter`; `program.py` `_contour` radius, `_finish` default radius, `_pass_ops` depth per pass, cut program rpm/feeds from `router_bit`, drill program feed record `fix_bit.plunge_feed`, `DrillOp.diameter` from the bits; `preview._drill_tools` diameter and `feed` (= `plunge_feed`) from the bits; `tool_diameter_conflict` reads the router and drill diameters from the bits (it goes away in Task 5).
- [ ] **Step 4: Run** the full suite → OK, including Task 1's baseline (its project migrates in Task 6; until then `Project` still builds settings from `settings` only, so the baseline uses the default table, which matches its numbers).
- [ ] **Step 5: Commit** `git commit -m "Read router and drill numbers from the bit in their head"`

### Task 5: Pocket groups name a head

**Files:**
- Modify: `nesting/settings.py` (`Pockets`), `nesting/pockets.py` (`GroupSettings`, `effective`, `_coerce`), `nesting/program.py` (`_pocket_program`, remove `tool_diameter_conflict`, `plan_programs`), `nesting/preview.py` (`pocket_groups_data`), `nesting/server.py` (`pocket_override_error`, `check_pockets`, `save`, `_pocket_groups`, `_circle_warnings`)
- Test: `tests/test_nesting_pockets.py`, `tests/test_nesting_program.py`, `tests/test_nesting_preview.py`, `tests/test_nesting_server.py`, `tests/test_nesting_cnc90.py:273`

**Interfaces:**
- Consumes: Task 4 (`Settings.tools`, `resolve`, `HeadError`).
- Produces:
  - `Pockets` fields: `min_circle_diameter, min_floor, tool, depth, direction`.
  - `@dataclass GroupSettings(enabled: bool, tool: int, depth: float, direction: str, bit: Bit | None)` with read-only properties `diameter, depth_per_pass, plunge_feed, cut_feed, spindle_rpm, stepover_pct` from `bit`.
  - `effective(group_key: str, overrides: dict, settings: Settings) -> GroupSettings`: overrides read only `enabled`, `tool`, `depth`, `direction` (others ignored); an enabled group resolves its head with `who='pocket group'`… raising `HeadError`; a switched-off group gets the head's bit when it resolves, else `bit=None`, never an error. Callers prefix the group id as today.
  - `program.check_pocket_heads(settings, overrides, groups, shapes) -> tuple[str, str] | None`: (message, field) for the first enabled group with a pocket on `shapes` whose head does not resolve; field `pockets.<id>.tool` when the group has its own `tool`, else `pockets.tool`; message `pocket group G2: head T65 holds no bit`. Replaces `tool_diameter_conflict` in `plan_programs` (as `ProgramError`) and in `Project.save` (as 400).
- The "one tool number two diameters" tests are removed (the rule is gone: one head holds one bit).

- [ ] **Step 1: Write the failing tests:**
  - `test_pockets.py::test_effective_reads_the_bit`: default settings → `gs.diameter == 8`, `gs.depth_per_pass == 9`, `gs.stepover_pct == 40`; override `{'tool': 65}` with `put_bit(s, 65, diameter=18)` → `gs.diameter == 18`; override `{'diameter': 12, 'stepover_pct': 50}` → ignored, `gs.diameter == 8`.
  - `test_program.py::test_group_head_errors_only_when_enabled` (Review Focus 3): plates with a pocket, override `{'tool': 65}`, T65 empty → `plan_programs` raises `ProgramError` containing `G1` and `T65`; with `{'tool': 65, 'enabled': False}` → plans, no `P` program for that group.
  - `test_program.py::test_empty_pocket_head_without_pockets_plans` (Review Focus 4): a rectangle shape without pockets, `s.tools.heads.pop(66)`, `router.tool = 65` with `put_bit(s, 65, diameter=8)`, `pockets.tool` 66 → `validate()` passes and `plan_programs` gives D and C programs.
  - `test_program.py::test_pocket_ops_carry_the_bit`: `put_bit(s, 65, diameter=6, spindle_rpm=16000, plunge_feed=0.5, cut_feed=2)`, `pockets.tool = 65` → every pocket op has `(65, 16000, 0.5, 2)`, ring offset uses 6 mm.
  - `test_server.py::test_save_refuses_empty_group_head`: PUT with `pockets = {key: {'tool': 65}}` and T65 empty → 400, field `pockets.G1.tool`, message contains `T65`.
  Rewrite the existing pocket tests that set `s.pockets.diameter/depth_per_pass/...` to `put_bit`; pass-count expectations on default settings change from 4 mm to 9 mm passes (R4).
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement.** `pocket_override_error` checks only the four kept fields (obsolete ones ignored, as unknown fields are). `pocket_groups_data` emits the same keys as today plus `bit` (`{'id', 'name'}` or None) and `head_label` (`settings.tools.label(tool)`); on an error the group is switched off with `error` and numbers from no bit (`None`). Server `_circle_warnings` and `_pocket_groups` call the new `effective(key, pockets, settings)`.
- [ ] **Step 4: Run** full suite → OK, baseline included.
- [ ] **Step 5: Commit** `git commit -m "Pocket groups name a head; speeds and feeds come from its bit"`

### Task 6: `project.json` stores the table; old projects migrate on load

**Files:**
- Modify: `nesting/server.py` (`Project._stored`, `_merged`, `_project`, `save`, `compute`, `generate`/`_write`), `nesting/output.py` (`PROJECT.json` gets `tools`)
- Test: `tests/test_nesting_server.py`, `tests/test_nesting_output.py`, `tests/test_nesting_tool_baseline.py`

**Interfaces:**
- Consumes: `migrate`, `OBSOLETE_GROUP_FIELDS` (Task 3), `ToolTable.from_dict/to_dict` (Task 2), `Settings.from_dict(d, tools)` (Task 4).
- Produces:
  - `_stored()` returns also `'tools'` (a dict, `ToolTable.to_dict()` form) and `'tools_notes'` (list of str): from `data['tools']` when present (notes `[]`), else `migrate(raw settings, raw pockets)` (the raw dict, before `Settings.from_dict` drops old fields). No file: default table, no notes.
  - `GET /api/project` body adds `tools`, `tools_notes`, `heads` (`[{'number': 66, 'label': 'big spindle', 'allows': ['router']}, ...]` in head order).
  - Notes for ignored overrides worded in the server: `pocket group G2: old setting cut_feed 2.5 is ignored (speeds and feeds come from the bit in its head)`; for a key matching no group: `a stored pocket setting: old setting ... is ignored ...`.
  - `compute` builds `Settings.from_dict(settings, tools)`; plan problems start with the notes (R6).
  - `save(body)`: `tools = body['tools']` if present else the stored table (R7); `ToolTable.from_dict` + `validate()` errors → 400 with the `SettingsError` field; strips `OBSOLETE_GROUP_FIELDS` from every override (drops an override left empty); writes `{'shapes', 'settings', 'pockets', 'tools'}`.
  - `write_output(..., )` puts `settings.tools.to_dict()` in `PROJECT.json` as `tools`.

- [ ] **Step 1: Write the failing tests** (`test_nesting_server.py`):
  - `test_old_project_migrates_on_load`: write a project.json in the real-project shape of Task 3 → GET project: `tools['heads'] == {'T10': 'b2', 'T66': 'b1'}`, `tools_notes` has the T66 line; plan `problems` contains it; project.json on disk unchanged (no write on load).
  - `test_ignored_override_lines`: old override `{'diameter': 12}` on G1's key → a problem line containing `pocket group G1`, `diameter 12`, `ignored`.
  - `test_migration_then_save_is_stable` (Review Focus 5): old project → GET → PUT the body back → file has `tools`, overrides have no obsolete fields; GET again → `tools_notes == []`, same bit ids; programs text equal before and after.
  - `test_save_without_tools_keeps_the_stored_table` (Review Focus 2): save a table with `put`-style edit (b1 diameter 12), then PUT `{'shapes', 'settings', 'pockets'}` only → GET shows diameter 12.
  - `test_save_refuses_bad_table`: PUT with heads `{'T66': 'b9'}` → 400, field `tools.heads.T66`; PUT with a router bit in `T1` → 400 `tools.heads.T1`; nothing written.
  - `test_output.py::test_project_json_has_tools`: `PROJECT.json['tools'] == settings.tools.to_dict()`.
  - Baseline: `test_consistent_project_programs_unchanged` now goes through migration (no change to the test); add `test_consistent_project_has_no_notes`: its `tools_notes == []`.
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement.** Keep the `upload` path working when project.json is bad (it reads only `settings`).
- [ ] **Step 4: Run** full suite → OK.
- [ ] **Step 5: Commit** `git commit -m "Store the tool table in project.json and migrate old projects on load"`

### Task 7: Show head and bit in the programs table, run sheet and preview

**Files:**
- Modify: `nesting/preview.py` (`_program_entry`, `_drill_tools`), `nesting/output.py` (programs table, drill tools table, pocket table)
- Test: `tests/test_nesting_preview.py`, `tests/test_nesting_output.py`

**Interfaces:**
- Consumes: `ToolTable.label` (Task 2), `pocket_groups_data`'s `head_label` (Task 5).
- Produces: program entries get `tool_labels: list[str]` (one per `tools`, `settings.tools.label(t)`); drill tool rows get `label`; run sheet shows `T66 Router 8` where it showed `T66`, and the drill table note reads "diameter and feed are the bit's, not written to the program: the control uses each tool's own feed; check the bit in the head really has that diameter".

- [ ] **Step 1: Write the failing tests:** `test_preview.py::test_program_entries_name_the_bit`: default settings → cut program `tool_labels == ['T66 Router 8']`, drill `['T1 Drill 6', 'T2 Drill 3']`. `test_output.py::test_runsheet_names_the_bit`: `RUNSHEET.html` contains `T66 Router 8` and `T1 Drill 6`.
- [ ] **Step 2: Run** → fail. **Step 3: Implement.** **Step 4: Run** full suite → OK.
- [ ] **Step 5: Commit** `git commit -m "Name the bit next to the head in the programs and the run sheet"`

### Task 8: The page: Tools page, head pickers, old fields gone

**Files:**
- Modify: `nesting/web/index.html`
- Test: `tests/test_nesting_server.py` (page smoke checks)

**Interfaces:**
- Consumes: `GET /api/project` (`tools`, `heads`, `tools_notes`, `pocket_groups[].head_label`), `PUT /api/project` with `tools`, error fields `tools.bits.<id>.<field>`, `tools.heads.T<n>`, `router.tool`, `drill_fix.tool`, `drill_screw.tool`, `pockets.tool`, `pockets.<G>.tool`.
- Produces (page behaviour):
  - Header switch **Plan | Tools**. Tools shows a full-width section in place of `<main>` with two tables.
  - **Bits**: name, type (select), Ø mm, spindle rpm, plunge m/min, cut m/min, depth/pass mm, stepover %, "in heads" (e.g. `T66`), delete. Cells a type does not use show `—`; optional ones may be left empty. "Add bit" adds a router bit with the R4 router numbers, id `b<n>` first free. Delete of a bit in a head is refused on the page: "Router 8 sits in T66: empty that head first" (the server refuses it too).
  - **Toolheads**: T number, where (label), bit select listing only bits of the allowed types plus "— empty —", "used by" (router / pocket default / pocket group ids / fixing drill / screw drill). T53, T56, T60, T61 rows say "listed only: no program uses this head".
  - Settings panel: Router section = head select (T65, T66, showing `tools.label`), clearance, direction; the preset select and `ROUTER_TOOLS` are removed. Drills = fixing head select (T1 to T30), screw head select, screw depth. Pockets = min circle Ø, min floor, head select, depth, direction. `gapNote` uses the router head's bit diameter.
  - Group card: enabled, head select (first option "default (T66 Router 8)" = no override), depth. `GROUP_FIELDS` loses diameter, depth per pass, feeds, stepover.
  - `tools_notes` lines show in the problems banner with the plan's problems.
  - The `tools` object is sent with every save.
- [ ] **Step 1: Write the failing tests** (`test_nesting_server.py`, page text checks like the existing ones): GET `/` contains `id="toolsPage"`, `id="bitsTable"`, `id="headsTable"`; does not contain `router.spindle_rpm`, `pockets.diameter`, `drill_fix.feed`, `ROUTER_TOOLS`; `GROUP_FIELDS` line has no `diameter`.
- [ ] **Step 2: Run** → fail. **Step 3: Implement** within the existing look (same CSS variables, `.field`, table styles). `showFieldError` maps `tools.bits.<id>.<field>` and `tools.heads.T<n>` to the inputs (`data-k`) and switches to the Tools page when the error is there.
- [ ] **Step 4: Run** full suite → OK. Manual check in a browser (start the server on a temp copy of a project): add a bit, put it in T65, point the router at T65, see the cut program's `S` and `F` change; try deleting a bit in use; make a head error and see the field marked. Note what was and was not clicked in the report.
- [ ] **Step 5: Commit** `git commit -m "Add the Tools page and pick heads in the settings and pocket groups"`

### Task 9: Docs

**Files:**
- Modify: `nesting/README.md` (Settings table, Pockets section, new "Tools" section), `docs/superpowers/specs/2026-11-13-tool-table-design.md` (status line + "As built": rulings R1 to R7 and any made during the build)

- [ ] **Step 1:** README "Tools": heads list and allowed types, bit fields per type, where stored (`project.json` `tools`), migration (R3, R4 consequence for pocket passes, R6), errors, "nothing verified on the machine; the numbers are placeholders for the shop to measure". Remove the removed fields from the Settings and Pockets tables; remove the "one tool number has one diameter" text.
- [ ] **Step 2:** Check: `grep -n "router.diameter\|pockets.diameter\|drill_fix.feed\|one tool number" nesting/README.md` → only in the migration paragraph.
- [ ] **Step 3:** Full suite → OK; `git diff windows-start -- nesting/backends/` → empty.
- [ ] **Step 4: Commit** `git commit -m "Document the tool table"`
