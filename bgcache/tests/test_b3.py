"""0.9.0b3: drawings saved on Save (player side), Help > Report a problem,
footage with the version in the file name and .mp4, a list of releases
folders."""
import base64
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)

tmp = os.path.realpath(tempfile.mkdtemp())
os.environ["BGCACHE_LOGS"] = os.path.join(tmp, "logs")

from bgcache import common, profile, report, update   # noqa: E402

# ---- player: Ctrl+S, the unsaved dot, ask before Stop / closing
p = open(os.path.join(REPO, "bgcache", "player.py")).read()
keys = p.split("def keyPressEvent")[1].split("def keyReleaseEvent")[0]
assert "if ctrl and key == Qt.Key_S and not shift:" in keys and "self.drawer.save_now()" in keys
assert 'dot = " ●" if mine is not None and mine.dirty else ""' in p
stop = p.split("def stop_bgcache")[1].split("def ")[0]
assert 'self.drawer.ask_to_save(self, "stopping bgcache")' in stop
close = p.split("def closeEvent")[1].split("def ")[0]
assert 'self.drawer.ask_to_save(self, "closing the player")' in close
print("ok: Ctrl+S saves drawings; DRAW tag shows a dot while unsaved; Stop and closing ask Save / Don't save / Cancel")

# ---- Report a problem
assert profile.DEFAULT["reports_url"] == "" and profile.DEFAULT["reports_folder"] == ""
c = open(os.path.join(REPO, "bgcache", "controller.py")).read()
assert '"reports_url": profile.get("reports_url") or ""' in c
assert 'help_menu.addAction("Report a problem...", self.report_problem)' in p
assert "if can_send:" in p and 'QPushButton("Save report...")' in p
print("ok: Help > Report a problem; Send only when the profile has reports_url (empty by default)")

session = "sess1"
logs = common.log_dir(session)
os.makedirs(logs, exist_ok=True)
open(os.path.join(logs, "worker.log"), "w", newline="").write("opened /shows/BIRDS/sq010_0040/anim/walk_v012.mb as artist7\n")
open(os.path.join(logs, "player.log"), "w", newline="").write("x" * (report.MAX_LOG_BYTES + 5000) + "\nlast line\n")
cfg = {"original_scene": "/shows/BIRDS/sq010_0040/anim/walk_v012.mb", "user": "artist7",
       "session": session, "profile": "test"}
items = report.gather(session, cfg, "0.9.0b3", "simple")
names = [n for n, _p, _t in items]
assert names[0] == "about.txt" and "worker.log" in names and "player.log" in names and "trace.log" not in names
plog = dict((n, t) for n, _p, t in items)["player.log"]
assert plog.startswith("[... the first") and plog.endswith("last line\n") and len(plog) <= report.MAX_LOG_BYTES + 100
print("ok: the report gathers about, the session's logs (the end of a long log), self-test, settings")

hidden = report.names_to_hide(cfg)
assert hidden["walk_v012"] == "SCENE" and hidden["walk"] == "SCENE" and hidden["artist7"] == "USER"
data = report.build(items, "it froze on Refresh", "me@example.com", hidden)
z = zipfile.ZipFile(io.BytesIO(data))
assert "it froze on Refresh" in z.read("what_happened.txt").decode() and "me@example.com" in z.read("what_happened.txt").decode()
w = z.read("worker.log").decode()
assert "walk" not in w and "artist7" not in w and "SCENE" in w and "USER" in w
plain = zipfile.ZipFile(io.BytesIO(report.build(items, "", "", None))).read("worker.log").decode()
assert "walk_v012" in plain
print("ok: Hide names swaps scene and user names (and show / sequence / shot from the profile) in every file")

out = report.save(data, os.path.join(tmp, "reports", report.file_name("0.9.0b3")))
assert os.path.exists(out) and out.endswith(".zip")

import urllib.request                                   # noqa: E402
sent = {}


class _Answer(object):
    def __init__(self, text):
        self.text = text

    def read(self):
        return self.text.encode()


def fake_urlopen(request, timeout=0):
    sent["body"] = json.loads(request.data.decode())
    return _Answer(json.dumps({"ok": True, "id": "abc"}))


real = urllib.request.urlopen
urllib.request.urlopen = fake_urlopen
ok, message = report.send("https://script.example/exec", data, "r.zip", "0.9.0b3")
assert ok and base64.b64decode(sent["body"]["zip"]) == data and sent["body"]["version"] == "0.9.0b3"


def no_network(request, timeout=0):
    raise OSError("no route")


urllib.request.urlopen = no_network
ok, message = report.send("https://script.example/exec", data, "r.zip", "0.9.0b3")
assert not ok and "no route" in message
urllib.request.urlopen = real
print("ok: Send posts the zip to the reports address; no network is a message, never an error box")

# ---- continuity: versions in file names, .mp4
from bgcache.continuity import resolver as cr           # noqa: E402
base = os.path.join(tmp, "anim")
os.makedirs(base)
for name in ("sq010_0040_anim_v003.mov", "sq010_0040_anim_v004.mp4", "sq010_0040_anim_v004.txt", "other_v009.mov"):
    open(os.path.join(base, name), "w").close()
assert [v for v, _ in cr._version_folders(base, "sq010_0040_anim_v*", "single_movie")] == [3, 4]
assert cr._version_folders(base, "sq010_0040_anim_v*", "single_movie")[-1][1].endswith("v004.mp4")
assert cr._find_single_movie(os.path.join(base, "sq010_0040_anim_v004.mp4")).endswith(".mp4")
os.makedirs(os.path.join(base, "sq010_0040_anim_v004"))
open(os.path.join(base, "sq010_0040_anim_v004", "take.mp4"), "w").close()
assert cr._version_folders(base, "sq010_0040_anim_v*", "single_movie")[-1][1].endswith("anim_v004")
print("ok: versions in movie file names side by side (shot_v004.mp4); a version folder wins; .mp4 found in folders")

seq = os.path.join(tmp, "light")
os.makedirs(seq)
for v, frames in ((2, (1001, 1002)), (5, (1001, 1002, 1003))):
    for f in frames:
        open(os.path.join(seq, "sq010_0040_light_v%03d.%d.jpg" % (v, f)), "w").close()
found = cr._version_folders(seq, "sq010_0040_light_v*", "image_sequence")
assert [v for v, _ in found] == [2, 5] and found[-1][1].endswith("v005.1001.jpg")
first, count, start = cr._sequence_from_file(found[-1][1])
assert count == 3 and start == 1001
assert cr._version_folders(seq, "sq010_0040_light_v*", "sound") == []
print("ok: image sequences with the version in the name (shot_v005.1001.jpg), counted per version; sound looks at folders only")

# ---- releases folder: a list
home = os.path.join(tmp, "home_releases")
old = os.path.join(tmp, "old_releases")
os.makedirs(os.path.join(home, "releases"))
os.makedirs(old)
open(os.path.join(home, "releases", "bgcache_0.9.0b3.zip"), "w").close()
open(os.path.join(old, "bgcache_0.9.0b3.zip"), "w").close()
open(os.path.join(old, "bgcache_0.9.0b2.zip"), "w").close()
found = update.releases([home, old])
assert found["0.9.0b3"].startswith(home) and found["0.9.0b2"].startswith(old)
assert update.check_folder([os.path.join(tmp, "gone"), home], "0.9.0b2")["state"] == "newer"
assert update.check_folder([os.path.join(tmp, "gone")], "0.9.0b2")["state"] == "error"
assert update.check_folder(home, "0.9.0b3")["state"] == "latest"
print("ok: releases_folder can be a list, first folder first; a missing folder is skipped")

shutil.rmtree(tmp, ignore_errors=True)
