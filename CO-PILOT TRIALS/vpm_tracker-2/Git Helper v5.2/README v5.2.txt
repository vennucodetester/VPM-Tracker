Git Helper v5.2

Open with:
Open Git Helper v5.2.cmd

WHAT IS NEW IN v5.2 - "Ask me first"
------------------------------------
v5.1 sometimes decided things on its own (for example, downloading GitHub's
copy over your folder). v5.2 never guesses. Whenever your folder and GitHub
disagree, it stops and shows a popup in plain English:

1. First connection where BOTH your folder and GitHub have files:
   - Upload this folder to GitHub (GitHub's old copy is saved as a milestone)
   - Download the GitHub copy (your files go to Recovery first)
   - Combine both
   - Let me look first (GitHub's copy goes into a side folder)
   - Do nothing

2. The same file changed in both places:
   - Keep MY versions / Keep GITHUB's versions / Choose file by file / Cancel

3. An upload would REMOVE files from GitHub's current copy (for example,
   you deleted files in your folder and clicked Sync):
   - Upload (make GitHub match this folder) / Don't upload
   Removed files always stay in GitHub's history, so they are never lost.

Nothing is ever lost. Every "losing" version is kept - yours in the Recovery
area, GitHub's in GitHub's history or as a milestone.

NEW: Recovery button
--------------------
Shows every snapshot Git Helper preserved for this folder, with dates.
You can put those files back into your folder or open them in Explorer.
Whenever files are preserved, a popup now tells you immediately where they went.

Rev Up
------
Rev Up = save a numbered milestone (rev-001, rev-002, ...) of your folder on
GitHub. Milestones are permanent save points you can always download later
with "Download Rev Up". The app explains this in a popup the first time.

Basic workflow:
1. Choose Destination folder (the project you want backed up - it cannot be
   the Git Helper install folder itself).
2. Paste GitHub repo link.
3. Click Connect or Sync, and answer the popup if one appears.

Support logs are written to:
Destination folder\.git-helper\git-helper-v5.2.log

Recovery snapshots live in:
Destination folder\.git-helper\recovery

The combined support report button writes:
Destination folder\Git Helper v5.2 Support Report.jsonl
