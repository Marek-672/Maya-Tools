import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time, tempfile
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
home = tempfile.mkdtemp(); os.environ["BGCACHE_LOGS"] = os.path.join(home, ".bgcache", "logs")
sys.path.insert(0, REPO)
from bgcache import common, controller as C
# logs live outside the temp session folder
s1 = common.new_session(); p = common.paths(s1)
assert p["logs"].startswith(os.environ["BGCACHE_LOGS"]) and os.path.isdir(p["logs"])
assert not p["log"].startswith(common.ROOT)
print("ok: logs go to", os.path.dirname(p["logs"]), "(survives temp clean-up)")
# pruning keeps the newest 15
for i in range(20):
    d = os.path.join(os.environ["BGCACHE_LOGS"], "old_%02d" % i); os.makedirs(d); os.utime(d, (i, i))
common._prune_logs()
left = os.listdir(os.environ["BGCACHE_LOGS"])
assert len(left) == 15 and os.path.basename(p["logs"]) in left
print("ok: only the newest 15 sessions' logs are kept")
# trace in your Maya: one flushed line per event; time changes at most once a second
c = C.Controller(); c.session = s1; c.cfg = {"trace": True}
c.trace("selection"); c.trace("curve-edited", 3); c.trace("time"); c.trace("time"); c.trace("flush", "3 curves pending")
lines = open(p["trace"]).read().splitlines()
assert [l.split(" ", 1)[1] for l in lines] == ["selection ", "curve-edited 3", "time ", "flush 3 curves pending"], lines
print("ok: trace.log:", " | ".join(lines))
c.cfg["trace"] = False; c.trace("selection"); assert len(open(p["trace"]).read().splitlines()) == 4
print("ok: show_ui(trace=False) turns it off")
