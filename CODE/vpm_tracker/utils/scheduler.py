"""
Pure-function scheduler for TaskNode trees.

Extracted from TreeGridView.recalculate_all_dates so both the UI and tests
(which don't boot a QApplication) can share one implementation.

Algorithm (see inline docstring of `schedule`):
  1. Post-order walk: anchor each node to its predecessor (if resolved) or
     its previous sibling, recurse, then rollup.
  2. Forward-pointing predecessor fixup: looped until stable so that
     A->B->C chains propagate in a single call even when B/C appear
     above A in tree order.
"""
from typing import Iterable, List
from models.task_node import TaskNode


def _flatten(roots: Iterable[TaskNode]) -> List[TaskNode]:
    out: List[TaskNode] = []

    def _walk(nodes):
        for n in nodes:
            out.append(n)
            _walk(n.children)
    _walk(roots)
    return out


def _rollup_only(node: TaskNode, visited: set):
    for child in node.children:
        _rollup_only(child, visited)
    node.update_dates_from_children(visited=visited)


def schedule(root_nodes: List[TaskNode]):
    """Re-run the full scheduler against `root_nodes` in place."""
    node_map = {n.id: n for n in _flatten(root_nodes)}
    visited: set = set()
    resolved: set = set()

    def walk(node: TaskNode):
        # Anchor start. Three mutually exclusive modes:
        #   1. predecessor_id set  -> snap to pred.end + 1
        #   2. first child (idx=0) -> snap to parent.start (if is_parallel=OFF)
        #   3. later child (idx>0) -> snap to prev sibling.end + 1 (if is_parallel=OFF)
        # is_parallel=ON means the user owns the start; scheduler leaves it alone.
        if node.predecessor_id and node.predecessor_id in node_map:
            pred = node_map[node.predecessor_id]
            if pred.id in resolved:
                node.update_from_predecessor(pred)
        elif node.parent:
            siblings = node.parent.children
            try:
                idx = siblings.index(node)
                if idx == 0:
                    node.update_first_child_from_parent(node.parent)
                else:
                    node.update_from_previous_sibling(siblings[idx - 1])
            except ValueError:
                pass

        for child in node.children:
            walk(child)

        node.update_dates_from_children(visited=visited)
        node.update_status_from_dates()
        node.update_owner_from_children()
        resolved.add(node.id)

    # Root list: treat roots as siblings of each other. First root is the
    # schedule's manual anchor; later roots chain off the previous root
    # (unless is_parallel=ON, in which case the user owns the date).
    for idx, root in enumerate(root_nodes):
        if idx > 0:
            root.update_from_previous_sibling(root_nodes[idx - 1])
        walk(root)

    # Forward-pointing predecessor fixup. A chain B(pred=A) -> C(pred=B) may
    # have C above B in tree order; one pass anchors C off a stale B.end.
    # Loop until nothing changes (bounded to protect against cycles).
    for _ in range(len(node_map) + 1):
        changed = False
        for n in node_map.values():
            if n.predecessor_id and n.predecessor_id in node_map:
                before = (n.start_date, n.end_date)
                n.update_from_predecessor(node_map[n.predecessor_id])
                if (n.start_date, n.end_date) != before:
                    changed = True
        if not changed:
            break

    # Final rollup sweep so parents reflect the fixup shifts.
    for root in root_nodes:
        _rollup_only(root, visited)
