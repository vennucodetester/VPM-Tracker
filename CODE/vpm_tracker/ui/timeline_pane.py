"""
TimelinePane — Gantt bars welded to the Tracker grid.

Unlike the old (deleted) gantt_chart.py, this pane does NOT keep its own
task list. Every paint asks the live TreeGridView where each row is on
screen right now (visualItemRect), so scrolling, expanding, collapsing
and editing in the grid are reflected instantly and can never drift out
of sync. Collapse a phase in the grid → its bars collapse to one summary
bar here, automatically.

Structure:
    TimelineContainer  (controls strip + horizontal scroll area)
        └── TimelineCanvas  (the actual painting surface)
"""
from datetime import datetime, date, timedelta

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QScrollArea, QFrame, QFileDialog, QToolTip,
                             QAbstractItemView)
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap

DATE_FMT = "%Y-%m-%d"

C_DONE = QColor("#1D9E75")
C_PROGRESS = QColor("#FFC107")
C_NOT_STARTED = QColor("#5C8DB8")
C_OVERDUE = QColor("#E24B4A")
C_PARENT = QColor("#546E7A")
C_TODAY = QColor("#EF9F27")
C_GRID = QColor(0, 0, 0, 25)
C_TEXT = QColor("#666666")

LEFT_PAD = 10
RIGHT_PAD = 30


def _parse(s):
    try:
        return datetime.strptime(s, DATE_FMT).date()
    except (ValueError, TypeError):
        return None


class TimelineCanvas(QWidget):
    def __init__(self, tree, parent=None):
        super().__init__(parent)
        self._tree = tree
        self.px_per_day = 0.0  # 0 = fit to width
        self._hits = []        # [(QRect, node)] for tooltips / click-to-jump
        self.setMouseTracking(True)
        self.setMinimumWidth(120)

    # ---- time range (recomputed each paint: 200 nodes is nothing) ----
    def _date_range(self):
        lo = hi = None
        stack = list(self._tree.root_nodes)
        while stack:
            n = stack.pop()
            stack.extend(n.children)
            s, e = _parse(n.start_date), _parse(n.end_date)
            if s and (lo is None or s < lo):
                lo = s
            if e and (hi is None or e > hi):
                hi = e
        if lo is None:
            today = date.today()
            return today - timedelta(days=7), today + timedelta(days=21)
        return lo - timedelta(days=3), hi + timedelta(days=7)

    def _effective_ppd(self, days):
        if self.px_per_day > 0:
            return self.px_per_day
        avail = max(self.parentWidget().width() if self.parentWidget()
                    else self.width(), 200) - LEFT_PAD - RIGHT_PAD - 20
        return max(0.5, avail / max(days, 1))

    def content_width(self):
        t0, t1 = self._date_range()
        days = (t1 - t0).days + 1
        return int(LEFT_PAD + days * self._effective_ppd(days) + RIGHT_PAD)

    def sizeHint(self):
        return QSize(self.content_width(), 200)

    def refresh(self):
        self.setMinimumWidth(self.content_width())
        self.updateGeometry()
        self.update()

    # ---- painting ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#fafaf8"))
        self._hits = []

        t0, t1 = self._date_range()
        days = (t1 - t0).days + 1
        ppd = self._effective_ppd(days)

        def x_of(d):
            return LEFT_PAD + (d - t0).days * ppd

        header_h = self._tree.header().height()
        self._draw_time_header(p, t0, t1, ppd, header_h, x_of)

        # Bars — one per visible grid row, at exactly the grid row's y.
        from ui.tree_grid_view import TaskTreeWidgetItem
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        today = date.today()
        viewport_h = self.height()
        it = QTreeWidgetItemIterator(self._tree)
        while it.value():
            item = it.value()
            it += 1
            if not isinstance(item, TaskTreeWidgetItem):
                continue
            r = self._tree.visualItemRect(item)
            if r.height() <= 0:
                continue  # hidden under a collapsed parent
            y = header_h + r.y()
            if y + r.height() < header_h or y > viewport_h:
                continue  # scrolled out of view
            self._draw_bar(p, item.node, y, r.height(), x_of, today)

        # Today line on top
        tx = int(x_of(today))
        if LEFT_PAD <= tx <= self.width():
            p.setPen(QPen(C_TODAY, 2))
            p.drawLine(tx, header_h, tx, self.height())

        p.end()

    def _draw_time_header(self, p, t0, t1, ppd, header_h, x_of):
        p.fillRect(QRect(0, 0, self.width(), header_h), QColor("#f0efe9"))
        p.setPen(QPen(C_TEXT))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)

        # Month bands + faint vertical gridlines down the chart
        d = date(t0.year, t0.month, 1)
        while d <= t1:
            x = int(x_of(d))
            if x >= LEFT_PAD - 40:
                p.setPen(QPen(C_GRID, 1))
                p.drawLine(x, 0, x, self.height())
                p.setPen(QPen(C_TEXT))
                p.drawText(x + 4, header_h - 6, d.strftime("%b %Y"))
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)

        # Weekly ticks when zoomed in enough to read them
        if ppd >= 5:
            d = t0 - timedelta(days=t0.weekday())
            while d <= t1:
                x = int(x_of(d))
                p.setPen(QPen(C_GRID, 1))
                p.drawLine(x, header_h - 4, x, self.height())
                d += timedelta(days=7)

    def _draw_bar(self, p, node, y, row_h, x_of, today):
        s, e = _parse(node.start_date), _parse(node.end_date)
        if not s or not e:
            return  # dateless (Inbox etc.) — no bar
        x1 = int(x_of(s))
        x2 = int(x_of(e + timedelta(days=1)))
        w = max(x2 - x1, 3)

        if node.children:
            bar_h = 5
            color = C_PARENT
        else:
            bar_h = max(10, row_h // 3)
            if node.status == "Completed":
                color = C_DONE
            elif e < today:
                color = C_OVERDUE
            elif node.status == "In Progress":
                color = C_PROGRESS
            else:
                color = C_NOT_STARTED

        bar_y = y + (row_h - bar_h) // 2
        rect = QRect(x1, bar_y, w, bar_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(rect, 2, 2)
        # widen the hit zone a little for easier hover/click
        self._hits.append((rect.adjusted(-2, -4, 2, 4), node))

    # ---- interaction ----
    def _node_at(self, pos):
        for rect, node in self._hits:
            if rect.contains(pos):
                return node
        return None

    def mouseMoveEvent(self, event):
        node = self._node_at(event.pos())
        if node:
            tip = f"{node.name}\n{node.start_date} → {node.end_date}  ·  {node.status}"
            if node.owner:
                tip += f"\n{node.owner}"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        node = self._node_at(event.pos())
        if node:
            self._tree.jump_to_node_id(node.id)
        super().mousePressEvent(event)

    # ---- export ----
    def export_image(self, path):
        """Full chart (all expanded rows, not just visible) with a name
        column — pasteable into email/slides."""
        from ui.tree_grid_view import TaskTreeWidgetItem
        rows = []

        def walk(item, depth):
            if isinstance(item, TaskTreeWidgetItem):
                rows.append((depth, item.node))
                if item.isExpanded():
                    for i in range(item.childCount()):
                        walk(item.child(i), depth + 1)

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i), 0)
        if not rows:
            return False

        NAME_W, ROW_H, HEAD_H = 230, 24, 28
        t0, t1 = self._date_range()
        days = (t1 - t0).days + 1
        ppd = max(self._effective_ppd(days), 2.0)
        chart_w = int(LEFT_PAD + days * ppd + RIGHT_PAD)
        pm = QPixmap(NAME_W + chart_w, HEAD_H + len(rows) * ROW_H + 10)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)

        def x_of(d):
            return NAME_W + LEFT_PAD + (d - t0).days * ppd

        # header
        p.fillRect(0, 0, pm.width(), HEAD_H, QColor("#f0efe9"))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        d = date(t0.year, t0.month, 1)
        while d <= t1:
            x = int(x_of(d))
            p.setPen(QPen(C_GRID, 1))
            p.drawLine(x, 0, x, pm.height())
            p.setPen(QPen(C_TEXT))
            p.drawText(x + 4, HEAD_H - 8, d.strftime("%b %Y"))
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)

        today = date.today()
        for idx, (depth, node) in enumerate(rows):
            y = HEAD_H + idx * ROW_H
            p.setPen(QPen(QColor("#222222")))
            name = node.name
            if len(name) > 34 - depth * 2:
                name = name[:31 - depth * 2] + "…"
            f = p.font()
            f.setBold(bool(node.children))
            p.setFont(f)
            p.drawText(8 + depth * 14, y + ROW_H - 7, name)
            s, e = _parse(node.start_date), _parse(node.end_date)
            if not s or not e:
                continue
            x1, x2 = int(x_of(s)), int(x_of(e + timedelta(days=1)))
            if node.children:
                color, bh = C_PARENT, 5
            elif node.status == "Completed":
                color, bh = C_DONE, 11
            elif e < today:
                color, bh = C_OVERDUE, 11
            elif node.status == "In Progress":
                color, bh = C_PROGRESS, 11
            else:
                color, bh = C_NOT_STARTED, 11
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRect(x1, y + (ROW_H - bh) // 2,
                                    max(x2 - x1, 3), bh), 2, 2)
        tx = int(x_of(today))
        p.setPen(QPen(C_TODAY, 2))
        p.drawLine(tx, HEAD_H, tx, pm.height())
        p.end()
        return pm.save(path)


class TimelineContainer(QWidget):
    """Controls strip + scrollable canvas. Lives on the right side of the
    Tracker splitter."""

    def __init__(self, tree, parent=None):
        super().__init__(parent)
        self._tree = tree

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        bar.setSpacing(4)

        def btn(label, tip, slot, checkable=False):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedHeight(22)
            b.setCheckable(checkable)
            b.clicked.connect(slot)
            bar.addWidget(b)
            return b

        self.toggle_btn = btn("Timeline ▾", "Show / hide the timeline",
                              self._toggle, checkable=True)
        self.toggle_btn.setChecked(True)
        btn("Fit", "Fit whole project in view", self._fit)
        btn("−", "Zoom out", lambda: self._zoom(0.7))
        btn("+", "Zoom in", lambda: self._zoom(1.4))
        btn("Export…", "Save the chart as a PNG image", self._export)
        bar.addStretch()
        root.addLayout(bar)

        self.canvas = TimelineCanvas(tree)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll)

        # Stay glued to the grid: any scroll, fold or edit repaints us.
        tree.verticalScrollBar().valueChanged.connect(
            lambda _: self.canvas.update())
        tree.itemExpanded.connect(lambda _: self.canvas.update())
        tree.itemCollapsed.connect(lambda _: self.canvas.update())
        tree.item_changed_signal.connect(lambda _: self.canvas.refresh())

    def refresh(self):
        self.canvas.refresh()

    def _toggle(self):
        visible = self.toggle_btn.isChecked()
        self.scroll.setVisible(visible)
        self.toggle_btn.setText("Timeline ▾" if visible else "Timeline ▸")

    def _fit(self):
        self.canvas.px_per_day = 0.0
        self.canvas.refresh()

    def _zoom(self, factor):
        t0, t1 = self.canvas._date_range()
        days = (t1 - t0).days + 1
        current = self.canvas._effective_ppd(days)
        self.canvas.px_per_day = max(0.5, min(30.0, current * factor))
        self.canvas.refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export timeline image", "timeline.png", "PNG image (*.png)")
        if path:
            self.canvas.export_image(path)
