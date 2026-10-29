import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import types, time, tempfile
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from unittest import mock
from bgcache import common, controller as C

# --- Stop frees the temp space once the background Maya is gone; logs kept
timers = []
C.QtCore.QTimer.singleShot = staticmethod(lambda ms, fn: timers.append(fn))
c = C.Controller(); c.session = common.new_session(); c.cfg = {"trace": True}
session = c.session
open(os.path.join(session, "scene_copy.mb"), "w").write("x" * 1000)
open(os.path.join(session, "frames", "f.1001.jpg"), "w").write("x")
logs = common.paths(session)["logs"]
c.trace("something")
class Proc:
    killed = False
    def poll(s): return None if not s.killed else -9
    def kill(s): s.killed = True
    def wait(s, t): pass
c.worker_proc = Proc()
with mock.patch.object(c, "remove_image_plane", lambda: None), mock.patch.object(c, "_set_label", lambda *a, **k: None), \
     mock.patch.object(c, "_update_buttons", lambda: None):
    c.stop()
assert os.path.isdir(session)                  # not yet: the background Maya may still be closing
timers[-1]()                                   # 20 s later
assert not os.path.exists(session) and c.worker_proc.killed and os.path.isfile(os.path.join(logs, "trace.log"))
print("ok: Stop removes the session's scene copies and frames once the background Maya has gone; logs kept")

# --- leftovers from crashes are swept at the next Start, unless that Maya is still running
dead = common.new_session(); common.write_json_atomic(common.paths(dead)["config"], {"controller_pid": 999999})
alive = common.new_session(); common.write_json_atomic(common.paths(alive)["config"], {"controller_pid": os.getpid()})
current = common.new_session()
assert common.prune_sessions(keep=current) == 1
assert not os.path.exists(dead) and os.path.isdir(alive) and os.path.isdir(current)
print("ok: leftover sessions swept at Start; ones a running Maya still uses are kept")
# remove_session refuses anything outside bgcache's own folder
outside = tempfile.mkdtemp(); common.remove_session(outside); assert os.path.isdir(outside)
print("ok: clean-up only ever deletes inside bgcache's own temp folder")

# --- Reload keeps only the newest two scene copies
c.session = common.new_session()
for i, name in enumerate(["scene_copy.mb", "scene_copy_2.mb", "scene_copy_3.mb", "scene_copy_4.mb"]):
    path = os.path.join(c.session, name); open(path, "w").write("x"); os.utime(path, (i, i))
c._prune_scene_copies(keep=2)
assert sorted(os.listdir(c.session)) == sorted(["inbox", "frames", "tmp", "scene_copy_3.mb", "scene_copy_4.mb"])
print("ok: Reload scene keeps only the newest two scene copies")

# --- ignored errors are noted in trace.log, condensed per place
C._controller = c; c.cfg = {"trace": True}
def somewhere():
    for _ in range(50):
        try:
            raise ValueError("bad plug")
        except Exception as error:
            C._ignored(error)
somewhere()
lines = [l for l in open(common.paths(c.session)["trace"]).read().splitlines() if "ignored" in l]
assert len(lines) == 1 and "ignored:somewhere" in lines[0] and "ValueError: bad plug" in lines[0]
print("ok: ignored errors are noted (50 in a row -> 1 line):", lines[0].split(" ", 1)[1])

# --- one-off options apply to the next Start only
C._start_kwargs = {"refresh_background_prefs": True, "light_background": False}
starts = []
with mock.patch.object(C, "get", lambda: types.SimpleNamespace(start=lambda **k: starts.append(dict(k)))):
    C._start_clicked(); C._start_clicked()
assert starts[0]["refresh_background_prefs"] is True and "refresh_background_prefs" not in starts[1]
assert starts[1]["light_background"] is False
print("ok: refresh_background_prefs applies once; settings like light_background stay")
