# Git Helper — Review (Round 2) & Remaining Fix

Round-1 review items have all been implemented in `git_helper.py`. This round
confirms that and flags one new latent bug introduced by the threading work.

---

## Round-1 items — all fixed ✅

1. **UI freeze / never hang** — git now runs on a background `QThread`
   (`GitTaskWorker` + `start_git_task`). `refresh_status` no longer fetches
   (instant, local-only). Fetch timeout reduced to 25s. Refresh and Sync do
   network work off the UI thread.
2. **False green when offline** — `RepoState` carries `remote_checked` /
   `remote_reachable`; status shows "Can't reach GitHub — showing local only".
3. **Setup pushes broken state** — on a setup pull conflict, `setup_repo` returns
   early before commit/push; the window opens for conflict resolution.
4. **"Let Me Look" abandons conflict** — `handle_conflicts` loops per file so
   viewing the diff re-asks the choice; only Stop exits.
5. **Restore/Snapshot during conflict** — both guarded by
   `has_unresolved_conflicts()`; whole-project restore commits dirty work first.
6. **Minor** — credential helper tries `manager` then `manager-core`; identity
   checks local + global; single fetch+merge model removes the double fetch;
   deleted-on-one-side conflicts handled via `conflict_sides()` + "Keep Deleted".

Bonus improvement: switched from `pull` to `fetch` + `merge origin/branch`,
avoiding a redundant network round-trip.

---

## Remaining bug (NEW, from the threading work) — fix this

### Completion callbacks may run on the worker thread (can crash intermittently)

**Problem:** the worker's `finished` signal is connected to **plain nested
functions / lambdas**:
- the `finished(result)` closures inside `do_sync` and `_run_and_display`,
- `self.worker.finished.connect(finished_fn)`,
- `self.worker_thread.finished.connect(lambda: self._clear_worker(...))`.

In PyQt6, a signal connected to a callable that is **not a bound method of a
QObject** uses a **direct connection**, so the callback executes in the **worker
thread**. These callbacks do GUI work — `QMessageBox.warning`, `handle_conflicts()`
(opens dialogs), `refresh_status()`. Touching Qt widgets from a non-GUI thread is
undefined behavior: it usually works, then randomly crashes. This reproduces the
original "sometimes it works, sometimes it doesn't" complaint.

Note: `progress`/`details` are safe because they connect to `self.write_progress`
/ `self.write_details`, which are bound methods of the main-thread window (queued).
Only the `finished` and cleanup callbacks are exposed.

**Fix (any one of these):**
- Make the completion handlers real methods/slots on the window instead of nested
  closures, so AutoConnection correctly queues them to the UI thread; or
- Pass `Qt.ConnectionType.QueuedConnection` explicitly on the `finished` and
  `worker_thread.finished` connects; or
- Route results through a dedicated `pyqtSignal` on the window and handle them in a
  bound slot.

Keep `progress`/`details` as-is (already correct).

**Re-test after fix:**
1. Run Sync repeatedly (clean, with edits, with a forced conflict) — no random
   crashes; all dialogs appear normally.
2. Sync while offline — friendly message, no crash.
3. Conflict during Sync — the choose-version dialog opens correctly every time.

---

## Summary

The app now matches the plan and the round-1 fixes. The only outstanding issue is
the thread-affinity of the completion callbacks (above). Fix that and the Git
Helper is solid for daily non-technical use.
