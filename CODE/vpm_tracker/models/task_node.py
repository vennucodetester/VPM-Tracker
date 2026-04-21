
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from utils.workday_calculator import WorkdayCalculator

DATE_FMT = "%Y-%m-%d"

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
        self.predecessor_id: Optional[str] = None # Manual Link Override

    def add_child(self, child: 'TaskNode'):
        child.parent = self
        self.children.append(child)
        
        # If this is the first child, inherit Parent's Start Date
        # This prevents the child (defaulting to Today) from rolling up and moving the Parent
        if len(self.children) == 1 and self.start_date:
            # Calculate current duration of child
            duration = 1
            if child.start_date and child.end_date:
                from utils.workday_calculator import WorkdayCalculator
                duration = WorkdayCalculator.calculate_duration(child.start_date, child.end_date)
            
            child.start_date = self.start_date
            
            # Update End Date to keep duration
            from utils.workday_calculator import WorkdayCalculator
            child.end_date = WorkdayCalculator.add_workdays(child.start_date, duration)
        
        # Smart Default: Parent becomes Parallel
        # FIX: Do NOT force parent to be parallel. This breaks the parent's link to its predecessor.
        # if not self.is_parallel:
        #     self.is_parallel = True
        #     # Trigger update to snap to parent start
        #     if self.parent:
        #         siblings = self.parent.children
        #         if self in siblings:
        #             idx = siblings.index(self)
        #             if idx > 0:
        #                 self.update_from_previous_sibling(siblings[idx-1])

        # New child should follow the last child if exists
        if len(self.children) > 1:
            prev_sibling = self.children[-2]
            child.update_from_previous_sibling(prev_sibling)
        
        self.update_dates_from_children()
        self.update_owner_from_children()



    def remove_child(self, child: 'TaskNode'):
        if child in self.children:
            idx = self.children.index(child)
            self.children.remove(child)
            child.parent = None
            
            # Re-link siblings if needed? 
            # If we remove a middle child, the next one should probably link to the previous one.
            if idx < len(self.children) and idx > 0:
                # The child at 'idx' is now the one that was after the removed one
                # It should link to 'idx-1'
                prev = self.children[idx-1]
                next_sib = self.children[idx]
                next_sib.update_from_previous_sibling(prev)
                next_sib.cascade_updates()
            
            # Smart Default: If no children left, become Sequential
            if not self.children:
                self.is_parallel = False
                # Trigger update to snap back to sequential
                if self.parent:
                    siblings = self.parent.children
                    if self in siblings:
                        my_idx = siblings.index(self)
                        if my_idx > 0:
                            self.update_from_previous_sibling(siblings[my_idx-1])
                
            self.update_dates_from_children()

    def set_date(self, date_type: str, date_str: str):
        """
        Set start or end date and trigger rollup and sibling updates.
        """
        changed = False
        if date_type == 'start':
            if self.start_date != date_str:
                self.start_date = date_str
                changed = True
                # If start changes, end might need to shift to keep duration?
                # Requirement: "dates need to be automated... if a task has children, then first children end date should be second childs start date"
                # If I manually change start, I probably want to keep duration constant?
                # Let's assume yes for now, unless end is also set.
                # Actually, let's just set it.
        elif date_type == 'end':
            if self.end_date != date_str:
                self.end_date = date_str
                changed = True
            
        if changed:
            self.update_status_from_dates()
            
            # 1. Update Parent Rollup
            if self.parent:
                self.parent.update_dates_from_children()
            
            # 2. Update Siblings (Next Sibling Start = My End)
            self.cascade_updates()

    def update_from_previous_sibling(self, prev_sibling: 'TaskNode'):
        """
        Set Start Date = Prev Sibling End Date.
        Keep Duration constant (shift End Date).
        """
        # Override: If predecessor_id is set, we ignore sibling logic here?
        # Actually, this method is called by parent.cascade_updates().
        # We should check here if we have a predecessor.
        if self.predecessor_id:
            # We can't resolve predecessor here easily without the full map.
            # But if we are here, it means we are being updated as part of a chain.
            # If we have a manual link, we should probably NOT be updated by sibling.
            return

        from utils.workday_calculator import WorkdayCalculator
        if self.dates_locked:
            return
            
        if not prev_sibling.end_date:
            return
            
        # New Logic: Start = Prev End + 1 Workday
        # If Parallel: Start = Parent Start (or Self Start if no parent, effectively no change)
        if self.is_parallel and self.parent and self.parent.start_date:
            new_start = self.parent.start_date
        else:
            new_start = WorkdayCalculator.get_next_workday(prev_sibling.end_date)
            
        if new_start != self.start_date:
            # Calculate duration
            duration = 1
            if self.start_date and self.end_date:
                duration = WorkdayCalculator.calculate_duration(self.start_date, self.end_date)
            
            self.start_date = new_start
            
            # Shift end date
            self.end_date = WorkdayCalculator.add_workdays(new_start, duration)

    def update_from_predecessor(self, predecessor: 'TaskNode'):
        """
        Update start date based on manual predecessor link.
        Start = Predecessor.End + 1 Workday
        """
        from utils.workday_calculator import WorkdayCalculator
        
        if self.dates_locked:
            print(f"DEBUG: '{self.name}' is LOCKED. Ignoring predecessor update.")
            return
            
        if not predecessor.end_date:
            print(f"DEBUG: Predecessor '{predecessor.name}' has NO END DATE. Skipping.")
            return
            
        new_start = WorkdayCalculator.get_next_workday(predecessor.end_date)
        print(f"DEBUG: Calc for '{self.name}': Pred '{predecessor.name}' Ends {predecessor.end_date} -> Next Workday = {new_start}")
        
        if new_start != self.start_date:
            print(f"DEBUG: Updating '{self.name}' Start: {self.start_date} -> {new_start}")
            # Calculate duration
            duration = 1
            if self.start_date and self.end_date:
                duration = WorkdayCalculator.calculate_duration(self.start_date, self.end_date)
            
            self.start_date = new_start
            self.end_date = WorkdayCalculator.add_workdays(new_start, duration)
            print(f"DEBUG: Updating '{self.name}' End: -> {self.end_date} (Duration: {duration})")
            
            self.update_status_from_dates()
            self.cascade_updates()
        else:
            print(f"DEBUG: '{self.name}' Start is already {new_start}. No change.")

    def cascade_updates(self):
        """
        Update next sibling to follow me.
        """
        if not self.parent:
            return
            
        siblings = self.parent.children
        try:
            idx = siblings.index(self)
            # Update all subsequent siblings in a chain
            for i in range(idx + 1, len(siblings)):
                prev = siblings[i-1]
                curr = siblings[i]
                curr.update_from_previous_sibling(prev)
                # If curr changed, its children (if any) don't need update, but IT needs to update ITS parent?
                # No, curr's parent is MY parent.
                # But if curr is a parent itself, does its start date change affect its children?
                # Usually Parent dates come FROM children.
                # If 'curr' is a parent, and we shift its start/end, 
                # we might be breaking the "Parent = Min/Max Children" rule.
                # Requirement: "all childrens date should populate into start and end date of the parent and vice versa"
                # "Vice versa" implies if I move Parent, Children move.
                
                if curr.children:
                    curr.shift_children()
                    
        except ValueError: pass
        
        # After cascading to siblings, update parent rollup once more just in case
        if self.parent:
            self.parent.update_dates_from_children()

    def shift_children(self):
        """
        If this node (Parent) moved, shift all children by the same delta.
        Wait, "vice versa" is tricky.
        If Parent Start changes, do we shift all children? Yes, usually.
        """
        from utils.workday_calculator import WorkdayCalculator
        # This requires knowing the OLD start date, which we lost.
        # For now, let's assume strict bottom-up for parents unless we implement explicit "Move Parent" logic.
        # But the requirement says "vice versa".
        # Let's implement a simple check:
        # If I am a parent, and my dates changed via 'update_from_previous_sibling',
        # I should probably shift my children to match my new start.
        
        if not self.children or not self.start_date:
            return
            
        # Find current min start of children
        current_min_start = None
        for child in self.children:
            if child.start_date:
                try:
                    dt = datetime.strptime(child.start_date, DATE_FMT)
                    if current_min_start is None or dt < current_min_start:
                        current_min_start = dt
                except ValueError: pass
                
        if current_min_start:
            try:
                new_start_dt = datetime.strptime(self.start_date, DATE_FMT)
                delta = (new_start_dt - current_min_start).days
                
                if delta != 0:
                    for child in self.children:
                        if child.start_date and child.end_date:
                            try:
                                s = datetime.strptime(child.start_date, DATE_FMT)
                                e = datetime.strptime(child.end_date, DATE_FMT)
                                child.start_date = (s + timedelta(days=delta)).strftime(DATE_FMT)
                                child.end_date = (e + timedelta(days=delta)).strftime(DATE_FMT)
                            except ValueError: pass
            except ValueError: pass

    @property
    def duration(self) -> str:
        from utils.workday_calculator import WorkdayCalculator
        if self.start_date and self.end_date:
            days = WorkdayCalculator.calculate_duration(self.start_date, self.end_date)
            return str(days)
        return "0"

    def set_duration(self, days: int):
        """
        Set duration -> Recalculate End Date.
        """
        from utils.workday_calculator import WorkdayCalculator
        if not self.start_date:
            return
            
        new_end = WorkdayCalculator.add_workdays(self.start_date, days)
        self.set_date('end', new_end)

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
            "children": [child.to_dict() for child in self.children],
            "expanded": self.expanded,
            "dates_locked": self.dates_locked,
            "predecessor_id": self.predecessor_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent: Optional['TaskNode'] = None) -> 'TaskNode':
        node = cls(name=data.get("name", "New Task"), parent=parent)
        node.id = data.get("id", str(uuid.uuid4()))
        node.start_date = data.get("start_date")
        node.end_date = data.get("end_date")
        node.status = data.get("status", "Not Started")
        node.owner = data.get("owner", "")
        node.notes = data.get("notes", "")
        node.expanded = data.get("expanded", True)
        node.dates_locked = data.get("dates_locked", False)
        node.predecessor_id = data.get("predecessor_id")
        
        # Legacy Migration: If "is_parallel" missing, default based on children
        if "is_parallel" in data:
            node.is_parallel = data["is_parallel"]
        else:
            # Legacy file: Parents default to Parallel, Leaves to Sequential
            node.is_parallel = len(data.get("children", [])) > 0
        
        for child_data in data.get("children", []):
            child_node = cls.from_dict(child_data, parent=node)
            node.children.append(child_node)
            
        # Auto-migrate status if needed
        node.update_status_from_dates()
            
        return node

    def update_dates_from_children(self):
        """
        Rollup: Start = Min(Children Start), End = Max(Children End).
        """
        if not self.children:
            return
            
        # Filter valid dates
        starts = [c.start_date for c in self.children if c.start_date]
        ends = [c.end_date for c in self.children if c.end_date]
        
        if not starts or not ends:
            return
            
        # Sort strings (YYYY-MM-DD works for sorting)
        min_start = min(starts)
        max_end = max(ends)
        
        # Update self without triggering full cascade loop if possible, 
        # but we DO want to cascade to our siblings if our dates change.
        
        # Use set_date to ensure propagation
        if self.start_date != min_start:
            self.set_date('start', min_start)
            
        if self.end_date != max_end:
            self.set_date('end', max_end)

    def update_owner_from_children(self):
        """
        Update owner based on children's owners.
        Format: "Owner1/Owner2" (sorted)
        """
        if not self.children:
            return

        owners = set()
        for child in self.children:
            if child.owner:
                # Split by "/" in case child is also a parent with multiple owners
                child_owners = child.owner.split('/')
                for o in child_owners:
                    if o.strip():
                        owners.add(o.strip())
        
        if owners:
            sorted_owners = sorted(list(owners))
            self.owner = "/".join(sorted_owners)
        else:
            self.owner = ""

    def set_duration(self, days: int):
        if days < 1: days = 1
        
        # Keep Start, Move End
        if self.start_date:
            from utils.workday_calculator import WorkdayCalculator
            new_end = WorkdayCalculator.add_workdays(self.start_date, days)
            # FIX: Use set_date to trigger cascade
            self.set_date('end', new_end)

    def set_owner(self, new_owner: str):
        """
        Set the owner and trigger parent updates.
        """
        if self.owner != new_owner:
            self.owner = new_owner
            if self.parent:
                self.parent.update_owner_from_children()
                self.parent.cascade_updates()

    def update_status_from_dates(self):
        """
        Automate status based on dates.
        - Not Started: Start Date > Today
        - In Progress: Start Date <= Today
        - Completed: All children must be completed (for parents)
        """
        if not self.start_date:
            return

        try:
            start_dt = datetime.strptime(self.start_date, DATE_FMT).date()
            today = datetime.now().date()

            # Check Children for Completion FIRST (for parent tasks)
            if self.children:
                all_completed = all(child.status == "Completed" for child in self.children)
                if all_completed:
                    self.status = "Completed"
                    return
                else:
                    # If parent is marked Completed but children aren't, downgrade to In Progress
                    if self.status == "Completed":
                        self.status = "In Progress"
                    # Continue to date-based status logic below

            # Skip date-based status update if already Completed and no children (leaf task)
            if self.status == "Completed" and not self.children:
                return

            # Date-based status for non-parent tasks or parents with incomplete children
            if start_dt > today:
                self.status = "Not Started"
            else:
                self.status = "In Progress"
        except ValueError: pass

    def set_status(self, new_status: str):
        """
        Set status and trigger parent updates.
        """
        if self.status != new_status:
            self.status = new_status
            if self.parent:
                self.parent.update_status_from_dates()

    def collect_dependencies(self) -> List['TaskNode']:
        """
        Return a list of all tasks that depend on this one (siblings and their descendants).
        """
        deps = []
        if self.parent:
            siblings = self.parent.children
            try:
                idx = siblings.index(self)
                # All subsequent siblings
                for i in range(idx + 1, len(siblings)):
                    sib = siblings[i]
                    deps.append(sib)
                    # And their children (recursive)
                    deps.extend(sib.get_all_descendants())
            except ValueError: pass
        return deps

    def get_all_descendants(self) -> List['TaskNode']:
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def simulate_date_change(self, new_start_date: str) -> List[Dict[str, Any]]:
        """
        Simulate what happens if we move this task to new_start_date.
        Returns a list of affected tasks with their simulated new dates.
        Assumes "Chain" logic (Ripple).
        """
        from utils.workday_calculator import WorkdayCalculator
        from datetime import datetime, timedelta
        
        impacts = []
        if not self.start_date:
            return impacts
            
        try:
            current_dt = datetime.strptime(self.start_date, DATE_FMT)
            new_dt = datetime.strptime(new_start_date, DATE_FMT)
            delta_days = (new_dt - current_dt).days
            
            if delta_days == 0:
                return impacts
                
            # Find all dependent tasks
            deps = self.collect_dependencies()
            
            for node in deps:
                if node.start_date:
                    try:
                        s = datetime.strptime(node.start_date, DATE_FMT)
                        new_s = s + timedelta(days=delta_days)
                        impacts.append({
                            'node': node,
                            'old_start': node.start_date,
                            'new_start': new_s.strftime(DATE_FMT),
                            'delta': delta_days
                        })
                    except ValueError: pass
                    
        except ValueError: pass
        
        return impacts
