"""0.8.0b20: a path curve is replaced whole in the background Maya (curve
-replace: degree, knots, CVs), so added or removed CVs work too; b19 skipped
a curve whose CV count changed (studio: 13 -> 16 CVs, shot re-rendered unchanged)."""
import os, sys, types
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w`
calls = []
cmds.objExists = lambda n: True
cmds.getAttr = lambda plug: [(0, 0, 0)] * 13
cmds.curve = lambda shape, **k: calls.append((shape, k))
del LOG[:]
pts = [[i, 0, 0] for i in range(16)]
knots = [0, 0] + list(range(14)) + [13, 13]
w.set_curve_shape("|path|curveShape4", pts, 3, knots)
shape, k = calls[-1]
assert shape == "|path|curveShape4" and k["replace"] is True and k["degree"] == 3
assert len(k["point"]) == 16 and k["knot"] == knots
assert any("16 CVs now (was 13), replaced in one step" in m for m in LOG), LOG
print("ok: 13 -> 16 CVs: the curve is replaced in one step (degree, knots, CVs), no Reload needed")
cmds.getAttr = lambda plug: [(0, 0, 0)] * 16
del LOG[:]
w.set_curve_shape("|path|curveShape4", [[0, 2, 0]] * 16, 3, knots)
assert any("CVs moved up to 2.00" in m for m in LOG), LOG
print("ok: same count: replaced too; worker.log says how far the CVs moved")
def refused(shape, **k): raise RuntimeError("no")
cmds.curve = refused
del LOG[:]
w.set_curve_shape("|path|curveShape4", [[0, 0, 0]] * 13, 3, knots)
assert any("replace failed" in m for m in LOG) and any("Reload scene" in m for m in LOG)
print("ok: if the replace is refused and the CV count differs, it says Reload scene")
c = _source.source("controller")
assert "def curve_definition(shape):" in c and "out.append(scene.curve_definition(shape))" in c
assert '"cc", "cached", "cr", "create"' in c
print("ok: your Maya sends the whole curve (degree, knots, object-space CVs), also after a rebuild or knot insert")
