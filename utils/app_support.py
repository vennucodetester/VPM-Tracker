import json
import os
from datetime import datetime

from utils.version_info import detect_version, install_dir


SUPPORT_DIR = ".git-helper"
LOG_DIR = "logs"
RECOVERY_DIR = "recovery"
SUPPORT_REPORT_NAME = "Support Report.jsonl"


def event_time():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def support_dir():
    path = os.path.join(install_dir(), SUPPORT_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir():
    path = os.path.join(support_dir(), LOG_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def recovery_dir():
    path = os.path.join(support_dir(), RECOVERY_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def support_report_path():
    return os.path.join(logs_dir(), SUPPORT_REPORT_NAME)


def append_support_event(event, **data):
    record = {
        "time": event_time(),
        "version": detect_version(),
        "event": event,
        **data,
    }
    try:
        with open(support_report_path(), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")
    except OSError:
        pass


def collect_support_report():
    append_support_event("support_report_collected")
    return support_report_path()
