"""1.0: bgcache Simple = bgcache without the continuity/ folder. The player
must work on its own: your shot only, no Continuity button, nothing from
the add-on imported, settings still saved."""
import os, sys, types, json, tempfile, shutil, wave, array
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
root = tempfile.mkdtemp(); os.environ["BGCACHE_ROOT"] = root
os.environ["HOME"] = root
os.environ.pop("BGCACHE_PROFILE", None)

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

# the Simple package: a copy of bgcache without continuity/
simple = tempfile.mkdtemp()
shutil.copytree(os.path.join(REPO, "bgcache"), os.path.join(simple, "bgcache"),
                ignore=shutil.ignore_patterns("continuity", "__pycache__"))
sys.path.insert(0, simple)
from bgcache import common
import bgcache.player as pl
assert pl.__file__.startswith(simple)
assert pl.Player.has_continuity is False and pl.NoContinuity in pl.Player.__mro__
print("ok: without the continuity folder the player loads, with no continuity part")

wav = os.path.join(root, "anim", "walk_sound.wav"); os.makedirs(os.path.dirname(wav))
w = wave.open(wav, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
w.writeframes(array.array("h", [500] * int(100 / 24.0 * 48000) * 2).tobytes()); w.close()
session = common.new_session(); p = common.paths(session)
cfg = {"session": session, "start": 1, "end": 100, "fps": 24.0, "height": 540,
       "cameras": [{"name": "|cam", "label": "cam"}],
       "original_scene": os.path.join(root, "anim", "scenes", "walk_v003.mb"),
       "drawings_root": os.path.join(root, "anim", "bgcache", "walk"),
       "audio": {"path": wav, "offset": 1, "source_start": 0, "source_end": 0, "mute": False}}
common.write_json_atomic(p["config"], cfg)
P = pl.Player(session)
assert P.shot_ids is None and P.live_shot is None and not P.continuity_on
assert not {"b_cont", "browser", "jobs", "job_timer"} & set(vars(P))
assert [s["kind"] for s in P.segments] == ["live"] and P.total == 100 and P.rate == 48000
print("ok: your shot only: 100 frames with its sound; no Continuity button, strip or job thread")
assert P.drawer.root == cfg["drawings_root"]
print("ok: drawings go where Maya said (project or scene folder)")
P.toggle_browser(); P.toggle_live_ref()            # C and R do nothing
P._set_sync(False)
saved = json.load(open(common.PREFS_PATH))
assert saved["sync"] is False and "shots" not in saved and "continuity" not in saved
print("ok: C and R are harmless; settings saved without continuity entries")
assert P._window_height() == 28 + 40 + 600 + pl.BAR_H + 40
assert not any(m.startswith("bgcache.continuity") for m in sys.modules)
print("ok: nothing from the add-on was imported")
