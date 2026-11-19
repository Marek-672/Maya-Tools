"""0.9.0b25: a mouse button Qt wrongly reports as held must not stop
cameras, shown / hidden and layers being followed for good."""
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import scene

state = {"qt": True, "os": None}
scene._qt_mouse_held = lambda: state["qt"]
scene._os_mouse_held = lambda: state["os"]
scene._held_since[0] = None
assert scene._mouse_held(now=100.0) is True and scene._mouse_held(now=110.0) is True
assert scene._mouse_held(now=100.0 + scene.HELD_STUCK_S + 1) is False
print("ok: a button reported down for more than %d s without a break counts as not held" % scene.HELD_STUCK_S)
state["qt"] = False
assert scene._mouse_held(now=200.0) is False
state["qt"] = True
assert scene._mouse_held(now=201.0) is True
print("ok: a real release resets it: the next drag is a drag again")
state["os"] = False
assert scene._mouse_held(now=202.0) is False
state["os"] = True
assert scene._mouse_held(now=203.0) is True
print("ok: on Windows the system's answer wins when Qt says held and the system says not")
scene._held_since[0] = None
state["os"] = None
assert scene._mouse_held() is True        # with the clock, not a given time
print("ok: works off the clock")
