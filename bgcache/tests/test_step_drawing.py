"""0.8.0b7: step through drawings (Draw mode keys and buttons), cycling round."""
import _source  # noqa: E402 (tests/_source.py)
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
for n in ("QWidget", "QFrame", "QLayout", "QSpinBox"): setattr(QtWidgets, n, Dummy)
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
    drawn_positions = pl.Player.drawn_positions
    _live_key = lambda self: "cam"
    def __init__(self, ticks, live=0, before=()):
        self.start, self.end, self.pos, self.live = 1001, 1048, 0, live
        self.view = "|cam"
        self.segments = ([{"kind": "before", "shot": "sh010", "n": live, "first": 1001}] if live else []) + \
                        [{"kind": "live", "shot": "sh020", "n": 48}]
        keys = {0: "cam"} if not live else {}
        def place(o):
            seg = self._locate(o)[0]
            return {"key": "cam" if seg["kind"] == "live" else "cam@sh010"}
        self.drawer = types.SimpleNamespace(place=place, ticks=lambda key=None: set(before) if key == "cam@sh010" else set(ticks))
        self.msgs = []
    def _offsets(self):
        o = 0
        for s in self.segments:
            yield o, s
            o += s["n"]
    def _locate(self, pos):
        for o, s in self._offsets():
            if pos < o + s["n"]:
                return s, pos - o
        return self.segments[-1], self.segments[-1]["n"] - 1
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

F = Fake({1010, 1030}, live=24, before={1005, 1012})  # a shot before yours on the strip, with its own drawings
F.pos = 3                                              # on that shot (its frame 1004)
F.step_drawing(1); assert F.pos == 4 and not F.msgs    # its drawing on 1005
F.step_drawing(1); assert F.pos == 11
F.step_drawing(1); assert F.pos == 4                   # b8: stays on the shot on screen, cycling
F.pos = 24 + 47                                        # last frame of your range
F.step_drawing(-1); assert F.frame() == 1030
assert F.drawn_positions() == [4, 11, 24 + 9, 24 + 29]
print("ok: b8: the shots around yours have their own drawings to step through; the bar marks them all")

# Draw mode: your Maya prev/next key hotkeys step drawings; otherwise they go to Maya's keys
src = _source.source("player")
assert 'action in ("prev_key", "next_key") and self.drawer.on' in src
assert "self.send_cmd(action)" in src
d = _source.source("drawui")
assert "step_drawing(s)" in d and "b_next_drawing" in d and "b_prev_drawing" in d
# B marks: full-height 3 px ticks with a dark edge
assert "QtCore.QRect(x - 1, bar.y(), 3, bar.height()), TICK)" in src
assert "QtCore.QRect(x - 2, bar.y(), 5, bar.height()), TICK_EDGE)" in src
print("ok: keys, Draw panel buttons and full-height marks are wired up")
