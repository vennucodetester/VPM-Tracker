
import sys
import os

# Add project root to path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Force Light Mode / Excel-like style
    app.setStyle("Fusion") # Fusion gives us a clean base to style on top of
    
    # Force Light Mode / Excel-like style
    app.setStyle("Fusion") 
    
    # Safe Light Theme
    # We target specific widgets to ensure White/Black contrast without breaking headers
    app.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #ffffff;
            color: #000000;
        }
        QTreeWidget {
            background-color: #ffffff;
            color: #000000;
            alternate-background-color: #f0f0f0;
            selection-background-color: #e6f2ff;
            selection-color: #000000;
            border: 1px solid #d0d0d0;
        }
        /* Header styling that ensures text is visible */
        QHeaderView::section {
            background-color: #e0e0e0;
            color: #000000;
            border: 1px solid #d0d0d0;
            padding: 4px;
            font-weight: bold;
        }
        QToolBar {
            background-color: #f0f0f0;
            border-bottom: 1px solid #d0d0d0;
        }
        /* Ensure input fields are visible */
        QLineEdit, QDateEdit, QComboBox {
            background-color: #ffffff;
            color: #000000;
            border: 1px solid #ccc;
        }
    """)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
