"""0.8.0b3: the drag-and-drop installer (tools/dragdrop/install_bgcache.py)
and the release zips (tools/build_release.py), with a fake Maya."""
import os, sys, types, tempfile, importlib.util, zipfile, shutil
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, os.path.join(REPO, "tools"))
import build_release

# ---- a fake Maya: user folder somewhere unusual (like E:/Users/.../Documents/maya)
user = os.path.join(tempfile.mkdtemp(), "Other Drive", "Documents", "maya")
os.makedirs(os.path.join(user, "2027", "prefs"))
shelves = {"Animation": [], "Custom": []}
buttons, dialogs = {}, []
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds"); mel = types.ModuleType("maya.mel")
cmds.internalVar = lambda userAppDir=False, userPrefDir=False: (user + "/") if userAppDir else os.path.join(user, "2027", "prefs") + "/"
def confirmDialog(**k):
    dialogs.append(k); return k.get("defaultButton")
cmds.confirmDialog = confirmDialog
cmds.tabLayout = lambda top, query=True, selectTab=False, childArray=False: "Animation" if selectTab else list(shelves)
def shelfLayout(tab, query=False, childArray=False, exists=False):
    return tab in shelves if exists else list(shelves.get(tab, []))
cmds.shelfLayout = shelfLayout
cmds.objectTypeUI = lambda b: "shelfButton"
def shelfButton(button=None, parent=None, edit=False, query=False, command=None, **k):
    if query:
        return buttons[button]["command"]
    if edit:
        buttons[button].update(k, command=command); return button
    name = "btn%d" % (len(buttons) + 1)
    buttons[name] = dict(k, command=command, tab=parent); shelves[parent].append(name); return name
cmds.shelfButton = shelfButton
def deleteUI(b):
    shelves[buttons[b]["tab"]].remove(b); del buttons[b]
cmds.deleteUI = deleteUI
mel.eval = lambda s: None
maya.cmds, maya.mel = cmds, mel
sys.modules.update({"maya": maya, "maya.cmds": cmds, "maya.mel": mel})

def staged(full):
    root = os.path.join(tempfile.mkdtemp(), "bgcache-test")
    os.makedirs(root)
    build_release.stage(root, full, "windows")
    return root

def load_installer(root):
    spec = importlib.util.spec_from_file_location("install_bgcache", os.path.join(root, "install_bgcache.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

version = build_release.version()
modules = os.path.join(user, "modules")
target = os.path.join(modules, "bgcache")

# ---- fresh install
inst = load_installer(staged(full=True))
report = inst.install(quiet=True)
assert os.path.isfile(os.path.join(target, "scripts", "bgcache", "controller.py"))
assert os.path.isfile(os.path.join(target, "icons", "bgcache.png"))
assert open(os.path.join(modules, "bgcache.mod")).read() == "+ bgcache %s bgcache\n" % version
import bgcache
assert os.path.dirname(bgcache.__file__) == os.path.join(target, "scripts", "bgcache"), bgcache.__file__
assert len(buttons) == 1 and buttons["btn1"]["tab"] == "Animation" and "bgcache.controller" in buttons["btn1"]["command"]
assert not dialogs
print("ok: installs into Maya's own user folder (any drive): modules/bgcache + bgcache.mod, usable at once, one shelf button")

# ---- update: old copy kept, still one button, a studio profile.json carried over
open(os.path.join(target, "scripts", "bgcache", "profile.json"), "w").write('{"shot_folder": "/studio/{shot}"}')
stale = os.path.join(user, "2027", "scripts", "bgcache"); os.makedirs(stale)
open(os.path.join(stale, "controller.py"), "w").close(); open(os.path.join(stale, "__init__.py"), "w").write('__version__ = "0.7.5"\n')
inst = load_installer(staged(full=True))
report = inst.install(quiet=True)
backups = os.listdir(os.path.join(modules, ".bgcache_backups"))
assert len(backups) == 1 and backups[0].startswith("bgcache_%s_" % version)
assert open(os.path.join(target, "scripts", "bgcache", "profile.json")).read() == '{"shot_folder": "/studio/{shot}"}'
assert not os.path.exists(stale) and os.listdir(os.path.join(user, "2027", "scripts", ".bgcache_backups"))[0].startswith("bgcache_0.7.5_")
assert len(buttons) == 1
assert "kept" in report and "would hide the new one" in report
print("ok: update keeps the old copy for rollback, keeps a studio profile.json, moves an old scripts/bgcache aside, no second button")

# ---- with dialogs: an existing install asks Update / Uninstall / Cancel
dialogs[:] = []
cmds.confirmDialog = lambda **k: (dialogs.append(k), "Cancel")[1]
assert inst.install() == "cancelled" and dialogs[0]["button"] == ["Update", "Uninstall", "Cancel"]
cmds.confirmDialog = confirmDialog
print("ok: dropped on an existing install it asks Update / Uninstall / Cancel; Cancel changes nothing")

# ---- refuses while bgcache is running in this Maya
running = types.SimpleNamespace(running=True)
fake_controller = types.ModuleType("bgcache.controller"); fake_controller.get = lambda: running
sys.modules["bgcache.controller"] = fake_controller
msg = inst.install(quiet=True)
assert "press Stop first" in msg and len(os.listdir(os.path.join(modules, ".bgcache_backups"))) == 1
assert "press Stop first" in inst.uninstall(quiet=True) and os.path.isdir(target)
running.running = False
print("ok: won't update while bgcache is running (Stop first)")

# ---- dropping the file again runs it afresh (Maya 2022+ caches dropped modules)
sys.modules["install_bgcache"] = inst
inst._forget_self()
assert "install_bgcache" not in sys.modules
print("ok: the installer forgets its cached copy, so a second drop runs the new file")

# ---- uninstall
report = inst.uninstall(quiet=True)
assert not os.path.exists(target) and not os.path.exists(os.path.join(modules, "bgcache.mod")) and not buttons
assert os.path.isdir(os.path.join(modules, ".bgcache_backups"))
assert not any(m == "bgcache" or m.startswith("bgcache.") for m in sys.modules)
print("ok: uninstall removes the module, the .mod file and the shelf button; backups stay")

# ---- the release zips
out = tempfile.mkdtemp()
made = build_release.build(out)
assert len(made) == 6
for path in made:
    names = zipfile.ZipFile(path).namelist()
    top = os.path.basename(path)[:-4]
    assert top + "/install_bgcache.py" in names and top + "/README.txt" in names
    assert top + "/module/scripts/bgcache/system/windows.py" in names and top + "/module/scripts/bgcache/system/macos.py" in names
    assert not any("studio_private" in n or n.endswith("profile.json") or "__pycache__" in n for n in names)
    has_cont = any("/scripts/bgcache/continuity/" in n for n in names)
    assert has_cont == path.endswith("-full.zip"), path
print("ok: 6 downloads (windows/macos/linux x simple/full); Simple has no continuity/, none has a profile.json or studio files")
