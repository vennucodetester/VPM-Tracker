# VPM Tracker — Local Usage Telemetry Plan (2026-07-07)

**Audience:** an LLM/developer implementing in this folder.
**Goal:** record HOW the user uses the app (features, frequency, friction) into
local log files that a future LLM session can read and analyze to propose
improvements. This is the instrumentation counterpart to the analysis done by
hand in `TRACKER_PART_D_REAL_USAGE_PLAN.md`.

**Hard requirements:**
- 100% local. No network, ever. Data stays on this machine.
- Can NEVER crash, block, or slow the app. Every logger call is wrapped;
  failures are silently ignored.
- Off switch in the Options menu ("Record usage statistics", default ON,
  persisted in QSettings key `usage_logging`).
- Low volume: one short JSON line per event, monthly rotation, auto-prune.

---

## 1. The logger — `utils/usage_logger.py`

```python
class UsageLogger:
    # module-level singleton, initialized once in tracker_app2.main()
    def log(self, event: str, **details): ...
```

- **Location:** `<repo>/usage_logs/usage-YYYY-MM.jsonl` (folder created on
  first write; add `usage_logs/` to `.gitignore` — usage data should NOT be
  committed/pushed by the git helper unless the user later opts in).
- **Line shape:**
  `{"ts": "2026-07-07 21:55:03", "sid": "a1b2c3", "ev": "delay_dialog", "d": {...}}`
  `sid` = 6-hex session id generated at app start (groups events per run).
- **Implementation:** plain `open(path, "a")` + `json.dumps` per call, wrapped
  in `try/except Exception: pass`. No threads, no buffering complexity —
  events are rare (human-speed), a synchronous append is microseconds.
- **Enabled check:** read once at startup from QSettings; `log()` is a no-op
  when disabled. Toggling in Options takes effect immediately.
- **Pruning:** on startup, delete `usage-*.jsonl` files older than 12 months.
- **Session bookkeeping:** log `app_start` (with app version) in `main()`;
  log `app_end` (with session duration seconds) in `MainWindow.closeEvent`.

## 2. What to log (the event catalog)

Keep detail payloads SMALL — counts and ids, not full content. Task names are
OK (the user's own machine) but never log full notes/journal text.

### Session / file
| event | details |
|---|---|
| `app_start` | `version` |
| `app_end` | `secs` (session length) |
| `file_open` | `path`, `projects`, `tasks` (total count) |
| `file_save` | `manual` (bool — manual save vs autosave) |
| `autosave_recovery_offered` / `_accepted` | — |

### Feature usage (one event per invocation)
| event | details |
|---|---|
| `menu_action` | `name` (the QAction text — instrument centrally, see §3) |
| `quick_capture` | `via` ("ctrl_space"/"menu"), `kind` ("note"/"task") |
| `search` | `chars` (query length), `hits` |
| `search_result_opened` | — |
| `tab_switch` | `to` ("tracker"/"visuals"/project index) |
| `zoom` | `pct` |
| `task_add` | `via` ("enter"/"context_menu"/"paste"/"note_drop") |
| `task_delete` | `count` |
| `indent`/`outdent` | `count` |
| `bulk_edit` | `what` ("status"/"owner"), `count` |
| `filter_apply` | `column`, `values` (count only) |
| `undo` / `redo` | — |
| `baseline_set` / `baseline_update_node` | — |
| `catchup_open` | `overdue` (count) |
| `catchup_apply` | `done`, `pushed`, `skipped` |
| `waiting_set` / `waiting_clear` | `days_waited` (on clear) |
| `notes_pad_open` | — |
| `note_promoted` | `to` ("task"/"task_notes") |
| `excel_export` | `projects` |

### Friction signals (the most valuable category)
| event | details |
|---|---|
| `dialog` | `name` ("impact_review"/"delay_log"/"date_validation"/…), `outcome` ("ok"/"cancel"), `ms_open` (time the dialog was up) |
| `warning_shown` | `name` ("start_is_auto"/"conflicting_settings"/"no_baseline"/"older_file_version"/…) |
| `error` | `where`, `type` (exception class name only) — hook `sys.excepthook` in tracker_app2 to log uncaught exceptions before showing/reraising |
| `load_failed` / `save_failed` | `type` |

Rule of thumb: any `QMessageBox.warning/critical` and any dialog with a Cancel
button should be logged with its outcome. Cancel-rates and repeat-warnings are
what reveal design problems.

## 3. Instrumentation strategy (keep the diff small)

1. **Menus (covers ~30 features in one place):** in
   `MainWindow.setup_menu`, wrap action wiring with a helper:
   ```python
   def _act(self, menu, text, slot, shortcut=None):
       a = QAction(text, self); ...
       a.triggered.connect(lambda: (usage.log("menu_action", name=text), slot()))
   ```
   Same helper pattern for `TreeGridView.open_context_menu` entries.
2. **Dialogs:** tiny wrapper `def timed_exec(dialog, name)` in usage_logger —
   records ms_open + accepted/rejected — and replace `dialog.exec()` at the
   ~10 interesting call sites (ImpactReviewDialog, DelayDelegate dialog,
   NotesDelegate dialog, date_validation box, bulk dialogs, search dialog
   open/close).
3. **Warnings:** grep `QMessageBox.warning|information|critical` in `ui/` and
   add a one-line `usage.log("warning_shown", name=...)` beside each with a
   short stable name (do NOT log the message text).
4. **Direct calls** for the remaining events (quick capture, zoom, tab switch,
   undo/redo, save/open) at their single call sites.

Total expected footprint: one new file + ~40 one-line insertions.

## 4. The analyzer — `utils/usage_report.py` (also runnable standalone)

`python -m utils.usage_report [months=3]` → prints a plain-text report AND
writes `usage_logs/report-latest.md`:

- Sessions: count, avg/median length, sessions per weekday, time-of-day
  histogram (morning glances vs long planning sessions).
- Feature leaderboard: every event name with count — INCLUDING a hardcoded
  list of known features that show ZERO usage ("never used: bulk_edit,
  visuals_tab, …").
- Friction top-10: warnings by count, dialogs sorted by cancel-rate and by
  total time spent in them.
- Errors: grouped by `where`/`type`.
- Trend: this month vs last month per feature.

Why the report file matters: a future LLM session should read
`usage_logs/report-latest.md` first (cheap), and only dig into raw `.jsonl`
when it needs detail. Note this convention in a comment at the top of
usage_logger.py.

## 5. Options-menu entry

`Options → Record usage statistics` (checkable QAction, checked by default).
Tooltip: "Keeps a private local log of which app features you use, so
improvement suggestions can be based on real usage. Nothing leaves this
computer." Unchecking stops logging immediately; the existing files stay
(user can delete `usage_logs\` manually).

## 6. Acceptance tests
1. Fresh start → `usage_logs/usage-2026-07.jsonl` appears with `app_start`,
   `file_open`; every line is valid JSON.
2. Trigger: a Sync of edits (n/a), an impact-dialog Cancel, a start-is-auto
   warning, a search, Ctrl+Space capture, undo → all appear with correct
   outcomes.
3. Toggle logging off in Options → no new lines; on → resumes.
4. Make the log folder read-only → app works normally, no crash, no popup.
5. `python -m utils.usage_report` produces the report with a never-used list.
6. `git status` shows no `usage_logs/` (gitignored).

## 7. Coordination
- Build AFTER the Phase 1–2 work currently in progress (several ui/ files are
  mid-edit); instrument the final shapes of those features, including zoom
  (B1), capture palette (B3), catch-up (D1), waiting-on (D2).
- Per the user's workflow: confirm the event catalog above with the user
  before implementing (it defines what gets recorded about them).
