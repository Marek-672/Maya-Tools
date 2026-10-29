"""0.8.0b9: graphics memory full. Seen at the studio: three Mayas on a 16 GB
virtual GPU, the background Maya printed OpenCL CL_OUT_OF_RESOURCES and the
cache sat red with no message. Now the background Maya notices the errors in
its log, switches its deformers to the CPU, redoes the frames rendered just
before, and says so; the player shows a red banner, and also warns on its own
when caching stops moving (in case the background Maya is too stuck to say)."""
import os, sys, json, time, types
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w`, session, paths `p`

evals = {}
cmds.evaluator = lambda name=None, enable=None, **k: evals.__setitem__(name, enable)
assert w.gpu_on is True and w.warning == ""
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
for _ in range(6): step()
st = json.load(open(p["status"]))
assert st["state"] == "ready" and st["gpu"] is True and st["warning"] == ""
print("ok: normal caching: GPU on, no warning")

# Maya prints the OpenCL errors into worker.log (its stdout)
with open(p["log"], "a") as h:
    h.write("OpenCL Error: CL_OUT_OF_RESOURCES error executing CL_COMMAND_NDRANGE_KERNEL on NVIDIA A40-16Q (Device 0).\n")
w._check_gpu(force=True)
st = json.load(open(p["status"]))
assert evals.get("deformer") is False and w.gpu_on is False
assert "GPU deformers failed in the background Maya: caching on the CPU" in st["warning"] and st["gpu"] is False
assert st["cameras"]["|shotCam"]["dirty"], "recent frames are redone"
assert any("GPU deformers failed (errors above): switched off" in m for m in LOG)
print("ok: OpenCL errors in the log: deformers to the CPU, recent frames redone, warning in the status")
for _ in range(6): step()
st = json.load(open(p["status"]))
assert not st["cameras"]["|shotCam"]["dirty"] and st["state"] == "ready"
print("ok: caching carries on (on the CPU) and finishes")

# More errors later: nothing switches twice
evals.clear()
with open(p["log"], "a") as h:
    h.write("OpenCL error CL_OUT_OF_RESOURCES\n")
w._check_gpu(force=True)
assert "deformer" not in evals
print("ok: already on the CPU: no second switch")

# The profile can keep the background Maya off the GPU from the start
w2 = worker.Worker(dict(cfg, background_gpu=False))
assert w2.gpu_on is False
print("ok: profile background_gpu false: CPU from the start")
assert worker.Worker(dict(cfg)).gpu_on is True
assert common.GPU_TROUBLE_RE.search("OpenCL Error: CL_OUT_OF_RESOURCES error executing CL_COMMAND_READ_BUFFER")
assert not common.GPU_TROUBLE_RE.search("rendered 6 frames in 0.40s")
text, pos = common.read_new(p["log"], 0)
assert "CL_OUT_OF_RESOURCES" in text and common.read_new(p["log"], pos)[0] == ""
print("ok: the error pattern and reading only what's new in the log")

src = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert 'cmds.evaluator(name="deformer", enable=self.gpu_on)' in src
print("ok: the scene setup uses the GPU only when allowed")
