"""
Git Helper — Standalone PyQt6 Git Dashboard
A simple GUI for pull/push/commit/stage/diff/stash/tag operations.
No LLM or external dependencies beyond PyQt6 and git CLI.
"""
import sys
import os
import subprocess
import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QGroupBox, QPushButton, QLineEdit, QPlainTextEdit,
    QTreeWidget, QTreeWidgetItem, QLabel, QDialog, QFileDialog,
    QMessageBox, QInputDialog,
)
from PyQt6.QtGui import QFont, QColor, QBrush, QPalette
from PyQt6.QtCore import Qt


# ============================================================================
# GIT RUNNER — subprocess wrapper for git CLI
# ============================================================================

class GitRunner:
    """Wraps all git operations via subprocess. Returns (success, output) tuples."""

    def __init__(self, repo_path):
        self.repo_path = repo_path

    def _run(self, args, timeout=30):
        """Run a git command and return (success: bool, output: str)."""
        try:
            kwargs = dict(
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(["git"] + args, **kwargs)
            output = (result.stdout or "") + (result.stderr or "")
            return (result.returncode == 0, output.strip())
        except subprocess.TimeoutExpired:
            return (False, "Command timed out. If push/pull needs auth, run git from terminal first.")
        except FileNotFoundError:
            return (False, "git is not installed or not in PATH.")

    def is_git_repo(self):
        ok, _ = self._run(["rev-parse", "--is-inside-work-tree"])
        return ok

    def status(self):
        return self._run(["status", "--porcelain=v1"])

    def status_long(self):
        return self._run(["status"])

    def pull(self):
        return self._run(["pull"], timeout=60)

    def push(self):
        return self._run(["push"], timeout=60)

    def stage_files(self, files):
        return self._run(["add", "--"] + files)

    def stage_all(self):
        return self._run(["add", "-A"])

    def unstage_files(self, files):
        return self._run(["restore", "--staged", "--"] + files)

    def commit(self, message):
        return self._run(["commit", "-m", message])

    def log(self, count=20):
        return self._run(["log", "--oneline", f"-n{count}"])

    def diff_file(self, filepath):
        return self._run(["diff", "--", filepath])

    def diff_staged_file(self, filepath):
        return self._run(["diff", "--cached", "--", filepath])

    def branch_info(self):
        return self._run(["branch", "-vv"])

    def current_branch(self):
        return self._run(["rev-parse", "--abbrev-ref", "HEAD"])

    def stash_save(self, message=""):
        args = ["stash", "push"]
        if message:
            args += ["-m", message]
        return self._run(args)

    def stash_list(self):
        return self._run(["stash", "list"])

    def stash_pop(self):
        return self._run(["stash", "pop"])

    def create_tag(self, name, message=""):
        args = ["tag", "-a", name]
        if message:
            args += ["-m", message]
        else:
            args += ["-m", name]
        return self._run(args)

    def list_tags(self, count=10):
        return self._run(["tag", "--sort=-creatordate"])

    def push_tags(self):
        return self._run(["push", "--tags"], timeout=60)


# ============================================================================
# DIFF DIALOG — modal file diff viewer
# ============================================================================

class DiffDialog(QDialog):
    def __init__(self, filename, diff_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Diff: {filename}")
        self.resize(750, 520)
        layout = QVBoxLayout(self)
        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Consolas", 10))
        text_edit.setPlainText(diff_text)
        layout.addWidget(text_edit)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)


# ============================================================================
# MAIN WINDOW — Git Helper Dashboard
# ============================================================================

class GitHelperWindow(QMainWindow):
    def __init__(self, repo_path):
        super().__init__()
        self.repo_path = repo_path
        self.git = GitRunner(repo_path)
        self.setWindowTitle(f"Git Helper — {os.path.basename(repo_path)}")
        self.resize(950, 650)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # --- Top bar: branch info + refresh ---
        top_bar = QHBoxLayout()
        self.branch_label = QLabel("Branch: ...")
        self.branch_label.setFont(QFont("Consolas", 10))
        top_bar.addWidget(self.branch_label)
        top_bar.addStretch()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_status)
        top_bar.addWidget(btn_refresh)
        main_layout.addLayout(top_bar)

        # --- Splitter: left (actions) | right (output) ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        # LEFT PANEL
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)

        # Remote group
        grp_remote = QGroupBox("Remote")
        remote_lay = QHBoxLayout(grp_remote)
        self.btn_pull = QPushButton("Pull")
        self.btn_push = QPushButton("Push")
        self.btn_pull.clicked.connect(self.do_pull)
        self.btn_push.clicked.connect(self.do_push)
        remote_lay.addWidget(self.btn_pull)
        remote_lay.addWidget(self.btn_push)
        left_layout.addWidget(grp_remote)

        # File status group
        grp_files = QGroupBox("Working Tree")
        files_lay = QVBoxLayout(grp_files)
        self.file_list = QTreeWidget()
        self.file_list.setHeaderLabels(["Status", "File"])
        self.file_list.setColumnWidth(0, 60)
        self.file_list.setFont(QFont("Consolas", 9))
        self.file_list.setRootIsDecorated(False)
        files_lay.addWidget(self.file_list)

        file_btn_row = QHBoxLayout()
        btn_stage_sel = QPushButton("Stage Selected")
        btn_stage_all = QPushButton("Stage All")
        btn_unstage = QPushButton("Unstage")
        btn_stage_sel.clicked.connect(self.do_stage_selected)
        btn_stage_all.clicked.connect(self.do_stage_all)
        btn_unstage.clicked.connect(self.do_unstage_selected)
        file_btn_row.addWidget(btn_stage_sel)
        file_btn_row.addWidget(btn_stage_all)
        file_btn_row.addWidget(btn_unstage)
        files_lay.addLayout(file_btn_row)
        left_layout.addWidget(grp_files)

        # Commit group
        grp_commit = QGroupBox("Commit")
        commit_lay = QVBoxLayout(grp_commit)
        self.commit_msg = QLineEdit()
        self.commit_msg.setPlaceholderText("Commit message...")
        commit_lay.addWidget(self.commit_msg)
        self.btn_commit = QPushButton("Commit")
        self.btn_commit.clicked.connect(self.do_commit)
        self.commit_msg.textChanged.connect(
            lambda txt: self.btn_commit.setEnabled(bool(txt.strip()))
        )
        self.btn_commit.setEnabled(False)
        commit_lay.addWidget(self.btn_commit)
        left_layout.addWidget(grp_commit)

        # Tools group
        grp_tools = QGroupBox("Tools")
        tools_lay = QVBoxLayout(grp_tools)
        row1 = QHBoxLayout()
        btn_log = QPushButton("View Log")
        btn_diff = QPushButton("Diff Selected")
        btn_log.clicked.connect(self.do_view_log)
        btn_diff.clicked.connect(self.do_diff_selected)
        row1.addWidget(btn_log)
        row1.addWidget(btn_diff)
        tools_lay.addLayout(row1)

        row2 = QHBoxLayout()
        btn_stash = QPushButton("Stash")
        btn_stash_pop = QPushButton("Pop Stash")
        btn_stash_list = QPushButton("List Stashes")
        btn_stash.clicked.connect(self.do_stash_save)
        btn_stash_pop.clicked.connect(self.do_stash_pop)
        btn_stash_list.clicked.connect(self.do_stash_list)
        row2.addWidget(btn_stash)
        row2.addWidget(btn_stash_pop)
        row2.addWidget(btn_stash_list)
        tools_lay.addLayout(row2)

        row3 = QHBoxLayout()
        btn_tag = QPushButton("Create Tag")
        btn_push_tags = QPushButton("Push Tags")
        btn_list_tags = QPushButton("List Tags")
        btn_tag.clicked.connect(self.do_create_tag)
        btn_push_tags.clicked.connect(self.do_push_tags)
        btn_list_tags.clicked.connect(self.do_list_tags)
        row3.addWidget(btn_tag)
        row3.addWidget(btn_push_tags)
        row3.addWidget(btn_list_tags)
        tools_lay.addLayout(row3)

        left_layout.addWidget(grp_tools)
        left_layout.addStretch()

        # RIGHT PANEL — output log
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        self.output_pane = QPlainTextEdit()
        self.output_pane.setReadOnly(True)
        self.output_pane.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.output_pane)
        btn_clear = QPushButton("Clear Output")
        btn_clear.clicked.connect(self.output_pane.clear)
        right_layout.addWidget(btn_clear)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([360, 560])

        # Status bar
        self.statusBar().showMessage(f"Repo: {self.repo_path}")

        # Stylesheet
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold; border: 1px solid #ccc; border-radius: 4px;
                margin-top: 8px; padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }
            QPushButton {
                padding: 5px 12px; border: 1px solid #ccc; border-radius: 3px;
                background: #f5f5f5;
            }
            QPushButton:hover { background: #e0e0e0; }
            QPushButton:pressed { background: #d0d0d0; }
            QPushButton:disabled { color: #aaa; }
            QPlainTextEdit {
                font-family: Consolas, 'Courier New', monospace; font-size: 10pt;
            }
        """)

    # ------------------------------------------------------------------
    # Helper: run a git op, display output, refresh
    # ------------------------------------------------------------------

    def _run_and_display(self, cmd_label, runner_fn):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.output_pane.appendPlainText(f"\n>>> git {cmd_label}  [{ts}]")
        success, output = runner_fn()
        self.output_pane.appendPlainText(output if output else "(no output)")
        if success:
            self.statusBar().showMessage(f"OK: git {cmd_label}", 5000)
        else:
            self.statusBar().showMessage(f"FAILED: git {cmd_label}", 5000)
            # Warn on merge conflicts
            if "CONFLICT" in output:
                QMessageBox.warning(
                    self, "Merge Conflict",
                    "Merge conflicts detected. Resolve them manually, then stage and commit."
                )
        self.refresh_status()

    def _get_checked_files(self):
        files = []
        for i in range(self.file_list.topLevelItemCount()):
            item = self.file_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                files.append(item.text(1))
        return files

    # ------------------------------------------------------------------
    # Refresh file list + branch info
    # ------------------------------------------------------------------

    def refresh_status(self):
        self.file_list.clear()
        # Branch label
        ok, branch = self.git.current_branch()
        if ok:
            ok2, detail = self.git.branch_info()
            tracking = ""
            if ok2:
                for line in detail.splitlines():
                    if line.startswith("*"):
                        tracking = line[2:].strip()
                        break
            self.branch_label.setText(f"Branch: {tracking if tracking else branch.strip()}")

        # File list from porcelain status
        ok, raw = self.git.status()
        if not ok:
            return
        for line in raw.splitlines():
            if len(line) < 4:
                continue
            idx_st = line[0]
            wrk_st = line[1]
            filepath = line[3:]
            display = f"{idx_st}{wrk_st}".strip()
            item = QTreeWidgetItem([display, filepath])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            # Color code
            color_map = {
                "M": QColor(200, 120, 0),
                "A": QColor(0, 150, 0),
                "D": QColor(200, 0, 0),
                "?": QColor(128, 128, 128),
                "R": QColor(0, 100, 200),
                "U": QColor(180, 0, 180),
            }
            dominant = idx_st if idx_st != " " else wrk_st
            c = color_map.get(dominant)
            if c:
                item.setForeground(0, QBrush(c))
                item.setForeground(1, QBrush(c))
            self.file_list.addTopLevelItem(item)

    # ------------------------------------------------------------------
    # Slot methods
    # ------------------------------------------------------------------

    def do_pull(self):
        self._run_and_display("pull", self.git.pull)

    def do_push(self):
        self._run_and_display("push", self.git.push)

    def do_stage_selected(self):
        files = self._get_checked_files()
        if not files:
            self.statusBar().showMessage("No files selected", 3000)
            return
        self._run_and_display(
            f"add -- {' '.join(files)}",
            lambda: self.git.stage_files(files),
        )

    def do_stage_all(self):
        self._run_and_display("add -A", self.git.stage_all)

    def do_unstage_selected(self):
        files = self._get_checked_files()
        if not files:
            self.statusBar().showMessage("No files selected", 3000)
            return
        self._run_and_display(
            f"restore --staged -- {' '.join(files)}",
            lambda: self.git.unstage_files(files),
        )

    def do_commit(self):
        msg = self.commit_msg.text().strip()
        if not msg:
            QMessageBox.warning(self, "Commit", "Please enter a commit message.")
            return
        self._run_and_display(f'commit -m "{msg}"', lambda: self.git.commit(msg))
        self.commit_msg.clear()

    def do_view_log(self):
        self._run_and_display("log --oneline -20", lambda: self.git.log(20))

    def do_diff_selected(self):
        files = self._get_checked_files()
        if not files:
            QMessageBox.information(self, "Diff", "Select a file first (checkbox).")
            return
        for f in files:
            ok, diff_text = self.git.diff_file(f)
            if not diff_text.strip():
                ok, diff_text = self.git.diff_staged_file(f)
            if not diff_text.strip():
                diff_text = "(No changes or file is untracked)"
            dlg = DiffDialog(f, diff_text, self)
            dlg.exec()

    def do_stash_save(self):
        msg, ok = QInputDialog.getText(self, "Stash", "Stash message (optional):")
        if ok:
            self._run_and_display(
                f'stash push -m "{msg}"',
                lambda: self.git.stash_save(msg),
            )

    def do_stash_pop(self):
        self._run_and_display("stash pop", self.git.stash_pop)

    def do_stash_list(self):
        self._run_and_display("stash list", self.git.stash_list)

    def do_create_tag(self):
        tag_name, ok = QInputDialog.getText(self, "Create Tag", "Tag name (e.g. v3.2.7):")
        if not ok or not tag_name.strip():
            return
        tag_msg, ok2 = QInputDialog.getText(self, "Tag Message", "Tag message:")
        if ok2:
            self._run_and_display(
                f'tag -a {tag_name.strip()} -m "{tag_msg}"',
                lambda: self.git.create_tag(tag_name.strip(), tag_msg),
            )

    def do_push_tags(self):
        self._run_and_display("push --tags", self.git.push_tags)

    def do_list_tags(self):
        self._run_and_display("tag --sort=-creatordate", self.git.list_tags)


# ============================================================================
# REPO DETECTION
# ============================================================================

def detect_repo():
    """Find a git repo: script dir, cwd, or ask the user."""
    runner = GitRunner("")
    candidates = [
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
    ]
    for path in candidates:
        runner.repo_path = path
        if runner.is_git_repo():
            return path
    # Fallback: ask user
    path = QFileDialog.getExistingDirectory(None, "Select Git Repository")
    if path:
        runner.repo_path = path
        if runner.is_git_repo():
            return path
    return ""


# ============================================================================
# MAIN
# ============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Light palette (matches VPM app feel)
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

    repo_path = detect_repo()
    if not repo_path:
        QMessageBox.critical(
            None, "Git Helper",
            "No git repository found.\n\nPlace this file inside a git repo and run again,\nor select a valid repo directory."
        )
        sys.exit(1)

    win = GitHelperWindow(repo_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
