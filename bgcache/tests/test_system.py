"""0.8.0b3: the per-system files (bgcache/system/). Each is tested here on its
own with a fake Maya install, so Windows and macOS logic is checked on any
machine. Linux must stay exactly as before (the studio)."""
import os, sys, stat, tempfile, importlib, json, time
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
from bgcache.system import linux, macos, windows
import bgcache.system as system

def touch_exe(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path

# ---- picks the right file for the system it runs on
for plat, name in (("win32", "windows"), ("darwin", "macos"), ("linux", "linux")):
    with mock.patch.object(sys, "platform", plat):
        importlib.reload(system)
        assert system.NAME == name, (plat, system.NAME)
importlib.reload(system)
print("ok: win32 -> windows.py, darwin -> macos.py, linux -> linux.py")

# ---- Windows: Maya on another drive, with spaces in the path
root = tempfile.mkdtemp()
loc = os.path.join(root, "Program Files", "Autodesk", "Maya2027")
maya_exe = touch_exe(os.path.join(loc, "bin", "maya.exe"))
mayapy_exe = touch_exe(os.path.join(loc, "bin", "mayapy.exe"))
with mock.patch.dict(os.environ, {"MAYA_LOCATION": loc}):
    assert windows.find_maya() == maya_exe and windows.find_mayapy() == mayapy_exe
with mock.patch.dict(os.environ, {"MAYA_LOCATION": ""}), mock.patch.object(sys, "executable", maya_exe), \
     mock.patch.object(windows, "on_path", lambda names: [None for _ in names]):
    assert windows.find_maya() == maya_exe and windows.find_mayapy() == mayapy_exe
print("ok: Windows: bin/maya.exe and bin/mayapy.exe from MAYA_LOCATION, else next to the running maya.exe")
assert windows.hidden_console() == {"creationflags": 0x08000000} and linux.hidden_console() == {}
print("ok: Windows starts console programs (mayapy, ffmpeg) with CREATE_NO_WINDOW; Linux/macOS unchanged")
assert windows.pid_alive(12345) is True          # no Windows API here: can't tell -> never closes anything
assert windows.pid_alive(None) is True
print("ok: Windows process check never reports a live Maya as gone when it can't ask")
calls = []
def flaky():
    calls.append(1)
    if len(calls) < 3:
        raise PermissionError("in use")
    return "done"
assert windows.retrying(flaky) == "done" and len(calls) == 3
with mock.patch.object(windows, "RETRY_S", 0.02):
    try:
        windows.retrying(lambda: (_ for _ in ()).throw(PermissionError("locked")))
        raise AssertionError("should give up")
    except PermissionError:
        pass
calls[:] = []
try:
    linux.retrying(flaky)
    raise AssertionError("linux must not retry")
except PermissionError:
    assert len(calls) == 1
print("ok: Windows retries a file another program has open (up to 0.5 s), then gives up; Linux doesn't retry")

# ---- shared files written through the Windows retry
from bgcache import common
target = os.path.join(root, "status.json")
real_replace, n = os.replace, {"fails": 2}
def busy_replace(a, b):
    if n["fails"]:
        n["fails"] -= 1
        raise PermissionError("player is reading it")
    return real_replace(a, b)
with mock.patch.object(common, "system", windows), mock.patch.object(common.os, "replace", busy_replace):
    common.write_json_atomic(target, {"state": "ready"})
assert json.load(open(target)) == {"state": "ready"} and not [f for f in os.listdir(root) if f.endswith(".tmp")]
print("ok: a status write that Windows refuses twice still lands, leaving no temp file")

# ---- macOS: Maya.app bundle
app = os.path.join(root, "Applications", "Autodesk", "maya2027", "Maya.app", "Contents")
mac_maya = touch_exe(os.path.join(app, "MacOS", "Maya"))
mac_py = touch_exe(os.path.join(app, "bin", "mayapy"))
with mock.patch.dict(os.environ, {"MAYA_LOCATION": app}):
    assert macos.find_maya() == mac_maya and macos.find_mayapy() == mac_py
with mock.patch.dict(os.environ, {"MAYA_LOCATION": ""}), mock.patch.object(sys, "executable", mac_maya):
    assert macos.find_maya() == mac_maya and macos.find_mayapy() == mac_py
print("ok: macOS: MacOS/Maya and bin/mayapy inside Maya.app, from MAYA_LOCATION or the running Maya")

# ---- Linux: exactly the old order, the studio wrapper only from the profile
lin = os.path.join(root, "usr", "autodesk", "maya2024")
lin_maya = touch_exe(os.path.join(lin, "bin", "maya"))
lin_py = touch_exe(os.path.join(lin, "bin", "mayapy"))
with mock.patch.dict(os.environ, {"MAYA_LOCATION": lin}):
    assert linux.find_maya() == lin_maya and linux.find_mayapy() == lin_py
wrap_dir = os.path.join(root, "studio_bin"); wrapper = touch_exe(os.path.join(wrap_dir, "studiomaya"))
with mock.patch.dict(os.environ, {"MAYA_LOCATION": "", "PATH": wrap_dir}), \
     mock.patch.object(linux, "_running_binary", lambda: None):
    assert linux.find_maya() is None
    assert linux.find_maya(("studiomaya",)) == wrapper
print("ok: Linux: bin/maya and bin/mayapy as before; a studio wrapper comes only from the profile's maya_wrappers")
