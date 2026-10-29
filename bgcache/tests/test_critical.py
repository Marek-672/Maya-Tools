import os, sys
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time, tempfile, shutil
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from unittest import mock
home = tempfile.mkdtemp()
os.environ["BGCACHE_LOGS"] = os.path.join(home, ".bgcache", "logs")
from bgcache import common, controller as C
C.scene.BG_APP_DIR = os.path.join(home, ".bgcache", "maya_app")

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

app, vdir = C.background_prefs()
bg = os.path.join(app, "2024", "prefs")
assert os.path.isfile(os.path.join(bg, "userPrefs.mel")) and os.path.isfile(os.path.join(bg, "pluginPrefs.mel"))
assert not os.path.exists(os.path.join(bg, "windowPrefs.mel")) and not os.path.exists(os.path.join(bg, "shelves"))
assert not os.path.exists(os.path.join(bg, "workspaces")) and vdir == user
print("ok: background Maya gets its own prefs folder, seeded from yours WITHOUT your layout, panel layouts or shelves")

# the background Maya's environment: its own prefs, your scripts/modules/plug-ins still found, no prompts
c = C.Controller(); c.session = common.new_session()
c.cfg = {"bg_app_dir": app, "user_maya_dir": user, "skip_in_background": []}
env = c._worker_env()
assert env["MAYA_APP_DIR"] == app
assert os.path.join(user, "scripts") in env["PYTHONPATH"] and os.path.join(user, "scripts") in env["MAYA_SCRIPT_PATH"]
assert os.path.join(user, "modules") in env["MAYA_MODULE_PATH"] and os.path.join(user, "plug-ins") in env["MAYA_PLUG_IN_PATH"]
assert env["MAYA_DISABLE_CIP"] == env["MAYA_NO_HOME"] == "1" and "MAYA_APP_DIR" not in os.environ
print("ok: background env: MAYA_APP_DIR is its own; your scripts, modules, plug-ins still on its paths; no first-run prompts")

# the background Maya writing to ITS prefs can't touch yours
open(os.path.join(bg, "windowPrefs.mel"), "w").write("// background single-view layout")
os.makedirs(os.path.join(bg, "shelves")); open(os.path.join(bg, "shelves", "shelf_Custom.mel"), "w").write("x")
assert {f: open(os.path.join(prefs, f)).read() for f in before} == before
print("ok: whatever the background Maya saves lands in its own folder; your layout and shelf untouched")

# refresh re-copies from yours
open(os.path.join(prefs, "userPrefs.mel"), "w").write("// changed viewport setting")
C.background_prefs(refresh=True)
assert open(os.path.join(bg, "userPrefs.mel")).read() == "// changed viewport setting" and not os.path.exists(os.path.join(bg, "windowPrefs.mel"))
print("ok: show_ui(refresh_background_prefs=True) re-copies your current prefs")

# if separate prefs can't be made, Start stops rather than sharing yours
src = _source.source("controller")
blk = src[src.index("self.cfg[\"bg_app_dir\"], self.cfg[\"user_maya_dir\"] = scene.background_prefs"):][:500]
assert "_abort(" in blk and "return" in blk
a, b = common.new_session(), common.new_session()
assert a != b
print("ok: no separate prefs -> Start stops (never shares yours); two Starts in one second get different sessions")
