
from PyQt6.QtWidgets import (QHeaderView, QStyleOptionHeader, QStyle, QMenu, 
                            QWidgetAction, QCheckBox, QWidget, QVBoxLayout, 
                            QPushButton, QHBoxLayout, QApplication, QLineEdit,
                            QDialog, QScrollArea, QLabel, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize, QPoint
from PyQt6.QtGui import QPainter, QIcon, QAction, QMouseEvent

class FilterPopup(QDialog):
    def __init__(self, column_values, active_filter, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.column_values = column_values
        self.active_filter = active_filter # Set of selected values, or None if all
        self.result_filter = None # Will be set on OK
        
        self.checkboxes = []
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(4, 4, 4, 4)
        self.layout().setSpacing(4)
        
        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.textChanged.connect(self.on_search_text_changed)
        self.layout().addWidget(self.search_bar)
        
        # Select All
        self.cb_all = QCheckBox("(Select All)")
        self.cb_all.toggled.connect(self.on_all_toggled)
        self.layout().addWidget(self.cb_all)
        
        # Scroll Area for List
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(200) # Limit height
        
        content_widget = QWidget()
        self.list_layout = QVBoxLayout(content_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Populate List
        for val in self.column_values:
            cb = QCheckBox(str(val))
            # Check if currently selected
            if self.active_filter is None or val in self.active_filter:
                cb.setChecked(True)
            
            self.checkboxes.append((val, cb))
            self.list_layout.addWidget(cb)
            cb.toggled.connect(self.update_all_state)
            
        scroll.setWidget(content_widget)
        self.layout().addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        self.layout().addLayout(btn_layout)
        
        self.update_all_state()
        
    def on_search_text_changed(self, text):
        text = text.lower().strip()
        for val, cb in self.checkboxes:
            if not text or text in str(val).lower():
                cb.setVisible(True)
            else:
                cb.setVisible(False)
        self.update_all_state()
        
    def update_all_state(self):
        # Only consider visible checkboxes
        visible_cbs = [cb for _, cb in self.checkboxes if not cb.isHidden()]
        if not visible_cbs: 
            return
            
        all_checked = all(cb.isChecked() for cb in visible_cbs)
        self.cb_all.blockSignals(True)
        self.cb_all.setChecked(all_checked)
        self.cb_all.blockSignals(False)

    def on_all_toggled(self, checked):
        # Only toggle visible checkboxes
        for _, cb in self.checkboxes:
            if not cb.isHidden():
                cb.setChecked(checked)
                
    def accept(self):
        # Collect results
        selected = set()
        is_searching = bool(self.search_bar.text().strip())
        
        # Logic:
        # If searching, we only affect visible items? 
        # Or we take the state of ALL items?
        # Excel: If I search and uncheck "Select All", it unchecks only visible.
        # If I search and check "Select All", it checks only visible.
        # Hidden items (filtered out by search) retain their state.
        
        for val, cb in self.checkboxes:
            if cb.isChecked():
                if is_searching:
                    if not cb.isHidden():
                        selected.add(val)
                else:
                    selected.add(val)
                
        # If all selected, return None (no filter)
        # Note: If searching, we might have selected < all, so this logic still holds.
        # But if we selected everything visible, and hidden were excluded, len(selected) < len(all).
        # So it will correctly return a filter set.
        
        if len(selected) == len(self.column_values):
            self.result_filter = None
        else:
            self.result_filter = selected
            
        super().accept()

class FilterHeaderView(QHeaderView):
    filter_changed = pyqtSignal(int, object) # column, selected_values (set or None)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        
        # Store filter state: {column: {set of checked values}}
        # If a column is not in dict, or set is empty/None, no filter.
        self.active_filters = {} 
        self.column_values = {} # {column: [all unique values]} - populated by parent

        # Icon for filter
        self.filter_icon_size = 16
        self.padding = 4

    def set_filter_values(self, column, values):
        """Update the list of available values for a column."""
        self.column_values[column] = sorted(list(set(values)))

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        # Draw Filter Icon
        # Position: Right side of the section
        icon_rect = QRect(
            rect.right() - self.filter_icon_size - self.padding,
            rect.center().y() - self.filter_icon_size // 2,
            self.filter_icon_size,
            self.filter_icon_size
        )
        
        # Check if filter is active for this column
        is_filtered = logicalIndex in self.active_filters and self.active_filters[logicalIndex] is not None

        # Draw a simple funnel shape
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if is_filtered:
            painter.setBrush(Qt.GlobalColor.blue)
            painter.setPen(Qt.GlobalColor.blue)
        else:
            painter.setBrush(Qt.GlobalColor.gray)
            painter.setPen(Qt.GlobalColor.gray)

        # Draw funnel
        # Simple triangle + rectangle
        x = icon_rect.x()
        y = icon_rect.y()
        w = icon_rect.width()
        h = icon_rect.height()
        
        # Just draw a simple triangle for now to represent filter
        path = [(x, y), (x + w, y), (x + w/2, y + h)]
        
        # Use standard icon if possible, or text "Y"
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        
        # Draw a small indicator
        indicator_text = "▼"
        if is_filtered:
            indicator_text = "Y" # Funnel-ish
            painter.setPen(Qt.GlobalColor.blue)
        
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, indicator_text)
        
        painter.restore()

    def mousePressEvent(self, event: QMouseEvent):
        # Check if click is on the filter icon area
        logicalIndex = self.logicalIndexAt(event.pos())
        if logicalIndex == -1:
            super().mousePressEvent(event)
            return

        # Calculate icon rect for this section
        # Note: sectionViewportPosition returns the x-coordinate (for horizontal header)
        x_start = self.sectionViewportPosition(logicalIndex)
        header_width = self.sectionSize(logicalIndex)
        header_height = self.height()
        
        # Right aligned icon
        icon_rect = QRect(
            x_start + header_width - self.filter_icon_size - self.padding * 2,
            0,
            self.filter_icon_size + self.padding * 2,
            header_height
        )

        if icon_rect.contains(event.pos()):
            self.show_filter_popup(logicalIndex)
        else:
            super().mousePressEvent(event)

    def show_filter_popup(self, column):
        if column not in self.column_values:
            return

        all_values = self.column_values[column]
        current_filter = self.active_filters.get(column)
        
        popup = FilterPopup(all_values, current_filter, self)
        
        # Position: Bottom-Left of the header section
        x_pos = self.sectionViewportPosition(column)
        header_height = self.height()
        
        # Map to global
        global_pos = self.mapToGlobal(QPoint(x_pos, header_height))
        
        popup.move(global_pos)
        
        if popup.exec():
            # Apply Filter
            new_filter = popup.result_filter
            if new_filter is None:
                self.active_filters.pop(column, None)
            else:
                self.active_filters[column] = new_filter
                
            self.filter_changed.emit(column, new_filter)
            self.viewport().update()
