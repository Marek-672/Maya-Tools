"""0.9.0b6: Help > Check for updates > Go back to an earlier version: the
copies kept on this computer (every update and drag-and-drop install keeps
one), older builds in a studio's releases folder, and older GitHub releases."""
import os
import shutil
import sys
import tempfile
import zipfile

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
from bgcache import update                                   # noqa: E402

root = os.path.realpath(tempfile.mkdtemp())


def package(where, version):
    os.makedirs(where, exist_ok=True)
    open(os.path.join(where, "__init__.py"), "w").write('__version__ = "%s"\n' % version)
    open(os.path.join(where, "controller.py"), "w").write("# %s\n" % version)
    return where


# a module install: modules/bgcache/scripts/bgcache, with kept copies in both places
scripts = os.path.join(root, "modules", "bgcache", "scripts")
live = package(os.path.join(scripts, "bgcache"), "0.9.0b6")
package(os.path.join(scripts, ".bgcache_backups", "bgcache_0.9.0b5_20261102_000000"), "0.9.0b5")
package(os.path.join(root, "modules", ".bgcache_backups", "bgcache_0.9.0b2_20261029", "scripts", "bgcache"), "0.9.0b2")
package(os.path.join(scripts, ".bgcache_backups", "bgcache_0.9.0b7_x"), "0.9.0b7")      # newer: not offered
rel = os.path.join(root, "releases")
os.makedirs(rel)
for v in ("0.9.0b4", "0.9.0b5", "0.9.0b6"):
    with zipfile.ZipFile(os.path.join(rel, "bgcache_%s.zip" % v), "w") as z:
        z.writestr("bgcache/__init__.py", '__version__ = "%s"\n' % v)
        z.writestr("bgcache/controller.py", "")

found = update.earlier_versions(scripts, "0.9.0b6", rel)
assert [(v["version"], v["where"]) for v in found] == [
    ("0.9.0b5", "on this computer"), ("0.9.0b4", "releases folder"), ("0.9.0b2", "on this computer")], found
assert [v["version"] for v in update.earlier_versions(scripts, "0.9.0b6")] == ["0.9.0b5", "0.9.0b2"]
print("ok: earlier versions: copies kept on this computer (both backup places), then the releases folder; "
      "newest first, never newer than yours")

zipped = update.zip_backup(found[0]["path"], os.path.join(root, "tmp"))
old, new, backup = update.install_over(zipped, live, log=lambda *a: None)
assert (old, new) == ("0.9.0b6", "0.9.0b5") and update._version_of(live) == "0.9.0b5"
assert update._version_of(backup) == "0.9.0b6"
assert [v["version"] for v in update.earlier_versions(scripts, "0.9.0b5")] == ["0.9.0b2"]
print("ok: going back installs that copy like an update; the version you left is kept (Check for updates "
      "can bring it back)")

update.github_releases = lambda repo, timeout=8.0: [
    {"version": v, "notes": "", "page": "", "assets": {"bgcache-%s-windows-full.zip" % v: "https://x/%s" % v}}
    for v in ("0.9.0b6", "0.9.0b5", "0.9.0b4", "0.9.0b2")]
gh = update.earlier_on_github("Marek-672/Maya-Tools", "0.9.0b6", "windows", "full")
assert [v["version"] for v in gh] == ["0.9.0b5", "0.9.0b4", "0.9.0b2"] and gh[0]["zip_url"] == "https://x/0.9.0b5"
assert update.earlier_on_github("r", "0.9.0b6", "windows", "simple") == []        # no Simple zips there
print("ok: older GitHub releases with a zip for your system and edition")

p = open(os.path.join(REPO, "bgcache", "player.py"), encoding="utf-8").read()
assert '("Go back to an earlier version", [' in p and "def go_back_to(self, item):" in p
assert 'result["earlier"] = update.earlier_versions(install_dir, __version__, self.cfg["releases_folder"])' in p
print("ok: Help > Check for updates lists 'Go back to an earlier version' with each version and where it's from")
shutil.rmtree(root, ignore_errors=True)
