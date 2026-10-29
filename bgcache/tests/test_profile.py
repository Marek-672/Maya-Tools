"""1.0: the pipeline profile: where shots, footage and drawings are.
Generic (no profile), the studio fixture (0.7.5 behaviour), and the
example studio profile with the sequence as a folder."""
import os, sys, json, tempfile, shutil
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
home = tempfile.mkdtemp(); os.environ["HOME"] = home
os.environ.pop("BGCACHE_PROFILE", None)
import types
from unittest import mock
qt = types.ModuleType("PySide2"); qt.QtCore = mock.MagicMock(); qt.QtGui = mock.MagicMock()
sys.modules.update({"PySide2": qt, "PySide2.QtCore": qt.QtCore, "PySide2.QtGui": qt.QtGui})
sys.path.insert(0, REPO)
from bgcache import profile as pf
from bgcache.continuity import resolver as cr, reel

def use(path):
    if path:
        os.environ["BGCACHE_PROFILE"] = path
    else:
        os.environ.pop("BGCACHE_PROFILE", None)
    pf._context.clear(); pf._extra.clear()
    return pf.load(force=True)

# ---- generic: no profile anywhere
prof = use(None)
assert pf.source() == "built-in generic profile" and prof["shot_folder"] == ""
assert pf.parse_shot("/projects/BIRDS/sq050_0472/maya/scenes/x.mb") is None
assert cr.get_departments() == [] and reel.department_order() == []
proj = os.path.join(home, "projects", "walk")
assert pf.drawings_root(os.path.join(proj, "scenes", "walk_v012.mb"), proj) == os.path.join(proj, "bgcache", "walk")
assert pf.drawings_root(os.path.join(proj, "scenes", "walk.v3.ma"), proj) == os.path.join(proj, "bgcache", "walk")
assert pf.drawings_root("/elsewhere/run_V004.mb", proj) == "/elsewhere/bgcache/run"
assert pf.drawings_root("/elsewhere/run_V004.mb", None) == "/elsewhere/bgcache/run"
assert pf.drawings_root(os.path.join(proj + "_other", "a.mb"), proj) == os.path.join(proj + "_other", "bgcache", "a")
assert pf.drawings_root("", proj) == os.path.join(home, ".bgcache", "drawings", "untitled")
assert pf.scene_stem("v001.mb") == "v001" and pf.scene_stem("my shot v2.mb") == "my_shot"
print("ok: no profile: no shots, no departments; drawings in <project>/bgcache/<scene> (version left out), else next to the scene")
info_mov = {"source_type": "single_movie", "source_path": "/x/a.mov"}
assert reel.movie_skip(info_mov, 341) == 0
print("ok: no profile: movies have no slate")

# ---- the studio profile (fixture): exactly 0.7.5
use(os.path.join(TESTS, "fixtures", "studio_profile.json"))
assert pf.parse_shot("/projects/BIRDS/sq050_0472/maya/scenes/x.mb") == ("BIRDS", "sq050_0472", "sq050")
assert pf.parse_shot("/projects/BIRDS/sq050_0472") == ("BIRDS", "sq050_0472", "sq050")
assert pf.parse_shot("/home/me/x.mb") is None and pf.parse_shot("/projects/BIRDS") is None
assert pf.drawings_root("/projects/BIRDS/sq050_0472/maya/scenes/x.mb", "/projects/BIRDS/sq050_0472/maya") == "/projects/BIRDS/sq050_0472/maya/bgcache"
assert [d["name"] for d in cr.get_departments()] == ["P", "WP", "shoco", "lighting", "editorial"]
assert reel.department_order() == ["P", "WP", "shoco", "editorial", "lighting"]
print("ok: studio profile: /projects/<show>/<shot>, sequence from the shot name, drawings in <shot>/maya/bgcache, Auto order")
# the shot reference tool's own departments (read only) replace the profile's
hook = os.path.join(home, ".studio_ref_config.json")
json.dump({"departments": [{"name": "X", "base_path": "/a/{shot}", "version_pattern": "X_v*",
                            "source_type": "image_sequence"}]}, open(hook, "w"))
before = open(hook).read()
assert [d["name"] for d in cr.get_departments()] == ["X"]
assert open(hook).read() == before
os.remove(hook)
print("ok: departments edited in the shot reference tool are used; its file is only read")
# sequence listing from a fake /projects tree, via the profile's shot_folder
jobs = tempfile.mkdtemp()
studio = json.load(open(os.path.join(TESTS, "fixtures", "studio_profile.json")))
studio["shot_folder"] = jobs + "/{show}/{shot}"
for d in studio["departments"]:
    d["base_path"] = d["base_path"].replace("/projects", jobs)
mine = os.path.join(home, "studio.json"); json.dump(studio, open(mine, "w"))
use(mine)
for shot in ("sq050_0460", "sq050_0472", "sq050_0480", "m0060_0010", "sq050x_0001"):
    os.makedirs(os.path.join(jobs, "BIRDS", shot))
open(os.path.join(jobs, "BIRDS", "sq050_9999"), "w").close()      # a file, not a shot
assert cr.list_shots_in_sequence("BIRDS", "sq050") == ["sq050_0460", "sq050_0472", "sq050_0480"]
seq = os.path.join(jobs, "BIRDS", "sq050_0472", "work", "mov", "P_sq050_0472_anim_v007", "1920x1080")
os.makedirs(seq)
for f in (1001, 1002, 1003):
    open(os.path.join(seq, "P_sq050_0472_anim_v007.%d.jpg" % f), "w").close()
os.makedirs(os.path.join(jobs, "BIRDS", "sq050_0472", "work", "mov", "P_sq050_0472_anim_v003"))
found = cr.resolve_shot("BIRDS", "sq050_0472")
assert found["department"] == "P" and found["version"] == 7 and found["frame_count"] == 3 and found["start_frame"] == 1001
print("ok: studio profile: sequence's shots listed from the shot folders; newest P version found")
with_slate = {"source_type": "single_movie", "source_path": jobs + "/BIRDS/sq050_0472/movie/cgr/a.mov"}
assert reel.movie_skip(with_slate, 4) == 1 and reel.movie_skip(with_slate, 3) == 0
print("ok: studio profile: a movie one frame longer than the shot skips its slate")

# ---- the example studio profile: sequence as a folder, {shot_folder} in departments
ex = json.load(open(os.path.join(REPO, "profiles", "example_studio.json")))
proj = tempfile.mkdtemp()
ex["shot_folder"] = proj + "/{show}/shots/{sequence}/{shot}"
ex["departments"][0]["base_path"] = "{shot_folder}/renders/anim"
mine = os.path.join(home, "example.json"); json.dump(ex, open(mine, "w"))
use(mine)
scene = proj + "/BIRDS/shots/sq010/sh0040/anim/scenes/sh0040_anim_v002.ma"
assert pf.parse_shot(scene) == ("BIRDS", "sh0040", "sq010")
assert pf.drawings_root(scene) == os.path.normpath(proj + "/BIRDS/shots/sq010/sh0040/review/bgcache")
for shot in ("sh0010", "sh0040", "sh0050"):
    os.makedirs(os.path.join(proj, "BIRDS", "shots", "sq010", shot))
os.makedirs(os.path.join(proj, "BIRDS", "shots", "sq020", "sh0100"))
assert cr.list_shots_in_sequence("BIRDS", "sq010") == ["sh0010", "sh0040", "sh0050"]
frames = os.path.join(proj, "BIRDS", "shots", "sq010", "sh0050", "renders", "anim", "sh0050_anim_v004")
os.makedirs(frames); open(os.path.join(frames, "sh0050_anim_v004.0101.png"), "w").close()
found = cr.resolve_shot("BIRDS", "sh0050")
assert found and found["department"] == "anim" and found["version"] == 4 and found["start_frame"] == 101, found
print("ok: example profile: sequence folder, neighbour shots listed, {shot_folder} filled in for a neighbour")
win = proj.replace("/", "\\") + "\\BIRDS\\shots\\sq010\\sh0040\\a.ma"
assert pf.parse_shot(win) == ("BIRDS", "sh0040", "sq010")
print("ok: Windows-style paths (backslashes) match the same shot")

# ---- where the profile comes from
use(None)
pkg = os.path.join(REPO, "bgcache", "profile.json")
assert not os.path.exists(pkg)
own = os.path.join(home, ".bgcache"); os.makedirs(own, exist_ok=True)
json.dump({"shot_folder": "/own/{shot}"}, open(os.path.join(own, "profile.json"), "w"))
assert pf.load(force=True)["shot_folder"] == "/own/{shot}" and pf.source().endswith(os.path.join(".bgcache", "profile.json"))
json.dump({"shot_folder": "/pkg/{shot}"}, open(pkg, "w"))
try:
    assert pf.load(force=True)["shot_folder"] == "/pkg/{shot}"          # the installed one beats your own
    use(mine); assert pf.get("shot_folder").startswith(proj)             # BGCACHE_PROFILE beats both
finally:
    os.remove(pkg)
bad = os.path.join(home, "bad.json"); open(bad, "w").write("{ not json")
assert use(bad)["shot_folder"] == "" and pf.source() == "built-in generic profile"
os.environ.pop("BGCACHE_PROFILE")
print("ok: profile from BGCACHE_PROFILE, then the installed bgcache folder, then ~/.bgcache; unreadable -> generic")
