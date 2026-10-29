"""0.8.0b12: image planes in the cache. The player's reference image plane and
image planes you add after Start reach the background Maya (Refresh, or at
once for the reference plane), so the player shows your animation over them;
Refresh no longer hides every plane when the panel you last clicked has
Show > Image Planes off."""
import os, sys, json, types
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w`

planes = {"oldPlane": {"camera": "shotCam", "attrs": {}, "ref": False, "time": False},
          "rigPlane": {"camera": "shotCam", "attrs": {}, "ref": True, "time": False},
          "staleMine": {"camera": "shotCam", "attrs": {}, "ref": False, "time": False}}
setattrs = {}
def ls(*a, **k):
    if k.get("type") == "imagePlane":
        return ["|%s|%sShape" % (n, n) for n in planes]
    if a and a[0] in planes:
        return ["|" + a[0]]
    return []
def listRelatives(node, parent=False, shapes=False, fullPath=False, type=None):
    name = node.strip("|").split("|")[0]
    if parent:
        return ["|" + name]
    if shapes and type == "imagePlane":
        return ["|%s|%sShape" % (name, name)] if name in planes else []
    if shapes and type == "camera":
        return ["|shotCam|shotCamShape"]
    return []
def imagePlane(shape=None, query=False, camera=None, fileName=None):
    if query:
        return [planes[shape.strip("|").split("|")[0]]["camera"]]
    planes["imagePlane1"] = {"camera": "shotCam", "attrs": {"imageName": fileName}, "ref": False, "time": False}
    return ["imagePlane1", "imagePlaneShape1"]
def rename(old, new):
    planes[new] = planes.pop(old); return new
def delete(node):
    planes.pop(node.strip("|").split("|")[0])
def referenceQuery(node, isNodeReferenced=False):
    return planes[node.strip("|").split("|")[0]]["ref"]
def connectAttr(a, b, force=False):
    planes[b.strip("|").split("|")[0]]["time"] = True
def setAttr(plug, value, type=None):
    setattrs[plug] = value
cmds.ls, cmds.listRelatives, cmds.imagePlane, cmds.rename = ls, listRelatives, imagePlane, rename
cmds.delete, cmds.referenceQuery, cmds.connectAttr, cmds.setAttr = delete, referenceQuery, connectAttr, setAttr
cmds.objExists = lambda n: True
cmds.listConnections = lambda *a, **k: []

mine = [{"name": "oldPlane", "camera": "shotCam", "attrs": {"depth": 50.0}, "time": False, "visible": True},
        {"name": "bgcache_reference", "camera": "shotCam", "visible": True, "time": True,
         "attrs": {"imageName": "/cache/ref.0001.jpg", "frameOffset": -1000, "depth": 0.15,
                   "frameExtension": 1001.0}}]
changed = w.sync_image_planes(mine)
assert "bgcache_reference" in planes and planes["bgcache_reference"]["time"], planes
assert setattrs.get("|bgcache_reference|bgcache_referenceShape.frameOffset") == -1000
assert not any(k.endswith("bgcache_referenceShape.frameExtension") for k in setattrs), "time-driven: not set"
assert setattrs.get("|oldPlane|oldPlaneShape.depth") == 50.0
assert "staleMine" not in planes and "rigPlane" in planes, "deleted yours are removed; referenced kept"
assert changed == 2
print("ok: planes added after Start (the reference plane) are made, existing ones updated, deleted ones removed, referenced ones kept")

wsrc = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert 'cmds.ls("bgcache_reference*"' not in wsrc
print("ok: the background Maya no longer deletes the reference plane when it opens the scene")

csrc = _source.source("controller")
assert 'display["imagePlane"] = True' not in csrc and '"image_planes": scene.image_planes()' in csrc
assert "panel = _shot_camera_panel() or _active_model_panel()" in csrc
assert 'and attrs.get("displayMode", 1) != 0' in csrc and 'cmds.getAttr(shape + ".visibility")' in csrc
assert "self._send_image_planes()" not in csrc.split("def show_image_plane")[1].split("def _before_save")[0]
print("ok: b14/b17: Show > Image Planes (like every display setting since b17) comes from the viewport looking through the shot camera (no longer forced on); "
      "a plane hidden with H or set to None is off in the cache; Refresh sends them; the player's reference plane too, only at Refresh (b17)")

# ---- b14: planes as in your Maya; the player's reference plane always shows
editor = {}
def modelEditor(panel, edit=False, query=False, **flags):
    editor.update(flags)
cmds.modelEditor = modelEditor
vis = {}
cmds.getAttr = lambda plug: vis.get(plug, True)
def setAttr2(plug, value, type=None):
    setattrs[plug] = value
    if plug.endswith(".visibility"):
        vis[plug] = value
cmds.setAttr = setAttr2
w.panel = "renderView"
w.show_planes = False                          # your view: Show > Image Planes off
w._apply_plane_visibility()
assert editor["imagePlane"] is True and vis.get("|oldPlane.visibility") is False
assert vis.get("|bgcache_reference.visibility", True) is True
print("ok: Show > Image Planes off in your view: the cache hides your planes but still shows the player's reference plane")
w.show_planes = True
w._apply_plane_visibility()
assert editor["imagePlane"] is True and vis.get("|oldPlane.visibility") is True
print("ok: turned back on (Refresh): your planes show again")
planes.pop("bgcache_reference")
w.show_planes = False
w._apply_plane_visibility()
assert editor["imagePlane"] is False
print("ok: no reference plane and Show > Image Planes off: no image planes drawn or loaded in the cache")
