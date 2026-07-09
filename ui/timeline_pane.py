"""
TimelinePane v3 — Gantt welded to the Tracker grid, redesigned around
two ideas after v2's hierarchy cues failed on deep trees:

1. Outline-level buttons (1 / 2 / 3 / All) — one click collapses the
   grid (and therefore the chart) to that depth. The readable
   "management chart" is the level-2/3 view, exactly like MS Project's
   Outline Level dropdown.

2. Groups draw as nested CONTAINER BOXES, not summary brackets:
   a light rounded outline wrapping the group's children rows,
   inset a few px per depth — real visual indentation. A COLLAPSED
   group draws as one fat slate bar (the clean phase bar).

Alignment contract: every paint asks Qt where the grid's viewport is
on screen (mapToGlobal), so bars sit pixel-exact beside their rows.
The controls strip lives BELOW the chart.
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
C_SUMMARY = QColor("#37474F")     # collapsed group bar
C_BOX = QColor("#90A4AE")         # expanded group outline
C_BOX_FILL = QColor(55, 71, 79, 6)
C_MILESTONE = QColor("#37474F")
C_TODAY = QColor("#FF6D00")
C_LINK = QColor("#78909C")
C_LABEL = QColor("#37474F")
C_BAND = QColor(0, 0, 0, 9)
C_MONTH_LINE = QColor(0, 0, 0, 38)
C_WEEK_LINE = QColor(0, 0, 0, 14)

LEFT_PAD = 18
RIGHT_PAD = 170  # room for labels after the last bar


def _parse(s):
    try:
        return datetime.strptime(s, DATE_FMT).date()
    except (ValueError, TypeError):
        return None


def _is_inbox(node):
    """True if this node is the Inbox notes group or lives inside it.

    The Inbox is a dateless root named 'inbox' used purely for quick notes.
    It is skipped everywhere in the timeline so notes never draw as bars.
    """
    n = node
    while n is not None:
        if n.parent is None and (n.name or "").strip().lower() == "inbox":
            return True
        n = n.parent
    return False


def _depth(node):
    d = 0
    n = node.parent
    while n is not None:
        d += 1
        n = n.parent
    return d


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
        stack = [r for r in self._tree.root_nodes if not _is_inbox(r)]
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
        return lo - timedelta(days=4), hi + timedelta(days=10)

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

    @staticmethod
    def _last_descendant_idx(rows, i):
        """Index of the last row that is a descendant of rows[i], or None."""
        node = rows[i][0]
        last = None
        j = i + 1
        while j < len(rows):
            anc = rows[j][0].parent
            ok = False
            while anc is not None:
                if anc is node:
                    ok = True
                    break
                anc = anc.parent
            if not ok:
                break
            last = j
            j += 1
        return last

    def _render_rows(self, p, rows, x_of, width, today, register_hits=False):
        """rows: list of (node, y, row_h) in visual order — shared by the
        live paint and the PNG export."""
        geom = {}  # node.id -> (x1, x2, y_center) for link arrows
        f = QFont(p.font())
        f.setPointSize(8)

        for idx, (node, y, row_h) in enumerate(rows):
            if idx % 2 == 1:
                p.fillRect(QRect(0, y, width, row_h), C_BAND)

        # --- groups first (boxes sit behind everything) ---
        for i, (node, y, row_h) in enumerate(rows):
            if not node.children:
                continue
            s, e = _parse(node.start_date), _parse(node.end_date)
            if not s or not e:
                continue
            x1 = int(x_of(s))
            x2 = int(x_of(e + timedelta(days=1)))
            yc = y + row_h // 2
            geom[node.id] = (x1, x2, yc)
            last = self._last_descendant_idx(rows, i)

            if last is None:
                # Collapsed group → one fat slate bar (management view)
                bh = max(14, int(row_h * 0.55))
                bar = QRect(x1, yc - bh // 2, max(x2 - x1, 4), bh)
                p.setPen(QPen(C_SUMMARY.darker(125), 1))
                p.setBrush(C_SUMMARY)
                p.drawRoundedRect(bar, 3, 3)
                if register_hits:
                    self._hits.append((bar.adjusted(-2, -4, 2, 4), node))
                if self.show_labels:
                    fb = QFont(f)
                    fb.setBold(True)
                    p.setFont(fb)
                    p.setPen(QPen(C_LABEL))
                    name = node.name if len(node.name) <= 40 else node.name[:37] + "…"
                    p.drawText(x2 + 8, yc + 4, name)
            else:
                # Expanded group → container box wrapping its children,
                # inset per depth so nesting reads as indentation.
                m = max(12 - _depth(node) * 3, 2)
                bx1, bx2 = x1 - m, x2 + m
                top = y + 2
                bottom = rows[last][1] + rows[last][2] - 2
                box = QRect(bx1, top, max(bx2 - bx1, 6), bottom - top)
                p.setPen(QPen(C_BOX, 1.4))
                p.setBrush(C_BOX_FILL)
                p.drawRoundedRect(box, 6, 6)
                if register_hits:
                    self._hits.append((QRect(bx1, y, box.width(), row_h),
                                       node))
                if self.show_labels:
                    fb = QFont(f)
                    fb.setBold(True)
                    p.setFont(fb)
                    p.setPen(QPen(C_SUMMARY))
                    name = node.name if len(node.name) <= 44 else node.name[:41] + "…"
                    p.drawText(bx1 + 8, yc + 4, name)

        # --- leaf bars & milestones on top ---
        p.setFont(f)
        for node, y, row_h in rows:
            if node.children:
                continue
            s, e = _parse(node.start_date), _parse(node.end_date)
            if not s or not e:
                continue
            x1 = int(x_of(s))
            x2 = int(x_of(e + timedelta(days=1)))
            yc = y + row_h // 2
            is_milestone = (e - s).days <= 0

            if is_milestone:
                size = min(row_h - 10, 16)
                cx = x1 + max((x2 - x1) // 2, 2)
                tri = QPolygonF([QPointF(cx, yc - size / 2),
                                 QPointF(cx + size / 2, yc),
                                 QPointF(cx, yc + size / 2),
                                 QPointF(cx - size / 2, yc)])
                p.setPen(QPen(C_MILESTONE.darker(120), 1))
                p.setBrush(C_MILESTONE)
                p.drawPolygon(tri)
                hit = QRect(int(cx - size), int(yc - size),
                            int(size * 2), int(size * 2))
                x2 = int(cx + size / 2)
            else:
                color = _status_color(node, today)
                bh = max(14, int(row_h * 0.55))
                bar = QRect(x1, yc - bh // 2, max(x2 - x1, 4), bh)
                p.setPen(QPen(color.darker(135), 1))
                p.setBrush(color)
                p.drawRoundedRect(bar, 3, 3)
                hit = bar.adjusted(-2, -4, 2, 4)

            geom[node.id] = (x1, x2, yc)
            if register_hits:
                self._hits.append((hit, node))
            if self.show_labels:
                p.setPen(QPen(C_LABEL))
                name = node.name if len(node.name) <= 40 else node.name[:37] + "…"
                p.drawText(x2 + 8, yc + 4, name)

        # --- dependency arrows (explicit links, both ends visible) ---
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
            # Inbox is notes, not schedule — never draw it on the chart.
            if _is_inbox(item.node):
                continue
            r = self._tree.visualItemRect(item)
            if r.height() <= 0:
                continue
            y = offset + r.y()
            # generous margins: an off-screen parent must still box its
            # visible children
            if y + r.height() < header_h - 800 or y > self.height() + 800:
                continue
            rows.append((item.node, y, r.height()))

        today = date.today()
        # Clip row drawing to below the header so boxes/labels from rows
        # scrolled upward can't paint over the month bar.
        p.save()
        p.setClipRect(QRect(0, header_h, self.width(),
                            self.height() - header_h))
        self._render_rows(p, rows, x_of, self.width(), today,
                          register_hits=True)
        p.restore()
        self._render_today(p, x_of, today, header_h, self.height())
        p.end()

    # ---------------- interaction ----------------
    def _node_at(self, pos):
        # later entries are drawn on top — search from the end
        for rect, node in reversed(self._hits):
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

    def wheelEvent(self, event):
        """Vertical wheel over the chart scrolls the GRID — the chart
        mirrors the grid's rows, so they move together regardless of
        which side the mouse is over. Shift+wheel (or a sideways wheel)
        still pans the chart horizontally via the scroll area."""
        if (abs(event.angleDelta().y()) > abs(event.angleDelta().x())
                and not (event.modifiers()
                         & Qt.KeyboardModifier.ShiftModifier)):
            from PyQt6.QtWidgets import QApplication
            QApplication.sendEvent(self._tree.viewport(), event)
            event.accept()
            return
        super().wheelEvent(event)

    # ---------------- export ----------------
    def export_image(self, path):
        """Full chart, every expanded row, name column + legend strip."""
        from ui.tree_grid_view import TaskTreeWidgetItem
        ordered = []

        def walk(item, depth):
            if isinstance(item, TaskTreeWidgetItem):
                if _is_inbox(item.node):
                    return  # exclude the Inbox notes group from exports too
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

        f = QFont(p.font())
        f.setPointSize(8)
        for idx, (depth, node) in enumerate(ordered):
            y = HEAD_H + idx * ROW_H
            f.setBold(bool(node.children))
            p.setFont(f)
            p.setPen(QPen(QColor("#222222")))
            name = node.name
            limit = 38 - depth * 2
            if len(name) > limit:
                name = name[:limit - 2] + "…"
            p.drawText(8 + depth * 12, y + ROW_H - 9, name)
        p.setPen(QPen(C_MONTH_LINE, 1))
        p.drawLine(NAME_W - 6, 0, NAME_W - 6, chart_bottom)

        rows = [(node, HEAD_H + idx * ROW_H, ROW_H)
                for idx, (_, node) in enumerate(ordered)]
        today = date.today()
        saved_labels = self.show_labels
        self.show_labels = False  # names live in the name column
        self._render_rows(p, rows, x_of, pm.width(), today)
        self.show_labels = saved_labels
        self._render_today(p, x_of, today, HEAD_H, chart_bottom)

        y = chart_bottom + 8
        f.setBold(False)
        p.setFont(f)
        x = 10
        for color, text in ((C_DONE, "Completed"),
                            (C_PROGRESS, "In progress"),
                            (C_NOT_STARTED, "Not started"),
                            (C_OVERDUE, "Overdue"),
                            (C_SUMMARY, "Group"),
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
    """Chart on top, controls strip at the BOTTOM (keeps the canvas top
    edge aligned with the grid's top edge)."""

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

        def btn(label, tip, slot, checkable=False, checked=False, width=None):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedHeight(22)
            if width:
                b.setFixedWidth(width)
            b.setCheckable(checkable)
            if checkable:
                b.setChecked(checked)
            b.clicked.connect(slot)
            bar.addWidget(b)
            return b

        self.toggle_btn = btn("Hide", "Show / hide the timeline",
                              self._toggle, checkable=True, checked=True)

        lv = QLabel("Levels:")
        lv.setStyleSheet("font-size: 10px; color: #555; margin-left: 6px;")
        bar.addWidget(lv)
        for label, level in (("1", 1), ("2", 2), ("3", 3), ("All", None)):
            btn(label,
                f"Collapse the plan to outline level {label} "
                "(grid and chart together)",
                lambda _, l=level: self._set_level(l), width=34)

        btn("Fit", "Fit whole project in view", self._fit)
        btn("−", "Zoom out", lambda: self._zoom(0.7), width=28)
        btn("+", "Zoom in", lambda: self._zoom(1.4), width=28)
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
            "<span style='color:#37474F'>■</span> group "
            "<span style='color:#90A4AE'>▢</span> open group")
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

    def _set_level(self, level):
        self._tree.set_outline_level(level)
        self.canvas.refresh()

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
