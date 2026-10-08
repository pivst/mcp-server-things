"""Optional test-process guard; load via PYTHONPATH=tests/safety:src.

Reject real Things execution and reads of private user data. Mocks still work.
"""

import os
import sys

user_home = os.path.expanduser("~")


def guard(event, args):
    if event in ("subprocess.Popen", "os.posix_spawn", "os.system"):
        value = str(args)
        if any(
            x in value for x in ("osascript", "Things3", "/usr/bin/open", "things:///")
        ):
            raise PermissionError("Test guard: real Things execution forbidden")
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = os.path.abspath(os.fsdecode(args[0]))
        if path.startswith(user_home + "/Library/") or (
            path.startswith(user_home + "/")
            and (
                path.endswith(".things-auth")
                or path.endswith("things-auth.txt")
                or path.endswith("/.env")
            )
        ):
            raise PermissionError("Test guard: private Things data/config forbidden")


sys.addaudithook(guard)
