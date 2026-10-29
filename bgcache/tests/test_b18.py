"""0.8.0b18: focus range (cache only part of the shot, set from the player),
path curves synced, calmer idle loop, GPU restart said plainly, renderer
settings logged, a before_playblast hook, 2 converted versions kept."""
import os, sys, json, types, tempfile, time
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)

# ---- the background Maya: renders dirty frames inside the focus only
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w` (frames 1-20, chunk 6)
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
for _ in range(10):
    step()
assert not w.cams["|shotCam"]["dirty"]
w.mark(1, 20)                                         # an edit that changes the whole shot
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam", "focus": [8, 12]})
del state["blasts"][:]
for _ in range(10):
    step()
done = {f for _c, a, b in state["blasts"] for f in range(int(a), int(b) + 1)}
assert done == set(range(8, 13)), done
assert w.cams["|shotCam"]["dirty"] == set(range(1, 8)) | set(range(13, 21))
st = json.load(open(p["status"]))
assert st["state"] == "ready" and len(st["cameras"]["|shotCam"]["dirty"]) == 15
print("ok: focus 8-12: only those frames re-render; the 15 outside stay dirty (red), status ready")
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam", "focus": None})
for _ in range(10):
    step()
assert not w.cams["|shotCam"]["dirty"]
print("ok: clearing the focus re-renders the frames that were waiting outside")

# ---- calmer idle loop
delays = []
w.timer = types.SimpleNamespace(start=lambda d: delays.append(d))
w._busy_t = time.time() - 5
step()
assert delays[-1] == worker.CALM_POLL_MS == 100
w.mark(3, 3)
step()
assert delays[-1] == 0
print("ok: idle for a while: checks every 0.1 s (was 0.05 s); straight back to full speed with work")

# ---- path curve CVs applied in the background Maya
cvs = {"|path|pathShape": [(0, 0, 0), (1, 0, 0), (2, 0, 0)]}
set_cv = {}
cmds.objExists = lambda n: n in cvs
cmds.getAttr = lambda plug: cvs[plug.split(".")[0]] if plug.endswith(".cv[*]") else 0
cmds.setAttr = lambda plug, *v, **k: set_cv.__setitem__(plug, v)
w.set_curve_shape("|path|pathShape", [[0, 0, 0], [1, 5, 0], [2, 0, 0]])
assert set_cv["|path|pathShape.controlPoints[1]"] == (1, 5, 0)
del LOG[:]
w.set_curve_shape("|path|pathShape", [[0, 0, 0]] * 5)
assert any("Reload scene to update its shape" in m for m in LOG)
print("ok: a path curve's moved CVs are set in the background Maya; a changed CV count says Reload scene")

# ---- renderer settings logged; before_playblast hook
calls = []
hook = types.ModuleType("studio_pb_hook"); hook.prepare = lambda panel: calls.append(panel)
sys.modules["studio_pb_hook"] = hook
w.cfg["before_playblast"] = "studio_pb_hook.prepare"
w._before_playblast()
assert calls == ["p"]
w.cfg["before_playblast"] = "no_such_module.fn"
w._before_playblast()                                  # logged, no failure
print("ok: before_playblast (a studio's playblast set-up) runs once with the panel; a broken one is only logged")
wsrc = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert 'log("renderer settings: %s"' in wsrc and '"renderMode", "lightingMode"' in wsrc
assert 'if cfg.get("gpu_rescued"):' in wsrc
print("ok: worker.log says the renderer's own shading/lighting mode; after a GPU restart the warning stays")

# ---- your Maya: which curves are watched
for n in ("maya", "maya.cmds"):
    sys.modules.pop(n, None)
for n in [m for m in sys.modules if m.startswith("bgcache")]:
    sys.modules.pop(n)
maya = types.ModuleType("maya"); cmds2 = types.ModuleType("maya.cmds"); mel = types.ModuleType("maya.mel")
api = types.ModuleType("maya.api"); om = types.ModuleType("maya.api.OpenMaya"); oma = types.ModuleType("maya.api.OpenMayaAnim")
class _F: kConstant = 0
oma.MFnAnimCurve = _F
for n, m in (("maya", maya), ("maya.cmds", cmds2), ("maya.mel", mel), ("maya.api", api),
             ("maya.api.OpenMaya", om), ("maya.api.OpenMayaAnim", oma)):
    sys.modules[n] = m
from bgcache import controller
curves = {"|path|pathShape": {"in": [], "out": ["motionPath1"]},          # a path you place: watched
          "|ctrl|ctrlShape": {"in": [], "out": []},                       # a rig control: not watched
          "|spine|spineShape": {"in": ["cluster1"], "out": ["ikHandle1"]},  # built by the rig: follows it
          "|ik|ikShape": {"in": [], "out": ["ikHandle1"]}}                 # spline IK curve you edit: watched
cmds2.ls = lambda type=None, long=True, noIntermediate=True: list(curves)
def listConnections(plug, source=True, destination=True):
    shape = plug.split(".")[0]
    return curves[shape]["in"] if plug.endswith(".create") else curves[shape]["out"]
cmds2.listConnections = listConnections
cmds2.nodeType = lambda n: {"motionPath1": "motionPath", "ikHandle1": "ikHandle", "cluster1": "cluster"}[n]
assert controller.path_curves() == ["|path|pathShape", "|ik|ikShape"]
print("ok: watched: curves you edit by hand that drive a motion path, spline IK, wire...; "
      "not rig controls, not curves built from other nodes")
c = _source.source("controller")
assert "self.callback_ids = self._watch_path_curves() + [" in c and '"op": "curve_shapes"' in c
assert "GPU_STUCK_S = 10.0" in c
assert 'cmds.scriptJob(conditionFalse=["playingBack", self._on_time_changed])' in c
assert "if playing and now - getattr(self, \"_time_written\", 0.0) < 0.25:" in c
print("ok: GPU restart after 10 s of silence (was 20); while your Maya plays it tells the player "
      "at most 4 times a second, and always the frame it stops on")

# ---- continuity: the newest 2 converted versions per department are kept
from bgcache.continuity import reel
d = tempfile.mkdtemp()
for name in ("P_v009_540p", "P_v011_540p", "P_v012_540p", "Lighting_v004_540p", "P_v003_1080p"):
    os.makedirs(os.path.join(d, name))
old = sorted(os.path.basename(x) for x in reel._older_versions(d))
assert old == ["P_v009_540p"], old
print("ok: continuity cache keeps the newest 2 converted versions per department (P v011, v012), "
      "older ones go (unless used today)")

# ---- the player: focus handles, I/O, status, cameras.json
pl = open(os.path.join(REPO, "bgcache", "player.py")).read()
for words in ("def set_focus(self", "Qt.Key_I, Qt.Key_O", "def _paint_focus", "mouseDoubleClickEvent",
              '"Clear focus range (cache the whole shot)"', '"focus": list(self.focus_range)',
              'text += "  ·  focus %d-%d" % self.focus_range', "dirty = self._dirty_in_focus()"):
    assert words in pl, words
print("ok: player: handles on the cache bar (drag; double-click clears), I / O at the frame you're on "
      "(Shift: back to the ends), View > Clear focus range, 'focus 1040-1070 · N waiting outside'")
