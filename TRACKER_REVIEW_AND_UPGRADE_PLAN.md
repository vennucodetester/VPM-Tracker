# VPM Tracker — Code Review + Upgrade Plan (2026-07-07)

**Audience:** an LLM (or developer) implementing fixes/features in this folder.
**App entry:** `tracker_app2.py` → `ui/main_window.py` (MainWindow) → `ui/project_widget.py`
(one per project tab) → `ui/tree_grid_view.py` (the core grid, 2,445 lines) +
`models/task_node.py` + `utils/scheduler.py`.

**Rule from the user's workflow:** every phase below needs the user's approval
before implementation. Pitch in plain language first.

---

## Part A — Bugs found in review (fix in this order)

### A1. File → Load discards unsaved work without asking  (data loss, HIGH)
`MainWindow._load_path()` (ui/main_window.py ~634) wipes all tabs and loads the new
file with **no unsaved-changes check**. `closeEvent` has the check; load doesn't.
**Fix:** at the top of `_load_path`, if `self.unsaved_changes`, show the same
Yes/No/Cancel save prompt as `closeEvent`; Cancel aborts the load.

### A2. Ctrl+Z / Ctrl+Y ambiguity with multiple project tabs  (HIGH)
Each `ProjectWidget.__init__` (ui/project_widget.py ~65) registers
`QShortcut(Undo/Redo, ApplicationShortcut)`. The Edit-menu `QAction`s in
MainWindow (~235) also bind Ctrl+Z / Ctrl+Y. Two+ enabled shortcuts on the same
key make Qt fire `activatedAmbiguously` instead of `activated` → undo silently
stops working (or targets a hidden tab) once a second project tab exists.
**Fix:** remove the per-ProjectWidget QShortcuts entirely. Keep ONLY the menu
actions in MainWindow, which already delegate to `active_project().undo()/redo()`.
To make them work while a cell editor is focused, set
`Qt.ShortcutContext.ApplicationShortcut` on the two QActions.
**Test:** open 2 tabs, edit in each, Ctrl+Z works in both; also while renaming a task.

### A3. Startup state is hostile to a forgetful user  (HIGH, pairs with feature B2)
- Every launch shows seeded fake data (`_seed_test_data`, "Project Alpha").
- The last-used file is NOT reopened (recent list exists but is manual).
- Autosave (`_autosave`) only runs when `current_filepath` is set → any work in a
  never-saved file is lost on crash.
**Fix:**
1. On startup: if `settings.value("recent_files")` has a valid entry, load it
   (reuse `_load_path`). Only seed test data when there is no recent file.
2. Crash-safety for unsaved files: when `current_filepath` is None and there are
   unsaved changes, autosave to `<QStandardPaths.AppDataLocation>/recovery.vpmt`;
   on next startup, if that file exists and is newer than its last import, offer
   to restore it. Delete it after a successful manual save.

### A4. Files with >5 projects are truncated on load, then overwritten on save  (data loss, MEDIUM)
`_load_path` caps at `MAX_PROJECTS = 5` (ui/main_window.py ~661); a later save
writes only the loaded 5. **Fix:** if `len(projects) > MAX_PROJECTS`, refuse the
silent cut — either raise the cap, or load all (cap only *new* tab creation), or
at minimum warn "this file has N projects; N−5 will be REMOVED if you save" and
default to not loading.

### A5. Autosave burns through the .bak rotation  (MEDIUM)
Autosave every 3 min + `_rotate_backups` on every save (utils/vpmt_io.py) means
all 5 backups can span ~15 minutes; older restore points vanish.
**Fix (pick one):**
- Rotate backups only on *manual* save, not autosave (autosave writes the main
  file atomically without touching .bak); or
- Add a daily backup tier: `filename.day1..day3` rotated once per calendar day.

### A6. Manual status choices are silently overwritten  (LOW)
`TaskNode.update_status_from_dates` (models/task_node.py ~348) recomputes status
from dates on every scheduler pass: picking "Not Started" on a task that already
started flips back to "In Progress"; picking "Overdue" (it's in the Status enum
and the dropdown) never sticks. **Fix:** remove "Overdue" from the StatusDelegate
dropdown (it's a computed display state, shown red), and don't let
`update_status_from_dates` override an explicit user-set status on leaf tasks
(add a `status_manual: bool` flag set by `set_status`, cleared when dates move
past it, or simply respect "Not Started"/"In Progress" user picks on leaves).

### A7. Delay dialog can log a zero/negative revision  (LOW)
`DelayDelegate._open_dialog` (ui/tree_grid_view.py ~222) computes `new_slip` and
logs it even when ≤ 0. **Fix:** if `new_slip <= 0`, show current trail read-only
(no "New: Rev …" input) — nothing new to log.

### A8. Bulk edits create one undo step per row  (LOW)
`bulk_set_status` / `bulk_set_owner` emit `item_changed_signal` per item; each
emit pushes a history snapshot in `ProjectWidget._on_tree_changed`. 10 rows =
10 Ctrl+Z presses. **Fix:** add a `begin_batch()/end_batch()` guard on
ProjectWidget that suppresses pushes and pushes once at the end (or emit the
signal once after the loop).

### A9. Dead code  (cosmetic)
Orphaned `paint()` in `OwnerDelegate` (ui/tree_grid_view.py ~113) after two blank
lines — first-line-only rendering that duplicates NotesDelegate. Delete it.

**Not reviewed in depth:** `ui/gantt_chart.py`, `ui/timeline_pane.py`,
`ui/focus_view.py`, `ui/header_filter.py`, `utils/critical_path.py`,
`utils/excel_export.py`. Review before large changes there.

---

## Part B — Requested features (each needs user approval before building)

### B1. Zoom — app-wide font size control
**UX:** Ctrl+`=` bigger, Ctrl+`-` smaller, Ctrl+`0` reset, Ctrl+mouse-wheel; show
"Zoom 110%" in the status bar; persist in `QSettings("VPM","VPMTracker")` key
`ui_zoom` and restore on launch. Range 70%–200%, step 10%.
**Implementation notes (the traps):**
- Fonts are hardcoded in several places: `tracker_app2.py` global stylesheet,
  `TreeGridView.setup_ui` (10pt bold + `QTreeView::item { height: 30px; }`),
  QFont sizes in main_window/dialogs/notes_panel, and the timeline/gantt painters.
- Centralize: a `ui/zoom.py` with `apply_zoom(app, factor)` that (a) sets
  `QApplication.setFont` scaled from a stored base, (b) re-emits a
  `zoom_changed` signal that TreeGridView uses to regenerate its stylesheet with
  `height: {int(30*factor)}px`, and timeline/gantt use to scale row heights and
  their painter fonts. Grep for `setPointSize|setFont|height: 30px|QFont\(`
  and route every hit through the base-size table.
- MainWindow owns the shortcuts (ApplicationShortcut) and the QSettings I/O.

### B2. Organization / forgetfulness package
The app must surface state instead of waiting to be asked.
1. **Auto-reopen last file** (see fix A3). Zero new UI.
2. **"Today" panel on startup** — a dialog (or better: a permanent first inner
   tab "Today") showing for the active file:
   - Overdue tasks (end < today, not Completed) — click to jump (reuse
     `jump_to_node_id`).
   - Due today / due this week.
   - Notes-pad lines older than N days ("still uncategorized").
   - Last 7 days' journal digest (reuse `_show_digest_since_last_visit` content).
   Data sources already exist: `get_all_nodes_flat()`, `proj.journal`,
   `notes_panel.get_notes()`.
3. **End-of-day nudge (optional, off by default):** if the app is open at a
   configured time (default 16:30), toast/dialog listing tasks due today not
   completed with buttons per task: Mark Done / +1 day (goes through the normal
   end-date path so delay logging still triggers) / Ignore.
Approval note: pitch 1+2 together; 3 separately.

### B3. Ctrl+Space quick capture, rebuilt
Current: `MainWindow._quick_capture` → shows the project notes dialog + focuses
the capture box. Problems: heavyweight, app-focus only, and Ctrl+Space collides
with Windows IME toggling for some keyboard layouts.
**New design — capture palette:**
- Frameless small popup centered on the main window (QDialog,
  `Qt.Popup | FramelessWindowHint`), one QLineEdit + a hint label.
- Enter → line goes to the active project's notes pad (existing
  `notes_panel.list.add_line`), popup closes, focus returns to where it was.
- Prefix syntax: `>` = create task at end of active project (reuse
  `_promote_lines_to_tasks`), `@name` anywhere = owner tag (already parsed by
  `_parse_owner_tags`). Show the parse live under the box ("→ Task for Larry").
- Esc closes without saving. Also keep a secondary shortcut `Ctrl+Shift+Space`
  in case Ctrl+Space is eaten by the IME.
- **Level 2 (separate approval):** system-wide hotkey while the app is running
  in the tray — needs a Win32 RegisterHotKey wrapper or the `keyboard` package;
  discuss the dependency before adding.

### B4. Editable Delay column
Today: Delay = `duration − baseline_duration`, read-only; the only reset is the
context-menu "Update Baseline (not a delay)".
**New interactions on the Delay cell (leaf tasks only; parents stay rollup-only):**
- Right-click menu (extend `open_context_menu` when the click lands on
  Columns.DELAY, or add these to the DelayDelegate double-click dialog):
  - **Mark On Track** — re-stamp baseline to current (reuse
    `update_baseline_for_node`), and append a journal line
    "Marked on track (was +Nd): <optional reason>". Do NOT silently erase the
    revision trail: move existing revisions into a journal line first, or keep
    them and add a "rebased" marker — decide with the user.
  - **Set Delay to…** — small dialog: spin box for target delay in days
    (can be 0 or negative) + required reason. Implementation: adjust
    `baseline_duration = duration − target` (this changes the *reference*, not
    the schedule — the dates stay put, the label reads what the user wants).
    Append a revision entry `{"rev": next, "date": today, "slip": target −
    old_diff, "reason": …}` so the audit trail stays truthful.
- Double-click keeps opening the existing log dialog, with these two actions
  added as buttons.
**Guard:** both actions require `baseline_duration is not None`; otherwise offer
"Set baseline for this task first?".

---

## Part C — Best-in-class comparison (idea menu, user picks)

Benchmarks: MS Project, Smartsheet, TeamGantt, Asana, Monday.com, Todoist,
Notion, Linear. Already competitive: impact simulation before date changes,
Rev A/B/C delay audit trail, baselines, per-project calendars, journal.

Ranked for THIS user (forgetful, organization-focused, daily R&D re-planning):
1. **Command palette (Ctrl+K)** — fuzzy-find any task or command; acts (jump,
   mark done, log delay). Foundation: `get_all_nodes_flat` + `jump_to_node_id`.
2. **"My Day" view** — see B2.
3. **Percent-complete** — per-task % field, drawn as fill on timeline bars;
   parent % = duration-weighted child average.
4. **Milestones** — zero-duration tasks drawn as diamonds; milestone flag on
   TaskNode; timeline + Excel export support.
5. **Saved views** — persist `active_filters` + expand state under a name;
   dropdown in the toolbar ("Larry's week", "Overdue only").
6. **WBS numbering** — computed 1.2.3 outline numbers as an optional first column.
7. **Priority / color labels** — enum on TaskNode, colored chip in the tree,
   filterable.
8. **Recurring tasks** — template + recurrence rule spawns next instance on
   completion (weekly QA checks etc.).
9. **One-page PDF/print status report** — project header, red/amber/green
   counts, overdue list, next-2-weeks list; reuses excel_export data shaping.
10. **Git-backed sync** — on every save, background `git add/commit/push` of the
    .vpmt via the same non-interactive plumbing as git_helper.py (see
    GIT_HELPER_V4_FIX_PLAN.md). Kills two problems: off-machine backup and
    the weak .bak rotation (A5).

---

## Suggested phasing
- **Phase 1 (safety):** A1, A2, A3, A4 — no visual changes, pure protection.
- **Phase 2 (asked-for):** B1 zoom, B4 editable delay, B3 capture palette, A5–A8.
- **Phase 3 (picked from Part C):** whatever the user selects, one at a time.
