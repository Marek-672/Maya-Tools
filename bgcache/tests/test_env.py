import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, os
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
os.environ["MAYA_MODULE_PATH"] = os.pathsep.join(["/studio/site/maya/modules", "/u/artist/maya/modules/animBot", "/apps/arnold/modules"])
os.environ["PYTHONPATH"] = os.pathsep.join(["/studio/site/python", "/u/artist/maya/scripts/AnimBot/py"])
from bgcache import common, controller
c = controller.Controller(); c.session = common.new_session()
c.cfg = {"skip_in_background": ["animbot"], "skip_user_setup": False}
env = c._worker_env()
assert "animbot" not in env["MAYA_MODULE_PATH"].lower() and "/apps/arnold/modules" in env["MAYA_MODULE_PATH"]
assert "animbot" not in env["PYTHONPATH"].lower() and "/studio/site/python" in env["PYTHONPATH"]
assert env["BGCACHE_BACKGROUND"] == "1" and "MAYA_SKIP_USERSETUP_PY" not in env
assert "animBot" in os.environ["MAYA_MODULE_PATH"]          # your own Maya untouched
c.cfg["skip_user_setup"] = True; assert c._worker_env()["MAYA_SKIP_USERSETUP_PY"] == "1"
print("ok: animBot paths dropped for the background Maya only; studio paths kept")
