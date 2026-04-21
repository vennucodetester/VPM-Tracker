"""
Regression test: after loading any project file and running a full recalc,
every task must satisfy start_date <= end_date, and every parent must
envelope its children's span.

Run from the CODE directory:
    python tests/test_timeline_invariants.py
"""
import os
import sys
import glob
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "vpm_tracker"))

from utils.vpmt_io import load_project  # noqa: E402
from models.task_node import TaskNode  # noqa: E402

DATE_FMT = "%Y-%m-%d"


def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n.children)


def assert_end_ge_start(node: TaskNode):
    if not node.start_date or not node.end_date:
        return
    s = datetime.strptime(node.start_date, DATE_FMT)
    e = datetime.strptime(node.end_date, DATE_FMT)
    assert e >= s, f"INVERTED: {node.name!r} start={node.start_date} end={node.end_date}"


def assert_parent_envelopes_children(node: TaskNode):
    if not node.children:
        return
    starts = [c.start_date for c in node.children if c.start_date]
    ends = [c.end_date for c in node.children if c.end_date]
    if not starts or not ends or not node.start_date or not node.end_date:
        return
    assert node.start_date <= min(starts), (
        f"Parent {node.name!r} start {node.start_date} > earliest child {min(starts)}"
    )
    assert node.end_date >= max(ends), (
        f"Parent {node.name!r} end {node.end_date} < latest child {max(ends)}"
    )


def run_file(path: str):
    print(f"\n== {os.path.basename(path)} ==")
    roots = load_project(path)
    total = 0
    for n in walk(roots):
        assert_end_ge_start(n)
        assert_parent_envelopes_children(n)
        total += 1
    print(f"   OK — {total} tasks pass invariants")


def main():
    save_dirs = [
        os.path.join(ROOT, "vpm_tracker"),                       # CODE/vpm_tracker/*.vpmt
        os.path.abspath(os.path.join(ROOT, "..", "SAVE FILES")), # repo-root/SAVE FILES/*.vpmt
    ]
    files = []
    for d in save_dirs:
        files.extend(sorted(glob.glob(os.path.join(d, "*.vpmt"))))
    if not files:
        print("No .vpmt files found.")
        sys.exit(1)

    failed = 0
    for f in files:
        try:
            run_file(f)
        except AssertionError as e:
            print(f"   FAIL: {e}")
            failed += 1

    if failed:
        print(f"\n{failed} file(s) failed invariants.")
        sys.exit(1)
    print("\nAll files pass timeline invariants.")


if __name__ == "__main__":
    main()
