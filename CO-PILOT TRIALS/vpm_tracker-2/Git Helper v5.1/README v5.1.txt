Git Helper v5.1

Open with:
Open Git Helper v5.1.cmd

This rev keeps Git Helper in this folder and manages only the destination folder
you choose inside the app. It does not search parent folders, and it blocks the
Git Helper install folder from being used as the destination.

Basic workflow:
1. Choose Destination folder.
2. Paste GitHub repo link.
3. Click Connect or Sync.

If the GitHub repo already has files and the destination has older local files,
Git Helper downloads the GitHub copy and preserves the older local files under:
Destination folder\.git-helper\recovery

Support logs are written to:
Destination folder\.git-helper\git-helper-v5.1.log

The combined support report button writes:
Destination folder\Git Helper v5.1 Support Report.jsonl
