"""macOS: Maya lives in an app bundle. MAYA_LOCATION is
/Applications/Autodesk/maya<version>/Maya.app/Contents; the Maya program is
MacOS/Maya and mayapy is bin/mayapy. Untested on a real Mac so far."""
import os
import sys

from bgcache.system import linux
from bgcache.system._shared import first, maya_location, on_path

NAME = "macos"


def _contents():
    """The running Maya's Maya.app/Contents folder, from MAYA_LOCATION or the
    program Python is running in."""
    loc = maya_location()
    if loc:
        return loc
    exe = os.path.realpath(sys.executable or "")
    marker = ".app/Contents/"
    if marker in exe:
        return exe[:exe.index(marker) + len(marker) - 1]
    return ""


def find_maya(extra_names=()):
    contents = _contents()
    exe = os.path.realpath(sys.executable or "")
    running = exe if os.path.basename(exe) == "Maya" else None
    return first([os.path.join(contents, "MacOS", "Maya") if contents else None,
                  running,
                  os.path.join(contents, "bin", "maya") if contents else None]
                 + on_path(("maya",) + tuple(extra_names)))


def find_mayapy():
    contents = _contents()
    return first([os.path.join(contents, "bin", "mayapy") if contents else None]
                 + on_path(("mayapy",)))


pid_alive = linux.pid_alive       # same as Linux (POSIX)
hidden_console = linux.hidden_console
retrying = linux.retrying
