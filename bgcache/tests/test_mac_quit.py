"""0.8.0b11, from the Mac test: Stop (and quitting your Maya) left the hidden
Maya waiting on "Save changes?" (its scene copy has your edits; on the Mac Maya
asks even with quit -force). It now marks its scene unchanged first. Also: it
checks it really uses its own preferences folder, and closes at once,
without saving, if the system gave it yours."""
import _source  # noqa: E402 (tests/_source.py)
import os, sys, json, time, types
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w`, session, paths `p`

seq = []
cmds.file = lambda *a, **k: seq.append(("file", k)) if "modified" in k else None
cmds.quit = lambda **k: seq.append(("quit", k))
os._exit = lambda code: seq.append(("exit", code))       # b8: it ends at once (Maya's own quit crashed at a studio)
w._quit()
assert seq == [("file", {"modified": False}), ("exit", 0)], seq
print("ok: quitting marks the scene unchanged first (no 'Save changes?'), then ends at once: "
      "no UI tear-down to crash in (b8)")

# its own prefs folder: fine
own = os.path.join(os.path.expanduser("~"), ".bgcache", "maya_app", "2025", "prefs")
yours = os.path.join(os.path.expanduser("~"), "Library", "Preferences", "Autodesk", "maya", "2025")
w.cfg["user_maya_dir"] = yours
cmds.internalVar = lambda userPrefDir=False, **k: own + "/"
seq[:] = []
assert w._own_prefs_ok() is True and not seq
assert any(m.startswith("preferences folder: ") for m in LOG)
print("ok: the background Maya logs its preferences folder (its own: carries on)")

# the system ignored MAYA_APP_DIR: it would use (and save over) yours
cmds.internalVar = lambda userPrefDir=False, **k: os.path.join(yours, "prefs") + "/"
assert w._own_prefs_ok() is False
assert [s[0] for s in seq] == ["file", "exit"]
st = json.load(open(p["status"]))
assert st["state"].startswith("error: the background Maya couldn't get its own preferences")
print("ok: using YOUR preferences folder: it closes at once without saving, and says why")

wsrc = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert "def _minimize_again" in wsrc and "singleShot(ms, self._minimize_again)" in wsrc
assert "main window minimized: " in wsrc
print("ok: the main window is minimised again once Maya has opened, and the log says if it worked (Mac)")
psrc = _source.source("player")
assert "_name_and_icon(app)" in psrc and "bgcache_200.png" in psrc and 'setApplicationName("bgcache")' in psrc
print("ok: the player is called bgcache and has its icon (the Mac Dock showed 'mayapy')")
