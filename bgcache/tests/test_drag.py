"""0.6.10: while a mouse button is held (dragging keys), edits wait; they're
sent once, just after you let go."""
import os, sys, types, time
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])   # Maya/Qt stubs
sys.path.insert(0, REPO)
from bgcache import common, controller
c = controller.Controller()
c.session = common.new_session()   # running = has a session
c.cfg = {"start": 1, "end": 10}
starts = []
c.flush_timer = types.SimpleNamespace(start=lambda ms: starts.append(ms), stop=lambda: None)
held = {"on": True}
controller.scene._mouse_held = lambda: held["on"]
sent = []
c.trace = lambda *a: sent.append(a[0])
c.pending = {"curve1"}
c._schedule()
c.flush()
assert starts[-1] == controller.HELD_POLL_MS and c.pending == {"curve1"} and "flush" not in sent
print("ok: mouse held -> nothing sent, checks again in %d ms" % controller.HELD_POLL_MS)
c._held_since -= controller.HELD_MAX_S + 1
held["on"] = True
c.pending = set()
c.flush()
assert "flush" in sent
print("ok: held for more than %.0f s -> sent anyway" % controller.HELD_MAX_S)
sent.clear(); c._schedule(); c.flush()                       # held again, then released
held["on"] = False
before = time.time(); c.flush()
assert "flush" in sent and c._last_edit_t >= before and c._held_since is None
print("ok: released -> sent at once, timed from the release")
