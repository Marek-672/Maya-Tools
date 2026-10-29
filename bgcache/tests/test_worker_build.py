import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, time
from unittest import mock
exec(open(os.path.join(TESTS, "test_display.py")).read().split("from bgcache import worker")[0])
from bgcache import worker
logs = []
worker.log = lambda m: logs.append(m)
w = worker.Worker.__new__(worker.Worker)
w.cfg = {"light": True, "plugins": [{"name": "gpuCache", "path": "/maya/plug-ins/gpuCache.so"},
                                    {"name": "studioSet", "path": "/tools/studioSet.so"}],
         "launched_at": 1000.0, "timing": {"export": 6.2, "snapshot": 3.1}}
loaded = set()
cmds.pluginInfo.side_effect = lambda name, **k: name in loaded
cmds.loadPlugin.side_effect = lambda path, **k: loaded.add({"/maya/plug-ins/gpuCache.so": "gpuCache", "/tools/studioSet.so": "studioSet"}[path])
w._load_plugins()
assert loaded == {"gpuCache", "studioSet"} and "gpuCache, studioSet" in logs[-1]
print("ok: light start loads the scene's plug-ins:", logs[-1])
w.timing = {"launch": 41.0, "plug-ins": 2.0, "scene open": 58.4, "setup": 1.6}
w.ready_t = 1000.0 + 6.2 + 3.1 + 41 + 2 + 58.4 + 1.6
w.ref_times = {"santa_rig.mb": 31.2, "livingroom_set.mb": 14.0, "chair.mb": 2.9}
w._log_startup(9.0)
assert logs[-2].startswith("startup: export 6s, snapshot 3s, launch 41s, plug-ins 2s, scene open 58s, setup 2s, first frames 9s  (total 2:01)"), logs[-2]
assert logs[-1] == "slowest references: santa_rig.mb 31s, livingroom_set.mb 14s, chair.mb 3s"
print("ok:", logs[-2]); print("ok:", logs[-1])
