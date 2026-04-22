"""
MainWindow — outer shell for multiple projects.

Each project lives in its own ProjectWidget, which itself holds a
Tracker + Visuals tab pair. MainWindow:
  - maintains the outer project-tabs QTabWidget (up to MAX_PROJECTS),
  - owns File / Options / Edit menus,
  - persists to and loads from a single .vpmt file (v2.0).
"""
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox,
    QTabWidget, QInputDialog, QMenu,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from ui.project_widget import ProjectWidget
from models.task_node import TaskNode
from vpm_tracker_core import AppConstants


MAX_PROJECTS = 5


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(AppConstants.APP_NAME)
        self.resize(1200, 800)

        self.current_filepath = None
        self.unsaved_changes = False

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Outer tab widget — one tab per project.
        self.project_tabs = QTabWidget()
        self.project_tabs.setTabsClosable(True)
        self.project_tabs.setMovable(True)
        self.project_tabs.tabCloseRequested.connect(self.close_project_tab)
        self.project_tabs.currentChanged.connect(self.on_project_tab_changed)
        self.project_tabs.tabBarDoubleClicked.connect(self.rename_project_tab)
        self.project_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.project_tabs.customContextMenuRequested.connect(self.on_tab_context_menu)
        self.layout.addWidget(self.project_tabs)

        self.setup_menu()

        # Start with one empty project so the window isn't blank.
        self._add_project_from_data("Project 1", {}, [])
        self._seed_test_data(self.project_tabs.widget(0))

    # ---------------- project lifecycle ----------------
    def _add_project_from_data(self, name: str, metadata: dict, roots: list) -> ProjectWidget:
        proj = ProjectWidget(name=name, metadata=metadata, roots=roots)
        proj.project_changed.connect(self.on_data_changed)
        index = self.project_tabs.addTab(proj, name)
        self.project_tabs.setCurrentIndex(index)
        proj.activate()
        return proj

    def _seed_test_data(self, proj: ProjectWidget):
        """Give a brand-new blank project something to look at."""
        if proj.tree_view.root_nodes:
            return
        root = TaskNode("Project Alpha")
        phase1 = TaskNode("Phase 1", parent=root)
        root.add_child(phase1)
        task1 = TaskNode("Task 1.1", parent=phase1)
        task1.status = "Completed"
        phase1.add_child(task1)
        phase1.add_child(TaskNode("Task 1.2", parent=phase1))
        proj.tree_view.load_project([root])
        # Re-seed history so the test data is the baseline.
        proj.reset_history_baseline()

    def add_new_project(self):
        if self.project_tabs.count() >= MAX_PROJECTS:
            QMessageBox.information(
                self, "Project Limit",
                f"Maximum of {MAX_PROJECTS} projects per file."
            )
            return
        default_name = f"Project {self.project_tabs.count() + 1}"
        name, ok = QInputDialog.getText(self, "New Project", "Project name:", text=default_name)
        if not ok or not name.strip():
            return
        self._add_project_from_data(name.strip(), {}, [])
        self.on_data_changed()

    def close_project_tab(self, index: int):
        if self.project_tabs.count() <= 1:
            QMessageBox.information(
                self, "Cannot Close",
                "A file must contain at least one project."
            )
            return
        proj = self.project_tabs.widget(index)
        if isinstance(proj, ProjectWidget):
            reply = QMessageBox.question(
                self, "Close Project",
                f"Remove project '{proj.name}' from this file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            proj.close_project()
        self.project_tabs.removeTab(index)
        self.on_data_changed()

    def rename_project_tab(self, index: int):
        if index < 0:
            return
        proj = self.project_tabs.widget(index)
        if not isinstance(proj, ProjectWidget):
            return
        new_name, ok = QInputDialog.getText(self, "Rename Project", "Project name:", text=proj.name)
        if ok and new_name.strip():
            proj.name = new_name.strip()
            self.project_tabs.setTabText(index, proj.name)
            self.on_data_changed()

    def on_tab_context_menu(self, pos):
        index = self.project_tabs.tabBar().tabAt(pos)
        if index < 0:
            return
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_project_tab(index))
        menu.addAction("Close Project", lambda: self.close_project_tab(index))
        menu.addSeparator()
        menu.addAction("Add New Project…", self.add_new_project)
        menu.exec(self.project_tabs.tabBar().mapToGlobal(pos))

    def on_project_tab_changed(self, index: int):
        proj = self.project_tabs.widget(index)
        if isinstance(proj, ProjectWidget):
            proj.activate()

    def active_project(self) -> ProjectWidget:
        w = self.project_tabs.currentWidget()
        return w if isinstance(w, ProjectWidget) else None

    def all_projects(self):
        return [
            self.project_tabs.widget(i)
            for i in range(self.project_tabs.count())
            if isinstance(self.project_tabs.widget(i), ProjectWidget)
        ]

    # ---------------- menu ----------------
    def refresh_all(self):
        """Kept as a public API (hooked from View menu); no toolbar button."""
        proj = self.active_project()
        if not proj:
            return
        proj.tree_view.recalculate_all_dates()
        if proj.inner_tabs.currentIndex() == 1:
            proj.gantt_view.load_nodes(proj.tree_view.root_nodes)

    def setup_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        new_action = QAction("New Project Tab", self)
        new_action.setShortcut("Ctrl+T")
        new_action.triggered.connect(self.add_new_project)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        load_action = QAction("Load…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_project_file)
        file_menu.addAction(load_action)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As…", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_project_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        export_all_action = QAction("Export to Excel (All Projects)…", self)
        export_all_action.triggered.connect(self.export_all_to_excel)
        file_menu.addAction(export_all_action)

        export_active_action = QAction("Export Current Project to Excel…", self)
        export_active_action.triggered.connect(self.export_active_to_excel)
        file_menu.addAction(export_active_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu — undo/redo forwarded to the active project.
        edit_menu = menu.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._undo_active)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self._redo_active)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()
        refresh_action = QAction("Refresh Timeline", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_all)
        edit_menu.addAction(refresh_action)

        # Options menu (operates on the active project's config).
        options_menu = menu.addMenu("Options")
        manage_owners_action = QAction("Manage Owners…", self)
        manage_owners_action.triggered.connect(self.open_owner_manager)
        options_menu.addAction(manage_owners_action)

        calendar_action = QAction("Calendar Settings…", self)
        calendar_action.triggered.connect(self.open_calendar_settings)
        options_menu.addAction(calendar_action)

    def _undo_active(self):
        proj = self.active_project()
        if proj:
            proj.undo()

    def _redo_active(self):
        proj = self.active_project()
        if proj:
            proj.redo()

    # ---------------- options dialogs ----------------
    def open_owner_manager(self):
        proj = self.active_project()
        if not proj:
            return
        proj.activate()
        from ui.dialogs import OwnerManagerDialog
        dialog = OwnerManagerDialog(self)
        dialog.exec()

    def open_calendar_settings(self):
        proj = self.active_project()
        if not proj:
            return
        proj.activate()
        from ui.calendar_dialog import CalendarSettingsDialog
        dialog = CalendarSettingsDialog(self)
        if dialog.exec():
            proj.tree_view.recalculate_all_dates()

    # ---------------- data change tracking ----------------
    def on_data_changed(self):
        if not self.unsaved_changes:
            self.unsaved_changes = True
        self.update_title()

    def update_title(self):
        title = AppConstants.APP_NAME
        title += f" - {self.current_filepath}" if self.current_filepath else " - New File"
        if self.unsaved_changes:
            title += " *"
        self.setWindowTitle(title)

    def closeEvent(self, event):
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_project_file()
                if self.unsaved_changes:
                    event.ignore()
                    return
                event.accept()
            elif reply == QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    # ---------------- file I/O ----------------
    def save_project_file(self):
        if not self.current_filepath:
            self.save_project_file_as()
            return
        try:
            from utils.vpmt_io import save_projects
            save_projects(
                [p.to_persistable() for p in self.all_projects()],
                self.current_filepath,
            )
            self.statusBar().showMessage(f"Saved to {self.current_filepath}", 3000)
            self.unsaved_changes = False
            self.update_title()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")

    def save_project_file_as(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save File As", "", f"VPM Files (*{AppConstants.FILE_EXT})"
        )
        if filename:
            self.current_filepath = filename
            self.save_project_file()

    def load_project_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", f"VPM Files (*{AppConstants.FILE_EXT})"
        )
        if not filename:
            return
        try:
            from utils.vpmt_io import load_projects
            projects = load_projects(filename)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load file: {e}")
            return

        # Wipe existing tabs. Each project's close_project releases ConfigManager state.
        while self.project_tabs.count():
            w = self.project_tabs.widget(0)
            if isinstance(w, ProjectWidget):
                w.close_project()
            self.project_tabs.removeTab(0)

        cap = min(len(projects), MAX_PROJECTS)
        for proj_dict in projects[:cap]:
            self._add_project_from_data(
                proj_dict["name"], proj_dict.get("metadata", {}),
                proj_dict.get("roots", []),
            )

        self.current_filepath = filename
        self.unsaved_changes = False
        self.update_title()
        self.statusBar().showMessage(f"Loaded {filename}", 3000)

    # ---------------- excel export ----------------
    def export_all_to_excel(self):
        self._export_to_excel(self.all_projects())

    def export_active_to_excel(self):
        proj = self.active_project()
        if proj:
            self._export_to_excel([proj])

    def _export_to_excel(self, projects):
        if not projects:
            return
        default_name = "export.xlsx"
        if self.current_filepath:
            stem = os.path.splitext(os.path.basename(self.current_filepath))[0]
            default_name = f"{stem}.xlsx"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", default_name, "Excel Workbook (*.xlsx)"
        )
        if not filename:
            return
        try:
            from utils.excel_export import export_projects
            export_projects([p.to_persistable() for p in projects], filename)
            self.statusBar().showMessage(f"Exported to {filename}", 4000)
        except ImportError:
            QMessageBox.critical(
                self, "Missing Dependency",
                "Excel export requires the 'openpyxl' package.\n\n"
                "Install it with:\n    pip install openpyxl",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export: {e}")
