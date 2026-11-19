"""0.9.0b12: onion skin counts (and stopping at your frames), the reference
image plane's opacity, cameras moved without keys."""
import os, sys, time, json, types
TESTS = os.path.dirname(os.path.abspath(__file__))

# ---- onion skin: counted in drawings, nearest first, none from outside your frames
src = open(os.path.join(TESTS, "test_drawer.py")).read()
exec(src.split("# a stroke: canvas points map")[0])     # Drawer d (stand-in Qt), player, Rect
frames = {str(f): [1] for f in (1130, 1140, 1145, 1150, 1155, 1160, 1170)}
assert drawing.onion_keys(frames, 1150, 2, 1) == ([1145, 1140], [1155])
assert drawing.onion_keys(frames, 1152, 1, 3) == ([1150], [1155, 1160, 1170])       # between drawings
assert drawing.onion_keys(frames, 1150, 0, 0) == ([], [])
assert drawing.onion_keys(frames, 1150, 5, 5, first=1142, last=1160) == ([1145], [1155, 1160])
print("ok: onion skin: your count of drawings before and after, nearest first; none outside the frames you have")

assert d.onion_before == 1 and d.onion_after == 1
mine = d.mine_now()
for f in (1130, 1140, 1145, 1150, 1155, 1160):
    mine.add_stroke(f, {"c": "#e8c547", "w": 4.0, "p": [[10, 10, 1.0], [20, 20 + f - 1100, 1.0]]})
calls = []
strokes_mod = sys.modules["bgcache.drawui_strokes"]
strokes_mod.paint_strokes = lambda p, strokes, opacity=1.0, tint=None: calls.append((round(opacity, 3), tint, (strokes or [{}])[0].get("p", [[0, 0]])[-1][1] + 1100 - 20 if strokes else None))
d.on, d.onion, d.onion_before, d.onion_after = True, True, 2, 1
player.start, player.end, player.frame = 1001, 1200, 1150
d.paint(mock.MagicMock(), Rect(0, 0, 960, 540), 1150)
ghosts = [(a, t, f) for a, t, f in calls if t]
assert ghosts == [(0.18, "#ff8a7a", 1140), (0.3, "#ff8a7a", 1145), (0.3, "#7ad1ff", 1155)], ghosts
calls[:] = []
player.start = 1142                                   # your frames start at 1142: 1140 is outside
d.paint(mock.MagicMock(), Rect(0, 0, 960, 540), 1150)
assert [(a, f) for a, t, f in calls if t] == [(0.3, 1145), (0.3, 1155)]
d.save_prefs()
assert player.prefs["drawing"]["onion_before"] == 2 and player.prefs["drawing"]["onion_after"] == 1
panel_src = open(os.path.join(os.path.dirname(TESTS), "bgcache", "drawui_panel.py")).read()
assert "self.onion_spins" in panel_src and "drawing.ONION_MAX" in panel_src
print("ok: 2 before (red, the nearer one stronger) and 1 after (blue) are drawn; a drawing outside your frames "
      "isn't a ghost; the counts are remembered; Before / After boxes in the strip")

# ---- the reference image plane's opacity
import subprocess
check = r'''
import os, sys, json
TESTS = %r
__file__ = os.path.join(TESTS, 'test_b12_part.py')
exec(open(os.path.join(TESTS, "test_plane.py")).read().split('c.show_image_plane("|shotCam", "/cache/ref.0001.jpg", -1000, "front")')[0])
c.show_image_plane("|shotCam", "/cache/ref.0001.jpg", -1000, "front", 0.5)
assert attrs["bgcache_referenceShape.alphaGain"] == 0.5
c.set_image_plane_alpha(0.25)
assert attrs["bgcache_referenceShape.alphaGain"] == 0.25
c.set_image_plane_alpha(7)
assert attrs["bgcache_referenceShape.alphaGain"] == 1.0
common.write_json_atomic(p["player_cmd"], {"cmd": "image_plane_alpha", "alpha": 0.4, "ts": 5})
c._poll_player_cmd()
assert attrs["bgcache_referenceShape.alphaGain"] == 0.4
c.remove_image_plane(); c.set_image_plane_alpha(0.3)        # no plane: nothing to set, no error
print("ok: your Maya: the image plane is made with the player's opacity, and the slider sets its Alpha Gain (0-1)")
''' % TESTS
r = subprocess.run([sys.executable, "-c", check], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, cwd=TESTS)
assert "ok: your Maya" in r.stdout, r.stdout
print(r.stdout.strip().splitlines()[-1])

check = r'''
import os, sys, json
TESTS = %r
__file__ = os.path.join(TESTS, 'test_b12_part.py')
exec(open(os.path.join(TESTS, "test_player.py")).read().split("assert P.shot_ids")[0])
P._save_prefs = lambda: None
assert P.plane_alpha == 1.0 and P.plane_mode is None
P.set_plane_alpha(0.4)
assert P.prefs["plane_alpha"] == 0.4 and not os.path.exists(P.p["player_cmd"])
P.plane_mode = "front"
P.set_plane_alpha(0.7)
sent = json.load(open(P.p["player_cmd"]))
assert sent["cmd"] == "image_plane_alpha" and sent["alpha"] == 0.7
ui = open(os.path.join(REPO, "bgcache", "continuity", "ui.py")).read()
assert "self._plane_opacity_item(menu)" in ui and "alpha=self.plane_alpha" in ui
print("ok: player: Image plane opacity (in the shot's menu) is remembered, sent with a new plane, and to a plane that's there")
''' % TESTS
r = subprocess.run([sys.executable, "-c", check], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, cwd=TESTS)
assert "ok: player" in r.stdout, r.stdout
print(r.stdout.strip().splitlines()[-1])

# ---- cameras moved without keys
check = r'''
import os, sys, json, time, types
TESTS = %r
__file__ = os.path.join(TESTS, 'test_b12_part.py')
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("\nctl._on_time_changed()\n")[0])
from bgcache import scene
cam, shape = "|rig|follow|followCam", "|rig|follow|followCam|followCamShape"
vals = {}
from bgcache import controller_cameras as cc
for a in cc.TRANSFORM_ATTRS: vals[cam + "." + a] = 0.0
for a in cc.SHAPE_ATTRS: vals[shape + "." + a] = 1.0
vals[shape + ".focalLength"] = 35.0
keyed = {cam + ".rotateY"}                                   # driven or keyed: never sent
cmds.objExists = lambda n: n in (cam, shape)
cmds.listRelatives = lambda n, **k: [shape] if n == cam and k.get("type") == "camera" else []
cmds.listConnections = lambda plug, **k: ["curve"] if plug in keyed else []
cmds.getAttr = lambda plug: vals[plug]
class Sel(object):
    def add(self, n): self.n = n
    def getDependNode(self, i): return self.n
om.MSelectionList = Sel
cbs, removed = [], []
om.MNodeMessage = types.SimpleNamespace(kAttributeSet=8, kAttributeEval=4,
    addAttributeChangedCallback=lambda node, fn, data: cbs.append((node, fn, data)) or len(cbs))
om.MMessage = types.SimpleNamespace(removeCallback=lambda cb: removed.append(cb))
held = [False]
scene._mouse_held = lambda: held[0]
posted = []
common.post_message = lambda session, msg: posted.append(msg)
type(ctl).running = property(lambda s: True)
ctl.cfg = {"start": 1001, "end": 1093, "trace": False}
ctl._watch_cameras([cam])
assert [n for n, fn, data in cbs] == [cam, shape]
ctl._watch_cameras([cam])
assert len(cbs) == 2
print("ok: the cameras being cached are watched (transform and shape), once")
fire = lambda kind=8: cbs[0][1](kind, None, None, cam)
vals[cam + ".translateX"] = 5.0; vals[cam + ".rotateY"] = 30.0
fire()
ctl._send_moved_cameras()
assert not posted                                             # still moving (0.4 s not up)
ctl._camera_moved[cam] = time.time() - 1
held[0] = True; ctl._send_moved_cameras(); assert not posted  # mouse still down: you're tumbling
held[0] = False; ctl._send_moved_cameras()
assert posted == [{"op": "statics", "values": [[cam + ".translateX", 5.0]], "ranges": [[1001, 1093]]}], posted
print("ok: you stop tumbling: the camera's new unkeyed values are sent and the shot re-renders; keyed values are left to the curves")
fire(4); ctl._send_moved_cameras()                            # an evaluation, not a set
fire(); ctl._camera_moved[cam] = time.time() - 1; ctl._send_moved_cameras()     # set to the same values
vals[shape + ".focalLength"] = 50.0
cbs[1][1](8, None, None, cam); ctl._camera_moved[cam] = time.time() - 1; ctl._send_moved_cameras()
assert len(posted) == 2 and posted[1]["values"] == [[shape + ".focalLength", 50.0]]
print("ok: nothing sent when nothing changed; a new focal length is sent")
ctl._watch_cameras([])
assert removed == [1, 2]
print("ok: a camera no longer cached is no longer watched")
# 0.9.0b17: a free image plane (a card in the scene) is watched like a camera
plane, pshape = "|ref_take1", "|ref_take1|ref_takeShape1"
for a in cc.TRANSFORM_ATTRS: vals[plane + "." + a] = 0.0
for a in cc.FREE_PLANE_ATTRS: vals[pshape + "." + a] = 1.0
cmds.ls = lambda **k: [pshape, "|cam|camShape|onCam|onCamShape"] if k.get("type") == "imagePlane" else []
cmds.imagePlane = lambda s, **k: [""] if s == pshape else ["|cam|camShape"]     # Maya answers [""] for a free plane
cmds.objExists = lambda n: n in (cam, shape, plane, pshape)
cmds.listRelatives = lambda n, **k: ([plane] if n == pshape and k.get("parent") else
                                     [pshape] if n == plane and k.get("type") == "imagePlane" else
                                     [shape] if n == cam and k.get("type") == "camera" else [])
assert cc.free_planes() == [plane]
del cbs[:]; del posted[:]
ctl._watch_cameras([cam])
assert [n for n, fn, data in cbs] == [cam, shape, plane, pshape]
vals[plane + ".translateZ"] = -300.0
cbs[2][1](8, None, None, plane); ctl._camera_moved[plane] = time.time() - 1; ctl._send_moved_cameras()
assert posted[-1]["values"] == [[plane + ".translateZ", -300.0]]
print("ok: b17: a free image plane (not the ones on a camera) is watched too: move it and the cache follows")
sent = ctl.free_plane_values()
assert [plane + ".translateZ", -300.0] in sent and [pshape + ".width", 1.0] in sent and len(sent) == 14
print("ok: b17: Refresh sends every free image plane's place and size")
''' % TESTS
r = subprocess.run([sys.executable, "-c", check], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, cwd=TESTS)
assert r.stdout.count("ok:") == 6, r.stdout
print("\n".join(l for l in r.stdout.splitlines() if l.startswith("ok:")))
