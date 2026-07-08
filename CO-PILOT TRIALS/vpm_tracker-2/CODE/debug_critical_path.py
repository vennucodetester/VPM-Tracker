
import json
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'vpm_tracker'))

from vpm_tracker.models.task_node import TaskNode
from vpm_tracker.utils.critical_path import CriticalPathAnalyzer

def main():
    file_path = "DG-2.0-4.vpmt"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r') as f:
        data = json.load(f)

    # Reconstruct Task Nodes
    root_nodes = []
    for task_data in data.get("tasks", []):
        root_nodes.append(TaskNode.from_dict(task_data))

    print(f"Loaded {len(root_nodes)} root nodes.")

    # Run Analysis
    analyzer = CriticalPathAnalyzer(root_nodes)
    results = analyzer.analyze()
    
    critical_ids = results['critical_path_ids']
    slack = results['slack']
    early_finish = results['early_finish']
    project_end = results['project_end']
    
    # Sort all nodes by Early Finish to find the true latest task
    sorted_by_ef = sorted(all_nodes, key=lambda x: early_finish.get(x.id, datetime.min), reverse=True)
    
    print("\nXXX RESULTS START XXX")
    print(f"Max EF: {early_finish.get(sorted_by_ef[0].id)}")
    
    for i in range(min(10, len(sorted_by_ef))):
        node = sorted_by_ef[i]
        ef = early_finish.get(node.id)
        print(f"EF: {ef} | Task: {node.name}")
    print("XXX RESULTS END XXX")

    # Check specifically for TC release
    print("\n--- TC release Analysis ---")
    tc_nodes = [n for n in all_nodes if "TC release" in n.name]
    for node in tc_nodes:
        ef = early_finish.get(node.id)
        sl = slack.get(node.id)
        print(f"Task: '{node.name}' (Parent: {node.parent.name if node.parent else 'None'}) | EF: {ef} | Slack: {sl}")

    print("\n--- Parent vs Child Criticality Mismatch ---")
    mismatches = 0
    for node in all_nodes:
        if node.children:
            child_critical = any(c.id in critical_ids for c in node.children)
            is_parent_critical = node.id in critical_ids
            
            if child_critical and not is_parent_critical:
                mismatches += 1
                print(f"MISMATCH: Parent '{node.name}' (Slack: {slack.get(node.id)}) is NOT critical.")
                for c in node.children:
                     if c.id in critical_ids:
                         print(f"  -> Critical Child: '{c.name}' (Slack: {slack.get(c.id)})")
                         
    if mismatches == 0:
        print("No parent-child mismatches found.")


if __name__ == "__main__":
    main()
