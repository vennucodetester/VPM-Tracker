
from enum import Enum
from PyQt6.QtGui import QColor

class AppConstants:
    APP_NAME = "VPM Tracker"
    VERSION = "1.0.0"
    FILE_EXT = ".vpmt"

class Columns:
    TREE = 0
    START = 1
    END = 2
    DURATION = 3
    STATUS = 4
    OWNER = 5
    NOTES = 6
    COUNT = 7
    
    NAMES = ["Task Name", "Start Date", "End Date", "Duration", "Status", "Owner", "Notes"]

class Status(Enum):
    PENDING = "Not Started"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    OVERDUE = "Overdue" # Calculated, not always stored explicitly as a status enum, but useful for logic

class Colors:
    # Backgrounds
    BG_DARK = QColor("#ffffff")      # White background
    BG_TREE = QColor("#f0f0f0")      # Light gray for tree/alternating
    
    # Status Colors (for text or small indicators)
    # Status Colors (for text or small indicators)
    RED = QColor("#FF0000")          # Pure Bright Red (Overdue)
    GREEN = QColor("#00C853")        # Vivid Green (Completed)
    ORANGE = QColor("#E65100")       # Dark Orange (Leaf)
    GRAY = QColor("#212121")         # Almost Black (Parent)
    
    # UI
    SELECTION = QColor("#0078d7")    # Standard Windows Blue
    TEXT_WHITE = QColor("#000000")   # Black text
    
    # Gantt / Dark Theme
    BG_DARK = QColor("#1e1e1e")
    GANTT_GRID = QColor("#333333")
    GANTT_TEXT = QColor("#dddddd")
    BAR_BLUE = QColor("#2979FF")     # In Progress (Normal)
    BAR_GREEN = QColor("#00C853")    # Completed
    BAR_DELAYED = QColor("#D50000")  # Red (Delayed)
    BAR_CRITICAL = QColor("#FF4081") # Pink (Critical)
    
    # Parent Bars
    BAR_PARENT_COLLAPSED = QColor("#424242") # (Fallback, usually overridden by status)
    BAR_PARENT_EXPANDED = QColor("#666666")  # Solid Gray
