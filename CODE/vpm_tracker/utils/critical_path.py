"""
Critical Path Analysis Utility

Implements Critical Path Method (CPM) algorithm for project scheduling.
Calculates Early Start, Early Finish, Late Start, Late Finish, and Slack for all tasks.
Identifies the critical path (tasks with zero slack).
"""

from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple
from models.task_node import TaskNode

DATE_FMT = "%Y-%m-%d"


class CriticalPathAnalyzer:
    """
    Analyzes task dependencies and calculates the critical path.

    The critical path is the longest sequence of dependent tasks that determines
    the minimum project duration. Any delay in critical path tasks delays the entire project.
    """

    def __init__(self, root_nodes: List[TaskNode]):
        """
        Initialize analyzer with root task nodes.

        Args:
            root_nodes: List of root-level TaskNode objects
        """
        self.root_nodes = root_nodes
        self.all_nodes = self._flatten_nodes(root_nodes)
        self.node_map = {node.id: node for node in self.all_nodes}

        # ONLY include LEAF tasks (no children) in critical path calculation
        self.leaf_nodes = [node for node in self.all_nodes if not node.children]

        # Results storage
        self.early_start: Dict[str, datetime] = {}
        self.early_finish: Dict[str, datetime] = {}
        self.late_start: Dict[str, datetime] = {}
        self.late_finish: Dict[str, datetime] = {}
        self.slack: Dict[str, int] = {}
        self.critical_path_ids: Set[str] = set()  # Critical LEAF task IDs
        self.critical_parent_ids: Set[str] = set()  # Parent IDs with critical descendants

    def _flatten_nodes(self, nodes: List[TaskNode]) -> List[TaskNode]:
        """Flatten hierarchical task structure into a flat list."""
        result = []
        for node in nodes:
            result.append(node)
            if node.children:
                result.extend(self._flatten_nodes(node.children))
        return result

    def _get_duration_days(self, node: TaskNode) -> int:
        """Calculate duration in days between start and end date."""
        if not node.start_date or not node.end_date:
            return 0

        try:
            start = datetime.strptime(node.start_date, DATE_FMT)
            end = datetime.strptime(node.end_date, DATE_FMT)
            return max(0, (end - start).days)
        except (ValueError, AttributeError):
            return 0

    def _get_predecessors(self, node: TaskNode) -> List[TaskNode]:
        """
        Get all predecessors for a LEAF task (both explicit and implicit).
        If predecessor is a PARENT task, resolves to its longest child.
        """
        predecessors = []

        # 1. Explicit predecessor (manual link)
        if node.predecessor_id and node.predecessor_id in self.node_map:
            pred = self.node_map[node.predecessor_id]

            # If predecessor is a PARENT (has children), use its longest child instead
            if pred.children:
                # Find the child with the latest end date
                longest_child = max(pred.children,
                                  key=lambda c: c.end_date if c.end_date else "0000-00-00")
                predecessors.append(longest_child)
            else:
                predecessors.append(pred)

        # 2. Implicit predecessor (previous sibling in sequential mode)
        elif node.parent and not node.is_parallel:
            siblings = node.parent.children
            try:
                idx = siblings.index(node)
                if idx > 0:
                    prev_sibling = siblings[idx - 1]
                    # If previous sibling is a parent, use its longest child
                    if prev_sibling.children:
                        longest_child = max(prev_sibling.children,
                                          key=lambda c: c.end_date if c.end_date else "0000-00-00")
                        predecessors.append(longest_child)
                    else:
                        predecessors.append(prev_sibling)
            except ValueError:
                pass

        return predecessors

    def _get_successors(self, node: TaskNode) -> List[TaskNode]:
        """Get all successors for a task (tasks that depend on this one)."""
        successors = []

        # Find all tasks that have this node as predecessor
        for other_node in self.all_nodes:
            if other_node.predecessor_id == node.id:
                successors.append(other_node)
            elif other_node.parent and not other_node.is_parallel:
                # Check if this node is the previous sibling
                siblings = other_node.parent.children
                try:
                    idx = siblings.index(other_node)
                    if idx > 0 and siblings[idx - 1].id == node.id:
                        successors.append(other_node)
                except ValueError:
                    pass

        return successors

    def _topological_sort(self) -> List[TaskNode]:
        """
        Sort LEAF tasks in topological order (predecessors before successors).
        Uses Kahn's algorithm for cycle detection.
        Only processes leaf tasks (tasks with no children).
        """
        # Calculate in-degree for each LEAF node
        in_degree = {node.id: 0 for node in self.leaf_nodes}
        for node in self.leaf_nodes:
            for succ in self._get_successors(node):
                if succ.id in in_degree:  # Only count successors that are also leaves
                    in_degree[succ.id] += 1

        # Start with leaf nodes that have no predecessors
        queue = [node for node in self.leaf_nodes if in_degree[node.id] == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for succ in self._get_successors(node):
                if succ.id in in_degree:  # Only process leaf successors
                    in_degree[succ.id] -= 1
                    if in_degree[succ.id] == 0:
                        queue.append(succ)

        # If not all leaf nodes are in result, there's a cycle
        if len(result) != len(self.leaf_nodes):
            print("WARNING: Circular dependency detected in leaf tasks!")
            # Return original list as fallback
            return self.leaf_nodes

        return result

    def forward_pass(self):
        """
        Calculate Early Start (ES) and Early Finish (EF) for all tasks.
        ES = max(EF of all predecessors)
        EF = ES + Duration
        """
        sorted_nodes = self._topological_sort()

        for node in sorted_nodes:
            if not node.start_date:
                continue

            try:
                node_start = datetime.strptime(node.start_date, DATE_FMT)
            except ValueError:
                continue

            predecessors = self._get_predecessors(node)

            if predecessors:
                # ES = max(predecessor EF)
                max_pred_ef = None
                for pred in predecessors:
                    if pred.id in self.early_finish:
                        if max_pred_ef is None or self.early_finish[pred.id] > max_pred_ef:
                            max_pred_ef = self.early_finish[pred.id]

                if max_pred_ef:
                    # Add 1 day (next workday logic)
                    self.early_start[node.id] = max_pred_ef + timedelta(days=1)
                else:
                    self.early_start[node.id] = node_start
            else:
                # No predecessors, use actual start date
                self.early_start[node.id] = node_start

            # Calculate Early Finish
            duration = self._get_duration_days(node)
            self.early_finish[node.id] = self.early_start[node.id] + timedelta(days=duration)

    def backward_pass(self):
        """
        Calculate Late Start (LS) and Late Finish (LF) for all tasks.
        LF = min(LS of all successors)
        LS = LF - Duration
        """
        sorted_nodes = list(reversed(self._topological_sort()))

        # Find project end date (max EF)
        if not self.early_finish:
            return

        project_end = max(self.early_finish.values())

        for node in sorted_nodes:
            if node.id not in self.early_finish:
                continue

            successors = self._get_successors(node)

            if successors:
                # LF = min(successor LS) - 1 day
                min_succ_ls = None
                for succ in successors:
                    if succ.id in self.late_start:
                        if min_succ_ls is None or self.late_start[succ.id] < min_succ_ls:
                            min_succ_ls = self.late_start[succ.id]

                if min_succ_ls:
                    self.late_finish[node.id] = min_succ_ls - timedelta(days=1)
                else:
                    self.late_finish[node.id] = project_end
            else:
                # No successors, this is an end task
                self.late_finish[node.id] = project_end

            # Calculate Late Start
            duration = self._get_duration_days(node)
            self.late_start[node.id] = self.late_finish[node.id] - timedelta(days=duration)

    def calculate_slack(self):
        """
        Calculate slack (float) for LEAF tasks only.
        Slack = LS - ES (or LF - EF, same result)
        Slack represents how much a task can be delayed without delaying the project.
        """
        # ONLY calculate slack for LEAF nodes (nodes with ES/LS calculated)
        for node in self.leaf_nodes:
            if node.id in self.early_start and node.id in self.late_start:
                slack_days = (self.late_start[node.id] - self.early_start[node.id]).days
                self.slack[node.id] = slack_days
            # Don't set slack for nodes without ES/LS - they're not in the calculation

    def identify_critical_path(self):
        """
        Identify LEAF tasks on the critical path.
        Critical tasks have zero slack.
        """
        self.critical_path_ids = {
            node_id for node_id, slack_val in self.slack.items()
            if slack_val == 0
        }

    def identify_critical_parents(self):
        """
        Identify parent tasks that have critical descendants.
        Marks all ancestors of critical leaf tasks.
        """
        self.critical_parent_ids.clear()

        # For each critical leaf task, mark all its ancestors
        for critical_id in self.critical_path_ids:
            if critical_id in self.node_map:
                node = self.node_map[critical_id]
                # Walk up the parent chain
                current = node.parent
                while current:
                    self.critical_parent_ids.add(current.id)
                    current = current.parent

    def analyze(self) -> Dict[str, any]:
        """
        Perform complete critical path analysis on LEAF tasks only.

        Returns:
            Dictionary containing:
            - critical_path_ids: Set of LEAF task IDs on critical path
            - critical_parent_ids: Set of parent task IDs with critical descendants
            - slack: Dict mapping task ID to slack days
            - early_start/early_finish: Dict mapping task ID to dates
            - late_start/late_finish: Dict mapping task ID to dates
            - project_duration: Total project duration in days
        """
        self.forward_pass()
        self.backward_pass()
        self.calculate_slack()
        self.identify_critical_path()
        self.identify_critical_parents()  # Mark parents with critical children

        # Calculate project duration
        project_duration = 0
        if self.early_finish:
            project_start = min(self.early_start.values()) if self.early_start else datetime.now()
            project_end = max(self.early_finish.values())
            project_duration = (project_end - project_start).days

        return {
            'critical_path_ids': self.critical_path_ids,  # Critical LEAF tasks
            'critical_parent_ids': self.critical_parent_ids,  # Parents with critical descendants
            'slack': self.slack,
            'early_start': self.early_start,
            'early_finish': self.early_finish,
            'late_start': self.late_start,
            'late_finish': self.late_finish,
            'project_duration': project_duration,
            'project_start': min(self.early_start.values()) if self.early_start else None,
            'project_end': max(self.early_finish.values()) if self.early_finish else None
        }

    def is_critical(self, node: TaskNode) -> bool:
        """Check if a task is on the critical path."""
        return node.id in self.critical_path_ids

    def get_slack_days(self, node: TaskNode) -> int:
        """Get slack (float) in days for a task."""
        return self.slack.get(node.id, 0)

    def get_critical_path_tasks(self) -> List[TaskNode]:
        """Get list of tasks on the critical path."""
        return [node for node in self.all_nodes if node.id in self.critical_path_ids]
