"""0.9.0b8: the whole shot in the player (the studio's cut, else Maya's
outer range), your playback range as the focus, and Sync linking them."""
import os, sys, json, time
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)

# ---- your Maya side: a stand-in Maya (test_sync's) with a time slider
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("\nctl._on_time_changed()\n")[0])
from bgcache import scene
rng = {"min": 1041, "max": 1072, "ast": 1001, "aet": 1093}
def playbackOptions(query=False, minTime=None, maxTime=None, animationStartTime=None, animationEndTime=None, **k):
    if query:
        return float(rng["min" if minTime else "max" if maxTime else "ast" if animationStartTime else "aet"])
    for key, value in (("min", minTime), ("max", maxTime), ("ast", animationStartTime), ("aet", animationEndTime)):
        if value is not None:
            rng[key] = value
cmds.playbackOptions = playbackOptions
scene.cmds = cmds

studio = {"start": "STUDIO_CUT_START", "end": "STUDIO_CUT_END", "shot": "SHOT"}
env = {"STUDIO_CUT_START": "1001", "STUDIO_CUT_END": "1093", "SHOT": "m0850_0630"}
r = scene.shot_range("/projects/BIRDS/m0850_0630/maya/scenes/anim_v012.mb", studio, env)
assert r == {"start": 1001, "end": 1093, "cut": [1001, 1093], "from": "studio", "maya": [1041, 1072]}, r
print("ok: the studio's cut (STUDIO_CUT_START/END) is the shot; your playback range 1041-1072 is kept as the focus")
r = scene.shot_range("/projects/BIRDS/m0850_0640/maya/scenes/anim_v003.mb", studio, env)
assert r["from"] == "outer range" and r["cut"] == [1001, 1093]
print("ok: a scene of another shot than the one Maya was launched for: Maya's outer range, not the launcher's numbers")
rng.update(ast=995, aet=1101, min=995, max=1101)
r = scene.shot_range("/projects/BIRDS/m0850_0630/maya/scenes/anim_v012.mb", studio, env)
assert (r["start"], r["end"], r["cut"]) == (995, 1101, [1001, 1093]), r
print("ok: frames animated past the cut (995-1101) are laid out; the cut stays 1001-1093")
rng.update(ast=1001, aet=1093, min=1041, max=1072)
r = scene.shot_range("/somewhere/test.ma", {}, {})
assert r["from"] == "outer range" and (r["start"], r["end"]) == (1001, 1093)
rng.update(ast=1041, aet=1072)
assert scene.shot_range("/somewhere/test.ma", {}, {})["from"] == "outer range"
print("ok: no studio settings: Maya's outer range is the shot (public default)")
rng.update(ast=1001, aet=1093)

# grow + following the player's focus
ctl.cfg = {"start": 1001, "end": 1093, "cut": [1001, 1093], "rev": 1, "trace": False}
type(ctl).running = property(lambda s: True)
posted = []
common.post_message = lambda session, msg: posted.append(msg)
rng.update(min=990, max=1060, ast=990)
ctl._on_range_changed()
assert (ctl.cfg["start"], ctl.cfg["end"], ctl.cfg["rev"]) == (990, 1093, 2)
assert posted[-1] == {"op": "grow", "start": 990, "end": 1093}
assert rd("maya_range")["range"] == [990, 1060] and rd("config")["start"] == 990
print("ok: your range going past the shot adds those frames (config rev up, the background Maya told); the range is sent")
rng.update(min=1001, max=1093)
ctl._on_range_changed()
assert (ctl.cfg["start"], ctl.cfg["end"]) == (1001, 1093) and posted[-1] == {"op": "grow", "start": 1001, "end": 1093}
print("ok: b11: your range back inside the cut: the shot goes back to the cut (1001-1093)")
rng.update(min=990, max=1060)
ctl._on_range_changed()
assert (ctl.cfg["start"], ctl.cfg["end"]) == (990, 1093)
ctl.sync_enabled = True
common.write_json_atomic(p["cameras"], {"checked": ["|cam"], "view": "|cam", "focus": [1010, 1030]})
ctl._follow_player_focus()
assert (rng["min"], rng["max"]) == (1010, 1030)
common.write_json_atomic(p["cameras"], {"checked": ["|cam"], "view": "|cam", "focus": None})
os.utime(p["cameras"], (time.time() + 5, time.time() + 5))
ctl._follow_player_focus()
assert (rng["min"], rng["max"]) == (990, 1093)
print("ok: Sync on: the player's focus is your playback range; clearing it opens your range to the whole shot")
rng.update(min=1020, max=1040)                  # you drag your range; the player's echo of an older one arrives
common.write_json_atomic(p["cameras"], {"checked": ["|cam"], "view": "|cam", "focus": [1015, 1040], "focus_from": "maya"})
os.utime(p["cameras"], (time.time() + 7, time.time() + 7))
ctl._follow_player_focus()
assert (rng["min"], rng["max"]) == (1020, 1040)
rng.update(min=990, max=1093)
print("ok: a focus the player took from your Maya isn't sent back (a late echo never undoes your drag)")
ctl.sync_enabled = False
common.write_json_atomic(p["cameras"], {"checked": ["|cam"], "view": "|cam", "focus": [1050, 1060]})
os.utime(p["cameras"], (time.time() + 9, time.time() + 9))
ctl._follow_player_focus()
assert (rng["min"], rng["max"]) == (990, 1093)
print("ok: Sync off: your range stays where it is")

# ---- the background Maya: grow makes the new frames dirty
from unittest import mock
qt.QtGui, qt.QtWidgets = mock.MagicMock(), mock.MagicMock()
sys.modules.update({"PySide2.QtGui": qt.QtGui, "PySide2.QtWidgets": qt.QtWidgets, "shiboken2": mock.MagicMock()})
_F.kTangentFixed = 1; _F.kTangentStep = 2
from bgcache import worker as W
w = W.Worker.__new__(W.Worker)
w.first, w.last, w.cfg = 1001, 1093, {"start": 1001, "end": 1093}
w.cams = {"|cam": {"dirty": set(), "versions": {}, "focus": 1001}}
W.cmds = cmds
W.log = lambda text: None
w.grow(990, 1100)
assert (w.first, w.last) == (990, 1100) and w.cams["|cam"]["dirty"] == set(range(990, 1001)) | set(range(1094, 1101))
print("ok: background Maya: grown frames are dirty (rendered when they're in the focus)")
w.cams["|cam"]["versions"] = {990: 3, 1050: 4}
w.grow(1001, 1093)
assert (w.first, w.last) == (1001, 1093) and all(f >= 1001 for f in w.cams["|cam"]["dirty"]) and w.cams["|cam"]["versions"] == {1050: 4}
print("ok: b11: back to the cut: frames outside it are dropped")
