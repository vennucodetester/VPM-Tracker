from datetime import datetime, timedelta
from utils.config_manager import ConfigManager

DATE_FMT = "%Y-%m-%d"

class WorkdayCalculator:
    @staticmethod
    def add_workdays(start_date_str: str, days: int) -> str:
        """
        Add 'days' workdays to start_date.
        """
        config = ConfigManager()
        holidays = set(config.get_holidays())
        exclude_weekends = config.get_exclude_weekends()
        
        try:
            current_date = datetime.strptime(start_date_str, DATE_FMT)
        except ValueError:
            return start_date_str
            
        added = 0
        # Direction: if days is negative, we go backwards? 
        # For duration, days is usually positive. 
        # If days is 0, return start_date? Or 1 day duration means same day?
        # Convention: Duration 1 day = Start Date == End Date.
        # So we add (days - 1) to get End Date.
        
        target_days = max(0, days - 1)
        direction = 1 if target_days >= 0 else -1
        
        while added < abs(target_days):
            current_date += timedelta(days=direction)
            
            # Check if valid workday
            if WorkdayCalculator.is_workday(current_date, holidays, exclude_weekends):
                added += 1
                
        return current_date.strftime(DATE_FMT)

    @staticmethod
    def get_next_workday(date_str: str) -> str:
        """
        Get the next valid workday after the given date.
        """
        config = ConfigManager()
        holidays = set(config.get_holidays())
        exclude_weekends = config.get_exclude_weekends()
        
        try:
            current_date = datetime.strptime(date_str, DATE_FMT)
        except ValueError:
            return date_str
            
        while True:
            current_date += timedelta(days=1)
            if WorkdayCalculator.is_workday(current_date, holidays, exclude_weekends):
                return current_date.strftime(DATE_FMT)

    @staticmethod
    def calculate_duration(start_date_str: str, end_date_str: str) -> int:
        """
        Calculate number of workdays between start and end (inclusive).
        """
        config = ConfigManager()
        holidays = set(config.get_holidays())
        exclude_weekends = config.get_exclude_weekends()
        
        try:
            start = datetime.strptime(start_date_str, DATE_FMT)
            end = datetime.strptime(end_date_str, DATE_FMT)
        except ValueError:
            return 0
            
        if start > end:
            return 0
            
        count = 0
        curr = start
        while curr <= end:
            if WorkdayCalculator.is_workday(curr, holidays, exclude_weekends):
                count += 1
            curr += timedelta(days=1)
            
        return count

    @staticmethod
    def is_workday(date_obj: datetime, holidays: set, exclude_weekends: bool) -> bool:
        date_str = date_obj.strftime(DATE_FMT)
        
        if date_str in holidays:
            return False
            
        if exclude_weekends:
            # 0=Mon, 6=Sun
            if date_obj.weekday() >= 5:
                return False
                
        return True
