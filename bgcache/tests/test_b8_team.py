"""0.9.0b8 team drawing: people with drawings on your shot are listed by
themselves, their layers off until you click the eye; an updated dot;
removing someone keeps them off; your Maya stopping asks to save first."""
import os, sys, types, json, time
TESTS = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(TESTS, "test_drawer.py")).read()
exec(src.split("# a stroke: canvas points map")[0])   # Drawer d on sq050_0472, camera "camera", user artist

sam = drawing.Drawings(drawing.layers_path(shot_root, "sam", "camera"), (960, 540), owner="sam")
sam.add_stroke(1150, {"c": "#e85d4a", "w": 4.0, "p": [[10, 10, 1.0], [20, 20, 1.0]]}); sam.save()
d._checks = d.NEW_PEOPLE_EVERY - 1
assert d.check_updates()
row = d.person("sam")
assert row is not None and row["hide_new"]
assert [r["key"] for r in d.rows()] == ["me", "m:l1", "P:sam", "p:sam:l1"]
assert 1150 not in d.ticks() and not d.person_visible(row)
print("ok: someone who saved drawings on your shot is listed by themselves, their layers off")
d.set_person_visible("sam", True)
assert 1150 in d.ticks() and d.person_visible(d.person("sam"))
print("ok: the eye on their heading shows all their layers")

time.sleep(0.01)
sam.add_stroke(1160, {"c": "#e85d4a", "w": 4.0, "p": [[30, 30, 1.0], [40, 40, 1.0]]}); sam.save()
d._checks = 0
d.check_updates()
assert d.person("sam")["status"] == "update" and 1160 not in d.ticks()
print("ok: they save again: Update (and a dot) on their heading; you see the new drawings only after Update")

d.set_linked("sam", False)
d._checks = d.NEW_PEOPLE_EVERY - 1
assert not d.check_updates() and d.person("sam") is None
d.set_linked("sam", True)
assert d.person("sam") is not None
print("ok: removed (x), they stay off the list until you tick them in Import again")

# your Maya stops bgcache: the player asks to save first, then closes
import bgcache.player as pl
asked = []
class FakePlayer(object):
    _check_close_request = pl.Player._check_close_request
    _answer_close = pl.Player._answer_close
    test_mode = False
    def __init__(s, unsaved):
        s.p = {"player_close": os.path.join(root, "close.json")}
        s._close_ts = 0
        s.closed = False
        s.drawer = types.SimpleNamespace(unsaved=lambda: ["camera"] if unsaved else [],
                                         ask_to_save=lambda parent, doing, cancel=True: asked.append((doing, cancel)) or True)
    def showNormal(s): pass
    def raise_(s): pass
    def activateWindow(s): pass
    def close(s): s.closed = True
from bgcache import common
F = FakePlayer(unsaved=True)
common.write_json_atomic(F.p["player_close"], {"ts": time.time(), "reason": "your Maya changes scene"})
F._check_close_request()
assert F.closed and asked == [("your Maya changes scene", False)]
assert common.read_json(F.p["player_close"] + ".answer")["state"] == "closing"
print("ok: your Maya opening another scene: the player asks Save / Don't save (no Cancel), then closes")
F = FakePlayer(unsaved=False); asked[:] = []
common.write_json_atomic(F.p["player_close"], {"ts": time.time() + 1, "reason": "stopping bgcache"})
F._check_close_request()
assert F.closed and not asked
print("ok: nothing unsaved: it just closes")
