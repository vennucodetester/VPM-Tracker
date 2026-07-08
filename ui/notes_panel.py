"""
NotesPanel — a per-project, docked scratch pad.

Replaces the old in-tree "Inbox": free-form note lines that live entirely
OUTSIDE the task tree, so they never touch the schedule, the timeline, or
the visuals. Each line can be dragged into the Tracker grid:

  - dropped ON a task   -> appended to that task's Notes (timestamped)
  - dropped on empty    -> promoted to a new, auto-scheduled task

Type @Name in a line to tag an owner; it pre-fills when the line is promoted
to a task. The pad's lines persist inside the .vpmt (per project) and are
included in Ctrl+F "Search Everything".

Fast capture: a single-line box at the bottom — type, press Enter, it lands
in the list and the box clears for the next thought. Ctrl+Space (from the
main window) shows the pad and focuses that box.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
                             QLabel, QLineEdit, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData

# Custom drag payload identifying a note line dragged out of the pad.
NOTE_MIME = "application/x-vpm-note"


class NotesListWidget(QListWidget):
    """A list of editable note lines that can be dragged into the tracker."""

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
        """Carry the selected line(s) as our custom note MIME (plus plain text
        so the drag also works as a fallback)."""
        md = QMimeData()
        text = "\n".join(i.text() for i in items if i.text().strip())
        md.setData(NOTE_MIME, text.encode("utf-8"))
        md.setText(text)
        return md

    def keyPressEvent(self, event):
        # Delete removes the selected line(s) when not mid-edit.
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
    """Docked pad: header + draggable line list + fast-capture box."""

    notes_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QLabel("📝 Notes")
        header.setStyleSheet("font-weight:bold; font-size:12px;")
        layout.addWidget(header)

        hint = QLabel(
            "Drag a line onto the grid → it becomes a task right where you "
            "drop it. Drop on a task's Notes column → adds it to that task "
            "instead. Tag an owner with @name.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#777; font-size:10px;")
        layout.addWidget(hint)

        self.list = NotesListWidget()
        layout.addWidget(self.list, 1)

        self.capture = QLineEdit()
        self.capture.setPlaceholderText("Jot a note…  (Enter to add)")
        self.capture.returnPressed.connect(self._on_capture_enter)
        layout.addWidget(self.capture)

        self.list.lines_changed.connect(self.notes_changed.emit)

    # ---- fast capture ----
    def _on_capture_enter(self):
        text = self.capture.text().strip()
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
        """Drop the line(s) that were just promoted into the tracker."""
        targets = set(l for l in (raw or "").split("\n") if l.strip())
        if not targets:
            return
        for i in range(self.list.count() - 1, -1, -1):
            if self.list.item(i).text() in targets:
                self.list.takeItem(i)
        self.notes_changed.emit()
