# Git Helper — Rebuild Plan (Smart Sync + Safe Restore)

A plan any LLM can follow to rebuild `git_helper.py` into a tool a non-technical
user can run with confidence. **No code is given here on purpose** — implement it
in PyQt6 to match the existing app's style.

---

## 1. Background & Goal

The current app exposes raw git buttons (Pull, Stage All, Commit, Push) that each
run **one** git command and give up the moment git refuses. In real use git
refuses constantly ("commit first", "pull first", "rejected", merge editor opens,
identity missing). The non-expert user is left staring at cryptic output with no
idea what to do next.

**Goal:** the user does almost nothing. One **Sync** button figures out the
correct sequence for the current situation and runs it. A **traffic light** shows
status in plain English. A **Restore Points** view lets them roll back safely. The
only manual setup is creating the GitHub repo and pasting its link once.

**Audience for the running app:** a non-IT user. Every message must be plain
English, never raw git jargon unless tucked into a collapsible "details" area.

---

## 2. Core Principles (apply everywhere)

1. **Never give up at the first refusal.** Inspect git's state, decide the next
   corrective step, do it. Chain steps until done or truly stuck.
2. **Never hang.** Run every git command with an environment that forbids
   interactive prompts and editors:
   - disable the editor so merge/commit never opens vim,
   - disable terminal auth prompts so a missing login fails fast instead of
     hanging, then show a clear "you need to log in once" message.
   - always use non-interactive merge (no-edit) with an auto-generated message.
3. **Never destroy the user's work.** Prefer additive, reversible operations.
   No `reset --hard`, no force-push, no history rewriting in any user-facing flow.
4. **Explain in plain English.** Map every known git error to a friendly sentence
   and, where possible, an automatic fix. Keep raw output in a collapsible panel.
5. **Self-heal on startup.** Check prerequisites and fix what can be fixed
   silently before the user touches anything.

---

## 3. Startup: Pre-flight Self-Heal

Run these checks when the app opens, before showing the main screen. Fix silently
where possible; only prompt the user when genuinely needed.

1. **Git installed?** If not, show a single clear message with a download link and
   stop. Everything else depends on this.
2. **Identity set?** (`user.name`, `user.email`). If missing, ask once for a name
   and email, set them globally, remember them. Never let a commit fail for this.
3. **Inside a git repo?** If yes → go to main screen. If no → run First-Time Setup
   (section 5).
4. **Remote configured?** If repo exists but has no `origin`, ask for the GitHub
   link and add it.
5. **Default branch name** is consistent (standardize on `main`).
6. **OneDrive / cloud-sync check** (section 4) — warn and offer protection.
7. **Credential helper present** (so the user logs in once, not every time). On
   Windows, ensure Git Credential Manager is the helper if available.

Show a short startup summary only if something was changed or needs attention;
otherwise go straight to the main screen.

---

## 4. OneDrive / Cloud-Sync Handling (root cause of "sometimes it works")

A repo inside OneDrive/Dropbox/Google Drive corrupts intermittently because the
cloud client syncs the hidden `.git` folder mid-operation. This is the most likely
cause of random failures.

**Detect:** check whether the repo path sits under a known cloud-sync folder
(OneDrive, Dropbox, Google Drive — match common path patterns and environment
variables).

**If detected, offer, in order of preference:**
1. **Recommended:** explain in one short paragraph why cloud + git is risky, and
   offer to help the user keep projects in a plain local folder (e.g.
   `C:\Projects`). GitHub becomes the backup instead of OneDrive.
2. **If the user stays in OneDrive:** mark the `.git` folder as "always keep on
   this device / do not free up space" so the cloud client stops touching it as
   aggressively. State clearly this reduces but does not eliminate the risk.

**Hard rule to surface:** never have the same cloud-synced folder open on two
computers at once. If multi-machine use is needed, the correct path is GitHub
(clone on each machine to a *local* folder), not OneDrive.

Make this a non-blocking warning with a "don't show again" option, plus a
permanent status chip ("⚠ In OneDrive") so it's never forgotten.

---

## 5. First-Time Setup (new project folder) — must handle existing remote content

The current setup assumes the GitHub repo is empty. It usually isn't (users create
a repo with a README/license on the website first), so the initial push is
rejected and setup dies. Fix the flow to handle both cases.

Steps after the user pastes the GitHub link:

1. `init` the folder if needed; set branch to `main`; add `origin`.
2. **Determine if the remote already has commits** (fetch and check). Two paths:
   - **Remote is empty:** stage all → commit → push and set upstream. Done.
   - **Remote has content (README etc.):** pull the remote first, reconciling
     unrelated histories non-interactively, then stage → commit → push. If the
     same file exists on both sides and conflicts, route to the Conflict flow
     (section 7).
3. Confirm success in plain English; if any step failed, show the friendly
   explanation and the corrective option, never a dead end.

---

## 6. The Smart Sync Button (the heart of the app)

Replace the separate Pull / Stage / Commit / Push buttons with **one primary
"Sync" button**. Keep the individual actions only inside an "Advanced" section for
power use. Sync runs this recipe, re-checking state between steps:

1. **Ensure identity** (from pre-flight; double-check).
2. **Save local work:** if there are changes, stage everything and commit. Use the
   note the user typed if any; otherwise auto-generate one (e.g.
   `Update <date> <time>`).
3. **Get GitHub's latest:**
   - If the working tree is clean, pull (non-interactive, no editor).
   - If a pull would collide with uncommitted leftovers, set them aside
     automatically (stash), pull, then restore (stash pop). If the restore
     conflicts, route to Conflict flow.
   - Reconcile divergent branches with a defined, non-interactive strategy so it
     never opens an editor or stops on "you have divergent branches".
4. **If GitHub was ahead and merged cleanly,** continue.
5. **Send your work up** (push). If push is rejected because the remote moved again
   between steps, loop back to step 3 once or twice, then stop with a clear message
   if still stuck.
6. **Report** in plain English with a single summary line and a green light.

**Progress display:** show each phase as a friendly line as it happens
("Saving your changes…", "Getting GitHub's latest…", "Sending your work up…",
"✅ Everything is in sync"). Keep raw git output in a collapsible "details" panel.

**Idempotent & safe:** running Sync when there's nothing to do should simply say
"Already up to date" and change nothing.

---

## 7. Status Traffic Light (always visible)

A prominent indicator at the top, computed from local vs remote state
(ahead/behind/dirty/conflict):

- 🟢 **Up to date** — local matches GitHub, nothing uncommitted.
- 🟡 **You have changes not sent yet** — show count; primary action: Sync.
- 🔵 **GitHub has newer changes** — behind remote; primary action: Sync.
- 🔴 **Conflict — needs your choice** — route to Conflict flow.
- ⚠ **In OneDrive** — persistent caution chip (section 4).

Refresh the light after every operation and on a manual Refresh.

---

## 8. Conflict Handling (plain English, no git jargon)

A conflict = the same file was changed in two places. The user must NOT be exposed
to conflict markers or `git mergetool`. Offer, per conflicted file:

- **Keep mine** (the user's version),
- **Keep GitHub's** (the incoming version),
- **Let me look** (open a simple side-by-side or the diff viewer that already
  exists, read-only, to help them decide).

After choices are made, finish the merge automatically (stage resolved files,
commit with an auto message, continue the Sync). Always offer a one-click
"undo this merge" escape that returns to the pre-merge state safely.

---

## 9. Restore Points / Revisions (user explicitly wants this)

Every successful Sync is already a save point. Build a friendly layer on top:

1. **Restore Points list:** show commits as plain rows — date, time, and the note —
   newest first. Hide hashes behind a "details" toggle. Tagged snapshots appear
   with their friendly name.
2. **Snapshot now:** one button = commit current state + a named bookmark (tag)
   the user types ("before big change"). For moments before something risky.
3. **Go back to a version — SAFELY (critical):** restoring an old version must be
   **additive**, never history-erasing. Implement restore as: bring the chosen
   version's files back into the working folder, then make that a **new** commit on
   top of history (and Sync it). This way:
   - history is never rewritten (safe with the remote, no force-push),
   - if the user doesn't like the result they just restore again,
   - it works the same whether they restore one file or the whole project.
   Explicitly avoid `reset --hard` / history rewriting in this flow.
4. **Restore scope:** let the user pick **one file** or the **whole project**.
5. **Always confirm** with a plain-English preview ("This will bring back the
   version from June 10 and save it as a new change. Your current version stays in
   history. Continue?").

---

## 10. Error → Plain-English Mapping (build a lookup)

Maintain a table that turns known git failures into a friendly message + the
automatic or one-click fix. At minimum cover:

- "would be overwritten by merge" / local changes → auto-stash then retry.
- "rejected … fetch first" / "remote contains work you do not have" → pull then
  push (the Sync loop already does this).
- "divergent branches … need to specify how to reconcile" → set strategy, retry.
- "Please tell me who you are" → set identity, retry.
- "Authentication failed" / timeout on push/pull → "You need to sign in to GitHub
  once" with guidance; do not hang.
- "unrelated histories" → reconcile with the explicit allow flag (setup case).
- "index.lock exists" → likely OneDrive; explain, offer to remove the stale lock
  safely (only if no git process is running) and surface the OneDrive warning.
- merge conflict markers present → route to Conflict flow (section 8).

Anything unmapped: show the friendly "something unexpected happened" message plus
the raw output in the details panel, and never leave the repo in a half-finished
merge/rebase state (abort cleanly if a step fails irrecoverably).

---

## 11. UI Layout (keep it close to today's app)

- **Top:** traffic-light status + repo name + OneDrive chip + Refresh.
- **Center, primary:** the big **Sync** button and the live progress lines.
- **Commit note field:** optional; if empty, Sync auto-generates the note.
- **File list:** show changed files in plain status words (New / Edited / Deleted),
  colored, read-only for daily use.
- **Restore Points panel:** list + "Snapshot now" + "Go back to a version".
- **Advanced (collapsed):** the original granular buttons (stage selected, unstage,
  diff, manual pull/push, stash, tags) for anyone who wants them.
- **Details panel (collapsed):** raw git output for troubleshooting.
- Keep the existing always-visible instructions, updated for the Sync workflow.

---

## 12. Implementation Notes for the LLM

- Build on the existing `GitRunner` subprocess wrapper; extend it with the new
  state-inspection helpers (ahead/behind counts, dirty check, remote-empty check,
  in-progress merge check) rather than rewriting from scratch.
- Every git invocation: no-window, captured output, non-interactive env, sensible
  timeout, and a clear timeout message.
- Make each high-level flow (Sync, Setup, Restore, Conflict) a single function
  that returns a structured result (what happened, success, friendly summary) so
  the UI layer stays thin.
- Keep all destructive git verbs out of user-facing paths. If a low-level verb is
  ever needed, guard it behind Advanced with an explicit confirmation.
- Write friendly messages as data (the mapping table in section 10) so they're easy
  to tune without touching logic.

---

## 13. Acceptance Tests (the app is "done" when all pass)

1. **New folder, empty GitHub repo:** paste link → Sync → everything pushed.
2. **New folder, GitHub repo already has a README:** paste link → Sync → histories
   reconciled, pushed, no dead end.
3. **Local edits + GitHub also changed:** Sync → auto-saves, pulls, merges, pushes,
   ends green.
4. **Same file changed both places:** Sync → Conflict flow with Keep Mine / Keep
   GitHub's → finishes cleanly.
5. **No identity configured:** first action sets it without failing.
6. **Not logged in:** clear "sign in once" message, no hang.
7. **Repo inside OneDrive:** warning shown + protection offered.
8. **Restore a single file** and **restore whole project:** old version returns as a
   new change; history intact; can be undone again.
9. **Nothing to do:** Sync says "Already up to date" and changes nothing.
10. **Any unmapped error:** friendly message + raw details + repo left in a clean
    (non-half-merged) state.
