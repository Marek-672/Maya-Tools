"""0.9.0b8: drawing on the shots around yours (continuity), saved to that
shot's drawings folder under your name; that shot's artist finds them."""
import os, sys, types, json
TESTS = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(TESTS, "test_drawer.py")).read()
exec(src.split("shot_root = os.path.join")[0])          # stand-in Qt, drawui imported
from bgcache import profile
jobs = os.path.join(root, "jobs")
profile.use({"shot_folder": jobs + "/{show}/{shot}", "drawings_folder": "{shot_folder}/maya/bgcache",
             "sequence_from_shot": "{sequence}_*"})
scene = os.path.join(jobs, "BIRDS", "sq050_0472", "maya", "scenes", "a.mb")

class Rect:
    def __init__(s, x, y, w, h): s._x, s._y, s._w, s._h = x, y, w, h
    def x(s): return s._x
    def y(s): return s._y
    def width(s): return s._w
class Pt:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y

flashes = []
segments = [{"kind": "before", "shot": "sq050_0471", "n": 24, "first": 1001},
            {"kind": "live", "shot": "sq050_0472", "n": 48}]
def _locate(pos):
    o = 0
    for s in segments:
        if pos < o + s["n"]:
            return s, pos - o
        o += s["n"]
player = types.SimpleNamespace(
    cfg={"width": 960, "height": 540, "user": "artist", "original_scene": scene, "cameras": []},
    prefs={}, shot_ids=("BIRDS", "sq050_0472", "sq050"), live_shot="sq050_0472", view="|sq050_0472_cam",
    canvas=mock.MagicMock(), last_target=Rect(0, 0, 960, 540), start=1001, pos=30, segments=segments,
    _locate=_locate, _flash_message=lambda text, seconds=3.0: flashes.append(text), _save_prefs=lambda: None)
d = drawui.Drawer(player)
d.root = profile.drawings_root(scene)
assert d.place()["key"] == "sq050_0472_cam" and d.place()["frame"] == 1007 and d.place()["first"] == 1001
player.pos = 5
place = d.place()
other = os.path.join(jobs, "BIRDS", "sq050_0471", "maya", "bgcache")
assert place == {"key": "sq050_0471_cam@sq050_0471", "root": other, "folder": "sq050_0471_cam",
                 "shot": "sq050_0471", "frame": 1006, "first": 1001, "last": 1024}, place
print("ok: on a shot before yours: its drawings folder, its camera folder (your camera's name with its shot), its frame")
player.view = "|shotCam"
assert d.folder_for("sq050_0471") == "shotCam"
player.view = "|sq050_0472_cam"
print("ok: a camera named the same in every shot keeps its name")

assert d.press(Pt(100, 100)); d.move(Pt(200, 120)); d.move(Pt(300, 140)); d.release(Pt(300, 140))
mine = d.mine_now()
assert mine.path == os.path.join(other, "artist", "drawings", "sq050_0471_cam", "layers.json")
assert mine.dirty and d.ticks() == {1006}
assert d.save_now() and json.load(open(mine.path))["layers"][0]["frames"].get("1006")
print("ok: a stroke on that shot is saved in its folder, under your name, on its frame (1006)")
assert d.ticks("sq050_0472_cam") == set()
print("ok: your own shot's drawings are separate")

# that shot's own artist sees you among the people with drawings there
seen = drawing.find_people(other, "sam", "sq050_0471_cam")
assert [p["user"] for p in seen] == ["artist"]
print("ok: sq050_0471's artist finds your drawings there, like anyone else's")

# a profile without drawings_folder: no drawing on other shots, and it says why
profile.use({})
d2 = drawui.Drawer(player)
assert d2.place() is None
player.pos = 5; flashes[:] = []
assert not d2.press(Pt(10, 10)) and "drawings_folder" in flashes[-1]
print("ok: without a drawings folder in the profile, drawing on other shots says why")
profile.use(None)

# b10: a drawing outside the frames you have (before the cut) never shows,
# held or not, until those frames are yours too
from bgcache import drawing as _dr
frames = {"995": [1], "1010": [2]}
assert _dr.held_key(frames, 1003, True) == 995           # plain hold: carries in from 995
assert _dr.held_key(frames, 1003, 1001) is None          # hold from 1001: nothing before 1010
assert _dr.held_key(frames, 1012, 1001) == 1010
assert _dr.held_key(frames, 996, 990) == 995             # range opened to 990: 995 shows again
assert _dr.held_key(frames, 1003, False) is None
profile.use({"shot_folder": jobs + "/{show}/{shot}", "drawings_folder": "{shot_folder}/maya/bgcache"})
d3 = drawui.Drawer(player); d3.root = profile.drawings_root(scene)
player.pos = 5
assert d3.hold_from() == 1001                            # the shot before yours: its movie starts at 1001
d3.hold = False
assert d3.hold_from() is False
profile.use(None)
print("ok: b10: drawings outside the frames you have never show, held or not; open the range and they do")
