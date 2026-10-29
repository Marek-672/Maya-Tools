"""0.8.0b2: Reload scene shows what it's doing. A banner over the picture:
"your Maya is exporting" -> "reloading in the background Maya" -> a short
"Scene reloaded" message; failures and reloads started from Maya too."""
import os, sys, types, json, tempfile, time
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
root = tempfile.mkdtemp(); os.environ["BGCACHE_ROOT"] = root; os.environ["HOME"] = root

class Dummy(object):
    def __init__(self, *a, **k): pass
    def __getattr__(self, name): return mock.MagicMock()
def qtmod(name):
    m = mock.MagicMock(); m.__name__ = name; return m
QtCore, QtGui, QtWidgets = qtmod("QtCore"), qtmod("QtGui"), qtmod("QtWidgets")
for n in ("QWidget", "QFrame", "QLayout"): setattr(QtWidgets, n, Dummy)
class DummyLabel(Dummy):
    def setText(self, text): self._text = text
    def text(self): return getattr(self, "_text", "")
QtWidgets.QLabel = DummyLabel
class DummyToolButton(Dummy):
    def setChecked(self, on): self._on = bool(on)
    def isChecked(self): return getattr(self, "_on", False)
    def setCheckable(self, on): pass
    InstantPopup = 2; MenuButtonPopup = 1
QtWidgets.QToolButton = DummyToolButton
pyside = types.ModuleType("PySide2"); pyside.QtCore, pyside.QtGui, pyside.QtWidgets = QtCore, QtGui, QtWidgets
sys.modules.update({"PySide2": pyside, "PySide2.QtCore": QtCore, "PySide2.QtGui": QtGui, "PySide2.QtWidgets": QtWidgets})
sys.path.insert(0, REPO)
from bgcache import common
import bgcache.player as pl

session = common.new_session(); p = common.paths(session)
cfg = {"session": session, "start": 1, "end": 50, "fps": 24.0, "height": 540, "rev": 1,
       "cameras": [{"name": "|cam", "label": "cam"}], "original_scene": os.path.join(root, "a.mb")}
common.write_json_atomic(p["config"], cfg)
def status(state, reloads):
    common.write_json_atomic(p["status"], {"state": state, "reloads": reloads, "cameras": {}, "ts": time.time()})
status("rendering", 3)                   # the background Maya has already reloaded 3 times
P = pl.Player(session)
assert P._reload_banner() is None and P._flash == ""
print("ok: no banner and no message at start, even after earlier reloads")

def sent():
    return common.read_json(p["player_cmd"])["cmd"]
P.reload_scene()
assert sent() == "reload"
assert "your Maya is exporting the scene" in P._reload_banner()
print("ok: Reload scene -> banner: your Maya is exporting the scene (0:00)")

time.sleep(0.02)
cfg.update(rev=2, reloaded_at=time.time()); common.write_json_atomic(p["config"], cfg); os.utime(p["config"], (time.time() + 1,) * 2)
P._poll()
assert P._reload_banner().startswith("Reloading scene in the background Maya")
status("reloading scene", 3); P._poll()
assert "(the picture is from before)" in P._reload_banner()
print("ok: export done -> banner: reloading in the background Maya; then '(the picture is from before)'")
status("rendering", 4); P._poll()
assert P._reload_banner() is None and P._flash.startswith("Scene reloaded")
print("ok: finished -> banner gone, 'Scene reloaded: re-rendering all frames'")

# a reload so quick the player never saw "reloading scene"
P._flash_until = 0
P.reload_scene(); status("rendering", 5); P._poll()
assert P._reload_banner() is None and P._flash.startswith("Scene reloaded")
print("ok: a reload faster than the player's check still ends the banner")

# started from the Maya panel: banner while it runs, message at the end
P._flash_until = 0
status("reloading scene", 5); P._poll()
assert P._reload_banner().startswith("Reloading scene in the background Maya")
status("ready", 6); P._poll()
assert P._reload_banner() is None and P._flash.startswith("Scene reloaded")
print("ok: a reload started in Maya shows the banner too")

# your Maya couldn't export: it says so, banner gone
P.reload_scene()
common.write_json_atomic(p["maya_time"], {"frame": 1, "ts": time.time() + 10,
                                          "note": "Reload scene failed: the scene couldn't be exported"})
pos = P.pos; P._follow_maya()
assert P._reload_banner() is None and "couldn't be exported" in P._flash and P.pos == pos
print("ok: a failed export is shown in the player; the frame doesn't move")

# nothing ever happens: the banner gives up and says where to look
P.reload_scene(); P.RELOAD_GIVE_UP_S = 0; time.sleep(0.01)
assert P._reload_banner() is None and "didn't start" in P._flash
print("ok: no sign of the reload for 10 minutes -> banner gone, points to the Script Editor")
