"""0.8.0b11, from the studio (2026-10-20): a rig that breaks on the GPU hung
the background Maya inside a playblast, so it could never switch to the CPU
itself, and the card wasn't full at all (4 of 16 GB). Now:
- the background Maya uses GPU deformers only if YOUR Maya does;
- your Maya sees GPU errors in worker.log plus no heartbeat for 20 s, and
  restarts the background Maya on the CPU, on a fresh copy of your scene."""
import os, sys, types, json, tempfile, time
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
os.environ["BGCACHE_ROOT"] = tempfile.mkdtemp()
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds"); mel = types.ModuleType("maya.mel")
api = types.ModuleType("maya.api"); om = types.ModuleType("maya.api.OpenMaya"); oma = types.ModuleType("maya.api.OpenMayaAnim")
class _F: kConstant = 0
oma.MFnAnimCurve = _F
for n, m in (("maya", maya), ("maya.cmds", cmds), ("maya.mel", mel), ("maya.api", api), ("maya.api.OpenMaya", om), ("maya.api.OpenMayaAnim", oma)):
    sys.modules[n] = m
qt = types.ModuleType("PySide2"); qc = types.ModuleType("PySide2.QtCore")
class T:
    def __init__(s): pass
    def setSingleShot(s, x): pass
    def start(s, *a): pass
    def stop(s): pass
    @property
    def timeout(s): return types.SimpleNamespace(connect=lambda f: None)
qc.QTimer = T; qt.QtCore = qc; sys.modules["PySide2"] = qt; sys.modules["PySide2.QtCore"] = qc
sys.path.insert(0, REPO)
from bgcache import common, controller

# ---- follow your Maya's GPU Override
def fake_evaluator(answer, registered=("deformer", "invisibility", "cache")):
    def ev(name=None, query=False, enable=False):
        if name is None:
            return list(registered)
        return answer
    return ev
for answer, want in ((True, True), (False, False), ([True], True), ([False], False)):
    cmds.evaluator = fake_evaluator(answer)
    assert controller.gpu_override_on() is want
# b17, studio: GPU Override off, the deformer evaluator isn't registered and the
# query answers with the list of all evaluators; that is NOT "on"
names = ["dnIsolateEvaluator", "invisibility", "frozen", "curveManager", "cache"]
cmds.evaluator = fake_evaluator(names, registered=names)
assert controller.gpu_override_on() is False
cmds.evaluator = fake_evaluator(names)              # registered, but a list of names back
assert controller.gpu_override_on() is False
print("ok: b17: GPU Override off with the deformer evaluator not registered (Maya answers with a list "
      "of evaluators) counts as off; b11-b16 read it as on")
def broken(**k): raise RuntimeError("no such evaluator")
cmds.evaluator = broken
assert controller.gpu_override_on() is False
src = _source.source("controller")
assert '"background_gpu": gpu_on, "gpu_reason": gpu_reason,' in src
settings = {}
controller.profile.get = lambda key, default=None: settings.get(key, "follow")
cmds.evaluator = fake_evaluator(False)        # your GPU Override: off
assert controller.gpu_choice() == (False, "off: GPU Override is off in your Maya")
settings["background_gpu"] = "always"
assert controller.gpu_choice() == (True, "on: the pipeline profile says always")
settings["background_gpu"] = False
assert controller.gpu_choice()[0] is False
settings["background_gpu"] = "follow"; cmds.evaluator = fake_evaluator(True)
assert controller.gpu_choice() == (True, "on: GPU Override is on in your Maya")
print("ok: GPU in the background Maya: follow your Maya (default), always (the studio: its shots switch "
      "GPU Override off on open), or never; the reason goes in the log")

# ---- the rescue
ctl = controller.Controller(); ctl.session = common.new_session()
p = common.paths(ctl.session)
ctl.cfg = {"background_gpu": True, "rev": 1, "scene": "/tmp/shot.mb"}
ctl.loading_since = None
ctl._gpu_log_pos, ctl._gpu_trouble_t, ctl._gpu_log_t, ctl.gpu_rescued = 0, None, 0.0, False
open(p["log"], "w").write("OpenCL evaluator is attempting to initialize OpenCL.\n"
                          "Choosing OpenCL Device NVIDIA A40-16Q.  Device Type: GPU  Device is available.\n")
fresh = {"ts": time.time(), "state": "rendering"}
stale = {"ts": time.time() - 60, "state": "rendering"}
assert ctl._gpu_rescue_needed(stale) is False, "a slow batch with no GPU errors is left alone"
print("ok: OpenCL start-up lines and a slow batch are not trouble")

with open(p["log"], "a") as h:
    h.write("OpenCL Error: Unknown error waiting for idle on NVIDIA A40-16Q (Device 0).\n")
ctl._gpu_log_t = 0
assert ctl._gpu_rescue_needed(fresh) is False, "still answering: it switches to the CPU by itself"
assert ctl._gpu_rescue_needed(stale) is True
print("ok: GPU errors + no heartbeat for 20 s: restart needed")

calls = []
class Proc:
    pid = 4242
    def poll(s): return None
    def kill(s): calls.append("kill")
    def wait(s, t=None): calls.append("wait")
ctl.worker_proc = Proc()
ctl._maya_cmd = ["/usr/autodesk/maya2024/bin/maya"]
ctl.flush = lambda: calls.append("flush")
ctl._progress = lambda t: None; ctl._progress_end = lambda: None
ctl._export_copy = lambda name: (calls.append(("export", name)), "/tmp/" + name)[1]
ctl._remove_callbacks = lambda: calls.append("remove_cbs")
ctl._install_callbacks = lambda: calls.append("install_cbs")
ctl._snapshot = lambda: calls.append("snapshot")
ctl._launch_worker = lambda cmd: calls.append(("launch", cmd))
ctl._tell_player = lambda note: calls.append(("note", note))
controller.scene.default_camera_nodes = lambda: set()
controller.scene.visibility_states = lambda: {}
ctl.trace = lambda *a: None
common.post_message(ctl.session, {"op": "keys", "curves": []})     # an edit not yet picked up
ctl.restart_on_cpu()
assert calls.index("kill") < calls.index(("export", "scene_copy_2.mb")) < calls.index(("launch", ctl._maya_cmd))
assert ctl.cfg["background_gpu"] is False and ctl.cfg["scene"] == "/tmp/scene_copy_2.mb" and ctl.cfg["rev"] == 2
assert json.load(open(p["config"]))["background_gpu"] is False
assert common.take_messages(ctl.session) == [], "old messages are already in the new copy"
assert ctl.loading_kind == "restart" and ctl.loading_since
assert any(c[0] == "note" and "restarting it on the CPU" in c[1] for c in calls if isinstance(c, tuple))
assert "warning" in json.load(open(p["status"]))
print("ok: restart on the CPU: old one killed, fresh scene copy with your edits, GPU off, player told")

ctl.loading_since = None
assert ctl._gpu_rescue_needed(stale) is False
print("ok: only once per session (after that, the usual 'stuck' banner)")
for name in ("maya", "maya.cmds", "maya.mel", "maya.api", "maya.api.OpenMaya", "maya.api.OpenMayaAnim", "PySide2", "PySide2.QtCore"):
    sys.modules.pop(name, None)
