# VPM Tracker — Stale Dates Fix + Visuals Day-to-Day Upgrades

Plan for any LLM to implement. Applies to the LIVE codebase at
`CO-PILOT TRIALS/vpm_tracker-2/` (the copies under `CODE/vpm_tracker/ui` are
stale/empty — do not edit those).

---

## Part 1 — BUG: "Dates don't change dynamically sometimes"

### Root cause (one pattern, many spots)

Updating dates is a two-step job:
1. `recalculate_all_dates()` — recomputes every task's dates in memory (the model)
2. `refresh_entire_tree()` — repaints the grid from the model (the screen)

Several mutation paths run step 1 but not step 2 (or neither), so the model is
right but the screen shows old dates until some unrelated edit repaints it.
That is exactly the reported symptom: "sometimes the dates don't change when I
update something." It is deterministic per action, which is why it feels random —
some actions repaint, some don't.

### Confirmed broken paths (file: `ui/tree_grid_view.py`)

| # | Path | What's missing | Line (approx) |
|---|------|----------------|----------------|
| 1 | `indent_task` / `outdent_task` | recalc ✓ but **no `refresh_entire_tree()`** | ~2376, ~2399 |
| 2 | `indent_selected_tasks` / `outdent_selected_tasks` | same — recalc without repaint | ~2421, ~2431 |
| 3 | `dropEvent` (drag-drop move, the live one) | `sync_hierarchy()` + recalc, **no repaint** | ~2211 |
| 4 | `add_child_task` | seeds dates from prev sibling only; **no full recalc, no repaint** — predecessor successors and rollups go stale | ~1635 |
| 5 | `toggle_date_lock` (Set/Unset Manual Date) | when UNSETTING, the scheduler should re-anchor the task — **no recalc, no repaint** | ~1404 |
| 6 | `link_selected_tasks` | per-pair date updates only; **no full recalc, no full repaint** — downstream/rollups stale | ~1412 |

Also in `ui/main_window.py`:

| # | Path | What's missing | Line (approx) |
|---|------|----------------|----------------|
| 7 | `open_calendar_settings` | recalc ✓ after holiday/weekend change, **no repaint** | ~554 |

### Dead-code hazard to remove

`ui/tree_grid_view.py` defines **`dropEvent` twice** in the same class (~840 and
~2211). Python silently keeps only the second; the ~90-line version at ~840 (manual
parent/child model surgery) is dead code that will mislead any future edit.
**Delete the ~840 definition entirely.** The live one at ~2211 (with `sync_hierarchy`)
is the real handler — fix that one per row 3 above.

### The systemic fix (do this instead of 7 one-line patches)

Whack-a-mole is how this bug keeps returning (this is the third round of it).
Fix it structurally:

1. Add one helper on `TreeGridView`, e.g. `commit_structure_change(node)`:
   runs `recalculate_all_dates()` → `refresh_entire_tree()` →
   `item_changed_signal.emit(node)` → `update_filter_options()`.
2. Route ALL structure/date mutation endings through it: indent/outdent (all 4),
   dropEvent, add_child_task, toggle_date_lock, link_selected_tasks,
   `_apply_predecessor_change` (already correct — converge it on the helper),
   delete/cut/paste (already correct — converge), calendar settings
   (call the project's tree helper from main_window).
3. `refresh_entire_tree()` already uses the save/restore blockSignals pattern, so
   the helper is safe to call from signal handlers.

Notes:
- Double recalc in already-correct paths is harmless (scheduler is idempotent,
  tree is small). Consistency beats micro-optimization here.
- Keep the auto delay-popup behavior in END/DURATION handlers as is.

### Acceptance tests for Part 1

1. Indent a task under a parent → its dates re-anchor **on screen immediately**.
2. Outdent it back → dates update immediately.
3. Drag-drop a task elsewhere → dates + parents update immediately.
4. Right-click → Unset Manual Date → task snaps back to scheduled dates immediately.
5. Add Child Task on a parent with a predecessor chain → downstream dates correct
   immediately.
6. Link Selected Tasks → all linked rows and their parents repaint immediately.
7. Options → Calendar Settings → add a holiday spanning a task → all dates shift
   on screen immediately.
8. Confirm only ONE `dropEvent` remains; drag-drop still works, notes-pad drop
   (NOTE_MIME) still works.
9. Existing suite passes (`tests/test_predecessor_chain.py`, 13 tests).

---

## Part 2 — Visuals tab: day-to-day usability upgrades

The Focus view (driver chain + week board) is read-only today. Make it the
morning control panel the user starts the day in. Ranked by value; effort tags:
S = small, M = medium.

### 2.1 "Ready to start" bucket (HIGH value, S)
New column/section on the week board: tasks that are **Not Started whose
predecessor (or previous sibling in the chain) is Completed** — i.e. nothing is
blocking them. This answers the #1 daily question: "what can I kick off today?"
Sort by start date; show owner.

### 2.2 Right-click quick actions on any task in Visuals (HIGH, M)
Context menu on every task name in the Focus view:
- **Mark Completed** (status change + scheduler + journal, same as the grid)
- **Log delay reason…** (opens the existing delay dialog)
- **Jump to Tracker** (already exists on click — keep)
After any action, refresh the Focus view in place. This removes the constant
tab-flipping for one-line updates.

### 2.3 Owner filter — "show only mine" (HIGH, S)
A small dropdown at the top of the Focus view: All owners / each owner from the
project. Filters the week board, watch list, and Ready-to-start bucket. The chain
stays unfiltered (it's about the project, not a person).

### 2.4 "Due today" emphasis (MED, S)
Inside "Due this week", bold the tasks whose end date is today and prefix with
"today". Zero new UI, big scanning win.

### 2.5 Delay reasons at your fingertips (MED, S)
Wherever a delayed task appears (chain pill, watch list, week board), the tooltip
shows its revision trail (latest reason + slip). The data already exists
(`revision_trail()`); just wire tooltips.

### 2.6 Live refresh while the tab is open (MED, S)
Focus view currently rebuilds only on tab switch. Rebuild whenever
`item_changed_signal` fires while the Visuals tab is the current tab (throttle to
e.g. once per second). Required anyway for 2.2's in-place actions.

### 2.7 Morning digest header (LOW, S — user previously deferred this)
One compact line at the top: "Project ends <date> (<+N>d vs plan) · X overdue ·
Y due this week · Z ready to start". The user skipped a metric strip before —
implement LAST and keep it to a single line of text, no cards.

### What NOT to do
- No new charts in the Focus view (the Timeline pane in Tracker covers visuals).
- No editing grids inside Visuals — quick actions only, the Tracker stays the
  editor.
- Don't re-add WBS numbers/dense stats — the user rejected visual noise twice.

### Acceptance tests for Part 2

1. A task whose predecessor was just completed appears under "Ready to start"
   without leaving the tab.
2. Right-click → Mark Completed on a week-board task → row moves to "Closed",
   journal gets an entry, Tracker shows the change, no tab switch needed.
3. Owner filter set to one person → all buckets show only that person's tasks;
   chain unchanged.
4. A delayed task's tooltip anywhere in Visuals shows the latest delay reason.
5. Edits made in the Tracker while Visuals is open appear within ~1 second.

---

## Suggested implementation order

1. Part 1 systemic fix + dead `dropEvent` removal (stops the recurring bug class).
2. Part 1 acceptance tests.
3. Part 2 items in order: 2.1 → 2.3 → 2.6 → 2.2 → 2.4 → 2.5 → (2.7 last, optional).
4. Run the full test suite + manual checklist.
