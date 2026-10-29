"""0.6.10: edits update the curve's keys in place, never leaving it empty;
full rebuild only as a fallback."""
import os, sys, types
TESTS = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(TESTS, "test_display.py")).read().split("from bgcache import worker")[0])
from bgcache import worker
logs = []
worker.log = lambda m: logs.append(m)

class MTime(object):
    def __init__(s, t, unit=None): s.t = float(t)
    def asUnits(s, unit): return s.t
    @staticmethod
    def uiUnit(): return "film"
curves = {}
seen = {"min_keys": 99}
class Curve(object):
    def __init__(s): s.keys = []              # [time, value] sorted
    def _sort(s): s.keys.sort(key=lambda k: k[0])
    def _track(s): seen["min_keys"] = min(seen["min_keys"], len(s.keys))
class Fn(object):
    def __init__(s, obj): s.c = curves[obj]
    numKeys = property(lambda s: len(s.c.keys))
    isWeighted = False
    def find(s, t):
        for i, k in enumerate(s.c.keys):
            if abs(k[0] - t.t) < 1e-6: return i
        return None
    def input(s, i): return MTime(s.c.keys[i][0])
    def addKey(s, t, v, itt=0, ott=0): s.c.keys.append([t.t, v]); s.c._sort(); s.c._track()
    def setValue(s, i, v, change=None): s.c.keys[i][1] = v
    def remove(s, i, change=None): del s.c.keys[i]; s.c._track()
    def evaluate(s, t):
        ks = s.c.keys
        if not ks: return 0.0
        if t.t <= ks[0][0]: return ks[0][1]
        for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
            if t0 <= t.t <= t1: return v0 + (v1 - v0) * (t.t - t0) / (t1 - t0)
        return ks[-1][1]
    def __getattr__(s, name): return lambda *a, **k: None   # tangent/infinity setters
worker.om = types.SimpleNamespace(MTime=MTime)
worker.oma = types.SimpleNamespace(MFnAnimCurve=Fn, MAnimCurveChange=lambda: None)
worker._mobj = lambda name: name

w = worker.Worker.__new__(worker.Worker)
w.convert_units = False
w.find_curve = lambda data: data["curve"]
def key(t, v): return [t, v, 1, 1, 0, 0, 0, 0, 1, 1, 0]
def data(keys): return {"curve": "c", "weighted": False, "pre": 0, "post": 0, "keys": keys,
                        "samples": [[t, None] for t in range(1, 41)]}
def run(keys):
    d = data(keys)
    fn = Fn("c"); probe = Curve(); probe.keys = [[k[0], k[1]] for k in keys]; probe._sort()
    real = curves["c"]; curves["p"] = probe
    d["samples"] = [[t, Fn("p").evaluate(MTime(t))] for t in range(1, 41)]
    curves["c"] = real; seen["min_keys"] = 99
    w.apply_curve(d)
    return [[round(a, 3), round(b, 3)] for a, b in curves["c"].keys]

curves["c"] = Curve(); curves["c"].keys = [[1, 0.0], [10, 5.0], [20, 0.0]]
assert run([key(1, 0.0), key(10, 8.0), key(20, 0.0)]) == [[1, 0], [10, 8], [20, 0]]
assert seen["min_keys"] == 99                         # no key added or removed: only a value set
print("ok: moving a key's value updates it in place")
assert run([key(1, 0.0), key(12, 8.0), key(20, 0.0)]) == [[1, 0], [12, 8], [20, 0]]
assert seen["min_keys"] >= 3
print("ok: moving a key in time adds the new one before removing the old (never empty)")
assert run([key(1, 0.0), key(12, 8.0), key(16, 3.0), key(20, 0.0)])[2] == [16, 3]
assert run([key(5, 2.0)]) == [[5, 2]] and seen["min_keys"] >= 1
print("ok: keys added and removed; the curve always keeps at least one key")
assert not any("rebuilt instead" in l for l in logs)

# fallback: if the in-place result doesn't match, the old full rebuild runs
calls = {"rebuild": 0}
real_rebuild = w._rebuild
w._update_keys = lambda *a: None                          # pretend in-place left it wrong
def rebuild(curve, d, convert):
    calls["rebuild"] += 1
    curves["c"].keys = [[k[0], k[1]] for k in d["keys"]]
w._rebuild = rebuild
assert run([key(1, 1.0), key(30, 9.0)]) == [[1, 1], [30, 9]] and calls["rebuild"] >= 1
assert any("rebuilt instead" in l for l in logs)
print("ok: if in place doesn't match your Maya, the full rebuild is used and noted")
