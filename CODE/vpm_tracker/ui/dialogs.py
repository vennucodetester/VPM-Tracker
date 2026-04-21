from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, QListWidget, 
                             QDialogButtonBox, QHBoxLayout, QPlainTextEdit, QComboBox, QLineEdit)
from PyQt6.QtCore import Qt

class ImpactDialog(QDialog):
    def __init__(self, affected_tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule Impact Warning")
        self.resize(400, 300)
        
        self.result_action = "cancel" # cancel, update_all, keep_others
        
        layout = QVBoxLayout(self)
        
        # Message
        msg = QLabel(f"Changing this date will shift {len(affected_tasks)} other tasks.")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        
        # List of changes
        self.list_widget = QListWidget()
        for item in affected_tasks:
            # item = {node, old_start, new_start, delta}
            node = item['node']
            text = f"{node.name}: {item['old_start']} -> {item['new_start']} ({item['delta']} days)"
            self.list_widget.addItem(text)
        layout.addWidget(self.list_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_update_all = QPushButton("Update All (Ripple)")
        self.btn_update_all.setToolTip("Shift all dependent tasks to maintain the chain.")
        self.btn_update_all.clicked.connect(self.on_update_all)
        
        self.btn_keep_others = QPushButton("Only This Task (Create Gap)")
        self.btn_keep_others.setToolTip("Only move this task. Successors will stay where they are (creating a gap).")
        self.btn_keep_others.clicked.connect(self.on_keep_others)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_update_all)
        btn_layout.addWidget(self.btn_keep_others)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        
    def on_update_all(self):
        self.result_action = "update_all"
        self.accept()
        
    def on_keep_others(self):
        self.result_action = "keep_others"
        self.accept()

class BulkPasteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Paste Tasks")
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel("Paste task names (one per line):")
        layout.addWidget(lbl)
        
        self.text_edit = QPlainTextEdit()
        layout.addWidget(self.text_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_lines(self):
        text = self.text_edit.toPlainText()
        return [line.strip() for line in text.split('\n') if line.strip()]

class BulkEditDialog(QDialog):
    def __init__(self, title, parent=None, options=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(300, 150)
        self.value = None
        
        layout = QVBoxLayout(self)
        
        if options:
            self.input_widget = QComboBox()
            self.input_widget.addItems(options)
        else:
            self.input_widget = QLineEdit()
            
        layout.addWidget(self.input_widget)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def on_accept(self):
        if isinstance(self.input_widget, QComboBox):
            self.value = self.input_widget.currentText()
        else:
            self.value = self.input_widget.text()
        self.accept()

class LinkTaskDialog(QDialog):
    """Searchable picker for the predecessor of a task.

    Shows ancestor path so tasks with the same name (e.g. 'Costing Estimate' under
    two different microblocks) are distinguishable. Auto-filters as you type.
    """

    def __init__(self, current_node, all_nodes, parent=None):
        from PyQt6.QtWidgets import QListWidgetItem
        super().__init__(parent)
        self.setWindowTitle(f"Set Predecessor for: {current_node.name}")
        self.resize(520, 460)
        self.selected_node_id = None
        self._current_node = current_node

        layout = QVBoxLayout(self)

        hint = QLabel("Pick the task whose END DATE this one should follow.\n"
                      "Type to filter by name, owner, or date.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        # Build the candidate list: exclude self, descendants, and ancestors (no cycles).
        descendant_ids = {d.id for d in current_node.get_all_descendants()}
        ancestor_ids = set()
        a = current_node.parent
        while a is not None:
            ancestor_ids.add(a.id)
            a = a.parent

        preselect_row = -1
        for node in all_nodes:
            if node.id == current_node.id:
                continue
            if node.id in descendant_ids or node.id in ancestor_ids:
                continue

            path = self._ancestor_path(node)
            label = f"{path}  ({node.start_date} → {node.end_date})"
            if node.owner:
                label += f"  [{node.owner}]"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, node.id)
            self.list_widget.addItem(item)
            if current_node.predecessor_id == node.id:
                preselect_row = self.list_widget.count() - 1

        if preselect_row >= 0:
            self.list_widget.setCurrentRow(preselect_row)

        # Double-click accepts.
        self.list_widget.itemDoubleClicked.connect(lambda _i: self.on_accept())

        btn_row = QHBoxLayout()
        self.btn_clear = QPushButton("Clear Predecessor")
        self.btn_clear.setToolTip("Remove any existing predecessor link on this task.")
        self.btn_clear.clicked.connect(self.on_clear)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.search.setFocus()

    @staticmethod
    def _ancestor_path(node) -> str:
        parts = [node.name]
        p = node.parent
        while p is not None:
            parts.append(p.name)
            p = p.parent
        return " / ".join(reversed(parts))

    def _apply_filter(self, text: str):
        needle = text.lower().strip()
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            it.setHidden(bool(needle) and needle not in it.text().lower())

    def on_accept(self):
        selected = self.list_widget.selectedItems()
        if selected and not selected[0].isHidden():
            self.selected_node_id = selected[0].data(Qt.ItemDataRole.UserRole)
        self.accept()

    def on_clear(self):
        self.selected_node_id = ""  # Empty string signals "remove link"
        self.accept()
