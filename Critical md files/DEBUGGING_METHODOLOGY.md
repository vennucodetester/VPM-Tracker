# DEBUGGING METHODOLOGY — the holy grail

Follow this for EVERY bug report in this project. Each rule below earned its
place by catching a real bug that code-reading alone had missed. If you skip
a step, say so explicitly and why.

---

## Rule 0 — A bug is not understood until it is REPRODUCED

Never fix from a description or from reading code. Build the smallest
harness that makes the bug happen and prints measurable evidence
(numbers, ranges, counts — not "looks right").

- This app is Qt: reproduce headlessly with `QT_QPA_PLATFORM=offscreen`,
  instantiate `MainWindow`, drive it programmatically, print state.
- If you cannot reproduce, you have NOT proven the bug is fixed or absent —
  you have proven your environment differs from the user's. Go to Rule 3.

*Case study:* "plot zoom only zooms Y." The zoom function was provably
correct. A real `QWheelEvent` sent through the view showed X never changed —
reproduced in one command, with numbers.

## Rule 1 — Bisect by LAYER, not by guess

When a feature "doesn't work," split the path into layers and test each
independently until the failure is localized:

1. **The logic** — call the function directly with a stub input. Works?
2. **The delivery** — send the real event/signal through the framework.
   Works?
3. **The state** — is the data the logic reads what you think it is?

The bug lives in the FIRST layer that fails, and almost never in the layer
the report points at.

*Case study:* direct `zoom_plot_at()` call → both axes zoomed (logic OK).
Delivered wheel event → Y only (delivery broken). Diagnosis in two steps:
pyqtgraph's grid extends the axis item's hit-area over the whole plot, so
the Y-axis handler was hijacking every plot-area wheel. The fix was routing,
not zoom math — unfindable by staring at the zoom function.

## Rule 2 — "The code is correct" is not "the feature works"

A correct function that never runs, an event that never arrives, a value
that is immediately overwritten — all render correct code useless. After
any fix, verify the USER-VISIBLE behavior end-to-end, and verify the
NEIGHBORS you might have broken (the 3-zone test: plot=both axes, left
strip=Y, bottom strip=X — all three asserted after the one-line fix).

## Rule 3 — When you can't reproduce: the environment IS the bug

Enumerate every difference between your run and the user's, and test under
THEIR conditions:

- **Launch path.** Terminal launches give pythonw valid std streams;
  double-click gives None. A logging redirect crashed every print() in the
  app — RecursionError on double-click, flawless from every terminal.
  ALWAYS verify launcher behavior by double-clicking the real `.cmd`.
- **Stale process.** Python loads code at process start. An app window
  opened before your edit runs old code forever. Rule: close ALL instances,
  relaunch, confirm via the title-bar build stamp.
- **Wrong copy.** This project has had 3+ folder copies. Check WHICH folder
  the user's launcher/shortcut actually starts before concluding anything.
- **Stale data.** Generator fixes are invisible if saved artifacts
  (diagram.json) predate them and are loaded verbatim. Ask: does this fix
  need a data regeneration/migration to become visible?
- **Stale instructions.** Verify the plan/spec files in the working folder
  match the latest decisions (this folder once had a day-old plan and a
  missing one — the implementer "ignored" instructions it never had).

## Rule 4 — Make the invisible visible FIRST

If diagnostics are being swallowed, fix that before the actual bug —
otherwise you are debugging blind and so is everyone after you.

- Exceptions must never be reduced to a one-line print. Log full
  tracebacks. A `try/except` that leaves a half-built scene must say WHAT
  failed and keep going visibly (error banner), not silently.
- Every "it silently doesn't work" report should end with a NEW permanent
  diagnostic (log line, integrity check, status chip), so the next
  occurrence is diagnosable from the log alone.

*Case studies:* one-line log files (console handler with a None stream ate
every record before the file handler saw it); `update_ui` swallowing the
scene-build crash that blanked the diagram.

## Rule 5 — Hidden state is guilty until proven innocent

When behavior appears "from nowhere" (phantom graph series, wrong defaults,
values the UI doesn't show), hunt for persisted or implicit state: session
JSON, learned-alias DBs, undo snapshots, leftover flags, fuzzy matchers
resurrecting stale entries. The rule that prevents the class: any state
that changes what the user sees must be visible somewhere in the UI.

## Rule 6 — Fix the root cause with the SMALLEST change, then re-verify

- One bug → one minimal, targeted change at the layer where the bisect
  landed. No opportunistic refactors in the same edit.
- Re-run the Rule-0 reproduction (must now pass) AND the neighbor checks
  (must still pass). Paste the measured before/after evidence.
- If the same class of bug can recur elsewhere, add the invariant/check
  that catches the class (see mapping_integrity_check), as a separate item.

## Rule 7 — Claims require evidence

"Done" means: reproduction passed, neighbors passed, verified via the
user's real launch path, evidence (numbers/log lines/screenshot) recorded
next to the checklist item. If any of that is missing, the status is ⚠️
with one line of why — never ✅. Claiming done without evidence cost this
project multiple full days.

---

## The 60-second checklist (print this)

1. ☐ Reproduce with measurable output (offscreen harness).
2. ☐ Bisect: logic → delivery → state. Name the failing layer.
3. ☐ Can't reproduce? Diff the environment: launcher, stale process,
     wrong copy, stale data, stale plans.
4. ☐ Diagnostics swallowed? Fix visibility first.
5. ☐ Behavior from nowhere? Find the hidden state.
6. ☐ Smallest fix at the failing layer.
7. ☐ Re-verify: reproduction + neighbors + real launch path.
8. ☐ Record evidence. Add a class-catching invariant if applicable.
