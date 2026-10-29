"""0.8.0b13, the the studio studio build: the player opens first, fewer buttons
(three menus), 2D pan/zoom ignored in the cache, the camera you look through
pre-picked, a CPU warning, and studio updates from the releases folder."""
import os, sys, json, zipfile, tempfile, re
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
from bgcache import update

def read(*p):
    return open(os.path.join(REPO, *p)).read()

# ---- releases folder: newest newer zip wins; test builds sort before the release
rel = tempfile.mkdtemp()
for v in ("0.7.5", "0.8.0b9", "0.8.0b12", "0.8.0b13", "0.8.0b2"):
    open(os.path.join(rel, "bgcache_%s.zip" % v), "w").close()
open(os.path.join(rel, "bgcache_notes.txt"), "w").close()
open(os.path.join(rel, "bgcache_source_0.8.0b20.zip"), "w").close()     # not a release zip
assert update.newer_release(rel, "0.8.0b12") == ("0.8.0b13", os.path.join(rel, "bgcache_0.8.0b13.zip"))
assert update.newer_release(rel, "0.8.0b13") is None
assert update.newer_release(rel, "0.8.0") is None
assert update.newer_release("/no/such/folder", "0.8.0b1") is None
sub = tempfile.mkdtemp(); os.makedirs(os.path.join(sub, "releases"))
open(os.path.join(sub, "releases", "bgcache_0.8.0b14.zip"), "w").close()
assert update.newer_release(sub, "0.8.0b13") == ("0.8.0b14", os.path.join(sub, "releases", "bgcache_0.8.0b14.zip"))
print("ok: zips are found in the releases folder itself or in its releases/ subfolder (install folder layout)")
assert update.version_key("0.8.0b2") < update.version_key("0.8.0b10") < update.version_key("0.8.0")
print("ok: update check: the newest bgcache_<version>.zip newer than yours (b10 after b2; source zips ignored)")

# ---- install over the running copy: backup, swap, profile kept or replaced
def make_pkg(where, version, profile=None):
    pkg = os.path.join(where, "bgcache")
    os.makedirs(pkg)
    open(os.path.join(pkg, "__init__.py"), "w").write('__version__ = "%s"\n' % version)
    open(os.path.join(pkg, "controller.py"), "w").write("# %s\n" % version)
    if profile is not None:
        json.dump(profile, open(os.path.join(pkg, "profile.json"), "w"))
    return pkg

def make_zip(version, profile=None):
    src = tempfile.mkdtemp()
    make_pkg(src, version, profile)
    path = os.path.join(tempfile.mkdtemp(), "bgcache_%s.zip" % version)
    with zipfile.ZipFile(path, "w") as z:
        for root, _, files in os.walk(os.path.join(src, "bgcache")):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, src))
    return path

home = tempfile.mkdtemp()
installed = make_pkg(home, "0.8.0b12", {"who": "old studio profile"})
old, new, backup = update.install_over(make_zip("0.8.0b13"), installed, log=lambda *a: None)
assert (old, new) == ("0.8.0b12", "0.8.0b13")
assert '"0.8.0b13"' in open(os.path.join(installed, "__init__.py")).read()
assert json.load(open(os.path.join(installed, "profile.json"))) == {"who": "old studio profile"}
assert os.path.isfile(os.path.join(backup, "controller.py")) and ".bgcache_backups" in backup
assert not [n for n in os.listdir(home) if ".old_" in n]
print("ok: Update: the installed bgcache is backed up to .bgcache_backups and replaced; "
      "a zip without a profile keeps the installed profile.json")
update.install_over(make_zip("0.8.0b14", {"who": "new studio profile"}), installed, log=lambda *a: None)
assert json.load(open(os.path.join(installed, "profile.json"))) == {"who": "new studio profile"}
print("ok: a release zip with its own profile.json brings it")

bad = os.path.join(tempfile.mkdtemp(), "bgcache_0.9.0.zip")
with zipfile.ZipFile(bad, "w") as z:
    z.writestr("readme.txt", "not bgcache")
try:
    update.install_over(bad, installed, log=lambda *a: None)
    raise AssertionError("a zip without bgcache/ must be refused")
except RuntimeError as error:
    assert "doesn't look like a bgcache release" in str(error)
assert '"0.8.0b14"' in open(os.path.join(installed, "__init__.py")).read()
real_access = os.access
os.access = lambda path, mode: False
try:
    update.install_over(make_zip("0.8.0b15"), installed, log=lambda *a: None)
    raise AssertionError("a folder you can't write must be refused")
except RuntimeError as error:
    assert "Ask the pipeline team" in str(error)
finally:
    os.access = real_access
assert '"0.8.0b14"' in open(os.path.join(installed, "__init__.py")).read()
print("ok: a wrong zip or a folder you can't write: nothing changes, and it says why")

u = read("bgcache", "update.py")
assert "old.unload()" in u and "_forget_loaded_code()" in u and "new.shelf_click(**kwargs)" in u
assert u.index("importlib.invalidate_caches()") < u.index('importlib.import_module("bgcache.controller")')
assert "Restart Maya to finish the update." in u
c = _source.source("controller")
assert 'elif cmd == "update":' in c and "update.update_and_restart(path)" in c
assert '"releases_folder": profile.get("releases_folder") or "",' in c
p = read("bgcache", "player.py")
assert "def check_for_update(self, quiet=False):" in p and '"Update and restart"' in p
assert 'self.check_for_update(quiet=True)' in p and 'self.send_cmd("update", path=path)' in p
studio = os.path.join(REPO, "studio_private", "profile.json")
if os.path.isfile(studio):                       # the studio source only, not the public copy
    pr = json.load(open(studio))
    assert pr["releases_folder"] and pr.get("background_gpu", "follow") == "follow"
print("ok: the player checks the studio releases folder when it opens and from bgcache > Check for updates; "
      "Update and restart: stop, swap, start the new copy in the same Maya")

# ---- the player opens before your scene is copied
start = c[c.index("    def _start(self"):c.index("    def _loading_state(self")]
assert start.index("self.launch_player()") < start.index("scene_file = self._export_copy()")
assert '_loading_state("copying scene" if must_copy else "snapshotting")' in start
assert start.index("self._pre_pick_camera()") < start.index("self.launch_player()")
assert '"Copying your Maya scene"' in p and '"copying scene", "snapshotting"' in p
print("ok: the player opens first and says \"Copying your Maya scene...\" while your scene is copied")
assert "def _pre_pick_camera(self):" in c and 'modelPanel(panel, query=True, camera=True)' in c
print("ok: the camera you're looking through (or the only shot camera) is cached without picking it")

# (the b13 toolbar was replaced in b14: see test_b14.py)

# ---- 2D pan/zoom and the CPU warning
w = read("bgcache", "worker.py")
assert 'cmds.setAttr(shape + ".panZoomEnabled", False)' in w and "ignored in the cache" in w
print("ok: 2D pan/zoom is ignored in the cache (always the full frame, so a reset needs no Refresh)")
assert '"  ·  caching on CPU"' in p and "_cpu_note" not in p and "_flash_message(cpu" not in p
assert '"GPU deformers: %s"' in w
print("ok: on the CPU: a quiet \"caching on CPU\" in the status line, no pop-up; worker.log says why")
assert '"gpu": gpu_on, "gpu_reason": gpu_reason}' in c and 'self._set_gpu(bool(msg["gpu"])' in w
assert 'cmds.evaluator(name="deformer", enable=on)' in w
print("ok: the background Maya copies your GPU Override at Start; switch it in your Maya and press Refresh "
      "to switch it there too")
assert '"pid": os.getpid()' in w and "def _stop_background_directly(self):" in p
assert 'common.post_message(self.session, {"op": "quit"})' in p and "SIGKILL" in p
assert '"player_cmd"] + ".done"' in c and "def _maya_answered(self):" in p
assert "self.stop_bgcache()           # also works when your Maya is frozen" in p
print("ok: Stop works with your Maya frozen: if your Maya doesn't answer in 4 s, the player tells the "
      "background Maya to quit, and ends it if it's stuck; never while your Maya is handling it")
