import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, json, tempfile, time
from unittest import mock
root = tempfile.mkdtemp(); os.environ["BGCACHE_ROOT"] = root
os.environ["HOME"] = os.environ["USERPROFILE"] = root  # prefs + resolver config go to a temp home

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
import importlib, json
prof_path = os.path.join(root, "profile.json")
os.environ["BGCACHE_PROFILE"] = prof_path            # nothing set up yet
from bgcache import common, profile
from bgcache.continuity import reel
import bgcache.player as pl

film = os.path.join(root, "film")
for rel in ("scenes/sh010_anim.ma", "playblasts/sh010_v02.mov", "playblasts/sh020_v01.mov"):
    path = os.path.join(film, rel); os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").close()
session = common.new_session(); p = common.paths(session)
cfg = {"session": session, "start": 1, "end": 48, "fps": 24.0, "height": 540,
       "cameras": [{"name": "|shotCam", "label": "shotCam"}],
       "original_scene": film + "/scenes/sh010_anim.ma", "audio": {}}
common.write_json_atomic(p["config"], cfg)
with mock.patch.object(reel.Jobs, "add", lambda self, *a: None):
    P = pl.Player(session)
assert P.shot_ids is None
opened = []
P.open_setup = lambda: opened.append(1)
P.toggle_continuity()
assert opened == [1] and not P.continuity_on
print("ok: before any setup, the Continuity switch opens Set up continuity (and stays off)")
src = open(os.path.join(REPO, "bgcache", "player.py")).read()
assert 'app_menu.addAction("Set up continuity...", self.open_setup)' in src
print("ok: bgcache > Set up continuity... in the Full edition")

# the wizard saved settings learned from one playblast: the strip fills without a restart
from bgcache.continuity import learn
lay = learn.learn(film + "/playblasts/sh010_v02.mov", film + "/scenes/sh010_anim.ma")
json.dump(learn.to_profile(lay), open(prof_path, "w"))
listed, cards = [], []
P._list_shots = lambda: listed.append(1)
P.browser.add_card = lambda card: cards.append(card)
P.browser.cards = {}
P._after_setup()
assert P.shot_ids and P.live_shot == "sh010" and P.continuity_on and listed == [1] and len(cards) == 1
assert reel.cr.list_shots_in_sequence("", P.shot_ids[2]) == ["sh010", "sh020"]
print("ok: after Save the player places the scene in its shot, turns continuity on and lists the shots")
