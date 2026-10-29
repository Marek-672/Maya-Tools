import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
nodes = {}   # transform -> {"shape", "attrs", "camera"}
attrs = {"|shotCamShape.nearClipPlane": 0.1, "|shotCamShape.farClipPlane": 10000.0,
         "|sideCamShape.nearClipPlane": 1.0, "|sideCamShape.farClipPlane": 5000.0}
conns = set()
def imagePlane(shape=None, camera=None, fileName=None, query=False):
    if query:
        for n in nodes.values():
            if n["shape"] == shape: return [n["camera"]]
    name = "imagePlane%d" % (len(nodes) + 1); nodes[name] = {"shape": name + "Shape", "camera": camera}
    return [name, name + "Shape"]
def rename(a, b): nodes[b] = nodes.pop(a); nodes[b]["shape"] = b + "Shape"; return b
def ls(pattern=None, type=None, long=False, **k):
    if isinstance(pattern, list): return pattern
    if pattern and pattern.startswith("bgcache_reference"): return [t for t in nodes if t.startswith("bgcache_reference")]
    return []
def listRelatives(n, shapes=False, type=None, fullPath=False, **k):
    if isinstance(n, list): n = n[0] if n else None
    if n in nodes: return [nodes[n]["shape"]]
    if n in ("|shotCam", "|sideCam"): return [n + "Shape"]
    return []
def setAttr(plug, value=None, type=None): attrs[plug] = value
cmds.imagePlane, cmds.rename, cmds.ls, cmds.listRelatives, cmds.setAttr = imagePlane, rename, ls, listRelatives, setAttr
cmds.getAttr = lambda plug: attrs[plug]
cmds.objExists = lambda n: n in ("|shotCam", "|sideCam")
cmds.listConnections = lambda plug, **k: [1] if plug in conns else []
cmds.connectAttr = lambda a, b, force=False: conns.add(b)
cmds.delete = lambda n: nodes.pop(n if isinstance(n, str) else n[0])
cmds.findKeyframe = lambda **k: 1042.0 if k["which"] == "next" else 1010.0
moved = []
def currentTime(*a, query=False, **k):
    if query: return 1001.0
    moved.append(a[0])
cmds.currentTime = currentTime
om.MSceneMessage = types.SimpleNamespace(addCallback=lambda *a: "cb", kBeforeSave=1)
from bgcache import common, controller
c = controller.Controller(); c.session = common.new_session(); c._cmd_ts = 0
p = common.paths(c.session)

c.show_image_plane("|shotCam", "/cache/ref.0001.jpg", -1000, "front")
tr, shape = c._find_plane()
assert tr == "bgcache_reference" and abs(attrs[shape + ".depth"] - 0.15) < 1e-9 and attrs[shape + ".fit"] == 0
assert attrs[shape + ".frameOffset"] == -1000 and attrs[shape + ".useFrameExtension"] == 1 and shape + ".frameExtension" in conns
assert attrs[tr + ".overrideDisplayType"] == 2 and attrs[shape + ".displayOnlyIfCurrent"] == 1 and c.save_cb == "cb"
print("ok: in front: depth just past near clip (0.15), fills the view, steps with time, can't be clicked")
attrs[shape + ".alphaGain"] = 0.4                   # your own tweak
c.show_image_plane("|shotCam", "/cache/ref.0001.jpg", -1000, "behind")
assert c._find_plane()[0] == "bgcache_reference" and len(nodes) == 1 and attrs[shape + ".depth"] == 9500.0
assert attrs[shape + ".alphaGain"] == 0.4
print("ok: behind: same plane moved to just inside far clip (9500); your attribute tweaks kept")
c.show_image_plane("|sideCam", "/cache/ref.0001.jpg", -1000, "front")
assert len(nodes) == 1 and nodes["bgcache_reference"]["camera"] == "|sideCamShape"
print("ok: switching camera re-attaches it (still one plane)")
c.remove_image_plane(); assert not nodes
print("ok: removed")

# step key works with Sync off, and tells the player to follow
c.sync_enabled = False
common.write_json_atomic(p["player_cmd"], {"cmd": "next_key", "ts": time.time()})
c._poll_player_cmd()
assert moved == [1042] and common.read_json(p["maya_time"]) == {**common.read_json(p["maya_time"]), "frame": 1042, "force": True}
print("ok: step key with Sync off moves Maya to 1042 and the player follows")
