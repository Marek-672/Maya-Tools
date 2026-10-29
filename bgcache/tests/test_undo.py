"""0.6.6 undo watcher: warns at Start when undo is off, offers to turn it on."""
import os, sys, types
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])   # Maya/Qt stubs
sys.path.insert(0, REPO)
from bgcache import controller
undo = {"on": True}; asked = []
def undoInfo(query=False, state=None, **k):
    if query: return undo["on"]
    if state is not None: undo["on"] = state
cmds.undoInfo = undoInfo
cmds.warning = lambda m: None
answer = {"v": "Turn undo on"}
cmds.confirmDialog = lambda **k: (asked.append(k), answer["v"])[1]

assert controller.check_undo() is True and not asked
print("ok: undo on -> no dialog")
undo["on"] = False
assert controller.check_undo() is True and undo["on"] is True and len(asked) == 1
assert "Preferences" in asked[0]["message"]
print("ok: undo off -> dialog, 'Turn undo on' turns it on and explains how to keep it on")
undo["on"] = False; answer["v"] = "Leave it off"
assert controller.check_undo() is False and undo["on"] is False
print("ok: 'Leave it off' leaves it alone")
cmds.undoInfo = lambda **k: 1 / 0
assert controller.check_undo() is False
print("ok: an error never stops Start")
