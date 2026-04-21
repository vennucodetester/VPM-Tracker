import json
from typing import List
from models.task_node import TaskNode
from utils.config_manager import ConfigManager

def save_project(nodes: List[TaskNode], filename: str):
    # Get current config
    config = ConfigManager()
    metadata = {
        "owners": config.get_owners(),
        "holidays": config.get_holidays(),
        "exclude_weekends": config.get_exclude_weekends()
    }
    
    tasks_data = [node.to_dict() for node in nodes]
    
    file_data = {
        "version": "1.1",
        "metadata": metadata,
        "tasks": tasks_data
    }
    
    with open(filename, 'w') as f:
        json.dump(file_data, f, indent=2)

def load_project(filename: str) -> List[TaskNode]:
    with open(filename, 'r') as f:
        data = json.load(f)
        
    tasks_data = []
    
    # Check format (List = Old, Dict = New)
    if isinstance(data, list):
        tasks_data = data
    elif isinstance(data, dict):
        tasks_data = data.get("tasks", [])
        
        # Load Metadata
        metadata = data.get("metadata", {})
        config = ConfigManager()
        if "owners" in metadata:
            config.set_owners(metadata["owners"])
        if "holidays" in metadata:
            config.set_holidays(metadata["holidays"])
        if "exclude_weekends" in metadata:
            config.set_exclude_weekends(metadata["exclude_weekends"])
            
    return [TaskNode.from_dict(d) for d in tasks_data]
