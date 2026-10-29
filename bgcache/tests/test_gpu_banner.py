"""0.8.0b9: the player's red banner when caching is in trouble: the background
Maya's own warning; graphics-memory errors in worker.log with nothing new for
30 s; or nothing new for 2 minutes at all. Never while paused or loading."""
import os, sys, time
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_reload.py")).read()
exec(src.split("P = pl.Player(session)")[0])          # Qt stubs + a session with config/status
P = pl.Player(session)
P.view = "|cam"; P.checked = ["|cam"]
P.loaded["|cam"] = {}; P.data["|cam"] = {}

def status(dirty, warning="", state="rendering"):
    common.write_json_atomic(p["status"], {"state": state, "reloads": 3, "ts": time.time(), "warning": warning,
                                           "cameras": {"|cam": {"dirty": dirty, "versions": {}}}})
status([])
P._poll()
assert P._health_banner() is None
print("ok: nothing dirty: no banner")

status([5, 6, 7]); P._poll()
assert P._health_banner() is None
P._progress_t -= P.STUCK_S + 5
assert P._health_banner().startswith("Caching seems stuck: nothing new for 2:0")
print("ok: red frames and nothing new for 2 minutes: 'Caching seems stuck'")

P._progress_t = time.time() - (P.STUCK_GPU_S + 5)
assert P._health_banner() is None
with open(p["log"], "a") as h:
    h.write("OpenCL Error: CL_OUT_OF_RESOURCES error executing CL_COMMAND_WRITE_BUFFER on NVIDIA A40-16Q (Device 0).\n")
P._log_check_t = 0; P._track_health()
assert P._gpu_trouble_t
P._progress_t = time.time() - (P.STUCK_GPU_S + 5)
assert P._health_banner().startswith("GPU deformers failed in the background Maya and caching stopped")
print("ok: OpenCL errors in worker.log and stuck 30 s: 'GPU deformers failed ... restarting it on the CPU'")

status([5, 6], warning="GPU deformers failed in the background Maya: caching on the CPU now (slower).")
P._poll()
assert P._health_banner().startswith("GPU deformers failed in the background Maya: caching on the CPU")
assert "GPU failed, caching on CPU" in open(os.path.join(REPO, "bgcache", "player.py")).read()
print("ok: the background Maya's own warning shows while frames are red, and in the status text")

status([5, 6], state="paused"); P.paused = True
assert P._health_banner() is None
P.paused = False
print("ok: never while paused")

status([], warning="GPU deformers failed in the background Maya: caching on the CPU now (slower)."); P._poll()
assert P._health_banner() is None
print("ok: once everything is cached the banner goes (the status text still says CPU)")
