import os
import sys
from PyQt6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt

# Set offscreen platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.tree_grid_view import MoneyDelegate, money_text

def test_money_delegate():
    app = QApplication(sys.argv)
    
    raw_potential = 7.5
    formatted_str = money_text(raw_potential)
    print(f"1. Node value {raw_potential} formatted by update_from_node: '{formatted_str}'")
    
    # Simulate Option A fix: store raw float instead of formatted string
    item = QTreeWidgetItem()
    item.setData(0, Qt.ItemDataRole.DisplayRole, raw_potential)
    
    delegate = MoneyDelegate()
    display_value = item.data(0, Qt.ItemDataRole.DisplayRole)
    print(f"2. Item DisplayRole data: '{display_value}'")
    
    rendered_text = delegate.displayText(display_value, None)
    print(f"3. MoneyDelegate.displayText rendered text: '{rendered_text}'")
    
    if rendered_text == formatted_str:
        print("4. FIX VERIFIED: Delegate returns correctly formatted string!")
    else:
        print("4. Fix failed.")

if __name__ == "__main__":
    test_money_delegate()
