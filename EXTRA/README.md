# VPM Tracker

Double-click `Open VPM Tracker.cmd` to run the tracker.

The visible app revision comes from the newest local git tag named like
`rev-2026.07.11-r1`. If no tag exists yet, the app falls back to
`2026.07.08-r1`.

Use `Rev Up VPM Tracker.cmd` after a verified change. It saves a recovery
snapshot in `.git-helper\recovery`, commits the current app state on `main`,
creates the next `rev-YYYY.MM.DD-rN` tag, and writes support events to
`.git-helper\logs\Support Report.jsonl`.

Local usage logs, save files, caches, and recovery snapshots are intentionally
ignored by git.
