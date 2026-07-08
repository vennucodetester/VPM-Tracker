
import sys
import os
import unittest
from datetime import datetime

# Add project root and vpm_tracker to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'vpm_tracker'))

from vpm_tracker.models.task_node import TaskNode
from vpm_tracker.models.formula_engine import FormulaEngine

class TestVPMFeatures(unittest.TestCase):
    def test_formulas_and_cascade(self):
        print("Testing Formulas and Cascades...")
        
        # Setup: Phase 1 -> Phase 2 (dep on Phase 1)
        root = TaskNode("Root")
        phase1 = TaskNode("Phase 1", parent=root)
        phase1.start_date = "2025-01-01"
        phase1.end_date = "2025-01-10"
        root.add_child(phase1)
        
        phase2 = TaskNode("Phase 2", parent=root)
        # Phase 2 starts 1 day after Phase 1 ends
        phase2.set_formula('start', "=PrevSibling.End+1")
        # Phase 2 ends 5 days after its start
        phase2.set_formula('end', "=Start+5")
        root.add_child(phase2)
        
        # Initial Evaluation
        self.assertEqual(phase2.start_date, "2025-01-11") # 10 + 1
        self.assertEqual(phase2.end_date, "2025-01-16")   # 11 + 5
        
        print("Initial formula evaluation passed.")
        
        # Update Phase 1
        print("Updating Phase 1 End Date...")
        phase1.set_date('end', "2025-01-20")
        
        # Check Cascade
        self.assertEqual(phase2.start_date, "2025-01-21") # 20 + 1
        self.assertEqual(phase2.end_date, "2025-01-26")   # 21 + 5
        
        print("Cascade update passed.")

    def test_ui_imports(self):
        print("Testing UI Imports...")
        try:
            from vpm_tracker.ui.header_filter import FilterHeaderView
            from vpm_tracker.ui.tree_grid_view import TreeGridView
            print("UI imports successful.")
        except ImportError as e:
            self.fail(f"Failed to import UI components: {e}")

if __name__ == '__main__':
    unittest.main()
