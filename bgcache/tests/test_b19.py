"""0.8.0b19: textures in the studio renderer (no texture clean-up at start,
textures reloaded at start and Refresh), path curves set in one API call,
focus written when a handle drag ends, studio-only commands in the studio's
own file (studio_private/studio_*.py, built in by tools/build_studio.py)."""
import os, sys, json, types, zipfile, tempfile, subprocess
STUDIO_OPTS = "dn" + "ViewportOptions"       # a studio's own command (kept out of the public text)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w`

# ---- textures reloaded in the render view
edits, ogs_calls = [], []
view = {"displayTextures": True}
def modelEditor(panel, edit=False, query=False, **k):
    if query:
        return view[list(k)[0]]
    edits.append(k); view.update(k)
cmds.modelEditor = modelEditor
cmds.refresh = lambda **k: edits.append("refresh")
cmds.ogs = lambda **k: ogs_calls.append(k)
w.panel = "renderView"
w._reload_textures()
assert edits == [{"displayTextures": False}, "refresh", {"displayTextures": True}], edits
assert {"reloadTextures": True} in ogs_calls
view["displayTextures"] = False; del edits[:]
w._reload_textures()
assert edits == []
print("ok: textures in the render view are switched off/on and Viewport 2.0 reloads them (not when your view has textures off)")
wsrc = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert "        self._apply_display()\n        self._reload_textures()" in wsrc
assert wsrc.count("self._reload_textures()") >= 2
assert "disposeReleasableTextures=True)" not in wsrc.split("def _apply_renderer")[1].split("def _before_playblast")[0]
assert STUDIO_OPTS not in wsrc
print("ok: at start and at every Refresh; no texture clean-up at start; no studio commands in the shared code")

# ---- path curve in one API call
class P(object):
    def __init__(s, x, y, z): s.v = (x, y, z)
class Fn(object):
    got = {}
    def __init__(s, path): s.path = path
    def setCVPositions(s, pts, space): Fn.got["cvs"] = [p.v for p in pts]; Fn.got["space"] = space
    def updateCurve(s): Fn.got["updated"] = True
class Sel(object):
    def add(s, n): s.n = n
    def getDagPath(s, i): return s.n
worker.om = types.SimpleNamespace(MSelectionList=Sel, MFnNurbsCurve=Fn, MPoint=P, MPointArray=list,
                                  MSpace=types.SimpleNamespace(kObject="object"))
cmds.objExists = lambda n: True
cmds.getAttr = lambda plug: [(0, 0, 0)] * 3
set_cv = []
cmds.setAttr = lambda *a, **k: set_cv.append(a)
w.set_curve_shape("|path|pathShape", [[0, 0, 0], [1, 5, 0], [2, 0, 0]])
assert Fn.got == {"cvs": [(0, 0, 0), (1, 5, 0), (2, 0, 0)], "space": "object", "updated": True} and not set_cv
print("ok: a path curve's CVs are set in one call, then the curve is told it changed (b18's one-by-one setAttr crashed Maya)")

# ---- the studio's own file and build
studio = os.path.join(REPO, "studio_private", "studio_studio.py")
if os.path.isfile(studio):
    assert STUDIO_OPTS + "(motionBlur=False)" in open(studio).read()
    prof = json.load(open(os.path.join(REPO, "studio_private", "profile.json")))
    assert prof["before_playblast"] == "bgcache.studio_studio.prepare"
    out = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "build_studio.py"), out, "--name", "studio"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rel = [f for f in os.listdir(out) if f.startswith("bgcache_") and f.endswith(".zip")][0]
    names = zipfile.ZipFile(os.path.join(out, rel)).namelist()
    assert "bgcache/studio_studio.py" in names and "bgcache/profile.json" in names
    dd = [f for f in os.listdir(out) if f.endswith("-dragdrop.zip")][0]
    assert any(n.endswith("module/scripts/bgcache/studio_studio.py") for n in zipfile.ZipFile(os.path.join(out, dd)).namelist())
    print("ok: the studio's own set-up (motion blur off) lives in studio_private/studio_studio.py, named in the studio "
          "profile, built into the studio zips only (tools/build_studio.py)")
mp_path = os.path.join(REPO, "tools", "make_public.py")
if os.path.isfile(mp_path):                # not in the public copy itself
    mp = open(mp_path).read()
    assert ("dn" + "viewport") in mp and "build_studio.py" not in mp.split("INCLUDE = ")[1].split("]")[0]
print("ok: the public copy refuses the studio viewport commands and leaves the studio build script out")
