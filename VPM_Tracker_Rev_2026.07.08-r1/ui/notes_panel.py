"""
NotesPanel — a per-project scratch pad (floating notepad window).

Free-form notes that live entirely OUTSIDE the task tree, so they never touch
the schedule, the timeline, or the visuals. Each note can be dragged into the
Tracker grid:

  - dropped ON a task   -> appended to that task's Notes (timestamped)
  - dropped on empty    -> promoted to a new, auto-scheduled task
                           (a multi-line note: first line = task name,
                            the rest becomes the new task's Notes)

Type @Name in a note to tag who you are waiting on when it is promoted to a
task. Notes persist inside the .vpmt (per project) and are included in Ctrl+F
"Search Everything".

Capture: a MULTI-LINE box at the bottom — Enter saves the note, Shift+Enter
adds a new line within it, so long notes are easy. The note lands in the list
and the box clears for the next thought. Ctrl+Space (or Ctrl+Shift+N) from the
main window opens this pad and focuses the box.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
                             QLabel, QPlainTextEdit, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData

# Custom drag payload identifying note(s) dragged out of the pad.
NOTE_MIME = "application/x-vpm-note"
# Record separator between distinct notes in the drag payload. A single note
# may itself span multiple lines ("\n"), so notes cannot be separated by "\n" —
# this ASCII record-separator keeps note boundaries unambiguous.
NOTE_SEP = "\x1e"


class CaptureBox(QPlainTextEdit):
    """Multi-line capture box. Enter submits; Shift+Enter inserts a newline."""

    submitted = pyqtSignal()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class NotesListWidget(QListWidget):
    """A list of editable notes (each may be multi-line) draggable to the tree."""

    lines_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.setWordWrap(True)
        self.itemChanged.connect(lambda _i: self.lines_changed.emit())

    def mimeData(self, items):
        """Carry the selected note(s) as our custom note MIME (plus plain text
        so the drag also works as a fallback into external apps). Notes are
        joined by NOTE_SEP so a multi-line note survives as one unit."""
        md = QMimeData()
        notes = [i.text() for i in items if i.text().strip()]
        md.setData(NOTE_MIME, NOTE_SEP.join(notes).encode("utf-8"))
        md.setText("\n\n".join(notes))
        return md

    def keyPressEvent(self, event):
        # Delete removes the selected note(s) when not mid-edit.
        if (event.key() == Qt.Key.Key_Delete
                and self.state() != QAbstractItemView.State.EditingState):
            for it in self.selectedItems():
                self.takeItem(self.row(it))
            self.lines_changed.emit()
            return
        super().keyPressEvent(event)

    def add_line(self, text=""):
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.addItem(item)
        self.lines_changed.emit()
        return item


class NotesPanel(QWidget):
    """Docked pad: header + draggable note list + multi-line capture box."""

    notes_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("📝 Notes")
        header.setStyleSheet("font-weight:bold; font-size:13px;")
        layout.addWidget(header)

        hint = QLabel(
            "Drag a note onto the grid → it becomes a task right where you "
            "drop it (first line = task name). Drop on a task's Notes column → "
            "adds it to that task instead. Tag who you are waiting on with @name.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#777; font-size:10px;")
        layout.addWidget(hint)

        self.list = NotesListWidget()
        layout.addWidget(self.list, 1)

        self.capture = CaptureBox()
        self.capture.setPlaceholderText(
            "Jot anything…   Enter saves,  Shift+Enter = new line")
        self.capture.setMinimumHeight(72)
        self.capture.setMaximumHeight(180)
        self.capture.submitted.connect(self._on_capture_enter)
        layout.addWidget(self.capture)

        self.list.lines_changed.connect(self.notes_changed.emit)

    # ---- fast capture ----
    def _on_capture_enter(self):
        text = self.capture.toPlainText().strip()
        if not text:
            return
        self.list.add_line(text)
        self.capture.clear()
        self.capture.setFocus()

    def focus_capture(self):
        self.capture.setFocus()
        self.capture.selectAll()

    # ---- persistence helpers ----
    def load_notes(self, lines):
        was = self.list.blockSignals(True)
        try:
            self.list.clear()
            for ln in (lines or []):
                if str(ln).strip():
                    self.list.add_line(str(ln))
        finally:
            self.list.blockSignals(was)

    def get_notes(self):
        return [self.list.item(i).text()
                for i in range(self.list.count())
                if self.list.item(i).text().strip()]

    def remove_line(self, raw):
        """Drop the note(s) that were just promoted into the tracker. `raw` is
        the drag payload — notes joined by NOTE_SEP (falls back to whole-string
        match for plain-text payloads)."""
        raw = raw or ""
        parts = raw.split(NOTE_SEP) if NOTE_SEP in raw else [raw]
        targets = set(p.strip() for p in parts if p.strip())
        if not targets:
            return
        for i in range(self.list.count() - 1, -1, -1):
            if self.list.item(i).text().strip() in targets:
                self.list.takeItem(i)
        self.notes_changed.emit()
