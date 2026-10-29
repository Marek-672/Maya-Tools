"""0.8.0b12: everything in the player. The shelf button starts bgcache (the
player opens at once) or brings the player back; Stop, Restart and Self-test
are in the player (and on the shelf button's right-click menu); closing the
player asks: stop, or keep caching. The old Maya panel is gone."""
import os, sys, types, json, time
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])   # Maya/Qt stubs
sys.path.insert(0, REPO)
from bgcache import controller, common
deferred = []
cmds.evalDeferred = lambda fn, **k: deferred.append(fn)
cmds.workspaceControl = lambda *a, **k: False
cmds.workspaceControlState = lambda *a, **k: False
cmds.currentTime = lambda *a, **k: 1001.0
c = controller.get()
calls = []
c.start = lambda **k: calls.append(("start", k)) or setattr(c, "session", common.new_session())
controller.shelf_click(width=1280)
assert calls == [("start", {"width": 1280})] and c.running
print("ok: shelf button when stopped: Start (with the shelf command's options)")

class Proc:
    def poll(s): return None
c.player_proc = Proc()
controller.shelf_click()
st = common.read_json(common.paths(c.session)["maya_time"])
assert st.get("raise") is True and len(calls) == 1
print("ok: shelf button while running: brings the player to the front (no second start)")
class Gone:
    def poll(s): return 0
c.player_proc = Gone()
c.launch_player = lambda: calls.append(("launch",))
controller.shelf_click()
assert calls[-1] == ("launch",)
print("ok: player closed (Keep caching): the shelf button opens it again")

c.stop = lambda: calls.append(("stop",))
common.write_json_atomic(common.paths(c.session)["player_cmd"], {"cmd": "stop", "ts": time.time() + 1})
c._cmd_ts = 0; c._poll_player_cmd(); [fn() for fn in deferred]; deferred.clear()
assert calls[-1] == ("stop",)
c.restart = lambda: calls.append(("restart",))
common.write_json_atomic(common.paths(c.session)["player_cmd"], {"cmd": "restart", "ts": time.time() + 2})
c._poll_player_cmd(); [fn() for fn in deferred]
assert calls[-1] == ("restart",)
print("ok: the player's Stop and Restart reach your Maya")

src = open(os.path.join(REPO, "bgcache", "install.py")).read()
assert "bgc.shelf_click()" in src and all(w in src for w in ("Stop bgcache", "Reopen player", "Restart bgcache", "Self-test"))
assert "menuItemPython" in src
print("ok: shelf button runs shelf_click, with a right-click menu: Stop, Reopen player, Restart, Self-test")
p = open(os.path.join(REPO, "bgcache", "player.py")).read()
for words in ('"Stop bgcache, or keep caching in the background?"', '"Don\'t ask again"', '"Keep caching"',
              '"Stop bgcache"', '"Restart bgcache"',
              'self._close_quietly = True        # your Maya is gone'):
    assert words in p, words
print("ok: the player has Stop and Scene > Restart / Stop / Self-test; closing asks (Stop / Keep caching / "
      "Cancel, Don't ask again), but not when your Maya has gone")
cs = _source.source("controller")
assert "def show_ui(panel=False" in cs and "shelf_click(**start_kwargs)" in cs
print("ok: old shelf buttons (show_ui) work the same as the new one")
