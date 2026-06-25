"""
FocusView: a practical project cockpit.

It answers two questions:
1. What timeline paths can move the project end date?
2. What should I pay attention to right now, and what changed recently?
"""
from datetime import datetime, timedelta
from html import escape

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal

from utils.workday_calculator import WorkdayCalculator

DATE_FMT = "%Y-%m-%d"


def _parse(date_str):
    try:
        return datetime.strptime(date_str, DATE_FMT).date()
    except (ValueError, TypeError):
        return None


def _fmt(date_str):
    d = _parse(date_str)
    return d.strftime("%b %d") if d else "?"


def _flatten(roots):
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n)
            walk(n.children)

    walk(roots)
    return out


def _link(node):
    return (
        f"<a href='{node.id}' style='color:inherit; text-decoration:none;'>"
        f"{escape(node.name)}</a>"
    )


class FocusView(QWidget):
    task_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_nodes = []
        self.journal = []
        self.base_font_size = 13

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        self.layout_body = QVBoxLayout(body)
        self.layout_body.setContentsMargins(16, 12, 16, 16)
        self.layout_body.setSpacing(14)

        self.chain_panel = self._make_panel()
        self.week_panel = self._make_panel()
        self.layout_body.addWidget(self.chain_panel)
        self.layout_body.addWidget(self.week_panel)
        self.layout_body.addStretch()

    @staticmethod
    def _make_panel():
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #f7f6f3; border-radius: 10px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        return frame

    @staticmethod
    def _clear(frame):
        lay = frame.layout()
        while lay.count():
            item = lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _label(self, html, size=13):
        adjusted = max(9, size + (self.base_font_size - 13))
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet(f"font-size: {adjusted}px; color: #202020;")
        lbl.setOpenExternalLinks(False)
        lbl.linkActivated.connect(self.task_activated.emit)
        return lbl

    def load_nodes(self, root_nodes, journal=None):
        self.root_nodes = root_nodes or []
        if journal is not None:
            self.journal = list(journal)
        self._rebuild()

    def set_display_font_size(self, size: int):
        self.base_font_size = max(9, min(18, int(size)))
        self._rebuild()

    # ---------------- timeline logic ----------------

    def _driver_of(self, node, node_map):
        if node.predecessor_id and node.predecessor_id in node_map:
            return node_map[node.predecessor_id]
        if node.parent:
            siblings = node.parent.children
            try:
                idx = siblings.index(node)
            except ValueError:
                return None
            if not node.is_parallel and idx > 0:
                return siblings[idx - 1]
            return self._driver_of(node.parent, node_map)
        try:
            idx = self.root_nodes.index(node)
        except ValueError:
            return None
        if not node.is_parallel and idx > 0:
            return self.root_nodes[idx - 1]
        return None

    @staticmethod
    def _defining_leaf(node):
        while node.children:
            dated = [c for c in node.children if c.end_date]
            if not dated:
                return node
            node = max(dated, key=lambda c: c.end_date)
        return node

    def _chain_for_terminal(self, terminal, node_map):
        chain = [terminal]
        seen = {terminal.id}
        current = terminal
        while True:
            driver = self._driver_of(current, node_map)
            if driver is None:
                break
            driver = self._defining_leaf(driver)
            if driver.id in seen:
                break
            chain.append(driver)
            seen.add(driver.id)
            current = driver
        chain.reverse()
        return chain

    def _compute_chains(self, all_nodes, node_map, limit=3):
        leaves = sorted(
            (n for n in all_nodes if not n.children and n.end_date),
            key=lambda n: n.end_date,
            reverse=True,
        )
        chains = []
        seen = set()
        for leaf in leaves:
            chain = self._chain_for_terminal(leaf, node_map)
            key = tuple(n.id for n in chain)
            if chain and key not in seen:
                chains.append(chain)
                seen.add(key)
            if len(chains) >= limit:
                break
        return chains

    def _compute_slack(self, all_nodes, node_map, project_end):
        successors = {}
        for node in all_nodes:
            driver = self._driver_of(node, node_map)
            if driver is not None:
                successors.setdefault(driver.id, []).append(node)

        memo = {}

        def terminal_end(node, guard):
            if node.id in memo:
                return memo[node.id]
            if node.id in guard:
                return node.end_date or ""
            guard.add(node.id)
            best = node.end_date or ""
            for succ in successors.get(node.id, []):
                end = terminal_end(succ, guard)
                if end > best:
                    best = end
            memo[node.id] = best
            return best

        slack = {}
        for node in all_nodes:
            end = terminal_end(node, set())
            if not end or not project_end:
                continue
            if end >= project_end:
                slack[node.id] = 0
            else:
                slack[node.id] = max(
                    0, WorkdayCalculator.calculate_duration(end, project_end) - 1
                )
        return slack

    # ---------------- rendering ----------------

    def _rebuild(self):
        all_nodes = _flatten(self.root_nodes)
        node_map = {n.id: n for n in all_nodes}
        self._build_chain_panel(all_nodes, node_map)
        self._build_week_panel(all_nodes)

    def _build_chain_panel(self, all_nodes, node_map):
        self._clear(self.chain_panel)
        lay = self.chain_panel.layout()

        chains = self._compute_chains(all_nodes, node_map, limit=3)
        if not chains:
            lay.addWidget(self._label("No scheduled tasks yet."))
            return

        project_end = max((n.end_date or "" for n in all_nodes), default="")
        today = datetime.now().date()
        primary = chains[0]

        lay.addWidget(self._label(
            f"Project ends <b>{_fmt(project_end)}</b>. These are the top timeline paths:",
            size=14,
        ))

        def render_chain(chain, rank):
            push_task = next((t for t in chain if t.status != "Completed"), None)
            pills = []
            for task in chain:
                if task.status == "Completed":
                    style = "background:#E1F5EE; color:#085041;"
                    tag = "done"
                elif task is push_task and rank == 1:
                    style = "background:#FCEBEB; color:#791F1F; border:2px solid #E24B4A;"
                    end = _parse(task.end_date)
                    if end and end >= today:
                        left = WorkdayCalculator.calculate_duration(
                            today.strftime(DATE_FMT), task.end_date
                        )
                        tag = f"{left}d left"
                    else:
                        tag = "overdue"
                else:
                    style = "background:#ECEAE4; color:#444441;"
                    tag = f"{task.duration}d"
                pills.append(
                    f"<span style='{style} padding:3px 8px; border-radius:6px; "
                    f"white-space:nowrap;'>{_link(task)} - {tag}</span>"
                )
            name = "Critical path" if rank == 1 else f"Path {rank}"
            chain_end = chain[-1].end_date if chain else project_end
            return (
                f"<b>{name}</b> <span style='color:#777'>(ends {_fmt(chain_end)})</span><br>"
                + " <span style='color:#888'>-&gt;</span> ".join(pills)
            )

        for rank, chain in enumerate(chains, start=1):
            lay.addWidget(self._label(render_chain(chain, rank), size=13))

        push_task = next((t for t in primary if t.status != "Completed"), None)
        if push_task:
            owner = f" ({escape(push_task.owner)})" if push_task.owner else ""
            lay.addWidget(self._label(
                f"<span style='color:#A32D2D; font-weight:bold;'>Push here:</span> "
                f"<b>{_link(push_task)}</b>{owner} - every workday saved here "
                f"moves the project end a day earlier.",
                size=13,
            ))

        slack = self._compute_slack(all_nodes, node_map, project_end)
        chain_ids = {task.id for chain in chains for task in chain}
        watch = sorted(
            (
                n for n in all_nodes
                if not n.children
                and n.status != "Completed"
                and n.id not in chain_ids
                and 0 < slack.get(n.id, 999) <= 5
            ),
            key=lambda n: slack[n.id],
        )[:3]
        if watch:
            rows = "<br>".join(
                f"- {_link(n)} - only <b>{slack[n.id]}d</b> of slack"
                for n in watch
            )
            lay.addWidget(self._label(
                f"<span style='color:#854F0B; font-weight:bold;'>Watch list:</span> "
                f"if these slip past their slack they join the chain and push "
                f"{_fmt(project_end)}.<br>{rows}",
                size=13,
            ))

    def _build_week_panel(self, all_nodes):
        self._clear(self.week_panel)
        lay = self.week_panel.layout()

        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        next_start = week_start + timedelta(days=7)
        next_end = next_start + timedelta(days=6)
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start - timedelta(days=1)
        prior_week_start = week_start - timedelta(days=14)
        prior_week_end = week_start - timedelta(days=8)

        overdue, due_week, starting = [], [], []
        for node in all_nodes:
            if node.children or node.status == "Completed":
                continue
            start, end = _parse(node.start_date), _parse(node.end_date)
            if end and end < today:
                overdue.append(node)
            elif end and today <= end <= week_end:
                due_week.append(node)
            elif start and next_start <= start <= next_end:
                starting.append(node)

        lay.addWidget(self._label("<b>Focus board</b>", size=14))
        cols = QHBoxLayout()
        cols.setSpacing(10)

        for title, color, items, date_of, prefix in (
            ("Overdue", "#A32D2D", sorted(overdue, key=lambda n: n.end_date or ""),
             lambda n: n.end_date, "due"),
            ("Due this week", "#854F0B", sorted(due_week, key=lambda n: n.end_date or ""),
             lambda n: n.end_date, "due"),
            ("Starting next week", "#0F6E56", sorted(starting, key=lambda n: n.start_date or ""),
             lambda n: n.start_date, "starts"),
        ):
            cols.addWidget(self._task_card(title, color, items, date_of, prefix), 1)

        cols.addWidget(self._journal_card(
            f"Changes last week ({last_week_start.strftime('%b %d')}-{last_week_end.strftime('%b %d')})",
            self._journal_entries_between(last_week_start, last_week_end),
        ), 1)
        cols.addWidget(self._journal_card(
            f"Changes week before ({prior_week_start.strftime('%b %d')}-{prior_week_end.strftime('%b %d')})",
            self._journal_entries_between(prior_week_start, prior_week_end),
        ), 1)
        lay.addLayout(cols)

    def _task_card(self, title, color, items, date_of, prefix):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #ffffff; border-radius: 8px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        head = QLabel(title)
        head.setStyleSheet(f"font-size:12px; font-weight:bold; color:{color};")
        lay.addWidget(head)
        if items:
            for node in items[:8]:
                owner = f" - {escape(node.owner)}" if node.owner else ""
                lay.addWidget(self._label(
                    f"{_link(node)}<br><span style='color:#999; font-size:11px;'>"
                    f"{prefix} {_fmt(date_of(node))}{owner}</span>",
                    size=12,
                ))
            if len(items) > 8:
                lay.addWidget(self._label(
                    f"<span style='color:#999'>+{len(items) - 8} more...</span>",
                    size=11,
                ))
        else:
            lay.addWidget(self._label("<span style='color:#bbb'>none</span>", size=12))
        lay.addStretch()
        return card

    def _journal_card(self, title, entries):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #ffffff; border-radius: 8px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        head = QLabel(title)
        head.setStyleSheet("font-size:12px; font-weight:bold; color:#5F5E5A;")
        lay.addWidget(head)
        if entries:
            for entry in entries[:8]:
                ts = escape(entry.get("ts", ""))
                text = escape(entry.get("text", ""))
                lay.addWidget(self._label(
                    f"<span style='color:#999'>{ts}</span><br>{text}",
                    size=11,
                ))
            if len(entries) > 8:
                lay.addWidget(self._label(
                    f"<span style='color:#999'>+{len(entries) - 8} more...</span>",
                    size=11,
                ))
        else:
            lay.addWidget(self._label("<span style='color:#bbb'>none</span>", size=12))
        lay.addStretch()
        return card

    def _journal_entries_between(self, start, end):
        entries = []
        for entry in self.journal:
            ts = entry.get("ts", "")
            try:
                day = datetime.strptime(ts[:10], DATE_FMT).date()
            except (ValueError, TypeError):
                continue
            if start <= day <= end:
                entries.append(entry)
        entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
        return entries
