import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, json, time
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])   # Maya/Qt stubs + temp root
from unittest import mock
os.environ["HOME"] = os.environ["USERPROFILE"] = os.environ["BGCACHE_ROOT"]
sys.path.insert(0, REPO)
qc.QCoreApplication = types.SimpleNamespace(processEvents=lambda: None)
vis = {"|char|geo": True, "|prop": True, "|animVis": True}
class It:
    def __init__(s, kind): s.items = list(vis.items()); s.i = 0
    def isDone(s): return s.i >= len(s.items)
    def thisNode(s): return s.items[s.i]
    def next(s): s.i += 1
class Dag:
    def __init__(s, item): s.item = item
    def fullPathName(s): return s.item[0]
    def findPlug(s, name, w): return types.SimpleNamespace(asBool=lambda: vis[s.item[0]])
om.MItDependencyNodes = It; om.MFnDagNode = Dag; om.MFn = types.SimpleNamespace(kTransform=1)
layers = {"bgLayer.visibility": True, "bgLayer.displayType": 0, "bgLayer.hideOnPlayback": False, "bgLayer.enabled": True}
cmds.ls = lambda *a, **k: ["defaultLayer", "bgLayer"] if k.get("type") == "displayLayer" else []
cmds.objExists = lambda plug: plug in layers
cmds.getAttr = lambda plug: layers[plug]
cmds.listConnections = lambda plug, **k: ["visCurve"] if plug.startswith("|animVis") else []
labels, buttons = [], {}
cmds.text = lambda *a, **k: labels.append((k.get("label"), k.get("enableBackground"))) if k.get("edit") else "lbl"
cmds.button = lambda name=None, **k: (buttons.__setitem__(name, k.get("enable")) if k.get("edit") else True)
cmds.file = lambda *a, **k: ("/projects/BIRDS/sq050_0472/maya/shot.mb" if k.get("sceneName") else (True if k.get("modified") else None))
cmds.playbackOptions = lambda **k: 1001.0 if k.get("minTime") else 1300.0
cmds.progressBar = lambda *a, **k: None
mel.eval = lambda s: "MainProgressBar"
from bgcache import common, controller
c = controller.Controller()
c.session = common.new_session(); c.cfg = {"start": 1001, "end": 1340, "rev": 1, "original_scene": "/projects/BIRDS/sq050_0472/maya/shot.mb"}
p = common.paths(c.session)
common.write_json_atomic(p["config"], c.cfg)
c.vis_base = controller.visibility_states()

# --- Refresh: layers always, objects only if changed, never animated visibility
vis["|prop"] = False; vis["|animVis"] = False; layers["bgLayer.visibility"] = False
c.refresh_display()
msg = common.take_messages(c.session)[-1]
plugs = dict((a, b) for a, b in msg["values"])
assert plugs["bgLayer.visibility"] is False and plugs["|prop.visibility"] is False
assert "|char|geo.visibility" not in plugs and "|animVis.visibility" not in plugs
assert msg["ranges"] == [[1001, 1340]]
c.refresh_display()
msg = common.take_messages(c.session)[-1]
assert not any(k.endswith(".visibility") and k.startswith("|") for k, v in msg["values"])
print("ok: Refresh sends display layers + only objects you hid/showed since last time (animated visibility left to curves)")

# --- 0.7.2: Refresh also re-reads your viewport (wireframe on shaded etc.)
assert "wireframeOnShaded" in controller.DISPLAY_FLAGS and "xray" in controller.DISPLAY_FLAGS
now_view = {"displayAppearance": "smoothShaded", "wireframeOnShaded": True, "pluginObjects": {}}
with mock.patch.object(controller.scene, "viewport_display", lambda: dict(now_view)):
    c.refresh_display()
msg = common.take_messages(c.session)[-1]
assert msg["display"]["wireframeOnShaded"] is True and msg["ranges"] == [[1001, 1340]]
assert c.cfg["display"]["wireframeOnShaded"] is True      # Reload scene sends the new settings too
with mock.patch.object(controller.scene, "viewport_display", lambda: {}):
    c.refresh_display()                                    # no viewport found: keep the old settings
assert "display" not in common.take_messages(c.session)[-1] and c.cfg["display"]["wireframeOnShaded"]
print("ok: Refresh re-reads your viewport's display settings (wireframe on shaded, x-ray...) and sends them")

# --- Reload scene
with mock.patch.object(controller.scene, "list_cameras", lambda: [{"name": "|cam", "label": "cam"}]), \
     mock.patch.object(controller.scene, "find_audio", lambda: None), \
     mock.patch.object(controller.scene, "default_camera_nodes", lambda: set()), \
     mock.patch.object(c, "_snapshot", lambda: None), \
     mock.patch.object(c, "_export_copy", lambda name="x": os.path.join(c.session, name)), \
     mock.patch.object(c, "_install_callbacks", lambda: None), \
     mock.patch.object(c, "_remove_callbacks", lambda: None):
    c.reload_scene()
msg = common.take_messages(c.session)[-1]
cfg = common.read_json(p["config"])
assert msg["op"] == "reload" and msg["end"] == 1300 and msg["scene"].endswith("scene_copy_2.mb")
assert cfg["rev"] == 2 and cfg["end"] == 1300 and cfg["cameras"][0]["name"] == "|cam"
assert c.loading_kind == "reload"
print("ok: Reload scene re-exports, rewrites config (new range/cameras) and tells the worker to reopen")

# --- status while loading, startup timing remembered
c.status_label = "lbl"
c.loading_since, c.loading_kind = time.time() - 70, "start"
c.cfg["usual_startup"] = 100
common.write_json_atomic(p["status"], {"state": "opening scene", "ts": time.time()})
c.worker_proc = types.SimpleNamespace(poll=lambda: None)
c._update_status()
assert labels[-1][0] == "Loading scene... 1:10 (usually about 1:40)", labels[-1]
common.write_json_atomic(p["status"], {"state": "ready, pick a camera", "ts": time.time(), "cameras": {}})
c._update_status()
from bgcache import common as reel
assert reel.load_prefs()["startup"]["shot.mb"] == 70.0 and c.loading_since is None
print("ok: panel shows 'Loading scene... 1:10 (usually about 1:40)'; startup time remembered:", reel.load_prefs()["startup"])

# --- worker dies: red label + player told
c.worker_proc = types.SimpleNamespace(poll=lambda: 1)
c._update_status()
assert labels[-1] == ("ERROR: background Maya exited, see worker.log", True)
assert common.read_json(p["status"])["state"].startswith("error")
print("ok: background Maya exit -> red ERROR in the panel, and the player is told")

# --- buttons: Start only when stopped
c.buttons = {"start": "b1", "stop": "b2", "refresh": "b3"}
c._update_buttons(); assert buttons == {"b1": False, "b2": True, "b3": True}
c.session = None; c._update_buttons(); assert buttons == {"b1": True, "b2": False, "b3": False}
print("ok: Start greyed out while running (no double starts); other buttons only while running")
