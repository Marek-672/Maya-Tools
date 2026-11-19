"""0.9.0b13: the strip's number boxes (brush size, onion Before / After): you
can type in them, Enter or an arrow click hands the keyboard back to the
player, and their arrows are painted bright."""
import os, sys
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(TESTS, "test_drawer.py")).read()
head = src.split("pyside = types.ModuleType")[0]
exec(head)

class DummySpin(Dummy):
    def __init__(self):
        self.focus, self.cleared, self.policy, self.val = True, 0, None, 2
        self.editingFinished = mock.MagicMock(); self._win = mock.MagicMock()
    def setFocusPolicy(self, p): self.policy = p
    def setKeyboardTracking(self, on): self.tracking = on
    def hasFocus(self): return self.focus
    def clearFocus(self): self.focus = False; self.cleared += 1
    def window(self): return self._win
    def interpretText(self): self.read = True
    def keyPressEvent(self, e): self.passed = e
    def mouseReleaseEvent(self, e): pass
    def initStyleOption(self, opt): raise AttributeError("no style here")
    def width(self): return 42
    def height(self): return 22
QtWidgets.QSpinBox = DummySpin
class QRect:
    def __init__(s, x, y, w, h): s.x, s.y, s.w, s.h = x, y, w, h
    def contains(s, p): return s.x <= p[0] < s.x + s.w and s.y <= p[1] < s.y + s.h
QtCore.QRect = QRect
QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Escape, QtCore.Qt.ClickFocus = 1, 2, 3, "click"
exec("pyside = types.ModuleType" + src.split("pyside = types.ModuleType")[1].split("shot_root = os.path.join")[0])
from bgcache import drawui_widgets as w

box = w.CountBox()
assert box.policy == "click" and box.tracking is False
print("ok: a click lets you type in the box (it was arrows only)")
key = mock.MagicMock(); key.key.return_value = 1
box.keyPressEvent(key)
assert box.read and box.cleared == 1 and box._win.setFocus.called and "passed" not in box.__dict__
print("ok: Enter takes the typed number and hands the keyboard back to the player")
digit = mock.MagicMock(); digit.key.return_value = 53
box.focus = True; box.keyPressEvent(digit)
assert box.passed is digit and box.cleared == 1
print("ok: digits go to the box")
up, down = box.arrow_rects()
assert (up.x, up.y, down.y) == (26, 1, 11)
click = mock.MagicMock(); click.pos.return_value = (30, 5)
box.focus = True; box.mouseReleaseEvent(click)
assert box.cleared == 2
inside = mock.MagicMock(); inside.pos.return_value = (5, 5)
box.focus = True; box.mouseReleaseEvent(inside)
assert box.cleared == 2
print("ok: a click on an arrow doesn't keep the keyboard; a click in the number does")
panel = open(os.path.join(os.path.dirname(TESTS), "bgcache", "drawui_panel.py")).read()
assert panel.count("CountBox()") == 2 and "QSpinBox" not in panel and "NoFocus" not in panel
assert "drawPolygon" in open(w.__file__).read()
print("ok: brush size and onion Before / After use it; its arrows are painted bright")
