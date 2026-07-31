# Part H — Timeline (bar chart) upgrades: SCOPE ONLY (2026-07-11)

**Audience:** the implementing LLM. Scope approved by the user; no code yet.
**Working copy:** THIS folder (`VPMTracker\VPM Tracker\`). CRLF line endings.
**File:** all items land in `ui/timeline_pane.py` unless noted.

**Existing model facts to build on (models/task_node.py):**
- `vave_potential` / `vave_realized`: Optional[float]; None = plain execution
  task. NOTHING auto-calculates between them (user rule).
- `vave_display_potential()` / `vave_display_realized()`: a node's own value,
  or the ROLLED-UP sum from children for parents — already used by the grid.
- `vave_total_potential()` / `vave_total_realized()`: subtree totals.
- VAVE visibility is toggled per project (grid: `set_vave_enabled`); the
  timeline must follow the same flag (get it from the ProjectWidget/Options
  state, not a new setting).
- Baseline data for slips: `baseline_end`, `baseline_duration`, `revisions`
  (list of {rev, date, end, slip, reason}).
- Critical chain: `utils/critical_path.py` `CriticalPathAnalyzer(roots).analyze()`
  → `critical_path_ids` / `critical_parent_ids` (already used by Visuals tab).

**User decisions (final):**
- Slip visuals exist but are OFF by default behind a checkbox — he does NOT
  want slips visible to leadership unless he chooses.
- Critical-chain outline: yes.
- Milestone red/green coloring: SKIPPED (user doesn't use milestones).
- Export header: yes.
- VAVE $ in labels and a bottom dollar bar: yes — including parent rollups
  (his point: "all parents of $ cells get an automatic addition in the bars";
  the rollup already exists in the model — the bars must show it).

---

## ✅ IMPLEMENTED 2026-07-12 (all items). See per-item "Verified" notes below.
## Deviations from scope:
## - H1 $ format: user chose WHOLE dollars on bars (`$18,000`) over the grid's
##   `.1f` (`$18,000.0`). Bars use `f"${v:,.0f}"`; grid cells keep money_text().
## - Sync: added `self.timeline.refresh()` to project_widget.set_vave_enabled
##   and the undo-restore path. The timeline only listened to item_changed_signal,
##   which the VAVE toggle does NOT emit, so the dollar bar/labels would not have
##   updated on toggle without this. (No new setting; VAVE-on is still read from
##   the grid's Potential column via TimelineCanvas._vave_on.)

## H1. VAVE dollars on bar labels (leafs AND parents)
# ✅ Verified: leaf `Trial 2 ($0 / $18,000)`; parent collapsed bar rolls up to
#    the summed value; task with no $ = name only; VAVE off = name only. Applied
#    to all three label sites (leaf, collapsed group, expanded box) + tooltip line.

When the project is VAVE-enabled and Labels are on:
- Any bar whose node has a non-None `vave_display_*` value gets the label
  `Name ($realized / $potential)` — e.g. `Trial 2 ($0 / $18,000)`.
  Use the same `money_text()` formatting as the grid (import or replicate).
- Applies to ALL THREE bar kinds: leaf bars, collapsed group bars, and
  expanded group box labels — parents use their rolled-up display values.
- Tasks with no $ anywhere beneath them: label unchanged (name only). VAVE
  off: labels exactly as today.
- Tooltip: append a `Potential $X · Realized $Y` line when values exist.

## H2. Bottom "overall dollar bar"
# ✅ Verified: DollarBar above the controls strip; text `Realized $6,500 of
#    $28,700 (23%)`; Inbox excluded; hidden when VAVE off or potential total 0;
#    green(realized)/amber(remaining); refreshes on item_changed_signal.

A slim horizontal stacked bar in the TimelineContainer, directly above the
controls strip, visible only when the project is VAVE-enabled and totals > 0:
- Segment 1 GREEN (`C_DONE #43A047`): total realized across all roots
  (`sum(vave_total_realized)` — Inbox excluded like everything else).
- Segment 2 AMBER (`C_PROGRESS #FFB300`): remaining = max(potential − realized, 0).
- Text on/next to it: `Realized $6,500 of $28,700 (23%)`; guard division by 0.
- Same color language as task bars: green = done/banked, amber = pending.
- Refresh on `item_changed_signal` (same hook the canvas already uses).

## H3. Slip shadows — behind an OFF-by-default "Slips" checkbox
# ✅ Verified: `Slips` button starts UNCHECKED every session (never persisted on).
#    Leaves with baseline_end != end_date get a ~40% ghost to baseline_end + a
#    `+Nd` label (red when late); tooltip appends revision_trail(); parents get
#    no ghost. Export reads show_slips at export time -> excluded unless on.

New checkable button `Slips` in the controls strip (default UNCHECKED,
NOT persisted checked across sessions — always starts off, deliberate):
- For each leaf with `baseline_end` differing from current `end_date`: draw a
  ghost — thin gray bar (same start, ending at `baseline_end`, ~40% height,
  drawn under the real bar) — plus a small `+Nd` label at the bar's right end
  (N = calendar-day diff; red text when positive).
- While Slips is on, bar tooltips append the task's `revision_trail()` so the
  logged reasons surface on hover.
- Parents: no ghost (their dates are rollups); leaves only.
- Slips must NOT appear in the PNG export unless the checkbox is on at export
  time (the leadership-safety rule).

## H4. Critical-chain outline
# ✅ Verified: `Critical` button (default off). Outline set == the Visuals-tab
#    CriticalPathAnalyzer result (critical_path_ids | critical_parent_ids),
#    asserted equal in a headless test. 2px #B71C1C over leaf bars + group boxes;
#    analysis re-run only while the toggle is on; legend gains `▭ critical chain`.

New checkable button `Critical` in the controls strip (default off):
- Run `CriticalPathAnalyzer` on the (non-Inbox) roots; bars whose node id is
  in the critical set get a 2px dark-red (`#B71C1C`) outline over their normal
  fill color. Group boxes on the chain: same outline color.
- Re-run analysis on `item_changed_signal` refresh only while the toggle is
  on (it's O(n) but no need to pay it when hidden).
- Legend gains `▭ critical chain` while active.

## H5. Export header block
# ✅ Verified: title band above the month header — bold `name — Jul 12, 2026`;
#    `1 of 4 tasks done · 1 late · Next milestone: Launch Jul 17` (adds
#    `· N on critical chain late` when Critical is on); green VAVE line when
#    enabled. Legend extends with Slip/Critical entries per toggle. Project name
#    read live from the enclosing ProjectWidget (survives renames).

`export_image()` gains a title band above the month header:
- Line 1 (bold): project name — export date.
- Line 2: `X of Y tasks done · Z late` (+ ` · N on critical chain late` when
  H4 data available) · next milestone name+date if any zero-duration task
  exists, else omit.
- Line 3 (only when VAVE-enabled): `VAVE: Realized $A of $B (P%)` in green.
- Respect current toggles: slips/critical only included when their buttons
  are on. Legend row extends accordingly.

## Out of scope (rejected or deferred by user)
- Milestone red/green coloring (user skipped — revisit only if he starts
  using milestone rows).
- Pace/progress line, weekend shading, color-by-phase, ⏳ waiting-on badges
  on bars — not requested; do not add.
- Any auto-calculation between Baseline/Proposed/Potential — forbidden.

## Acceptance checks — ALL PASSED (headless, 2026-07-12)
# 1✅ VAVE off: labels name-only, no dollar bar (render path untouched).
# 2✅ leaf `Trial 2 ($0 / $18,000)`; parent rolls up summed; no-$ task name only.
# 3✅ dollar bar = grid rolled-up root totals; updated live after editing Realized $.
# 4✅ Slips off default (no ghosts, clean export); on = ghosts + +Nd + trail tips;
#    export gated on the toggle at export time.
# 5✅ Critical set == Visuals-tab analyzer ids (asserted equal).
# 6✅ Export PNG shows the header band with correct counts/totals (888x238 grew
#    by the title band vs the plain header).
# 7✅ Real pre-VAVE .vpmt backup boots in MainWindow, renders, exports; VAVE-off
#    everywhere (dollar bar hidden, legacy nodes have vave fields = None).
1. VAVE off → timeline pixel-identical to today; no dollar bar.
2. VAVE on: leaf with $ shows `Name ($r / $p)`; its parent's collapsed bar
   shows the SUMMED values; task without $ shows name only.
3. Dollar bar math matches the grid's rolled-up root totals; updates after
   editing a Realized $ cell.
4. Slips checkbox off (default): no ghosts anywhere, exports clean. On:
   ghosts + `+Nd` + reasons in tooltips; export includes them only while on.
5. Critical toggle outlines the same ids the Visuals tab's analyzer reports.
6. Export PNG shows the header block with correct counts/totals.
7. Old .vpmt files (no vave fields) behave as VAVE-off everywhere.
