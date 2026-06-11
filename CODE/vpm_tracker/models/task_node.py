
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from utils.workday_calculator import WorkdayCalculator

DATE_FMT = "%Y-%m-%d"


def _clamp_end(start: Optional[str], end: Optional[str]) -> Optional[str]:
    """Guarantee end >= start. Returns a valid end string or the original if inputs are bad."""
    if not start or not end:
        return end
    try:
        s = datetime.strptime(start, DATE_FMT)
        e = datetime.strptime(end, DATE_FMT)
    except ValueError:
        return end
    if e < s:
        return start
    return end


class TaskNode:
    def __init__(self, name: str = "New Task", parent: Optional['TaskNode'] = None):
        self.id: str = str(uuid.uuid4())
        self.name: str = name
        self.start_date: Optional[str] = datetime.now().strftime("%Y-%m-%d")
        self.end_date: Optional[str] = datetime.now().strftime("%Y-%m-%d")
        self.status: str = "Not Started"
        self.owner: str = ""
        self.notes: str = ""
        self.is_parallel: bool = False

        # Hierarchy
        self.parent: Optional[TaskNode] = parent
        self.children: List[TaskNode] = []

        # Meta
        self.expanded: bool = True
        self.dates_locked: bool = False
        self.predecessor_id: Optional[str] = None  # Manual cross-tree link
        self.baseline_duration: Optional[int] = None  # Set by "Set Baseline" (Rev A)
        self.baseline_end: Optional[str] = None       # End date at baseline time
        self.delay_notes: str = ""  # Legacy free-text log (pre-revision files)
        # Revision trail: Rev A = baseline; each slip confirmed by the user
        # appends {"rev","date","end","slip","reason"}. See DelayDelegate.
        self.revisions: list = []

    def add_child(self, child: 'TaskNode'):
        child.parent = self
        self.children.append(child)

        if len(self.children) == 1 and self.start_date:
            duration = 1
            if child.start_date and child.end_date:
                duration = WorkdayCalculator.calculate_duration(child.start_date, child.end_date)
            child.start_date = self.start_date
            child.end_date = WorkdayCalculator.add_workdays(child.start_date, duration)

        if len(self.children) > 1:
            child.update_from_previous_sibling(self.children[-2])

        self.update_dates_from_children()
        self.update_owner_from_children()

    def remove_child(self, child: 'TaskNode'):
        if child in self.children:
            idx = self.children.index(child)
            self.children.remove(child)
            child.parent = None

            if 0 < idx < len(self.children):
                prev = self.children[idx - 1]
                next_sib = self.children[idx]
                next_sib.update_from_previous_sibling(prev)
                # (further ripple is the scheduler's job — callers recalc)

            if not self.children:
                self.is_parallel = False
                if self.parent:
                    siblings = self.parent.children
                    if self in siblings:
                        my_idx = siblings.index(self)
                        if my_idx > 0:
                            self.update_from_previous_sibling(siblings[my_idx - 1])

            self.update_dates_from_children()

    # ------------------------------------------------------------------
    # Core setter — single point of truth for date mutation
    # ------------------------------------------------------------------

    def set_date(self, date_type: str, date_str: str,
                 force: bool = False,
                 is_rollup: bool = False,
                 visited: Optional[set] = None):
        """
        Set a date and (optionally) cascade to siblings + rollup to parent.

        force=True   - bypass dates_locked (manual UI override only)
        is_rollup=True - called from update_dates_from_children; skip cascade to avoid loops
        visited      - set of node ids already touched in this cascade (recursion guard)
        """
        # F1: honor dates_locked — but only for the start date.
        # The end date is always auto-rolled-up from children (max of children's
        # end dates), so we must let end-date writes through even when locked.
        if self.dates_locked and not force and date_type == 'start':
            return

        changed = False
        if date_type == 'start':
            if self.start_date != date_str:
                self.start_date = date_str
                changed = True
        elif date_type == 'end':
            if self.end_date != date_str:
                self.end_date = date_str
                changed = True

        # F5: enforce end >= start invariant — ALWAYS, even if the caller's
        # update was a no-op. Guards against any upstream code that mutates
        # start_date/end_date directly.
        fixed_end = _clamp_end(self.start_date, self.end_date)
        if fixed_end != self.end_date:
            self.end_date = fixed_end
            changed = True

        if not changed:
            return

        self.update_status_from_dates()

        if is_rollup:
            # Rollup only touches its own parent chain; do NOT cascade to siblings/children
            if self.parent:
                self.parent.update_dates_from_children(visited=visited)
            return

        if visited is None:
            visited = set()
        if self.id in visited:
            return
        visited.add(self.id)

        if self.parent:
            self.parent.update_dates_from_children(visited=visited)

        # NOTE: no sibling cascade here. Propagating a date change to other
        # tasks is the scheduler's job (utils/scheduler.py) — every UI call
        # site follows a mutation with recalculate_all_dates(). Having a
        # second propagation path in the model was the source of the
        # "toggle it twice" / stale-date bugs.

    # ------------------------------------------------------------------
    # Sibling / predecessor propagation
    # ------------------------------------------------------------------

    def update_from_previous_sibling(self, prev_sibling: 'TaskNode'):
        """Start = Prev.End + 1 workday, shift End to preserve duration."""
        if self.predecessor_id:
            # Manual link wins over implicit sibling chain
            return
        if self.dates_locked:
            return
        if not prev_sibling.end_date:
            return

        # is_parallel ON = snap to parent.start_date (parallel with parent);
        # OFF = auto-chain to prev sibling's end + 1 workday.
        if self.is_parallel and self.parent and self.parent.start_date:
            new_start = self.parent.start_date
        else:
            new_start = WorkdayCalculator.get_next_workday(prev_sibling.end_date)

        if new_start != self.start_date:
            duration = 1
            if self.start_date and self.end_date:
                duration = WorkdayCalculator.calculate_duration(self.start_date, self.end_date)
            self.start_date = new_start
            self.end_date = WorkdayCalculator.add_workdays(new_start, duration)
            self.end_date = _clamp_end(self.start_date, self.end_date)

    def update_first_child_from_parent(self, parent: 'TaskNode'):
        """First child with is_parallel=OFF anchors to parent.start_date.
        Duration is preserved; end shifts to match."""
        if self.predecessor_id or self.dates_locked:
            return
        if not parent.start_date:
            return
        new_start = parent.start_date
        if new_start != self.start_date:
            duration = 1
            if self.start_date and self.end_date:
                duration = WorkdayCalculator.calculate_duration(self.start_date, self.end_date)
            self.start_date = new_start
            self.end_date = WorkdayCalculator.add_workdays(new_start, duration)
            self.end_date = _clamp_end(self.start_date, self.end_date)

    def update_from_predecessor(self, predecessor: 'TaskNode'):
        """Start = Predecessor.End + 1 workday (manual cross-tree link)."""
        if self.dates_locked:
            return
        if not predecessor.end_date:
            return

        new_start = WorkdayCalculator.get_next_workday(predecessor.end_date)
        if new_start != self.start_date:
            duration = 1
            if self.start_date and self.end_date:
                duration = WorkdayCalculator.calculate_duration(self.start_date, self.end_date)
            self.start_date = new_start
            self.end_date = WorkdayCalculator.add_workdays(new_start, duration)
            self.end_date = _clamp_end(self.start_date, self.end_date)
            self.update_status_from_dates()

    # cascade_updates() was removed: it was a second, competing date-
    # propagation engine alongside utils/scheduler.py. The scheduler is
    # now the only code that ripples date changes between tasks.

    # ------------------------------------------------------------------
    # Shift children by explicit delta (F2 — no stale min-start math)
    # ------------------------------------------------------------------

    def shift_children(self, delta_days: int):
        """Shift every descendant by delta_days (calendar days)."""
        if not self.children or delta_days == 0:
            return
        for child in self.children:
            if child.dates_locked:
                continue
            if child.start_date:
                child.start_date = self._add_days(child.start_date, delta_days)
            if child.end_date:
                child.end_date = self._add_days(child.end_date, delta_days)
                child.end_date = _clamp_end(child.start_date, child.end_date)
            if child.children:
                child.shift_children(delta_days)

    @staticmethod
    def _add_days(date_str: str, delta_days: int) -> str:
        try:
            dt = datetime.strptime(date_str, DATE_FMT)
        except ValueError:
            return date_str
        return (dt + timedelta(days=delta_days)).strftime(DATE_FMT)

    @staticmethod
    def _days_between(a: Optional[str], b: Optional[str]) -> int:
        if not a or not b:
            return 0
        try:
            da = datetime.strptime(a, DATE_FMT)
            db = datetime.strptime(b, DATE_FMT)
        except ValueError:
            return 0
        return (db - da).days

    # ------------------------------------------------------------------
    # Duration helpers
    # ------------------------------------------------------------------

    @property
    def duration(self) -> str:
        if self.start_date and self.end_date:
            return str(WorkdayCalculator.calculate_duration(self.start_date, self.end_date))
        return "0"

    def set_duration(self, days: int):
        if days < 1:
            days = 1
        if not self.start_date:
            return
        new_end = WorkdayCalculator.add_workdays(self.start_date, days)
        self.set_date('end', new_end)

    # ------------------------------------------------------------------
    # Delay / revision helpers
    # ------------------------------------------------------------------

    def logged_slip(self) -> int:
        """Total slip already recorded across all revisions."""
        return sum(r.get("slip", 0) for r in self.revisions)

    def revision_trail(self) -> str:
        """Human-readable Rev A..N trail (falls back to legacy delay_notes)."""
        lines = []
        if self.baseline_duration is not None:
            base = f"Rev A  (baseline)  {self.baseline_duration}d"
            if self.baseline_end:
                base += f"  end {self.baseline_end}"
            lines.append(base)
        for r in self.revisions:
            slip = r.get("slip", 0)
            sign = f"+{slip}d" if slip > 0 else f"{slip}d"
            line = f"Rev {r.get('rev', '?')}  {r.get('date', '')}  {sign}"
            if r.get("end"):
                line += f"  end {r['end']}"
            if r.get("reason"):
                line += f"  — {r['reason']}"
            lines.append(line)
        if not self.revisions and self.delay_notes:
            # Old files logged free text before revisions existed
            lines.append(self.delay_notes)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Rollup (F4 — pass is_rollup=True so set_date doesn't re-cascade)
    # ------------------------------------------------------------------

    def update_dates_from_children(self, visited: Optional[set] = None):
        if not self.children:
            return
        starts = [c.start_date for c in self.children if c.start_date]
        ends = [c.end_date for c in self.children if c.end_date]
        if not starts or not ends:
            return

        min_start = min(starts)
        max_end = max(ends)

        if self.start_date != min_start:
            self.set_date('start', min_start, is_rollup=True, visited=visited)
        if self.end_date != max_end:
            self.set_date('end', max_end, is_rollup=True, visited=visited)

    def update_owner_from_children(self):
        if not self.children:
            return
        owners = set()
        for child in self.children:
            if child.owner:
                for o in child.owner.split('/'):
                    if o.strip():
                        owners.add(o.strip())
        self.owner = "/".join(sorted(owners)) if owners else ""

    def set_owner(self, new_owner: str):
        if self.owner != new_owner:
            self.owner = new_owner
            if self.parent:
                self.parent.update_owner_from_children()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def update_status_from_dates(self):
        if not self.start_date:
            return
        try:
            start_dt = datetime.strptime(self.start_date, DATE_FMT).date()
            today = datetime.now().date()
            if self.children:
                if all(c.status == "Completed" for c in self.children):
                    self.status = "Completed"
                    return
                if self.status == "Completed":
                    self.status = "In Progress"
            if self.status == "Completed" and not self.children:
                return
            self.status = "Not Started" if start_dt > today else "In Progress"
        except ValueError:
            pass

    def set_status(self, new_status: str):
        if self.status != new_status:
            self.status = new_status
            if self.parent:
                self.parent.update_status_from_dates()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "owner": self.owner,
            "notes": self.notes,
            "is_parallel": self.is_parallel,
            "children": [c.to_dict() for c in self.children],
            "expanded": self.expanded,
            "dates_locked": self.dates_locked,
            "predecessor_id": self.predecessor_id,
            "baseline_duration": self.baseline_duration,
            "baseline_end": self.baseline_end,
            "delay_notes": self.delay_notes,
            "revisions": self.revisions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent: Optional['TaskNode'] = None) -> 'TaskNode':
        node = cls(name=data.get("name", "New Task"), parent=parent)
        node.id = data.get("id", str(uuid.uuid4()))
        node.start_date = data.get("start_date")
        node.end_date = data.get("end_date")
        # Repair any inverted span from a previous buggy save
        node.end_date = _clamp_end(node.start_date, node.end_date)
        node.status = data.get("status", "Not Started")
        node.owner = data.get("owner", "")
        node.notes = data.get("notes", "")
        node.expanded = data.get("expanded", True)
        node.dates_locked = data.get("dates_locked", False)
        node.predecessor_id = data.get("predecessor_id")
        node.baseline_duration = data.get("baseline_duration")
        node.baseline_end = data.get("baseline_end")
        node.delay_notes = data.get("delay_notes", "")
        node.revisions = data.get("revisions", [])

        if "is_parallel" in data:
            node.is_parallel = data["is_parallel"]
        else:
            node.is_parallel = len(data.get("children", [])) > 0

        for child_data in data.get("children", []):
            child_node = cls.from_dict(child_data, parent=node)
            node.children.append(child_node)

        node.update_status_from_dates()
        return node

    # ------------------------------------------------------------------
    # Dependency traversal (used by simulate / CPM / UI)
    # ------------------------------------------------------------------

    def collect_dependencies(self) -> List['TaskNode']:
        deps = []
        if self.parent:
            siblings = self.parent.children
            try:
                idx = siblings.index(self)
                for i in range(idx + 1, len(siblings)):
                    sib = siblings[i]
                    deps.append(sib)
                    deps.extend(sib.get_all_descendants())
            except ValueError:
                pass
        return deps

    def get_all_descendants(self) -> List['TaskNode']:
        out = []
        for c in self.children:
            out.append(c)
            out.extend(c.get_all_descendants())
        return out

    def simulate_date_change(self, new_start_date: str) -> List[Dict[str, Any]]:
        impacts = []
        if not self.start_date:
            return impacts
        try:
            current_dt = datetime.strptime(self.start_date, DATE_FMT)
            new_dt = datetime.strptime(new_start_date, DATE_FMT)
            delta_days = (new_dt - current_dt).days
            if delta_days == 0:
                return impacts
            for node in self.collect_dependencies():
                if node.start_date:
                    try:
                        s = datetime.strptime(node.start_date, DATE_FMT)
                        impacts.append({
                            'node': node,
                            'old_start': node.start_date,
                            'new_start': (s + timedelta(days=delta_days)).strftime(DATE_FMT),
                            'delta': delta_days,
                        })
                    except ValueError:
                        pass
        except ValueError:
            pass
        return impacts
