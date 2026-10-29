import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time
from unittest import mock
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from bgcache import common, controller as C
c = C.Controller(); c.session = common.new_session(); c.cfg = {"start": 1001, "end": 1010}
CONST, CYCLE = C.CONSTANT, 3
key = lambda t, v, iy=0.0, oy=0.0: (t, v, 1, 1, 1.0, iy, 1.0, oy, True, True, False)
curve = lambda keys, pre=CONST, post=CONST: {"keys": keys, "weighted": False, "pre": pre, "post": post, "plug": "cog_ctrl.squash"}
F, L = 1001, 1010

# 1) "key everything": first key on an unkeyed attribute, value unchanged -> nothing to re-render
c.static_vals = {"cog_ctrl.squash": 0.5}
with mock.patch.object(C.scene, "frame_values", lambda n, a, b: [0.5] * (b - a + 1)):
    ranges, send, why = c._dirty("curve1", None, curve([key(1005, 0.5)]), F, L)
assert ranges == [] and send and why is None and "cog_ctrl.squash" not in c.static_vals
print("ok: first key, same value -> nothing re-renders (curve still sent to the background)")
# 2) first key with a different value -> whole shot, with a reason
c.static_vals = {"cog_ctrl.squash": 0.5}
with mock.patch.object(C.scene, "frame_values", lambda n, a, b: [0.9] * (b - a + 1)):
    ranges, send, why = c._dirty("curve1", None, curve([key(1005, 0.9)]), F, L)
assert ranges == [[F, L]] and "value changed" in why
print("ok: first key, new value -> whole shot, reason:", why)
# 3) value never recorded -> whole shot (safe), reason says so
c.static_vals = {}
ranges, send, why = c._dirty("curve1", None, curve([key(1005, 0.9)]), F, L)
assert ranges == [[F, L]] and "wasn't recorded" in why
print("ok: unknown earlier value -> whole shot (safe):", why)
# 4) cycling curve: only frames that really changed
old = curve([key(1001, 0), key(1005, 1)], post=CYCLE); old["frames"] = [0, .25, .5, .75, 1, 0, .25, .5, .75, 1]
new_vals = [0, .25, .5, .9, 1, 0, .25, .5, .9, 1]
with mock.patch.object(C.scene, "frame_values", lambda n, a, b: list(new_vals)):
    ranges, send, why = c._dirty("cyc", old, curve([key(1001, 0), key(1004, .9), key(1005, 1)], post=CYCLE), F, L)
assert ranges == [[1004, 1004], [1009, 1009]] and send and why is None
print("ok: cycle curve -> only the changed frames:", ranges)
# 5) ordinary key move still uses the tight key-to-key range
ranges, send, why = c._dirty("x", curve([key(1001, 0), key(1005, 1), key(1009, 0)]),
                             curve([key(1001, 0), key(1005, 2), key(1009, 0)]), F, L)
assert ranges == [[1001, 1009]] and why is None
print("ok: normal edit range unchanged:", ranges)
# 6) constant detection for Delete Static Channels
assert C.constant_value(curve([key(1001, .5), key(1009, .5)])) == .5
assert C.constant_value(curve([key(1001, .5), key(1009, .5, oy=.3)])) is None
assert C.constant_value(curve([key(1001, .5), key(1009, .7)])) is None
print("ok: static curve detection (equal values + flat tangents)")
# 7) flush: deleting a static curve sends no frames; changed one sends the whole shot with a reason
C.cmds.objExists = lambda n: True
C.cmds.getAttr = lambda plug: 0.5
c.snap = {"crv_static": curve([key(1001, .5), key(1009, .5)]), "crv_moving": curve([key(1001, .1), key(1009, .9)])}
c.pending, c.pending_handles = set(), []
c.removed = [("crv_static", "cog_ctrl.a"), ("crv_moving", "cog_ctrl.b")]
c.cfg.update({"start": F, "end": L})
with mock.patch.object(C.scene, "plug_value", lambda p: 0.5):
    c.flush()
msgs = common.take_messages(c.session)
assert len(msgs) == 1 and msgs[0]["op"] == "delete_curves"
assert sorted(x["plug"] for x in msgs[0]["curves"]) == ["cog_ctrl.a", "cog_ctrl.b"]
assert msgs[0]["ranges"] == [[F, L]] and msgs[0]["why"] == ["cog_ctrl.b: curve deleted, value changed"]
# only static curves deleted (Delete Static Channels): nothing to re-render
c.snap = {"s%d" % i: curve([key(1001, .5)]) for i in range(500)}
c.removed = [("s%d" % i, "ctl%d.a" % i) for i in range(500)]
with mock.patch.object(C.scene, "plug_value", lambda p: 0.5):
    c.flush()
msgs = common.take_messages(c.session)
assert len(msgs) == 1 and len(msgs[0]["curves"]) == 500 and msgs[0]["ranges"] == []
print("ok: deletions go in ONE message (500 curves -> 1 message); static ones re-render nothing; reasons kept")
