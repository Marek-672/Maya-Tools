"""0.8.0b7: drag_into_maya.py, the studio's drag-and-drop for the install_bgcache
folder. It must do exactly what ./install does (same releases/, same
~/maya/<ver>/scripts/bgcache, same backups), never lose a version, ask before
going back, and leave ./install --list / --rollback working."""
import os, sys, types, shutil, subprocess, tempfile, zipfile
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)

root = tempfile.mkdtemp()
user = os.path.join(root, "maya")                         # what Maya reports as userAppDir
os.makedirs(user)
folder = os.path.join(root, "install_bgcache")            # the shared install folder
os.makedirs(os.path.join(folder, "releases"))
for f in ("drag_into_maya.py", "install_bgcache.py"):
    shutil.copy(os.path.join(REPO, "tools", f), folder)

def make_release(version):
    path = os.path.join(folder, "releases", "bgcache_%s.zip" % version)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("bgcache/__init__.py", '__version__ = "%s"\n' % version)
        z.writestr("bgcache/controller.py", "# fake\n")
        z.writestr("bgcache/icons/bgcache.png", "png")
for v in ("0.7.5", "0.8.0b6", "0.8.0b7"):
    make_release(v)

# Maya stubs
cmds = types.ModuleType("maya.cmds")
cmds.internalVar = lambda **k: user + "/"
cmds.about = lambda **k: "2024"
asked = []
cmds.confirmDialog = lambda **k: asked.append(k["message"]) or k["button"][0]
mel = types.ModuleType("maya.mel")
def _no_shelf(*a): raise RuntimeError("no shelf in tests")
mel.eval = _no_shelf
maya = types.ModuleType("maya"); maya.cmds, maya.mel = cmds, mel
sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.mel": mel})

sys.path.insert(0, folder)
import drag_into_maya as dd
scripts = os.path.join(user, "2024", "scripts")
target = os.path.join(scripts, "bgcache")
backups = os.path.join(scripts, ".bgcache_backups")
def installed():
    return dd._cli().version_of(target)
def n_backups():
    return len(os.listdir(backups)) if os.path.isdir(backups) else 0

out = dd.run(quiet=True, choice="newest")
assert installed() == "0.8.0b7", out
assert "bgcache 0.8.0b7 is installed for Maya 2024." in out
assert os.path.isfile(os.path.join(user, "2024", "prefs", "icons", "bgcache.png"))
print("ok: first drop installs the newest build into ~/maya/2024/scripts/bgcache, like ./install")

out = dd.run(quiet=True, choice="version", version="0.7.5")
assert installed() == "0.7.5" and n_backups() == 1, out
assert "(was 0.8.0b7)" in out
print("ok: Other version installs 0.7.5; b7 is kept in .bgcache_backups")

out = dd.run(quiet=True, choice="rollback")
assert installed() == "0.8.0b7", out
print("ok: Roll back puts b7 back")

out = dd.run(quiet=True, choice="newest")
assert installed() == "0.8.0b7" and n_backups() >= 2
for b in os.listdir(backups):                      # every backup is a whole copy, none nested in another
    assert os.path.isfile(os.path.join(backups, b, "__init__.py")) and not os.path.exists(os.path.join(backups, b, "bgcache")), b
print("ok: reinstalling the same version keeps a backup too")

# Going back asks first; Cancel changes nothing
asked.clear()
cmds.confirmDialog = lambda **k: asked.append(k["message"]) or k["button"][-1]       # always Cancel
before = n_backups()
assert dd.run(choice="version", version="0.8.0b6") == "cancelled"
assert installed() == "0.8.0b7" and n_backups() == before
assert any("goes BACK from 0.8.0b7 to the older 0.8.0b6" in m for m in asked), asked
print("ok: going back to an older build asks first, and Cancel leaves everything as it was")

# The main dialog, Cancel: nothing happens
asked.clear()
assert dd.run() == "cancelled" and installed() == "0.8.0b7"
assert "Installed now:  0.8.0b7" in asked[0] and "Newest build:  0.8.0b7" in asked[0]
print("ok: the dialog shows what's installed and the newest build")
cmds.confirmDialog = lambda **k: asked.append(k["message"]) or k["button"][0]

# A drag-and-drop module copy (modules/bgcache) would compete: moved aside, not deleted
mod_dir = os.path.join(user, "modules", "bgcache", "scripts", "bgcache")
os.makedirs(mod_dir)
open(os.path.join(mod_dir, "__init__.py"), "w").write('__version__ = "0.8.0b7"\n')
open(os.path.join(user, "modules", "bgcache.mod"), "w").write("+ bgcache 0.8.0b7 bgcache\n")
out = dd.run(quiet=True, choice="newest")
assert not os.path.exists(os.path.join(user, "modules", "bgcache"))
assert not os.path.exists(os.path.join(user, "modules", "bgcache.mod"))
assert len(os.listdir(os.path.join(user, "modules", ".bgcache_backups"))) == 2
assert "second copy" in out
print("ok: a module copy from the other installer is moved to modules/.bgcache_backups")

# Refuses while bgcache is running
fake = types.ModuleType("bgcache.controller"); fake.get = lambda: types.SimpleNamespace(running=True)
sys.modules["bgcache.controller"] = fake
out = dd.run(quiet=True, choice="version", version="0.7.5")
assert "press Stop first" in out and installed() == "0.8.0b7"
del sys.modules["bgcache.controller"]
print("ok: won't install while bgcache is running")

assert "isn't in releases/" in dd.run(quiet=True, choice="version", version="9.9")
cmds.confirmDialog = lambda **k: "0.7.5" if "0.7.5" in k["button"] else k["button"][0]
out = dd.run(choice="version")                      # the version buttons, then "Go back to 0.7.5"
assert installed() == "0.7.5", out
dd.run(quiet=True, choice="newest")
print("ok: Other version... shows build buttons; picking 0.7.5 installs it")
print("ok: an unknown version is refused with the list")

# ./install still sees the same installs and backups
env = dict(os.environ, MAYA_APP_DIR=user)
res = subprocess.run([sys.executable, os.path.join(folder, "install_bgcache.py"), "--list"],
                     capture_output=True, text=True, env=env)
assert "installed: 0.8.0b7" in res.stdout and "0.7.5" in res.stdout and "previous installs" in res.stdout, res.stdout
res = subprocess.run([sys.executable, os.path.join(folder, "install_bgcache.py"), "--version", "0.7.5"],
                     capture_output=True, text=True, env=env)
assert "Installing bgcache 0.7.5" in res.stdout and installed() == "0.7.5", res.stdout + res.stderr
res = subprocess.run([sys.executable, os.path.join(folder, "install_bgcache.py"), "--rollback"],
                     capture_output=True, text=True, env=env)
assert "Rolled back from 0.7.5 to 0.8.0b7. Restart Maya." in res.stdout, res.stdout + res.stderr
print("ok: ./install --list, --version and --rollback work on the same installs")
shutil.rmtree(root, ignore_errors=True)
