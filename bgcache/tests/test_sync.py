import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, json, tempfile, time
os.environ["BGCACHE_ROOT"] = tempfile.mkdtemp()
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds"); mel = types.ModuleType("maya.mel")
api = types.ModuleType("maya.api"); om = types.ModuleType("maya.api.OpenMaya"); oma = types.ModuleType("maya.api.OpenMayaAnim")
class _F: kConstant = 0
oma.MFnAnimCurve = _F
now = {"t": 1001, "playing": False, "jobs": []}
def currentTime(*a, query=False, **k):
    if query: return float(now["t"])
    now["t"] = a[0]; ctl._on_time_changed()   # Maya fires timeChanged
cmds.currentTime = currentTime
cmds.play = lambda query=False, state=False: now["playing"]
for n, m in (("maya", maya), ("maya.cmds", cmds), ("maya.mel", mel), ("maya.api", api), ("maya.api.OpenMaya", om), ("maya.api.OpenMayaAnim", oma)):
    sys.modules[n] = m
qt = types.ModuleType("PySide2"); qc = types.ModuleType("PySide2.QtCore")
class T:
    def __init__(s): pass
    def setSingleShot(s, x): pass
    def start(s, *a): pass
    def stop(s): pass
    @property
    def timeout(s): return types.SimpleNamespace(connect=lambda f: None)
qc.QTimer = T; qt.QtCore = qc; sys.modules["PySide2"] = qt; sys.modules["PySide2.QtCore"] = qc
sys.path.insert(0, REPO)
from bgcache import common, controller
ctl = controller.Controller(); ctl.session = common.new_session(); ctl._player_ts = time.time() - 1
p = common.paths(ctl.session)
rd = lambda k: common.read_json(p[k])

ctl._on_time_changed()
assert rd("maya_time")["frame"] == 1001; print("ok: Maya frame published")
ts0 = rd("maya_time")["ts"]
common.write_json_atomic(p["player_time"], {"frame": 1100, "ts": time.time(), "sync": True})
ctl._poll_player_time()
assert now["t"] == 1001, "Maya waits until the player rests on the frame"
common.write_json_atomic(p["player_time"], {"frame": 1101, "ts": time.time() + 0.01, "sync": True})
ctl._poll_player_time(); assert now["t"] == 1001
common.write_json_atomic(p["player_time"], {"frame": 1100, "ts": time.time() + 0.02, "sync": True})
ctl._poll_player_time(); assert now["t"] == 1001
print("ok: stepping/scrubbing through frames doesn't move Maya on every frame")
ctl._pending_frame = (ctl._pending_frame[0], time.time() - 1)      # rested a second on 1100
ctl._poll_player_time()
assert now["t"] == 1100 and rd("maya_time")["ts"] == ts0
print("ok: once the player rests on a frame, Maya moves there once; no echo back to the player")
controller.scene.SETTLE_S = 0          # the rest checks the rules, not the waiting
ctl._poll_player_time(); assert now["t"] == 1100; print("ok: same player message not applied twice")
now["t"] = 1200; ctl._on_time_changed(); assert rd("maya_time")["frame"] == 1200; print("ok: later Maya change still published")
now["playing"] = True
common.write_json_atomic(p["player_time"], {"frame": 1010, "ts": time.time() + 1, "sync": True})
ctl._poll_player_time(); assert now["t"] == 1200; print("ok: ignored while Maya is playing")
now["playing"] = False
common.write_json_atomic(p["player_time"], {"frame": 1020, "ts": time.time() + 2, "sync": False})
ctl._poll_player_time(); assert now["t"] == 1200
now["t"] = 1300; ctl._on_time_changed(); assert rd("maya_time")["frame"] == 1200
print("ok: sync off stops both directions")
