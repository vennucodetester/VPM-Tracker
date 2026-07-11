import os
import runpy
import sys
import traceback


HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "git_helper_v5_2.py")
LOG = os.path.join(HERE, "git-helper-v5.2-startup.log")

try:
    os.chdir(HERE)
    runpy.run_path(APP, run_name="__main__")
except SystemExit:
    raise
except BaseException:
    details = traceback.format_exc()
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(details + "\n")
    except OSError:
        pass
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "Git Helper could not open. The reason was saved here:\n\n" + LOG + "\n\n" + details[-1200:],
            "Git Helper v5.2 Startup Error",
            0x10,
        )
    raise
