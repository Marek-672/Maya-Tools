import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types
from unittest import mock
sys.argv = ["x"]
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])   # reuse the Maya/Qt stubs
sys.path.insert(0, REPO)
ws = {}
def workspaceControl(name, exists=False, query=False, edit=False, childArray=False, uiScript=None, **k):
    if exists: return name in ws
    if query and childArray: return ws[name]["children"] or None
    if query and k.get("floating"): return ws[name].get("floating", True)
    if edit: ws[name]["edits"].append(k); return
    ws[name] = {"children": ["mayaInternal"], "edits": [], "ui": uiScript, "kw": k}
    exec_ui = True
built = []
layouts = {}
def columnLayout(name, **k):
    layouts[name] = "bgcacheWorkspaceControl"; built.append(name)
def layout(name, exists=False, query=False, parent=False):
    if exists: return name in layouts
    if query and parent: return "MayaWindow|" + layouts[name]
cmds.layout = layout
cmds.deleteUI = lambda n: layouts.pop(n, None)
cmds.workspaceControl = workspaceControl
cmds.window = lambda *a, **k: False
cmds.setParent = lambda *a: None
cmds.columnLayout = columnLayout
cmds.separator = cmds.button = lambda *a, **k: None
cmds.text = lambda *a, **k: "label"
cmds.scriptJob = lambda **k: 1
deferred = []
cmds.evalDeferred = lambda fn, **k: deferred.append(fn)
from bgcache import controller
controller.show_ui(panel=True, width=1280)
assert len(built) == 1 and ws["bgcacheWorkspaceControl"]["kw"]["floating"] is True
assert ws["bgcacheWorkspaceControl"]["ui"] == "import bgcache.controller as bgc; bgc._build_ui()"   # plain Python (Maya wraps it)
controller._build_ui()          # Maya running the uiScript outside the shelf button: closes, never duplicates
assert deferred
controller.show_ui(panel=True)            # second call: show the existing panel
assert len(built) == 1 and ws["bgcacheWorkspaceControl"]["edits"][-1]["visible"] is True
print("ok: dockable panel built once; reopening shows it; a Maya restore closes it instead of duplicating")

# ===== 0.6.7: the panel goes with the shot and isn't restored next time =====
state = {"bgcacheWorkspaceControl": True}
def workspaceControlState(name, exists=False, remove=False):
    if exists: return state.get(name, False)
    if remove: state.pop(name, None)
cmds.workspaceControlState = workspaceControlState
cbs = {}
class SM:
    kBeforeOpen, kBeforeNew, kMayaExiting = "open", "new", "exit"
    @staticmethod
    def addCallback(msg, fn): cbs[msg] = fn; return len(cbs)
controller.om.MSceneMessage = SM
controller._panel_scene_cbs[:] = []
deleted = []
cmds.deleteUI = lambda n: (deleted.append(n), ws.pop(n, None), layouts.pop(n, None))
controller.show_ui(panel=True)
assert set(cbs) == {"open", "new", "exit"}
deferred.clear(); cbs["open"]()
assert deferred and not deleted                      # deferred: nothing deleted mid-open
deferred[-1]()
assert "bgcacheWorkspaceControl" in deleted and "bgcacheWorkspaceControl" not in state
print("ok: opening another file closes the panel (after the switch) and forgets its saved layout")
controller.show_ui(panel=True); state["bgcacheWorkspaceControl"] = True; deleted.clear()
cbs["exit"]()
assert "bgcacheWorkspaceControl" in deleted and not state
print("ok: quitting Maya closes the panel at once, so it isn't saved in the layout")
n = len(cbs); controller.show_ui(panel=True); assert len(controller._panel_scene_cbs) == 3
print("ok: callbacks added once, however often the shelf button is clicked")

# ===== 0.7.5: Maya brings the panel back while a scene opens: closed again after =====
SM.kAfterOpen, SM.kAfterNew = "after_open", "after_new"
controller._panel_scene_cbs[:] = []; cbs.clear()
controller.show_ui(panel=True)
assert {"after_open", "after_new"} <= set(cbs)
timers = []
controller.QtCore.QTimer.singleShot = lambda ms, fn: timers.append(fn)
controller.show_ui(panel=True); state["bgcacheWorkspaceControl"] = True; deleted.clear(); deferred.clear()
cbs["after_open"]()                                # the scene is in: close it (deferred) and once more later
assert deferred and timers
deferred[-1]()
assert "bgcacheWorkspaceControl" in deleted
controller.show_ui(panel=True); deleted.clear()
c = controller.get()
with mock.patch.object(type(c), "running", new=property(lambda self: True)):
    timers[-1]()                                   # bgcache running: the panel stays
assert not deleted
print("ok: after a scene opens the panel is closed again (and a moment later), unless bgcache is running")

# ===== next build: a DOCKED panel is part of your layout and stays =====
controller.show_ui(panel=True); ws["bgcacheWorkspaceControl"]["floating"] = False
state["bgcacheWorkspaceControl"] = True; deleted.clear(); deferred.clear()
cbs["open"](); [fn() for fn in list(deferred)]
assert not deleted and state.get("bgcacheWorkspaceControl")
print("ok: docked: opening another file keeps the panel")
cbs["exit"]()
assert not deleted and state.get("bgcacheWorkspaceControl")
print("ok: docked: quitting Maya keeps it in the layout, so it comes back next time")
built.clear(); deferred.clear(); layouts.clear()
controller._build_ui()            # Maya restoring an old docked panel at the next start
assert not built and deferred
print("ok: b12: a panel Maya restores from an older version's layout (docked or floating) is closed: "
      "everything is in the player now")
