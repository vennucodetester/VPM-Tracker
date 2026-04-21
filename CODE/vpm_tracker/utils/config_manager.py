import json
import os

CONFIG_FILE = "vpm_config.json"

class ConfigManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.load_config()
        return cls._instance

    def load_config(self):
        self.owners = ["Unassigned", "Me"]
        self.holidays = []
        self.exclude_weekends = True
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.owners = data.get("owners", self.owners)
                    self.holidays = data.get("holidays", self.holidays)
                    self.exclude_weekends = data.get("exclude_weekends", self.exclude_weekends)
            except Exception:
                pass
    
    def save_config(self):
        data = {
            "owners": self.owners,
            "holidays": self.holidays,
            "exclude_weekends": self.exclude_weekends
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def get_owners(self):
        return self.owners

    def set_owners(self, owners):
        self.owners = owners
        self.save_config()

    def get_holidays(self):
        return self.holidays

    def set_holidays(self, holidays):
        self.holidays = holidays
        self.save_config()

    def get_exclude_weekends(self):
        return self.exclude_weekends

    def set_exclude_weekends(self, exclude):
        self.exclude_weekends = exclude
        self.save_config()
