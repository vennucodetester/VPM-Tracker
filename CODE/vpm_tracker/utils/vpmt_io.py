"""
vpmt file I/O — v2.0 multi-project format with back-compat for v1.x.

v2.0 structure:
    {
        "version": "2.0",
        "projects": [
            {"name": "...", "metadata": {...}, "tasks": [...]},
            ...
        ]
    }

Legacy formats still supported on load:
  - plain list of task dicts (oldest)
  - {"version": "1.1", "metadata": {...}, "tasks": [...]}  (single project)

Saves always emit v2.0. The loader returns a list of Project dicts so the
UI can spin up one tab per project regardless of source format.
"""
import json
from typing import List, Dict
from models.task_node import TaskNode


CURRENT_VERSION = "2.0"


def _repair_envelope(node: TaskNode):
    """Post-load repair: walk post-order and roll parent dates up from children
    using direct string min/max (no cascade, no side-effects on siblings).
    Fixes legacy files where a buggy writer persisted parents out-of-sync with
    their children, without triggering the full scheduler."""
    for child in node.children:
        _repair_envelope(child)
    if node.children:
        starts = [c.start_date for c in node.children if c.start_date]
        ends = [c.end_date for c in node.children if c.end_date]
        if starts:
            node.start_date = min(starts)
        if ends:
            node.end_date = max(ends)


def save_projects(projects: List[Dict], filename: str):
    """Save a list of project dicts to disk in v2.0 format.

    Each project dict must have: {"name": str, "metadata": dict, "roots": [TaskNode, ...]}.
    """
    payload = {
        "version": CURRENT_VERSION,
        "projects": [
            {
                "name": p["name"],
                "metadata": p.get("metadata", {}),
                "tasks": [n.to_dict() for n in p.get("roots", [])],
            }
            for p in projects
        ],
    }
    with open(filename, "w") as f:
        json.dump(payload, f, indent=2)


def load_projects(filename: str) -> List[Dict]:
    """Load any supported format and return a list of project dicts:
    [{"name": str, "metadata": dict, "roots": [TaskNode, ...]}, ...].
    """
    with open(filename, "r") as f:
        data = json.load(f)

    projects_raw = _normalize_to_projects(data)

    result = []
    for idx, proj in enumerate(projects_raw):
        name = proj.get("name") or f"Project {idx + 1}"
        metadata = proj.get("metadata", {}) or {}
        tasks_data = proj.get("tasks", []) or []
        roots = [TaskNode.from_dict(d) for d in tasks_data]
        for r in roots:
            _repair_envelope(r)
        result.append({"name": name, "metadata": metadata, "roots": roots})

    # Always hand back at least one project so the UI has something to show.
    if not result:
        result.append({"name": "Project 1", "metadata": {}, "roots": []})
    return result


def _normalize_to_projects(data) -> List[Dict]:
    """Map any supported on-disk shape into a v2.0-style list of project dicts."""
    # Oldest: bare list of task dicts
    if isinstance(data, list):
        return [{"name": "Project 1", "metadata": {}, "tasks": data}]

    if not isinstance(data, dict):
        return []

    # v2.0+: explicit projects array
    if "projects" in data and isinstance(data["projects"], list):
        return data["projects"]

    # v1.1: single-project envelope
    if "tasks" in data:
        return [{
            "name": "Project 1",
            "metadata": data.get("metadata", {}),
            "tasks": data.get("tasks", []),
        }]

    # Unknown shape — treat as empty so the app still opens
    return []


# ---- legacy single-project API retained as thin wrappers ----
# The regression test (tests/test_timeline_invariants.py) and any external
# tooling imports these names directly.
def save_project(nodes: List[TaskNode], filename: str):
    """Legacy single-project saver — writes v2.0 with one project.
    Active ConfigManager metadata is captured at save time."""
    from utils.config_manager import ConfigManager
    config = ConfigManager()
    metadata = {
        "owners": config.get_owners(),
        "holidays": config.get_holidays(),
        "exclude_weekends": config.get_exclude_weekends(),
    }
    save_projects(
        [{"name": "Project 1", "metadata": metadata, "roots": nodes}],
        filename,
    )


def load_project(filename: str) -> List[TaskNode]:
    """Legacy single-project loader — returns only the first project's roots."""
    projects = load_projects(filename)
    if not projects:
        return []
    first = projects[0]
    # Push metadata into the active config so legacy call sites keep working.
    from utils.config_manager import ConfigManager
    config = ConfigManager()
    md = first.get("metadata", {}) or {}
    if "owners" in md:
        config.set_owners(md["owners"])
    if "holidays" in md:
        config.set_holidays(md["holidays"])
    if "exclude_weekends" in md:
        config.set_exclude_weekends(md["exclude_weekends"])
    return first.get("roots", [])
