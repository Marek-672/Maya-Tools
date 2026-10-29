import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time
from unittest import mock
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from bgcache import common, controller as C
c = C.get(); c.session = common.new_session(); c.cfg = {"start": 1001, "end": 1010}

# --- selection records unkeyed values only (deferred, via the API)
C.QtCore.QTimer.singleShot = staticmethod(lambda ms, fn: fn())
class Plug:
    def __init__(s, keyed, v): s.isDestination, s._v = keyed, v
    def asDouble(s): return s._v
class Fn:
    def __init__(s, obj): pass
    def findPlug(s, attr, w): return Plug(attr == "translateX", 0.25)
    def name(s): return "cog_ctrl"
class Dag:
    def __init__(s, path): pass
    def partialPathName(s): return "cog_ctrl"
class Obj:
    def hasFn(s, t): return True
sel = types.SimpleNamespace(length=lambda: 1, getDependNode=lambda i: Obj(), getDagPath=lambda i: None)
C.om.MGlobal = types.SimpleNamespace(getActiveSelectionList=lambda: sel)
C.om.MFnDependencyNode, C.om.MFnDagNode = Fn, Dag
C.om.MFn = types.SimpleNamespace(kDagNode=1)
C.cmds.listAttr = lambda n, **k: ["translateX", "squash"]
c._on_selection()
assert c.static_vals == {"cog_ctrl.squash": 0.25}
print("ok: selecting a control records its unkeyed values via the API (keyed ones skipped), once it settles")

# --- panel: restored by Maya -> closed; shelf button -> built; background Maya -> never
deferred, built = [], []
C.cmds.evalDeferred = lambda fn, **k: deferred.append(fn)
C.cmds.layout = lambda *a, **k: False
C.cmds.setParent = lambda *a: None
C.cmds.columnLayout = lambda *a, **k: built.append("ui")
C.cmds.button = lambda *a, **k: "b"
C.cmds.text = lambda *a, **k: "t"
C.cmds.separator = lambda *a, **k: None
C.cmds.window = lambda *a, **k: False
ws = {}
def workspaceControl(name, exists=False, **k):
    if exists: return name in ws
    if not k.get("edit"): ws[name] = k
C.cmds.workspaceControl = workspaceControl
jobs = []
C.cmds.scriptJob = lambda **k: jobs.append(k) or len(jobs)
C._build_ui()                                   # what Maya runs when restoring a saved layout
assert deferred and not built
print("ok: a panel Maya restores from a saved layout is closed, not left blank")
deferred.clear()
C.show_ui(panel=True)
assert built == ["ui"] and not deferred and "bgcacheWorkspaceControl" in ws
assert any(j.get("event", [None])[0] == "quitApplication" for j in jobs)
print("ok: shelf button builds the panel; it's removed when Maya quits so it isn't remembered")
os.environ["BGCACHE_BACKGROUND"] = "1"; built.clear(); ws.clear()
C.show_ui(); assert not built and not ws
del os.environ["BGCACHE_BACKGROUND"]
print("ok: never shown in the background Maya")

# --- light launch: -noAutoloadPlugins on the command line
captured = []
class P:
    def __init__(s, cmd, **k): captured.append(cmd)
    def poll(s): return None
c.cfg.update({"light": True, "skip_in_background": []})
with mock.patch.object(C.subprocess, "Popen", P), mock.patch.object(C.scene, "find_maya", lambda: "/fake/maya"):
    c._launch_worker()
assert "-noAutoloadPlugins" in captured[-1]
c.cfg["light"] = False
with mock.patch.object(C.subprocess, "Popen", P), mock.patch.object(C.scene, "find_maya", lambda: "/fake/maya"):
    c._launch_worker()
assert "-noAutoloadPlugins" not in captured[-1]
print("ok: light start adds -noAutoloadPlugins (and show_ui(light_background=False) turns it off)")
