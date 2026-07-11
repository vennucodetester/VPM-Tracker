"""
Private local usage logging for VPM Tracker.

Future analysis sessions should read usage_logs/report-latest.md first, then
inspect raw JSONL logs only when more detail is needed. Nothing is sent over
the network; failures are intentionally ignored so logging can never interrupt
the app.
"""
import json
import os
import secrets
import time
from datetime import datetime, timedelta

from PyQt6.QtCore import QSettings


class UsageLogger:
    def __init__(self):
        self.sid = secrets.token_hex(3)
        self.started = time.time()
        self.enabled = True
        self.root = os.path.abspath(os.path.join(os.getcwd(), "usage_logs"))
        # Automated/offscreen runs (tests, verification scripts) must never
        # pollute the user's real usage data.
        if (os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
                or os.environ.get("VPM_TELEMETRY", "") == "0"):
            self.enabled = False
            return
        try:
            self.enabled = bool(QSettings("VPM", "VPMTracker").value(
                "usage_logging", True, type=bool))
            self.prune()
        except Exception:
            pass

    def set_enabled(self, enabled: bool):
        try:
            self.enabled = bool(enabled)
            QSettings("VPM", "VPMTracker").setValue("usage_logging", self.enabled)
        except Exception:
            pass

    def path(self):
        stamp = datetime.now().strftime("%Y-%m")
        return os.path.join(self.root, f"usage-{stamp}.jsonl")

    def prune(self):
        try:
            if not os.path.isdir(self.root):
                return
            cutoff = datetime.now() - timedelta(days=366)
            for name in os.listdir(self.root):
                if not (name.startswith("usage-") and name.endswith(".jsonl")):
                    continue
                path = os.path.join(self.root, name)
                if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                    os.remove(path)
        except Exception:
            pass

    def log(self, event: str, **details):
        try:
            if not self.enabled:
                return
            os.makedirs(self.root, exist_ok=True)
            line = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sid": self.sid,
                "ev": event,
                "d": details or {},
            }
            with open(self.path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(line, separators=(",", ":"), default=str) + "\n")
        except Exception:
            pass

    def session_secs(self) -> int:
        try:
            return int(time.time() - self.started)
        except Exception:
            return 0


usage = UsageLogger()


def log(event: str, **details):
    usage.log(event, **details)


def set_enabled(enabled: bool):
    usage.set_enabled(enabled)


def is_enabled() -> bool:
    return bool(getattr(usage, "enabled", True))


def timed_exec(dialog, name: str):
    start = time.time()
    try:
        result = dialog.exec()
        outcome = "ok" if result else "cancel"
        usage.log("dialog", name=name, outcome=outcome,
                  ms_open=int((time.time() - start) * 1000))
        return result
    except Exception as exc:
        usage.log("error", where=f"dialog:{name}", type=type(exc).__name__)
        raise
