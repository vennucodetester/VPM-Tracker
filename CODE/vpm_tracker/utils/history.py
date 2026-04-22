"""
HistoryStack — snapshot-based undo/redo for a single project.

We avoid the QUndoCommand-per-mutation pattern (which would require surgery
at every call site) by serializing the whole project state before each
user action. A snapshot is cheap: the existing TaskNode.to_dict machinery
is already fast enough, and deep copies beat per-action diffing for
correctness.

Typical flow:
    stack.push(project.get_snapshot())   # BEFORE a user mutation
    ... mutation happens ...
    stack.undo(current_snapshot)         # returns the previous snapshot
    stack.redo(current_snapshot)         # returns the next snapshot

Caller is responsible for rebuilding the UI from the returned snapshot.
"""
import copy
from typing import Any, Optional


DEFAULT_MAX_DEPTH = 50


class HistoryStack:
    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH):
        self._undo: list = []
        self._redo: list = []
        self._max = int(max_depth)

    def push(self, snapshot: Any) -> None:
        """Record a state as the 'previous' for the next undo.
        Clears the redo stack because a new branch of history has started."""
        if snapshot is None:
            return
        self._undo.append(copy.deepcopy(snapshot))
        if len(self._undo) > self._max:
            # Drop oldest to stay within budget
            self._undo = self._undo[-self._max:]
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, current_snapshot: Any) -> Optional[Any]:
        """Pop the last recorded state and return it. The caller's current
        state goes onto the redo stack."""
        if not self._undo:
            return None
        prev = self._undo.pop()
        self._redo.append(copy.deepcopy(current_snapshot))
        if len(self._redo) > self._max:
            self._redo = self._redo[-self._max:]
        return prev

    def redo(self, current_snapshot: Any) -> Optional[Any]:
        if not self._redo:
            return None
        nxt = self._redo.pop()
        self._undo.append(copy.deepcopy(current_snapshot))
        if len(self._undo) > self._max:
            self._undo = self._undo[-self._max:]
        return nxt

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
