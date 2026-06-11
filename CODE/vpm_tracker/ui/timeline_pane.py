"""
TimelinePane v2 — Gantt bars welded to the Tracker grid, drawn to read
like MS Project: fat bordered bars with task-name labels, dark summary
brackets for phases, milestone diamonds, dependency arrows, row banding.

Alignment contract: the canvas asks Qt where the grid's viewport really
is on screen (mapToGlobal) every paint, so bars sit pixel-exact beside
their rows no matter what headers/toolbars surround either widget.
The controls strip lives BELOW the chart so the canvas top edge lines
up with the grid's top edge.
"""
from datetime import datetime, date, timedelta

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QScrollArea, QFrame, QFileDialog,
                             QToolTip)
from PyQt6.QtCore import Qt, QRect, QSize, QPoint, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QPolygonF, QFont

DATE_FMT = "%Y-%m-%d"

C_DONE = QColor("#43A047")
C_PROGRESS = QColor("#FFB300")
C_NOT_STARTED = QColor("#64B5F6")
C_OVERDUE = QColor("#E53935")
C_SUMMARY = QColor("#37474F")
C_MILESTONE = QColor("#37474F")
C_TODAY = QColor("#FF6D00")
C_LINK = QColor("#78909C")
C_LABEL = QColor("#37474F")
C_BAND = QColor(0, 0, 0, 9)
C_MONTH_LINE = QColor(0, 0, 0, 38)
C_WEEK_LINE = QColor(0, 0, 0, 14)

LEFT_PAD = 14
RIGHT_PAD = 160  # room for labels after the last bar


def _parse(s):
    try:
        return datetime.strptime(s, DATE_FMT).date()
    except (ValueError, TypeError):
        return None


def _status_color(node, today):
    e = _parse(node.end_date)
    if node.status == "Completed":
        return C_DONE
    if e and e < today:
        return C_OVERDUE
    if node.status == "In Progress":
        return C_PROGRESS
    return C_NOT_STARTED


class TimelineCanvas(QWidget):
    def __init__(self, tree, parent=None):
        super().__init__(parent)
        self._tree = tree
        self.px_per_day = 0.0     # 0 = fit to width
        self.show_labels = True
        self.show_links = True
        self._hits = []           # [(QRect, node)]
        self.setMouseTracking(True)
        self.setMinimumWidth(160)

    # ---------------- time range ----------------
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
        return lo - timedelta(days=3), hi + timedelta(days=10)

    def _effective_ppd(self, days):
        if self.px_per_day > 0:
            return self.px_per_day
        avail = max(self.parentWidget().width() if self.parentWidget()
                    else self.width(), 240) - LEFT_PAD - RIGHT_PAD
        return max(0.5, avail / max(days, 1))

    def content_width(self):
        t0, t1 = self._date_range()
        days = (t1 - t0).days + 1
        return int(LEFT_PAD + days * self._effective_ppd(days) + RIGHT_PAD)

    def sizeHint(self):
        return QSize(self.content_width(), 240)

    def refresh(self):
        self.setMinimumWidth(self.content_width())
        self.updateGeometry()
        self.update()

    # ---------------- shared chart renderer ----------------
    def _render_header(self, p, t0, t1, ppd, x_of, header_h, total_h, width):
        p.fillRect(QRect(0, 0, width, header_h), QColor("#eceae3"))
        f = QFont(p.font())
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        d = date(t0.year, t0.month, 1)
        while d <= t1:
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            x = int(x_of(d))
            x_next = int(x_of(min(nxt, t1 + timedelta(days=1))))
            p.setPen(QPen(C_MONTH_LINE, 1))
            p.drawLine(x, 0, x, total_h)
            p.setPen(QPen(QColor("#444444")))
            label = d.strftime("%b %Y") if ppd >= 1.4 else d.strftime("%b")
            p.drawText(QRect(x, 0, max(x_next - x, 30), header_h),
                       Qt.AlignmentFlag.AlignCenter, label)
            d = nxt
        if ppd >= 4:
            d = t0 - timedelta(days=t0.weekday())
            while d <= t1:
                x = int(x_of(d))
                p.setPen(QPen(C_WEEK_LINE, 1))
                p.drawLine(x, header_h, x, total_h)
                d += timedelta(days=7)
        p.setPen(QPen(C_MONTH_LINE, 1))
        p.drawLine(0, header_h, width, header_h)

    def _render_rows(self, p, rows, x_of, width, today,
                     register_hits=False):
        """rows: list of (node, y, row_h) — shared by live paint + export."""
        geom = {}  # node.id -> (x1, x2, y_center) for link arrows
        f = QFont(p.font())
        f.setPointSize(8)
        f.setBold(False)
        p.setFont(f)

        for idx, (node, y, row_h) in enumerate(rows):
            if idx % 2 == 1:
                p.fillRect(QRect(0, y, width, row_h), C_BAND)

        for node, y, row_h in rows:
            s, e = _parse(node.start_date), _parse(node.end_date)
            if not s or not e:
                continue
            x1 = int(x_of(s))
            x2 = int(x_of(e + timedelta(days=1)))
            w = max(x2 - x1, 4)
            yc = y + row_h // 2
            is_parent = bool(node.children)
            is_milestone = (not is_parent) and (e - s).days <= 0

            if is_parent:
                # MS Project-style summary bracket: thick dark bar with
                # downward end caps.
                bh = 8
                bar = QRect(x1, yc - bh // 2 - 2, w, bh)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(C_SUMMARY)
                p.drawRect(bar)
                cap = bh + 4
                for cx in (x1, x2):
                    tri = QPolygonF([QPointF(cx - 5, bar.bottom() + 1),
                                     QPointF(cx + 5, bar.bottom() + 1),
                                     QPointF(cx, bar.bottom() + 1 + cap // 2)])
                    p.drawPolygon(tri)
                hit = bar.adjusted(-2, -6, 2, 10)
            elif is_milestone:
                size = min(row_h - 10, 16)
                cx = x1 + max((x2 - x1) // 2, 2)
                tri = QPolygonF([QPointF(cx, yc - size / 2),
                                 QPointF(cx + size / 2, yc),
                                 QPointF(cx, yc + size / 2),
                                 QPointF(cx - size / 2, yc)])
                p.setPen(QPen(C_MILESTONE.darker(120), 1))
                p.setBrush(C_MILESTONE)
                p.drawPolygon(tri)
                hit = QRect(int(cx - size), int(yc - size), int(size * 2),
                            int(size * 2))
                x2 = int(cx + size / 2)  # labels/arrows hang off the diamond
            else:
                color = _status_color(node, today)
                bh = max(14, int(row_h * 0.55))
                bar = QRect(x1, yc - bh // 2, w, bh)
                p.setPen(QPen(color.darker(135), 1))
                p.setBrush(color)
                p.drawRoundedRect(bar, 3, 3)
                hit = bar.adjusted(-2, -4, 2, 4)

            geom[node.id] = (x1, x2, yc)
            if register_hits:
                self._hits.append((hit, node))

            if self.show_labels:
                p.setPen(QPen(C_LABEL))
                name = node.name if len(node.name) <= 38 else node.name[:35] + "…"
                fb = QFont(p.font())
                fb.setBold(is_parent)
                p.setFont(fb)
                p.drawText(x2 + 8, yc + 4, name)

        # Dependency arrows for explicit predecessor links, both ends visible
        if self.show_links:
            p.setPen(QPen(C_LINK, 1.4))
            p.setBrush(C_LINK)
            for node, y, row_h in rows:
                pid = node.predecessor_id
                if not pid or pid not in geom or node.id not in geom:
                    continue
                px1, px2, pyc = geom[pid]
                sx1, sx2, syc = geom[node.id]
                elbow_x = px2 + 7
                p.drawLine(px2 + 1, pyc, elbow_x, pyc)
                p.drawLine(elbow_x, pyc, elbow_x, syc)
                p.drawLine(elbow_x, syc, max(sx1 - 3, elbow_x), syc)
                ax = max(sx1 - 3, elbow_x)
                arrow = QPolygonF([QPointF(ax, syc - 4),
                                   QPointF(ax, syc + 4),
                                   QPointF(ax + 5, syc)])
                p.drawPolygon(arrow)
        return geom

    def _render_today(self, p, x_of, today, y0, y1):
        tx = int(x_of(today))
        p.setPen(QPen(C_TODAY, 2))
        p.drawLine(tx, y0, tx, y1)
        f = QFont(p.font())
        f.setPointSize(7)
        p.setFont(f)
        p.setPen(QPen(C_TODAY))
        p.drawText(tx + 3, y0 + 10, "Today")

    # ---------------- live painting ----------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#fbfaf7"))
        self._hits = []

        t0, t1 = self._date_range()
        days = (t1 - t0).days + 1
        ppd = self._effective_ppd(days)

        def x_of(d):
            return LEFT_PAD + (d - t0).days * ppd

        # Pixel-exact row offset: where is the grid's viewport relative
        # to this canvas, on the actual screen?
        try:
            tree_top = self._tree.viewport().mapToGlobal(QPoint(0, 0)).y()
            my_top = self.mapToGlobal(QPoint(0, 0)).y()
            offset = tree_top - my_top
        except RuntimeError:
            offset = 24
        header_h = max(offset, 20)

        self._render_header(p, t0, t1, ppd, x_of, header_h,
                            self.height(), self.width())

        from ui.tree_grid_view import TaskTreeWidgetItem
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        rows = []
        it = QTreeWidgetItemIterator(self._tree)
        while it.value():
            item = it.value()
            it += 1
            if not isinstance(item, TaskTreeWidgetItem):
                continue
            r = self._tree.visualItemRect(item)
            if r.height() <= 0:
                continue
            y = offset + r.y()
            if y + r.height() < header_h or y > self.height():
                continue
            rows.append((item.node, y, r.height()))

        today = date.today()
        self._render_rows(p, rows, x_of, self.width(), today,
                          register_hits=True)
        self._render_today(p, x_of, today, header_h, self.height())
        p.end()

    # ---------------- interaction ----------------
    def _node_at(self, pos):
        for rect, node in self._hits:
            if rect.contains(pos):
                return node
        return None

    def mouseMoveEvent(self, event):
        node = self._node_at(event.pos())
        if node:
            tip = (f"{node.name}\n{node.start_date} → {node.end_date}"
                   f"  ·  {node.status}")
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

    # ---------------- export ----------------
    def export_image(self, path):
        """Full chart, every expanded row, name column + legend strip."""
        from ui.tree_grid_view import TaskTreeWidgetItem
        ordered = []

        def walk(item, depth):
            if isinstance(item, TaskTreeWidgetItem):
                ordered.append((depth, item.node))
                if item.isExpanded():
                    for i in range(item.childCount()):
                        walk(item.child(i), depth + 1)

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i), 0)
        if not ordered:
            return False

        NAME_W, ROW_H, HEAD_H, LEGEND_H = 250, 28, 30, 30
        t0, t1 = self._date_range()
        days = (t1 - t0).days + 1
        ppd = max(self._effective_ppd(days), 2.5)
        chart_w = int(LEFT_PAD + days * ppd + RIGHT_PAD)
        pm = QPixmap(NAME_W + chart_w,
                     HEAD_H + len(ordered) * ROW_H + LEGEND_H)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        def x_of(d):
            return NAME_W + LEFT_PAD + (d - t0).days * ppd

        chart_bottom = HEAD_H + len(ordered) * ROW_H
        self._render_header(p, t0, t1, ppd, x_of, HEAD_H,
                            chart_bottom, pm.width())

        # Name column
        f = QFont(p.font())
        f.setPointSize(8)
        for idx, (depth, node) in enumerate(ordered):
            y = HEAD_H + idx * ROW_H
            f.setBold(bool(node.children))
            p.setFont(f)
            p.setPen(QPen(QColor("#222222")))
            name = node.name
            limit = 36 - depth * 2
            if len(name) > limit:
                name = name[:limit - 2] + "…"
            p.drawText(8 + depth * 14, y + ROW_H - 9, name)
        p.setPen(QPen(C_MONTH_LINE, 1))
        p.drawLine(NAME_W - 6, 0, NAME_W - 6, chart_bottom)

        rows = [(node, HEAD_H + idx * ROW_H, ROW_H)
                for idx, (_, node) in enumerate(ordered)]
        today = date.today()
        # labels are in the name column already — avoid double text
        saved_labels = self.show_labels
        self.show_labels = False
        self._render_rows(p, rows, x_of, pm.width(), today)
        self.show_labels = saved_labels
        self._render_today(p, x_of, today, HEAD_H, chart_bottom)

        # Legend strip
        y = chart_bottom + 8
        f.setBold(False)
        f.setPointSize(8)
        p.setFont(f)
        x = 10
        for color, text in ((C_DONE, "Completed"),
                            (C_PROGRESS, "In progress"),
                            (C_NOT_STARTED, "Not started"),
                            (C_OVERDUE, "Overdue"),
                            (C_SUMMARY, "Phase"),
                            (C_MILESTONE, "◆ Milestone")):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRect(QRect(x, y, 12, 12))
            p.setPen(QPen(QColor("#333333")))
            p.drawText(x + 16, y + 11, text)
            x += 16 + 10 + len(text) * 6 + 14
        p.end()
        return pm.save(path)


class TimelineContainer(QWidget):
    """Chart on top, controls strip at the BOTTOM — keeping the canvas
    top edge aligned with the grid's top edge."""

    def __init__(self, tree, parent=None):
        super().__init__(parent)
        self._tree = tree

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = TimelineCanvas(tree)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        bar.setSpacing(4)

        def btn(label, tip, slot, checkable=False, checked=False):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedHeight(22)
            b.setCheckable(checkable)
            if checkable:
                b.setChecked(checked)
            b.clicked.connect(slot)
            bar.addWidget(b)
            return b

        self.toggle_btn = btn("Hide", "Show / hide the timeline",
                              self._toggle, checkable=True, checked=True)
        btn("Fit", "Fit whole project in view", self._fit)
        btn("−", "Zoom out", lambda: self._zoom(0.7))
        btn("+", "Zoom in", lambda: self._zoom(1.4))
        self.labels_btn = btn("Labels", "Show task names next to bars",
                              self._set_flags, checkable=True, checked=True)
        self.links_btn = btn("Links", "Show dependency arrows",
                             self._set_flags, checkable=True, checked=True)
        btn("Export…", "Save the full chart as a PNG image", self._export)

        legend = QLabel(
            "<span style='color:#43A047'>■</span> done "
            "<span style='color:#FFB300'>■</span> active "
            "<span style='color:#64B5F6'>■</span> planned "
            "<span style='color:#E53935'>■</span> late "
            "<span style='color:#37474F'>▬</span> phase")
        legend.setStyleSheet("font-size: 10px; color: #555;")
        bar.addWidget(legend)
        bar.addStretch()
        root.addLayout(bar)

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
        self.toggle_btn.setText("Hide" if visible else "Show timeline")

    def _set_flags(self):
        self.canvas.show_labels = self.labels_btn.isChecked()
        self.canvas.show_links = self.links_btn.isChecked()
        self.canvas.update()

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
