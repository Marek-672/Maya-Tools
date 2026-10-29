"""0.7.3: Pause re-rendering. Edits keep being applied while paused (frames
go red), nothing renders; Resume starts at the frame you're on."""
import os, sys, runpy
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
ns = runpy.run_path(os.path.join(TESTS, "test_worker.py"))   # reuse its fake Maya
worker, common, state = ns["worker"], ns["common"], ns["state"]

session = common.new_session()
cfg = {"session": session, "start": 1, "end": 40, "chunk": 12, "quality": 85,
       "width": 64, "height": 36, "fps": 24}
w = worker.Worker(cfg); w.panel = "p"; w.cfg["controller_pid"] = os.getpid()
w.timer = type("T", (), {"start": lambda self, d: None})()
p = common.paths(session)
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
for _ in range(40): w.step()
assert not w.cams["|shotCam"]["dirty"]

common.post_message(session, {"op": "pause", "on": True, "focus": 1})
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[5, 30]], "focus": 5})
state["blasts"].clear()
for _ in range(20): w.step()
st = common.read_json(p["status"])
assert not state["blasts"], state["blasts"]
assert w.cams["|shotCam"]["dirty"] == set(range(5, 31))
assert st["paused"] is True and st["state"] == "paused" and st["cameras"]["|shotCam"]["dirty"][0] == 5
assert not w.edits                   # no "edit synced" timing spanning the pause
print("ok: paused: edits applied, frames 5-30 stay red, nothing rendered, status says paused")

common.post_message(session, {"op": "pause", "on": False, "focus": 22})
for _ in range(30): w.step()
first = state["blasts"][0]
assert first[1] == 22 and first[2] == 22, first     # the frame you're on, alone, first
assert not w.cams["|shotCam"]["dirty"]
assert common.read_json(p["status"])["paused"] is False
print("ok: resume starts at the frame you're on (22), alone first, then the rest")

src = open(os.path.join(os.path.dirname(TESTS), "bgcache", "player.py")).read()
assert '"op": "pause"' in src and "pauseButton" in src
src = _source.source("controller")
assert '"pause": cmds.button' in src
print("ok: Pause in the player toolbar and the Maya panel")

src = open(os.path.join(os.path.dirname(TESTS), "bgcache", "player.py")).read()
assert '"PAUSED", y=tag_y, pause_icon=True' in src and "QColor(190, 30, 30, 46)" in src
print("ok: (0.7.5) paused: red tint over the picture and an orange II PAUSED tag")
