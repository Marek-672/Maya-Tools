import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, os, subprocess
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])
sys.path.insert(0, REPO)
from unittest import mock
from bgcache import common, controller
c = controller.Controller(); c.session = common.new_session(); c.cfg = {"skip_in_background": ["animbot"]}
cmds.warning = print
captured = []
class FakeProc:
    def __init__(s, cmd, **k): captured.append((cmd, k.get("env"))); s.cmd = cmd
    def poll(s): return None
with mock.patch.object(controller.subprocess, "Popen", FakeProc), \
     mock.patch.object(controller.scene, "find_mayapy", lambda: sys.executable), \
     mock.patch.object(controller.scene, "find_maya", lambda: "/fake/maya"):
    c.mayapy_cmd = None
    c.launch_player()
    c._launch_worker()
(pcmd, penv), (wcmd, wenv) = captured
# 1) the player's exact command, with PYTHONPATH wiped and run from another folder
env = {k: v for k, v in penv.items() if k != "PYTHONPATH"}
assert penv["BGCACHE_PKG"] == REPO
test_cmd = [a.replace("'bgcache.player'", "'bgcache.common'") for a in pcmd]
r = subprocess.run(test_cmd, env=env, cwd="/", capture_output=True, text=True)
assert r.returncode == 0, r.stderr
print("ok: player command finds bgcache even with PYTHONPATH wiped:", " ".join(pcmd[:2]), "...")
# 2) worker MEL command: a fixed string (no folder path to break the quoting
#    on Windows), bgcache's folder in BGCACHE_PKG
mel_cmd = wcmd[-1]
assert mel_cmd == controller.WORKER_COMMAND and REPO not in mel_cmd and wenv["BGCACHE_PKG"] == REPO, mel_cmd
assert mel_cmd.startswith('python("') and mel_cmd.endswith('")') and mel_cmd.count('"') == 2
inner = mel_cmd[len('python("'):-2]
r = subprocess.run([sys.executable, "-c", inner.replace("import bgcache.worker; bgcache.worker.boot()",
                                                       "import bgcache.common; print('found', bgcache.common.__file__)")],
                   env=dict({"BGCACHE_PKG": wenv["BGCACHE_PKG"]},
                            # Windows' Python can't start without SYSTEMROOT
                            **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {})),
                   cwd="/", capture_output=True, text=True)
assert r.returncode == 0 and REPO in r.stdout, (r.stdout, r.stderr)
print("ok: background Maya command is fixed and finds bgcache through BGCACHE_PKG:", mel_cmd)
# a folder with spaces and backslashes (a Windows install) changes nothing in the command
with mock.patch.object(controller.scene, "_pkg_parent", lambda: r"D:\Program Files\maya tools"):
    e = c._env()
assert e["BGCACHE_PKG"] == r"D:\Program Files\maya tools" and controller.WORKER_COMMAND == mel_cmd
print("ok: a Windows folder like D:\\Program Files\\... only goes in the environment")
# 3) animBot's userSetup line hits the stand-in in the background Maya
stub_first = wenv["PYTHONPATH"].split(os.pathsep)[0]
r = subprocess.run([sys.executable, "-c", "import animBot; animBot.launch(); animBot.anything(1, 2)"],
                   env={"PYTHONPATH": stub_first}, capture_output=True, text=True)
assert r.returncode == 0 and "animBot skipped" in r.stdout, (r.stdout, r.stderr)
assert "animbot" not in penv.get("PYTHONPATH", "").lower() or "stubs" not in penv["PYTHONPATH"]
print("ok: animBot.launch() in the background Maya does nothing:", r.stdout.strip())
