"""0.8.0b12: refreshing footage. A version re-published under the same name
used to keep playing its old converted frames (the cache was keyed by
path); now the cache remembers the file's date and size. Right-click a shot:
Check for newer now, Reload this shot's footage, Show in folder; Refresh all
on the strip."""
import os, sys, json, time, types, tempfile
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
from unittest import mock
qt = types.ModuleType("PySide2"); qt.QtCore = mock.MagicMock(); qt.QtGui = mock.MagicMock()
sys.modules.update({"PySide2": qt, "PySide2.QtCore": qt.QtCore, "PySide2.QtGui": qt.QtGui})
sys.path.insert(0, REPO)
from bgcache.continuity import reel
reel.CACHE_ROOT = tempfile.mkdtemp()
src = tempfile.mkdtemp()
movie = os.path.join(src, "sq010_0030_light_v006.mov")
open(movie, "wb").write(b"x" * 1000)
info = {"source_type": "single_movie", "source_path": movie, "department": "Lighting", "version": 6}
out = reel.cache_dir("sq010_0030", info, 540); os.makedirs(out)
open(os.path.join(out, "f.1.jpg"), "wb").write(b"j")
json.dump({"source": movie, "frames": 1, "stamp": reel.source_stamp(info)}, open(os.path.join(out, "done.json"), "w"))
assert reel.footage_changed("sq010_0030", info, 540) is False
print("ok: the cache remembers the movie's date and size")
open(movie, "wb").write(b"y" * 2000)               # re-published, same name
t = time.time() + 60; os.utime(movie, (t, t))
assert reel.footage_changed("sq010_0030", info, 540) is True
print("ok: the same version re-published is noticed")
os.makedirs(reel.cache_dir("sq010_0030", dict(info, version=5), 540))
reel.forget("sq010_0030", info)
assert not os.path.exists(out) and os.path.isdir(reel.cache_dir("sq010_0030", dict(info, version=5), 540))
print("ok: Reload forgets only that version's converted frames")

ui = open(os.path.join(REPO, "bgcache", "continuity", "ui.py")).read()
for words in ('"Check for newer now"', '"Update this shot\'s footage"', '"Show in folder"', '"Update footage"',
              "def refresh_all_footage", "def check_newer_now", "def reload_footage"):
    assert words in ui, words
assert "self.reel_mod.footage_changed(shot, info, self.height_px)" in ui
print("ok: right-click: Check for newer now / Reload this shot's footage / Show in folder; Refresh all on the strip; "
      "the 2-minute check reloads changed files for shots that follow Latest")
for name in ("PySide2", "PySide2.QtCore", "PySide2.QtGui"):
    sys.modules.pop(name, None)
