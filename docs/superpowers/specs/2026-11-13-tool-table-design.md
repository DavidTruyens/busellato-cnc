# Tool table for the nesting tool — design

Date: 2026-11-13
Status: built on branch tool-table, not yet run on the machine (see "As built"). Builds on the nesting tool with pockets (`nesting/`, PR #8 unmerged at the time of writing; this work starts from that branch).

## Goal

One place where the cutting bits are defined (type, diameter, spindle speed, feeds), and a second place that says which bit sits in which machine toolhead (T number). Routers, drills and pocket groups then only name a toolhead. Change a bit once and every program follows.

Why: the same tool number (T66) currently carries its diameter, speed and feeds in three places (router settings, pocket defaults, per-group overrides) and they disagree (12 mm vs 8 mm in one real project). Changing a bit means hunting for every copy, and the tool refuses to plan while the copies disagree.

## What exists (build on it)

- `nesting/settings.py`: `Router` (tool, diameter, spindle_rpm, plunge_feed, cut_feed, depth_per_pass, clearance, depth settings), `DrillFix` (tool, diameter, feed), `DrillScrew` (tool, diameter, depth, feed), `Pockets` (tool, diameter, depth, depth_per_pass, plunge_feed, cut_feed, spindle_rpm, stepover_pct, direction, min_circle_diameter, min_floor). Cross-field checks, including "one tool number must have one diameter".
- Per pocket group overrides (project.json `pockets`, keyed by group key): tool, diameter, depth, depth_per_pass, feeds, spindle_rpm, stepover_pct, direction, enabled.
- The program model carries tool numbers and, per operation, diameter, rpm and feeds; the CNC90 emitter writes them. Golden programs must stay byte for byte identical.
- The page (`nesting/web/index.html`) has a Settings panel and the pocket group cards; the run sheet, preview and `PROJECT.json` list tools.
- Tool numbers known from the machine (tool table `TESTINE.PAR` on the H03 backup, names only, numeric fields not decoded): T65 router D=18, T66 router D=8, T1 to T30 vertical drills, T53 and T56 horizontal drills, T60 blade X, T61 blade Y. The machine's own values are out of date (the real T66 bit is 12 mm).

## Decisions (the user's, unless marked "my call")

1. **Two tables on a Tools page**, next to the existing Settings (layout A of the mockup).
   - **Bits** (like a Fusion tool library): name, type, diameter, spindle speed, plunge feed, cut feed, depth per pass, stepover. Type is `router`, `drill` or `blade`. The columns that apply depend on the type (my call: drill has diameter, spindle speed and plunge feed; blade has diameter, spindle speed and cut feed; router has all of them). A bit shows where it is used (the heads it sits in).
   - **Toolheads**: the machine's T numbers, each with a fixed label of where it is (big spindle, drill cross vertical, drill cross horizontal, blade/drill in X, blade/drill in Y). Each head holds one bit or nothing. A bit may sit in several heads.
2. **Programs name a toolhead only.** The router, the fixing drill, the screw drill and each pocket group choose a T number. Diameter, speed and feeds, depth per pass and stepover come from the bit in that head. Depth, direction and enabled stay with the operation or the pocket group.
3. **No per-group overrides** of speed or feed. Pocket groups may still pick another head (so another bit), and a depth. The override fields for diameter, rpm, feeds, depth per pass and stepover are removed.
4. **Heads in use:** the two big spindles (T65, T66), the vertical drills of the cross (T1 to T30) and the horizontal drills (T53, T56) are listed. The X and Y heads (T60, T61) are one head each; a bit on either side is treated as the same. The shop uses everything except the X and Y heads for now, so no program uses T60 or T61; they are listed and can hold a bit, nothing more.
5. **Layout and checks unchanged otherwise:** only where the numbers come from changes.

## My calls (change any)

- **Where it is stored:** `project.json` of the project folder, a new `tools` key with `bits` (list; each has an id, name, type and its numbers) and `heads` (T number to bit id). Each PC with its own project has its own table. A shared table for all machines is not part of this.
- **First start (migration):** a project without `tools` gets one built from its current settings: the router becomes a bit in its head, the fixing and screw drills become bits in their heads, the pocket default sits in its head. If two settings name the same head with different numbers, the router's wins, and the page shows one line saying what was merged. Old per-group override fields are ignored (a project that has them still loads). The first save writes the new form.
- **Settings that stay:** `router.tool`, `drill_fix.tool`, `drill_screw.tool`, `pockets.tool` (as head numbers), clearance and depth settings, `pockets.min_circle_diameter`, `pockets.min_floor`, `pockets.direction`, the group `depth`. The old diameter, speed, feed, depth-per-pass and stepover fields disappear from Settings and from the pocket group cards.
- **Errors, each naming the operation and the head:** a head with no bit; a bit of the wrong type for the operation (a drill bit used by the router, a router bit used by a drill, a blade used by anything); a head number not in the list. The "one tool number two diameters" error disappears, because one head holds one bit. A pocket narrower than its bit stays an error as today.
- **Deleting a bit** that sits in a head is refused with the head numbers listed; empty its heads first.
- **Heads list:** fixed in code (T65, T66, T1 to T30, T53, T56, T60, T61), taken from `TESTINE.PAR` names; adding another number means a code change. Not verified on the machine.
- **Programs and the page show** the head and its bit (for example "T66 Router 12") in the run sheet, the programs table, `PROJECT.json` and the pocket group cards.
- **Seed values** on a project with no settings at all: the current placeholder defaults (router T66, 18000 rpm, plunge 1, cut 3 m/min; drills as now), all marked as placeholders until measured.

## More calls, from the builder check (mine; change any)

- **Drill bit fields:** a drill's one feed is the bit's plunge feed, which replaces `drill_fix.feed` and `drill_screw.feed`. The drill spindle speed is stored on the bit and shown, but drill programs do not write it today and the emitter does not change, so it stays unwritten. Depth stays on the operation (`drill_screw.depth` and the fixing depth).
- **"Byte for byte" covers projects whose settings agree** (the golden and existing tests). A project whose settings disagreed about one head could not be planned before (the old diameter error), so it has no output to keep. For those the migration takes the router's numbers for a shared head, and the page shows one line per merged head saying what was taken and what was dropped (not silent).
- **Which depth per pass:** the router's `depth_per_pass` moves to the router bit and is used for both the contour cut and pockets; there is no separate pocket value. Depths (`router` cut depth rules, pocket depth, screw depth) stay on the operation.
- **Heads restrict bit types:** T65 and T66 take router bits, T1 to T30, T53 and T56 take drill bits, T60 and T61 take drill or blade bits. The bit picker of a head lists only the allowed types, and a saved file that breaks this is refused with the head named.
- **Old per-group overrides** (diameter, rpm, feeds, depth per pass, stepover) are not applied. Loading such a project shows one line per group and field saying it was ignored; nothing is created from them.
- **Saving:** the page saves `tools` together with the settings through the existing project save; the builder chooses the exact API as long as a partial save cannot drop the `tools` key.

## Constraints

- Output must not change for an unchanged project: same programs, byte for byte, as with the settings today (golden tests and the existing tests keep passing; tests that read the old settings fields are rewritten to the new ones).
- The preview and the program use the same numbers (existing rule). The CNC90 emitter does not change.
- Nothing here has run on the machine; the real bit diameters, speeds and feeds are the shop's to enter and measure.
- The repo is public: nothing confidential in files, commit messages or the PR text (the shop operator is "the shop operator").

## Non-goals

- Per-group or per-operation overrides of speed and feed.
- Programs that use the horizontal drills or the X and Y heads (listed only).
- Reading, writing or syncing the machine's `TESTINE.PAR`; importing a Fusion tool library; tool life or wear counters.
- Several bits per head or automatic tool selection.

## Anti-goals

- A program written with a diameter, speed or feed from a bit that is not the one in the head the program names.
- A silent default when a head is empty or wrong: it must be an error that names the head.
- The tool refusing to plan because of an old project file's obsolete fields.

## Left to the builder

- The exact JSON shape, the page layout within the existing look, validation messages, and how the pocket cutter-ring code gets its diameter and stepover from the bit.
- Which `Settings` fields remain on the Python side (the settings module may become the place that resolves a head to a bit).
- The migration code and the test data for old project files.

## Open items (need the machine or the user)

1. The real bits, diameters, speeds and feeds; which heads hold what.
2. Whether `TESTINE.PAR` has per-head speed and feed fields that should replace the placeholders (not decoded).
3. Whether the machine accepts the head numbers chosen for each operation (as before, not verified).

## As built

Differences from, and decisions beyond, the design text above (the code and `nesting/README.md` are the reference). Nothing here has run on the machine: the programs are format-checked and tested, and the bit numbers are placeholders for the shop to measure.

- **Module:** `nesting/tools.py` holds the fixed heads, `Bit`, `ToolTable` (load, save, check) and the migration. It also owns `SettingsError` and the stepover limits; `settings.py` re-exports them. `Settings` carries a `tools` table and resolves each operation's head to its bit (`router_bit`, `fix_bit`, `screw_bit`); pocket groups resolve theirs in `pockets.effective`. The CNC90 emitter and `nesting/backends/` are unchanged; the golden programs ZZT1, ZZT1AD and ZZT2A are still byte for byte identical.
- **Programs use only some heads (R1):** router and pockets use T65 or T66, the fixing and screw drills use T1 to T30. T53, T56, T60 and T61 are listed and can hold a bit; an operation naming one is refused ("programs do not use T53").
- **Pocket default head (R2):** `pockets.tool` must be T65 or T66 (checked with the settings). That it holds a router bit is checked only for a switched-on pocket group with a pocket on the plan, so a project with no pockets plans with an empty default head. A switched-off group on an empty head is not an error.
- **Migration order (R3):** per head, router, pocket default, fixing drill, screw drill; the first one wins every number that differs, and one note per head says what was taken and what was dropped. A migrated operation whose head cannot hold its kind of bit (not in the list, or the wrong kind, for example an old `pockets.tool` 7) gets its bit created but not placed, plus a note; planning then stops with the head error. The old router had no stepover: it takes the pocket default's only when they share a head.
- **Seed table (R4):** the default table equals the migration of the old default settings: `b1` "Router 8" (router, 8 mm, 18000 rpm, plunge 1, cut 3, depth per pass 9, stepover 40) in T66, `b2` "Drill 6" (drill, 6 mm, plunge 1) in T1, `b3` "Drill 3" (drill, 3 mm, plunge 1) in T2. The old defaults disagreed on T66's depth per pass (router 9, pockets 4); the router's 9 is taken, so pocket programs of a project on the old default settings now cut in 9 mm passes, not 4. This is the one place where output of an old project changes.
- **Optional fields (R5):** a drill's or blade's spindle speed (and a blade's cut feed) is optional and seeded empty; no program writes a drill's spindle speed.
- **Notes (R6):** migration notes are shown in the plan's problem list (first) and returned by `GET /api/project` as `tools_notes`, with one line per old per-group override field found ("pocket group G1: old setting diameter 12 is ignored ..."). Nothing is written on load. The first save writes the new form, strips the obsolete per-group fields (a group left with no fields is dropped) and the notes disappear. Obsolete fields hand-added to a project already in the new form are ignored without a note until the next save.
- **Save without `tools` (R7):** a `PUT /api/project` without a `tools` key keeps the stored table (migrated for an old project), never resets to the defaults. When `project.json` cannot be read, such a save is refused with a 400 on field `tools` ("project.json cannot be read (...), so its tool table is unknown; save with a tool table").
- **Bad stored table:** `GET /api/project` returns the table as stored, never replaced by a default, with `tools_error` (`field`, `message`) and every pocket group marked off with the error. The plan stops with the same error. A hand-edited table is refused with the head or bit named: a head naming a missing bit, a bit of a type the head does not take, an unknown head such as `T70`, `bits` not a list, an unknown bit type, duplicate bit ids. The page sends `tools` with every save, so a save writes the table shown on the Tools page; when the stored table cannot be shown it offers "Start an empty tool table".
- **Bit checks:** id 1 to 20 letters, digits, `-` or `_`; name 1 to 40 characters; every number greater than 0; router `stepover_pct` from 10 to 100 (still capped at 70 when used). A head whose bit is missing or of the wrong type is a `HeadError` of the form "<operation>: head T66 holds no bit" (the pocket group error names the group, for example "pocket group G1: head T65 holds no bit").
- **Page:** a Tools page next to Plan with the bits table (add, edit, delete; type changes reset the numbers to that type's seeds) and the heads table (the bit picker offers the head's allowed types; "used by" names the operations that use the head, and heads no program uses say "listed only"). Deleting a bit that sits in a head is refused with the head numbers listed. The Settings and the pocket group rows pick a head (labelled with its bit, "T66 Router 8"); the pocket group rows keep only enabled, head and depth. The run sheet, programs table, `PROJECT.json` (which also holds the table) and the Cut view show the head with its bit. The page was checked with a scripted headless browser, not by hand.
- **Removed:** `router.diameter`, `spindle_rpm`, `plunge_feed`, `cut_feed`, `depth_per_pass`; `drill_fix.diameter`, `feed`; `drill_screw.diameter`, `feed`; `pockets.diameter`, `depth_per_pass`, `plunge_feed`, `cut_feed`, `spindle_rpm`, `stepover_pct`; and the same per-group override fields. The "one tool number has one diameter" error is gone. Unknown old fields in a saved settings object are ignored.
- **Pocket group head check on save:** saving checks that every switched-on group with a pocket on a placed shape has a router bit in its head.
