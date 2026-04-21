
import sys
import json
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QToolBar, 
                            QFileDialog, QMessageBox, QStyle, QTabWidget)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import QSize, Qt

from ui.tree_grid_view import TreeGridView
from ui.gantt_chart import GanttChartWidget
from models.task_node import TaskNode
from vpm_tracker_core import AppConstants, Columns

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(AppConstants.APP_NAME)
        self.resize(1200, 800)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        # Tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # Tab 1: Tracker
        self.tree_view = TreeGridView()
        self.tabs.addTab(self.tree_view, "Tracker")
        
        # Tab 2: Visuals
        self.gantt_view = GanttChartWidget()
        self.gantt_view.main_window = self  # Set reference for tab switching
        self.tabs.addTab(self.gantt_view, "Visuals")
        
        # Connect selection
        self.tree_view.itemClicked.connect(self.on_tree_selection_changed)
        self.tree_view.currentItemChanged.connect(self.on_tree_selection_changed)
        
        # Connect data changes & Tab Switching
        self.tree_view.item_changed_signal.connect(self.on_data_changed)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        self.setup_toolbar()
        self.setup_menu()
        
        # Track current file and state
        self.current_filepath = None
        self.unsaved_changes = False
        
        # Initial Data (Test)
        self.create_test_data()

    def on_tab_changed(self, index):
        if index == 1: # Visuals Tab
            # Reload data into Gantt
            self.gantt_view.load_nodes(self.tree_view.root_nodes)

    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)
        
        # Refresh Button (Icon Only)
        refresh_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "Refresh Timeline", self)
        refresh_action.triggered.connect(self.refresh_all)
        toolbar.addAction(refresh_action)

    def refresh_all(self):
        self.tree_view.recalculate_all_dates()
        if self.tabs.currentIndex() == 1:
            self.gantt_view.load_nodes(self.tree_view.root_nodes)

    def setup_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        
        load_action = QAction("Load...", self)
        load_action.triggered.connect(self.load_project)
        file_menu.addAction(load_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Options Menu
        options_menu = menu.addMenu("Options")
        
        manage_owners_action = QAction("Manage Owners...", self)
        manage_owners_action.triggered.connect(self.open_owner_manager)
        options_menu.addAction(manage_owners_action)
        
        calendar_action = QAction("Calendar Settings...", self)
        calendar_action.triggered.connect(self.open_calendar_settings)
        options_menu.addAction(calendar_action)

    def open_owner_manager(self):
        from ui.dialogs import OwnerManagerDialog
        dialog = OwnerManagerDialog(self)
        if dialog.exec():
            pass

    def open_calendar_settings(self):
        from ui.calendar_dialog import CalendarSettingsDialog
        dialog = CalendarSettingsDialog(self)
        if dialog.exec():
            # self.tree_view.refresh_entire_tree() # Method needs implementation or rename
            self.tree_view.recalculate_all_dates()

    def create_test_data(self):
        root = TaskNode("Project Alpha")
        phase1 = TaskNode("Phase 1", parent=root)
        root.add_child(phase1)
        
        task1 = TaskNode("Task 1.1", parent=phase1)
        task1.status = "Completed"
        phase1.add_child(task1)
        
        task2 = TaskNode("Task 1.2", parent=phase1)
        phase1.add_child(task2)
        
        self.tree_view.load_project([root])
        # Load Gantt initially too if needed
        # self.gantt_view.load_nodes([root])

    def on_tree_selection_changed(self):
        # Placeholder for future selection logic
        pass

    def on_data_changed(self):
        if not self.unsaved_changes:
            self.unsaved_changes = True
            self.update_title()

    def update_title(self):
        title = AppConstants.APP_NAME
        if self.current_filepath:
            title += f" - {self.current_filepath}"
        else:
            title += " - New Project"
            
        if self.unsaved_changes:
            title += " *"
            
        self.setWindowTitle(title)

    def closeEvent(self, event):
        if self.unsaved_changes:
            reply = QMessageBox.question(self, "Unsaved Changes",
                                       "You have unsaved changes. Do you want to save before closing?",
                                       QMessageBox.StandardButton.Yes | 
                                       QMessageBox.StandardButton.No | 
                                       QMessageBox.StandardButton.Cancel)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.save_project()
                # If save failed or was cancelled (e.g. Save As cancelled), don't close
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

    def save_project(self):
        if self.current_filepath:
            try:
                from utils.vpmt_io import save_project
                save_project(self.tree_view.root_nodes, self.current_filepath)
                self.statusBar().showMessage(f"Saved to {self.current_filepath}", 3000)
                self.unsaved_changes = False
                self.update_title()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file: {e}")
        else:
            self.save_project_as()

    def save_project_as(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Project As", "", f"VPM Files (*{AppConstants.FILE_EXT})")
        if filename:
            self.current_filepath = filename
            self.save_project()

    def load_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Project", "", f"VPM Files (*{AppConstants.FILE_EXT})")
        if filename:
            try:
                from utils.vpmt_io import load_project
                nodes = load_project(filename)
                self.tree_view.load_project(nodes)
                self.current_filepath = filename
                self.unsaved_changes = False
                self.update_title()
                self.statusBar().showMessage(f"Loaded {filename}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load file: {e}")
