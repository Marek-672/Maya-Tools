import os, sys
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time, tempfile, shutil
APP_DIR_BEFORE = os.environ.get("MAYA_APP_DIR")      # yours, if your system sets it
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from unittest import mock
home = tempfile.mkdtemp()
os.environ["BGCACHE_LOGS"] = os.path.join(home, ".bgcache", "logs")
from bgcache import common, controller as C
C.scene.BG_APP_DIR = os.path.join(home, ".bgcache", "maya_clean")
C.scene.OLD_BG_APP_DIR = os.path.join(home, ".bgcache", "maya_app")

# a user's real Maya prefs, with a layout and a personal shelf
user = os.path.join(home, "maya", "2024")
prefs = os.path.join(user, "prefs")
for d in ("shelves", "workspaces", "icons"):
    os.makedirs(os.path.join(prefs, d))
for f, body in (("userPrefs.mel", "// units, evaluation, viewport"), ("pluginPrefs.mel", "// autoload list"),
                ("windowPrefs.mel", "// MY layout"), ("shelves/shelf_Mine.mel", "// MY shelf"),
                ("workspaces/MyLayout.json", "{}")):
    open(os.path.join(prefs, f), "w").write(body)
for d in ("scripts", "modules", "plug-ins"):
    os.makedirs(os.path.join(user, d))
before = {f: open(os.path.join(prefs, f)).read() for f in ("userPrefs.mel", "windowPrefs.mel", "shelves/shelf_Mine.mel")}
C.cmds.internalVar = lambda **k: prefs + "/"

# 0.9.0b19: the background Maya starts from Maya's own defaults, plus the few of your settings that decide the picture
mine = {"vp2RenderingEngine": "OpenGLCoreProfileCompat", "colorManagementPolicyFileName": 'C:\\ocio\\a "b".xml',
        "vp2SomeNumber": 3, "vp2SomeList": ["a", "b"], "workspaceLayoutToLoadOnStartup": "MyLayout"}
C.cmds.optionVar = lambda list=False, query=None, **k: sorted(mine) if list else mine[query]
app, vdir = C.background_prefs()
bg = os.path.join(app, "2024", "prefs")
made = open(os.path.join(bg, "userPrefs.mel")).read()
assert 'optionVar -sv "vp2RenderingEngine" "OpenGLCoreProfileCompat";' in made and 'optionVar -iv "vp2SomeNumber" 3;' in made
assert 'C:\\\\ocio\\\\a \\"b\\".xml' in made and "vp2SomeList" not in made and "workspaceLayout" not in made
assert 'optionVar -iv "useScenePanelConfig" 0;' in made and "// units, evaluation, viewport" not in made
assert sorted(os.listdir(bg)) == ["userPrefs.mel"] and vdir == user
setup = open(os.path.join(app, "2024", "scripts", "userSetup.py")).read()
assert "BGCACHE_BACKGROUND" in setup and "setWindowOpacity(0.0)" in setup and "showMinimized" in setup and "import maya" not in setup
print("ok: background Maya gets its own, clean settings: Maya's defaults plus your graphics and colour settings; "
      "none of your layouts, panel layouts, shelves or other prefs; and a start-up script that keeps its window down")
# the background Maya's environment: its own prefs, your scripts/modules/plug-ins still found, no prompts
c = C.Controller(); c.session = common.new_session()
c.cfg = {"bg_app_dir": app, "user_maya_dir": user, "skip_in_background": []}
env = c._worker_env()
assert env["MAYA_APP_DIR"] == app
assert os.path.join(user, "scripts") in env["PYTHONPATH"] and os.path.join(user, "scripts") in env["MAYA_SCRIPT_PATH"]
assert os.path.join(user, "modules") in env["MAYA_MODULE_PATH"] and os.path.join(user, "plug-ins") in env["MAYA_PLUG_IN_PATH"]
assert env["MAYA_DISABLE_CIP"] == env["MAYA_NO_HOME"] == "1" and os.environ.get("MAYA_APP_DIR") == APP_DIR_BEFORE
print("ok: background env: MAYA_APP_DIR is its own; your scripts, modules, plug-ins still on its paths; no first-run prompts")

# the background Maya writing to ITS prefs can't touch yours
open(os.path.join(bg, "windowPrefs.mel"), "w").write("// background single-view layout")
os.makedirs(os.path.join(bg, "shelves")); open(os.path.join(bg, "shelves", "shelf_Custom.mel"), "w").write("x")
assert {f: open(os.path.join(prefs, f)).read() for f in before} == before
print("ok: whatever the background Maya saves lands in its own folder; your layout and shelf untouched")

# written again at every Start, so a changed setting of yours is picked up; refresh starts from nothing
mine["vp2RenderingEngine"] = "DirectX11"
C.background_prefs()
assert '"vp2RenderingEngine" "DirectX11"' in open(os.path.join(bg, "userPrefs.mel")).read() and os.path.isdir(os.path.join(bg, "shelves"))
C.background_prefs(refresh=True)
assert not os.path.exists(os.path.join(bg, "shelves")) and not os.path.exists(os.path.join(bg, "windowPrefs.mel"))
print("ok: your picture settings are carried at every Start; refresh_background_prefs=True empties its folder first")
# the old way, for a studio that needs it: a copy of your prefs without the layouts
C.scene.profile.use({"background_prefs": "copy"})
app_old, _v = C.background_prefs()
old = os.path.join(app_old, "2024", "prefs")
assert app_old != app and os.path.isfile(os.path.join(old, "pluginPrefs.mel")) and not os.path.exists(os.path.join(old, "workspaces"))
C.scene.profile.use(None)
print('ok: "background_prefs": "copy" in the profile keeps the old way (a copy of yours, no layouts)')

# if separate prefs can't be made, Start stops rather than sharing yours
src = _source.source("controller")
blk = src[src.index("self.cfg[\"bg_app_dir\"], self.cfg[\"user_maya_dir\"] = scene.background_prefs"):][:500]
assert "_abort(" in blk and "return" in blk
a, b = common.new_session(), common.new_session()
assert a != b
print("ok: no separate prefs -> Start stops (never shares yours); two Starts in one second get different sessions")
