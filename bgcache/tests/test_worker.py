import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, json, glob, tempfile, shutil
root = tempfile.mkdtemp(); os.environ["BGCACHE_ROOT"] = root
# --- fake maya ---
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds"); api = types.ModuleType("maya.api")
om = types.ModuleType("maya.api.OpenMaya"); oma = types.ModuleType("maya.api.OpenMayaAnim")
class _F: kTangentFixed = 1
oma.MFnAnimCurve = _F
scene_cams = {"|shotCam", "|sideCam"}
state = {"cam": None, "blasts": []}
cmds.objExists = lambda n: n in scene_cams
def modelEditor(panel, edit=True, camera=None, **k):
    if camera: state["cam"] = camera
cmds.modelEditor = modelEditor
def playblast(startTime, endTime, filename, **k):
    state["blasts"].append((state["cam"], startTime, endTime))
    for f in range(startTime, endTime + 1):
        open("%s.%04d.jpg" % (filename, f), "w").write(state["cam"])
cmds.playblast = playblast
melmod = types.ModuleType("maya.mel"); melmod.eval = lambda s: None; maya.mel = melmod; maya.__path__ = []
for m, o in (("maya", maya), ("maya.cmds", cmds), ("maya.mel", melmod), ("maya.api", api), ("maya.api.OpenMaya", om), ("maya.api.OpenMayaAnim", oma)):
    sys.modules[m] = o
qt = types.ModuleType("PySide2"); qc = types.ModuleType("PySide2.QtCore")
class T:
    def __init__(s): pass
    def setSingleShot(s, x): pass
    @property
    def timeout(s): return types.SimpleNamespace(connect=lambda f: None)
qc.QTimer = T; qt.QtCore = qc; sys.modules["PySide2"] = qt; sys.modules["PySide2.QtCore"] = qc
qg = types.ModuleType("PySide2.QtGui"); qw = types.ModuleType("PySide2.QtWidgets"); qt.QtGui = qg; qt.QtWidgets = qw
blank = {"on": False}
class QImage:
    def __init__(s, path): s.path = path
    def isNull(s): return False
    def width(s): return 64
    def height(s): return 36
    def pixel(s, x, y): return 0 if blank["on"] else x * 1000 + y
qg.QImage = QImage
sys.modules["PySide2.QtGui"] = qg; sys.modules["PySide2.QtWidgets"] = qw
sys.modules["shiboken2"] = types.ModuleType("shiboken2")
win = {"iconify": None}
def window(name, edit=False, iconify=None, **k):
    if iconify is not None: win["iconify"] = iconify
cmds.window = window
sys.path.insert(0, REPO)
from bgcache import common, worker
LOG = []
worker.log = lambda m: (LOG.append(m), print("   log:", m))

session = common.new_session()
cfg = {"session": session, "start": 1, "end": 20, "chunk": 6, "quality": 85, "width": 64, "height": 36, "fps": 24}
w = worker.Worker(cfg); w.panel = "p"; w.cfg["controller_pid"] = os.getpid()
p = common.paths(session)
def step(): w.step()  # timer.start is a no-op stub? patch:
w.timer = types.SimpleNamespace(start=lambda d: None)

step(); st = json.load(open(p["status"]))
assert st["state"].startswith("ready, pick") and not state["blasts"]; print("ok: nothing renders before a camera is checked")

common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
for _ in range(10): step()
st = json.load(open(p["status"]))
assert st["state"] == "ready" and len(st["cameras"]["|shotCam"]["versions"]) == 20
assert all(c == "|shotCam" for c, a, b in state["blasts"])
assert open(common.frame_path(session, 5, "|shotCam")).read() == "|shotCam"
print("ok: shotCam cached, 20 frames,", len(state["blasts"]), "chunks")

# check sideCam (not viewed) then make an edit: viewed cam must render first
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam", "|sideCam", "|ghost"], "view": "|shotCam"})
step()  # picks up camera + renders first chunk of sideCam
common.post_message(session, {"op": "dirty", "ranges": [[10, 12]]})
state["blasts"].clear(); step()
assert state["blasts"][0][0] == "|shotCam" and state["blasts"][0][1] == 10, state["blasts"]
print("ok: after an edit the viewed camera renders first:", state["blasts"][0])
for _ in range(20): step()
st = json.load(open(p["status"]))
assert st["state"] == "ready" and len(st["cameras"]["|sideCam"]["versions"]) == 20
assert "|ghost" not in st["cameras"]
print("ok: sideCam caught up in idle time; missing camera skipped")

# switch view, uncheck shotCam -> frames deleted
common.write_json_atomic(p["cameras"], {"checked": ["|sideCam"], "view": "|sideCam"})
step(); st = json.load(open(p["status"]))
assert st["view"] == "|sideCam" and "|shotCam" not in st["cameras"]
assert not os.path.exists(common.frames_dir(session, "|shotCam"))
print("ok: unchecking drops the camera's frames")

# --- edit focus + timing: edit at Maya frame 15 inside dirty range 10-18
import time as _t
state["blasts"].clear()
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[10, 18]], "focus": 15, "ts": _t.time()})
step()
assert state["blasts"][0][1] == 15, state["blasts"]
for _ in range(10): step()
order = [b[1] for b in state["blasts"] if b[0] == "|sideCam"]
assert order[0] == 15 and 10 in order, order
assert any(m.startswith("edit synced: 9 frames") for m in LOG), LOG[-3:]
print("ok: render starts at the frame being worked on:", order, "|", [m for m in LOG if m.startswith("edit synced")][-1])

# --- hidden render window gives blank frames -> restored and re-rendered once
w.render_hidden, w.render_checked = True, False
blank["on"] = True
common.post_message(session, {"op": "dirty", "ranges": [[1, 3]]})
step()
assert win["iconify"] is False and not w.render_hidden
assert w.cams["|sideCam"]["dirty"] >= {1, 2, 3}
blank["on"] = False
for _ in range(5): step()
assert not w.cams["|sideCam"]["dirty"]
print("ok: blank frames with hidden window -> window restored, frames re-rendered")

# --- Reload scene: reopen in place, keep cameras, new range, everything re-rendered
opened = []
w._open = lambda path: opened.append(path)
before_versions = dict(w.cams["|sideCam"]["versions"])
common.post_message(session, {"op": "reload", "scene": "/tmp/scene_copy_3.mb", "start": 1, "end": 12})
w.step()      # handles the reload (and starts re-rendering)
assert opened == ["/tmp/scene_copy_3.mb"] and (w.first, w.last) == (1, 12)
assert "|sideCam" in w.cams and all(f <= 12 for f in w.cams["|sideCam"]["versions"])
for _ in range(6): w.step()
st = json.load(open(p["status"]))
assert st["end"] == 12 and st["state"] == "ready" and len(st["cameras"]["|sideCam"]["versions"]) == 12
print("ok: Reload scene reopens in the same Maya, keeps cameras, new range re-rendered")
shutil.rmtree(root)

# ===== 1.0: tools switched off in the background Maya come from the profile =====
calls = []
fake = types.ModuleType("studio_tool"); fake_cb = types.ModuleType("studio_tool.callback")
fake_cb.stop_all = lambda: calls.append("stopped"); fake.callback = fake_cb
sys.modules["studio_tool"] = fake; sys.modules["studio_tool.callback"] = fake_cb
jobs = ["0: 'rig_has_changed' studio_tool callback"]
cmds.scriptJob = lambda listJobs=True: list(jobs)
w.cfg["switch_off_in_background"] = [{"if_scriptjob_contains": "rig_has_changed",
                                      "call": "studio_tool.callback.stop_all"}]
w._switch_off_tools(force=True)
assert calls == ["stopped"], calls
w._switch_off_tools()                      # checked again within 5 s: skipped
assert calls == ["stopped"]
jobs[:] = ["0: something else"]
w._switch_off_tools(force=True)            # its script job isn't running: nothing to do
assert calls == ["stopped"]
w.cfg["switch_off_in_background"] = [{"if_scriptjob_contains": "x", "call": "no_such_tool.stop"}]
jobs[:] = ["x"]
w._switch_off_tools(force=True)            # a missing tool is logged, never an error
assert any("could not switch off no_such_tool.stop" in m for m in LOG)
w.cfg["switch_off_in_background"] = []
print("ok: profile's switch_off_in_background: called when its script job runs, re-checked every 5 s, missing tool only logged")

# ===== 0.8.0b2: the status counts finished reloads (the player's reload banner uses it) =====
before = getattr(w, "reloads", 0)
assert before >= 1                                   # the Reload scene check above counted
os.makedirs(os.path.dirname(w.p["status"]), exist_ok=True)   # an earlier check removed the session folder
w._open = lambda scene: None
w.reload({"op": "reload", "scene": "/x/scene_copy_2.mb", "start": w.first, "end": w.last})
w._status_key = None; w.write_status()
assert json.load(open(w.p["status"]))["reloads"] == before + 1
print("ok: status says how many reloads have finished")
