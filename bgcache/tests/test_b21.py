"""0.8.0b21 clean-up: the controller split into topic files, no function over
80 lines, every "catch any error and carry on" says why or reports it, and
the old names still work (bgcache.controller.list_cameras etc.)."""
import ast
import glob
import os
import re
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
PKG = os.path.join(REPO, "bgcache")
FILES = sorted(glob.glob(os.path.join(PKG, "**", "*.py"), recursive=True))

# ---- the split
for name in ("scene", "controller_edits", "controller_refresh", "controller_gpu", "controller_sync",
             "controller_refplane"):
    assert os.path.isfile(os.path.join(PKG, name + ".py")), name
c = open(os.path.join(PKG, "controller.py")).read()
assert "class Controller(RefreshMixin, GpuRescueMixin, EditsMixin, SyncMixin, RefPlaneMixin):" in c
assert "from bgcache.scene import *" in c
assert len(c.splitlines()) < 1000, len(c.splitlines())
print("ok: controller.py is the Controller's start/launch/stop/status and the shelf; the rest is in topic files")

# ---- no long functions
long_ones = []
for path in FILES:
    for node in ast.walk(ast.parse(open(path).read())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno - node.lineno + 1 > 80:
            long_ones.append("%s %s (%d lines)" % (os.path.relpath(path, REPO), node.name,
                                                   node.end_lineno - node.lineno + 1))
assert not long_ones, long_ones
print("ok: no function over 80 lines")

# ---- no silent "catch anything" (each one logs, reports, re-raises or says why)
REPORTS = re.compile(r"\b(log|print|_ignored|warning|displayWarning|displayError|trace|write|append|"
                     r"format_exc|_flash|_flash_message|_set_label|_tell_player|raise)\b")
silent = []
for path in FILES:
    lines = open(path).read().splitlines()
    for node in ast.walk(ast.parse("\n".join(lines))):
        if not isinstance(node, ast.ExceptHandler):
            continue
        broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"))
        if not broad:
            continue
        text = "\n".join(lines[node.lineno - 1:node.body[-1].end_lineno])
        if "#" in text or REPORTS.search("\n".join(lines[node.body[0].lineno - 1:node.body[-1].end_lineno])):
            continue
        silent.append("%s:%d" % (os.path.relpath(path, REPO), node.lineno))
assert not silent, silent
print("ok: every 'catch any error' logs it, shows it, re-raises it or has a one-line reason")

# ---- old names still work, and the split files point at the same functions
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from bgcache import controller, scene                     # noqa: E402
for name in ("list_cameras", "viewport_display", "viewport_renderer", "image_planes", "gpu_override_on",
             "curve_definition", "path_curves", "find_audio", "REF_PLANE", "DISPLAY_FLAGS", "_shot_camera_panel",
             "_ignored", "_mouse_held"):
    assert getattr(controller, name) is getattr(scene, name), name
for name in ("get", "unload", "shelf_click", "shelf_stop", "shelf_reopen", "shelf_restart", "shelf_selftest",
             "show_ui", "_build_ui", "check_undo"):
    assert callable(getattr(controller, name)), name
ctl = controller.Controller()
for method in ("start", "stop", "flush", "refresh_display", "reload_scene", "restart_on_cpu", "show_image_plane",
               "push_selected", "_poll_player_time", "_install_callbacks", "_send_path_curves"):
    assert callable(getattr(ctl, method, None)), method
assert controller.Controller.GPU_STUCK_S == 10.0
print("ok: old names still work (bgcache.controller.list_cameras, REF_PLANE, shelf_click...) "
      "and the Controller has all its methods")

# ---- scene.py finds the running Controller without importing controller.py
assert scene._current() is None
controller._controller = ctl
assert scene._current() is ctl
controller._controller = None
print("ok: scene.py looks up the running Controller only when it needs it (no import loop)")

dev = open(os.path.join(PKG, "DEVELOPER.md")).read()
for name in ("controller_edits.py", "scene.py", "worker.py", "player.py", "tests/run_tests.py", "build_studio.py"):
    assert name in dev, name
print("ok: DEVELOPER.md maps the code, the tests and the build scripts")
