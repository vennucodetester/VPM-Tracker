from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
                             QPushButton, QCheckBox, QLabel, QCalendarWidget, 
                             QDialogButtonBox, QMessageBox)
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QTextCharFormat, QFont, QColor, QBrush
from utils.config_manager import ConfigManager

class CalendarSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calendar Settings")
        self.resize(600, 400)
        self.config = ConfigManager()
        self.holidays = set(self.config.get_holidays())
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Weekend Settings
        self.weekend_cb = QCheckBox("Exclude Weekends (Saturday & Sunday)")
        self.weekend_cb.setChecked(self.config.get_exclude_weekends())
        layout.addWidget(self.weekend_cb)
        
        layout.addSpacing(10)
        
        # Holidays Section
        layout.addWidget(QLabel("Holidays (Select date to add/remove):"))
        
        h_layout = QHBoxLayout()
        
        # Calendar
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        
        # Styling: Remove dark header background, make text bold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setForeground(QBrush(QColor("black")))
        fmt.setBackground(QBrush(QColor("white"))) # Remove dark gray default
        
        for day in [Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
                    Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday,
                    Qt.DayOfWeek.Sunday]:
            self.calendar.setWeekdayTextFormat(day, fmt)
            
        self.calendar.clicked.connect(self.on_date_clicked)
        h_layout.addWidget(self.calendar)
        
        # Initial Highlight
        self.highlight_holidays()
        
        # List
        v_layout = QVBoxLayout()
        self.holiday_list = QListWidget()
        self.refresh_list()
        v_layout.addWidget(self.holiday_list)
        
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected_holiday)
        v_layout.addWidget(remove_btn)
        
        h_layout.addLayout(v_layout)
        layout.addLayout(h_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def on_date_clicked(self, qdate):
        date_str = qdate.toString("yyyy-MM-dd")
        if date_str in self.holidays:
            self.holidays.remove(date_str)
            # Clear format
            self.calendar.setDateTextFormat(qdate, QTextCharFormat())
        else:
            self.holidays.add(date_str)
            
        self.highlight_holidays()
        self.refresh_list()
        
    def highlight_holidays(self):
        # Format for holidays
        h_fmt = QTextCharFormat()
        h_fmt.setBackground(QBrush(QColor("#ffcccc"))) # Light Red
        h_fmt.setForeground(QBrush(QColor("black")))
        
        for date_str in self.holidays:
            try:
                qdate = QDate.fromString(date_str, "yyyy-MM-dd")
                self.calendar.setDateTextFormat(qdate, h_fmt)
            except: pass
        
    def remove_selected_holiday(self):
        item = self.holiday_list.currentItem()
        if item:
            date_str = item.text()
            if date_str in self.holidays:
                self.holidays.remove(date_str)
                
                # Clear format
                qdate = QDate.fromString(date_str, "yyyy-MM-dd")
                self.calendar.setDateTextFormat(qdate, QTextCharFormat())
                
                self.refresh_list()
                
    def refresh_list(self):
        self.holiday_list.clear()
        for date_str in sorted(list(self.holidays)):
            self.holiday_list.addItem(date_str)
            
    def accept(self):
        self.config.set_holidays(list(self.holidays))
        self.config.set_exclude_weekends(self.weekend_cb.isChecked())
        super().accept()
