# Part H bug report — timeline colors + dollar bar (2026-07-12)

## ✅ ALL THREE FIXED + regression sweep passed (2026-07-12, headless)
- BUG 1: `_is_late_or_delayed` → `_is_late` (pure `status!=Completed and end<today`;
  baseline comparison deleted). Palette restored: `C_PROGRESS #FFB300`,
  `C_NOT_STARTED #64B5F6`. Legend back to "late". Verified: Aluminum-coil repro
  (`end=2027-02-01`, slipped baseline) now colors amber, not red; a task with
  `end<today` still red.
- BUG 2: recursive parent branch removed from `_status_color` (leaves only);
  group boxes reverted to `C_BOX`/`C_BOX_FILL`, collapsed bars to `C_SUMMARY`;
  `C_WAITING` and its legend/entry removed (both the QLabel legend and the export
  legend). Verified: overdue leaf in two nested groups → parent not red, boxes
  neutral, only the leaf red.
- BUG 3: added `self.timeline.refresh()` after the initial `load_project` in
  `ProjectWidget.__init__` (the missing wake-up); the toggle + `load_snapshot`
  refreshes were already present. Verified: constructing a VAVE ProjectWidget
  shows the $ bar with totals `(0, 28000)`; toggling VAVE off hides it, on shows.
- Sweep: #1 VAVE-off pre-Part-H look ✅ · #2 real .vpmt boots/renders/exports ✅
  · #3 slips export gating (563 px differ between off/on export) ✅.
- Note: for a *delayed* task the gray ghost is mostly hidden behind the taller
  real bar (per the plan's "drawn under"); the red `+Nd` label carries the slip.
  Not one of the 3 bugs — flagged for the user in case a visible baseline track
  is wanted.


**Audience:** the implementing LLM. Read `Critical md files\IMPLEMENTATION_METHODOLOGY.md`
and `DEBUGGING_METHODOLOGY.md` first. All three bugs below were REPRODUCED
headlessly against the live code in THIS folder (`ui/timeline_pane.py`,
mtime 2026-07-12 07:40) — reproduction evidence included. Fix in the order
given; each fix has its own acceptance check.

**Scope authority:** `TRACKER_PART_H_TIMELINE_SCOPE.md`. Two of these bugs are
scope violations, not just defects — the scope text wins over any "improvement".

---

## BUG 1 — Red now leaks private slip data (HIGH, house-rule violation)

**User report:** "Why is the Aluminum coil bar red?" (its end date is Feb 2027,
months in the future).

**Root cause:** `_is_late_or_delayed()` (timeline_pane.py ~line 82) returns
True when `int(node.duration) > int(node.baseline_duration)` — so any task
that EVER slipped its baseline paints `C_OVERDUE` red forever, regardless of
its end date. The legend was relabeled "late/delayed" to match.

**Reproduction (offscreen):** task with `end_date="2027-02-01"`,
`status="In Progress"`, `baseline_duration=10` →
`_is_late_or_delayed(...) == True`, `_status_color(...) == C_OVERDUE`.

**Why it must change:** house rule #3 (IMPLEMENTATION_METHODOLOGY Rule 2):
slip information is OPT-IN behind the Slips checkbox and must never show by
default — including through colors. Red must mean exactly one thing: past its
end date and not Completed.

**Fix:**
- `_is_late_or_delayed` → restore to the pure late check
  (`status != "Completed" and end < today`); delete the baseline comparison
  (rename back to `_is_late` for honesty).
- Slip visibility stays where the scope put it: H3 ghost bars +
  `revision_trail()` tooltips, only while `show_slips` is on.
- Legend text back to "late".

**Accept:** the repro task colors as In-Progress (not red); a task with
`end < today` still colors red; with Slips ON the repro task shows a ghost
bar but keeps its normal color.

## BUG 2 — Status colors flood the group boxes; palette remapped (HIGH)

**User report:** "The color code implementation doesn't seem right" — the
screenshot shows every nested group box tinted red (pink wash over the whole
chart).

**Root causes (both unscoped changes):**
1. `_status_color()` now recurses: a parent takes the "worst" child color, and
   expanded group boxes / collapsed summary bars are drawn in that status
   color (18-alpha fill + colored border). One red leaf repaints its entire
   ancestor chain of boxes. Original design: group boxes NEUTRAL
   (`C_BOX` gray outline, `C_BOX_FILL`), collapsed groups slate `C_SUMMARY`,
   so leaf colors carry the story.
2. The palette was remapped: active amber→blue `#1976D2`, planned
   blue→gray `#90A4AE`, plus a new amber "waiting" color. The scope's
   out-of-scope list says waiting-on visuals: "not requested; do not add".

**Fix:**
- Groups: revert expanded boxes to `C_BOX`/`C_BOX_FILL` and collapsed bars to
  `C_SUMMARY`, exactly as before Part H. Remove the recursive parent branch
  from `_status_color` (leaves only, as originally).
- Palette: restore `C_DONE #43A047` (done), `C_PROGRESS #FFB300` (active),
  `C_NOT_STARTED #64B5F6` (planned), `C_OVERDUE #E53935` (late). Remove
  `C_WAITING` and its legend entry. Note: the H2 DollarBar reuses
  `C_PROGRESS` for "pending" — amber restores the intended green/amber money
  bar too.
- Keep everything H-scoped that touches these code paths: $ labels,
  critical outline, ghosts.

**Accept:** with one overdue leaf inside two nested groups, both group boxes
render gray outline/near-white fill (assert brush color), and only the leaf
bar is red; legend shows the four original colors + critical when toggled.

## BUG 3 — Dollar bar built correctly but never wakes up (MEDIUM)

**User report:** "I don't see an overall $ bar at the bottom."

**Root cause:** `DollarBar.refresh()` is only called (a) once at
`TimelineContainer.__init__` — which runs BEFORE the project file loads, so
totals are 0 and it hides itself — and (b) on `item_changed_signal`.
Neither `TreeGridView.set_vave_enabled()` (toggling VAVE on) nor the
file-load path notifies the timeline. Verified: `is_active()` returns True
and an explicit `refresh()` shows the bar with correct totals
(`(0.0, 28.0)` in the repro) — the widget works; the wake-up calls are missing.

**Fix (pick the minimal wiring, no new settings):**
- In `ProjectWidget`, wherever VAVE is toggled / `set_vave_enabled` is called,
  follow with `self.timeline.refresh()`.
- After `load_project(...)` completes in ProjectWidget init and in
  `load_snapshot`, call `self.timeline.refresh()`.
- (Optional hardening) `TimelineContainer._set_level/_fit` already repaint the
  canvas; leave them alone.

**Accept:** offscreen — build ProjectWidget with a VAVE task (potential > 0),
enable VAVE, NO cell edits: `dollar_bar.isHidden() == False` and painted text
matches `Realized $X of $Y (P%)`. Toggle VAVE off → bar hides.

---

## Verify after all three (the regression sweep)
1. VAVE off, no baselines → timeline identical to pre-Part-H: neutral boxes,
   4-color leaves, no dollar bar, no ghosts.
2. The user's real file: Aluminum coil NOT red; genuinely-late tasks red;
   group boxes gray; dollar bar visible with the grid's same totals.
3. Slips checkbox on → ghosts + tooltips appear; off → none, and PNG export
   contains no ghosts.
4. Paste the offscreen test output into your completion report — claims
   without output don't count (IMPLEMENTATION_METHODOLOGY Rule 6).
