"""0.7.3: self-test report helpers, and the background benchmark against the fake Maya."""
import os, sys, runpy
TESTS = os.path.dirname(os.path.abspath(__file__))
ns = runpy.run_path(os.path.join(TESTS, "test_worker.py"))   # fake Maya + worker
worker, common, state = ns["worker"], ns["common"], ns["state"]
from bgcache import selftest
import tempfile; os.environ["HOME"] = os.environ["USERPROFILE"] = tempfile.mkdtemp()     # the report is saved under ~/.bgcache

m = selftest.fit([(1, 1.38), (3, 1.94), (6, 2.78), (12, 4.46)])
assert abs(m[0] - 1.1) < 0.02 and abs(m[1] - 0.28) < 0.01, m
assert selftest.fit([(1, 1.0), (1, 1.2)]) is None
print("ok: fit gives start-up + per-frame:", selftest.model_text(m))

log = """[bgcache 10:00:01] trace: rendered 1 frames in 1.40s (playblast 1.38s)
[bgcache 10:00:03] trace: rendered 5 frames in 2.60s (playblast 2.50s)
[bgcache 10:00:03] edit synced: 12 frames, first frame after 1.60s, all after 4.1s (your Maya 0.10s, pickup 0.05s, apply 0.03s, first frame render 1.42s) batches 1,5,6
[bgcache 10:01:03] edit synced: 3 frames, first frame after 2.00s, all after 3.0s (your Maya 0.20s, pickup 0.05s, apply 0.05s, first frame render 1.70s) batches 1,2
"""
out = selftest.summarize_log(log)
assert out[0].startswith("2 edits synced: first new frame after 1.80s"), out
assert "first frame render 1.56s" in out[1] and "1 fr 1.38s" in out[2] and "fitted: 1.10s start-up + 0.28s/frame" in out[3], out
assert selftest.summarize_log("")[0] == "no edits synced in this log yet"
print("ok: worker.log summary:", out[0])

states = {"cache": False, "deformer": True, "invisibility": True, "frustum": False}
assert selftest.evaluator_text(states).startswith("frustum off, invisibility on")
assert selftest.frustum_name(states) == "frustum" and selftest.frustum_name({"cache": True}) is None
assert "wireframeOnShaded=on" in selftest.display_text({"displayAppearance": "smoothShaded", "wireframeOnShaded": True})
print("ok: evaluators and display shown in a line")

# the background part, run in the fake worker: benchmark lines + variants restore evaluators
session = common.new_session()
cfg = {"session": session, "start": 1, "end": 40, "chunk": 12, "quality": 85, "width": 64, "height": 36, "fps": 24}
w = worker.Worker(cfg); w.panel = "p"; w.cfg["controller_pid"] = os.getpid()
w.timer = type("T", (), {"start": lambda self, d: None})()
common.write_json_atomic(common.paths(session)["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
for _ in range(10): w.step()
cmds = sys.modules["maya.cmds"]
ev = {"invisibility": True, "frustum": False, "cache": False}
def evaluator(name=None, query=False, enable=None, **k):
    if query and name is None: return list(ev)
    if query: return ev[name]
    ev[name] = enable
cmds.evaluator = evaluator
state["blasts"].clear()
common.post_message(session, {"op": "selftest", "id": "abc", "frame": 5, "hide": ["|nothere"]})
w.step()
res = common.read_json(os.path.join(common.paths(session)["logs"], "selftest.json"))
text = "\n".join(res["lines"])
assert res["id"] == "abc", res
assert "frustum evaluator: yes (frustum)" in text and "as is:" in text, text
assert "invisibility evaluator off:" in text and "frustum evaluator on:" in text, text
assert "none of |nothere found" in text, text
assert ev == {"invisibility": True, "frustum": False, "cache": False}     # put back as they were
assert state["blasts"] and all(b[1] >= 5 for b in state["blasts"]), state["blasts"]
print("ok: background self-test benchmarks, tries invisibility off / frustum on, restores them")

# your-Maya side with bgcache stopped: report printed and saved, never raises
from unittest import mock
import types
fake_c = types.SimpleNamespace(running=False, session=None)
fake_ctrl = types.SimpleNamespace(get=lambda: fake_c, viewport_display=lambda: {"displayAppearance": "wireframe"})
cmds.about = lambda **k: "2024" if k.get("version") else "cut1"
cmds.file = lambda *a, **k: "/projects/BIRDS/sq050_0472/maya/a.mb"
cmds.evaluationManager = lambda **k: ["parallel"]
import bgcache
with mock.patch.dict(sys.modules, {"bgcache.controller": fake_ctrl}), mock.patch.object(bgcache, "controller", fake_ctrl, create=True):
    out = selftest.run()
joined = "\n".join(out)
assert "Maya 2024 (cut1), scene a.mb" in joined and "displayAppearance=wireframe" in joined, joined
assert "bgcache isn't running" in joined and "WORKER LOG" in joined, joined
saved = sorted(__import__("glob").glob(os.path.join(os.path.expanduser("~"), ".bgcache", "selftest_*.txt")))
assert saved and open(saved[-1]).read().startswith("bgcache "), saved
print("ok: run() prints and saves the report (bgcache stopped: your-Maya part + log)")
