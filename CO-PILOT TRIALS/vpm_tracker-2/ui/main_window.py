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
    QTabWidget, QInputDialog, QMenu, QLabel,
)
from PyQt6.QtGui import QAction, QKeySequence, QShortcut, QFont
from PyQt6.QtCore import Qt, QSettings, QStandardPaths

from ui.project_widget import ProjectWidget
from models.task_node import TaskNode
from vpm_tracker_core import AppConstants
from utils import usage_logger


MAX_PROJECTS = 5


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{AppConstants.APP_NAME} - {AppConstants.REVISION_LABEL}")
        self.resize(1200, 800)

        self.current_filepath = None
        self.unsaved_changes = False
        self.settings = QSettings("VPM", "VPMTracker")
        self._search_dialog = None
        self._loading_startup = True

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
        self._setup_global_shortcuts()
        self.statusBar().addPermanentWidget(QLabel(AppConstants.REVISION_LABEL))
        self._apply_saved_zoom()

        if not self._restore_startup_state():
            self._add_project_from_data("Project 1", {}, [])
            self._seed_test_data(self.project_tabs.widget(0))
        self._loading_startup = False
        self._update_overdue_action()

        # Autosave: every 3 minutes, if a file path exists and there are
        # unsaved changes, save silently. A crash costs minutes, not a day.
        from PyQt6.QtCore import QTimer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(3 * 60 * 1000)

    def _setup_global_shortcuts(self):
        self._notepad_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self._notepad_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._notepad_shortcut.activated.connect(lambda: self._open_notes_pad(via="ctrl_space"))

    def _autosave(self):
        if not self.unsaved_changes:
            return
        try:
            from utils.vpmt_io import save_projects
            target = self.current_filepath or self._recovery_path()
            save_projects(
                [p.to_persistable() for p in self.all_projects()],
                target,
                rotate_backups=False,
            )
            if self.current_filepath:
                usage_logger.log("file_save", manual=False)
                self.unsaved_changes = False
                self.update_title()
                self.statusBar().showMessage("Autosaved", 2000)
            else:
                self.statusBar().showMessage("Recovery copy saved", 2000)
        except Exception:
            pass  # autosave must never interrupt the user; manual save will surface errors

    def _recovery_path(self) -> str:
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), ".vpm_tracker")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "recovery.vpmt")

    def _restore_startup_state(self) -> bool:
        recovery = self._recovery_path()
        if os.path.exists(recovery):
            last_saved = self.settings.value("recovery_last_imported_mtime", 0, type=float) or 0
            recovery_mtime = os.path.getmtime(recovery)
            if recovery_mtime > last_saved:
                reply = QMessageBox.question(
                    self, "Restore Recovery File?",
                    "A recovery copy from an unsaved file was found.\n\n"
                    "Restore it now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                usage_logger.log("autosave_recovery_offered")
                if reply == QMessageBox.StandardButton.Yes:
                    usage_logger.log("autosave_recovery_accepted")
                    if self._load_path(recovery, prompt_unsaved=False, is_recovery=True):
                        self.current_filepath = None
                        self.unsaved_changes = True
                        self.settings.setValue("recovery_last_imported_mtime", recovery_mtime)
                        self.update_title()
                        return True
                else:
                    self.settings.setValue("recovery_last_imported_mtime", recovery_mtime)

        for path in self._recent_files():
            if self._load_path(path, prompt_unsaved=False):
                return True
        return False

    # ---------------- project lifecycle ----------------
    def _add_project_from_data(self, name: str, metadata: dict, roots: list,
                               journal: list = None,
                               notes: list = None) -> ProjectWidget:
        proj = ProjectWidget(name=name, metadata=metadata, roots=roots,
                             journal=journal, notes=notes)
        proj.project_changed.connect(self.on_data_changed)
        index = self.project_tabs.addTab(proj, name)
        self.project_tabs.setCurrentIndex(index)
        proj.activate()
        if hasattr(proj.tree_view, "apply_zoom"):
            proj.tree_view.apply_zoom(getattr(self, "_zoom_factor", 1.0))
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
        self._update_overdue_action()
        usage_logger.log("tab_switch", to=f"project:{index}")

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
    def _wire_action(self, action: QAction, slot, name: str = None):
        label = name or action.text()
        action.triggered.connect(lambda *args: (usage_logger.log("menu_action", name=label), slot()))

    def setup_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        new_action = QAction("New Project Tab", self)
        new_action.setShortcut("Ctrl+T")
        self._wire_action(new_action, self.add_new_project)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        load_action = QAction("Load…", self)
        load_action.setShortcut("Ctrl+O")
        self._wire_action(load_action, self.load_project_file)
        file_menu.addAction(load_action)

        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        self._wire_action(save_action, self.save_project_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As…", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        self._wire_action(save_as_action, self.save_project_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        export_all_action = QAction("Export to Excel (All Projects)…", self)
        self._wire_action(export_all_action, self.export_all_to_excel)
        file_menu.addAction(export_all_action)

        export_active_action = QAction("Export Current Project to Excel…", self)
        self._wire_action(export_active_action, self.export_active_to_excel)
        file_menu.addAction(export_active_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        self._wire_action(exit_action, self.close)
        file_menu.addAction(exit_action)

        # Edit menu — undo/redo forwarded to the active project.
        edit_menu = menu.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._wire_action(undo_action, self._undo_active)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._wire_action(redo_action, self._redo_active)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()
        refresh_action = QAction("Refresh All", self)
        refresh_action.setShortcut("F5")
        self._wire_action(refresh_action, self._refresh_all)
        edit_menu.addAction(refresh_action)

        edit_menu.addSeparator()
        delay_summary_action = QAction("View Delay Summary…", self)
        self._wire_action(delay_summary_action, self._show_delay_summary)
        edit_menu.addAction(delay_summary_action)

        self.catch_up_action = QAction("Catch Up on Overdue...", self)
        self._wire_action(self.catch_up_action, self._show_catch_up, "Catch Up on Overdue")
        edit_menu.addAction(self.catch_up_action)

        waiting_action = QAction("View Waiting-On List...", self)
        self._wire_action(waiting_action, self._show_waiting_list)
        edit_menu.addAction(waiting_action)

        journal_action = QAction("View Activity Journal…", self)
        self._wire_action(journal_action, self._show_journal)
        edit_menu.addAction(journal_action)

        edit_menu.addSeparator()
        search_action = QAction("Search Everything…", self)
        search_action.setShortcut("Ctrl+F")
        self._wire_action(search_action, self._show_search)
        edit_menu.addAction(search_action)

        capture_action = QAction("Open Notes Pad…", self)
        capture_action.setShortcuts(["Ctrl+Shift+N", "Ctrl+Shift+Space"])
        capture_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._wire_action(capture_action, lambda: self._open_notes_pad(via="menu"), "Open Notes Pad")
        edit_menu.addAction(capture_action)

        edit_menu.addSeparator()
        zoom_in_action = QAction("Zoom In", self)
        self._wire_action(zoom_in_action, lambda: self._adjust_zoom(0.1))
        edit_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        self._wire_action(zoom_out_action, lambda: self._adjust_zoom(-0.1))
        edit_menu.addAction(zoom_out_action)

        zoom_reset_action = QAction("Reset Zoom", self)
        self._wire_action(zoom_reset_action, lambda: self._set_zoom(1.0))
        edit_menu.addAction(zoom_reset_action)

        edit_menu.addSeparator()
        set_bl_action = QAction("Set Baseline", self)
        self._wire_action(set_bl_action, self._set_baseline)
        edit_menu.addAction(set_bl_action)

        clear_bl_action = QAction("Clear All Baselines", self)
        self._wire_action(clear_bl_action, self._clear_baseline)
        edit_menu.addAction(clear_bl_action)

        # Options menu (operates on the active project's config).
        options_menu = menu.addMenu("Options")
        font_bigger_action = QAction("Font Bigger", self)
        font_bigger_action.setShortcut("Ctrl+=")
        font_bigger_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._wire_action(font_bigger_action, lambda: self._adjust_zoom(0.1))
        options_menu.addAction(font_bigger_action)

        font_smaller_action = QAction("Font Smaller", self)
        font_smaller_action.setShortcut("Ctrl+-")
        font_smaller_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._wire_action(font_smaller_action, lambda: self._adjust_zoom(-0.1))
        options_menu.addAction(font_smaller_action)

        font_reset_action = QAction("Reset Font Size", self)
        font_reset_action.setShortcut("Ctrl+0")
        font_reset_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._wire_action(font_reset_action, lambda: self._set_zoom(1.0))
        options_menu.addAction(font_reset_action)

        options_menu.addSeparator()

        manage_waiting_action = QAction("Manage Waiting People…", self)
        self._wire_action(manage_waiting_action, self.open_waiting_people_manager)
        options_menu.addAction(manage_waiting_action)

        calendar_action = QAction("Calendar Settings…", self)
        self._wire_action(calendar_action, self.open_calendar_settings)
        options_menu.addAction(calendar_action)

        usage_action = QAction("Record usage statistics", self)
        usage_action.setCheckable(True)
        usage_action.setChecked(usage_logger.is_enabled())
        usage_action.setToolTip(
            "Keeps a private local log of which app features you use, so "
            "improvement suggestions can be based on real usage. Nothing leaves this computer."
        )
        usage_action.toggled.connect(usage_logger.set_enabled)
        options_menu.addAction(usage_action)

    def _undo_active(self):
        proj = self.active_project()
        if proj:
            proj.undo()
            usage_logger.log("undo")

    def _redo_active(self):
        proj = self.active_project()
        if proj:
            proj.redo()
            usage_logger.log("redo")

    def _full_path(self, node):
        parts = []
        n = node
        while n:
            parts.append(n.name)
            n = n.parent
        return " > ".join(reversed(parts))

    def _overdue_leaves(self, proj=None):
        from datetime import datetime
        proj = proj or self.active_project()
        if not proj:
            return []
        today = datetime.now().date()
        overdue = []
        for node in proj.tree_view.get_all_nodes_flat():
            if node.children or node.status == "Completed" or not node.end_date:
                continue
            try:
                end = datetime.strptime(node.end_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            if end < today:
                overdue.append((node, end, (today - end).days))
        overdue.sort(key=lambda row: row[1])
        return overdue

    def _update_overdue_action(self):
        action = getattr(self, "catch_up_action", None)
        if not action:
            return
        count = len(self._overdue_leaves())
        action.setText(f"Catch Up on Overdue... ({count} overdue)" if count else "Catch Up on Overdue...")

    def _show_catch_up(self):
        from datetime import datetime
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
            QWidget, QHBoxLayout, QRadioButton, QButtonGroup, QDateEdit,
            QLineEdit, QDialogButtonBox, QHeaderView,
        )
        from PyQt6.QtCore import QDate
        from utils.workday_calculator import WorkdayCalculator

        proj = self.active_project()
        if not proj:
            return
        overdue = self._overdue_leaves(proj)
        usage_logger.log("catchup_open", overdue=len(overdue))
        if not overdue:
            QMessageBox.information(self, "Catch Up", "No overdue leaf tasks.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Catch Up on Overdue - {proj.name}")
        dialog.resize(900, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"{len(overdue)} overdue leaf task(s), oldest first."))
        table = QTableWidget(len(overdue), 4)
        table.setHorizontalHeaderLabels(["Task", "Was due", "Days late", "Action"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        rows = []
        today_q = QDate.currentDate()
        today_str = today_q.toString("yyyy-MM-dd")
        for row, (node, end_date, late_days) in enumerate(overdue):
            table.setItem(row, 0, QTableWidgetItem(self._full_path(node)))
            table.setItem(row, 1, QTableWidgetItem(node.end_date or ""))
            table.setItem(row, 2, QTableWidgetItem(str(late_days)))
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 0, 4, 0)
            group = QButtonGroup(action_widget)
            skip = QRadioButton("Skip")
            done = QRadioButton("Done")
            push = QRadioButton("Push to")
            skip.setChecked(True)
            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            try:
                duration = int(node.duration)
            except (ValueError, TypeError):
                duration = 1
            default_end = WorkdayCalculator.add_workdays(today_str, max(1, duration))
            date_edit.setDate(QDate.fromString(default_end, "yyyy-MM-dd"))
            for btn in (skip, done, push):
                group.addButton(btn)
                action_layout.addWidget(btn)
            action_layout.addWidget(date_edit)
            table.setCellWidget(row, 3, action_widget)
            rows.append({"node": node, "group": group, "skip": skip, "done": done,
                         "push": push, "date": date_edit})
        layout.addWidget(table, 1)
        reason_edit = QLineEdit()
        reason_edit.setPlaceholderText("Shared reason for pushed tasks (optional)")
        layout.addWidget(reason_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if not usage_logger.timed_exec(dialog, "catchup"):
            return

        shared_reason = reason_edit.text().strip() or "Pushed during catch-up"
        done_count = pushed_count = skipped_count = 0
        changed = []
        today = datetime.now().strftime("%Y-%m-%d")
        proj.begin_batch()
        try:
            for row in rows:
                node = row["node"]
                if row["done"].isChecked():
                    node.set_status("Completed")
                    done_count += 1
                    changed.append(node)
                    proj.tree_view.journal_event.emit(f"Catch-up: '{node.name}' marked Completed")
            for row in rows:
                node = row["node"]
                if not row["push"].isChecked():
                    if not row["done"].isChecked():
                        skipped_count += 1
                    continue
                new_end = row["date"].date().toString("yyyy-MM-dd")
                old_end = node.end_date
                node.set_date("end", new_end)
                pushed_count += 1
                changed.append(node)
                if node.baseline_duration is not None and not node.children:
                    try:
                        total_diff = int(node.duration) - node.baseline_duration
                        uncovered = total_diff - node.logged_slip()
                    except (ValueError, TypeError):
                        uncovered = 0
                    if uncovered > 0:
                        node.log_delay_revision({
                            "rev": chr(ord("B") + len(node.revisions)),
                            "date": today,
                            "end": new_end,
                            "slip": uncovered,
                            "reason": shared_reason,
                        })
                proj.tree_view.journal_event.emit(
                    f"Catch-up: '{node.name}' pushed {old_end or '-'} -> {new_end}: {shared_reason}")
            proj.tree_view.recalculate_all_dates()
            proj.tree_view.refresh_entire_tree()
            proj.tree_view.journal_event.emit(
                f"Catch-up: {done_count} done, {pushed_count} pushed, {skipped_count} skipped")
            usage_logger.log("catchup_apply", done=done_count, pushed=pushed_count, skipped=skipped_count)
            if changed:
                proj.tree_view.item_changed_signal.emit(changed[0])
        finally:
            proj.end_batch()
        self._update_overdue_action()

    def _show_waiting_list(self):
        from datetime import datetime
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
            QDialogButtonBox, QHeaderView,
        )
        from PyQt6.QtGui import QColor

        proj = self.active_project()
        if not proj:
            return
        today = datetime.now().date()
        rows = []
        for node in proj.tree_view.get_all_nodes_flat():
            if not node.waiting_on:
                continue
            days = 0
            if node.waiting_since:
                try:
                    since = datetime.strptime(node.waiting_since, "%Y-%m-%d").date()
                    days = max(0, (today - since).days)
                except ValueError:
                    pass
            rows.append((node, days))
        rows.sort(key=lambda item: item[1], reverse=True)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Waiting-On List - {proj.name}")
        dialog.resize(760, 420)
        layout = QVBoxLayout(dialog)
        if not rows:
            layout.addWidget(QLabel("No tasks are marked waiting."))
        else:
            table = QTableWidget(len(rows), 4)
            table.setHorizontalHeaderLabels(["Task", "Waiting on", "Since", "Days"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            for row, (node, days) in enumerate(rows):
                values = [self._full_path(node), node.waiting_on, node.waiting_since or "", str(days)]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, node.id)
                    if days >= 5:
                        item.setForeground(QColor("#D50000"))
                    table.setItem(row, col, item)

            def open_row(item):
                node_id = item.data(Qt.ItemDataRole.UserRole)
                if node_id:
                    dialog.accept()
                    proj.inner_tabs.setCurrentIndex(0)
                    proj.tree_view.jump_to_node_id(node_id)

            table.itemDoubleClicked.connect(open_row)
            layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _set_baseline(self):
        proj = self.active_project()
        if proj:
            proj.tree_view.set_baseline()
            self.on_data_changed()

    def _clear_baseline(self):
        proj = self.active_project()
        if proj:
            proj.tree_view.clear_baseline()
            self.on_data_changed()

    def _refresh_all(self):
        """Full refresh: re-run the scheduler AND repaint every row.
        The old Refresh Timeline only recalculated the model without
        repainting, which is why dates looked stale until the user
        wiggled them back and forth."""
        proj = self.active_project()
        if not proj:
            return
        node = proj.tree_view.root_nodes[0] if proj.tree_view.root_nodes else None
        proj.tree_view.commit_structure_change(node)
        if proj.inner_tabs.currentIndex() == 1:
            proj.gantt_view.load_nodes(proj.tree_view.root_nodes)

    def _open_notes_pad(self, via="ctrl_space"):
        """Open the project's Notes pad (big floating notepad) with the cursor
        in its multi-line capture box. Ctrl+Space / Ctrl+Shift+N / the Edit menu
        all land here — one place to jot notes AND see everything already jotted."""
        proj = self.active_project()
        if not proj:
            return
        proj.show_notes_and_capture()
        usage_logger.log("quick_capture", via=via, kind="open_pad")

    def _apply_saved_zoom(self):
        self._zoom_factor = float(self.settings.value("ui_zoom", 1.0) or 1.0)
        self._set_zoom(self._zoom_factor, persist=False, announce=False)

    def _adjust_zoom(self, delta: float):
        self._set_zoom(getattr(self, "_zoom_factor", 1.0) + delta)

    def _set_zoom(self, factor: float, persist: bool = True, announce: bool = True):
        from PyQt6.QtWidgets import QApplication
        factor = max(0.7, min(2.0, round(factor, 1)))
        self._zoom_factor = factor
        app = QApplication.instance()
        if app:
            base = app.property("vpm_base_font")
            if base is None:
                base = app.font()
                app.setProperty("vpm_base_font", base)
            font = QFont(base)
            font.setPointSizeF(max(1.0, base.pointSizeF() * factor))
            app.setFont(font)
        for proj in self.all_projects():
            if hasattr(proj.tree_view, "apply_zoom"):
                proj.tree_view.apply_zoom(factor)
        if persist:
            self.settings.setValue("ui_zoom", factor)
        if announce:
            self.statusBar().showMessage(f"Zoom {int(factor * 100)}%", 1500)
            usage_logger.log("zoom", pct=int(factor * 100))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._adjust_zoom(0.1 if event.angleDelta().y() > 0 else -0.1)
            event.accept()
            return
        super().wheelEvent(event)

    # ---------------- global search ----------------
    def _show_search(self):
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLineEdit,
                                     QListWidget, QListWidgetItem, QLabel)
        if self._search_dialog is not None:
            self._search_dialog.show()
            self._search_dialog.raise_()
            self._search_dialog.activateWindow()
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Search Everything")
        dlg.resize(640, 420)
        dlg.setModal(False)
        layout = QVBoxLayout(dlg)
        box = QLineEdit()
        box.setPlaceholderText("Search task names, notes, delay reasons, journal…")
        layout.addWidget(box)
        hint = QLabel("Type at least 2 characters. Click a result to jump to it.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)
        results = QListWidget()
        layout.addWidget(results)

        def full_path(node):
            parts, n = [], node
            while n:
                parts.append(n.name)
                n = n.parent
            return " > ".join(reversed(parts))

        def run_search(query: str):
            results.clear()
            q = query.strip().lower()
            if len(q) < 2:
                return
            for tab_idx in range(self.project_tabs.count()):
                proj = self.project_tabs.widget(tab_idx)
                if not isinstance(proj, ProjectWidget):
                    continue
                tag = f"[{proj.name}] " if self.project_tabs.count() > 1 else ""
                for node in proj.tree_view.get_all_nodes_flat():
                    hits = []
                    if q in node.name.lower():
                        hits.append("name")
                    if node.notes and q in node.notes.lower():
                        hits.append("notes")
                    if getattr(node, "waiting_on", "") and q in node.waiting_on.lower():
                        hits.append("waiting on")
                    delay_text = (node.delay_notes + " " + " ".join(
                        r.get("reason", "") for r in node.revisions)).lower()
                    if q in delay_text:
                        hits.append("delay log")
                    if hits:
                        it = QListWidgetItem(
                            f"{tag}{full_path(node)}   — {', '.join(hits)}")
                        it.setData(Qt.ItemDataRole.UserRole, (tab_idx, node.id))
                        results.addItem(it)
                for e in proj.journal:
                    if q in e.get("text", "").lower():
                        it = QListWidgetItem(
                            f"{tag}Journal {e.get('ts', '')}: {e.get('text', '')}")
                        it.setData(Qt.ItemDataRole.UserRole, (tab_idx, None))
                        results.addItem(it)
                for line in proj.notes_panel.get_notes():
                    if q in line.lower():
                        it = QListWidgetItem(f"{tag}📝 Note: {line}")
                        it.setData(Qt.ItemDataRole.UserRole,
                                   (tab_idx, "__note__"))
                        results.addItem(it)
            usage_logger.log("search", chars=len(q), hits=results.count())

        def open_result(it):
            usage_logger.log("search_result_opened")
            tab_idx, node_id = it.data(Qt.ItemDataRole.UserRole)
            self.project_tabs.setCurrentIndex(tab_idx)
            proj = self.project_tabs.widget(tab_idx)
            if node_id == "__note__":
                proj.show_notes_and_capture()
            elif node_id:
                proj.inner_tabs.setCurrentIndex(0)
                proj.tree_view.jump_to_node_id(node_id)
            else:
                self._show_journal()

        box.textChanged.connect(run_search)
        results.itemClicked.connect(open_result)
        results.itemActivated.connect(open_result)

        self._search_dialog = dlg
        dlg.finished.connect(lambda _: setattr(self, "_search_dialog", None))
        dlg.show()
        box.setFocus()

    def _show_digest_since_last_visit(self):
        """'Since you were here' — journal entries from the last 7 days,
        shown once right after a file is opened."""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        lines = []
        for proj in self.all_projects():
            recent = [e for e in proj.journal if e.get("ts", "") >= cutoff]
            for e in recent[-15:]:
                prefix = f"[{proj.name}] " if self.project_tabs.count() > 1 else ""
                lines.append(f"{e['ts']}  {prefix}{e['text']}")
        if not lines:
            return
        lines.sort()
        body = "\n".join(lines[-25:])
        QMessageBox.information(
            self, "Since you were here",
            f"Activity in the last 7 days:\n\n{body}")

    def _show_journal(self):
        """Full activity journal for the active project."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QPlainTextEdit,
                                     QDialogButtonBox, QLabel)
        proj = self.active_project()
        if not proj:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Activity Journal — {proj.name}")
        dialog.resize(560, 440)
        layout = QVBoxLayout(dialog)
        if proj.journal:
            text = "\n".join(
                f"{e.get('ts', '?')}  {e.get('text', '')}"
                for e in reversed(proj.journal))  # newest first
            view = QPlainTextEdit(text)
            view.setReadOnly(True)
            layout.addWidget(view)
        else:
            layout.addWidget(QLabel(
                "No activity recorded yet. The journal fills in "
                "automatically as you work."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _show_delay_summary(self):
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel,
                                     QTableWidget, QTableWidgetItem,
                                     QHeaderView, QDialogButtonBox)
        from PyQt6.QtGui import QColor
        from PyQt6.QtCore import Qt

        proj = self.active_project()
        if not proj:
            return

        def full_path(node):
            parts, n = [], node
            while n:
                parts.append(n.name)
                n = n.parent
            return " > ".join(reversed(parts))

        # Collect delayed tasks
        delayed = []
        for node in proj.tree_view.get_all_nodes_flat():
            if node.children:  # skip parents — their delay is a rollup of children
                continue
            if node.baseline_duration is None:
                continue
            try:
                diff = int(node.duration) - node.baseline_duration
            except (ValueError, TypeError):
                continue
            if diff > 0:
                delayed.append((node, diff))

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Delay Summary — {proj.name}")
        dialog.resize(620, 400)
        layout = QVBoxLayout(dialog)

        if not delayed:
            layout.addWidget(QLabel("No delays detected. All tasks are on track!"))
        else:
            total = sum(d for _, d in delayed)
            summary_lbl = QLabel(f"  {len(delayed)} task(s) delayed  |  Total slip: +{total}d")
            summary_lbl.setStyleSheet("font-weight: bold; padding: 6px;")
            layout.addWidget(summary_lbl)

            table = QTableWidget(len(delayed), 3)
            table.setHorizontalHeaderLabels(["Task", "Delay", "Log"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setWordWrap(True)
            table.verticalHeader().setVisible(False)

            for row, (node, diff) in enumerate(delayed):
                name_item = QTableWidgetItem(full_path(node))
                delay_item = QTableWidgetItem(f"+{diff}d")
                delay_item.setForeground(QColor("#FF0000"))
                delay_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                has_log = bool(node.revisions or node.delay_notes)
                log_text = (node.revision_trail() if has_log
                            else "(no reason logged — double-click Delay cell to add)")
                log_item = QTableWidgetItem(log_text)
                if not has_log:
                    log_item.setForeground(QColor("#999999"))
                table.setItem(row, 0, name_item)
                table.setItem(row, 1, delay_item)
                table.setItem(row, 2, log_item)
                table.resizeRowToContents(row)

            layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # ---------------- options dialogs ----------------
    def open_waiting_people_manager(self):
        proj = self.active_project()
        if not proj:
            return
        proj.activate()
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QHBoxLayout, QPushButton, QInputDialog, QDialogButtonBox
        from utils.config_manager import ConfigManager
        config = ConfigManager()
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Waiting People")
        dialog.resize(360, 420)
        layout = QVBoxLayout(dialog)
        people = QListWidget()
        for name in config.get_owners():
            if name:
                people.addItem(name)
        layout.addWidget(people)
        row = QHBoxLayout()
        add_btn = QPushButton("Add")
        remove_btn = QPushButton("Remove")
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        layout.addLayout(row)

        def add_person():
            name, ok = QInputDialog.getText(dialog, "Add Waiting Person", "Name/team:")
            if ok and name.strip():
                existing = [people.item(i).text() for i in range(people.count())]
                if name.strip() not in existing:
                    people.addItem(name.strip())

        def remove_person():
            row_idx = people.currentRow()
            if row_idx >= 0:
                people.takeItem(row_idx)

        add_btn.clicked.connect(add_person)
        remove_btn.clicked.connect(remove_person)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if usage_logger.timed_exec(dialog, "waiting_people_manager"):
            config.set_owners([
                people.item(i).text().strip()
                for i in range(people.count())
                if people.item(i).text().strip()
            ])
            self.on_data_changed()

    def open_calendar_settings(self):
        proj = self.active_project()
        if not proj:
            return
        proj.activate()
        from ui.calendar_dialog import CalendarSettingsDialog
        dialog = CalendarSettingsDialog(self)
        if usage_logger.timed_exec(dialog, "calendar_settings"):
            node = proj.tree_view.root_nodes[0] if proj.tree_view.root_nodes else None
            proj.tree_view.commit_structure_change(node)

    # ---------------- data change tracking ----------------
    def on_data_changed(self):
        if not self.unsaved_changes:
            self.unsaved_changes = True
        self.update_title()
        self._update_overdue_action()

    def update_title(self):
        title = f"{AppConstants.APP_NAME} - {AppConstants.REVISION_LABEL}"
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
        if event.isAccepted():
            usage_logger.log("app_end", secs=usage_logger.usage.session_secs())

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
            usage_logger.log("file_save", manual=True)
            self.unsaved_changes = False
            self.update_title()
            self._remember_recent(self.current_filepath)
            recovery = self._recovery_path()
            if os.path.exists(recovery):
                self.settings.setValue("recovery_last_imported_mtime", os.path.getmtime(recovery))
                try:
                    os.remove(recovery)
                except OSError:
                    pass
        except Exception as e:
            usage_logger.log("save_failed", type=type(e).__name__)
            usage_logger.log("warning_shown", name="save_failed")
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
        self._load_path(filename)

    def _confirm_discard_unsaved(self) -> bool:
        if not self.unsaved_changes:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Save before loading another file?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.save_project_file()
            return not self.unsaved_changes
        if reply == QMessageBox.StandardButton.No:
            return True
        return False

    def _load_path(self, filename: str, prompt_unsaved: bool = True,
                   is_recovery: bool = False) -> bool:
        if prompt_unsaved and not self._confirm_discard_unsaved():
            return False
        try:
            from utils.vpmt_io import load_projects, read_version, CURRENT_VERSION
            projects = load_projects(filename)
            file_version = read_version(filename)
        except Exception as e:
            usage_logger.log("load_failed", type=type(e).__name__)
            usage_logger.log("warning_shown", name="load_failed")
            QMessageBox.critical(self, "Error", f"Could not load file: {e}")
            return False

        # Seatbelt: a file written by an older app version may lack newer
        # data (baselines, delay logs, journal). Say so NOW, not days later.
        if file_version != CURRENT_VERSION:
            usage_logger.log("warning_shown", name="older_file_version")
            QMessageBox.information(
                self, "Older file version",
                f"This file was saved by an older version of the app "
                f"(file: {file_version}, current: {CURRENT_VERSION}).\n\n"
                "Newer data such as baselines, delay logs, or the activity "
                "journal may be missing from it. Saving will upgrade the "
                "file to the current format.")

        # Wipe existing tabs. Each project's close_project releases ConfigManager state.
        while self.project_tabs.count():
            w = self.project_tabs.widget(0)
            if isinstance(w, ProjectWidget):
                w.close_project()
            self.project_tabs.removeTab(0)

        for proj_dict in projects:
            self._add_project_from_data(
                proj_dict["name"], proj_dict.get("metadata", {}),
                proj_dict.get("roots", []),
                proj_dict.get("journal", []),
                proj_dict.get("notes", []),
            )

        self.current_filepath = None if is_recovery else filename
        self.unsaved_changes = False
        self.update_title()
        self.statusBar().showMessage(f"Loaded {filename}", 3000)
        if not is_recovery:
            self._remember_recent(filename)
            self._warn_duplicate_basename(filename)
        if not self._loading_startup:
            self._show_digest_since_last_visit()
        self._set_zoom(getattr(self, "_zoom_factor", 1.0), persist=False, announce=False)
        self._update_overdue_action()
        self._show_holiday_tip_if_needed()
        usage_logger.log(
            "file_open",
            path=filename,
            projects=len(projects),
            tasks=sum(len(p.tree_view.get_all_nodes_flat()) for p in self.all_projects()),
        )
        return True

    # ---------------- recent files ----------------
    def _recent_files(self) -> list:
        files = self.settings.value("recent_files", []) or []
        if isinstance(files, str):
            files = [files]
        return [f for f in files if os.path.exists(f)]

    def _remember_recent(self, path: str):
        files = self._recent_files()
        if path in files:
            files.remove(path)
        files.insert(0, path)
        self.settings.setValue("recent_files", files[:8])

    def _populate_recent_menu(self):
        self.recent_menu.clear()
        files = self._recent_files()
        if not files:
            empty = QAction("(no recent files)", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for path in files:
            try:
                from datetime import datetime
                mod = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
            except OSError:
                mod = "unknown date"
            act = QAction(f"{path}  ({mod})", self)
            act.setToolTip(path)
            act.triggered.connect(lambda _, p=path: self._load_path(p))
            self.recent_menu.addAction(act)

    def _warn_duplicate_basename(self, opened_path: str):
        opened_abs = os.path.abspath(opened_path)
        opened_base = os.path.basename(opened_abs).lower()
        try:
            opened_mtime = os.path.getmtime(opened_abs)
        except OSError:
            return
        for path in self._recent_files():
            candidate = os.path.abspath(path)
            if candidate == opened_abs:
                continue
            if os.path.basename(candidate).lower() != opened_base:
                continue
            try:
                candidate_mtime = os.path.getmtime(candidate)
            except OSError:
                continue
            if candidate_mtime > opened_mtime:
                usage_logger.log("warning_shown", name="newer_duplicate_basename")
                QMessageBox.warning(
                    self, "Newer File With Same Name",
                    f"A newer file with the same name exists at:\n\n{candidate}\n\n"
                    "Are you sure this is the right one?")
                return

    def _show_holiday_tip_if_needed(self):
        from utils.config_manager import ConfigManager
        default_holidays = ConfigManager.default_snapshot().get("holidays", []) or []
        if not default_holidays:
            return
        for proj in self.all_projects():
            md = proj.to_persistable().get("metadata", {}) or {}
            if not (md.get("holidays") or []):
                self.statusBar().showMessage(
                    "Tip: this project has no holidays set - Options > Calendar Settings.",
                    8000,
                )
                return

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
            usage_logger.log("excel_export", projects=len(projects))
            self.statusBar().showMessage(f"Exported to {filename}", 4000)
        except ImportError:
            usage_logger.log("warning_shown", name="excel_missing_dependency")
            QMessageBox.critical(
                self, "Missing Dependency",
                "Excel export requires the 'openpyxl' package.\n\n"
                "Install it with:\n    pip install openpyxl",
            )
        except Exception as e:
            usage_logger.log("error", where="excel_export", type=type(e).__name__)
            QMessageBox.critical(self, "Export Failed", f"Could not export: {e}")
