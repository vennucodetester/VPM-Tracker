# Part I — Progress fill on group bars + % labels: SCOPE ONLY (2026-07-12)

**Audience:** the implementing LLM. Read
`Critical md files\IMPLEMENTATION_METHODOLOGY.md` first; scope authority rules
from Part H apply. All changes in `ui/timeline_pane.py` (helper math may go in
`models/task_node.py`). No new columns, menus, or settings.

**User's goal (his words, paraphrased):** dollars may not move week to week,
but tasks complete — the chart must SHOW that movement. Chosen options:
dual-color progress fill on group bars (Option 1) + the percentage in labels
and the export header (Option 4). Options 2 (dollar-bar work stripe) and 3
(last-week tick) were discussed and DEFERRED — do not build them.

---

## I1. The progress number (one shared function — build this first)

`progress_fraction(node) -> Optional[float]` (suggest on TaskNode or a
timeline helper):

- Collect all LEAF descendants of `node` (a leaf = no children), excluding
  the Inbox subtree and leaves with no start/end dates.
- Weight = each leaf's workday duration (`int(node.duration)`; guard
  ValueError → weight 1).
- `fraction = sum(weight of leaves with status == "Completed") / sum(all weights)`.
- Return None when there are no dated leaves (→ no fill, no % label).
- DURATION-WEIGHTED on purpose (user decision): finishing one 20-day task
  must move the number more than ten 1-day tasks. Do NOT count tasks equally.
- Pure read-only math — no caching, no stored field, recomputed per paint
  (chart already repaints per refresh; n is small).

## I2. Dual-color fill on COLLAPSED group bars

The collapsed group bar (currently one flat `C_SUMMARY` slate bar):

- Left portion, `fraction` of the bar width: `C_DONE` green.
- Remainder: `C_SUMMARY` slate as today (NOT amber — amber means "active
  leaf", and the undone remainder of a phase is not necessarily active).
- 1px divider line at the boundary (slate darker) so 49% vs 51% reads.
- fraction None → bar unchanged (all slate). fraction 1.0 → all green.
- Rounded-rect corners must still look right: draw the slate full bar first,
  then the green portion clipped to the left part (same rounding trick the
  DollarBar uses).
- EXPANDED group boxes stay neutral outlines — no fill (Part H bug 2 lesson:
  tinting boxes floods the chart). Their progress shows via the label (I3).
- Leaf bars: UNCHANGED. A leaf has no children to fill from; its color stays
  pure status. (No per-task %-complete field exists and none is to be added.)

## I3. Percentage in bar labels

- Every GROUP label (collapsed bar and expanded box) gains the percent before
  the VAVE suffix: `Cassette VAVE activities · 45% ($0 / $60)`.
  Non-VAVE projects: `Phase 1 · 45%`.
- Percent = `round(fraction * 100)`; omit entirely when fraction is None.
- Applies in live paint AND `export_image` label column.
- Leaf labels unchanged.

## I4. Export header line

In `_export_header_lines`:
- Non-VAVE: add line `Progress: 45% of work complete` (project-level
  fraction across all non-Inbox roots).
- VAVE-enabled: merge into the existing VAVE line:
  `VAVE: 45% of work complete · Realized $6,500 of $60,000 (11%)`.
  Keep the money percent AND the work percent clearly separate — they answer
  different questions and the user's whole point is showing work movement
  while money stands still.

## Explicitly out of scope
- Option 2 (work stripe under the DollarBar) and Option 3 (last-week tick /
  weekly snapshots) — deferred by user, need fresh approval.
- Any stored/persisted progress history; any per-leaf %-complete field.
- Recoloring leaves, boxes, or the palette (Part H bug report restored these;
  do not touch).

## Acceptance checks (offscreen)
1. Parent with two dated leaves: 20d Completed + 5d In Progress →
   `progress_fraction == 0.8` (duration-weighted, NOT 0.5).
2. Dateless-leaves-only parent → fraction None: slate bar, no % in label.
3. Collapsed bar paint: render via `export_image` to QPixmap; sample pixels —
   left region green (#43A047), right region slate, for a 50% fixture.
4. Labels: group with fraction 0.45 and VAVE on →
   `... · 45% ($0 / $60)`; VAVE off → `... · 45%`; leaf label has no %.
5. Export header: VAVE file shows the merged line with both percents;
   non-VAVE shows `Progress: N%`.
6. Inbox tasks never affect any fraction.
7. Regression: leaf colors, expanded boxes, DollarBar, slips gating —
   all exactly as after the Part H bug fixes.

---

## Implementation result (2026-07-12)

Done in `ui/timeline_pane.py`.

- `progress_fraction(node)` added as read-only, duration-weighted leaf math.
- Collapsed group bars now draw slate remainder plus green completed-work fill
  with a divider.
- Group labels show `N%` before the VAVE dollar suffix; leaf labels are
  unchanged.
- Export header adds `Progress: N% of work complete` for non-VAVE projects.
- VAVE export header merges work progress and money progress:
  `VAVE: N% of work complete - Realized $A of $B (P%)`.

Verified headlessly:

```text
ACCEPT1_fraction=0.800
ACCEPT2_fraction=None
ACCEPT3_pixels=left:#43a047,right:#37474f
ACCEPT4_group_vave_label=Cassette VAVE activities - 45% ($0 / $60)
ACCEPT4_group_nonvave_label=Cassette VAVE activities - 45%
ACCEPT4_leaf_label=Done work
ACCEPT5_nonvave_header=P - Jul 12, 2026 | 1 of 2 tasks done | Progress: 45% of work complete
ACCEPT5_vave_header=P - Jul 12, 2026 | 1 of 2 tasks done | VAVE: 45% of work complete - Realized $6,500 of $60,000 (11%)
ACCEPT6_roots_fraction=0.455,root_fraction=0.455
ACCEPT7_future_slipped_leaf_color=#ffb300
EXPORT_SMOKE_BYTES=3592
RESULT=PASS
```
