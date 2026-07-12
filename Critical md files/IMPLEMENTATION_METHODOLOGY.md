# IMPLEMENTATION METHODOLOGY — read this before writing any code

Companion to `DEBUGGING_METHODOLOGY.md`. That file is for fixing bugs; THIS
file is for implementing a scoped plan (`TRACKER_PART_*.md` etc.) in the VPM
Tracker codebase. Follow it in order. Every rule earned its place by a real
mistake that cost the user an evening. If you skip a step, say so and why.

---

## Rule 0 — Find the LIVE code before touching anything

The working folder has MOVED at least three times. Never trust a path from a
plan, a memory, or an old conversation. Prove the location first:

```
# newest task_node.py wins — that folder is the live app
Get-ChildItem C:\Users\silam\OneDrive\Documents -Recurse -Filter task_node.py -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 3 FullName, LastWriteTime
```

As of 2026-07-12 the live app is `C:\Users\silam\OneDrive\Documents\VPMTracker\VPM Tracker\`.
Ignore `.git-helper\recovery\...` and `__pycache__` hits — those are snapshots,
not the app. If two candidate folders tie, STOP and ask the user which one.

## Rule 1 — Read the whole plan, then read the code the plan touches

- Read the plan file top to bottom ONCE before editing. The plan's
  "Out of scope / rejected" section is as binding as the features: adding a
  rejected feature is a failure even if it works perfectly.
- For every file the plan names, READ the actual functions you will modify
  before editing them. Plans describe intent; only the file shows current
  truth (someone may have changed it since the plan was written).
- List for yourself: which functions you'll change, which you'll add, which
  signals/callers are affected. If the plan contradicts the code you read
  (function renamed, moved, already implemented), STOP and report the
  mismatch — do not improvise a reinterpretation.

## Rule 2 — House rules that override anything you think is better

These are USER DECISIONS. Do not "improve" them:

1. **Nothing auto-calculates money.** Potential $ is never derived from
   Baseline−Proposed or anything else. Only SUMS (totals, parent rollups)
   are computed.
2. **The notepad types like OneNote.** Plain Enter = new line. Never add
   Enter-to-submit, Shift+Enter tricks, or capture boxes anywhere near notes.
3. **Slip/delay visuals are private.** Anything that shows slippage must be
   OFF by default and opt-in per session (leadership must not see slips by
   accident, including in exports).
4. **Blank $ = execution task.** No flags, no per-task VAVE marking.
5. **New rows are never "delayed".** A fresh task's first typed end/duration
   re-baselines silently (`baseline_provisional` flow in tree_grid_view).
6. **Don't clutter.** No new top-level menu items or context-menu entries
   beyond what the plan specifies; the user is actively REMOVING options.
7. Match existing naming and comment style; comments explain constraints,
   not narrate lines.

## Rule 3 — One plan item at a time, verified before the next

Implement in the plan's order (it's dependency-sorted). For EACH item:

1. Make the smallest edit that completes the item.
2. Compile check: `python -m py_compile <changed files>` — zero cost, catches
   half of weak-model mistakes.
3. Run the item's acceptance check from the plan (see Rule 4 for how).
4. Only then start the next item.

Never batch five items and test at the end — when something breaks you won't
know which edit did it, and you'll burn the debugging file's Rule 1 doing
archaeology on your own changes.

## Rule 4 — Verify like the debugging file reproduces: headless, with numbers

The app is PyQt6. You can drive ALL of it without a display:

```
$env:QT_QPA_PLATFORM = "offscreen"   # (bash: QT_QPA_PLATFORM=offscreen)
python - <<'EOF'
import sys, os
sys.path.insert(0, os.getcwd())
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.main_window import MainWindow
from models.task_node import TaskNode
w = MainWindow()
proj = w.active_project()
# ...build tiny fixture nodes, call the code you changed, PRINT numbers...
EOF
```

- Assert MEASURABLE facts ("label text == 'Trial 2 ($0 / $18,000)'",
  "totals bar sums to 28700"), never "looks right".
- Telemetry is auto-disabled under offscreen, so tests won't pollute the
  user's usage logs. Do NOT remove that guard.
- GUI paint code (timeline) can't be screenshot-asserted headlessly — instead
  call the pure helpers (e.g. `_date_range`, label-building, totals math)
  directly, and render to a `QPixmap` via `export_image(...)` to prove the
  paint path doesn't crash.
- After your last item, run the plan's FULL acceptance list plus one boot
  test: construct MainWindow, open a real save file copy, no exceptions.
- Also honor DEBUGGING_METHODOLOGY Rule 3: if the feature involves the
  launcher, test by double-clicking the real `.cmd`, not just terminal runs.

## Rule 5 — Codebase-specific traps (each has bitten before)

- **CRLF:** files are CRLF. Most edit tools preserve this; verify one changed
  file after your first edit (`file ui/x.py` → must still say CRLF).
- **`blockSignals` discipline:** anything that programmatically updates tree
  items must save/restore: `was = self.blockSignals(True) ... finally:
  self.blockSignals(was)`. Force-unblocking breaks outer callers and causes
  popup loops.
- **`Columns` enum ripples:** adding/reordering columns in
  `vpm_tracker_core.py` touches delegates, filters, excel_export, copy/paste,
  and update_from_node. Avoid new columns unless the plan demands one.
- **After ANY structure/date mutation** call
  `commit_structure_change(node)` (recalc + repaint + filters + signal) — or
  for multi-row batches: mutate all, then ONE
  `recalculate_all_dates()` + `refresh_entire_tree()` +
  `item_changed_signal.emit(first_node)` inside
  `proj.begin_batch()/end_batch()` so Ctrl+Z is a single step.
- **Persistence:** every new TaskNode/project field needs `to_dict` +
  `from_dict(default)` + a `CURRENT_VERSION` bump in `utils/vpmt_io.py`.
  Old files MUST load with sane defaults (write a test that loads a dict
  without the new key).
- **Per-project config:** holidays/owners come from `ConfigManager` and
  depend on the ACTIVE project — call sites assume `proj.activate()` ran.
- **Money:** reuse `parse_money` / `money_text` from the grid; never invent a
  second formatter.
- **The Inbox root** (name "inbox", dateless) is notes, not schedule — every
  timeline/summary/export loop must skip it (see `_is_inbox`).
- **Journal + telemetry:** user-visible actions get a
  `journal_event.emit("...")` line and a `usage_logger.log(event, ...)` call
  (names/counts only, never note text or dollar values in telemetry... the
  existing `vave_edit` logs column names only — follow that).

## Rule 6 — Ship it the project's way

1. Re-run the full acceptance list; paste the actual output into your final
   report — claims without output don't count.
2. Update the plan MD: mark each item ✅ with a one-line "how verified", and
   record any deviation you were forced to make and why.
3. Snapshot/rev per the project convention (`rev_up.py` / "Rev Up VPM
   Tracker.cmd") rather than editing history.
4. Report to the user in plain language: what they will SEE changed, any
   item you could not finish (say so plainly — a truthful "H3 not done"
   beats a broken H3), and the one-click way to try each new thing.

## Rule 7 — When stuck, stop cleanly

If an item resists after two honest attempts: revert to the last verified
state (recovery snapshots exist in `.git-helper\recovery\`), mark the item
"BLOCKED: <exact error / mismatch>" in the plan file, and move to the next
INDEPENDENT item. A half-implemented feature woven through six files is the
most expensive thing you can leave behind.
