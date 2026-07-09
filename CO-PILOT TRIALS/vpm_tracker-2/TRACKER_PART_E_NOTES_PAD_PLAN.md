# VPM Tracker — Part E: OneNote-Style Notes Pad (2026-07-08)

**Audience:** an LLM/developer implementing in this folder.
**Origin:** the Phase-2 B3 "capture palette" rewrite shrank note capture into a
tiny popup and ORPHANED the Notes pad (no menu/button opens it; only a Ctrl+F
search-result click does). User wants the opposite: go back to opening the pad,
make it **bigger**, and make it **OneNote-like** so it's easy to pile lots of
things in.

**User-approved direction:**
- Layout: **bigger floating window** (resizable, remembers size/position).
- Capture: **multi-line capture box** + **"similar to OneNote, easy to add more
  things."**

**Keep working (do not regress):** drag a note onto the grid → becomes a task or
appends to a task's Notes (`NOTE_MIME` payload, see `ui/tree_grid_view.py`
`_handle_note_drop`); `@name` owner tags; per-project persistence inside the
`.vpmt` file; inclusion in Ctrl+F "Search Everything".

---

## Current state (what exists today)

- `ui/notes_panel.py` — `NotesPanel`: header + hint + `NotesListWidget` (a
  `QListWidget` of one-line, editable, draggable note strings) + a single-line
  `QLineEdit` capture box (Enter adds a line).
- `ui/project_widget.py` — the pad lives in a floating `QDialog`
  (`self.notes_dialog`, 520×520, hidden on close) built in `_build_ui`; opened
  by `show_notes_and_capture()`.
- Persistence: `to_persistable()` / snapshots store `"notes": [str, ...]`
  (a flat list of line strings) inside each project in the `.vpmt`.
- **Bug to fix as part of this:** `show_notes_and_capture()` has no entry point.

---

## Decision points (CONFIRM with user before building)

### DP1 — Enter key behavior in the multi-line box
A multi-line box needs a rule for "new line vs. save the note." Recommended
(chat-app familiar): **Enter = save the note; Shift+Enter = new line within the
note.** Pasting text that contains blank lines creates one note per blank-line-
separated block. (Alt option: a visible "Add note" button + Ctrl+Enter to save.)

### DP2 — Storage format migration (flat strings → note objects)
OneNote-style features (types, timestamps, checkboxes, pinning, sections) need
each note to carry fields, so `"notes"` changes from `[str]` to `[obj]`:

```json
{"text": "...", "type": "note|todo|heading", "done": false,
 "pinned": false, "ts": "2026-07-08 14:32"}
```

**Back-compat is mandatory:** on load, a bare string becomes
`{"text": s, "type": "note"}`. On save, always write objects. Old files must
open cleanly; a file saved by the new app won't open in the pre-migration app
(acceptable — same as prior version bumps). Bump `CURRENT_VERSION` in
`utils/vpmt_io.py` and let the existing "older file version" notice handle it.
Update `NotesPanel.get_notes()/load_notes()`, `_parse_owner_tags` callers, the
drag payload builder, and Ctrl+F search (`run_search` reads
`proj.notes_panel.get_notes()` — must read `.text`).

---

## Phase A — the must-haves the user picked  ✅ IMPLEMENTED 2026-07-08

**Status:** DONE in this session (this Claude session made the edits directly).
Decisions taken: DP1 = Enter saves / Shift+Enter newline; DP2 = NOT migrated yet
(Phase A keeps notes as plain-text strings — multi-line notes are just strings
with "\n"; the object-format migration is only needed for Phase B and remains
open). Files changed: `ui/main_window.py` (retired the palette `_quick_capture`,
added `_open_notes_pad`, Ctrl+Space + Ctrl+Shift+N + Ctrl+Shift+Space + Edit
menu all open the pad), `ui/notes_panel.py` (multi-line `CaptureBox`,
`NOTE_SEP`-joined drag payload, note-aware `remove_line`), `ui/tree_grid_view.py`
(`_handle_note_drop` splits on `NOTE_SEP`; new `_split_note`; multi-line note →
one task with first line = name, rest = the task's Notes), `ui/project_widget.py`
(pad default 760×640, geometry remembered in QSettings `notes_pad_geometry`).
Verified offscreen: multi-line capture, drag payload, promote-to-task, boot.
Known limitation: double-clicking an existing multi-line note edits it with
Qt's single-line inline editor (collapses it) — acceptable for A; Phase B's
card editors fix it.

### (original Phase A spec below, for reference)

### A1. Restore the pad's entry points (fix the orphan)
- `Edit → Open Notes Pad` menu action, shortcut **Ctrl+Shift+N**
  (`ApplicationShortcut`), calls `active_project().show_notes_and_capture()`.
- **Ctrl+Space** opens the SAME pad (not the tiny palette) with focus in the
  capture box — this is the revert the user asked for. Remove/retire the
  frameless popup in `_quick_capture`, or repoint it at `show_notes_and_capture`.
- Keep `Ctrl+Shift+Space` as a secondary binding (IME-collision fallback).

### A2. Bigger, resizable, remembered window
- Raise default size (e.g. 720×640) and save/restore geometry in
  `QSettings("VPM","VPMTracker")` key `notes_pad_geometry` on move/resize/close.
- Ensure the dialog is resizable (it already is a QDialog; verify no fixed size).

### A3. Multi-line capture box
- Replace the bottom `QLineEdit` with a `QPlainTextEdit` (3–4 lines tall,
  grows to ~10). Implement DP1's Enter/Shift+Enter rule via a keyPressEvent
  override. Multi-block paste → multiple notes.
- Placeholder: "Jot anything… Enter saves, Shift+Enter for a new line."

### A4. Notes become multi-line blocks (not one-liners)
- Switch the list from one-line items to blocks that can hold multiple lines
  (word-wrapped, full text visible; no more silent truncation to first line).
  Simplest robust route: keep `QListWidget` but size each row to its content
  (`setSizeHint` from the wrapped text), OR move to a vertical scroll area of
  small `QPlainTextEdit`/label "cards." Cards read better for OneNote feel;
  pick based on effort and keep drag-to-grid intact.

**Phase A acceptance:** Ctrl+Space and Ctrl+Shift+N both open the big pad; type
a 3-line note, Enter saves it as one block showing all 3 lines; paste 4
blank-line-separated blocks → 4 notes; window reopens at last size; drag a note
to the grid still makes a task; old `.vpmt` files load; Ctrl+F still finds notes.

---

## Phase B — the "OneNote, easy to add more things" upgrades (approve after A)

### B1. Note types via a per-note toggle (right-click or a small ◑ button)
- **Note** (plain text), **To-do** (checkbox that ticks off — strike-through
  when done), **Heading/Section** (bold, groups the notes under it).
- To-do + note blocks stay draggable to the grid; headings are pad-only.

### B2. Pin to top
- Star a note; pinned notes sort above the rest. Journal nothing (pad-local).

### B3. Auto date-stamp (optional, per the user's other pick list)
- New notes get `ts`; show a small gray date on each card; toggle in the pad
  header to show/hide.

### B4. Sections / collapse
- Heading blocks (B1) can collapse the notes beneath them, so a long pad stays
  scannable ("Lab", "CFD", "Ideas").

### B5. Reorder by dragging within the pad
- Drag a card up/down to reorder (distinct from dragging OUT to the grid —
  internal move vs. `NOTE_MIME` external drop; guard the two so they don't
  conflict).

**Phase B acceptance:** toggle a note to a to-do and tick it (persists); pin a
note (stays on top after reload); add a heading and collapse its section;
reorder two notes; everything survives save/load.

---

## Explicitly deferred / heavier (discuss before attempting)
- **Rich text** (bold/bullets/colors): changes storage to HTML and complicates
  drag-to-task (tasks want plain text). Only if the user asks.
- **Images / file attachments / multiple pages:** true OneNote territory, but
  images embedded in the `.vpmt` (base64) would bloat the file badly (it's
  already ~175 KB of JSON). If wanted, store attachments as separate files in a
  sidecar folder next to the `.vpmt` and reference them — a separate plan.
- **System-wide capture hotkey** (capture when the app isn't focused): needs a
  Win32 `RegisterHotKey` wrapper or the `keyboard` package — separate approval.

---

## Coordination
- Files touched overlap with active Phase-1/2 work (`ui/main_window.py`,
  `ui/project_widget.py`, `ui/notes_panel.py` are in flux; a `VERSIONS\` folder
  exists). Rebase on top of that work; don't edit concurrently in two sessions.
- Per the user's workflow: pitch Phase A in plain language, confirm DP1 + DP2,
  build A, then pitch Phase B item-by-item.
