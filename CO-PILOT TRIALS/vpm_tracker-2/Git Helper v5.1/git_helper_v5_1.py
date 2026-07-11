import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


APP_VERSION = "v5.1"
APP_DISPLAY_NAME = f"Git Helper {APP_VERSION}"
SUPPORT_DIR = ".git-helper"
CONFIG_DIR_NAME = "Git Helper v5.1"
CONFIG_FILE_NAME = "config.json"
GLOBAL_LOG_NAME = "git-helper-v5.1-all-folders.jsonl"
PROJECT_LOG_NAME = "git-helper-v5.1.log"
SUPPORT_REPORT_NAME = "Git Helper v5.1 Support Report.jsonl"
DEFAULT_BRANCH = "main"
IGNORED_TOP_LEVEL = {".git", SUPPORT_DIR}


def now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def event_time():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def norm_path(path):
    return os.path.normcase(os.path.abspath(path))


def app_data_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, CONFIG_DIR_NAME)


def config_path():
    return os.path.join(app_data_dir(), CONFIG_FILE_NAME)


def global_log_path():
    return os.path.join(app_data_dir(), GLOBAL_LOG_NAME)


def project_log_path(destination):
    return os.path.join(destination, SUPPORT_DIR, PROJECT_LOG_NAME)


def safe_remote_for_log(url):
    return re.sub(r"(https?://)[^/@\s]+@", r"\1[credentials-hidden]@", url or "")


def append_json_line(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")


def log_event(destination, event, **data):
    record = {
        "time": event_time(),
        "version": APP_VERSION,
        "event": event,
        "destination": os.path.abspath(destination) if destination else "",
        **data,
    }
    for path in [global_log_path(), project_log_path(destination) if destination else ""]:
        if not path:
            continue
        try:
            append_json_line(path, record)
        except OSError:
            pass


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(data):
    os.makedirs(app_data_dir(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2)


def is_inside(child, parent):
    child = norm_path(child)
    parent = norm_path(parent)
    return child == parent or child.startswith(parent + os.sep)


def install_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def list_visible_entries(folder):
    if not os.path.isdir(folder):
        return []
    return [name for name in os.listdir(folder) if name not in IGNORED_TOP_LEVEL]


def folder_has_user_files(folder):
    return bool(list_visible_entries(folder))


def backup_and_clear_destination(destination, reason):
    entries = list_visible_entries(destination)
    if not entries:
        return ""
    recovery_root = os.path.join(destination, SUPPORT_DIR, "recovery", f"{now_stamp()}-{reason}")
    os.makedirs(recovery_root, exist_ok=True)
    for name in entries:
        source = os.path.join(destination, name)
        target = os.path.join(recovery_root, name)
        shutil.move(source, target)
    log_event(destination, "destination_preserved_before_download", recovery_folder=recovery_root, files=entries)
    return recovery_root


def collect_support_report(destination):
    destination = os.path.abspath(destination)
    report = os.path.join(destination, SUPPORT_REPORT_NAME)
    sources = [global_log_path(), project_log_path(destination)]
    seen = set()
    lines = []
    for source in sources:
        if not os.path.isfile(source):
            continue
        with open(source, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                clean = line.strip()
                if clean and clean not in seen:
                    seen.add(clean)
                    lines.append(clean)
    with open(report, "w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")
    return report, len(lines)


def friendly_error(output):
    text = (output or "").lower()
    if "authentication failed" in text or "could not read username" in text:
        return "GitHub needs you to sign in on this computer."
    if "repository not found" in text:
        return "GitHub could not find that repo link, or this computer does not have access to it."
    if "please tell me who you are" in text or "unable to auto-detect email" in text:
        return "Git needs your name and email once before it can save changes."
    if "would be overwritten" in text:
        return "This folder has older local files. Git Helper preserved them before downloading the GitHub copy."
    if "conflict" in text or "unmerged" in text:
        return "The same file changed in two places. Git Helper saved the details in the support log."
    if output and output.strip():
        return "Git could not finish that step. The details were saved in the support log."
    return "Git could not finish that step, and Git did not return details."


@dataclass
class GitResult:
    ok: bool
    output: str = ""
    friendly: str = ""


class GitProject:
    def __init__(self, destination, remote_url):
        self.destination = os.path.abspath(destination) if destination and destination.strip() else ""
        self.remote_url = remote_url.strip()

    def run(self, args, timeout=90):
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_MERGE_AUTOEDIT"] = "no"
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.destination,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except FileNotFoundError:
            output = "Git is not installed or is not in PATH."
            log_event(self.destination, "git_missing", command=["git"] + args)
            return GitResult(False, output, output)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            log_event(self.destination, "git_timeout", command=["git"] + args, output=output)
            return GitResult(False, output, "Git took too long and was stopped.")
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        log_event(
            self.destination,
            "git_command",
            command=["git"] + [safe_remote_for_log(a) for a in args],
            returncode=result.returncode,
            output=output[-4000:],
        )
        return GitResult(result.returncode == 0, output, "" if result.returncode == 0 else friendly_error(output))

    def ensure_valid_boundary(self):
        if not self.destination:
            return GitResult(False, "", "Choose a destination folder first.")
        os.makedirs(self.destination, exist_ok=True)
        if is_inside(install_dir(), self.destination):
            return GitResult(
                False,
                "",
                "The destination folder cannot be the Git Helper install folder or one of its parent folders.",
            )
        if not self.remote_url:
            return GitResult(False, "", "Paste the GitHub repo link first.")
        return GitResult(True)

    def ensure_identity(self):
        name = self.run(["config", "--global", "user.name"])
        email = self.run(["config", "--global", "user.email"])
        if name.ok and name.output.strip() and email.ok and email.output.strip():
            return GitResult(True)
        self.run(["config", "--global", "user.name", "Git Helper User"])
        self.run(["config", "--global", "user.email", "git-helper-user@example.com"])
        return GitResult(True, "Configured a local Git identity.")

    def ensure_repo(self):
        boundary = self.ensure_valid_boundary()
        if not boundary.ok:
            return boundary
        if not os.path.isdir(os.path.join(self.destination, ".git")):
            init = self.run(["init", "-b", DEFAULT_BRANCH])
            if not init.ok:
                init = self.run(["init"])
                if not init.ok:
                    return init
                self.run(["branch", "-M", DEFAULT_BRANCH])
            log_event(self.destination, "repo_initialized")
        self.ensure_identity()
        remote = self.run(["remote", "get-url", "origin"])
        if remote.ok:
            if remote.output.strip() != self.remote_url:
                set_url = self.run(["remote", "set-url", "origin", self.remote_url])
                if not set_url.ok:
                    return set_url
                log_event(self.destination, "remote_updated", remote=safe_remote_for_log(self.remote_url))
        else:
            add = self.run(["remote", "add", "origin", self.remote_url])
            if not add.ok:
                return add
            log_event(self.destination, "remote_added", remote=safe_remote_for_log(self.remote_url))
        return GitResult(True)

    def remote_default_branch(self):
        result = self.run(["ls-remote", "--symref", "origin", "HEAD"], timeout=45)
        if result.ok:
            for line in result.output.splitlines():
                match = re.search(r"refs/heads/([^\s]+)", line)
                if match:
                    return match.group(1)
        return DEFAULT_BRANCH

    def remote_has_files(self):
        result = self.run(["ls-remote", "--heads", "origin"], timeout=45)
        return result.ok and bool(result.output.strip())

    def has_local_commit(self):
        return self.run(["rev-parse", "--verify", "HEAD"], timeout=30).ok

    def current_branch(self):
        result = self.run(["branch", "--show-current"], timeout=30)
        return result.output.strip() if result.ok and result.output.strip() else DEFAULT_BRANCH

    def status_porcelain(self):
        result = self.run(["status", "--porcelain"], timeout=45)
        return result.output if result.ok else ""

    def dirty(self):
        return bool(self.status_porcelain().strip())

    def commit_if_needed(self, message):
        if not self.dirty():
            return GitResult(True, "No local changes to save.")
        add = self.run(["add", "-A"])
        if not add.ok:
            return add
        commit = self.run(["commit", "-m", message])
        if not commit.ok and "nothing to commit" not in commit.output.lower():
            return commit
        return GitResult(True, commit.output or "Saved local changes.")

    def checkout_remote_clean(self, branch):
        backup = ""
        if not self.has_local_commit() and folder_has_user_files(self.destination):
            backup = backup_and_clear_destination(self.destination, "before-github-download")
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        checkout = self.run(["checkout", "-B", branch, f"origin/{branch}"], timeout=120)
        if not checkout.ok:
            backup = backup or backup_and_clear_destination(self.destination, "checkout-retry")
            checkout = self.run(["checkout", "-B", branch, f"origin/{branch}"], timeout=120)
        if not checkout.ok:
            return checkout
        self.run(["branch", "--set-upstream-to", f"origin/{branch}", branch])
        message = f"Downloaded GitHub files into {self.destination}."
        if backup:
            message += f" Older local files were preserved in {backup}."
        return GitResult(True, message)

    def first_upload(self):
        self.run(["branch", "-M", DEFAULT_BRANCH])
        commit = self.commit_if_needed(f"Save local files with {APP_DISPLAY_NAME}")
        if not commit.ok:
            return commit
        push = self.run(["push", "-u", "origin", DEFAULT_BRANCH], timeout=120)
        return push if not push.ok else GitResult(True, "Uploaded this folder to GitHub.")

    def connect(self):
        setup = self.ensure_repo()
        if not setup.ok:
            return setup
        if self.remote_has_files():
            branch = self.remote_default_branch()
            if not self.has_local_commit():
                return self.checkout_remote_clean(branch)
            self.run(["fetch", "origin"], timeout=120)
            self.run(["branch", "-M", branch])
            self.run(["branch", "--set-upstream-to", f"origin/{branch}", branch])
            return GitResult(True, f"Connected to GitHub branch {branch}.")
        return self.first_upload()

    def sync(self):
        setup = self.connect()
        if not setup.ok:
            return setup
        branch = self.current_branch()
        save = self.commit_if_needed(f"Save local work {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if not save.ok:
            return save
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        if self.run(["rev-parse", "--verify", f"origin/{branch}"], timeout=30).ok:
            pull = self.run(["pull", "--no-rebase", "--no-edit", "origin", branch], timeout=120)
            if not pull.ok:
                log_event(self.destination, "sync_pull_failed", friendly=pull.friendly, output=pull.output)
                return pull
        push = self.run(["push", "-u", "origin", branch], timeout=120)
        if not push.ok:
            return push
        return GitResult(True, "Synced. GitHub and this folder are up to date.")

    def next_rev_name(self):
        tags = self.run(["tag", "--list", "rev-*"], timeout=45)
        highest = 0
        if tags.ok:
            for tag in tags.output.splitlines():
                match = re.fullmatch(r"rev-(\d+)", tag.strip())
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"rev-{highest + 1:03d}"

    def rev_up(self):
        synced = self.sync()
        if not synced.ok:
            return synced
        tag = self.next_rev_name()
        made = self.run(["tag", "-a", tag, "-m", f"{APP_DISPLAY_NAME} {tag}"], timeout=45)
        if not made.ok:
            return made
        pushed = self.run(["push", "origin", tag], timeout=120)
        if not pushed.ok:
            return pushed
        log_event(self.destination, "revision_created", revision=tag)
        return GitResult(True, f"Created and uploaded {tag}.")

    def download_new_rev(self):
        setup = self.ensure_repo()
        if not setup.ok:
            return setup
        branch = self.remote_default_branch()
        parent = os.path.dirname(self.destination)
        base = re.sub(r"-rev-\d+$", "", os.path.basename(self.destination), flags=re.IGNORECASE)
        index = 1
        while True:
            target = os.path.join(parent, f"{base}-rev-{index:03d}")
            if not os.path.exists(target):
                break
            index += 1
        result = subprocess.run(
            ["git", "clone", "--branch", branch, self.remote_url, target],
            text=True,
            capture_output=True,
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        log_event(self.destination, "download_new_rev", target=target, returncode=result.returncode, output=output[-4000:])
        if result.returncode != 0:
            return GitResult(False, output, friendly_error(output))
        return GitResult(True, f"Downloaded a clean copy here:\n{target}")


class Worker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished.emit(self.fn())
        except BaseException:
            self.finished.emit(GitResult(False, traceback.format_exc(), "Something unexpected happened. A support log was saved."))


class GitHelperWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.thread = None
        self.worker = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_now)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(860, 620)
        self.build_ui()
        self.load_profile()
        log_event("", "app_started", install_folder=install_dir(), saved_destination=self.destination_text.text().strip())

    def build_ui(self):
        root = QWidget()
        main = QVBoxLayout(root)
        main.setContentsMargins(16, 14, 16, 12)
        main.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Git Helper")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        version = QLabel(APP_VERSION)
        version.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        version.setStyleSheet("color: #666;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(version)
        main.addLayout(title_row)

        form = QGridLayout()
        form.setColumnStretch(1, 1)
        form.addWidget(QLabel("Destination folder"), 0, 0)
        self.destination_text = QLineEdit()
        self.destination_text.setPlaceholderText("Choose the app/project folder Git Helper should manage")
        form.addWidget(self.destination_text, 0, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_destination)
        form.addWidget(browse, 0, 2)
        form.addWidget(QLabel("GitHub repo link"), 1, 0)
        self.remote_text = QLineEdit()
        self.remote_text.setPlaceholderText("https://github.com/owner/repo.git")
        form.addWidget(self.remote_text, 1, 1, 1, 2)
        main.addLayout(form)

        actions = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_repo)
        self.sync_button = QPushButton("Sync")
        self.sync_button.clicked.connect(self.sync_now)
        self.rev_button = QPushButton("Rev Up")
        self.rev_button.clicked.connect(self.rev_up)
        self.download_button = QPushButton("Download Rev Up")
        self.download_button.clicked.connect(self.download_new_rev)
        self.report_button = QPushButton("Collect Support Report")
        self.report_button.clicked.connect(self.collect_report)
        for button in [self.connect_button, self.sync_button, self.rev_button, self.download_button, self.report_button]:
            actions.addWidget(button)
        main.addLayout(actions)

        auto_row = QHBoxLayout()
        self.auto_check = QCheckBox("Auto sync")
        self.auto_check.stateChanged.connect(self.update_auto_sync)
        self.auto_minutes = QSpinBox()
        self.auto_minutes.setRange(1, 240)
        self.auto_minutes.setValue(int(self.config.get("auto_minutes", 15) or 15))
        self.auto_minutes.valueChanged.connect(self.update_auto_sync)
        auto_row.addWidget(self.auto_check)
        auto_row.addWidget(QLabel("every"))
        auto_row.addWidget(self.auto_minutes)
        auto_row.addWidget(QLabel("minutes"))
        auto_row.addStretch(1)
        main.addLayout(auto_row)

        self.status = QLabel("Choose a destination folder and repo link, then click Connect.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("background: #f4f6f8; border: 1px solid #d8dee4; padding: 10px;")
        main.addWidget(self.status)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Git Helper v5.1 will record decisions and Git details here.")
        main.addWidget(self.details, 1)
        self.setCentralWidget(root)

    def load_profile(self):
        self.destination_text.setText(self.config.get("destination", ""))
        self.remote_text.setText(self.config.get("remote_url", ""))
        self.auto_check.setChecked(bool(self.config.get("auto_sync", False)))

    def save_profile(self):
        self.config["destination"] = self.destination_text.text().strip()
        self.config["remote_url"] = self.remote_text.text().strip()
        self.config["auto_sync"] = self.auto_check.isChecked()
        self.config["auto_minutes"] = self.auto_minutes.value()
        save_config(self.config)

    def browse_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose destination folder", self.destination_text.text().strip() or os.path.expanduser("~"))
        if folder:
            self.destination_text.setText(folder)
            self.save_profile()

    def project(self):
        self.save_profile()
        return GitProject(self.destination_text.text().strip(), self.remote_text.text().strip())

    def set_busy(self, busy):
        for button in [self.connect_button, self.sync_button, self.rev_button, self.download_button, self.report_button]:
            button.setEnabled(not busy)
        self.destination_text.setEnabled(not busy)
        self.remote_text.setEnabled(not busy)

    def run_task(self, label, fn):
        if self.thread:
            return
        self.save_profile()
        self.status.setText(f"{label}...")
        self.details.appendPlainText(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {label}")
        self.set_busy(True)
        self.thread = QThread()
        self.worker = Worker(fn)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.task_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_thread)
        self.thread.start()

    def task_finished(self, result):
        if result.ok:
            self.status.setText(result.output or "Done.")
        else:
            self.status.setText(result.friendly or "Something unexpected happened. The details were saved.")
        if result.output:
            self.details.appendPlainText(result.output)
        if result.friendly and not result.ok:
            self.details.appendPlainText(result.friendly)
        log_event(self.destination_text.text().strip(), "task_finished", ok=result.ok, friendly=result.friendly, output=(result.output or "")[-4000:])

    def clear_thread(self):
        self.thread = None
        self.worker = None
        self.set_busy(False)

    def connect_repo(self):
        self.run_task("Connecting to GitHub", lambda: self.project().connect())

    def sync_now(self):
        self.run_task("Syncing", lambda: self.project().sync())

    def rev_up(self):
        self.run_task("Creating revision", lambda: self.project().rev_up())

    def download_new_rev(self):
        self.run_task("Downloading clean revision folder", lambda: self.project().download_new_rev())

    def collect_report(self):
        destination = self.destination_text.text().strip()
        if not destination:
            QMessageBox.warning(self, APP_DISPLAY_NAME, "Choose a destination folder first.")
            return
        try:
            report, count = collect_support_report(destination)
            self.status.setText(f"Support report collected: {report}")
            self.details.appendPlainText(f"Collected {count} support log records into {report}")
            QMessageBox.information(self, APP_DISPLAY_NAME, f"Support report collected:\n{report}")
        except OSError as exc:
            QMessageBox.warning(self, APP_DISPLAY_NAME, f"Could not collect the support report.\n\n{exc}")

    def update_auto_sync(self):
        self.save_profile()
        if self.auto_check.isChecked():
            self.timer.start(self.auto_minutes.value() * 60 * 1000)
            self.status.setText(f"Auto sync is on every {self.auto_minutes.value()} minutes.")
        else:
            self.timer.stop()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    win = GitHelperWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
