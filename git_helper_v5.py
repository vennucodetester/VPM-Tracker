"""
Git Helper v4 - Smart Sync + Safe Restore.

A small PyQt6 app for non-technical GitHub workflows:
- one Sync button for normal work,
- plain-English status,
- non-interactive git commands,
- safe restore points that create new commits instead of rewriting history.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)


DEFAULT_REMOTE_URL = "https://github.com/vennucodetester/VPM-Tracker.git"
GITIGNORE_LINES = ["__pycache__/", "*.pyc", "*.bak*", ".git-helper/"]
APP_VERSION = "v5"
APP_DISPLAY_NAME = f"Git Helper {APP_VERSION}"
SUPPORT_DIR = ".git-helper"
SUPPORT_LOG = "git-helper-v5.log"
GLOBAL_SUPPORT_DIR = "Git Helper v5"
GLOBAL_SUPPORT_LOG = "git-helper-v5-all-folders.jsonl"
EXPORTED_SUPPORT_REPORT = "Git Helper v5 Support Report.jsonl"


INSTRUCTIONS = """Git Helper manages only this folder and the folders below it.

Sync: download GitHub updates, save this computer's edits, and upload them.
Rev Up: Sync, then mark the next numbered revision in GitHub.
Download New Rev: make a clean new numbered folder beside this one.

Different files are never silently discarded. Recovery copies and a support log
are kept in the hidden .git-helper folder."""


def support_path(repo_path, *parts):
    return os.path.join(repo_path, SUPPORT_DIR, *parts)


def global_support_log_path():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, GLOBAL_SUPPORT_DIR, GLOBAL_SUPPORT_LOG)


def append_json_line(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")


def append_support_log(repo_path, event, **data):
    if not repo_path:
        return
    try:
        folder = support_path(repo_path)
        os.makedirs(folder, exist_ok=True)
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "version": APP_VERSION,
            "event": event,
            "project_folder": os.path.abspath(repo_path),
            **data,
        }
        append_json_line(support_path(repo_path, SUPPORT_LOG), record)
        append_json_line(global_support_log_path(), record)
    except OSError:
        pass


def collect_support_report(repo_path):
    sources = [global_support_log_path(), support_path(repo_path, SUPPORT_LOG)]
    destination = os.path.join(repo_path, EXPORTED_SUPPORT_REPORT)
    if os.path.isfile(destination):
        sources.insert(0, destination)
    seen = set()
    lines = []
    for source in sources:
        if not os.path.isfile(source):
            continue
        with open(source, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                normalized = line.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    lines.append(normalized)
    with open(destination, "w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")
    return destination, len(lines)


def safe_command_for_log(args):
    cleaned = []
    for value in args:
        text = str(value)
        text = re.sub(r"(https?://)[^/@\s]+@", r"\1[credentials-hidden]@", text)
        cleaned.append(text)
    return cleaned


@dataclass
class GitResult:
    success: bool
    output: str = ""
    friendly: str = ""


@dataclass
class RepoState:
    branch: str = "main"
    dirty: bool = False
    conflicted: bool = False
    ahead: int = 0
    behind: int = 0
    has_remote: bool = False
    upstream: bool = False
    remote_checked: bool = False
    remote_reachable: bool = True
    remote_error: str = ""
    changed_files: list = field(default_factory=list)


FRIENDLY_ERRORS = [
    (
        ("would be overwritten by merge", "local changes would be overwritten"),
        "Your local changes need to be saved before GitHub's changes can be brought in. Sync can usually fix this by saving first.",
    ),
    (
        ("fetch first", "rejected", "remote contains work"),
        "GitHub has newer changes. Sync will get those first, then send your work again.",
    ),
    (
        ("divergent branches", "need to specify how to reconcile"),
        "Your computer and GitHub both have new work. Sync will combine them without opening a text editor.",
    ),
    (
        ("please tell me who you are", "unable to auto-detect email address"),
        "Git needs your name and email once before it can save changes.",
    ),
    (
        ("authentication failed", "could not read username", "terminal prompts disabled", "repository not found"),
        "GitHub needs you to sign in once on this computer.",
    ),
    (
        ("unrelated histories",),
        "This folder and the GitHub repo were started separately. Setup will combine them safely.",
    ),
    (
        ("index.lock",),
        "Git is locked, often because OneDrive or another Git command touched it. Close other Git tools and try again.",
    ),
    (
        ("conflict", "merge conflict", "unmerged"),
        "The same file changed in two places. Choose which version to keep, then Sync can finish.",
    ),
]


def friendly_error(output):
    text = (output or "").lower()
    for needles, message in FRIENDLY_ERRORS:
        if any(needle in text for needle in needles):
            return message
    if text.strip():
        return "Git could not finish that step. The technical details are in the Details panel."
    return "Git could not finish that step, but it did not return any technical details."


def is_auth_error(output):
    text = (output or "").lower()
    return any(
        needle in text
        for needle in (
            "authentication failed",
            "could not read username",
            "terminal prompts disabled",
            "repository not found",
        )
    )


def norm_path(path):
    return os.path.normcase(os.path.abspath(path))


class GitRunner:
    """Small, non-interactive wrapper around git."""

    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.last_remote_checked = False
        self.last_remote_reachable = True
        self.last_remote_error = ""

    def _git_env(self):
        env = os.environ.copy()
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "echo",
                "GIT_EDITOR": "true",
                "GIT_MERGE_AUTOEDIT": "no",
            }
        )
        return env

    def _run(self, args, timeout=45):
        started = datetime.datetime.now()
        try:
            kwargs = {
                "cwd": self.repo_path or None,
                "capture_output": True,
                "text": True,
                "timeout": timeout,
                "env": self._git_env(),
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(["git"] + args, **kwargs)
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            success = result.returncode == 0
            append_support_log(
                self.repo_path,
                "git_command",
                command=safe_command_for_log(["git"] + args),
                success=success,
                return_code=result.returncode,
                duration_ms=int((datetime.datetime.now() - started).total_seconds() * 1000),
                output=output,
            )
            return GitResult(success, output, "" if success else friendly_error(output))
        except subprocess.TimeoutExpired:
            append_support_log(self.repo_path, "git_timeout", command=safe_command_for_log(["git"] + args), timeout=timeout)
            return GitResult(
                False,
                "Command timed out.",
                "Git took too long. If this was a GitHub login step, sign in once and try again.",
            )
        except FileNotFoundError:
            append_support_log(self.repo_path, "git_missing", command=safe_command_for_log(["git"] + args))
            return GitResult(
                False,
                "git is not installed or not in PATH.",
                "Git is not installed. Install Git for Windows, then reopen this app.",
            )

    def git_installed(self):
        return self._run(["--version"]).success

    def is_git_repo(self):
        return self._run(["rev-parse", "--is-inside-work-tree"]).success

    def repo_toplevel(self):
        result = self._run(["rev-parse", "--show-toplevel"])
        return norm_path(result.output.strip()) if result.success and result.output.strip() else ""

    def is_own_repo(self):
        top = self.repo_toplevel()
        return bool(top) and top == norm_path(self.repo_path)

    def init(self):
        return self._run(["init"])

    def current_branch(self):
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.output.strip() if result.success and result.output.strip() != "HEAD" else ""

    def set_branch_main(self):
        return self._run(["branch", "-M", "main"])

    def config_get(self, key, global_scope=False):
        args = ["config"]
        if global_scope:
            args.append("--global")
        args.append(key)
        return self._run(args)

    def config_set(self, key, value, global_scope=False):
        args = ["config"]
        if global_scope:
            args.append("--global")
        args += [key, value]
        return self._run(args)

    def ensure_credential_helper(self):
        if sys.platform != "win32":
            return GitResult(True, "")
        current = self.config_get("credential.helper", global_scope=True)
        if current.success and current.output.strip():
            return current
        result = self.config_set("credential.helper", "manager", global_scope=True)
        if result.success:
            return result
        return self.config_set("credential.helper", "manager-core", global_scope=True)

    def remotes(self):
        return self._run(["remote", "-v"])

    def has_remote(self):
        return bool(self.remotes().output.strip())

    def add_or_set_origin(self, url):
        if "origin" in self.remotes().output:
            return self._run(["remote", "set-url", "origin", url])
        return self._run(["remote", "add", "origin", url])

    def fetch(self):
        result = self._run(["fetch", "--prune", "origin"], timeout=25)
        self.last_remote_checked = True
        self.last_remote_reachable = result.success
        self.last_remote_error = "" if result.success else result.friendly
        return result

    def default_remote_branch(self):
        result = self._run(["ls-remote", "--symref", "origin", "HEAD"], timeout=25)
        if result.success:
            for line in result.output.splitlines():
                match = re.match(r"ref:\s+refs/heads/([^\s]+)\s+HEAD", line.strip())
                if match:
                    return match.group(1)
        return "main"

    def remote_has_branches(self):
        result = self._run(["ls-remote", "--heads", "origin"], timeout=25)
        return result.success and bool(result.output.strip()), result

    def checkout_new_branch(self, branch):
        current = self.current_branch()
        if current == branch:
            return GitResult(True, f"Already on {branch}.")
        return self._run(["checkout", "-B", branch])

    def remote_branch_exists(self, branch="main"):
        result = self._run(["ls-remote", "--heads", "origin", branch], timeout=25)
        return result.success and bool(result.output.strip())

    def remote_tracking_exists(self, branch=None):
        branch = branch or self.current_branch()
        return self._run(["rev-parse", "--verify", f"origin/{branch}"]).success

    def upstream_exists(self):
        return self._run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]).success

    def status_porcelain(self):
        return self._run(["status", "--porcelain=v1"])

    def changed_files(self):
        result = self.status_porcelain()
        files = []
        conflicted = False
        if not result.success:
            return files, conflicted
        for line in result.output.splitlines():
            if len(line) < 4:
                continue
            code = line[:2]
            path = line[3:]
            if code in ("UU", "AA", "DD", "AU", "UA", "DU", "UD") or "U" in code:
                conflicted = True
            files.append((code, path))
        return files, conflicted

    def dirty(self):
        return bool(self.status_porcelain().output.strip())

    def merge_in_progress(self):
        return self._run(["rev-parse", "-q", "--verify", "MERGE_HEAD"]).success

    def has_unresolved_conflicts(self):
        _, conflicted = self.changed_files()
        return conflicted or self.merge_in_progress()

    def ahead_behind(self):
        if not self.upstream_exists():
            return 0, 0
        result = self._run(["rev-list", "--left-right", "--count", "HEAD...@{u}"])
        if not result.success:
            return 0, 0
        parts = result.output.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])
        return 0, 0

    def repo_state(self, fetch_remote=False):
        files, conflicted = self.changed_files()
        if fetch_remote and self.has_remote():
            self.fetch()
        ahead, behind = self.ahead_behind()
        return RepoState(
            branch=self.current_branch() or "(not set)",
            dirty=bool(files),
            conflicted=conflicted,
            ahead=ahead,
            behind=behind,
            has_remote=self.has_remote(),
            upstream=self.upstream_exists(),
            remote_checked=self.last_remote_checked,
            remote_reachable=self.last_remote_reachable,
            remote_error=self.last_remote_error,
            changed_files=files,
        )

    def stage_all(self):
        return self._run(["add", "-A"])

    def stage_files(self, files):
        return self._run(["add", "--"] + files)

    def unstage_files(self, files):
        return self._run(["restore", "--staged", "--"] + files)

    def commit(self, message):
        return self._run(["commit", "-m", message])

    def commit_if_needed(self, message):
        if not self.dirty():
            return GitResult(True, "No local changes to save.")
        staged = self.stage_all()
        if not staged.success:
            return staged
        committed = self.commit(message)
        if committed.success:
            return committed
        if "nothing to commit" in committed.output.lower():
            return GitResult(True, committed.output, "No local changes to save.")
        return committed

    def pull_no_edit(self, allow_unrelated=False):
        branch = self.current_branch()
        if not branch:
            return GitResult(False, "No branch is checked out.", "This project does not have a branch checked out yet.")
        args = ["pull", "--no-edit", "--no-rebase", "origin", branch]
        if allow_unrelated:
            args.insert(1, "--allow-unrelated-histories")
        return self._run(args, timeout=45)

    def merge_fetched_remote(self):
        branch = self.current_branch()
        if not branch:
            return GitResult(False, "No branch is checked out.", "This project does not have a branch checked out yet.")
        if not self.remote_tracking_exists(branch):
            return GitResult(True, "No GitHub branch exists yet.")
        return self._run(["merge", "--no-edit", f"origin/{branch}"], timeout=45)

    def push(self):
        branch = self.current_branch()
        if not branch:
            return GitResult(False, "No branch is checked out.", "This project does not have a branch checked out yet.")
        if self.upstream_exists():
            return self._run(["push"], timeout=45)
        return self._run(["push", "-u", "origin", branch], timeout=45)

    def stash_save(self, message="Temporary save before Sync"):
        return self._run(["stash", "push", "-u", "-m", message])

    def stash_pop(self):
        return self._run(["stash", "pop"])

    def diff_file(self, filepath):
        return self._run(["diff", "--", filepath])

    def diff_staged_file(self, filepath):
        return self._run(["diff", "--cached", "--", filepath])

    def log(self, count=20):
        return self._run(["log", "--oneline", f"-n{count}"])

    def restore_points(self, count=50):
        fmt = "%H%x1f%ad%x1f%s"
        return self._run(["log", f"--pretty=format:{fmt}", "--date=local", f"-n{count}"])

    def create_tag(self, name, message=""):
        msg = message or name
        return self._run(["tag", "-a", name, "-m", msg])

    def list_tags(self):
        return self._run(["tag", "--sort=-creatordate"])

    def push_tags(self):
        return self._run(["push", "--tags"], timeout=90)

    def merge_remote_keep_local_on_collision(self):
        branch = self.current_branch()
        if not branch or not self.remote_tracking_exists(branch):
            return GitResult(True, "No GitHub changes to combine.")
        return self._run(["merge", "--no-edit", "-X", "ours", f"origin/{branch}"], timeout=60)

    def finish_conflicts_keep_local(self):
        unresolved = self._run(["diff", "--name-only", "--diff-filter=U"])
        if not unresolved.success:
            return unresolved
        for path in [line for line in unresolved.output.splitlines() if line.strip()]:
            kept = self._run(["checkout", "--ours", "--", path])
            if not kept.success:
                removed = self._run(["rm", "-f", "--ignore-unmatch", "--", path])
                if not removed.success:
                    return removed
        staged = self.stage_all()
        if not staged.success:
            return staged
        return self.commit_staged_if_needed("Combine GitHub updates; keep this computer's edits on collisions")

    def revision_tags(self):
        result = self._run(["tag", "--list", "rev-*", "--sort=v:refname"])
        return [line.strip() for line in result.output.splitlines() if line.strip()] if result.success else []

    def next_revision_tag(self):
        numbers = []
        for tag in self.revision_tags():
            match = re.fullmatch(r"rev-(\d+)", tag)
            if match:
                numbers.append(int(match.group(1)))
        return f"rev-{(max(numbers, default=0) + 1):04d}"

    def remote_url(self):
        result = self._run(["remote", "get-url", "origin"])
        return result.output.strip() if result.success else ""

    def create_revision(self):
        tag = self.next_revision_tag()
        created = self._run(["tag", "-a", tag, "-m", f"Project revision {tag}"])
        if not created.success:
            return created, ""
        pushed = self._run(["push", "origin", tag], timeout=60)
        return pushed, tag

    def checkout_ours(self, file_path):
        return self._run(["checkout", "--ours", "--", file_path])

    def checkout_theirs(self, file_path):
        return self._run(["checkout", "--theirs", "--", file_path])

    def conflict_sides(self, file_path):
        result = self._run(["ls-files", "-u", "--", file_path])
        if not result.success:
            return True, True
        stages = set()
        for line in result.output.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2].isdigit():
                stages.add(parts[2])
        return "2" in stages, "3" in stages

    def remove_file(self, file_path):
        return self._run(["rm", "-f", "--", file_path])

    def merge_abort(self):
        return self._run(["merge", "--abort"])

    def checkout_file_from_commit(self, commit_hash, file_path):
        return self._run(["checkout", commit_hash, "--", file_path])

    def tracked_files(self, ref="HEAD"):
        result = self._run(["ls-tree", "-r", "--name-only", ref])
        if not result.success:
            return []
        return [line.strip() for line in result.output.splitlines() if line.strip()]

    def remove_tracked_file(self, file_path):
        return self._run(["rm", "-f", "--", file_path])

    def remote_file_hashes(self, branch):
        result = self._run(["ls-tree", "-r", "--format=%(objectname)%x09%(path)", f"origin/{branch}"])
        if not result.success:
            return {}, result
        files = {}
        for line in result.output.splitlines():
            if "\t" not in line:
                continue
            object_hash, path = line.split("\t", 1)
            if object_hash and path:
                files[path] = object_hash
        return files, result

    def remote_contains_folder(self, branch, folder_path):
        folder_path = folder_path.replace("\\", "/").strip("/")
        if not folder_path:
            return False, GitResult(True, "")
        remote_files, result = self.remote_file_hashes(branch)
        if not result.success:
            return False, result
        prefix = folder_path + "/"
        return any(path == folder_path or path.startswith(prefix) for path in remote_files), result

    def local_file_hash(self, file_path):
        return self._run(["hash-object", "--", file_path])

    def collision_safe_reset(self, branch):
        remote_files, result = self.remote_file_hashes(branch)
        if not result.success:
            return GitResult(False, result.output, result.friendly), []

        backups = []
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        recovery_root = support_path(self.repo_path, "recovery", stamp)
        repo_root = norm_path(self.repo_path)
        for rel_path, remote_hash in remote_files.items():
            local_path = os.path.abspath(os.path.join(self.repo_path, rel_path))
            if not norm_path(local_path).startswith(repo_root + os.sep):
                continue
            if not os.path.exists(local_path):
                continue

            if os.path.isfile(local_path):
                local_hash = self.local_file_hash(rel_path)
                if local_hash.success and local_hash.output.strip() == remote_hash:
                    os.remove(local_path)
                    continue

            backup_path = os.path.join(recovery_root, rel_path)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            if os.path.exists(backup_path):
                backup_path += ".local"
            os.replace(local_path, backup_path)
            saved_as = os.path.relpath(backup_path, self.repo_path)
            backups.append(saved_as)
            append_support_log(self.repo_path, "local_file_preserved", file=rel_path, recovery_copy=saved_as)

        helper_files = {"git_helper_v5.py", "Open Git Helper v5.cmd"}
        for current_root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [name for name in dirs if name not in {".git", SUPPORT_DIR}]
            for filename in files:
                local_path = os.path.join(current_root, filename)
                rel_path = os.path.relpath(local_path, self.repo_path).replace("\\", "/")
                if rel_path in remote_files or rel_path in helper_files:
                    continue
                backup_path = os.path.join(recovery_root, "old-local-extras", rel_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                os.replace(local_path, backup_path)
                saved_as = os.path.relpath(backup_path, self.repo_path)
                backups.append(saved_as)
                append_support_log(self.repo_path, "old_extra_preserved", file=rel_path, recovery_copy=saved_as)

        reset = self._run(["reset", "--hard", f"origin/{branch}"], timeout=60)
        if not reset.success:
            return reset, backups
        upstream = self._run(["branch", "--set-upstream-to", f"origin/{branch}", branch])
        return upstream if not upstream.success else reset, backups

    def ensure_gitignore_hygiene(self):
        gitignore_path = os.path.join(self.repo_path, ".gitignore")
        existing = []
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8", errors="replace") as fh:
                existing = [line.rstrip("\n") for line in fh]

        normalized = {line.strip() for line in existing}
        missing = [line for line in GITIGNORE_LINES if line not in normalized]
        if missing:
            with open(gitignore_path, "a", encoding="utf-8", newline="\n") as fh:
                if existing and existing[-1].strip():
                    fh.write("\n")
                for line in missing:
                    fh.write(line + "\n")

        self._run(["rm", "-r", "--cached", "--ignore-unmatch", "__pycache__"])
        if os.path.exists(gitignore_path):
            self.stage_files([".gitignore"])
        return GitResult(True, "Checked .gitignore.")

    def commit_staged_if_needed(self, message):
        diff = self._run(["diff", "--cached", "--quiet"])
        if diff.success:
            return GitResult(True, "No staged changes to save.")
        committed = self.commit(message)
        if committed.success:
            return committed
        if "nothing to commit" in committed.output.lower():
            return GitResult(True, committed.output, "No staged changes to save.")
        return committed


class DiffDialog(QDialog):
    def __init__(self, filename, diff_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Diff: {filename}")
        self.resize(780, 540)
        layout = QVBoxLayout(self)
        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Consolas", 10))
        text_edit.setPlainText(diff_text)
        layout.addWidget(text_edit)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        layout.addWidget(close)


class RestoreDialog(QDialog):
    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Go Back to a Version")
        self.resize(520, 160)
        self.scope = "whole"
        self.file_path = ""

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Whole project", "One file"])
        self.file_combo = QComboBox()
        self.file_combo.addItems(files)
        self.file_combo.setEnabled(False)
        self.scope_combo.currentIndexChanged.connect(
            lambda idx: self.file_combo.setEnabled(idx == 1)
        )
        form.addRow("Restore:", self.scope_combo)
        form.addRow("File:", self.file_combo)
        layout.addLayout(form)

        row = QHBoxLayout()
        ok = QPushButton("Continue")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(ok)
        row.addWidget(cancel)
        layout.addLayout(row)

    def accept(self):
        self.scope = "file" if self.scope_combo.currentIndex() == 1 else "whole"
        self.file_path = self.file_combo.currentText()
        super().accept()


class IdentityDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tell Git Who You Are")
        self.resize(430, 150)
        layout = QVBoxLayout(self)
        label = QLabel("Git needs your name and email once before it can save changes.")
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)
        form.addRow("Email:", self.email_edit)
        layout.addLayout(form)
        row = QHBoxLayout()
        ok = QPushButton("Save")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(ok)
        row.addWidget(cancel)
        layout.addLayout(row)

    def values(self):
        return self.name_edit.text().strip(), self.email_edit.text().strip()


class SetupWizardDialog(QDialog):
    def __init__(self, need_identity=False, parent=None):
        super().__init__(parent)
        self.need_identity = need_identity
        self.setWindowTitle("Set Up GitHub")
        self.resize(520, 220 if need_identity else 150)

        layout = QVBoxLayout(self)
        label = QLabel("Connect this folder to GitHub and download the project files.")
        label.setWordWrap(True)
        layout.addWidget(label)

        form = QFormLayout()
        self.url_edit = QLineEdit(DEFAULT_REMOTE_URL)
        form.addRow("GitHub URL:", self.url_edit)
        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        if need_identity:
            form.addRow("Name:", self.name_edit)
            form.addRow("Email:", self.email_edit)
        layout.addLayout(form)

        row = QHBoxLayout()
        setup = QPushButton("Set Up")
        cancel = QPushButton("Cancel")
        setup.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(setup)
        row.addWidget(cancel)
        layout.addLayout(row)

    def values(self):
        return (
            self.url_edit.text().strip(),
            self.name_edit.text().strip(),
            self.email_edit.text().strip(),
        )


class GitTaskWorker(QObject):
    progress = pyqtSignal(str)
    details = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, task_fn):
        super().__init__()
        self.task_fn = task_fn

    def run(self):
        try:
            result = self.task_fn(self.progress.emit, self.details.emit)
        except Exception as exc:
            details = traceback.format_exc()
            result = {
                "success": False,
                "message": "Git Helper hit an internal problem. It was recorded in the support log.",
                "details": details,
            }
        self.finished.emit(result)


class GitHelperWindow(QMainWindow):
    task_result_ready = pyqtSignal(dict)
    worker_cleanup_ready = pyqtSignal()

    def __init__(self, repo_path, startup_notes=None):
        super().__init__()
        self.repo_path = repo_path
        self.git = GitRunner(repo_path)
        self.onedrive_warning_dismissed = False
        self.worker_thread = None
        self.worker = None
        self.pending_finished_fn = None
        self.worker_disable_sync = True
        self.last_sync_success = False
        self.setWindowTitle(f"{APP_DISPLAY_NAME} - {os.path.basename(repo_path)}")
        self.resize(1120, 760)
        self.task_result_ready.connect(
            self._handle_task_result,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker_cleanup_ready.connect(
            self._clear_worker,
            Qt.ConnectionType.QueuedConnection,
        )
        self._build_ui()
        self.auto_sync_timer = QTimer(self)
        self.auto_sync_timer.timeout.connect(self.do_sync)
        self.auto_sync_check.toggled.connect(self._update_auto_sync)
        self.auto_sync_minutes.valueChanged.connect(self._update_auto_sync)
        self._update_auto_sync()
        append_support_log(self.repo_path, "app_started", folder=self.repo_path)
        if startup_notes:
            self.write_details("Startup checks:\n" + "\n".join(startup_notes))
        self.refresh_status()
        if is_cloud_path(self.repo_path) and not self.onedrive_warning_dismissed:
            self.show_cloud_warning()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        top_bar = QHBoxLayout()
        self.status_label = QLabel("Status: Checking...")
        self.status_label.setFont(QFont("Segoe UI", 12, weight=QFont.Weight.Bold))
        self.branch_label = QLabel("Branch: ...")
        self.cloud_label = QLabel("")
        self.cloud_label.setStyleSheet("color: #8a5a00; font-weight: bold;")
        self.version_label = QLabel(APP_DISPLAY_NAME)
        self.version_label.setStyleSheet("color: #666; font-size: 9pt;")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.do_refresh)
        top_bar.addWidget(self.status_label, stretch=2)
        top_bar.addWidget(self.branch_label)
        top_bar.addWidget(self.cloud_label)
        top_bar.addWidget(self.version_label)
        top_bar.addStretch()
        top_bar.addWidget(refresh)
        main_layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)

        sync_group = QGroupBox("Daily Workflow")
        sync_layout = QVBoxLayout(sync_group)
        self.commit_msg = QLineEdit()
        self.commit_msg.setPlaceholderText("Optional note, such as 'updated schedule'")
        sync_layout.addWidget(self.commit_msg)
        self.btn_sync = QPushButton("Sync")
        self.btn_sync.setMinimumHeight(46)
        self.btn_sync.setStyleSheet("font-size: 14pt; font-weight: bold; background: #e9f7ef;")
        self.btn_sync.clicked.connect(self.do_sync)
        sync_layout.addWidget(self.btn_sync)
        automation_row = QHBoxLayout()
        self.auto_sync_check = QCheckBox("Auto Sync")
        self.auto_sync_check.setChecked(True)
        self.auto_sync_minutes = QSpinBox()
        self.auto_sync_minutes.setRange(2, 240)
        self.auto_sync_minutes.setValue(15)
        self.auto_sync_minutes.setSuffix(" min")
        automation_row.addWidget(self.auto_sync_check)
        automation_row.addWidget(self.auto_sync_minutes)
        automation_row.addStretch()
        sync_layout.addLayout(automation_row)

        revision_row = QHBoxLayout()
        self.btn_rev_up = QPushButton("Rev Up")
        self.btn_download_rev = QPushButton("Download New Rev")
        self.btn_rev_up.clicked.connect(self.do_rev_up)
        self.btn_download_rev.clicked.connect(self.do_download_new_rev)
        revision_row.addWidget(self.btn_rev_up)
        revision_row.addWidget(self.btn_download_rev)
        sync_layout.addLayout(revision_row)
        self.progress_pane = QPlainTextEdit()
        self.progress_pane.setReadOnly(True)
        self.progress_pane.setMaximumHeight(130)
        self.progress_pane.setFont(QFont("Segoe UI", 9))
        sync_layout.addWidget(self.progress_pane)

        self.file_list = QTreeWidget()
        self.file_list.setHeaderLabels(["Status", "File"])
        self.file_list.setColumnWidth(0, 110)
        self.file_list.setRootIsDecorated(False)
        self.file_list.setFont(QFont("Segoe UI", 9))
        sync_layout.addWidget(self.file_list)
        left_layout.addWidget(sync_group)

        restore_group = QGroupBox("Restore Points")
        restore_layout = QVBoxLayout(restore_group)
        self.restore_list = QTreeWidget()
        self.restore_list.setHeaderLabels(["Date / Time", "Note", "Details"])
        self.restore_list.setColumnWidth(0, 180)
        self.restore_list.setColumnWidth(1, 220)
        self.restore_list.setRootIsDecorated(False)
        restore_layout.addWidget(self.restore_list)
        restore_row = QHBoxLayout()
        snapshot = QPushButton("Snapshot Now")
        restore = QPushButton("Go Back")
        snapshot.clicked.connect(self.do_snapshot)
        restore.clicked.connect(self.do_restore)
        restore_row.addWidget(snapshot)
        restore_row.addWidget(restore)
        restore_layout.addLayout(restore_row)
        left_layout.addWidget(restore_group)

        self.btn_show_advanced = QPushButton("Show Advanced Options...")
        self.btn_show_advanced.clicked.connect(self._toggle_advanced)
        left_layout.addWidget(self.btn_show_advanced)
        self.grp_advanced = QGroupBox("Advanced")
        adv = QVBoxLayout(self.grp_advanced)
        row1 = QHBoxLayout()
        for text, slot in [
            ("Pull", self.do_pull),
            ("Stage All", self.do_stage_all),
            ("Commit", self.do_commit),
            ("Push", self.do_push),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row1.addWidget(btn)
        adv.addLayout(row1)
        row2 = QHBoxLayout()
        for text, slot in [
            ("Stage Selected", self.do_stage_selected),
            ("Unstage", self.do_unstage_selected),
            ("Diff", self.do_diff_selected),
            ("Log", self.do_view_log),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row2.addWidget(btn)
        adv.addLayout(row2)
        row3 = QHBoxLayout()
        for text, slot in [
            ("Stash", self.do_stash_save),
            ("Pop Stash", self.do_stash_pop),
            ("Create Tag", self.do_create_tag),
            ("Push Tags", self.do_push_tags),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row3.addWidget(btn)
        adv.addLayout(row3)
        self.grp_advanced.setVisible(False)
        left_layout.addWidget(self.grp_advanced)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        instructions_box = QTextEdit()
        instructions_box.setReadOnly(True)
        instructions_box.setFont(QFont("Consolas", 9))
        instructions_box.setPlainText(INSTRUCTIONS)
        instructions_box.setMaximumHeight(230)
        instructions_box.setStyleSheet("background-color: #fffff0; border: 1px solid #ddd; padding: 8px;")
        right_layout.addWidget(instructions_box)
        details_label = QLabel("Details:")
        details_label.setFont(QFont("Segoe UI", 9, weight=QFont.Weight.Bold))
        details_row = QHBoxLayout()
        details_row.addWidget(details_label)
        details_row.addStretch()
        open_support = QPushButton("Open Support Folder")
        open_support.clicked.connect(self.open_support_folder)
        details_row.addWidget(open_support)
        collect_support = QPushButton("Collect All Logs Here")
        collect_support.clicked.connect(self.collect_all_logs_here)
        details_row.addWidget(collect_support)
        right_layout.addLayout(details_row)
        self.output_pane = QPlainTextEdit()
        self.output_pane.setReadOnly(True)
        self.output_pane.setFont(QFont("Consolas", 9))
        right_layout.addWidget(self.output_pane)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([540, 560])
        self.statusBar().showMessage(f"Repo: {self.repo_path}")
        self.setStyleSheet(
            """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 16px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #bbb;
                border-radius: 3px;
                background: #f5f5f5;
            }
            QPushButton:hover { background: #e7e7e7; }
            QPushButton:pressed { background: #d4d4d4; }
            QPushButton:disabled { color: #aaa; }
            """
        )

    def _toggle_advanced(self):
        visible = not self.grp_advanced.isVisible()
        self.grp_advanced.setVisible(visible)
        self.btn_show_advanced.setText("Hide Advanced Options" if visible else "Show Advanced Options...")

    def write_progress(self, message):
        self.progress_pane.appendPlainText(message)
        QApplication.processEvents()

    def write_details(self, message):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        message = message if str(message or "").strip() else "(no output)"
        self.output_pane.appendPlainText(f"\n[{ts}] {message}")
        append_support_log(self.repo_path, "app_message", message=str(message))
        QApplication.processEvents()

    def _update_auto_sync(self):
        if not hasattr(self, "auto_sync_timer"):
            return
        self.auto_sync_timer.stop()
        if self.auto_sync_check.isChecked():
            self.auto_sync_timer.start(self.auto_sync_minutes.value() * 60 * 1000)
            self.statusBar().showMessage(f"Auto Sync every {self.auto_sync_minutes.value()} minutes", 3000)

    def open_support_folder(self):
        folder = support_path(self.repo_path)
        os.makedirs(folder, exist_ok=True)
        append_support_log(self.repo_path, "support_folder_opened")
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError as exc:
            QMessageBox.warning(self, "Support Folder", f"Could not open the folder.\n\n{folder}\n\n{exc}")

    def collect_all_logs_here(self):
        try:
            destination, count = collect_support_report(self.repo_path)
            append_support_log(self.repo_path, "support_report_collected", report=destination, records=count)
            QMessageBox.information(
                self,
                "Support Report Ready",
                f"Collected {count} log records from every Git Helper v5 folder used on this computer.\n\n"
                f"The report is ready in this project folder:\n{destination}\n\n"
                "The next Sync will upload it with the project.",
            )
            self.refresh_status()
        except OSError as exc:
            QMessageBox.warning(self, "Support Report", f"The combined report could not be created.\n\n{exc}")

    def start_git_task(self, task_fn, finished_fn, disable_sync=True):
        if self.worker_thread is not None:
            self.statusBar().showMessage("Git is already working. Please wait.", 4000)
            return
        self.pending_finished_fn = finished_fn
        self.worker_disable_sync = disable_sync
        if disable_sync:
            self.btn_sync.setEnabled(False)
        self.worker_thread = QThread(self)
        self.worker = GitTaskWorker(task_fn)
        self.worker.moveToThread(self.worker_thread)
        self.worker.progress.connect(self.write_progress)
        self.worker.details.connect(self.write_details)
        self.worker.finished.connect(
            self.task_result_ready.emit,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(
            self.worker_cleanup_ready.emit,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def _handle_task_result(self, result):
        if result.get("details"):
            append_support_log(self.repo_path, "worker_exception", traceback=result["details"])
            self.write_details(result["details"])
        if self.pending_finished_fn is not None:
            self.pending_finished_fn(result)

    def _clear_worker(self):
        self.worker = None
        self.worker_thread = None
        self.pending_finished_fn = None
        if self.worker_disable_sync:
            self.btn_sync.setEnabled(True)
        self.refresh_status()

    def auto_message(self, prefix="Update"):
        note = self.commit_msg.text().strip()
        if note:
            return note
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"{prefix} {stamp}"

    def _run_and_display(self, label, fn):
        self.write_details(f">>> {label}")

        def task(progress, details):
            result = fn()
            details(result.output or "(no output)")
            return {
                "success": result.success,
                "message": result.friendly,
                "auth": (not result.success) and is_auth_error(result.output),
            }

        def finished(result):
            if result.get("auth"):
                offer_github_sign_in(self.repo_path, self)
                return
            if not result.get("success"):
                QMessageBox.warning(
                    self,
                    "Git Helper",
                    f"{result.get('message', 'Git could not finish.')}\n\nDetails are shown in the Details panel.",
                )

        self.start_git_task(task, finished, disable_sync=False)

    def _get_checked_files(self):
        files = []
        for i in range(self.file_list.topLevelItemCount()):
            item = self.file_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                files.append(item.text(1))
        return files

    def refresh_status(self):
        state = self.git.repo_state()
        self.branch_label.setText(f"Branch: {state.branch}")
        self.cloud_label.setText("In OneDrive" if is_cloud_path(self.repo_path) else "")
        self.file_list.clear()

        if state.conflicted:
            self.status_label.setText("Red: Conflict - needs your choice")
            self.status_label.setStyleSheet("color: #a40000;")
        elif state.dirty:
            self.status_label.setText(f"Yellow: You have {len(state.changed_files)} change(s) not sent yet")
            self.status_label.setStyleSheet("color: #8a6500;")
        elif state.behind:
            self.status_label.setText(f"Blue: GitHub has {state.behind} newer change(s)")
            self.status_label.setStyleSheet("color: #0059b3;")
        elif state.ahead:
            self.status_label.setText(f"Yellow: {state.ahead} saved change(s) not sent yet")
            self.status_label.setStyleSheet("color: #8a6500;")
        elif state.remote_checked and not state.remote_reachable:
            self.status_label.setText("Warning: Can't reach GitHub - showing local only")
            self.status_label.setStyleSheet("color: #8a5a00;")
        else:
            self.status_label.setText("Green: Up to date")
            self.status_label.setStyleSheet("color: #137333;")

        for code, path in state.changed_files:
            word = self._plain_status_word(code)
            item = QTreeWidgetItem([word, path])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            color = {
                "New": QColor(0, 130, 0),
                "Edited": QColor(190, 110, 0),
                "Deleted": QColor(180, 0, 0),
                "Conflict": QColor(170, 0, 170),
                "Renamed": QColor(0, 90, 170),
            }.get(word, QColor(90, 90, 90))
            item.setForeground(0, QBrush(color))
            item.setForeground(1, QBrush(color))
            self.file_list.addTopLevelItem(item)

        self.refresh_restore_points()

    def do_refresh(self):
        self.write_progress("Checking GitHub...")

        def task(progress, details):
            result = self.git.fetch()
            details(result.output or result.friendly)
            if result.success:
                progress("GitHub check finished.")
                return {"success": True, "message": "Status refreshed."}
            if is_auth_error(result.output):
                return {"success": False, "auth": True, "message": result.friendly}
            progress("Can't reach GitHub right now. Showing local status only.")
            return {"success": False, "message": result.friendly, "offline": True}

        def finished(result):
            if result.get("auth"):
                offer_github_sign_in(self.repo_path, self)
                return
            if not result.get("success") and not result.get("offline"):
                QMessageBox.warning(self, "Refresh", result.get("message", "Could not refresh."))

        self.start_git_task(task, finished, disable_sync=False)

    def _plain_status_word(self, code):
        if "U" in code or code in ("AA", "DD"):
            return "Conflict"
        if "D" in code:
            return "Deleted"
        if "A" in code or "?" in code:
            return "New"
        if "R" in code:
            return "Renamed"
        return "Edited"

    def refresh_restore_points(self):
        self.restore_list.clear()
        result = self.git.restore_points(40)
        if not result.success:
            return
        for line in result.output.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 3:
                continue
            commit_hash, date_text, subject = parts
            item = QTreeWidgetItem([date_text, subject, commit_hash[:10]])
            item.setData(0, Qt.ItemDataRole.UserRole, commit_hash)
            self.restore_list.addTopLevelItem(item)

    def do_sync(self):
        if self.worker_thread is not None:
            self.statusBar().showMessage("Git is already working. Please wait.", 4000)
            return
        self.progress_pane.clear()
        self.last_sync_success = False
        self.write_progress("Checking the project...")
        if not ensure_identity(self.git, self):
            self.write_progress("Stopped: Git still needs your name and email.")
            return
        if not self.git.has_remote():
            if not ask_for_remote(self.git, self):
                self.write_progress("Stopped: GitHub link is still missing.")
                return

        if is_cloud_path(self.repo_path) and not self.onedrive_warning_dismissed:
            self.show_cloud_warning()

        if self.git.repo_state().conflicted:
            self.handle_conflicts()
            if self.git.repo_state().conflicted:
                self.write_progress("Stopped: a conflict still needs your choice.")
                return

        commit_message = self.auto_message()

        def task(progress, details):
            progress("Checking GitHub...")
            fetched = self.git.fetch()
            details(fetched.output or fetched.friendly)
            if not fetched.success:
                if is_auth_error(fetched.output):
                    return {"success": False, "auth": True, "message": fetched.friendly}
                progress("Can't reach GitHub right now. Your local files were not changed.")
                return {"success": False, "offline": True, "message": fetched.friendly}

            state = self.git.repo_state()
            if state.conflicted:
                return {"success": False, "conflict": True, "message": "A conflict needs your choice."}

            progress("Saving your changes...")
            saved = self.git.commit_if_needed(commit_message)
            details(saved.output or saved.friendly)
            if not saved.success:
                return {"success": False, "message": saved.friendly}

            for attempt in range(3):
                progress("Getting GitHub's latest...")
                merge = self.git.merge_remote_keep_local_on_collision()
                details(merge.output or merge.friendly)
                if not merge.success:
                    text = merge.output.lower()
                    if "conflict" in text or "unmerged" in text:
                        progress("The same item changed on both computers. Keeping this computer's edit...")
                        resolved = self.git.finish_conflicts_keep_local()
                        details(resolved.output or resolved.friendly)
                        append_support_log(
                            self.repo_path,
                            "collision_resolved",
                            policy="kept current computer's version",
                            git_output=merge.output,
                        )
                        if not resolved.success:
                            return {"success": False, "message": resolved.friendly}
                        merge = resolved
                    if "would be overwritten" in text:
                        stash = self.git.stash_save()
                        details(stash.output or stash.friendly)
                        if not stash.success:
                            return {"success": False, "message": stash.friendly}
                        merge = self.git.merge_remote_keep_local_on_collision()
                        details(merge.output or merge.friendly)
                        pop = self.git.stash_pop()
                        details(pop.output or pop.friendly)
                        if not merge.success or not pop.success:
                            combined = (merge.output or "") + "\n" + (pop.output or "")
                            if "conflict" in combined.lower() or "unmerged" in combined.lower():
                                return {"success": False, "conflict": True, "message": friendly_error(combined)}
                            return {"success": False, "message": friendly_error(combined)}
                    else:
                        return {"success": False, "message": merge.friendly}

                state = self.git.repo_state()
                if state.conflicted:
                    return {"success": False, "conflict": True, "message": "A conflict needs your choice."}

                progress("Sending your work up...")
                push = self.git.push()
                details(push.output or push.friendly)
                if push.success:
                    progress("Everything is in sync.")
                    return {"success": True, "message": "Everything is in sync."}
                if is_auth_error(push.output):
                    return {"success": False, "auth": True, "message": push.friendly}
                text = push.output.lower()
                if "rejected" in text or "fetch first" in text:
                    progress("GitHub moved while we were syncing, so trying once more...")
                    fetch_again = self.git.fetch()
                    details(fetch_again.output or fetch_again.friendly)
                    if not fetch_again.success:
                        if is_auth_error(fetch_again.output):
                            return {"success": False, "auth": True, "message": fetch_again.friendly}
                        return {"success": False, "offline": True, "message": fetch_again.friendly}
                    continue
                return {"success": False, "message": push.friendly}

            return {
                "success": False,
                "message": "GitHub kept changing while Sync was running. Try Sync again in a moment.",
            }

        def finished(result):
            if result.get("success"):
                self.last_sync_success = True
                self.commit_msg.clear()
                return
            if result.get("auth"):
                if offer_github_sign_in(self.repo_path, self):
                    QTimer.singleShot(200, self.do_sync)
                return
            if result.get("conflict"):
                self.write_progress("A conflict needs your choice.")
                self.handle_conflicts()
                if not self.git.repo_state().conflicted:
                    self.write_progress("Conflict choices saved. Finishing Sync...")
                    QTimer.singleShot(200, self.do_sync)
                return
            if result.get("offline"):
                QMessageBox.warning(self, "Sync", result.get("message", "Can't reach GitHub right now."))
                return
            QMessageBox.warning(self, "Sync", result.get("message", "Sync could not finish."))

        self.start_git_task(task, finished)

    def handle_conflicts(self):
        files, _ = self.git.changed_files()
        conflict_files = [path for code, path in files if "U" in code or code in ("AA", "DD")]
        if not conflict_files:
            return
        for path in conflict_files:
            while True:
                has_mine, has_github = self.git.conflict_sides(path)
                box = QMessageBox(self)
                box.setWindowTitle("Choose a Version")
                if not has_mine or not has_github:
                    box.setText(
                        f"This file was deleted in one place and edited in another:\n\n{path}\n\n"
                        "Choose whether to keep the file or keep it deleted."
                    )
                    mine_text = "Keep Deleted" if not has_mine else "Keep Mine"
                    github_text = "Keep Deleted" if not has_github else "Keep GitHub's"
                else:
                    box.setText(
                        f"The same file changed in two places:\n\n{path}\n\n"
                        "Choose which version to keep. You can also look at the differences first."
                    )
                    mine_text = "Keep Mine"
                    github_text = "Keep GitHub's"
                keep_mine = box.addButton(mine_text, QMessageBox.ButtonRole.AcceptRole)
                keep_github = box.addButton(github_text, QMessageBox.ButtonRole.DestructiveRole)
                look = box.addButton("Let Me Look", QMessageBox.ButtonRole.HelpRole)
                stop = box.addButton("Stop", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                clicked = box.clickedButton()
                if clicked == look:
                    diff = self.git.diff_file(path)
                    DiffDialog(path, diff.output or "(No differences to show.)", self).exec()
                    continue
                if clicked == stop:
                    return
                if clicked == keep_mine:
                    result = self.git.checkout_ours(path) if has_mine else self.git.remove_file(path)
                elif clicked == keep_github:
                    result = self.git.checkout_theirs(path) if has_github else self.git.remove_file(path)
                else:
                    return
                break
            self.write_details(result.output or result.friendly)
            if not result.success:
                QMessageBox.warning(self, "Conflict", result.friendly)
                return
            staged = self.git.stage_files([path])
            self.write_details(staged.output or staged.friendly)
            if not staged.success:
                return
        finish = self.git.commit("Finish combining GitHub changes")
        self.write_details(finish.output or finish.friendly)

    def show_cloud_warning(self):
        self.onedrive_warning_dismissed = True
        result = protect_git_folder(self.repo_path)
        if result.success:
            self.write_details("OneDrive detected. Git Helper automatically asked Windows to keep the hidden .git folder on this device.")
        else:
            self.write_details(result.output or result.friendly)

    def do_snapshot(self):
        if self.git.has_unresolved_conflicts():
            QMessageBox.warning(self, "Snapshot Now", "Finish the current Sync first, then make a snapshot.")
            return
        name, ok = QInputDialog.getText(self, "Snapshot Now", "Name this restore point:")
        if not ok or not name.strip():
            return
        message = f"Snapshot: {name.strip()}"
        commit = self.git.commit_if_needed(message)
        self.write_details(commit.output or commit.friendly)
        safe_tag = "snapshot-" + re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-")
        tag = self.git.create_tag(safe_tag, name.strip())
        self.write_details(tag.output or tag.friendly)
        if commit.success and tag.success:
            self.write_progress("Snapshot saved.")
        self.refresh_status()

    def do_rev_up(self):
        if self.worker_thread is not None:
            self.statusBar().showMessage("Git is already working. Please wait.", 4000)
            return
        self.progress_pane.clear()
        self.write_progress("Syncing before creating the revision...")

        def after_sync():
            if self.worker_thread is not None:
                QTimer.singleShot(250, after_sync)
                return
            if not self.last_sync_success:
                self.write_progress("Revision was not created because Sync did not finish.")
                return

            def task(progress, details):
                progress("Creating the next numbered revision...")
                result, tag = self.git.create_revision()
                details(result.output or result.friendly)
                return {"success": result.success, "message": result.friendly, "tag": tag}

            def finished(result):
                if result.get("success"):
                    tag = result.get("tag")
                    self.write_progress(f"Revision {tag} is saved locally and on GitHub.")
                    append_support_log(self.repo_path, "revision_created", revision=tag)
                else:
                    QMessageBox.warning(self, "Rev Up", result.get("message") or "The revision could not be created.")

            self.start_git_task(task, finished)

        self.do_sync()
        QTimer.singleShot(250, after_sync)

    def do_download_new_rev(self):
        remote = self.git.remote_url()
        if not remote:
            QMessageBox.warning(self, "Download New Rev", "This folder is not connected to GitHub yet.")
            return
        parent = os.path.dirname(self.repo_path)
        base = re.sub(r"-rev-\d+$", "", os.path.basename(self.repo_path), flags=re.IGNORECASE)
        existing = []
        for name in os.listdir(parent):
            match = re.fullmatch(re.escape(base) + r"-rev-(\d+)", name, flags=re.IGNORECASE)
            if match:
                existing.append(int(match.group(1)))
        number = max(existing, default=0) + 1
        target = os.path.join(parent, f"{base}-rev-{number:04d}")

        def task(progress, details):
            progress(f"Downloading a clean copy into {os.path.basename(target)}...")
            result = subprocess.run(
                ["git", "clone", "--origin", "origin", remote, target],
                cwd=parent,
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            append_support_log(self.repo_path, "revision_download", target=target, success=result.returncode == 0, output=output)
            details(output)
            if result.returncode != 0:
                return {"success": False, "message": friendly_error(output)}
            source_script = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
            source_name = "Git Helper v5.exe" if getattr(sys, "frozen", False) else "git_helper_v5.py"
            source_cmd = os.path.join(os.path.dirname(source_script), "Open Git Helper v5.cmd")
            shutil.copy2(source_script, os.path.join(target, source_name))
            if os.path.isfile(source_cmd):
                shutil.copy2(source_cmd, os.path.join(target, "Open Git Helper v5.cmd"))
            return {"success": True, "target": target}

        def finished(result):
            if result.get("success"):
                self.write_progress(f"Clean revision folder created: {result['target']}")
                QMessageBox.information(self, "Download New Rev", f"Your clean new folder is ready:\n{result['target']}")
            else:
                QMessageBox.warning(self, "Download New Rev", result.get("message") or "Download failed. See the support log.")

        self.start_git_task(task, finished)

    def do_restore(self):
        if self.git.has_unresolved_conflicts():
            QMessageBox.warning(self, "Go Back", "Finish the current Sync first, then restore a version.")
            return
        item = self.restore_list.currentItem()
        if not item:
            QMessageBox.information(self, "Go Back", "Choose a restore point first.")
            return
        commit_hash = item.data(0, Qt.ItemDataRole.UserRole)
        files = self.git.tracked_files(commit_hash)
        dlg = RestoreDialog(files, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        scope_text = "the whole project" if dlg.scope == "whole" else dlg.file_path
        confirm = QMessageBox.question(
            self,
            "Confirm Restore",
            f"This will bring back {scope_text} from:\n{item.text(0)}\n\n"
            "It will save that as a new change. Your current version stays in history. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if self.git.dirty():
            saved = self.git.commit_if_needed(f"Save current work before restore {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
            self.write_details(saved.output or saved.friendly)
            if not saved.success:
                QMessageBox.warning(self, "Go Back", "Your current edits could not be saved first. Restore was stopped.")
                self.refresh_status()
                return

        if dlg.scope == "file":
            result = self.git.checkout_file_from_commit(commit_hash, dlg.file_path)
            self.write_details(result.output or result.friendly)
        else:
            result = self.restore_whole_project(commit_hash)
        if not result.success:
            QMessageBox.warning(self, "Go Back", result.friendly)
            self.refresh_status()
            return
        commit = self.git.commit_if_needed(f"Restore version from {item.text(0)}")
        self.write_details(commit.output or commit.friendly)
        if commit.success:
            QMessageBox.information(self, "Go Back", "That version has been brought back safely as a new change.")
        self.refresh_status()

    def restore_whole_project(self, commit_hash):
        old_files = set(self.git.tracked_files(commit_hash))
        current_files = set(self.git.tracked_files("HEAD"))
        result = self.git._run(["checkout", commit_hash, "--", "."])
        self.write_details(result.output or result.friendly)
        if not result.success:
            return result
        for file_path in sorted(current_files - old_files):
            removed = self.git.remove_tracked_file(file_path)
            self.write_details(removed.output or removed.friendly)
            if not removed.success:
                return removed
        return self.git.stage_all()

    def do_pull(self):
        self._run_and_display("pull", self.git.pull_no_edit)

    def do_push(self):
        self._run_and_display("push", self.git.push)

    def do_stage_all(self):
        self._run_and_display("add all changes", self.git.stage_all)

    def do_commit(self):
        message = self.auto_message()
        self._run_and_display("commit", lambda: self.git.commit_if_needed(message))
        self.commit_msg.clear()

    def do_stage_selected(self):
        files = self._get_checked_files()
        if not files:
            self.statusBar().showMessage("No files selected", 3000)
            return
        self._run_and_display("stage selected", lambda: self.git.stage_files(files))

    def do_unstage_selected(self):
        files = self._get_checked_files()
        if not files:
            self.statusBar().showMessage("No files selected", 3000)
            return
        self._run_and_display("unstage selected", lambda: self.git.unstage_files(files))

    def do_view_log(self):
        self._run_and_display("show recent restore points", lambda: self.git.log(20))

    def do_diff_selected(self):
        files = self._get_checked_files()
        if not files:
            QMessageBox.information(self, "Diff", "Choose a file first.")
            return
        for file_path in files:
            diff = self.git.diff_file(file_path)
            if not diff.output.strip():
                diff = self.git.diff_staged_file(file_path)
            DiffDialog(file_path, diff.output or "(No changes to show.)", self).exec()

    def do_stash_save(self):
        msg, ok = QInputDialog.getText(self, "Stash", "Temporary save note:")
        if ok:
            self._run_and_display("temporary save", lambda: self.git.stash_save(msg or "Temporary save"))

    def do_stash_pop(self):
        self._run_and_display("restore temporary save", self.git.stash_pop)

    def do_create_tag(self):
        tag_name, ok = QInputDialog.getText(self, "Create Tag", "Tag name:")
        if not ok or not tag_name.strip():
            return
        tag_msg, ok2 = QInputDialog.getText(self, "Tag Message", "Tag message:")
        if ok2:
            self._run_and_display("create tag", lambda: self.git.create_tag(tag_name.strip(), tag_msg))

    def do_push_tags(self):
        self._run_and_display("push tags", self.git.push_tags)


def is_cloud_path(path):
    resolved = os.path.normcase(os.path.abspath(path))
    env_keys = [
        "OneDrive",
        "OneDriveConsumer",
        "OneDriveCommercial",
        "DROPBOX",
        "GOOGLE_DRIVE",
    ]
    roots = [os.environ.get(key) for key in env_keys if os.environ.get(key)]
    home = os.path.expanduser("~")
    roots += [
        os.path.join(home, "OneDrive"),
        os.path.join(home, "Dropbox"),
        os.path.join(home, "Google Drive"),
        os.path.join(home, "My Drive"),
    ]
    return any(resolved.startswith(os.path.normcase(os.path.abspath(root))) for root in roots if root)


def protect_git_folder(repo_path):
    git_folder = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_folder):
        return GitResult(True, "No .git folder found to protect.")
    if sys.platform != "win32":
        return GitResult(True, "Cloud protection is only needed on Windows in this helper.")
    try:
        kwargs = {
            "cwd": repo_path,
            "capture_output": True,
            "text": True,
            "timeout": 30,
        }
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(["attrib", "+P", "-U", ".git", "/S", "/D"], **kwargs)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode == 0:
            return GitResult(True, output or "Asked Windows to keep the .git folder on this device.")
        return GitResult(False, output, "Windows could not change the OneDrive setting for the .git folder.")
    except subprocess.TimeoutExpired:
        return GitResult(False, "attrib timed out.", "Windows took too long changing the OneDrive setting.")
    except FileNotFoundError:
        return GitResult(False, "attrib was not found.", "Windows could not find the tool used for OneDrive protection.")


def identity_configured(runner):
    local_name = runner.config_get("user.name")
    local_email = runner.config_get("user.email")
    global_name = runner.config_get("user.name", global_scope=True)
    global_email = runner.config_get("user.email", global_scope=True)
    has_local_identity = local_name.success and local_name.output.strip() and local_email.success and local_email.output.strip()
    has_global_identity = global_name.success and global_name.output.strip() and global_email.success and global_email.output.strip()
    return bool(has_local_identity or has_global_identity)


def ensure_identity(runner, parent=None, notes=None):
    if identity_configured(runner):
        return True
    dlg = IdentityDialog(parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    user_name, user_email = dlg.values()
    if not user_name or not user_email:
        QMessageBox.warning(parent, "Identity Needed", "Please enter both a name and an email.")
        return False
    set_name = runner.config_set("user.name", user_name, global_scope=True)
    set_email = runner.config_set("user.email", user_email, global_scope=True)
    if notes is not None:
        notes.append("Saved your Git name and email.")
    return set_name.success and set_email.success


def launch_github_sign_in(repo_path):
    try:
        flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        subprocess.Popen(
            ["cmd", "/k", "git", "fetch", "origin"] if sys.platform == "win32" else ["git", "fetch", "origin"],
            cwd=repo_path,
            creationflags=flags,
        )
        return True
    except (OSError, FileNotFoundError):
        return False


def offer_github_sign_in(repo_path, parent=None):
    box = QMessageBox(parent)
    box.setWindowTitle("GitHub Sign In")
    box.setText(
        "GitHub needs you to sign in once on this computer.\n\n"
        "A black window will open. Follow the sign-in steps in your browser, then come back here."
    )
    sign_in = box.addButton("Sign in now", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() != sign_in:
        return False
    if not launch_github_sign_in(repo_path):
        QMessageBox.warning(parent, "GitHub Sign In", "Could not open the Git sign-in window.")
        return False
    QMessageBox.information(
        parent,
        "GitHub Sign In",
        "Finish the browser sign-in, close the black window if it stays open, then click OK to try again.",
    )
    return True


def ask_for_remote(runner, parent=None):
    url, ok = QInputDialog.getText(
        parent,
        "GitHub Link Needed",
        "Paste the GitHub repo link for this project:",
    )
    if not ok or not url.strip():
        return False
    result = runner.add_or_set_origin(url.strip())
    if not result.success:
        QMessageBox.warning(parent, "GitHub Link", result.friendly)
        return False
    return True


def setup_repo(target_folder, parent=None):
    runner = GitRunner(target_folder)
    notes = []
    parent_repo = ""
    parent_relative_path = ""
    if runner.is_git_repo() and not runner.is_own_repo():
        parent_repo = runner.repo_toplevel()
        if parent_repo:
            parent_relative_path = os.path.relpath(target_folder, parent_repo)

    need_identity = not identity_configured(runner)
    dlg = SetupWizardDialog(need_identity=need_identity, parent=parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return "", notes

    url, user_name, user_email = dlg.values()
    if not url:
        QMessageBox.warning(parent, "Set Up GitHub", "Please paste the GitHub repo link.")
        return "", notes
    if need_identity:
        if not user_name or not user_email:
            QMessageBox.warning(parent, "Set Up GitHub", "Please enter both a name and an email.")
            return "", notes
        runner.config_set("user.name", user_name, global_scope=True)
        runner.config_set("user.email", user_email, global_scope=True)
        notes.append("Saved your Git name and email.")

    init = runner.init()
    notes.append(init.output or "Created a Git repository.")
    if not init.success:
        QMessageBox.warning(parent, "Set Up GitHub", init.friendly)
        return "", notes

    remote = runner.add_or_set_origin(url)
    notes.append(remote.output or "Connected this folder to GitHub.")
    if not remote.success:
        QMessageBox.warning(parent, "Set Up GitHub", remote.friendly)
        return "", notes

    runner.ensure_credential_helper()
    fetch = runner.fetch()
    if not fetch.success and is_auth_error(fetch.output):
        if offer_github_sign_in(target_folder, parent):
            fetch = runner.fetch()
    notes.append(fetch.output or "Checked GitHub for existing files.")
    if not fetch.success:
        QMessageBox.warning(parent, "Set Up GitHub", fetch.friendly)
        return "", notes

    remote_has_work, remote_check = runner.remote_has_branches()
    notes.append(remote_check.output or "Checked whether the GitHub repository already has files.")
    if not remote_check.success:
        QMessageBox.warning(parent, "Set Up GitHub", remote_check.friendly)
        return "", notes

    if not remote_has_work:
        branch = "main"
        checkout = runner.checkout_new_branch(branch)
        notes.append(checkout.output or "Created the first main branch.")
        if not checkout.success:
            QMessageBox.warning(parent, "Set Up GitHub", checkout.friendly)
            return "", notes
        runner.ensure_gitignore_hygiene()
        first_commit = runner.commit_if_needed("First upload")
        notes.append(first_commit.output or first_commit.friendly)
        if not first_commit.success:
            QMessageBox.warning(parent, "Set Up GitHub", first_commit.friendly)
            return target_folder, notes
        push = runner.push()
        if not push.success and is_auth_error(push.output):
            if offer_github_sign_in(target_folder, parent):
                push = runner.push()
        notes.append(push.output or push.friendly)
        if not push.success:
            QMessageBox.warning(parent, "Set Up GitHub", push.friendly)
            return target_folder, notes
        append_support_log(target_folder, "empty_repository_first_upload", branch=branch)
        QMessageBox.information(
            parent,
            "First Upload Complete",
            f"GitHub was empty, so Git Helper uploaded this folder as its first version on {branch}.",
        )
        return target_folder, notes

    branch = runner.default_remote_branch()
    checkout = runner.checkout_new_branch(branch)
    notes.append(checkout.output or f"Using GitHub branch {branch}.")
    if not checkout.success:
        QMessageBox.warning(parent, "Set Up GitHub", checkout.friendly)
        return "", notes

    if parent_repo and parent_relative_path:
        contains_self, tree_result = runner.remote_contains_folder(branch, parent_relative_path)
        if not tree_result.success:
            QMessageBox.warning(parent, "Set Up GitHub", tree_result.friendly)
            return "", notes
        if contains_self:
            QMessageBox.warning(
                parent,
                "Set Up GitHub",
                "This GitHub repo already contains this folder as a subfolder.\n\n"
                "Setup stopped so the repo would not be downloaded into itself. Open Git Helper from the parent project folder instead.",
            )
            return "", notes

    reset, backups = runner.collision_safe_reset(branch)
    notes.append(reset.output or reset.friendly)
    if not reset.success:
        QMessageBox.warning(parent, "Set Up GitHub", reset.friendly)
        return "", notes

    runner.ensure_gitignore_hygiene()
    hygiene_commit = runner.commit_staged_if_needed("Add .gitignore")
    notes.append(hygiene_commit.output or hygiene_commit.friendly)

    extra_commit = runner.commit_if_needed(f"Add {APP_DISPLAY_NAME}")
    notes.append(extra_commit.output or extra_commit.friendly)
    if not extra_commit.success:
        QMessageBox.warning(parent, "Set Up GitHub", extra_commit.friendly)
        return target_folder, notes

    push = runner.push()
    if not push.success and is_auth_error(push.output):
        if offer_github_sign_in(target_folder, parent):
            push = runner.push()
    notes.append(push.output or push.friendly)
    if not push.success:
        QMessageBox.warning(parent, "Set Up GitHub", push.friendly)
        return target_folder, notes

    summary = f"Downloaded {len(runner.tracked_files('HEAD'))} files from GitHub."
    if backups:
        summary += f"\n\n{len(backups)} different local file(s) were preserved in .git-helper\\recovery."
    if extra_commit.output and "No local changes" not in extra_commit.output:
        summary += "\n\nYour extra local files were sent up to GitHub."
    QMessageBox.information(parent, "Setup Complete", summary)
    return target_folder, notes


def detect_or_setup_repo(parent=None):
    target_folder = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
    runner = GitRunner(target_folder)
    if not runner.git_installed():
        QMessageBox.critical(
            parent,
            "Git Missing",
            "Git is not installed. Install Git for Windows from https://git-scm.com/download/win, then reopen this app.",
        )
        return "", []

    candidates = [target_folder]

    startup_notes = []
    for path in candidates:
        runner.repo_path = path
        if runner.is_own_repo():
            ensure_identity(runner, parent, startup_notes)
            runner.ensure_credential_helper()
            if not runner.has_remote():
                ask_for_remote(runner, parent)
            if runner.has_remote():
                fetched = runner.fetch()
                if fetched.success:
                    has_remote_work, checked = runner.remote_has_branches()
                    if checked.success and not has_remote_work:
                        branch = runner.current_branch() or "main"
                        checkout = runner.checkout_new_branch(branch)
                        if checkout.success:
                            runner.ensure_gitignore_hygiene()
                            first_commit = runner.commit_if_needed("First upload")
                            first_push = runner.push() if first_commit.success else first_commit
                            if first_push.success:
                                startup_notes.append(
                                    f"GitHub was empty. Uploaded this folder as its first version on {branch}."
                                )
                                append_support_log(path, "empty_repository_recovered", branch=branch)
                            else:
                                startup_notes.append(first_push.friendly or "The first upload could not finish.")
            runner.ensure_gitignore_hygiene()
            hygiene_commit = runner.commit_staged_if_needed("Add .gitignore")
            if hygiene_commit.success and "No staged changes" not in (hygiene_commit.output or ""):
                startup_notes.append("Updated .gitignore for local cache and backup files.")
            if is_cloud_path(path):
                startup_notes.append("This project is inside a cloud-synced folder. GitHub is the safer backup for code projects.")
            return path, startup_notes
        if runner.is_git_repo():
            startup_notes.append("Ignored the Git project above this folder. Git Helper manages only this folder and below.")
            path, notes = setup_repo(path, parent)
            startup_notes.extend(notes)
            return path, startup_notes

    result = QMessageBox.question(
        parent,
        "Set Up Project",
        f"No Git repository was found in:\n{target_folder}\n\nSet this folder up with GitHub now?",
    )
    if result != QMessageBox.StandardButton.Yes:
        return "", []
    path, notes = setup_repo(target_folder, parent)
    startup_notes.extend(notes)
    return path, startup_notes


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Text, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    repo_path, notes = detect_or_setup_repo()
    if not repo_path:
        QMessageBox.critical(None, "Git Helper", "No repository set up. Exiting.")
        sys.exit(1)

    win = GitHelperWindow(repo_path, notes)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        details = traceback.format_exc()
        startup_folder = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
        startup_log = os.path.join(startup_folder, "git-helper-v5-startup.log")
        try:
            with open(startup_log, "a", encoding="utf-8") as fh:
                fh.write(details + "\n")
        except OSError:
            pass
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "Git Helper could not open. The reason was saved here:\n\n" + startup_log + "\n\n" + details[-1200:],
                f"{APP_DISPLAY_NAME} Startup Error",
                0x10,
            )
        raise
