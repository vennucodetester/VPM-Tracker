"""
Gantt Chart Widget - Microsoft Project Style

A comprehensive Gantt chart visualization with:
- Timeline rendering with horizontal task bars
- Critical path highlighting
- Dependency arrows (Finish-to-Start)
- Milestone markers
- Slack/float visualization
- Zoom and pan controls
- Color-coded tasks by status and criticality
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                             QLabel, QPushButton, QSlider, QSplitter, QTreeWidget,
                             QTreeWidgetItem, QHeaderView, QToolBar, QStyle, QLineEdit,
                             QCheckBox, QComboBox, QDateEdit, QSpinBox, QGroupBox,
                             QTreeWidgetItemIterator, QMenu)
from PyQt6.QtCore import Qt, QRect, QPoint, QPointF, QSize, pyqtSignal, QDate
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QPainterPath,
                        QFont, QPalette, QPolygonF, QLinearGradient, QAction)

from models.task_node import TaskNode
from utils.critical_path import CriticalPathAnalyzer


def get_top_n_critical_paths(root_nodes: List[TaskNode], n: int = 5) -> List[Dict]:
    """
    Get top N critical paths using progressive hiding algorithm.

    Args:
        root_nodes: List of root task nodes
        n: Number of critical paths to find (default 5)

    Returns:
        List of dictionaries with:
        - number: Path number (1-5)
        - task_ids: Set of critical task IDs
        - tasks: List of TaskNode objects
    """
    hidden_task_ids = set()
    critical_paths = []

    for i in range(n):
        # Rebuild tree without hidden tasks
        filtered_roots = _rebuild_tree_without_hidden(root_nodes, hidden_task_ids)

        if not filtered_roots:
            break  # No more tasks to analyze

        # Calculate critical path
        analyzer = CriticalPathAnalyzer(filtered_roots)
        results = analyzer.analyze()

        critical_ids = results['critical_path_ids']
        if not critical_ids:
            break  # No more critical paths

        # Get actual task objects
        critical_tasks = [task for task in _flatten_all_nodes(filtered_roots)
                         if task.id in critical_ids]

        # Store this critical path
        critical_paths.append({
            'number': i + 1,
            'task_ids': critical_ids,
            'tasks': critical_tasks
        })

        # Hide these tasks for next iteration
        hidden_task_ids.update(critical_ids)

    return critical_paths


def _rebuild_tree_without_hidden(root_nodes: List[TaskNode], hidden_ids: Set[str]) -> List[TaskNode]:
    """Rebuild task tree excluding hidden task IDs."""
    if not hidden_ids:
        return root_nodes

    def clone_node_tree(node: TaskNode, parent: Optional[TaskNode] = None) -> Optional[TaskNode]:
        # Skip hidden nodes
        if node.id in hidden_ids:
            return None

        # Clone this node
        cloned = TaskNode(node.name, parent=parent)
        cloned.id = node.id
        cloned.status = node.status
        cloned.owner = node.owner
        cloned.start_date = node.start_date
        cloned.end_date = node.end_date
        # duration is auto-calculated from start_date and end_date, no need to set
        cloned.is_parallel = node.is_parallel
        cloned.predecessor_id = node.predecessor_id
        cloned.notes = node.notes

        # Recursively clone children (excluding hidden ones)
        for child in node.children:
            cloned_child = clone_node_tree(child, cloned)
            if cloned_child:
                cloned.add_child(cloned_child)

        return cloned

    # Rebuild roots
    new_roots = []
    for root in root_nodes:
        cloned_root = clone_node_tree(root)
        if cloned_root:
            new_roots.append(cloned_root)

    return new_roots


def _flatten_all_nodes(nodes: List[TaskNode]) -> List[TaskNode]:
    """Flatten hierarchical nodes to a list."""
    result = []
    for node in nodes:
        result.append(node)
        if node.children:
            result.extend(_flatten_all_nodes(node.children))
    return result
from vpm_tracker_core import Columns

DATE_FMT = "%Y-%m-%d"


class TopCriticalPathsPanel(QWidget):
    """
    Left panel displaying top 5 critical paths.
    Shows tasks in expandable groups, click to highlight in Gantt.
    """

    task_clicked = pyqtSignal(TaskNode)  # Emitted when a task is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.critical_paths = []
        self.setup_ui()

    def setup_ui(self):
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Title
        title = QLabel("TOP 5 CRITICAL PATHS")
        title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #FF5050; padding: 5px;")
        layout.addWidget(title)

        # Description
        desc = QLabel("Progressive critical path analysis.\nClick task to highlight in timeline.")
        desc.setStyleSheet("color: #aaa; font-size: 9pt; padding: 0 5px 10px 5px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Tree widget for critical paths
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

    def load_critical_paths(self, root_nodes: List[TaskNode]):
        """Load and display top 5 critical paths."""
        self.tree.clear()
        self.critical_paths = get_top_n_critical_paths(root_nodes, n=5)

        for path_info in self.critical_paths:
            path_number = path_info['number']
            tasks = path_info['tasks']

            # Create parent item for this critical path
            parent_item = QTreeWidgetItem(self.tree)
            parent_item.setText(0, f"🔴 {path_number}{'st' if path_number == 1 else 'nd' if path_number == 2 else 'rd' if path_number == 3 else 'th'} Critical Path ({len(tasks)} tasks)")
            parent_item.setExpanded(path_number == 1)  # Expand first path by default

            # Set bold font for parent
            font = parent_item.font(0)
            font.setBold(True)
            parent_item.setFont(0, font)

            # Group tasks by their parent to show hierarchy
            tasks_by_parent = {}
            for task in tasks:
                parent_key = task.parent.id if task.parent else None
                if parent_key not in tasks_by_parent:
                    tasks_by_parent[parent_key] = []
                tasks_by_parent[parent_key].append(task)

            # Add task items grouped by parent
            for parent_key, child_tasks in tasks_by_parent.items():
                if child_tasks:
                    # Get parent name (one level up)
                    parent_name = child_tasks[0].parent.name if child_tasks[0].parent else "Root"

                    # Create parent group item
                    parent_group_item = QTreeWidgetItem(parent_item)
                    parent_group_item.setText(0, f"   📁 {parent_name}")
                    parent_group_font = parent_group_item.font(0)
                    parent_group_font.setItalic(True)
                    parent_group_item.setFont(0, parent_group_font)
                    parent_group_item.setExpanded(True)

                    # Add critical child tasks under the parent
                    for task in child_tasks:
                        task_item = QTreeWidgetItem(parent_group_item)
                        task_item.setText(0, f"      ⚠️  {task.name}")
                        task_item.setData(0, Qt.ItemDataRole.UserRole, task)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on a task item."""
        task = item.data(0, Qt.ItemDataRole.UserRole)
        if task:  # Only emit if it's a task item (not a path header)
            self.task_clicked.emit(task)


class GanttTimeline(QWidget):
    """
    The timeline canvas where task bars, dependencies, and critical path are drawn.
    """

    task_double_clicked = pyqtSignal(TaskNode)
    reload_required = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(400)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Data
        self.tasks: List[TaskNode] = []
        self.task_y_positions: Dict[str, int] = {}  # task_id -> y position
        self.node_map: Dict[str, TaskNode] = {}

        # Critical path data
        self.analyzer: Optional[CriticalPathAnalyzer] = None
        self.critical_path_ids: Set[str] = set()  # Critical LEAF tasks
        self.critical_parent_ids: Set[str] = set()  # Parents with critical descendants
        self.slack_data: Dict[str, int] = {}

        # Hidden tasks tracking
        self.root_nodes: List[TaskNode] = []
        self.hidden_task_ids: Set[str] = set()

        # Timeline settings
        self.start_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self.pixels_per_day = 20  # Zoom level
        self.row_height = 35
        self.header_height = 60
        self.left_margin = 10
        self.top_margin = self.header_height + 10

        # Colors (Microsoft Project inspired)
        self.color_critical = QColor(255, 80, 80)       # Red for critical path
        self.color_normal = QColor(100, 150, 255)       # Blue for normal tasks
        self.color_completed = QColor(100, 200, 100)    # Green for completed
        self.color_milestone = QColor(255, 200, 50)     # Gold for milestones
        self.color_slack = QColor(150, 150, 150, 100)   # Gray transparent for slack
        self.color_dependency = QColor(80, 80, 80)      # Dark gray for arrows
        self.color_today = QColor(255, 100, 0, 150)     # Orange for today marker
        self.color_grid = QColor(200, 200, 200, 50)     # Light gray for grid
        self.color_highlight = QColor(255, 140, 0, 200) # Orange for highlighted task (from critical paths panel)

        # Interaction
        self.hovered_task: Optional[TaskNode] = None
        self.highlighted_task: Optional[TaskNode] = None
        self.show_critical_path = True
        self.show_slack = True
        self.show_dependencies = True

        # Set background
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        self.setPalette(pal)

        # Tooltip setup
        self.setToolTip("")

    def load_tasks(self, root_nodes: List[TaskNode]):
        """Load tasks and calculate critical path."""
        self.tasks = self._flatten_nodes(root_nodes)
        self.node_map = {task.id: task for task in self.tasks}

        # Calculate Y positions
        self.task_y_positions = {}
        y_pos = self.top_margin
        for task in self.tasks:
            self.task_y_positions[task.id] = y_pos
            y_pos += self.row_height

        # Calculate timeline bounds
        self._calculate_timeline_bounds()

        # Perform critical path analysis
        self.analyzer = CriticalPathAnalyzer(root_nodes)
        results = self.analyzer.analyze()
        self.critical_path_ids = results['critical_path_ids']  # Critical LEAF tasks
        self.critical_parent_ids = results['critical_parent_ids']  # Parents with critical descendants
        self.slack_data = results['slack']

        # Update widget size
        self._update_size()
        self.update()

    def _flatten_nodes(self, nodes: List[TaskNode]) -> List[TaskNode]:
        """Flatten hierarchical nodes to a list."""
        result = []
        for node in nodes:
            result.append(node)
            if node.children:
                result.extend(self._flatten_nodes(node.children))
        return result

    def _calculate_timeline_bounds(self):
        """Calculate the start and end dates for the timeline."""
        if not self.tasks:
            self.start_date = datetime.now()
            self.end_date = datetime.now() + timedelta(days=30)
            return

        start_dates = []
        end_dates = []

        for task in self.tasks:
            if task.start_date:
                try:
                    start_dates.append(datetime.strptime(task.start_date, DATE_FMT))
                except ValueError:
                    pass
            if task.end_date:
                try:
                    end_dates.append(datetime.strptime(task.end_date, DATE_FMT))
                except ValueError:
                    pass

        if start_dates and end_dates:
            # Add padding (1 week before/after)
            self.start_date = min(start_dates) - timedelta(days=7)
            self.end_date = max(end_dates) + timedelta(days=7)
        else:
            self.start_date = datetime.now()
            self.end_date = datetime.now() + timedelta(days=30)

    def _update_size(self):
        """Update widget size based on content."""
        if not self.start_date or not self.end_date:
            return

        timeline_width = (self.end_date - self.start_date).days * self.pixels_per_day
        timeline_height = len(self.tasks) * self.row_height + self.top_margin + 50

        self.setMinimumWidth(timeline_width + self.left_margin + 100)
        self.setMinimumHeight(timeline_height)

    def _date_to_x(self, date_str: str) -> int:
        """Convert date string to X coordinate."""
        if not self.start_date:
            return 0

        try:
            date = datetime.strptime(date_str, DATE_FMT)
            days_from_start = (date - self.start_date).days
            return self.left_margin + (days_from_start * self.pixels_per_day)
        except (ValueError, AttributeError):
            return 0

    def _x_to_date(self, x: int) -> datetime:
        """Convert X coordinate to date."""
        if not self.start_date:
            return datetime.now()

        days_from_start = (x - self.left_margin) / self.pixels_per_day
        return self.start_date + timedelta(days=int(days_from_start))

    def set_zoom(self, zoom_level: int):
        """Set zoom level (pixels per day)."""
        self.pixels_per_day = max(5, min(50, zoom_level))
        self._update_size()
        self.update()

    def paintEvent(self, event):
        """Main paint event - draws the entire Gantt chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw timeline header
        self._draw_timeline_header(painter)

        # Draw grid lines
        self._draw_grid(painter)

        # Draw today marker
        self._draw_today_marker(painter)

        # Draw task bars with slack
        if self.show_slack:
            self._draw_slack_bars(painter)

        self._draw_task_bars(painter)

        # Draw dependencies
        if self.show_dependencies:
            self._draw_dependencies(painter)

        # Draw milestones
        self._draw_milestones(painter)

    def _draw_timeline_header(self, painter: QPainter):
        """Draw the timeline header with date labels."""
        if not self.start_date or not self.end_date:
            return

        painter.fillRect(0, 0, self.width(), self.header_height, QColor(40, 40, 40))

        # Draw month/year labels
        font = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor(220, 220, 220)))

        current_date = self.start_date
        while current_date <= self.end_date:
            x = self._date_to_x(current_date.strftime(DATE_FMT))

            # Draw month label at start of month
            if current_date.day == 1 or current_date == self.start_date:
                month_label = current_date.strftime("%b %Y")
                painter.drawText(QRect(x, 5, 100, 20), Qt.AlignmentFlag.AlignLeft, month_label)

            # Draw day labels
            day_label = str(current_date.day)
            painter.setFont(QFont("Arial", 7))
            painter.setPen(QPen(QColor(180, 180, 180)))
            painter.drawText(QRect(x, 30, self.pixels_per_day, 20),
                           Qt.AlignmentFlag.AlignCenter, day_label)

            # Draw week separators
            if current_date.weekday() == 0:  # Monday
                painter.setPen(QPen(QColor(100, 100, 100), 1, Qt.PenStyle.DashLine))
                painter.drawLine(x, self.header_height, x, self.height())

            current_date += timedelta(days=1)

        # Draw header bottom border
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.drawLine(0, self.header_height, self.width(), self.header_height)

    def _draw_grid(self, painter: QPainter):
        """Draw background grid."""
        if not self.start_date or not self.end_date:
            return

        painter.setPen(QPen(self.color_grid, 1))

        # Horizontal lines (per task)
        for i, task in enumerate(self.tasks):
            y = self.top_margin + (i * self.row_height)
            painter.drawLine(0, y, self.width(), y)

        # Vertical lines (per day)
        current_date = self.start_date
        while current_date <= self.end_date:
            x = self._date_to_x(current_date.strftime(DATE_FMT))

            # Weekend shading
            if current_date.weekday() in [5, 6]:  # Saturday, Sunday
                rect = QRect(x, self.header_height, self.pixels_per_day, self.height())
                painter.fillRect(rect, QColor(50, 50, 50, 30))

            current_date += timedelta(days=1)

    def _draw_today_marker(self, painter: QPainter):
        """Draw a vertical line for today's date."""
        today = datetime.now()
        if self.start_date and self.end_date:
            if self.start_date <= today <= self.end_date:
                x = self._date_to_x(today.strftime(DATE_FMT))
                painter.setPen(QPen(self.color_today, 2))
                painter.drawLine(x, self.header_height, x, self.height())

                # Label
                painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                painter.drawText(x + 5, self.header_height + 15, "TODAY")

    def _draw_task_bars(self, painter: QPainter):
        """Draw task bars with color coding."""
        for task in self.tasks:
            if not task.start_date or not task.end_date:
                continue

            x_start = self._date_to_x(task.start_date)
            x_end = self._date_to_x(task.end_date)
            y = self.task_y_positions.get(task.id, 0)

            # Determine bar properties
            is_critical_leaf = task.id in self.critical_path_ids  # Critical LEAF task
            is_critical_parent = task.id in self.critical_parent_ids  # Parent with critical descendants
            is_completed = task.status == "Completed"
            bar_rect = QRect(x_start, y + 5, x_end - x_start, self.row_height - 10)

            # --- NEW Coloring Logic for Option 1 ---
            # Critical LEAF tasks → RED fill + RED outline (completely red)
            # Critical PARENT tasks → Status fill (blue/green) + RED outline
            # Non-critical tasks → Status fill, no red outline

            # Step 1: Determine fill color
            if is_critical_leaf and self.show_critical_path:
                # Critical LEAF → RED fill
                bar_color = self.color_critical
            elif is_completed:
                # Completed → Green fill
                bar_color = self.color_completed
            else:
                # In-progress/Not started → Blue fill
                bar_color = self.color_normal

            # Step 2: Draw bar with fill color
            gradient = QLinearGradient(QPointF(bar_rect.topLeft()), QPointF(bar_rect.bottomLeft()))
            gradient.setColorAt(0, bar_color.lighter(120))
            gradient.setColorAt(1, bar_color.darker(110))
            painter.setBrush(QBrush(gradient))
            painter.setPen(QPen(bar_color.darker(150), 1))
            painter.drawRoundedRect(bar_rect, 3, 3)

            # Step 3: Add RED OUTLINE for ALL critical tasks (leaf and parent)
            if (is_critical_leaf or is_critical_parent) and self.show_critical_path:
                painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill, just outline
                painter.setPen(QPen(self.color_critical, 3))  # Thick red outline
                painter.drawRoundedRect(bar_rect, 3, 3)

            # Draw task name on bar
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Arial", 8))

            # Truncate text if too long
            text = task.name
            if bar_rect.width() < 100:
                text = text[:10] + "..." if len(text) > 10 else text

            painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, text)

            # Draw highlight overlay if this task is highlighted
            if self.highlighted_task and task.id == self.highlighted_task.id:
                painter.setPen(QPen(self.color_highlight, 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(bar_rect.adjusted(-2, -2, 2, 2), 3, 3)

    def _draw_slack_bars(self, painter: QPainter):
        """Draw slack (float) visualization as dotted extensions."""
        if not self.analyzer:
            return

        for task in self.tasks:
            if task.id not in self.slack_data:
                continue

            slack_days = self.slack_data[task.id]
            if slack_days <= 0 or not task.end_date:
                continue

            # Calculate slack bar position
            x_end = self._date_to_x(task.end_date)
            slack_width = slack_days * self.pixels_per_day
            y = self.task_y_positions.get(task.id, 0)

            # Draw slack as dotted line
            slack_rect = QRect(x_end, y + self.row_height // 2 - 2, slack_width, 4)
            painter.fillRect(slack_rect, self.color_slack)

            # Draw slack label
            if slack_width > 30:
                painter.setPen(QPen(QColor(150, 150, 150)))
                painter.setFont(QFont("Arial", 7))
                painter.drawText(x_end + 5, y + self.row_height // 2 + 10,
                               f"+{slack_days}d slack")

    def _draw_dependencies(self, painter: QPainter):
        """Draw dependency arrows between tasks."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for task in self.tasks:
            # Find predecessor
            predecessor = None
            if task.predecessor_id and task.predecessor_id in self.node_map:
                predecessor = self.node_map[task.predecessor_id]
            elif task.parent and not task.is_parallel:
                # Implicit predecessor (previous sibling)
                siblings = task.parent.children
                try:
                    idx = siblings.index(task)
                    if idx > 0:
                        predecessor = siblings[idx - 1]
                except ValueError:
                    pass

            if not predecessor or not predecessor.end_date or not task.start_date:
                continue

            # Calculate arrow coordinates
            pred_x_end = self._date_to_x(predecessor.end_date)
            pred_y = self.task_y_positions.get(predecessor.id, 0) + self.row_height // 2

            task_x_start = self._date_to_x(task.start_date)
            task_y = self.task_y_positions.get(task.id, 0) + self.row_height // 2

            # Draw arrow path (Finish-to-Start)
            path = QPainterPath()
            path.moveTo(pred_x_end, pred_y)

            # Calculate control points for curved arrow
            mid_x = (pred_x_end + task_x_start) / 2

            if abs(task_y - pred_y) < 5:
                # Horizontal arrow
                path.lineTo(task_x_start - 10, task_y)
            else:
                # Curved arrow
                path.lineTo(mid_x, pred_y)
                path.lineTo(mid_x, task_y)
                path.lineTo(task_x_start - 10, task_y)

            # Draw path
            pen_color = QColor(255, 100, 100) if task.id in self.critical_path_ids else self.color_dependency
            painter.setPen(QPen(pen_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

            # Draw arrowhead
            self._draw_arrowhead(painter, task_x_start - 10, task_y, pen_color)

    def _draw_arrowhead(self, painter: QPainter, x: int, y: int, color: QColor):
        """Draw an arrowhead pointing right."""
        arrow_size = 8
        points = QPolygonF([
            QPointF(x, y),
            QPointF(x - arrow_size, y - arrow_size // 2),
            QPointF(x - arrow_size, y + arrow_size // 2)
        ])

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(points)

    def _draw_milestones(self, painter: QPainter):
        """Draw diamond markers for milestone tasks (zero duration)."""
        for task in self.tasks:
            if not task.start_date or not task.end_date:
                continue

            # Check if milestone (zero or 1-day duration)
            try:
                start = datetime.strptime(task.start_date, DATE_FMT)
                end = datetime.strptime(task.end_date, DATE_FMT)
                duration_days = (end - start).days

                if duration_days <= 1 and "milestone" in task.name.lower():
                    x = self._date_to_x(task.start_date)
                    y = self.task_y_positions.get(task.id, 0) + self.row_height // 2

                    # Draw diamond
                    diamond_size = 12
                    points = QPolygonF([
                        QPointF(x, y - diamond_size),
                        QPointF(x + diamond_size, y),
                        QPointF(x, y + diamond_size),
                        QPointF(x - diamond_size, y)
                    ])

                    painter.setBrush(QBrush(self.color_milestone))
                    painter.setPen(QPen(self.color_milestone.darker(150), 2))
                    painter.drawPolygon(points)

            except ValueError:
                pass

    def highlight_task(self, task: TaskNode):
        """Highlight a specific task."""
        self.highlighted_task = task
        self.update()

    def set_root_nodes(self, root_nodes: List[TaskNode]):
        """Set the root nodes for hiding functionality."""
        self.root_nodes = root_nodes

    def _show_context_menu(self, pos: QPoint):
        """Show context menu on right-click."""
        # Find task at position
        task = self._get_task_at_position(pos)

        if not task:
            return

        menu = QMenu(self)

        # Check if task is critical
        is_critical = task.id in self.critical_path_ids

        # Add "Hide Critical Task" option (only for critical tasks)
        if is_critical:
            hide_action = QAction("Hide Critical Task", self)
            hide_action.triggered.connect(lambda: self._hide_critical_task(task))
            menu.addAction(hide_action)

        # Always add "Show All Hidden Tasks" option
        if self.hidden_task_ids:
            menu.addSeparator()
            show_all_action = QAction(f"Show All Hidden Tasks ({len(self.hidden_task_ids)})", self)
            show_all_action.triggered.connect(self._show_all_hidden_tasks)
            menu.addAction(show_all_action)

        # Show menu at cursor position
        menu.exec(self.mapToGlobal(pos))

    def _hide_critical_task(self, task: TaskNode):
        """Hide a critical task and reload to show next critical path."""
        self.hidden_task_ids.add(task.id)
        self.reload_required.emit()

    def _show_all_hidden_tasks(self):
        """Show all hidden tasks."""
        self.hidden_task_ids.clear()
        self.reload_required.emit()

    def get_filtered_root_nodes(self) -> List[TaskNode]:
        """Get root nodes with hidden tasks filtered out."""
        if not self.hidden_task_ids:
            return self.root_nodes

        # Rebuild tree without hidden nodes
        def clone_node_tree(node: TaskNode, parent: Optional[TaskNode] = None) -> Optional[TaskNode]:
            # Skip hidden nodes
            if node.id in self.hidden_task_ids:
                return None

            # Clone this node
            cloned = TaskNode(node.name, parent=parent)
            # Copy all attributes
            cloned.id = node.id
            cloned.status = node.status
            cloned.owner = node.owner
            cloned.start_date = node.start_date
            cloned.end_date = node.end_date

            cloned.is_parallel = node.is_parallel
            cloned.predecessor_id = node.predecessor_id
            cloned.notes = node.notes

            # Recursively clone children (excluding hidden ones)
            for child in node.children:
                cloned_child = clone_node_tree(child, cloned)
                if cloned_child:
                    cloned.add_child(cloned_child)

            return cloned

        # Rebuild roots
        new_roots = []
        for root in self.root_nodes:
            cloned_root = clone_node_tree(root)
            if cloned_root:
                new_roots.append(cloned_root)

        return new_roots

    def mouseMoveEvent(self, event):
        """Handle mouse move for tooltips."""
        pos = event.pos()
        task_at_pos = self._get_task_at_position(pos)

        if task_at_pos != self.hovered_task:
            self.hovered_task = task_at_pos
            if task_at_pos:
                self._show_tooltip(task_at_pos, event.globalPosition().toPoint())
            else:
                self.setToolTip("")

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to jump to Tracker tab."""
        pos = event.pos()
        task_at_pos = self._get_task_at_position(pos)

        if task_at_pos:
            self.task_double_clicked.emit(task_at_pos)

    def _get_task_at_position(self, pos: QPoint) -> Optional[TaskNode]:
        """Find task at mouse position."""
        x = pos.x()
        y = pos.y()

        for task in self.tasks:
            if not task.start_date or not task.end_date:
                continue

            x_start = self._date_to_x(task.start_date)
            x_end = self._date_to_x(task.end_date)
            task_y = self.task_y_positions.get(task.id, 0)

            # Check if mouse is within task bar bounds
            if (x_start <= x <= x_end and
                task_y + 5 <= y <= task_y + self.row_height - 5):
                return task

        return None

    def _show_tooltip(self, task: TaskNode, global_pos: QPoint):
        """Show rich tooltip for a task."""
        # Calculate critical path info
        is_critical = task.id in self.critical_path_ids
        slack_days = self.slack_data.get(task.id, 0)

        # Get early/late dates if available
        early_start = ""
        late_start = ""
        if self.analyzer:
            results = self.analyzer.analyze()
            if task.id in results['early_start']:
                early_start = results['early_start'][task.id].strftime('%Y-%m-%d')
            if task.id in results['late_start']:
                late_start = results['late_start'][task.id].strftime('%Y-%m-%d')

        # Find predecessor
        predecessor_name = "None"
        if task.predecessor_id and task.predecessor_id in self.node_map:
            predecessor_name = self.node_map[task.predecessor_id].name
        elif task.parent and not task.is_parallel:
            siblings = task.parent.children
            try:
                idx = siblings.index(task)
                if idx > 0:
                    predecessor_name = siblings[idx - 1].name
            except ValueError:
                pass

        # Find successors
        successors = []
        for other_task in self.tasks:
            if other_task.predecessor_id == task.id:
                successors.append(other_task.name)
            elif other_task.parent and not other_task.is_parallel:
                siblings = other_task.parent.children
                try:
                    idx = siblings.index(other_task)
                    if idx > 0 and siblings[idx - 1].id == task.id:
                        successors.append(other_task.name)
                except ValueError:
                    pass

        successors_text = ", ".join(successors[:3]) if successors else "None"
        if len(successors) > 3:
            successors_text += f" (+{len(successors) - 3} more)"

        # Build tooltip HTML
        tooltip = f"""<html>
<style>
    body {{ font-family: Arial; font-size: 10pt; }}
    .header {{ font-size: 11pt; font-weight: bold; color: #FF5050; }}
    .section {{ font-weight: bold; margin-top: 8px; }}
    .critical {{ color: #FF5050; font-weight: bold; }}
    .normal {{ color: #6496FF; }}
</style>
<body>
<div class="header">📋 {task.name}</div>
<hr>
<div><b>Status:</b> {task.status}</div>
<div><b>Owner:</b> {task.owner or 'Unassigned'}</div>

<div class="section">📅 Schedule:</div>
<div>Start: {task.start_date or 'N/A'}</div>
<div>End: {task.end_date or 'N/A'}</div>
<div>Duration: {task.duration} days</div>

<div class="section">⏱️ Critical Path:</div>
<div>Is Critical: <span class="{'critical' if is_critical else 'normal'}">{'YES ⚠️' if is_critical else 'NO'}</span></div>
<div>Slack: {slack_days} days</div>"""

        if early_start:
            tooltip += f"<div>Early Start: {early_start}</div>"
        if late_start:
            tooltip += f"<div>Late Start: {late_start}</div>"

        tooltip += f"""
<div class="section">🔗 Dependencies:</div>
<div>Predecessor: {predecessor_name}</div>
<div>Successors: {successors_text}</div>"""

        if task.notes:
            notes_preview = task.notes[:100] + "..." if len(task.notes) > 100 else task.notes
            tooltip += f"""
<div class="section">📝 Notes:</div>
<div>{notes_preview}</div>"""

        tooltip += """
</body>
</html>"""

        self.setToolTip(tooltip)


class GanttChartWidget(QWidget):
    """
    Main Gantt Chart Widget with critical path analysis.
    Microsoft Project style with right-click hide functionality.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None  # Will be set by main window
        self.root_nodes = []  # Store original root nodes
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Splitter: Top 5 Critical Paths Panel on left, Timeline on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Top 5 Critical Paths
        self.critical_paths_panel = TopCriticalPathsPanel()
        self.critical_paths_panel.task_clicked.connect(self._on_critical_task_clicked)
        splitter.addWidget(self.critical_paths_panel)

        # Right panel: Timeline in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.timeline = GanttTimeline()
        self.timeline.task_double_clicked.connect(self._on_task_double_clicked)
        self.timeline.reload_required.connect(self._reload_with_filtered_tasks)
        scroll_area.setWidget(self.timeline)
        splitter.addWidget(scroll_area)

        # Set splitter proportions (25% left panel, 75% timeline)
        splitter.setSizes([300, 900])

        layout.addWidget(splitter)

    def _create_toolbar(self) -> QToolBar:
        """Create toolbar with controls."""
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setStyleSheet("QToolBar { background: #2b2b2b; border-bottom: 1px solid #555; }")

        # Zoom controls
        toolbar.addWidget(QLabel(" Zoom: "))

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setMaximumWidth(30)
        zoom_out_btn.clicked.connect(lambda: self._zoom(-5))
        toolbar.addWidget(zoom_out_btn)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(5)
        self.zoom_slider.setMaximum(50)
        self.zoom_slider.setValue(20)
        self.zoom_slider.setMaximumWidth(150)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_slider)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setMaximumWidth(30)
        zoom_in_btn.clicked.connect(lambda: self._zoom(5))
        toolbar.addWidget(zoom_in_btn)

        toolbar.addSeparator()

        # Toggle buttons
        self.critical_path_btn = QPushButton("Critical Path")
        self.critical_path_btn.setCheckable(True)
        self.critical_path_btn.setChecked(True)
        self.critical_path_btn.toggled.connect(self._toggle_critical_path)
        toolbar.addWidget(self.critical_path_btn)

        self.slack_btn = QPushButton("Show Slack")
        self.slack_btn.setCheckable(True)
        self.slack_btn.setChecked(True)
        self.slack_btn.toggled.connect(self._toggle_slack)
        toolbar.addWidget(self.slack_btn)

        self.dependencies_btn = QPushButton("Dependencies")
        self.dependencies_btn.setCheckable(True)
        self.dependencies_btn.setChecked(True)
        self.dependencies_btn.toggled.connect(self._toggle_dependencies)
        toolbar.addWidget(self.dependencies_btn)

        toolbar.addSeparator()

        # Legend
        legend_label = QLabel(" 🔴 Critical | 🔵 Normal | 🟢 Complete | 🟡 Milestone ")
        legend_label.setStyleSheet("color: #e0e0e0; padding: 5px;")
        toolbar.addWidget(legend_label)

        return toolbar

    def load_nodes(self, root_nodes: List[TaskNode]):
        """Load task nodes and render Gantt chart."""
        if not root_nodes:
            return

        # Store original root nodes
        self.root_nodes = root_nodes

        # Load top 5 critical paths in left panel
        self.critical_paths_panel.load_critical_paths(root_nodes)

        # Set root nodes in timeline for hiding functionality
        self.timeline.set_root_nodes(root_nodes)

        # Load timeline
        self.timeline.load_tasks(root_nodes)

    def _reload_with_filtered_tasks(self):
        """Reload timeline with filtered root nodes (excluding hidden tasks)."""
        # Get filtered root nodes from timeline
        filtered_roots = self.timeline.get_filtered_root_nodes()

        # Reload timeline with filtered tasks
        if filtered_roots:
            self.timeline.load_tasks(filtered_roots)
        else:
            # All tasks hidden - show empty timeline
            self.timeline.tasks = []
            self.timeline.update()

    def _zoom(self, delta: int):
        """Zoom in or out."""
        new_value = self.zoom_slider.value() + delta
        self.zoom_slider.setValue(max(5, min(50, new_value)))

    def _on_zoom_changed(self, value: int):
        """Handle zoom slider change."""
        self.timeline.set_zoom(value)

    def _toggle_critical_path(self, checked: bool):
        """Toggle critical path visualization."""
        self.timeline.show_critical_path = checked
        self.timeline.update()

    def _toggle_slack(self, checked: bool):
        """Toggle slack visualization."""
        self.timeline.show_slack = checked
        self.timeline.update()

    def _toggle_dependencies(self, checked: bool):
        """Toggle dependency arrows."""
        self.timeline.show_dependencies = checked
        self.timeline.update()

    def _on_critical_task_clicked(self, task: TaskNode):
        """Handle click on task in Top 5 Critical Paths panel - highlight in Gantt with orange."""
        self.timeline.highlight_task(task)

    def _on_task_double_clicked(self, task: TaskNode):
        """Handle double-click on task bar - jump to Tracker tab and highlight."""
        if self.main_window:
            # Switch to Tracker tab (index 0)
            self.main_window.tabs.setCurrentIndex(0)

            # Find and highlight the task in tree view
            self._highlight_task_in_tree(task)

    def _highlight_task_in_tree(self, task: TaskNode):
        """Find and highlight task in the tree view."""
        if not self.main_window:
            return

        tree_view = self.main_window.tree_view

        # Search for the task in tree
        iterator = QTreeWidgetItemIterator(tree_view)
        while iterator.value():
            item = iterator.value()
            item_task = item.data(0, Qt.ItemDataRole.UserRole)

            if item_task and hasattr(item_task, 'id') and item_task.id == task.id:
                # Found the task!
                tree_view.setCurrentItem(item)
                tree_view.scrollToItem(item)

                # Highlight with yellow background
                for col in range(tree_view.columnCount()):
                    item.setBackground(col, QColor(255, 255, 0, 100))  # Yellow highlight

                break

            iterator += 1
