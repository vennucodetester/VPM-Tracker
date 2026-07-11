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
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QCommandLinkButton,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


APP_VERSION = "v5.2"
APP_DISPLAY_NAME = f"Git Helper {APP_VERSION}"
SUPPORT_DIR = ".git-helper"
CONFIG_DIR_NAME = "Git Helper v5.2"
LEGACY_CONFIG_DIR_NAME = "Git Helper v5.1"
CONFIG_FILE_NAME = "config.json"
GLOBAL_LOG_NAME = "git-helper-v5.2-all-folders.jsonl"
PROJECT_LOG_NAME = "git-helper-v5.2.log"
SUPPORT_REPORT_NAME = "Git Helper v5.2 Support Report.jsonl"
DEFAULT_BRANCH = "main"
IGNORED_TOP_LEVEL = {".git", SUPPORT_DIR}

# Conflict codes from "git status --porcelain".
# "ours" = my side, "theirs" = GitHub's side.
CONFLICT_CODES = {"UU", "AA", "AU", "UA", "UD", "DU", "DD"}
OURS_EXISTS = {"UU", "AA", "AU", "UD"}
THEIRS_EXISTS = {"UU", "AA", "UA", "DU"}


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


def legacy_config_path():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, LEGACY_CONFIG_DIR_NAME, CONFIG_FILE_NAME)


def global_log_path():
    return os.path.join(app_data_dir(), GLOBAL_LOG_NAME)


def project_log_path(destination):
    return os.path.join(destination, SUPPORT_DIR, PROJECT_LOG_NAME)


def recovery_root(destination):
    return os.path.join(destination, SUPPORT_DIR, "recovery")


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
    for path in [config_path(), legacy_config_path()]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
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
    snapshot = os.path.join(recovery_root(destination), f"{now_stamp()}-{reason}")
    os.makedirs(snapshot, exist_ok=True)
    for name in entries:
        source = os.path.join(destination, name)
        target = os.path.join(snapshot, name)
        shutil.move(source, target)
    log_event(destination, "destination_preserved_before_download", recovery_folder=snapshot, files=entries)
    return snapshot


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
        return "This folder has files that would be replaced. Git Helper stopped so nothing was lost."
    if "conflict" in text or "unmerged" in text:
        return "The same file changed in two places. Git Helper saved the details in the support log."
    if output and output.strip():
        return "Git could not finish that step. The details were saved in the support log."
    return "Git could not finish that step, and Git did not return details."


def conflict_labels(code):
    if code == "UD":
        return ("Keep my file (GitHub removed it)", "Remove it here too")
    if code == "DU":
        return ("Keep it removed (I removed it)", "Bring back GitHub's file")
    if code == "AU":
        return ("Keep my new file", "Don't keep it")
    if code == "UA":
        return ("Don't add it", "Add GitHub's new file")
    return ("My version", "GitHub's version")


@dataclass
class GitResult:
    ok: bool
    output: str = ""
    friendly: str = ""
    decision: dict = field(default=None)
    recovery: str = ""


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

    def ensure_support_dir_ignored(self):
        # Keep Git Helper's own logs and Recovery snapshots out of GitHub.
        try:
            support = os.path.join(self.destination, SUPPORT_DIR)
            os.makedirs(support, exist_ok=True)
            ignore = os.path.join(support, ".gitignore")
            if not os.path.isfile(ignore):
                with open(ignore, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write("*\n")
        except OSError:
            pass

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
        self.ensure_support_dir_ignored()
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

    def merge_in_progress(self):
        return os.path.isfile(os.path.join(self.destination, ".git", "MERGE_HEAD"))

    def conflicted_files(self):
        files = []
        for line in self.status_porcelain().splitlines():
            if len(line) < 4:
                continue
            code = line[:2]
            if code not in CONFLICT_CODES:
                continue
            path = line[3:].strip().strip('"')
            mine_label, github_label = conflict_labels(code)
            files.append({"path": path, "code": code, "mine_label": mine_label, "github_label": github_label})
        return files

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

    def preserve_working_copy(self, path, snapshot):
        # Copies the file currently in the folder into a Recovery snapshot,
        # keeping its sub-folder structure. Returns the snapshot path used.
        source = os.path.join(self.destination, path)
        if not os.path.isfile(source):
            return snapshot
        if not snapshot:
            snapshot = os.path.join(recovery_root(self.destination), f"{now_stamp()}-your-versions-from-sync")
        target = os.path.join(snapshot, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        return snapshot

    def download_github_copy(self, branch):
        # "GitHub wins": this folder becomes a copy of GitHub. Anything already
        # in the folder is preserved in Recovery first - nothing is deleted.
        backup = ""
        if folder_has_user_files(self.destination):
            backup = backup_and_clear_destination(self.destination, "before-github-download")
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        checkout = self.run(["checkout", "-f", "-B", branch, f"origin/{branch}"], timeout=120)
        if not checkout.ok:
            return checkout
        self.run(["branch", "--set-upstream-to", f"origin/{branch}", branch])
        message = "Done. This folder now matches GitHub."
        if backup:
            message += f"\nYour previous files were NOT deleted. They were saved to:\n{backup}"
        return GitResult(True, message, recovery=backup)

    def replace_github_with_folder(self, branch):
        # "My folder wins": GitHub becomes a copy of this folder. GitHub's old
        # copy is saved as a milestone first so it can always be downloaded.
        commit = self.commit_if_needed(f"Save local files with {APP_DISPLAY_NAME}")
        if not commit.ok:
            return commit
        self.run(["branch", "-M", branch])
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        tag = ""
        if self.run(["rev-parse", "--verify", f"origin/{branch}"], timeout=30).ok:
            tag = f"github-copy-before-upload-{now_stamp()}"
            made = self.run(["tag", tag, f"origin/{branch}"], timeout=30)
            if made.ok:
                pushed_tag = self.run(["push", "origin", tag], timeout=120)
                if not pushed_tag.ok:
                    tag = ""
            else:
                tag = ""
        push = self.run(["push", "--force-with-lease", "-u", "origin", branch], timeout=120)
        if not push.ok:
            return push
        message = "Done. GitHub now matches this folder."
        if tag:
            message += f"\nGitHub's old copy was saved as milestone '{tag}', so nothing was lost."
        log_event(self.destination, "github_replaced_with_folder", saved_milestone=tag)
        return GitResult(True, message)

    def combine_unrelated(self, branch, origin):
        # "Keep both": merge GitHub's files with this folder's files.
        commit = self.commit_if_needed(f"Save local files with {APP_DISPLAY_NAME}")
        if not commit.ok:
            return commit
        self.run(["branch", "-M", branch])
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        merge = self.run(["merge", "--allow-unrelated-histories", "--no-edit", f"origin/{branch}"], timeout=120)
        if not merge.ok:
            files = self.conflicted_files()
            if files:
                return GitResult(
                    False,
                    merge.output,
                    "",
                    decision={"kind": "conflicts", "files": files, "branch": branch, "origin": origin},
                )
            if self.merge_in_progress():
                self.run(["merge", "--abort"], timeout=60)
            return merge
        push = self.run(["push", "-u", "origin", branch], timeout=120)
        if not push.ok:
            return push
        return GitResult(True, "Done. GitHub's files and your files are now combined, and GitHub is up to date.")

    def resolve_unrelated(self, choice, branch, origin):
        setup = self.ensure_repo()
        if not setup.ok:
            return setup
        if choice == "upload":
            result = self.replace_github_with_folder(branch)
        elif choice == "download":
            result = self.download_github_copy(branch)
        elif choice == "combine":
            result = self.combine_unrelated(branch, origin)
        elif choice == "side":
            return self.download_new_rev(label="github-copy")
        else:
            return GitResult(True, "Nothing was changed.")
        if result.ok and origin == "rev" and choice in ("upload", "download", "combine"):
            rev = self.rev_up()
            combined_output = "\n".join(part for part in [result.output, rev.output] if part)
            return GitResult(rev.ok, combined_output, rev.friendly, decision=rev.decision, recovery=result.recovery)
        return result

    def resolve_conflicts(self, files, mapping, branch, origin):
        if not self.merge_in_progress():
            return GitResult(False, "", "The sync that needed a decision is no longer waiting. Click Sync again.")
        snapshot = ""
        kept_mine = 0
        kept_github = 0
        for item in files:
            path = item["path"]
            code = item["code"]
            choice = mapping.get(path, "mine")
            if code == "DD":
                self.run(["rm", "-f", "--", path], timeout=30)
                continue
            ours = code in OURS_EXISTS
            theirs = code in THEIRS_EXISTS
            if choice == "github":
                kept_github += 1
                if ours:
                    # Bring my clean version into the folder just long enough
                    # to copy it into Recovery, so it is never lost.
                    self.run(["checkout", "--ours", "--", path], timeout=30)
                    snapshot = self.preserve_working_copy(path, snapshot)
                if theirs:
                    self.run(["checkout", "--theirs", "--", path], timeout=30)
                    self.run(["add", "--", path], timeout=30)
                else:
                    self.run(["rm", "-f", "--", path], timeout=30)
            else:
                kept_mine += 1
                if ours:
                    self.run(["checkout", "--ours", "--", path], timeout=30)
                    self.run(["add", "--", path], timeout=30)
                else:
                    self.run(["rm", "-f", "--", path], timeout=30)
        commit = self.run(["commit", "--no-edit"], timeout=60)
        if not commit.ok and "nothing to commit" not in commit.output.lower():
            return commit
        push = self.run(["push", "-u", "origin", branch], timeout=120)
        if not push.ok:
            return push
        parts = ["Sync finished with your choices."]
        if kept_mine:
            parts.append(f"{kept_mine} file(s) kept your version.")
        if kept_github:
            parts.append(f"{kept_github} file(s) kept GitHub's version.")
        if snapshot:
            parts.append(f"Your versions of the replaced files were saved to:\n{snapshot}")
        log_event(self.destination, "conflicts_resolved", kept_mine=kept_mine, kept_github=kept_github, recovery=snapshot)
        result = GitResult(True, "\n".join(parts), recovery=snapshot)
        if origin == "rev":
            rev = self.rev_up()
            combined_output = "\n".join(part for part in [result.output, rev.output] if part)
            return GitResult(rev.ok, combined_output, rev.friendly, decision=rev.decision, recovery=snapshot)
        return result

    def cancel_merge(self):
        if self.merge_in_progress():
            aborted = self.run(["merge", "--abort"], timeout=60)
            if not aborted.ok:
                return aborted
        return GitResult(True, "Nothing was changed. Your folder is back the way it was before Sync.")

    def first_upload(self):
        self.run(["branch", "-M", DEFAULT_BRANCH])
        commit = self.commit_if_needed(f"Save local files with {APP_DISPLAY_NAME}")
        if not commit.ok:
            return commit
        push = self.run(["push", "-u", "origin", DEFAULT_BRANCH], timeout=120)
        return push if not push.ok else GitResult(True, "Uploaded this folder to GitHub.")

    def connect(self, origin="connect"):
        setup = self.ensure_repo()
        if not setup.ok:
            return setup
        if not self.remote_has_files():
            return self.first_upload()
        branch = self.remote_default_branch()
        if not self.has_local_commit():
            if folder_has_user_files(self.destination):
                # Both sides have files and they have never been connected.
                # Never decide silently - ask the user.
                return GitResult(False, "", "", decision={"kind": "unrelated", "branch": branch, "origin": origin})
            return self.download_github_copy(branch)
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        if self.run(["rev-parse", "--verify", f"origin/{branch}"], timeout=30).ok:
            related = self.run(["merge-base", "HEAD", f"origin/{branch}"], timeout=30)
            if not related.ok:
                return GitResult(False, "", "", decision={"kind": "unrelated", "branch": branch, "origin": origin})
        self.run(["branch", "-M", branch])
        self.run(["branch", "--set-upstream-to", f"origin/{branch}", branch])
        return GitResult(True, "Connected. This folder and GitHub are linked.")

    def upload_removals(self, branch):
        # What would disappear from GitHub's current copy if we upload now?
        diff = self.run(["diff", "--name-status", f"origin/{branch}", "HEAD"], timeout=45)
        removed = []
        added = 0
        changed = 0
        if diff.ok:
            for line in diff.output.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                status, path = parts[0].strip(), parts[1].strip().strip('"')
                if status.startswith("D"):
                    removed.append(path)
                elif status.startswith("A"):
                    added += 1
                else:
                    changed += 1
        return removed, added, changed

    def sync(self, origin="sync", approved_upload=False):
        setup = self.connect(origin=origin)
        if not setup.ok or setup.decision:
            return setup
        branch = self.current_branch()
        save = self.commit_if_needed(f"Save local work {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if not save.ok:
            return save
        fetch = self.run(["fetch", "origin"], timeout=120)
        if not fetch.ok:
            return fetch
        ahead = behind = 0
        remote_branch_exists = self.run(["rev-parse", "--verify", f"origin/{branch}"], timeout=30).ok
        if remote_branch_exists:
            counts = self.run(["rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"], timeout=45)
            if counts.ok:
                parts = counts.output.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    ahead, behind = int(parts[0]), int(parts[1])
            if behind:
                pull = self.run(["pull", "--no-rebase", "--no-edit", "origin", branch], timeout=120)
                if not pull.ok:
                    files = self.conflicted_files()
                    if files:
                        return GitResult(
                            False,
                            pull.output,
                            "",
                            decision={"kind": "conflicts", "files": files, "branch": branch, "origin": origin},
                        )
                    if self.merge_in_progress():
                        self.run(["merge", "--abort"], timeout=60)
                    log_event(self.destination, "sync_pull_failed", friendly=pull.friendly, output=pull.output)
                    return pull
        if remote_branch_exists and not approved_upload:
            removed, added, changed = self.upload_removals(branch)
            if removed:
                # This upload would remove files from GitHub's current copy.
                # Never do that silently - ask the user first.
                return GitResult(
                    False,
                    "",
                    "",
                    decision={
                        "kind": "upload_removals",
                        "removed": removed,
                        "added": added,
                        "changed": changed,
                        "branch": branch,
                        "origin": origin,
                    },
                )
        push = self.run(["push", "-u", "origin", branch], timeout=120)
        if not push.ok:
            low = push.output.lower()
            if "fetch first" in low or "non-fast-forward" in low or "[rejected]" in low:
                # GitHub changed while we were syncing. Try once more.
                pull = self.run(["pull", "--no-rebase", "--no-edit", "origin", branch], timeout=120)
                if not pull.ok:
                    files = self.conflicted_files()
                    if files:
                        return GitResult(
                            False,
                            pull.output,
                            "",
                            decision={"kind": "conflicts", "files": files, "branch": branch, "origin": origin},
                        )
                    if self.merge_in_progress():
                        self.run(["merge", "--abort"], timeout=60)
                    return pull
                behind = 1
                push = self.run(["push", "-u", "origin", branch], timeout=120)
                if not push.ok:
                    return GitResult(False, push.output, "", decision={"kind": "retry", "origin": origin})
            else:
                return push
        if ahead and behind:
            message = "Combined your changes with GitHub's changes. Both are kept, and GitHub is up to date."
        elif ahead:
            message = "Uploaded your changes to GitHub."
        elif behind:
            message = "Downloaded the latest from GitHub. Nothing of yours was changed."
        else:
            message = "Everything is already up to date."
        return GitResult(True, message)

    def next_rev_name(self):
        tags = self.run(["tag", "--list", "rev-*"], timeout=45)
        highest = 0
        if tags.ok:
            for tag in tags.output.splitlines():
                match = re.fullmatch(r"rev-(\d+)", tag.strip())
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"rev-{highest + 1:03d}"

    def rev_up(self, approved_upload=False):
        synced = self.sync(origin="rev", approved_upload=approved_upload)
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
        return GitResult(True, f"Created and uploaded milestone {tag}.")

    def download_new_rev(self, label="rev"):
        setup = self.ensure_repo()
        if not setup.ok:
            return setup
        branch = self.remote_default_branch()
        parent = os.path.dirname(self.destination)
        base = re.sub(r"-(rev|github-copy)-\d+$", "", os.path.basename(self.destination), flags=re.IGNORECASE)
        index = 1
        while True:
            target = os.path.join(parent, f"{base}-{label}-{index:03d}")
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
        return GitResult(True, f"Downloaded a clean copy of GitHub here:\n{target}\nYour current folder was not changed.")


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


class DecisionDialog(QDialog):
    def __init__(self, parent, title, intro, options):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        label = QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)
        for key, text, explanation in options:
            button = QCommandLinkButton(text, explanation)
            button.clicked.connect(lambda _=False, k=key: self.pick(k))
            layout.addWidget(button)

    def pick(self, key):
        self.choice = key
        self.accept()

    @staticmethod
    def ask(parent, title, intro, options):
        dialog = DecisionDialog(parent, title, intro, options)
        dialog.exec()
        return dialog.choice


class FileChoiceDialog(QDialog):
    def __init__(self, parent, title, intro, files):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        self.groups = []
        layout = QVBoxLayout(self)
        label = QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setColumnStretch(0, 1)
        row = 0
        for item in files:
            if item.get("code") == "DD":
                continue
            name = QLabel(item["path"])
            name.setWordWrap(True)
            mine = QRadioButton(item["mine_label"])
            github = QRadioButton(item["github_label"])
            mine.setChecked(True)
            group = QButtonGroup(self)
            group.addButton(mine)
            group.addButton(github)
            grid.addWidget(name, row, 0)
            grid.addWidget(mine, row, 1)
            grid.addWidget(github, row, 2)
            self.groups.append((item["path"], mine))
            row += 1
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setMinimumHeight(min(60 + row * 34, 420))
        layout.addWidget(scroll)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("Do it")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Go back")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def mapping(self):
        return {path: ("mine" if mine.isChecked() else "github") for path, mine in self.groups}

    @staticmethod
    def ask(parent, title, intro, files):
        dialog = FileChoiceDialog(parent, title, intro, files)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.mapping()
        return None


class RecoveryDialog(QDialog):
    def __init__(self, parent, destination):
        super().__init__(parent)
        self.destination = destination
        self.root = recovery_root(destination)
        self.setWindowTitle(f"{APP_DISPLAY_NAME} - Recovery")
        self.setMinimumSize(680, 460)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Whenever Git Helper replaces files in your folder, it first saves them here. "
            "Nothing in Recovery is ever deleted by Git Helper. Pick a snapshot to see what is inside, "
            "put files back, or open the folder."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.snapshots = QListWidget()
        self.snapshots.currentRowChanged.connect(self.show_details)
        layout.addWidget(self.snapshots, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(140)
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        self.restore_button = QPushButton("Put these files back into my folder")
        self.restore_button.clicked.connect(self.put_back)
        open_button = QPushButton("Open this snapshot in Explorer")
        open_button.clicked.connect(self.open_folder)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.restore_button)
        buttons.addWidget(open_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.names = []
        self.reload()

    def reload(self):
        self.snapshots.clear()
        self.names = []
        if os.path.isdir(self.root):
            for name in sorted(os.listdir(self.root), reverse=True):
                if not os.path.isdir(os.path.join(self.root, name)):
                    continue
                self.names.append(name)
                self.snapshots.addItem(self.friendly_name(name))
        if not self.names:
            self.details.setPlainText("Recovery is empty. Nothing has been preserved for this folder yet.")
            self.restore_button.setEnabled(False)
        else:
            self.restore_button.setEnabled(True)
            self.snapshots.setCurrentRow(0)

    def friendly_name(self, name):
        stamp = name[:15]
        reason = name[16:].replace("-", " ") if len(name) > 16 else ""
        try:
            when = datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S").strftime("%b %d, %Y at %I:%M %p")
        except ValueError:
            when = name
        return f"{when} - {reason}" if reason else when

    def selected_path(self):
        row = self.snapshots.currentRow()
        if row < 0 or row >= len(self.names):
            return ""
        return os.path.join(self.root, self.names[row])

    def show_details(self, _row):
        path = self.selected_path()
        if not path:
            return
        entries = sorted(os.listdir(path))
        lines = [f"This snapshot holds {len(entries)} item(s):"] + [f"  {name}" for name in entries]
        self.details.setPlainText("\n".join(lines))

    def open_folder(self):
        path = self.selected_path()
        if path and sys.platform == "win32":
            os.startfile(path)

    def put_back(self):
        snapshot = self.selected_path()
        if not snapshot:
            return
        entries = sorted(os.listdir(snapshot))
        if not entries:
            QMessageBox.information(self, APP_DISPLAY_NAME, "This snapshot is empty.")
            return
        collisions = [name for name in entries if os.path.exists(os.path.join(self.destination, name))]
        mapping = {}
        if collisions:
            files = [
                {
                    "path": name,
                    "code": "",
                    "mine_label": "Use the Recovery copy",
                    "github_label": "Keep the folder's current copy",
                }
                for name in collisions
            ]
            mapping = FileChoiceDialog.ask(
                self,
                f"{APP_DISPLAY_NAME} - Putting files back",
                "Some of these files already exist in your folder. For each one, choose which copy to keep. "
                "Any current copy that gets replaced is itself saved to Recovery first.",
                files,
            )
            if mapping is None:
                return
        backup_root = os.path.join(self.root, f"{now_stamp()}-before-restore")
        restored = []
        skipped = []
        for name in entries:
            source = os.path.join(snapshot, name)
            target = os.path.join(self.destination, name)
            if name in collisions:
                if mapping.get(name) == "github":
                    skipped.append(name)
                    continue
                os.makedirs(backup_root, exist_ok=True)
                shutil.move(target, os.path.join(backup_root, name))
            if os.path.isdir(source):
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            restored.append(name)
        log_event(self.destination, "recovery_restored", snapshot=snapshot, restored=restored, skipped=skipped)
        summary = f"Put back {len(restored)} item(s) into your folder."
        if skipped:
            summary += f"\nKept the folder's current copy for {len(skipped)} item(s)."
        summary += "\n\nThe Recovery snapshot itself was kept, so you can do this again any time."
        summary += "\n\nTip: click Sync to upload the restored files to GitHub."
        QMessageBox.information(self, APP_DISPLAY_NAME, summary)
        self.reload()


class GitHelperWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.thread = None
        self.worker = None
        self.pending_decision = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_now)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(880, 640)
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
        self.connect_button.setToolTip("Link this folder to your GitHub repo. If both already have files, Git Helper asks you what to do.")
        self.sync_button = QPushButton("Sync")
        self.sync_button.clicked.connect(self.sync_now)
        self.sync_button.setToolTip("Save this folder and GitHub together. If the same file changed in both places, Git Helper asks which one wins.")
        self.rev_button = QPushButton("Rev Up")
        self.rev_button.clicked.connect(self.rev_up)
        self.rev_button.setToolTip("Sync, then save a numbered milestone (rev-001, rev-002, ...) on GitHub that you can always go back to.")
        self.download_button = QPushButton("Download Rev Up")
        self.download_button.clicked.connect(self.download_new_rev)
        self.download_button.setToolTip("Download a fresh copy of GitHub into a NEW side folder. This folder is not changed.")
        for button in [self.connect_button, self.sync_button, self.rev_button, self.download_button]:
            actions.addWidget(button)
        main.addLayout(actions)

        actions2 = QHBoxLayout()
        self.recovery_button = QPushButton("Recovery")
        self.recovery_button.clicked.connect(self.open_recovery)
        self.recovery_button.setToolTip("See files Git Helper preserved before changing this folder, and put them back if you want.")
        self.report_button = QPushButton("Collect Support Report")
        self.report_button.clicked.connect(self.collect_report)
        self.report_button.setToolTip("Gather Git Helper's logs into one file you can share when asking for help.")
        actions2.addWidget(self.recovery_button)
        actions2.addWidget(self.report_button)
        actions2.addStretch(1)
        main.addLayout(actions2)

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
        self.details.setPlaceholderText("Git Helper v5.2 will record decisions and Git details here.")
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
        for button in [self.connect_button, self.sync_button, self.rev_button, self.download_button, self.recovery_button, self.report_button]:
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
        if getattr(result, "decision", None):
            self.pending_decision = True
            self.status.setText("Git Helper needs a decision from you...")
            log_event(self.destination_text.text().strip(), "decision_needed", kind=result.decision.get("kind"))
            QTimer.singleShot(0, lambda: self.handle_decision(result))
            return
        if result.ok:
            self.status.setText(result.output or "Done.")
        else:
            self.status.setText(result.friendly or "Something unexpected happened. The details were saved.")
        if result.output:
            self.details.appendPlainText(result.output)
        if result.friendly and not result.ok:
            self.details.appendPlainText(result.friendly)
        log_event(self.destination_text.text().strip(), "task_finished", ok=result.ok, friendly=result.friendly, output=(result.output or "")[-4000:])
        recovery = getattr(result, "recovery", "")
        if recovery:
            QTimer.singleShot(0, lambda: self.show_preserved_popup(recovery))

    def show_preserved_popup(self, path):
        box = QMessageBox(self)
        box.setWindowTitle(APP_DISPLAY_NAME)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "Your files were NOT deleted.\n\n"
            "Before changing your folder, Git Helper saved copies here:\n\n"
            f"{path}\n\n"
            "You can put them back any time with the Recovery button."
        )
        open_button = box.addButton("Open that folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_button and sys.platform == "win32":
            os.startfile(path)

    def handle_decision(self, result):
        if self.thread:
            # The finished worker thread is still shutting down; try again in a
            # moment so the follow-up task is not silently dropped by run_task.
            QTimer.singleShot(50, lambda: self.handle_decision(result))
            return
        decision = result.decision
        kind = decision.get("kind")
        origin = decision.get("origin", "sync")
        if kind == "unrelated":
            self.decide_unrelated(decision, origin)
        elif kind == "conflicts":
            self.decide_conflicts(decision, origin)
        elif kind == "upload_removals":
            self.decide_upload_removals(decision, origin)
        elif kind == "retry":
            self.decide_retry(origin)
        else:
            self.pending_decision = False

    def decide_upload_removals(self, decision, origin):
        removed = decision.get("removed", [])
        added = decision.get("added", 0)
        changed = decision.get("changed", 0)
        shown = removed[:10]
        listing = "\n".join(f"  {path}" for path in shown)
        if len(removed) > len(shown):
            listing += f"\n  ...and {len(removed) - len(shown)} more"
        summary_bits = []
        if added:
            summary_bits.append(f"add {added} new file(s)")
        if changed:
            summary_bits.append(f"update {changed} file(s)")
        summary = " and ".join(summary_bits)
        intro = (
            f"This upload will REMOVE {len(removed)} file(s) from GitHub's current copy:\n"
            + listing
            + (f"\n\nIt will also {summary}." if summary else "")
            + "\n\nRemoved files are NOT lost - they stay in GitHub's history and in past milestones."
        )
        choice = DecisionDialog.ask(
            self,
            f"{APP_DISPLAY_NAME} - Your decision",
            intro,
            [
                (
                    "upload",
                    "Upload - make GitHub match this folder",
                    "GitHub's front page will show exactly what is in this folder now.",
                ),
                (
                    "cancel",
                    "Don't upload",
                    "GitHub stays as it is. Your folder keeps your changes. You can Sync again any time.",
                ),
            ],
        )
        self.pending_decision = False
        if choice != "upload":
            self.status.setText("Upload stopped. GitHub was not changed. Your folder keeps your changes.")
            self.details.appendPlainText("You chose not to upload.")
            return
        self.details.appendPlainText("You approved the upload, including the removals.")
        if origin == "rev":
            self.run_task("Creating revision", lambda: self.project().rev_up(approved_upload=True))
        else:
            self.run_task("Uploading to GitHub", lambda: self.project().sync(origin=origin, approved_upload=True))

    def decide_unrelated(self, decision, origin):
        branch = decision.get("branch", DEFAULT_BRANCH)
        choice = DecisionDialog.ask(
            self,
            f"{APP_DISPLAY_NAME} - Your decision",
            "This folder and GitHub BOTH have files, and they are not connected yet.\n"
            "Git Helper will not guess. What do you want to do?",
            [
                (
                    "upload",
                    "Upload this folder to GitHub",
                    "GitHub will be replaced with this folder's files. GitHub's current copy is saved as a milestone first, so nothing is lost.",
                ),
                (
                    "download",
                    "Download the GitHub copy into this folder",
                    "This folder will match GitHub. Your current files are moved to the Recovery area first - nothing is deleted.",
                ),
                (
                    "combine",
                    "Combine both",
                    "Keep GitHub's files AND your files together. If the same file exists in both, you choose which one to keep.",
                ),
                (
                    "side",
                    "Let me look first",
                    "Download GitHub's copy into a separate side folder so you can compare. Nothing changes here.",
                ),
                (
                    "cancel",
                    "Do nothing",
                    "Close this window and change nothing.",
                ),
            ],
        )
        self.pending_decision = False
        if choice in (None, "cancel"):
            self.status.setText("Nothing was changed.")
            self.details.appendPlainText("You chose to do nothing.")
            return
        labels = {
            "upload": "Uploading this folder to GitHub",
            "download": "Downloading the GitHub copy into this folder",
            "combine": "Combining GitHub's files with this folder",
            "side": "Downloading GitHub's copy into a side folder",
        }
        self.details.appendPlainText(f"You chose: {labels[choice]}.")
        self.run_task(labels[choice], lambda: self.project().resolve_unrelated(choice, branch, origin))

    def decide_conflicts(self, decision, origin):
        branch = decision.get("branch", DEFAULT_BRANCH)
        files = decision.get("files", [])
        shown = [item["path"] for item in files if item.get("code") != "DD"][:10]
        listing = "\n".join(f"  {path}" for path in shown)
        extra = len([f for f in files if f.get("code") != "DD"]) - len(shown)
        if extra > 0:
            listing += f"\n  ...and {extra} more"
        mapping = None
        cancelled = False
        while True:
            choice = DecisionDialog.ask(
                self,
                f"{APP_DISPLAY_NAME} - Your decision",
                "You and GitHub both changed the same file(s):\n" + listing + "\n\nWhich version should be kept?",
                [
                    (
                        "mine",
                        "Keep MY versions",
                        "Your files win. GitHub's versions are still saved in GitHub's history, so they are not lost.",
                    ),
                    (
                        "github",
                        "Keep GITHUB's versions",
                        "GitHub's files win. Your versions are copied to the Recovery area first, so they are not lost.",
                    ),
                    (
                        "perfile",
                        "Let me choose file by file",
                        "Pick the winner for each file separately.",
                    ),
                    (
                        "cancel",
                        "Cancel",
                        "Stop and put everything back the way it was before Sync.",
                    ),
                ],
            )
            if choice == "perfile":
                mapping = FileChoiceDialog.ask(
                    self,
                    f"{APP_DISPLAY_NAME} - Choose file by file",
                    "For each file, choose which version to keep. Whichever version loses is still kept - "
                    "yours goes to Recovery, GitHub's stays in GitHub's history.",
                    files,
                )
                if mapping is None:
                    continue
                break
            if choice in ("mine", "github"):
                mapping = {item["path"]: choice for item in files}
                break
            cancelled = True
            break
        self.pending_decision = False
        if cancelled:
            self.run_task("Putting everything back", lambda: self.project().cancel_merge())
            return
        self.details.appendPlainText("You chose which versions to keep.")
        self.run_task(
            "Finishing sync with your choices",
            lambda: self.project().resolve_conflicts(files, mapping, branch, origin),
        )

    def decide_retry(self, origin):
        choice = DecisionDialog.ask(
            self,
            f"{APP_DISPLAY_NAME} - Your decision",
            "GitHub changed while syncing (maybe another computer uploaded at the same time).",
            [
                ("retry", "Try again", "Run the sync one more time."),
                ("cancel", "Stop for now", "Your saved work stays in this folder. Nothing is lost."),
            ],
        )
        self.pending_decision = False
        if choice != "retry":
            self.status.setText("Sync stopped. Your work is saved in this folder - try Sync again later.")
            return
        if origin == "rev":
            self.run_task("Creating revision", lambda: self.project().rev_up())
        else:
            self.run_task("Syncing", lambda: self.project().sync(origin=origin))

    def clear_thread(self):
        self.thread = None
        self.worker = None
        self.set_busy(False)

    def confirm_with_skip(self, config_key, text):
        if self.config.get(config_key):
            return True
        box = QMessageBox(self)
        box.setWindowTitle(APP_DISPLAY_NAME)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Ok).setText("Continue")
        box.button(QMessageBox.StandardButton.Cancel).setText("Not now")
        check = QCheckBox("Don't show this explanation again")
        box.setCheckBox(check)
        proceed = box.exec() == QMessageBox.StandardButton.Ok
        if proceed and check.isChecked():
            self.config[config_key] = True
            save_config(self.config)
        return proceed

    def connect_repo(self):
        self.run_task("Connecting to GitHub", lambda: self.project().connect())

    def sync_now(self):
        if self.thread or self.pending_decision:
            return
        self.run_task("Syncing", lambda: self.project().sync())

    def rev_up(self):
        if not self.confirm_with_skip(
            "skip_rev_up_explainer",
            "Rev Up saves a numbered milestone of your folder on GitHub (rev-001, rev-002, ...).\n\n"
            "A milestone is a permanent save point. You can always download any past milestone later "
            "with 'Download Rev Up', even after more changes.\n\n"
            "Your folder is synced first, then the milestone is created. Continue?",
        ):
            return
        self.run_task("Creating revision", lambda: self.project().rev_up())

    def download_new_rev(self):
        if not self.confirm_with_skip(
            "skip_download_rev_explainer",
            "Download Rev Up downloads a fresh copy of everything on GitHub into a NEW side folder "
            "next to your destination folder.\n\n"
            "Your current folder is not changed. Continue?",
        ):
            return
        self.run_task("Downloading clean revision folder", lambda: self.project().download_new_rev())

    def open_recovery(self):
        destination = self.destination_text.text().strip()
        if not destination or not os.path.isdir(destination):
            QMessageBox.warning(self, APP_DISPLAY_NAME, "Choose a destination folder first.")
            return
        RecoveryDialog(self, os.path.abspath(destination)).exec()

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
