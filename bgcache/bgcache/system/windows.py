"""Windows: maya.exe / mayapy.exe, no console windows, a process check that
asks Windows (os.kill would END the process there), and retries for files
another program has open (Windows refuses to replace or open them then).

Maya can be on any drive: MAYA_LOCATION is e.g. D:/Program Files/Autodesk/Maya2027,
and inside Maya sys.executable is the running maya.exe."""
import os
import sys
import time

from bgcache.system._shared import first, maya_location, on_path

NAME = "windows"
CREATE_NO_WINDOW = 0x08000000
RETRY_S = 0.5


def _running(name):
    exe = sys.executable or ""
    return exe if os.path.basename(exe).lower() == name else None


def find_maya(extra_names=()):
    loc = maya_location()
    return first([os.path.join(loc, "bin", "maya.exe") if loc else None, _running("maya.exe")]
                 + on_path(("maya",) + tuple(extra_names)))


def find_mayapy():
    loc = maya_location()
    running = _running("maya.exe")
    return first([os.path.join(loc, "bin", "mayapy.exe") if loc else None,
                  os.path.join(os.path.dirname(running), "mayapy.exe") if running else None]
                 + on_path(("mayapy",)))


def pid_alive(pid):
    """True if the process exists. Can't tell: True (never close anything by mistake)."""
    if not pid:
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE, ERROR_ACCESS_DENIED = 0x1000, 259, 5
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            # no such process, unless it exists but belongs to someone else
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # can't ask Windows: assume it's still running (never quit by mistake)
        return True


def hidden_console():
    return {"creationflags": CREATE_NO_WINDOW}


def retrying(fn):
    """fn(), retried for up to RETRY_S on PermissionError."""
    deadline = time.time() + RETRY_S
    while True:
        try:
            return fn()
        except PermissionError:
            if time.time() > deadline:
                raise
            time.sleep(0.005)
