import importlib.util
import os
import tempfile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("git_helper_v5", os.path.join(HERE, "git_helper_v5.py"))
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class CombinedLogTests(unittest.TestCase):
    def test_report_combines_events_from_multiple_folders(self):
        with tempfile.TemporaryDirectory(prefix="git-helper-v5-logs-") as root:
            first = os.path.join(root, "first")
            final = os.path.join(root, "final")
            os.makedirs(first)
            os.makedirs(final)
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = os.path.join(root, "local-app-data")
            try:
                APP.append_support_log(first, "first_folder_event")
                APP.append_support_log(final, "final_folder_event")
                report, count = APP.collect_support_report(final)
                self.assertGreaterEqual(count, 2)
                with open(report, encoding="utf-8") as fh:
                    contents = fh.read()
                self.assertIn("first_folder_event", contents)
                self.assertIn("final_folder_event", contents)
                self.assertIn("project_folder", contents)
            finally:
                if previous is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous


if __name__ == "__main__":
    unittest.main()
