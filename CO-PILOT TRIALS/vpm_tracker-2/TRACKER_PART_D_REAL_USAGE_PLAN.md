# VPM Tracker — Part D: Upgrades from Real-Usage Analysis (2026-07-07)

**Audience:** an LLM/developer implementing changes in this folder.
**Context:** follows `TRACKER_REVIEW_AND_UPGRADE_PLAN.md` (Phases 1–2 are being
implemented separately — coordinate; several files are already modified in the
working tree). These items were derived from analyzing the user's real project
file `DG-PH2-6-24.vpmt` (163 tasks, depth 7, Apr–Dec 2026, 199 journal entries,
11 delay revisions, ALL owners blank, 21 overdue leaves as of 2026-07-07).

**User decision:** implement D1, D2, D3, D4, D5 below. The "Not a delay /
correction button in the delay dialog" idea was explicitly REJECTED for now —
do not change the delay-reason prompt behavior.

**Priority order (user-approved):** D1 (Catch-Up mode) → D2 (Waiting On) →
D3 (auto note on delay) → D4 (holiday inheritance fix) → D5 (file hygiene).
D0 is a one-time cleanup to do first.

---

## D0 — One-time cleanup: nested repo folder + relocated data file

Tonight's git-helper setup run pulled the repo into itself. Current state:
- `vpm_tracker-2\CO-PILOT TRIALS\vpm_tracker-2\...` is a nested duplicate tree.
- The live `DG-PH2-6-24.vpmt` now exists ONLY at that nested path; the top-level
  copy is gone (only `.bak4`/`.bak5` remain at top level).
- Commits involved: `f0341fb "Save local files after setup"` through
  `ac60d21` (2026-07-07 21:25–21:41).

**Steps (confirm each with the user before deleting anything):**
1. Compare all copies of `DG-PH2-6-24.vpmt` (nested path, git history at
   `origin/main`, `.bak4/.bak5`) by mtime and content; identify the newest.
2. Move the newest back to
   `...\vpm_tracker-2\DG-PH2-6-24.vpmt` (the canonical location).
3. Delete the nested `vpm_tracker-2\CO-PILOT TRIALS\` duplicate tree — ONLY
   after step 2 is verified and the user confirms.
4. Commit the flattened state with a clear message; push.
5. Tell the user their tracker "Open Recent" entry may point at the old/nested
   path — after D5's recent-menu change this becomes self-evident.

---

## D1 — Catch-Up mode (overdue triage)  ← biggest win

**Problem observed:** 21 overdue leaf tasks. Updating each one requires
end-date edit → ImpactReviewDialog → delay dialog; nobody does that 21 times,
so red rot accumulates and the plan stops being trusted.

**Feature:** `Edit → Catch Up on Overdue…` (also a button/badge in the toolbar
showing the overdue count, e.g. red "21 overdue" — clicking opens the dialog).

**Dialog:** table of all overdue leaves (`end_date < today`, status !=
"Completed", `children == []`), sorted oldest-first, columns:
`Task (full path) | Was due | Days late | Action`.
Per row, the Action cell has three mutually exclusive choices:
- **Done** — set status "Completed" (via `node.set_status`).
- **Push to [date editor]** — default = today + original workday duration
  remaining (simplest good default: keep duration, move end so that end ≥
  today; a QDateEdit pre-filled, user can adjust). Applies through
  `node.set_date('end', …)` so scheduling stays consistent.
- **Skip** — leave untouched (default).
Below the table: one shared optional "reason" QLineEdit ("applies to all pushed
tasks") + `Apply` / `Cancel` buttons.

**On Apply:**
- Perform all Done actions, then all Push actions, then run
  `recalculate_all_dates()` + `refresh_entire_tree()` ONCE (not per row).
- For each pushed task that slips past baseline, append a revision entry
  (same shape as `DelayDelegate._open_dialog`, ui/tree_grid_view.py ~280):
  `{"rev": next, "date": today, "end": new_end, "slip": uncovered_slip,
  "reason": shared_reason or "Pushed during catch-up"}`. Do NOT open the
  per-task delay dialog — the shared reason replaces it here (this does not
  conflict with the user's rejection of changing the normal delay dialog;
  Catch-Up is a separate bulk path).
- Also run D3's auto-note append for each pushed task.
- Journal one line per action + a summary line
  ("Catch-up: 5 done, 9 pushed, 7 skipped").
- Single undo step for the whole batch — requires the batch guard from item A8
  of the previous plan (`ProjectWidget` suppress-push + one push at end). If A8
  isn't built yet, build it as part of D1.
- Emit `item_changed_signal` once at the end (dirty flag + autosave).

**Skip the ImpactReviewDialog** in this flow — the point is speed; the single
recalc at the end applies the ripple. (Simulation-per-row would defeat the
feature.)

**Acceptance test:** file with 5 overdue tasks → open Catch-Up, mark 2 Done,
push 2 (+3 days each), skip 1 → one Apply: statuses/dates/delay revisions/
journal all correct, ONE Ctrl+Z restores everything, downstream dependent
tasks rippled.

---

## D2 — "Waiting On" tracking (replace the unused Owner workflow)

**Problem observed:** all 115 leaf owners are blank, but delay reasons/notes
constantly reference people/teams being waited on ("CFD team busy", "lab didn't
get to it", "Doug was wondering…"). The real need is *who am I waiting on and
since when*, not assignment.

**Model:** add to `TaskNode` (models/task_node.py, `__init__` + `to_dict` +
`from_dict` with backward-compatible defaults):
- `waiting_on: str = ""` (person/team, free text with completer from config
  owners list)
- `waiting_since: Optional[str] = None` (auto-set to today when `waiting_on`
  becomes non-empty; cleared together)

**UI:**
1. Context menu on a task: `Mark Waiting On…` → small dialog: who (editable
   combo seeded from `ConfigManager().get_owners()` + all `waiting_on` values in
   the tree) + optional note. Sets fields, journals
   "'Task': waiting on Lab since 2026-07-07". `Clear Waiting` when set (journals
   "waited N days").
2. Display: do NOT add a new column (Columns enum ripples into export/filters —
   keep the diff small). Instead show it in the **Owner column** as
   `⏳ Lab (14d)` when `waiting_on` is set (the owner text is unused by this
   user; when both exist, waiting display wins, tooltip shows both). Amber
   foreground `#FF8F00`. Rendered in `TaskTreeWidgetItem.update_from_node`.
3. **Waiting list:** `Edit → View Waiting-On List…` — table of every task with
   `waiting_on` set: `Task (path) | Waiting on | Since | Days`, sorted by days
   descending, double-click jumps via `jump_to_node_id`. Rows ≥ 5 workdays in
   red.
4. Wire into the Today/startup panel (B2 of the previous plan) if/when it
   exists: "Waiting on others: N (oldest: Lab, 14 days)".
5. `Search Everything` should match `waiting_on` text (ui/main_window.py
   `run_search`).

**Excel export:** include `waiting_on`/`waiting_since` in the Owner column text
or an extra column — check `utils/excel_export.py` and keep its format working.

**Acceptance test:** mark 2 tasks waiting → column shows ⏳ with day count,
list dialog shows both, persists through save/load (and old files load fine
without the fields), journal lines written, clear works.

---

## D3 — Auto-write the note line when a delay is logged

**Problem observed:** the user hand-writes a dated note for every slip
("[2026-05-13]: Delayed again. 5/7 to 5/14") *in addition to* the delay
revision — same fact recorded twice, manually.

**Feature:** whenever a delay revision is appended, ALSO prepend one line to
`node.notes` (same format the Notes editor uses):
`[YYYY-MM-DD]: Delayed +Nd, end → <new_end>. <reason>`

**Call sites that append revisions (all must do this — extract one helper,
e.g. `TaskNode.log_delay_revision(rev_dict)` that appends the revision AND the
note line):**
- `DelayDelegate._open_dialog` accept path (ui/tree_grid_view.py ~284)
- `TreeGridView._log_delay_from_review` (~1224)
- D1's catch-up push path (new)

Prepend (newest first) to match the user's existing habit; guard against
double-prefixing when notes already start with today's identical line.
No settings toggle needed — if the user objects later, add one.

**Acceptance test:** log a delay via double-click, via an End-date edit, and
via Catch-Up → each produces exactly one new note line and one revision; the
Notes cell first-line preview shows it.

---

## D4 — Holiday inheritance fix (real scheduling bug in the user's file)

**Problem observed:** global `vpm_config.json` has 6 holidays
(Thanksgiving/Christmas/New Year etc.) but the project's metadata in
`DG-PH2-6-24.vpmt` is `{'owners': ['Unassigned','Me'], 'holidays': [],
'exclude_weekends': True}` — the project schedules straight through Christmas.
Cause: per-project config (utils/config_manager.py) defaults to empty and never
inherits the global profile.

**Fixes:**
1. **Inherit on create:** in `ConfigManager.register_project`, when `metadata`
   is empty/missing keys, seed from `_projects["__default__"].snapshot()`
   instead of hardcoded defaults (owners AND holidays AND exclude_weekends).
   Careful: `register_project` is also called on file LOAD with real metadata —
   only fill keys that are absent, never override what the file says. A file
   that explicitly saved `"holidays": []` is indistinguishable from "never set";
   resolve via fix 2.
2. **Warn in Calendar Settings** (ui/calendar_dialog.py): when the active
   project's holiday list is empty and the global default list is not, show an
   inline note + "Copy global holidays (N)" button.
3. **One-time nudge on load** (ui/main_window.py `_load_path`): after loading,
   if any project has 0 holidays while the global default has >0, statusBar
   message (not a popup): "Tip: this project has no holidays set — Options →
   Calendar Settings."

**For the user's live file:** after implementing, open it, use the Copy-global
button, save. Verify Nov–Dec task dates shift accordingly (expect end dates
around holidays to move later).

**Acceptance test:** new project inherits global holidays; loading the real
file triggers the tip; Copy button fills the 6 dates and reschedules.

---

## D5 — File hygiene (stop the copy chaos)

**Problem observed:** at least 30 scattered .vpmt copies across
`SAVE FILES\`, versioned filenames (`DG-2.0-2`, `-3`, `-bckup`, `DG 2.5-4-21`),
three folder levels, plus tonight's nested duplication. Manual version control
by filename = "which file is current?" hazard.

**App changes (small, do these):**
1. **Open Recent menu shows full path + last-modified date** in the entry text
   (ui/main_window.py `_populate_recent_menu`), not just the basename — twin
   files in different folders become distinguishable.
2. **Title bar already shows the full path** — keep.
3. **Duplicate-basename warning on open:** in `_load_path`, after loading,
   check the recent-files list for a DIFFERENT path with the same basename and
   a NEWER mtime than the file just opened; if found, warn: "A newer file with
   the same name exists at <path>. Are you sure this is the right one?"

**User-facing guidance (put in a short section the LLM should relay to the
user after implementing):** keep ONE canonical file per real project in ONE
folder; stop making dated copies — the app's `.bak1–5` (+ the daily tier from
item A5) and git history are the version control. The `SAVE FILES` folder and
old `DG-2.0*` copies should be archived into a single `ARCHIVE\` folder (user
confirms before moving).

**Acceptance test:** open the older of two same-named files → warning appears
naming the newer path; recent menu shows paths+dates.

---

## Explicitly out of scope (user said no, for now)
- Changing the delay-reason prompt itself (no "Not a delay" button, no
  suppression of the prompt). `Update Baseline (not a delay)` in the context
  menu stays as the only correction path.
- All previous Part C ideas (command palette, % complete, milestones, saved
  views, WBS, recurring, PDF report) — user declined.

## Coordination notes for the implementing LLM
- Phases 1–2 of `TRACKER_REVIEW_AND_UPGRADE_PLAN.md` are in progress in this
  working tree (`models/task_node.py`, `ui/main_window.py`,
  `ui/project_widget.py`, `ui/tree_grid_view.py`, `utils/vpmt_io.py` are
  modified). Rebase this work on top of that; D1 depends on A8 (batch undo).
- Every feature must survive save→load round-trip of old files (missing new
  fields default cleanly) — follow the `from_dict(..., data.get(key, default))`
  pattern.
- Per the user's workflow: pitch each D-item in plain language and get approval
  of the concrete UI before building it, one item at a time.
