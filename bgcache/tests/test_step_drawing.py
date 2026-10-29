"""0.8.0b7: step through drawings (Draw mode keys and buttons), cycling round."""
import os, sys, types, json, tempfile, time
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
root = tempfile.mkdtemp(); os.environ["BGCACHE_ROOT"] = root; os.environ["HOME"] = os.environ["USERPROFILE"] = root

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

class Fake(object):
    step_drawing = pl.Player.step_drawing
    drawn_frames = pl.Player.drawn_frames
    def __init__(self, ticks, live=0):
        self.start, self.end, self.pos, self.live = 1001, 1048, 0, live
        self.drawer = types.SimpleNamespace(ticks=lambda: set(ticks))
        self.msgs = []
    def _live_offset(self): return self.live
    def _jump(self, pos): self.pos = pos
    def _flash_message(self, text, seconds=3.0): self.msgs.append(text)
    def frame(self): return self.start + self.pos - self.live

F = Fake({1010, 1020, 1021, 1040, 990, 1060})        # 990 and 1060 are outside the range: ignored
assert F.drawn_frames() == [1010, 1020, 1021, 1040]
seen = []
for _ in range(5):
    F.step_drawing(1); seen.append(F.frame())
assert seen == [1010, 1020, 1021, 1040, 1010], seen
assert F.msgs == ["Back to the first drawing"], F.msgs
print("ok: next steps drawing by drawing (neighbouring frames one at a time), then cycles to the first")

F.msgs = []; seen = []; F.pos = 44                    # frame 1045, after the last drawing
for _ in range(5):
    F.step_drawing(-1); seen.append(F.frame())
assert seen == [1040, 1021, 1020, 1010, 1040], seen
assert F.msgs == ["Round to the last drawing"], F.msgs
print("ok: previous goes back, and before the first cycles to the last")

F = Fake({1020}); F.pos = 5
F.step_drawing(1); assert F.frame() == 1020 and not F.msgs
F.step_drawing(1); assert F.frame() == 1020 and not F.msgs          # one drawing: stays, no message
print("ok: a single drawing stays put")

F = Fake(set()); F.step_drawing(1)
assert F.pos == 0 and F.msgs == ["No drawings to step to"]
print("ok: no drawings: says so, doesn't move")

F = Fake({1010, 1030}, live=24)                        # neighbour shot before yours on the strip
F.pos = 3                                              # on the neighbour
F.step_drawing(1); assert F.frame() == 1010 and not F.msgs
F.pos = 24 + 47                                        # last frame of your range
F.step_drawing(-1); assert F.frame() == 1030
print("ok: works with neighbouring shots on the strip")

# Draw mode: your Maya prev/next key hotkeys step drawings; otherwise they go to Maya's keys
src = open(os.path.join(REPO, "bgcache", "player.py")).read()
assert 'action in ("prev_key", "next_key") and self.drawer.on' in src
assert "self.send_cmd(action)" in src
d = open(os.path.join(REPO, "bgcache", "drawui.py")).read()
assert "step_drawing(s)" in d and "b_next_drawing" in d and "b_prev_drawing" in d
# B marks: full-height 3 px ticks with a dark edge
assert "QtCore.QRect(x - 1, bar.y(), 3, bar.height()), TICK)" in src
assert "QtCore.QRect(x - 2, bar.y(), 5, bar.height()), TICK_EDGE)" in src
print("ok: keys, Draw panel buttons and full-height marks are wired up")
