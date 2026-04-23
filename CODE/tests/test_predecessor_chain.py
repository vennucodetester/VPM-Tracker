"""
Integration test for predecessor propagation across a 3-link chain.

Reproduces the user-reported bug: editing A's start/end/duration must ripple
through B (pred=A) and C (pred=B) in a single scheduler pass — no second
click needed.

Run from the CODE directory:
    python tests/test_predecessor_chain.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "vpm_tracker"))

from models.task_node import TaskNode  # noqa: E402
from utils.scheduler import schedule  # noqa: E402
from utils.workday_calculator import WorkdayCalculator as WC  # noqa: E402


def _make_chain(a_start="2026-01-05", a_end="2026-01-09",
                b_start="2026-01-12", b_end="2026-01-14",
                c_start="2026-01-15", c_end="2026-01-16"):
    """Build three independent root tasks A, B, C with B->A, C->B links."""
    a = TaskNode("A")
    a.start_date, a.end_date = a_start, a_end
    b = TaskNode("B")
    b.start_date, b.end_date = b_start, b_end
    b.predecessor_id = a.id
    c = TaskNode("C")
    c.start_date, c.end_date = c_start, c_end
    c.predecessor_id = b.id
    return a, b, c


def _assert_linked(a, b, c, msg):
    expected_b_start = WC.get_next_workday(a.end_date)
    expected_c_start = WC.get_next_workday(b.end_date)
    assert b.start_date == expected_b_start, (
        f"{msg}: B.start={b.start_date} expected {expected_b_start} (A.end={a.end_date})"
    )
    assert c.start_date == expected_c_start, (
        f"{msg}: C.start={c.start_date} expected {expected_c_start} (B.end={b.end_date})"
    )


def test_edit_a_end_ripples():
    a, b, c = _make_chain()
    roots = [a, b, c]
    schedule(roots)
    _assert_linked(a, b, c, "baseline")

    a.set_date("end", "2026-01-23")
    schedule(roots)
    _assert_linked(a, b, c, "after A.end edit")


def test_edit_a_duration_ripples():
    a, b, c = _make_chain()
    roots = [a, b, c]
    schedule(roots)
    b_dur_before = WC.calculate_duration(b.start_date, b.end_date)
    c_dur_before = WC.calculate_duration(c.start_date, c.end_date)

    a.set_duration(10)
    schedule(roots)

    _assert_linked(a, b, c, "after A.duration edit")
    assert WC.calculate_duration(b.start_date, b.end_date) == b_dur_before, "B duration drifted"
    assert WC.calculate_duration(c.start_date, c.end_date) == c_dur_before, "C duration drifted"


def test_edit_a_start_ripples():
    a, b, c = _make_chain()
    roots = [a, b, c]
    schedule(roots)

    a.set_date("start", "2026-02-02")
    schedule(roots)
    _assert_linked(a, b, c, "after A.start edit")


def test_forward_pointing_link_order():
    """Build the chain with C above B above A in root order — the fixup
    pass must still converge so C anchors to the new B.end."""
    a, b, c = _make_chain()
    roots = [c, b, a]  # reversed tree order
    schedule(roots)
    _assert_linked(a, b, c, "reversed root order baseline")

    a.set_date("end", "2026-01-30")
    schedule(roots)
    _assert_linked(a, b, c, "reversed root order after A.end edit")


def test_parent_rollup_with_chain():
    """A lives under parent P; editing A still ripples to sibling-root B, C."""
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-01-05", "2026-01-09"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-01-05", "2026-01-09"
    p.add_child(a)

    b = TaskNode("B")
    b.start_date, b.end_date = "2026-01-12", "2026-01-14"
    b.predecessor_id = a.id
    c = TaskNode("C")
    c.start_date, c.end_date = "2026-01-15", "2026-01-16"
    c.predecessor_id = b.id

    roots = [p, b, c]
    schedule(roots)
    _assert_linked(a, b, c, "parent rollup baseline")

    a.set_date("end", "2026-01-23")
    schedule(roots)
    _assert_linked(a, b, c, "after A.end edit (A under parent)")
    # Parent P must envelope A
    assert p.end_date >= a.end_date, f"P.end={p.end_date} < A.end={a.end_date}"


def test_is_parallel_on_snaps_to_parent():
    """is_parallel=ON -> start always snaps to parent.start_date."""
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-01-05", "2026-01-16"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-01-05", "2026-01-09"
    p.add_child(a)
    b = TaskNode("B", parent=p)
    b.start_date, b.end_date = "2026-01-14", "2026-01-16"  # stale
    b.is_parallel = True
    p.add_child(b)

    schedule([p])
    assert b.start_date == p.start_date, (
        f"is_parallel=ON should snap B.start to parent.start={p.start_date}; "
        f"got {b.start_date}"
    )


def test_is_parallel_off_later_child_chains():
    """is_parallel=OFF on a later child -> chains to prev sibling.end + 1."""
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-01-05", "2026-01-16"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-01-05", "2026-01-09"
    p.add_child(a)
    b = TaskNode("B", parent=p)
    b.start_date, b.end_date = "2026-01-20", "2026-01-22"  # stale
    b.is_parallel = False
    p.add_child(b)

    schedule([p])
    expected = WC.get_next_workday(a.end_date)
    assert b.start_date == expected, (
        f"is_parallel=OFF later child B.start={b.start_date} expected {expected}"
    )


def test_first_child_snaps_to_parent():
    """is_parallel=OFF first child -> start snaps to parent.start."""
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-04-17", "2026-05-06"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-04-24", "2026-04-28"  # off-parent stale
    a.is_parallel = False
    p.add_child(a)

    schedule([p])
    assert a.start_date == p.start_date, (
        f"first child A.start={a.start_date} expected {p.start_date}"
    )


def test_second_root_chains_from_first():
    """2nd root with is_parallel=OFF -> chains from first root's end + 1."""
    r1 = TaskNode("R1")
    r1.start_date, r1.end_date = "2026-01-05", "2026-01-09"
    r2 = TaskNode("R2")
    r2.start_date, r2.end_date = "2026-02-01", "2026-02-03"  # stale
    r2.is_parallel = False

    schedule([r1, r2])
    expected = WC.get_next_workday(r1.end_date)
    assert r2.start_date == expected, (
        f"2nd root R2.start={r2.start_date} expected {expected}"
    )


def test_second_root_is_parallel_on_is_manual():
    """2nd root with is_parallel=ON -> radio has no effect at root level;
    root still chains from prev root (no parent to snap to)."""
    r1 = TaskNode("R1")
    r1.start_date, r1.end_date = "2026-01-05", "2026-01-09"
    r2 = TaskNode("R2")
    r2.start_date, r2.end_date = "2026-03-01", "2026-03-05"
    r2.is_parallel = True

    schedule([r1, r2])
    # Roots have no parent, so is_parallel snap-to-parent does not apply.
    # The root chaining rule (prev_root.end + 1) still fires for 2nd+ roots.
    expected = WC.get_next_workday(r1.end_date)
    assert r2.start_date == expected, (
        f"2nd root R2.start={r2.start_date} expected {expected} "
        f"(root chaining applies; is_parallel irrelevant at root level)"
    )


def test_is_parallel_on_later_child_snaps_to_parent():
    """is_parallel=ON on a later (non-first) child -> still snaps to parent.start,
    NOT to prev_sibling.end + 1."""
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-01-05", "2026-01-30"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-01-05", "2026-01-09"
    p.add_child(a)
    b = TaskNode("B", parent=p)
    b.start_date, b.end_date = "2026-01-12", "2026-01-16"
    p.add_child(b)
    c = TaskNode("C", parent=p)
    c.start_date, c.end_date = "2026-01-20", "2026-01-23"  # stale
    c.is_parallel = True  # Radio ON: should snap to parent.start
    p.add_child(c)

    schedule([p])
    assert c.start_date == p.start_date, (
        f"Radio ON later child C.start={c.start_date} expected parent.start={p.start_date}"
    )


def test_dates_locked_keeps_manual():
    """dates_locked=True -> start is frozen; end rolls up from children.

    Specifically:
    - The locked node's start_date must never be overwritten by the scheduler.
    - Leaf locked node: end_date stays hand-typed (no children to roll up from).
    - Parent locked node WITH children: end_date = max(children.end_date).
    """
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-01-05", "2026-01-30"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-01-05", "2026-01-09"
    p.add_child(a)

    # Leaf locked task — both dates hand-typed, no children.
    b = TaskNode("B", parent=p)
    b.start_date, b.end_date = "2026-01-19", "2026-01-23"
    b.dates_locked = True
    p.add_child(b)

    schedule([p])
    assert b.start_date == "2026-01-19", (
        f"Leaf locked B.start should stay 2026-01-19; got {b.start_date}"
    )
    assert b.end_date == "2026-01-23", (
        f"Leaf locked B.end should stay 2026-01-23; got {b.end_date}"
    )

    # Shift A's end — B's start must still stay frozen.
    a.set_date("end", "2026-01-23")
    schedule([p])
    assert b.start_date == "2026-01-19", (
        f"After upstream shift, locked B.start should still be 2026-01-19; got {b.start_date}"
    )

    # Parent locked task WITH children: start frozen, end = max(children.end).
    parent_locked = TaskNode("PL")
    parent_locked.start_date, parent_locked.end_date = "2026-02-02", "2026-02-06"
    parent_locked.dates_locked = True
    c1 = TaskNode("C1", parent=parent_locked)
    c1.start_date, c1.end_date = "2026-02-02", "2026-02-06"
    parent_locked.add_child(c1)
    c2 = TaskNode("C2", parent=parent_locked)
    c2.start_date, c2.end_date = "2026-02-09", "2026-02-20"
    parent_locked.add_child(c2)

    schedule([parent_locked])
    assert parent_locked.start_date == "2026-02-02", (
        f"Locked parent start must stay 2026-02-02; got {parent_locked.start_date}"
    )
    assert parent_locked.end_date == "2026-02-20", (
        f"Locked parent end must roll up to max child end 2026-02-20; got {parent_locked.end_date}"
    )


def test_parallel_and_predecessor_not_both():
    """Nodes must never have both is_parallel=True and predecessor_id set at
    the same time — the scheduler should not crash and predecessor wins."""
    p = TaskNode("P")
    p.start_date, p.end_date = "2026-01-05", "2026-01-09"
    a = TaskNode("A", parent=p)
    a.start_date, a.end_date = "2026-01-05", "2026-01-09"
    p.add_child(a)
    b = TaskNode("B")
    b.start_date, b.end_date = "2026-01-12", "2026-01-14"
    # Both set — UI prevents this but scheduler must not crash.
    b.predecessor_id = a.id
    b.is_parallel = True

    roots = [p, b]
    schedule(roots)  # must not raise
    # predecessor wins in scheduler (processed first in walk)
    expected = WC.get_next_workday(a.end_date)
    assert b.start_date == expected, (
        f"B.start={b.start_date} expected {expected} when both flags set"
    )


if __name__ == "__main__":
    tests = [
        test_edit_a_end_ripples,
        test_edit_a_duration_ripples,
        test_edit_a_start_ripples,
        test_forward_pointing_link_order,
        test_parent_rollup_with_chain,
        test_is_parallel_on_snaps_to_parent,
        test_is_parallel_off_later_child_chains,
        test_first_child_snaps_to_parent,
        test_second_root_chains_from_first,
        test_second_root_is_parallel_on_is_manual,
        test_is_parallel_on_later_child_snaps_to_parent,
        test_dates_locked_keeps_manual,
        test_parallel_and_predecessor_not_both,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    if failures:
        print(f"\n{failures} failure(s)")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
