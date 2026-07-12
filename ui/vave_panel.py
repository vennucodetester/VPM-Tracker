import uuid

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils import usage_logger


VAVE_COLUMNS = [
    ("idea", "Idea"),
    ("category", "Category"),
    ("baseline_cost", "Baseline $"),
    ("proposed_cost", "Proposed $"),
    ("potential", "Potential $"),
    ("realized", "Realized $"),
    ("status", "Status"),
    ("notes", "Notes"),
]

MONEY_KEYS = {"baseline_cost", "proposed_cost", "potential", "realized"}
STATUS_VALUES = ["Idea", "Validated", "Implemented", "Realized", "Dropped"]
DEFAULT_CATEGORIES = ["Material", "Design", "Supplier", "Process"]


def money_text(value):
    if value is None or value == "":
        return ""
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return ""


def parse_money(text):
    clean = (text or "").strip()
    if not clean:
        return None
    clean = clean.replace("$", "").replace(",", "")
    return float(clean)


def normalized_item(raw):
    item = dict(raw or {})
    item.setdefault("id", uuid.uuid4().hex)
    item.setdefault("idea", "")
    item.setdefault("category", "")
    for key in MONEY_KEYS:
        value = item.get(key)
        try:
            item[key] = None if value in ("", None) else float(value)
        except (TypeError, ValueError):
            item[key] = None
    if item.get("status") not in STATUS_VALUES:
        item["status"] = "Idea"
    item.setdefault("notes", "")
    return item


class ComboDelegate(QStyledItemDelegate):
    def __init__(self, values, editable=False, parent=None):
        super().__init__(parent)
        self.values = list(values)
        self.editable = editable

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setEditable(self.editable)
        combo.addItems(self.values)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        if editor.findText(value) < 0 and value:
            editor.addItem(value)
        editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText().strip(), Qt.ItemDataRole.EditRole)


class VavePanel(QWidget):
    vave_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._loading = False
        self._old_cell = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.summary_label = QLabel()
        font = QFont()
        font.setBold(True)
        self.summary_label.setFont(font)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(VAVE_COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in VAVE_COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._remember_cell_value)
        self.table.currentItemChanged.connect(lambda cur, _prev: self._remember_cell_value(cur))

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 115)
        self.table.setColumnWidth(3, 115)
        self.table.setColumnWidth(4, 115)
        self.table.setColumnWidth(5, 115)
        self.table.setColumnWidth(6, 120)
        self.table.setColumnWidth(7, 320)

        self.table.setItemDelegateForColumn(1, ComboDelegate(self.category_values(), editable=True, parent=self.table))
        self.table.setItemDelegateForColumn(6, ComboDelegate(STATUS_VALUES, editable=False, parent=self.table))
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Idea")
        self.delete_button = QPushButton("Delete Selected")
        self.add_button.clicked.connect(self.add_item)
        self.delete_button.clicked.connect(self.delete_selected)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def category_values(self):
        seen = list(DEFAULT_CATEGORIES)
        for item in self._items:
            value = (item.get("category") or "").strip()
            if value and value not in seen:
                seen.append(value)
        return seen

    def set_items(self, items):
        self._items = [normalized_item(item) for item in (items or [])]
        self.refresh()

    def items(self):
        return [dict(item) for item in self._items]

    def add_item(self):
        self._items.append(normalized_item({"status": "Idea"}))
        self.refresh()
        usage_logger.log("vave_item_add")
        self.vave_changed.emit()

    def delete_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        reply = QMessageBox.question(
            self,
            "Delete VAVE Ideas",
            f"Delete {len(rows)} selected VAVE idea(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for row in rows:
            if 0 <= row < len(self._items):
                del self._items[row]
        self.refresh()
        usage_logger.log("vave_item_delete", count=len(rows))
        self.vave_changed.emit()

    def totals(self):
        potential = 0.0
        realized = 0.0
        for item in self._items:
            if item.get("status") == "Dropped":
                continue
            potential += float(item.get("potential") or 0)
            realized += float(item.get("realized") or 0)
        pct = (realized / potential * 100.0) if potential else 0.0
        return potential, realized, pct

    def refresh(self):
        self._loading = True
        try:
            self.table.setRowCount(len(self._items))
            self.table.setItemDelegateForColumn(
                1, ComboDelegate(self.category_values(), editable=True, parent=self.table)
            )
            for row, item in enumerate(self._items):
                for col, (key, _label) in enumerate(VAVE_COLUMNS):
                    value = item.get(key)
                    text = money_text(value) if key in MONEY_KEYS else str(value or "")
                    table_item = QTableWidgetItem(text)
                    table_item.setData(Qt.ItemDataRole.UserRole, value)
                    if key in MONEY_KEYS:
                        table_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        table_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self._apply_row_tint(table_item, item.get("status"))
                    self.table.setItem(row, col, table_item)
            self._update_summary()
        finally:
            self._loading = False

    def _apply_row_tint(self, table_item, status):
        if status == "Realized":
            table_item.setBackground(QBrush(QColor("#dff3df")))
        elif status == "Dropped":
            table_item.setBackground(QBrush(QColor("#e6e6e6")))
            table_item.setForeground(QBrush(QColor("#666666")))

    def _update_summary(self):
        potential, realized, pct = self.totals()
        self.summary_label.setText(
            f"Potential: ${potential:,.0f}   |   Realized: ${realized:,.0f}   |   {pct:.0f}% realized"
        )

    def _remember_cell_value(self, item):
        if item is None:
            return
        self._old_cell[(item.row(), item.column())] = item.text()

    def _on_item_changed(self, table_item):
        if self._loading or table_item is None:
            return
        row = table_item.row()
        col = table_item.column()
        if row < 0 or row >= len(self._items):
            return
        key, label = VAVE_COLUMNS[col]
        old_value = self._items[row].get(key)
        old_text = self._old_cell.get(
            (row, col),
            money_text(old_value) if key in MONEY_KEYS else str(old_value or ""),
        )
        try:
            if key in MONEY_KEYS:
                value = parse_money(table_item.text())
            elif key == "status":
                value = table_item.text().strip()
                if value not in STATUS_VALUES:
                    value = "Idea"
            else:
                value = table_item.text().strip()
        except ValueError:
            self._status_message(f"Invalid {label}; keeping previous value.")
            self._loading = True
            try:
                table_item.setText(old_text)
            finally:
                self._loading = False
            return

        self._items[row][key] = value
        usage_logger.log("vave_edit", col=label)
        self.refresh()
        self.vave_changed.emit()

    def _status_message(self, text):
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(text, 3000)
