# Git Helper v4 — Diagnosis & Fix Plan

**Audience:** an LLM (or developer) fixing `git_helper.py` in this folder.
**User's one goal:** *"Paste `git_helper.py` into any folder and reliably push or pull my GitHub work — with as few questions as possible."*

**Repo:** `https://github.com/vennucodetester/VPM-Tracker.git` (default branch: `main`).

---

## Part 1 — Confirmed root causes (verified against the user's real machine and repo)

### Bug A (the failure the user just hit): "download into a new folder" collides with `git_helper.py` itself
The GitHub repo **contains `git_helper.py` at its root** (verified with `git ls-tree origin/main`).
The user's workflow is: create new empty folder → paste `git_helper.py` into it → run it → answer "set up with GitHub" → paste URL.

`setup_repo()` (line ~1274) then does `git init` + `git pull --allow-unrelated-histories origin main`.
Git refuses this pull with:

```
error: The following untracked working tree files would be overwritten by merge:
        git_helper.py
```

Git refuses even when the file content is identical. The app has no handler for this
error (`FRIENDLY_ERRORS` doesn't match it — "would be overwritten by **merge**" pattern
matches, but the suggested fix "Sync can usually fix this by saving first" is wrong for
setup, and setup has no retry path). Result: setup fails every time. **This is the
core "paste anywhere and download" failure.**

### Bug B: new folders under `Documents\VPM-Tracker` attach to the WRONG repo
`C:\Users\silam\OneDrive\Documents\VPM-Tracker` is **itself a git repo** (verified:
`git rev-parse --show-toplevel` from inside it returns that path). The user creates
new working folders *under* it (e.g. `CO-PILOT TRIALS\<new-folder>`).

`GitRunner.is_git_repo()` (line ~179) uses `rev-parse --is-inside-work-tree`, which
returns true for **any subfolder of any repo**. So in a brand-new folder the app:
- skips the setup wizard (thinks a repo already exists — the parent one),
- shows status/changes of the *parent* repo,
- `has_remote()` may be false or point elsewhere → asks for a URL and rewires the
  **parent repo's** origin,
- `git add -A` stages the entire parent tree.

This explains "every time there is a new issue" — behavior depends on where the folder
was created. **Fix:** a folder counts as "the repo" only if
`git -C <folder> rev-parse --show-toplevel` equals `<folder>` itself. If the folder is
inside a *different* repo, say so plainly and offer: "Use this folder as its own new
project (recommended)" vs "Cancel".

### Bug C: download is faked with init+pull instead of a real clone-style flow
"Get my work onto a new machine/folder" is fundamentally `git clone`, but
`setup_repo()` improvises it with `init → add remote → pull --allow-unrelated-histories`.
Consequences:
- Bug A (untracked collision) has no escape hatch.
- If the remote default branch weren't `main`, `remote_branch_exists("main")` is false
  and setup **silently skips downloading**, then commits local files and pushes a brand
  new `main` — looks like "download failed / did nothing".
- `--allow-unrelated-histories` can produce bizarre merge states when the folder has
  extra files.

### Bug D: first-time GitHub sign-in is impossible from inside the app
`_git_env()` sets `GIT_TERMINAL_PROMPT=0` and `GIT_ASKPASS=echo` (correct for
non-interactive use), but on a machine/folder where Git Credential Manager has no
stored token, every fetch/push fails with "could not read username". The friendly
message tells the user to "open GitHub Desktop or a terminal" — a dead end for this
user. The app needs a built-in one-time sign-in step (see Fix 4).

### Bug E: question overload on first run
On a fresh folder the user can be asked, in sequence: identity dialog → "set up
project?" → remote URL → conflict warnings → OneDrive warning → message boxes for each
setup step result. The user experiences this as "it asks a bunch of things and fails".

### Minor issues (fix opportunistically)
- The repo tracks `__pycache__/` and `*.bak*` files (verified in `origin/main`).
  There is no `.gitignore`. Setup should create/append one and `git rm -r --cached __pycache__`.
- `detect_or_setup_repo()` checks candidates `[script_dir, cwd]` — with Bug B either
  can resolve to the wrong repo.
- `current_branch()` returns the literal fallback `"main"` when HEAD is unborn, which
  masks branch mismatches.
- Whole tree lives in OneDrive → occasional `index.lock` failures (already has a
  friendly message; keep the `attrib +P -U` protection offer).

---

## Part 2 — The fix plan

Keep the existing v3 app (UI, Sync loop, conflict dialogs, restore points are fine).
Replace only the **startup/first-run flow** and add a **sign-in fallback**. Four fixes,
in priority order:

### Fix 1 — Correct repo detection (fixes Bug B)
In `GitRunner`, add:

```python
def repo_toplevel(self):
    r = self._run(["rev-parse", "--show-toplevel"])
    return os.path.normcase(os.path.abspath(r.output.strip())) if r.success else ""

def is_own_repo(self):
    top = self.repo_toplevel()
    return top != "" and top == os.path.normcase(os.path.abspath(self.repo_path))
```

In `detect_or_setup_repo()` replace `runner.is_git_repo()` with `runner.is_own_repo()`.
If `is_git_repo()` is true but `is_own_repo()` is false, show ONE dialog:

> "This folder is inside another Git project (`<toplevel>`), but is not its own
> project. Make this folder its own separate project connected to GitHub?"
> [Set up this folder] [Cancel]

"Set up this folder" proceeds to Fix 2 (git handles nested repos fine; the inner
`.git` takes precedence). Never operate on the parent repo implicitly.

### Fix 2 — Real "Download from GitHub" first-run wizard (fixes Bugs A, C, E)
Replace `setup_repo()` with a single-dialog wizard. One window, asked once:

1. **GitHub URL** (text field, pre-filled with
   `https://github.com/vennucodetester/VPM-Tracker.git` if a sibling/previous config
   suggests it — optional nicety).
2. **Name + email** fields, shown only if identity isn't already configured
   (check global config first — usually it is, so usually hidden).

Then run this sequence (all non-interactive, progress shown in the existing progress
pane, NO further dialogs unless something truly needs a decision):

```
git init
git remote add origin <url>          (or set-url if exists)
git fetch origin                      → on auth failure, go to Fix 4, then retry once
default_branch = parse `git ls-remote --symref origin HEAD`
                                      (line "ref: refs/heads/<name>\tHEAD"; fallback "main")
git checkout -b <default_branch>      (creates the local branch on the unborn HEAD)
```

**Collision-safe download** (the key new logic — replaces `pull --allow-unrelated-histories`):

```python
remote_files = set(git ls-tree -r --name-only origin/<default_branch>)
for f in remote_files that exist locally (untracked, since index is empty):
    if local file content hash == git hash-object of remote blob (git cat-file):
        # identical (e.g. the pasted git_helper.py) — safe to let checkout overwrite
        delete the local copy
    else:
        rename local file to f + ".mine-<YYYYMMDD-HHMM>"   # keep the user's version
git reset --hard origin/<default_branch>       # populate working tree from GitHub
git branch --set-upstream-to origin/<default_branch>
```

Simplest identical-content check: `git hash-object <local_file>` vs the blob hash from
`git ls-tree -r origin/<branch>` — pure string compare, no content reading in Python.

After download: if any `.mine-*` backups were created OR the folder had extra files not
on GitHub, run a normal **Sync** (existing code path) to commit and push them up. Report
one plain-English summary: *"Downloaded 23 files from GitHub. 1 of your local files
differed and was kept as `X.mine-...`. Your extra files were sent up to GitHub."*

**Do NOT** rename the branch to `main` (`set_branch_main` at startup — delete that call);
use whatever the remote default branch is, everywhere `"main"` is currently hardcoded
(`remote_branch_exists`, `pull_no_edit`, etc. already mostly use `current_branch()` —
audit the remaining literals).

### Fix 3 — `.gitignore` hygiene
During setup (and once for the existing repo), ensure `.gitignore` contains:

```
__pycache__/
*.pyc
*.bak*
```

and untrack already-committed junk: `git rm -r --cached __pycache__` (ignore failure if
absent). Commit as "Add .gitignore". This prevents merge noise on `.pyc` files that
differ per machine.

### Fix 4 — Built-in one-time GitHub sign-in (fixes Bug D)
When any fetch/push fails with an auth-related error (`authentication failed`,
`could not read username`, `terminal prompts disabled`, `repository not found` on a
private repo), show one dialog:

> "GitHub needs you to sign in once on this computer. A black window will open —
> follow the sign-in steps in your browser, then come back and click Sync."
> [Sign in now] [Cancel]

"Sign in now" launches a **visible** console (do NOT use `CREATE_NO_WINDOW`, do NOT set
`GIT_TERMINAL_PROMPT=0` for this one call):

```python
subprocess.Popen(
    ["cmd", "/k", "git", "fetch", "origin"],
    cwd=repo_path,
    creationflags=subprocess.CREATE_NEW_CONSOLE,
)
```

Git Credential Manager pops the browser OAuth flow, stores the token, and every later
non-interactive call works. (Prefer `git credential-manager github login` if present;
plain `git fetch` in a console is the reliable fallback.)

---

## Part 3 — What NOT to change

- The Sync task loop, conflict resolution dialogs, restore points, snapshot/tag logic,
  and the threading model (`task_result_ready` / `worker_cleanup_ready` queued signals)
  are working — leave them alone.
- Keep `GIT_TERMINAL_PROMPT=0` etc. for all normal operations; only the explicit
  sign-in console (Fix 4) is interactive.
- Keep the OneDrive warning and `attrib +P -U .git` protection.

---

## Part 4 — Acceptance tests (run all before declaring done)

Use a throwaway GitHub repo or this real one; test folders both **inside** and
**outside** `Documents\VPM-Tracker`.

1. **The headline scenario:** new empty folder (inside the OneDrive VPM-Tracker tree),
   paste `git_helper.py`, run it, paste the URL. Expected: everything downloads, no
   error, at most 2 dialogs total (nested-repo confirm + wizard), status "Green: Up to
   date". Verify `git rev-parse --show-toplevel` == the new folder.
2. Same, but first **edit one line** of the pasted `git_helper.py` before running.
   Expected: download succeeds, the edited copy is preserved as
   `git_helper.py.mine-<stamp>`, GitHub's copy is in place.
3. Same, in a folder **outside** any repo (e.g. Desktop). Expected: no nested-repo
   dialog, straight to wizard, clean download.
4. New folder with **extra files** (e.g. a `notes.txt`). Expected: download succeeds
   and `notes.txt` is committed and pushed to GitHub automatically.
5. **Fresh machine simulation:** temporarily clear the GitHub credential
   (`cmdkey /list` → delete the git:https://github.com entry, or
   `git credential-manager github logout`). Run setup. Expected: the sign-in dialog +
   console appears, browser auth completes, retry succeeds.
6. Existing repo folder (this one): open the app, make an edit, Sync. Expected:
   unchanged v3 behavior — commit, merge, push, green status.
7. Remote with default branch **not** named `main`: setup downloads it correctly and
   never renames or pushes a stray `main`.
8. Run the app in a subfolder of an existing repo and click **Cancel** at the
   nested-repo dialog. Expected: app exits without touching the parent repo (verify
   `git -C <parent> status` and `git -C <parent> remote -v` unchanged, no stray `.git`
   in the subfolder).

---

## Part 5 — Implementation order

1. Fix 1 (repo detection) — small, unblocks everything else.
2. Fix 2 (download wizard) — the bulk of the work; build `default_branch` detection
   and collision-safe checkout as separate `GitRunner` methods so they're testable.
3. Fix 4 (sign-in console) — wire into both the wizard and Sync's auth-failure path.
4. Fix 3 (.gitignore) — trivial, do during setup and on first run in existing repos.
5. Run all acceptance tests in Part 4.
