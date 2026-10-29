import os, sys
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time, tempfile
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from unittest import mock
os.environ["BGCACHE_LOGS"] = tempfile.mkdtemp()
from bgcache import common, controller as C
C.QtCore.QTimer.singleShot = staticmethod(lambda ms, fn: None)
added = []
om.MSceneMessage = types.SimpleNamespace(kBeforeOpen=1, kBeforeNew=2, kMayaExiting=3, kBeforeSave=4,
                                         addCallback=lambda kind, fn: added.append((kind, fn)) or ("scene", kind))
removed, deferred = [], []
om.MMessage = types.SimpleNamespace(removeCallback=lambda cb: removed.append(cb))
oma.MAnimMessage = types.SimpleNamespace(addAnimCurveEditedCallback=lambda fn: "anim")
om.MDGMessage = types.SimpleNamespace(addNodeAddedCallback=lambda fn, t: "added", addNodeRemovedCallback=lambda fn, t: "removed")
cmds.scriptJob = lambda **k: 1
cmds.evalDeferred = lambda fn, **k: deferred.append(fn)
c = C.Controller(); c.session = common.new_session(); c.cfg = {"trace": True, "start": 1001, "end": 1010}
c._install_callbacks()
kinds = [k for k, fn in added]
assert kinds == [1, 2, 3]
print("ok: listens for File > Open, File > New and Maya quitting")

# File > Open on another shot: bgcache stops BEFORE the old scene is torn down
with mock.patch.object(c, "remove_image_plane", lambda: None), mock.patch.object(c, "_set_label", lambda *a, **k: None), \
     mock.patch.object(c, "_update_buttons", lambda: None):
    session = c.session
    open_cb = [fn for k, fn in added if k == 1][0]
    open_cb(None)
assert c.session is None and not c.running
assert common.take_messages(session)[-1]["op"] == "quit"
assert ("scene", 1) not in removed and deferred           # its own callback removed a moment later
deferred[-1](); assert ("scene", 1) in removed
print("ok: opening another shot stops bgcache first; its own callback is removed afterwards, not from inside itself")

# the flood of curve events while the old scene is torn down: all ignored
c.pending = set(); c.pending_handles = []; c.removed = []
for _ in range(5000):
    c._on_curve_removed(object()); c._on_curve_added(object())
c._on_curves_edited([object()] * 10); c._on_selection()
assert not c.pending and not c.pending_handles and not c.removed
print("ok: 10,000 curve deletions/creations during the file change are ignored")

# trace stays small during busy moments
c2 = C.Controller(); c2.session = common.new_session(); c2.cfg = {"trace": True}
for _ in range(3000):
    c2.trace("curve-removed")
lines = open(common.paths(c2.session)["trace"]).read().splitlines()
assert len(lines) <= 2, len(lines)
print("ok: 3,000 busy events -> %d trace line(s)" % len(lines))

# forced end after Stop is a silent kill (no crash file, nothing saved)
src = _source.source("controller")
assert "worker.kill()" in src and "worker.terminate()" not in src
print("ok: a background Maya still loading after Stop is ended silently (kill, not terminate)")
