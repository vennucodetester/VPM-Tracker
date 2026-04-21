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
    def __init__(self, current_node, all_nodes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Link {current_node.name} to...")
        self.resize(400, 400)
        self.selected_node_id = None
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel("Select a Predecessor Task:")
        layout.addWidget(lbl)
        
        self.list_widget = QListWidget()
        
        # Filter logic:
        # 1. Not self
        # 2. Not a descendant (cycle)
        # 3. Not already the predecessor? (Optional, but good to show current)
        
        descendants = current_node.get_all_descendants()
        descendant_ids = {d.id for d in descendants}
        
        for node in all_nodes:
            if node.id == current_node.id:
                continue
            if node.id in descendant_ids:
                continue
                
            item_text = f"{node.name} ({node.start_date} - {node.end_date})"
            item = QListWidget() # Wait, wrong type for item
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, node.id)
            
            if current_node.predecessor_id == node.id:
                item.setSelected(True)
                
            self.list_widget.addItem(item)
            
        layout.addWidget(self.list_widget)
        
        # Clear Link Button
        self.btn_clear = QPushButton("Clear Link")
        self.btn_clear.clicked.connect(self.on_clear)
        layout.addWidget(self.btn_clear)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def on_accept(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            self.selected_node_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        self.accept()
        
    def on_clear(self):
        self.selected_node_id = "" # Empty string means clear
        self.accept()
