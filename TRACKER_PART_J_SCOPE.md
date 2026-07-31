# Part J — Data safety, menu fixes, cleanup: SCOPE ONLY (2026-07-24)

**Audience:** the implementing LLM. Read `Critical md files\IMPLEMENTATION_METHODOLOGY.md`
first. Working copy = THIS folder. CRLF line endings — preserve them.

Everything below is either a REPRODUCED defect or an explicit user decision.
Nothing here is a suggestion to improve on. Build in the order given: J1 is the
only item where the cost of skipping it is lost work.

---

## J1 — Stop two app windows from destroying each other's work (CRITICAL)

**Evidence (one week of telemetry, 29 real sessions):** seven overlapping
instance pairs, ALL on the same `.vpmt`. Worst case 2026-07-11 23:21 — one
window stayed open 51 minutes while five other instances opened, edited and
saved that same file underneath it. Two `JSONDecodeError` load failures on
2026-07-11 00:52 occurred inside an overlap window (two instances launched
16 s apart, both loading the same file).

Today there is NO protection: no lock, no "already open" warning, no detection
that the file changed on disk. Whoever saves last silently wins. The existing
atomic `.tmp` + `os.replace` save protects against a crash mid-write, NOT
against two processes.

### J1a. Lock file
- On successful load/save of `<file>.vpmt`, write `<file>.vpmt.lock` containing
  JSON: `{"pid": int, "host": str, "started": ISO8601, "heartbeat": ISO8601}`.
- Refresh `heartbeat` on every autosave tick (the 3-minute timer already runs).
- Remove the lock on clean exit (`closeEvent`) and on switching files.
- **Stale-lock rule:** a lock whose `heartbeat` is older than 15 minutes, OR
  whose `pid` is not running on this host, is stale → ignore it and take over
  silently. This is mandatory; without it a crash locks the user out of his own
  file forever.

### J1b. What the second window does
On open, if a live lock exists, show ONE dialog naming the file and when the
other window last touched it, with three buttons:
- **Open read-only (recommended)** — loads normally but sets a
  `read_only` flag: autosave disabled, Save/Save As→Save disabled, and a
  persistent amber banner across the top: "Read-only — this file is open in
  another window."
- **Open a copy** — loads and immediately does Save-As to
  `<name> (copy 2026-07-24 2131).vpmt`, which then becomes the working file.
- **Take over** — only after a second confirm spelling out the risk
  ("the other window's unsaved changes will be lost when it saves").

### J1c. Detect the file changing underneath you
- Record the file's mtime + size at load and after every save.
- Before ANY save (manual or autosave), re-stat the file. If it differs from
  what this window last wrote → do NOT overwrite. Show: "This file was changed
  by another window since you opened it," with **Save as a copy** /
  **Overwrite anyway** / **Cancel**.
- Also re-check on window focus-in: if the file changed on disk and this window
  has NO unsaved changes, offer "Reload the newer version?".

### J1d. Telemetry
Log `lock_conflict {choice}` (readonly/copy/takeover), `stale_lock_cleared`,
`external_change_detected {action}`. These tell us next time whether the
guardrail is working or annoying.

**Acceptance:**
1. Open file in window A; open same file in window B → B shows the dialog;
   read-only choice → B's autosave never fires and its Save is disabled.
2. Kill window A with Task Manager, reopen → lock is stale by pid → opens
   normally, no dialog, no orphan lock left behind.
3. With A and B open on the same file, save in A, then edit+save in B →
   B warns about the external change instead of silently overwriting.
4. Single-window normal use: zero new dialogs, lock created and removed,
   no `.lock` files left after a clean exit.

---

## J2 — Remove "Waiting On" completely (user decision: "I will never use it")

**Evidence:** zero `waiting_set` / `waiting_clear` events in a full week;
one 74-second visit to the manager dialog and never again. The column occupies
prime grid space and its two context-menu entries sit ABOVE the one he uses
most (see J3).

Remove from the UI:
- `vpm_tracker_core.py` — drop `"Waiting On"` from `Columns.NAMES`, remove the
  `WAITING` index, decrement the following indices, and fix `COUNT`.
  **This ripples** — audit every `Columns.` use: delegates, `update_from_node`,
  `on_item_changed`, copy/paste, filters, `excel_export`, and the timeline.
  (IMPLEMENTATION_METHODOLOGY Rule 5 names this exact trap.)
- `ui/tree_grid_view.py` — delete `WaitingOnDelegate`, its
  `setItemDelegateForColumn`, the `Mark Waiting On...` / `Clear Waiting`
  context actions, and the waiting branch in `on_item_changed`.
- `ui/main_window.py` — delete the `Manage Waiting People…` menu action, its
  handler, and the Waiting-On list dialog; drop waiting text from
  `Search Everything`.
- `ui/focus_view.py` — remove the "waiting on X" fragments from the Visuals
  narrative.

Keep in the MODEL only: `waiting_on` / `waiting_since` fields plus their
`to_dict`/`from_dict` lines, so existing `.vpmt` files still load and re-save
without data loss. They simply become dormant. Do not delete model fields.

**Acceptance:** grid shows no Waiting On column; no waiting entries in any
menu; an existing file with `waiting_on` values loads, saves, and reloads with
those values intact in the JSON; Excel export has no waiting column.

---

## J3 — "Set Predecessor" belongs at the TOP of the right-click menu

**User:** "right click set predecessor is something I need often, I don't want
that buried inside options somewhere."

Today it is the ~11th entry (`tree_grid_view.py` ~line 1165), below Add Child,
the two Waiting entries, Cut/Copy/Paste, Indent/Outdent, Bulk Paste and
Expand All.

New order for the task right-click menu (top to bottom):
1. **Set Predecessor (click target)**
2. **Clear Predecessor** — enabled only when one is set
3. **Jump to Predecessor** — only when one is set
   *(separator)*
4. Add Child Task
5. Indent / Outdent
   *(separator)*
6. Cut / Copy / Paste Below
   *(separator)*
7. Delete Task(s)
   *(separator)*
8. **More ▸** submenu — everything else, unchanged in behaviour:
   Pick from list… (advanced), Set/Unset Manual Date, Update Baseline
   (not a delay), Mark On Track…, Set Delay to…, Bulk Paste Children…,
   Expand All.

Rationale: top-level = what he uses weekly; the submenu keeps the rest without
cluttering. No behaviour changes, pure reordering/regrouping.

**Acceptance:** right-click a task → the first three entries are the
predecessor actions; every previously available action is still reachable
(top level or under More); Ctrl+L still starts linking.

---

## J4 — Always allow a comment on a delay

**User:** "I was not able to enter comments at every delay."

Current behaviour (`tree_grid_view.py` ~line 292): the reason box is created
ONLY when `new_slip > 0`; otherwise the dialog shows "No new unlogged delay.
History is shown read-only" and there is no way to type anything.

Change: always show the reason field.
- `new_slip > 0` → unchanged (logs a revision with that slip).
- `new_slip <= 0` → label reads `Add a note (no schedule change)`; on OK with
  non-empty text, append a revision with `"slip": 0` and the typed reason so it
  joins the same Rev trail and the same auto-note line in the task's Notes.
- Empty text + OK → nothing recorded (unchanged).

Do NOT change anything else about this dialog — the user has twice asked that
the delay prompt itself stay as is.

**Acceptance:** on-track task → dialog offers a note box; typing one adds a
`slip: 0` revision visible in the trail and a dated line in the task's Notes;
a delayed task behaves exactly as before.

---

## J5 — Fix the garbled symbols in the Visuals tab (REPRODUCED)

**User:** "a lot of symbols that I don't recognise, especially on the visual tab."

**Root cause — proven at byte level:** `ui/focus_view.py` is mojibake. Some
tool read the UTF-8 file as Windows-1252 and wrote it back, so every em dash,
ellipsis and bullet is now stored as its double-encoded form:
- mojibake fingerprint (`C3 A2 E2 82 AC`) — **9 occurrences**
- 37 suspicious characters total
- proper UTF-8 em dash (`E2 80 94`) — **0 occurrences**, though the prose
  clearly uses them
- the file still decodes as valid UTF-8 (mojibake always does), which is why
  no tool has flagged it.

`ui/focus_view.py` is the ONLY affected file — the other modules scan clean.

**Fix:** repair the text, then guard against a recurrence.
```python
raw = open(p, "rb").read().decode("utf-8")
fixed = raw.encode("cp1252").decode("utf-8")   # verified: 0 residual bad chars
open(p, "w", encoding="utf-8", newline="\r\n").write(fixed)
```
Verify BEFORE committing: `fixed` must contain real `—`, `…`, `•`, `·`, and the
mojibake fingerprint count must be 0. Byte-compare the rest of the file is
unchanged apart from those sequences.

**Guard:** add a tiny check (test or a few lines in the rev script) that fails
if any source file contains the fingerprint `Ã¢â‚¬` / `â€`. Also state the rule
in `Critical md files\IMPLEMENTATION_METHODOLOGY.md`: **always read and write
source files as UTF-8 explicitly; never let PowerShell's default ANSI codepage
touch a `.py` file** (`Get-Content`/`Set-Content` without `-Encoding utf8` is
how this happened).

**Acceptance:** fingerprint count 0 across all `.py`; the Visuals tab renders
proper dashes/bullets; app boots and the Visuals tab paints without exception.

---

## Out of scope (do not build here)
- The "Today"/status screen (biggest opportunity from the telemetry, but it
  needs its own scope and user sign-off).
- Any Catch-Up redesign — the user has not re-tested the per-row-notes version
  yet; wait for his verdict.
- Telemetry instrumentation gaps (grid edits, notepad edits, timeline toggles)
  — worth doing, but scope separately.
