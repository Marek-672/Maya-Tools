"""Next build: the player's toolbar wraps onto more rows in a narrow window
instead of stopping the window from getting narrower (studio note l16)."""
import os, sys, types
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
exec(open(os.path.join(TESTS, "test_reload.py")).read().split("from bgcache import common")[0])   # Qt stubs
QtWidgets.QLayout = Dummy
sys.modules.pop("bgcache.widgets", None)
from bgcache import widgets
F = widgets.FlowLayout

class Item:
    def __init__(s, w, hidden=False): s.w, s.hidden = w, hidden
    def sizeHint(s): return types.SimpleNamespace(width=lambda: s.w, height=lambda: 24)
    def widget(s): return types.SimpleNamespace(isHidden=lambda: s.hidden)
fake = types.SimpleNamespace(STRETCH=F.STRETCH, _space=8)
a, b, c, d = Item(100), Item(100), Item(100), Item(100)
fake._items = [a, b, F.STRETCH, c, d]
lines = F._lines(fake, 1000)
assert len(lines) == 1 and lines[0] == [a, b, F.STRETCH, c, d]
print("ok: wide window: one row, the stretch keeps the right group to the right")
lines = F._lines(fake, 230)
assert [[i for i in l if i is not F.STRETCH] for l in lines] == [[a, b], [c, d]], lines
print("ok: narrow window: wraps onto a second row")
lines = F._lines(fake, 90)
assert len([l for l in lines if any(i is not F.STRETCH for i in l)]) == 4
print("ok: very narrow: one button per row, never wider than the window allows")
fake._items = [a, Item(100, hidden=True), c]
assert F._lines(fake, 1000) == [[a, c]]
print("ok: hidden buttons (e.g. Continuity in Simple) take no room")
src = open(os.path.join(REPO, "bgcache", "player.py")).read()
assert "row = FlowLayout(bar" in src and "setFixedHeight(40)\n        row = QtWidgets.QHBoxLayout(bar)" not in src
print("ok: the player's toolbar uses it")
