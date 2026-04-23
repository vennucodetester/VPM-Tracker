from datetime import datetime
from PyQt6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QHeaderView, 
                            QAbstractItemView, QMenu, QMessageBox, QStyledItemDelegate,
                            QCalendarWidget, QDateEdit, QStyle, QStyleOptionButton, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QDate, QTimer, QRect
from PyQt6.QtGui import QAction, QColor, QBrush, QKeySequence

from vpm_tracker_core import Columns, Colors, AppConstants, Status
from models.task_node import TaskNode
from ui.dialogs import BulkEditDialog, BulkPasteDialog, ImpactDialog, LinkTaskDialog
from ui.header_filter import FilterHeaderView
from utils.workday_calculator import WorkdayCalculator

class DateDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd")

        # Explicitly highlight today in the calendar popup. Qt's default
        # outline can get swallowed by dark-theme stylesheets, so we set a
        # bold, accent-colored text format on today's cell.
        from PyQt6.QtGui import QTextCharFormat, QColor, QFont
        cal = editor.calendarWidget()
        if cal is not None:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setForeground(QColor("#FFD54F"))  # amber — pops on dark + light
            fmt.setBackground(QColor(255, 213, 79, 60))  # subtle amber tint
            cal.setDateTextFormat(QDate.currentDate(), fmt)

        # Auto-open calendar popup
        def open_popup():
            from PyQt6.QtWidgets import QToolButton
            for child in editor.children():
                if isinstance(child, QToolButton):
                    child.animateClick()
                    return

        QTimer.singleShot(100, open_popup)
        return editor

    def setEditorData(self, editor, index):
        date_str = index.model().data(index, Qt.ItemDataRole.EditRole)
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                editor.setDate(QDate(dt.year, dt.month, dt.day))
            except ValueError:
                editor.setDate(QDate.currentDate())
        else:
            editor.setDate(QDate.currentDate())

    def setModelData(self, editor, model, index):
        date = editor.date()
        model.setData(index, date.toString("yyyy-MM-dd"), Qt.ItemDataRole.EditRole)

class StatusDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        from PyQt6.QtWidgets import QComboBox
        editor = QComboBox(parent)
        editor.addItems([s.value for s in Status])
        QTimer.singleShot(100, editor.showPopup)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        if value:
            editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

class OwnerDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        from PyQt6.QtWidgets import QComboBox
        editor = QComboBox(parent)
        
        # Dynamic Owners: Get from Tree
        owners = set()
        tree_view = self.parent()
        if tree_view and hasattr(tree_view, 'get_all_nodes_flat'):
            all_nodes = tree_view.get_all_nodes_flat()
            for n in all_nodes:
                if n.owner:
                    # Split combined owners
                    parts = n.owner.split('/')
                    for p in parts:
                        if p.strip():
                            owners.add(p.strip())
                            
        sorted_owners = sorted(list(owners))
        editor.addItems(sorted_owners)
        editor.setEditable(True) 
        QTimer.singleShot(100, editor.showPopup) # Open immediately
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        if value:
            editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)



    def paint(self, painter, option, index):
        # Render only the first line
        text = index.data()
        if text:
            first_line = text.split('\n')[0]
            # We need to modify the option to draw only first line
            opt = option
            opt.text = first_line
            super().paint(painter, opt, index)
        else:
            super().paint(painter, option, index)

class NotesDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        # Return None to prevent default editor from opening
        return None

    def editorEvent(self, event, model, option, index):
        from PyQt6.QtCore import QEvent
        # Check for Double Click
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self.open_dialog(index)
            return True # Event consumed
        return super().editorEvent(event, model, option, index)

    def open_dialog(self, index):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox
        from models.task_node import TaskNode
        
        tree_view = self.parent()
        if not tree_view or not hasattr(tree_view, 'itemFromIndex'):
            return

        item = tree_view.itemFromIndex(index)
        if not item or not hasattr(item, 'node'):
            return
            
        node = item.node
        current_notes = node.notes
        today_tag = datetime.now().strftime("[%Y-%m-%d]: ")
        
        edit_text = current_notes
        cursor_pos = 0
        
        lines = edit_text.split('\n') if edit_text else []
        first_line = lines[0] if lines else ""
        
        is_blank_today = first_line.strip() == today_tag.strip()
        
        if is_blank_today:
            cursor_pos = len(today_tag)
        else:
            if edit_text:
                edit_text = today_tag + " \n" + edit_text
            else:
                edit_text = today_tag + " "
            cursor_pos = len(today_tag)
        
        dialog = QDialog(tree_view)
        dialog.setWindowTitle(f"Notes - {node.name}")
        dialog.resize(400, 300)
        layout = QVBoxLayout(dialog)
        
        text_edit = QPlainTextEdit(edit_text)
        layout.addWidget(text_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        cursor = text_edit.textCursor()
        cursor.setPosition(cursor_pos)
        text_edit.setTextCursor(cursor)
        text_edit.setFocus()
        
        if dialog.exec():
            new_text = text_edit.toPlainText()
            node.notes = new_text
            item.update_from_node()
            tree_view.item_changed_signal.emit(node)

    def paint(self, painter, option, index):
        text = index.data()
        if text:
            first_line = text.split('\n')[0]
            opt = option
            opt.text = first_line
            super().paint(painter, opt, index)
        else:
            super().paint(painter, option, index)

class TaskTreeWidgetItem(QTreeWidgetItem):
    def __init__(self, node: TaskNode):
        super().__init__()
        self.node = node
        self.update_from_node()
        
    def update_from_node(self):
        self.setText(Columns.TREE, self.node.name)

        # Parallel Toggle (Checkbox styled as Radio)
        self.setCheckState(Columns.TREE, Qt.CheckState.Checked if self.node.is_parallel else Qt.CheckState.Unchecked)

        self.setText(Columns.START, self.node.start_date or "")
        self.setText(Columns.END, self.node.end_date or "")
        self.setText(Columns.DURATION, self.node.duration)
        self.setText(Columns.STATUS, self.node.status)
        self.setText(Columns.OWNER, self.node.owner)
        self.setText(Columns.PREDECESSOR, self._predecessor_label())
        self.setText(Columns.NOTES, self.node.notes)

        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
        
        # Visual indication for locked dates
        if self.node.dates_locked:
            self.setForeground(Columns.START, QBrush(Colors.GRAY))
            self.setForeground(Columns.END, QBrush(Colors.GRAY))
        else:
            # Reset to default (which might be overridden by status color below, 
            # but usually date columns are black unless locked)
            self.setForeground(Columns.START, QBrush(Colors.TEXT_WHITE))
            self.setForeground(Columns.END, QBrush(Colors.TEXT_WHITE))
        
        # Coloring Logic (Strict Priority)
        # Priority 1: Overdue (Red) - End < Today AND Status != Completed (Recursive)
        # Priority 2: Completed (Green) - Status = Completed
        # Priority 3: Leaf Tasks (Orange) - No children
        # Priority 4: Parent Tasks (Gray) - Has children
        
        status_color = Colors.TEXT_WHITE # Default
        
        is_completed = self.node.status == "Completed"
        is_overdue = self.check_is_overdue(self.node)
        
        if is_overdue:
            status_color = Colors.RED
        elif is_completed:
            status_color = Colors.GREEN
        else:
            status_color = Colors.TEXT_WHITE
            
        # Apply color to all columns
        for col in range(Columns.COUNT):
            self.setForeground(col, QBrush(status_color))

        # Implicit predecessor label rendered in gray so it reads as a default, not a user choice.
        if self._predecessor_is_implicit():
            self.setForeground(Columns.PREDECESSOR, QBrush(Colors.GRAY))

    def _predecessor_label(self) -> str:
        """Render 'Depends On' cell.

        '⇦ Name' — explicit predecessor link set by the user.
        '↑ Name' — implicit default: the previous sibling, which the scheduler
                   uses automatically when no explicit predecessor is set.
        ''      — no link and no prior sibling.
        """
        if self.node.predecessor_id:
            tree = self.treeWidget()
            name = None
            if tree is not None and hasattr(tree, 'resolve_node_name'):
                name = tree.resolve_node_name(self.node.predecessor_id)
            return f"⇦ {name}" if name else "⇦ (missing)"

        prev = self._implicit_predecessor()
        if prev is not None:
            return f"↑ {prev.name}"
        return ""

    def _implicit_predecessor(self):
        """Previous sibling the scheduler would chain from when no explicit link is set."""
        parent = self.node.parent
        if not parent:
            return None
        try:
            idx = parent.children.index(self.node)
        except ValueError:
            return None
        if idx <= 0:
            return None
        return parent.children[idx - 1]

    def _predecessor_is_implicit(self) -> bool:
        return (not self.node.predecessor_id) and (self._implicit_predecessor() is not None)

    def check_is_overdue(self, node: TaskNode) -> bool:
        # Recursive check: Overdue if self is overdue OR any child is overdue
        
        # 1. Check Self
        self_overdue = False
        if node.status != "Completed" and node.end_date:
            try:
                end_dt = datetime.strptime(node.end_date, "%Y-%m-%d")
                if end_dt.date() < datetime.now().date():
                    self_overdue = True
            except ValueError: pass
            
        if self_overdue:
            return True
            
        # 2. Check Parent Boundary (If Parent Locked)
        if node.parent and node.parent.dates_locked and node.end_date and node.parent.end_date:
            try:
                c_end = datetime.strptime(node.end_date, "%Y-%m-%d")
                p_end = datetime.strptime(node.parent.end_date, "%Y-%m-%d")
                if c_end > p_end:
                    return True
            except ValueError: pass

        # 3. Check Children (Recursive)
        for child in node.children:
            if self.check_is_overdue(child):
                return True
                
        return False

class TreeGridView(QTreeWidget):
    item_changed_signal = pyqtSignal(TaskNode) # Signal when data changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_nodes = [] # List of top-level TaskNodes
        self.active_filters = {} # {column: set_of_allowed_values}
        self.is_updating = False # Flag to prevent recursion
        
        # Linking Mode State
        self.linking_mode = False
        self.linking_source_node = None
        
        self.setup_ui()

    def setup_ui(self):
        self.setHeaderLabels(Columns.NAMES)
        
        # Custom Filter Header
        self.filter_header = FilterHeaderView(Qt.Orientation.Horizontal, self)
        self.setHeader(self.filter_header)
        self.filter_header.filter_changed.connect(self.apply_column_filter)
        
        # Allow resizing of Task Name column
        self.header().setSectionResizeMode(Columns.TREE, QHeaderView.ResizeMode.Interactive)
        self.header().resizeSection(Columns.TREE, 300) # Default width
        
        # Notes column should stretch to fill space
        self.header().setSectionResizeMode(Columns.NOTES, QHeaderView.ResizeMode.Stretch)
        
        # Enable Extended Selection (Shift/Ctrl)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Signals
        self.itemChanged.connect(self.on_item_changed)
        self.itemCollapsed.connect(self.on_item_collapsed)
        self.itemExpanded.connect(self.on_item_expanded)
        
        # Delegates
        self.setItemDelegateForColumn(Columns.START, DateDelegate(self))
        self.setItemDelegateForColumn(Columns.END, DateDelegate(self))
        self.setItemDelegateForColumn(Columns.STATUS, StatusDelegate(self))
        self.setItemDelegateForColumn(Columns.OWNER, OwnerDelegate(self))
        self.setItemDelegateForColumn(Columns.NOTES, NotesDelegate(self))
        
        # Adjustable Row Height (Global)
        # QTreeWidget items don't have a simple "setHeight". 
        # We can use a stylesheet to enforce minimum height.
        # Also style the indicator to look like a radio button (Round)
        self.setStyleSheet("""
            QTreeView::item { height: 30px; }
            QTreeView::indicator { width: 10px; height: 10px; border-radius: 5px; border: 1px solid #999; }
            QTreeView::indicator:checked { background-color: #999; border: 1px solid #999; image: none; }
            QTreeView::indicator:unchecked { background-color: transparent; }
        """) 
        
        # Context Menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)
        
        # Font Settings
        font = self.font()
        font.setPointSize(10)
        font.setBold(True)
        self.setFont(font)

        # Drag and Drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def keyPressEvent(self, event):
        if self.linking_mode and event.key() == Qt.Key.Key_Escape:
            self._cancel_linking_mode()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
        else:
            super().keyPressEvent(event)
            
    def copy_selection_to_clipboard(self):
        selected_items = self.selectedItems()
        if not selected_items:
            return
            
        # Sort by visual order
        # It's hard to sort by visual order easily without traversing, 
        # but let's just use the list order which might be random-ish or selection order.
        # For a simple copy, selection order is usually fine or we can try to sort.
        
        text_rows = []
        for item in selected_items:
            if isinstance(item, TaskTreeWidgetItem):
                # Tab-separated values
                row_data = [
                    item.text(Columns.TREE),
                    item.text(Columns.START),
                    item.text(Columns.END),
                    item.text(Columns.DURATION),
                    item.text(Columns.STATUS),
                    item.text(Columns.OWNER),
                    item.text(Columns.NOTES)
                ]
                text_rows.append("\t".join(row_data))
                
        clipboard_text = "\n".join(text_rows)
        QApplication.clipboard().setText(clipboard_text)

    def start_linking_mode(self, source_item: TaskTreeWidgetItem):
        """Enter click-to-link mode. No modal popup — cursor + status bar hint only."""
        self.linking_mode = True
        self.linking_source_node = source_item.node
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._show_link_hint(
            f"Linking '{source_item.node.name}': click a task to set as predecessor. "
            f"Click the same task to clear. Esc or right-click to cancel."
        )

    def _show_link_hint(self, msg: str):
        """Write to the main window's status bar if one exists; silent otherwise."""
        w = self.window()
        status = getattr(w, 'statusBar', None)
        if callable(status):
            try:
                status().showMessage(msg, 8000)
            except Exception:
                pass

    def _cancel_linking_mode(self):
        self.linking_mode = False
        self.linking_source_node = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._show_link_hint("Linking cancelled.")

    def mousePressEvent(self, event):
        if self.linking_mode:
            # Right-click cancels cleanly.
            if event.button() == Qt.MouseButton.RightButton:
                self._cancel_linking_mode()
                return

            item = self.itemAt(event.position().toPoint())
            if not isinstance(item, TaskTreeWidgetItem):
                # Click on empty space: do nothing, stay in linking mode.
                return

            target_node = item.node
            source_node = self.linking_source_node

            # Clicking the source row again clears the predecessor (toggle-off).
            if target_node.id == source_node.id:
                self._apply_predecessor_change(source_node, None)
                self.linking_mode = False
                self.linking_source_node = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self._show_link_hint(f"Cleared predecessor on '{source_node.name}'.")
                return

            # Reject cycles: target cannot be a descendant or ancestor of source.
            if target_node in source_node.get_all_descendants():
                self._show_link_hint("Cannot link to a descendant (would create a cycle).")
                return
            ancestor = source_node.parent
            while ancestor:
                if ancestor.id == target_node.id:
                    self._show_link_hint("Cannot link to an ancestor (would create a cycle).")
                    return
                ancestor = ancestor.parent

            self._apply_predecessor_change(source_node, target_node.id)
            self.linking_mode = False
            self.linking_source_node = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._show_link_hint(f"Linked '{source_node.name}' ⇦ '{target_node.name}'.")
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click on the Depends On column jumps to the predecessor
        (explicit link or the implicit '↑ prev sibling') instead of opening
        an editor. Every other column behaves normally.
        """
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, TaskTreeWidgetItem):
            col = self.columnAt(int(event.position().x()))
            if col == Columns.PREDECESSOR:
                self.jump_to_predecessor(item)
                return
        super().mouseDoubleClickEvent(event)

    def dropEvent(self, event):
        # Get the item being moved
        source_item = self.currentItem()
        if not source_item:
            return
            
        # Get the target
        target_item = self.itemAt(event.position().toPoint())
        drop_indicator = self.dropIndicatorPosition()
        
        # Perform the default move first to update UI
        super().dropEvent(event)
        
        # Now update the data model (TaskNodes)
        source_node = source_item.node
        
        # Remove from old parent
        if source_node.parent:
            if source_node in source_node.parent.children:
                source_node.parent.children.remove(source_node)
                # Update old parent dates
                source_node.parent.update_dates_from_children()
        elif source_node in self.root_nodes:
            self.root_nodes.remove(source_node)
            
        # Find new parent
        new_parent_item = source_item.parent()
        if new_parent_item:
            new_parent_node = new_parent_item.node
            source_node.parent = new_parent_node
            
            # Insert at correct index
            idx = new_parent_item.indexOfChild(source_item)
            new_parent_node.children.insert(idx, source_node)
            
            # Update new parent dates
            new_parent_node.update_dates_from_children()
            
            # Smart Default: If new parent was sequential, it might need to become parallel?
            # Or if we drop into a parent, it should become parallel?
            # Let's reuse add_child logic if possible, but we are inserting at specific index.
            # Let's reuse add_child logic if possible, but we are inserting at specific index.
            # FIX: Do NOT force parent to be parallel. This breaks the parent's link to its predecessor.
            # if not new_parent_node.is_parallel:
            #     new_parent_node.is_parallel = True
                
        else:
            # Moved to root
            source_node.parent = None
            # Find index in root
            idx = self.indexOfTopLevelItem(source_item)
            self.root_nodes.insert(idx, source_node)
            
        # Recalculate dates for the whole tree to ensure sequencing is correct
        self.recalculate_all_dates()
        self.item_changed_signal.emit(source_node)

    def load_project(self, nodes: list[TaskNode]):
        self.clear()
        self.root_nodes = nodes
        for node in nodes:
            self.add_node_to_tree(node, self.invisibleRootItem())
        
        self.update_filter_options()
        
        # Force full recalculation to apply new logic (e.g. Next-Day Sequencing) to old files
        self.recalculate_all_dates()

    def add_node_to_tree(self, node: TaskNode, parent_item: QTreeWidgetItem):
        item = TaskTreeWidgetItem(node)
        parent_item.addChild(item)
        item.setExpanded(node.expanded)
        
        for child in node.children:
            self.add_node_to_tree(child, item)

    def update_filter_options(self):
        """Collect unique values for each column and pass to header."""
        # We need to traverse all items
        values = {col: set() for col in range(Columns.COUNT)}
        
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            for col in range(Columns.COUNT):
                text = item.text(col)
                if col == Columns.OWNER:
                    # Split by / or ,
                    parts = text.replace(',', '/').split('/')
                    for p in parts:
                        if p.strip():
                            values[col].add(p.strip())
                else:
                    values[col].add(text)
            iterator += 1
            
        for col, vals in values.items():
            self.filter_header.set_filter_values(col, list(vals))

    def apply_column_filter(self, column, allowed_values):
        if allowed_values is None:
            self.active_filters.pop(column, None)
        else:
            self.active_filters[column] = allowed_values
            
        self.filter_items()

    def filter_items(self):
        """Apply all active filters to the tree."""
        # Logic:
        # Iterate all items.
        # If an item matches ALL filters, it is visible.
        # If an item is visible, its parents must be visible (standard tree behavior).
        # If an item is hidden, its children are hidden (visually).
        
        # However, for a tree, usually if a child matches, we show the parent too.
        # Let's implement: Show item if it matches filters OR if any of its descendants match filters.
        
        # First pass: Determine match status for every item
        # We can do a bottom-up traversal or just recursive check.
        
        root = self.invisibleRootItem()
        self.filter_recursive(root)

    def filter_recursive(self, item):
        # Returns True if this item or any child is visible
        
        # Check if this item matches filters
        matches = True
        if self.active_filters:
            for col, allowed in self.active_filters.items():
                text = item.text(col)
                if col == Columns.OWNER:
                    # Intersection Logic
                    parts = set(p.strip() for p in text.replace(',', '/').split('/') if p.strip())
                    # If allowed contains any of parts, it's a match
                    # Note: allowed is a set of strings
                    if not parts.intersection(allowed):
                        matches = False
                        break
                else:
                    if text not in allowed:
                        matches = False
                        break
        
        # Check children
        child_visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            if self.filter_recursive(child):
                child_visible = True
        
        # Visibility Logic:
        # Visible if (Matches Filters) OR (Has Visible Children)
        # Note: If filters are active, and I don't match, but my child does, I should be visible but maybe grayed out?
        # Standard behavior: Just show it.
        
        should_be_visible = matches or child_visible
        
        # If no filters are active, everything is visible
        if not self.active_filters:
            should_be_visible = True
            
        # Root item (invisible) doesn't need setHidden, but we return result for it
        if item != self.invisibleRootItem():
            item.setHidden(not should_be_visible)
            
        return should_be_visible

    def open_context_menu(self, position: QPoint):
        item = self.itemAt(position)
        
        # Fallback: If clicked on empty space but have selection, use selection
        if not item and self.selectedItems():
            item = self.selectedItems()[0]
            
        menu = QMenu()
        
        if item:
            selected_items = self.selectedItems()
            
            # Bulk Operations for Selection (Status/Owner/Link)
            if len(selected_items) > 1:
                status_action = QAction(f"Set Status ({len(selected_items)} items)...", self)
                status_action.triggered.connect(lambda: self.bulk_set_status(selected_items))
                menu.addAction(status_action)
                
                owner_action = QAction(f"Set Owner ({len(selected_items)} items)...", self)
                owner_action.triggered.connect(lambda: self.bulk_set_owner(selected_items))
                menu.addAction(owner_action)
                
                link_action = QAction(f"Link Selected Tasks ({len(selected_items)} items)", self)
                link_action.triggered.connect(lambda: self.link_selected_tasks(selected_items))
                menu.addAction(link_action)
                
                menu.addSeparator()

            # Standard Operations (Smart handle single vs multiple)
            add_action = QAction("Add Child Task", self)
            add_action.triggered.connect(lambda: self.add_child_task(item))
            menu.addAction(add_action)
            
            paste_action = QAction("Bulk Paste Children...", self)
            paste_action.triggered.connect(lambda: self.bulk_paste_children(item))
            menu.addAction(paste_action)
            
            expand_all_action = QAction("Expand All", self)
            expand_all_action.triggered.connect(lambda: self.expand_all_selected(selected_items))
            menu.addAction(expand_all_action)
            
            menu.addSeparator()
            
            # Indent / Outdent (Smart)
            indent_action = QAction("Indent", self)
            indent_action.triggered.connect(lambda: self.indent_smart(item))
            menu.addAction(indent_action)
            
            outdent_action = QAction("Outdent", self)
            outdent_action.triggered.connect(lambda: self.outdent_smart(item))
            menu.addAction(outdent_action)
            
            menu.addSeparator()
            
            # Date Locking
            lock_action = QAction("Unset Manual Date" if item.node.dates_locked else "Set Manual Date", self)
            lock_action.triggered.connect(lambda: self.toggle_date_lock(item))
            menu.addAction(lock_action)
            
            # Predecessor linking — primary path is inline (click the cell or use this).
            pick_pred_action = QAction("Set Predecessor (Click Target)", self)
            pick_pred_action.setShortcut("Ctrl+L")
            pick_pred_action.triggered.connect(lambda: self.start_linking_mode(item))
            menu.addAction(pick_pred_action)

            # Advanced fallback: searchable dialog for distant/large trees.
            link_pred_action = QAction("Pick from list… (advanced)", self)
            link_pred_action.triggered.connect(lambda: self.open_link_dialog(item))
            menu.addAction(link_pred_action)

            # Jump + clear — only meaningful when an explicit link exists.
            if item.node.predecessor_id:
                jump_action = QAction("Jump to Predecessor", self)
                jump_action.triggered.connect(lambda: self.jump_to_predecessor(item))
                menu.addAction(jump_action)

                clear_link_action = QAction("Clear Predecessor", self)
                clear_link_action.triggered.connect(lambda: self.clear_link(item))
                menu.addAction(clear_link_action)
            
            menu.addSeparator()
            
            delete_action = QAction("Delete Task(s)", self)
            delete_action.triggered.connect(lambda: self.delete_smart(item))
            menu.addAction(delete_action)
        else:
            # No item selected (Root context)
            add_action = QAction("Add Root Task", self)
            add_action.triggered.connect(lambda: self.add_child_task(None))
            menu.addAction(add_action)
            
        menu.exec(self.viewport().mapToGlobal(position))

    def editItem(self, item: QTreeWidgetItem, column: int = 0):
        if not isinstance(item, TaskTreeWidgetItem):
            super().editItem(item, column)
            return

        # Predecessor column: enter inline linking mode. No free-text edit, no popup.
        if column == Columns.PREDECESSOR:
            self.start_linking_mode(item)
            return

        # Block auto-scheduled start dates. _start_is_auto returns False when
        # dates_locked=True, so "Set Manual Date" tasks bypass this block and
        # become editable. END is never blocked — it always controls duration.
        if column == Columns.START and self._start_is_auto(item.node):
            return

        super().editItem(item, column)

    def jump_to_predecessor(self, item: TaskTreeWidgetItem):
        """Select, expand ancestors of, scroll to, and briefly flash the
        task this item depends on. Handles both explicit predecessor_id
        links and the implicit previous-sibling default shown in
        'Depends On'.
        """
        target_node = None
        pred_id = item.node.predecessor_id
        if pred_id:
            t = self._find_item_by_id(pred_id)
            if t is not None:
                target_node = t
        if target_node is None:
            # Fall back to the implicit predecessor (the '↑ Name' entry)
            implicit = item._implicit_predecessor()
            if implicit is not None:
                target_node = self._find_item_by_id(implicit.id)
        if target_node is None:
            return

        # Expand every ancestor so the target row is visible.
        ancestor = target_node.parent()
        while ancestor is not None:
            ancestor.setExpanded(True)
            ancestor = ancestor.parent()

        self.clearSelection()
        target_node.setSelected(True)
        self.setCurrentItem(target_node)
        self.scrollToItem(target_node, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._flash_item(target_node)

    def _flash_item(self, item: 'TaskTreeWidgetItem'):
        """Briefly highlight a row with an amber background, then revert."""
        from PyQt6.QtGui import QColor
        flash_color = QBrush(QColor(255, 213, 79, 140))  # amber overlay
        original = [item.background(col) for col in range(Columns.COUNT)]
        self.blockSignals(True)
        for col in range(Columns.COUNT):
            item.setBackground(col, flash_color)
        self.blockSignals(False)

        def revert():
            self.blockSignals(True)
            try:
                for col in range(Columns.COUNT):
                    item.setBackground(col, original[col])
            except RuntimeError:
                pass  # item was removed before timer fired
            self.blockSignals(False)

        QTimer.singleShot(1400, revert)

    def _find_item_by_id(self, node_id: str):
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            it = iterator.value()
            if isinstance(it, TaskTreeWidgetItem) and it.node.id == node_id:
                return it
            iterator += 1
        return None

    def toggle_date_lock(self, item: TaskTreeWidgetItem):
        item.node.dates_locked = not item.node.dates_locked
        item.update_from_node()
        self.item_changed_signal.emit(item.node)

    def link_selected_tasks(self, items):
        """
        Links selected tasks in visual order.
        Task[i].Start = Task[i-1].End
        """
        # Group by parent to be safe
        # Use ID as key because QTreeWidgetItem is not hashable
        grouped = {} # {parent_id: (parent_item, [children])}
        
        for item in items:
            parent = item.parent() or self.invisibleRootItem()
            pid = id(parent)
            if pid not in grouped:
                grouped[pid] = (parent, [])
            grouped[pid][1].append(item)
            
        for pid, (parent, siblings) in grouped.items():
            # Sort siblings by index
            siblings.sort(key=lambda x: parent.indexOfChild(x))
            
            # Apply links
            for i in range(1, len(siblings)):
                prev_item = siblings[i-1]
                curr_item = siblings[i]
                
                # Manual link: Set Start = Prev.End
                curr_item.node.update_from_previous_sibling(prev_item.node)
                curr_item.update_from_node()
                self.item_changed_signal.emit(curr_item.node)
                
        QMessageBox.information(self, "Tasks Linked", f"Linked {len(items)} tasks.\nStart dates aligned sequentially.")



    def bulk_paste_children(self, parent_item: QTreeWidgetItem):
        dialog = BulkPasteDialog(self)
        if dialog.exec():
            lines = dialog.get_lines()
            parent_node = parent_item.node
            
            for name in lines:
                new_node = TaskNode(name, parent=parent_node)
                parent_node.add_child(new_node)
                self.add_node_to_tree(new_node, parent_item)
            
            parent_item.setExpanded(True)
            if lines:
                self.item_changed_signal.emit(parent_node)
            self.update_filter_options()

    def bulk_set_status(self, items: list[QTreeWidgetItem]):
        # Get status options from Enum
        options = [s.value for s in Status]
        dialog = BulkEditDialog("Bulk Set Status", self, options=options)
        if dialog.exec() and dialog.value:
            for item in items:
                if isinstance(item, TaskTreeWidgetItem):
                    item.node.status = dialog.value
                    item.update_from_node()
                    self.item_changed_signal.emit(item.node)
            self.update_filter_options()

    def bulk_set_owner(self, items: list[QTreeWidgetItem]):
        dialog = BulkEditDialog("Bulk Set Owner", self)
        if dialog.exec() and dialog.value is not None:
            for item in items:
                if isinstance(item, TaskTreeWidgetItem):
                    item.node.owner = dialog.value
                    item.update_from_node()
                    self.item_changed_signal.emit(item.node)
            self.update_filter_options()

    def _start_is_auto(self, node: TaskNode) -> bool:
        """True when the scheduler owns this task's start date, i.e. start
        is not user-editable. Mirrors the rules in utils.scheduler.

        Manual (returns False) when:
          - dates_locked=True  → "Set Manual Date" escape hatch, user owns it.
          - first root task    → schedule anchor, always user-typed.
        Auto (returns True) when:
          - predecessor_id is set, OR
          - node has a parent (all children are auto — radio ON snaps to
            parent.start, radio OFF chains from prev sibling).
        """
        if node.dates_locked:
            return False   # manual mode — user owns the start
        if node.predecessor_id:
            return True
        if node.parent is not None:
            return True
        # Root task: only the first root is manual.
        if self.root_nodes and node is self.root_nodes[0]:
            return False
        return True

    def _apply_predecessor_change(self, node: TaskNode, new_pred_id):
        """Single point of mutation for predecessor links.

        Funneling every path (inline click, context menu clear, advanced dialog)
        through here guarantees the Depends On column repaints immediately —
        the refresh step was missing on the earlier per-path call sites.

        Conflict guard: parallel mode and a predecessor link are mutually
        exclusive. Setting a predecessor while is_parallel=True is blocked.
        Clearing (new_pred_id=None) is always allowed.
        """
        if new_pred_id and node.is_parallel:
            QMessageBox.warning(
                self, "Conflicting settings",
                f"'{node.name}' is set to run in parallel with its parent.\n\n"
                "Disable parallel mode first before linking a predecessor."
            )
            # Cancel link — exit linking mode without changing anything.
            self._cancel_linking_mode()
            return

        node.predecessor_id = new_pred_id if new_pred_id else None
        self.recalculate_all_dates()
        self.refresh_entire_tree()
        self.item_changed_signal.emit(node)

    def clear_link(self, item: TaskTreeWidgetItem):
        self._apply_predecessor_change(item.node, None)

    def open_link_dialog(self, item: TaskTreeWidgetItem):
        all_nodes = self.get_all_nodes_flat()
        dialog = LinkTaskDialog(item.node, all_nodes, self)
        if dialog.exec():
            result_id = dialog.selected_node_id
            if result_id is not None:
                self._apply_predecessor_change(item.node, result_id or None)

    def get_all_nodes_flat(self) -> list[TaskNode]:
        nodes = []
        def traverse(node_list):
            for node in node_list:
                nodes.append(node)
                traverse(node.children)
        traverse(self.root_nodes)
        return nodes

    def resolve_node_name(self, node_id: str) -> str:
        """Lookup a node's display name by id. Used by the Depends On column."""
        node_map = self._get_node_map()
        n = node_map.get(node_id)
        return n.name if n else ""

    def _get_node_map(self) -> dict:
        """Fresh flat id→node map. Cheap enough for trees of a few thousand tasks."""
        return {n.id: n for n in self.get_all_nodes_flat()}

    def recalculate_all_dates(self):
        """Delegate to the shared scheduler (see utils.scheduler)."""
        from utils.scheduler import schedule
        schedule(self.root_nodes)

    def add_child_task(self, parent_item: QTreeWidgetItem = None):
        # If no parent selected, add to root
        parent_node = parent_item.node if parent_item else None
        new_node = TaskNode("New Task", parent=parent_node)
        
        # Auto-Link Logic: If there are existing children, link this new one to the last one
        siblings = parent_node.children if parent_node else self.root_nodes
        # Note: new_node is not in siblings list yet (added below)
        
        if siblings:
            # Link to the last sibling
            # We want: Start = PrevSibling.End
            # new_node.set_formula('start', "=PrevSibling.End")
            # Default duration 1 day?
            # new_node.set_formula('end', "=Start+1")
            
            # Use new manual logic
            prev = siblings[-1]
            new_node.update_from_previous_sibling(prev)
        
        if parent_node:
            parent_node.add_child(new_node)
            parent_item.setExpanded(True)
            self.add_node_to_tree(new_node, parent_item)
        else:
            self.root_nodes.append(new_node)
            self.add_node_to_tree(new_node, self.invisibleRootItem())
            
        # Evaluate formulas immediately -> No formulas anymore
        # new_node.evaluate_formulas()
            
        self.item_changed_signal.emit(new_node)
        self.update_filter_options()

    def delete_task(self, item: QTreeWidgetItem):
        if not item: return
        
        node = item.node
        parent_item = item.parent()
        
        if node.parent:
            node.parent.remove_child(node)
        elif node in self.root_nodes:
            self.root_nodes.remove(node)
            
        if parent_item:
            parent_item.removeChild(item)
        else:
            self.invisibleRootItem().removeChild(item)
        
        self.item_changed_signal.emit(node) # Emit deleted node (or parent) for update
        self.update_filter_options()

    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        # Update model from UI
        if isinstance(item, TaskTreeWidgetItem):
            node = item.node
            text = item.text(column)
            
            # Block signals to prevent recursion when we update the item programmatically
            self.blockSignals(True)
            
            if column == Columns.TREE:
                # Check if checkState changed
                new_state = item.checkState(Columns.TREE) == Qt.CheckState.Checked
                if node.is_parallel != new_state:
                    # Conflict guard: parallel and predecessor are mutually exclusive.
                    if new_state and node.predecessor_id:
                        QMessageBox.warning(
                            self, "Conflicting settings",
                            f"'{node.name}' already has a predecessor link.\n\n"
                            "Remove the predecessor link first before enabling "
                            "parallel mode."
                        )
                        # Revert the checkbox — do NOT update node.is_parallel.
                        item.setCheckState(
                            Columns.TREE,
                            Qt.CheckState.Unchecked if not node.is_parallel
                            else Qt.CheckState.Checked
                        )
                    else:
                        node.is_parallel = new_state
                        self.recalculate_all_dates()

                name_changed = node.name != text
                node.name = text
                # If the name changed, refresh every row so any task that
                # points to this one via predecessor_id (Depends On column)
                # picks up the new label. _predecessor_label resolves by id.
                if name_changed:
                    self.refresh_entire_tree()
            elif column == Columns.START:
                # Smart Date Change Logic
                if self.is_updating: return

                # Block manual start edits whenever the scheduler owns the
                # start. Only the first root task and any is_parallel=ON task
                # are manually editable. See _start_is_auto for the rules.
                if self._start_is_auto(node):
                    if node.predecessor_id:
                        msg = ("This task has a predecessor link. Remove the "
                               "predecessor first before editing its Start "
                               "date manually.")
                    else:
                        msg = ("This task's start date is auto-scheduled.\n\n"
                               "To type a date manually, right-click the task "
                               "and choose 'Set Manual Date'.")
                    QMessageBox.warning(self, "Start date is automatic", msg)
                    item.setText(Columns.START, node.start_date or "")
                    self.blockSignals(False)
                    return
                
                # 1. Simulate Impact
                impacts = node.simulate_date_change(text)
                
                if impacts:
                    # 2. Show Dialog
                    dialog = ImpactDialog(impacts, self)
                    if dialog.exec():
                        if dialog.result_action == "update_all":
                            # Standard Ripple: set this node's start, then
                            # re-run the scheduler so children (Radio ON →
                            # snap to parent.start; Radio OFF → chain from
                            # prev sibling) and downstream predecessors all
                            # update in one pass.
                            old_start = node.start_date
                            old_end = node.end_date
                            # Preserve duration while shifting start
                            if old_start and old_end and text != old_start:
                                dur = WorkdayCalculator.calculate_duration(old_start, old_end)
                                node.start_date = text
                                node.end_date = WorkdayCalculator.add_workdays(text, dur)
                            else:
                                node.start_date = text
                            node.update_status_from_dates()
                            self.recalculate_all_dates()
                            self.validate_child_dates(item)
                            self.refresh_entire_tree()
                        elif dialog.result_action == "keep_others":
                            # Gap: shift only this node, leave siblings alone.
                            old_start = node.start_date
                            old_end = node.end_date
                            if old_start and old_end:
                                dur = WorkdayCalculator.calculate_duration(old_start, old_end)
                                node.start_date = text
                                node.end_date = WorkdayCalculator.add_workdays(text, dur)
                            else:
                                node.start_date = text
                            node.update_status_from_dates()
                            # Re-run scheduler so explicit-predecessor successors
                            # still resolve (gap suppresses sibling-chain ripple only).
                            self.recalculate_all_dates()
                            self.refresh_entire_tree()
                    else:
                        # Cancel: Revert text
                        item.setText(Columns.START, node.start_date)
                else:
                    # No downstream impact — set date and re-run scheduler
                    # so this node's own children move with it.
                    old_start = node.start_date
                    old_end = node.end_date
                    if old_start and old_end and text != old_start:
                        dur = WorkdayCalculator.calculate_duration(old_start, old_end)
                        node.start_date = text
                        node.end_date = WorkdayCalculator.add_workdays(text, dur)
                    else:
                        node.start_date = text
                    node.update_status_from_dates()
                    self.recalculate_all_dates()
                    self.validate_child_dates(item)
                    self.refresh_entire_tree()
                    
            elif column == Columns.END:
                # End date is always editable — it controls duration, not the
                # start anchor. Predecessor links only own the start.
                node.set_date('end', text)
                self.validate_child_dates(item)
                # BUG FIX: must re-run the scheduler so predecessor_id successors
                # pick up the new end date. refresh_entire_tree() alone only repaints.
                self.recalculate_all_dates()
                self.refresh_entire_tree()
            elif column == Columns.STATUS: 
                node.set_status(text)
                # Status change might affect parent, refresh tree
                self.refresh_entire_tree()
            elif column == Columns.OWNER: 
                node.set_owner(text)
                
                # Recursive Rollup: Update ALL ancestors
                current_item = item
                while current_item.parent():
                    parent_item = current_item.parent()
                    if isinstance(parent_item, TaskTreeWidgetItem):
                        # Update the node logic
                        parent_item.node.update_owner_from_children()
                        # Update the UI text immediately
                        parent_item.update_from_node()
                    current_item = parent_item
                    
                self.refresh_entire_tree()
            elif column == Columns.NOTES: node.notes = text
            elif column == Columns.DURATION:
                try:
                    days = int(text)
                    node.set_duration(days)
                    # BUG FIX: duration change shifts end_date, which must
                    # ripple through predecessor_id successors. refresh alone
                    # only repaints — we also need to re-run the scheduler.
                    self.recalculate_all_dates()
                    self.refresh_entire_tree()
                except ValueError:
                    pass # Ignore invalid input
            
            # Refresh duration (it's calculated)
            item.setText(Columns.DURATION, node.duration)
            
            # Re-apply colors in case status/dates changed
            item.update_from_node()
            
            self.blockSignals(False)
            
            self.item_changed_signal.emit(node)
            self.update_filter_options()

    def on_item_collapsed(self, item: QTreeWidgetItem):
        if isinstance(item, TaskTreeWidgetItem):
            item.node.expanded = False
            # Recursively collapse children so next expansion is single-level
            for i in range(item.childCount()):
                child = item.child(i)
                child.setExpanded(False)
                if isinstance(child, TaskTreeWidgetItem):
                    child.node.expanded = False
                    # We need to recurse deeper to ensure grandchildren are also collapsed
                    self.on_item_collapsed(child)

    def on_item_expanded(self, item: QTreeWidgetItem):
        if isinstance(item, TaskTreeWidgetItem):
            item.node.expanded = True

    def refresh_parents(self, item: QTreeWidgetItem):
        """Update parent items visually after a rollup."""
        parent = item.parent()
        while parent:
            if isinstance(parent, TaskTreeWidgetItem):
                parent.update_from_node()
            parent = parent.parent()

    def refresh_entire_tree(self):
        """
        Recursively update all items from their nodes.
        This is necessary because a change in one node might cascade to 
        siblings or children anywhere in the tree.
        """
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if isinstance(item, TaskTreeWidgetItem):
                item.update_from_node()
            iterator += 1

    def validate_child_dates(self, item: TaskTreeWidgetItem):
        """
        Check if child dates exceed LOCKED parent dates.
        Offers: Abort (Snap to parent), Retry (Unlock parent), Ignore.
        """
        node = item.node
        parent_node = node.parent
        
        if not parent_node or not parent_node.dates_locked:
            return

        # Get Parent Dates
        try:
            p_start = datetime.strptime(parent_node.start_date, "%Y-%m-%d")
            p_end = datetime.strptime(parent_node.end_date, "%Y-%m-%d")
            c_start = datetime.strptime(node.start_date, "%Y-%m-%d") if node.start_date else None
            c_end = datetime.strptime(node.end_date, "%Y-%m-%d") if node.end_date else None
        except ValueError:
            return

        violation = False
        msg_text = "WARNING: Child Task Dates Outside Parent Range\n\n"
        
        if c_start and c_start < p_start:
            msg_text += f"Child starts {(p_start - c_start).days} days before parent.\n"
            violation = True
            
        if c_end and c_end > p_end:
            msg_text += f"Child ends {(c_end - p_end).days} days after parent.\n"
            violation = True
            
        if violation:
            msg_text += f"\nParent: {parent_node.name} (Locked: {parent_node.start_date} - {parent_node.end_date})"
            msg_text += f"\nChild: {node.name} ({node.start_date} - {node.end_date})"
            msg_text += "\n\nWhat would you like to do?"
            
            box = QMessageBox(self)
            box.setWindowTitle("Date Validation Warning")
            box.setText(msg_text)
            box.setIcon(QMessageBox.Icon.Warning)
            
            btn_abort = box.addButton("Abort (Snap to Parent)", QMessageBox.ButtonRole.ActionRole)
            btn_retry = box.addButton("Retry (Unlock Parent)", QMessageBox.ButtonRole.ActionRole)
            btn_ignore = box.addButton("Ignore", QMessageBox.ButtonRole.ActionRole)
            
            box.exec()
            
            if box.clickedButton() == btn_abort:
                # Snap to parent
                if c_start and c_start < p_start:
                    node.set_date('start', parent_node.start_date)
                    item.setText(Columns.START, parent_node.start_date) # Update UI immediately
                if c_end and c_end > p_end:
                    node.set_date('end', parent_node.end_date)
                    item.setText(Columns.END, parent_node.end_date) # Update UI immediately
            elif box.clickedButton() == btn_retry:
                # Unlock parent
                parent_node.dates_locked = False
                # Find parent item and update it
                parent_item = item.parent()
                if isinstance(parent_item, TaskTreeWidgetItem):
                    parent_item.update_from_node()
            # else Ignore: do nothing

    def dropEvent(self, event):
        # Let Qt handle the visual move
        super().dropEvent(event)
        
        # Now sync the internal TaskNode hierarchy to match the visual QTreeWidget hierarchy
        self.sync_hierarchy()
        
        # Trigger date updates
        self.recalculate_all_dates()
        
    def sync_hierarchy(self):
        # Rebuild root_nodes list and parent/child relationships based on visual order
        new_roots = []
        
        def process_item(item, parent_node=None):
            node = item.node
            
            # Update parent
            if node.parent != parent_node:
                # Remove from old parent's children list if it was there
                if node.parent and node in node.parent.children:
                    node.parent.children.remove(node)
                node.parent = parent_node
            
            # Clear children list and rebuild it from visual children
            node.children = []
            for i in range(item.childCount()):
                child_item = item.child(i)
                if isinstance(child_item, TaskTreeWidgetItem):
                    node.children.append(child_item.node)
                    process_item(child_item, node)
                    
        # Process top-level items
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if isinstance(item, TaskTreeWidgetItem):
                new_roots.append(item.node)
                process_item(item, None)
                
        self.root_nodes = new_roots
        


    def indent_task(self, item):
        self._indent_item_internal(item)
        self.sync_hierarchy()
        self.recalculate_all_dates()

    def _indent_item_internal(self, item):
        # Move item to be a child of the previous sibling
        parent = item.parent()
        index = parent.indexOfChild(item) if parent else self.indexOfTopLevelItem(item)
        
        if index > 0:
            prev_item = parent.child(index - 1) if parent else self.topLevelItem(index - 1)
            
            # Remove from current position
            if parent:
                parent.takeChild(index)
            else:
                self.takeTopLevelItem(index)
                
            # Add to prev_item
            prev_item.addChild(item)
            prev_item.setExpanded(True)

    def outdent_task(self, item):
        self._outdent_item_internal(item)
        self.sync_hierarchy()
        self.recalculate_all_dates()

    def _outdent_item_internal(self, item):
        # Move item to be a sibling of its parent
        parent = item.parent()
        if parent:
            grandparent = parent.parent()
            index = parent.indexOfChild(item)
            parent_index = grandparent.indexOfChild(parent) if grandparent else self.indexOfTopLevelItem(parent)
            
            # Remove from parent
            parent.takeChild(index)
            
            # Add to grandparent (or root) after parent
            if grandparent:
                grandparent.insertChild(parent_index + 1, item)
            else:
                self.insertTopLevelItem(parent_index + 1, item)

    def indent_selected_tasks(self, items):
        # Sort items by visual order to ensure consistent behavior
        sorted_items = self._get_sorted_selection(items)
        
        for item in sorted_items:
            self._indent_item_internal(item)
            
        self.sync_hierarchy()
        self.recalculate_all_dates()

    def outdent_selected_tasks(self, items):
        # Sort items by visual order
        sorted_items = self._get_sorted_selection(items)
        
        for item in sorted_items:
            self._outdent_item_internal(item)
            
        self.sync_hierarchy()
        self.recalculate_all_dates()

    def _get_sorted_selection(self, items):
        """Returns the items sorted by their appearance in the tree."""
        selected_ids = {id(i) for i in items}
        sorted_list = []
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if id(item) in selected_ids:
                sorted_list.append(item)
            iterator += 1
        return sorted_list

    def indent_smart(self, item):
        selected = self.selectedItems()
        if len(selected) > 1:
            self.indent_selected_tasks(selected)
        else:
            # If item passed from context menu is not selected, use it. 
            # Otherwise use selection (which might be just 1 item)
            target = item if item else (selected[0] if selected else None)
            if target:
                self.indent_task(target)

    def outdent_smart(self, item):
        selected = self.selectedItems()
        if len(selected) > 1:
            self.outdent_selected_tasks(selected)
        else:
            target = item if item else (selected[0] if selected else None)
            if target:
                self.outdent_task(target)

    def delete_smart(self, item):
        selected = self.selectedItems()
        if len(selected) > 1:
            # Bulk delete
            # Sort reverse to avoid index issues? 
            # Actually delete_task handles removal safely.
            # But we should probably ask for confirmation once.
            reply = QMessageBox.question(self, "Delete Tasks", 
                                       f"Are you sure you want to delete {len(selected)} tasks?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for i in selected:
                    self.delete_task(i)
        else:
            target = item if item else (selected[0] if selected else None)
            if target:
                self.delete_task(target)

    def expand_all_selected(self, items):
        """Recursively expand selected items and their children."""
        for item in items:
            self.expand_recursive(item)

    def expand_recursive(self, item: QTreeWidgetItem):
        """Recursively expand an item and all its descendants."""
        item.setExpanded(True)
        if isinstance(item, TaskTreeWidgetItem):
            item.node.expanded = True
            
        for i in range(item.childCount()):
            child = item.child(i)
            self.expand_recursive(child)

from PyQt6.QtWidgets import QTreeWidgetItemIterator
