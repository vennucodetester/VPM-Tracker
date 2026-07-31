import os
import re
import subprocess
import sys


FALLBACK_VERSION = "2026.07.08-r1"


def install_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _run_git(args):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(
        ["git", "-C", install_dir(), *args],
        text=True,
        capture_output=True,
        timeout=10,
        creationflags=flags,
    )


def detect_version():
    try:
        result = _run_git(["tag", "--list", "rev-*", "--sort=-v:refname"])
        for line in result.stdout.splitlines():
            name = line.strip()
            if re.fullmatch(r"rev-\d{4}\.\d{2}\.\d{2}-r\d+", name):
                return name.removeprefix("rev-")
    except Exception:
        pass
    return FALLBACK_VERSION
