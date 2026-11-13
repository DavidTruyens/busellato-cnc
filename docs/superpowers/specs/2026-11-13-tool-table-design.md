# Tool table for the nesting tool — design

Date: 2026-11-13
Status: design, not built. Builds on the nesting tool with pockets (`nesting/`, PR #8 unmerged at the time of writing; this work starts from that branch).

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
