"""Linux: bgcache's original behaviour (the studio's), unchanged."""
import os
import sys

from bgcache.system._shared import first, maya_location, on_path

NAME = "linux"


def _running_binary():
    """The binary this Maya is actually running, e.g. .../maya.bin."""
    try:
        exe = os.path.realpath("/proc/self/exe")
        return exe if os.path.basename(exe).startswith("maya") else None
    except Exception:  # no /proc (not Linux): unknown
        return None


def find_maya(extra_names=()):
    """Same Maya binary as this session if possible, so it shares the exact
    setup. extra_names: studio wrapper commands to try on the PATH last (the
    profile's maya_wrappers)."""
    loc = maya_location()
    return first([os.path.join(loc, "bin", "maya") if loc else None, _running_binary()]
                 + on_path(("maya",) + tuple(extra_names)))


def find_mayapy():
    loc = maya_location()
    exe = _running_binary()
    return first([os.path.join(loc, "bin", "mayapy") if loc else None,
                  os.path.join(os.path.dirname(exe), "mayapy") if exe else None]
                 + on_path(("mayapy",)))


def pid_alive(pid):
    """True if the process exists."""
    if not pid:
        return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def hidden_console():
    return {}


def retrying(fn):
    return fn()
