"""
ProjectWidget — one project's Tracker + Visuals pair.

The outer MainWindow creates one ProjectWidget per project tab. Each widget
owns its own TreeGridView, GanttChartWidget, metadata, and undo stack, and
registers itself with ConfigManager so scheduler calls always resolve
settings against the active project.
"""
import uuid
from typing import Dict, List

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence, QShortcut

from models.task_node import TaskNode
from ui.tree_grid_view import TreeGridView
from ui.gantt_chart import GanttChartWidget
from utils.config_manager import ConfigManager
from utils.history import HistoryStack


class ProjectWidget(QWidget):
    # Fires when anything in this project changes (for the dirty flag / title).
    project_changed = pyqtSignal()

    def __init__(self, name: str = "Project 1", metadata: Dict = None,
                 roots: List[TaskNode] = None, parent=None):
        super().__init__(parent)
        self.project_id = f"proj-{uuid.uuid4().hex[:8]}"
        self.name = name or "Project 1"
        self.history = HistoryStack(max_depth=50)

        # Register metadata into the per-project config store.
        ConfigManager.register_project(self.project_id, metadata or {})

        self._build_ui()

        # Initial load — important to do after ConfigManager is registered
        # so the scheduler reads the right holidays/weekend rules.
        self._activate_config()
        self.tree_view.load_project(list(roots) if roots else [])

        # Undo timing: we snapshot AFTER a mutation, but push the *previous*
        # snapshot (held in _last_snapshot). That way undo restores the state
        # the user saw *before* the edit, not the one they just produced.
        self._last_snapshot = self.get_snapshot()
        self._restoring = False  # suppress history pushes during undo/redo restore
        self.tree_view.item_changed_signal.connect(self._on_tree_changed)

        # Ctrl+Z / Ctrl+Y shortcuts — ApplicationShortcut scope so they fire
        # even when focus is inside the tree's cell editor.
        for seq, slot in (
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.Redo, self.redo),
            (QKeySequence("Ctrl+Y"), self.redo),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(slot)

    # ---- UI ----
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inner_tabs = QTabWidget()
        layout.addWidget(self.inner_tabs)

        self.tree_view = TreeGridView()
        self.inner_tabs.addTab(self.tree_view, "Tracker")

        self.gantt_view = GanttChartWidget()
        self.gantt_view.main_window = self  # keeps legacy attr for the gantt code
        self.inner_tabs.addTab(self.gantt_view, "Visuals")

        self.inner_tabs.currentChanged.connect(self._on_inner_tab_changed)

    def _on_inner_tab_changed(self, index: int):
        if index == 1:  # Visuals
            self.gantt_view.load_nodes(self.tree_view.root_nodes)

    # ---- lifecycle ----
    def activate(self):
        """Called when this project's tab becomes visible."""
        self._activate_config()
        if self.inner_tabs.currentIndex() == 1:
            self.gantt_view.load_nodes(self.tree_view.root_nodes)

    def close_project(self):
        """Called before the tab is removed — release per-project state."""
        ConfigManager.unregister_project(self.project_id)

    def _activate_config(self):
        ConfigManager.set_active_project(self.project_id)

    # ---- snapshot / history ----
    def get_snapshot(self) -> Dict:
        """Serialize current state to a plain dict (safe to deepcopy)."""
        from utils.config_manager import ConfigManager as CM
        return {
            "name": self.name,
            "metadata": CM.snapshot_project(self.project_id),
            "tasks": [n.to_dict() for n in self.tree_view.root_nodes],
        }

    def load_snapshot(self, snap: Dict):
        """Restore state from a snapshot dict (reverse of get_snapshot)."""
        if not snap:
            return
        self.name = snap.get("name", self.name)
        md = snap.get("metadata", {}) or {}
        ConfigManager.register_project(self.project_id, md)
        self._activate_config()

        roots = [TaskNode.from_dict(d) for d in (snap.get("tasks") or [])]
        # Guard against the restore's own itemChanged storms flooding history.
        self._restoring = True
        try:
            self.tree_view.load_project(roots)
        finally:
            self._restoring = False

    def reset_history_baseline(self):
        """Drop all history and pin the current state as the new undo baseline.

        Called after programmatic loads (file open, test-data seed, load_snapshot
        from an external snapshot) so that Ctrl+Z can't rewind past the user's
        intended starting point.
        """
        self.history.clear()
        self._last_snapshot = self.get_snapshot()

    def undo(self):
        if not self.history.can_undo():
            return
        current = self.get_snapshot()
        prev = self.history.undo(current)
        if prev is not None:
            self.load_snapshot(prev)
            self._last_snapshot = prev
            self.project_changed.emit()

    def redo(self):
        if not self.history.can_redo():
            return
        current = self.get_snapshot()
        nxt = self.history.redo(current)
        if nxt is not None:
            self.load_snapshot(nxt)
            self._last_snapshot = nxt
            self.project_changed.emit()

    def _on_tree_changed(self, *_):
        """Called every time a task is mutated through the tree widget.

        We push the *previous* snapshot (captured in _last_snapshot before
        the mutation landed) so that Ctrl+Z restores what the user saw
        before their edit, not the edit itself. Then we refresh
        _last_snapshot to the new post-edit state for next time.
        """
        if self._restoring:
            return
        self.history.push(self._last_snapshot)
        self._last_snapshot = self.get_snapshot()
        self.project_changed.emit()

    # ---- convenience used by MainWindow ----
    def to_persistable(self) -> Dict:
        """Shape matching utils.vpmt_io.save_projects()."""
        from utils.config_manager import ConfigManager as CM
        return {
            "name": self.name,
            "metadata": CM.snapshot_project(self.project_id),
            "roots": list(self.tree_view.root_nodes),
        }
