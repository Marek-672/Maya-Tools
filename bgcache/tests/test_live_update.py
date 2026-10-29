"""0.8.0b11: updating without restarting Maya. The installer switches off what
the old copy left running (its callbacks, the panel's buttons) and rebuilds an
open panel from the new copy; uninstall closes the panel."""
import os, sys, types, importlib.util
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)

calls = []
ui = {"layout": True, "panel": True, "visible": True, "state": True, "jobs": {7}}
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds")
api = types.ModuleType("maya.api"); om = types.ModuleType("maya.api.OpenMaya")
def scriptJob(exists=None, kill=None, force=False):
    if exists is not None:
        return exists in ui["jobs"]
    ui["jobs"].discard(kill); calls.append(("kill", kill))
cmds.scriptJob = scriptJob
cmds.layout = lambda name, exists=False: ui["layout"]
def workspaceControl(name, exists=False, query=False, visible=False):
    return ui["panel"] if exists else ui["visible"]
cmds.workspaceControl = workspaceControl
cmds.workspaceControlState = lambda name, exists=False, remove=False: ui["state"] if exists else ui.update(state=False)
def deleteUI(name):
    calls.append(("deleteUI", name))
    if name == "bgcacheLayout": ui["layout"] = False
    if name == "bgcacheWorkspaceControl": ui["panel"] = False
cmds.deleteUI = deleteUI
om.MMessage = types.SimpleNamespace(removeCallback=lambda cb: calls.append(("cb", cb)))
maya.cmds, maya.api, api.OpenMaya = cmds, api, om
sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.api": api, "maya.api.OpenMaya": om})

spec = importlib.util.spec_from_file_location("install_bgcache_t", os.path.join(REPO, "tools", "dragdrop", "install_bgcache.py"))
inst = importlib.util.module_from_spec(spec); spec.loader.exec_module(inst)

# ---- an old copy (b10: no unload()) with its quit job and scene callbacks
old = types.ModuleType("bgcache.controller"); old._quit_job = 7; old._panel_scene_cbs = [11, 12]
sys.modules["bgcache.controller"] = old
inst._retire_loaded_bgcache()
assert ("kill", 7) in calls and ("cb", 11) in calls and ("cb", 12) in calls and old._panel_scene_cbs == []
assert ("deleteUI", "bgcacheLayout") in calls and ui["panel"], calls   # contents go, the (docked) panel stays
print("ok: update: the old copy's callbacks are switched off and the panel's old buttons removed; the panel itself stays where it is")

# ---- a newer copy with unload(): the installer uses it
seen = []
old2 = types.ModuleType("bgcache.controller"); old2.unload = lambda: seen.append("unload")
sys.modules["bgcache.controller"] = old2
inst._retire_loaded_bgcache()
assert seen == ["unload"]
print("ok: copies from b11 on clean up after themselves (unload)")

# ---- the open panel is rebuilt from the new copy; a hidden one waits for the shelf button
shown = []
new = types.ModuleType("bgcache.controller"); new.show_ui = lambda: shown.append(1)
pkg = types.ModuleType("bgcache"); pkg.controller = new
sys.modules.update({"bgcache": pkg, "bgcache.controller": new})
ui.update(panel=True, visible=True)
assert inst._refresh_panel() is True and shown == [1]
ui["visible"] = False
assert inst._refresh_panel() is False and shown == [1]
print("ok: an open panel is rebuilt at once from the new copy; a closed one is rebuilt when the shelf button opens it")

# ---- uninstall closes the panel and forgets it
ui.update(panel=True, state=True); calls[:] = []
sys.modules["bgcache.controller"] = types.ModuleType("bgcache.controller")
inst._retire_loaded_bgcache(close_panel=True)
assert ("deleteUI", "bgcacheWorkspaceControl") in calls and not ui["panel"] and not ui["state"]
print("ok: uninstall closes the panel and drops its saved state")

# ---- controller.unload exists for the next update
src = _source.source("controller")
assert "\ndef unload():" in src and "_controller.stop()" in src.split("def unload():")[1][:600]
print("ok: controller.unload() stops bgcache, removes its callbacks and the panel's contents")
for name in ("maya", "maya.cmds", "maya.api", "maya.api.OpenMaya", "bgcache", "bgcache.controller"):
    sys.modules.pop(name, None)

# ---- the studio install folder's drag_into_maya.py does the same
d = open(os.path.join(REPO, "tools", "drag_into_maya.py")).read()
assert "def _retire_loaded_bgcache(" in d and "    _retire_loaded_bgcache(close_panel=True)" in d
i = open(os.path.join(REPO, "tools", "dragdrop", "install_bgcache.py")).read()
assert "    _retire_loaded_bgcache(close_panel=True)" in i and "refreshed = _refresh_panel()" not in i
print("ok: both installers update without a restart; from b12 they close an old version's panel "
      "(never rebuild it: that would start bgcache)")
