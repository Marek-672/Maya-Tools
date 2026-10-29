"""0.6.9/0.6.10: batches sized by time from a fitted model (playblast start-up
+ per-frame cost) so a new edit is picked up quickly without paying the start-up
cost on every frame; 1 frame first after an edit; status.json only rewritten
when something changed; edit timing line."""
import os, sys, runpy, json, time as _time, types
TESTS = os.path.dirname(os.path.abspath(__file__))
ns = runpy.run_path(os.path.join(TESTS, "test_worker.py"))   # reuse its fake Maya
worker, common, state = ns["worker"], ns["common"], ns["state"]
LOG = ns["LOG"]

# fake clock: each rendered frame costs COST seconds, each playblast OVERHEAD
clock = {"t": 1000.0}
COST = {"frame": 0.2, "overhead": 0.1}
worker.time = types.SimpleNamespace(time=lambda: clock["t"], strftime=_time.strftime, sleep=_time.sleep)
cmds = sys.modules["maya.cmds"]
real_blast = cmds.playblast
def blast(startTime, endTime, filename, **k):
    clock["t"] += COST["overhead"] + COST["frame"] * (endTime - startTime + 1)
    return real_blast(startTime=startTime, endTime=endTime, filename=filename, **k)
cmds.playblast = blast

session = common.new_session()
cfg = {"session": session, "start": 1, "end": 60, "chunk": 12, "quality": 85,
       "width": 64, "height": 36, "fps": 24}
w = worker.Worker(cfg); w.panel = "p"; w.cfg["controller_pid"] = os.getpid()
w.timer = type("T", (), {"start": lambda self, d: None})()
p = common.paths(session)

def sizes(cam=None):
    return [b - a + 1 for c, a, b in state["blasts"] if cam is None or c == cam]

common.write_json_atomic(p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
state["blasts"].clear()
for _ in range(30): w.step()
got = sizes()
assert got[:2] == [1, worker.FIRST_BATCH] and sum(got) == 60, got
assert max(got) == 3, got          # 0.1 s start-up + 0.2 s/frame: 0.75 s -> 3 frames
print("ok: measures with 1 then 3 frames; 0.2 s/frame rig -> batches of 3 (~0.7 s):", got)
st, per = w.render_model("|shotCam")
assert abs(st - 0.1) < 0.02 and abs(per - 0.2) < 0.02, (st, per)
print("ok: fitted start-up %.2fs + %.2fs/frame" % (st, per))

# big edit: whole shot dirty -> 1 frame first, from the current frame, then timed batches
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[1, 60]], "focus": 10,
                              "edited": clock["t"] - 0.2, "ts": clock["t"] - 0.05})
state["blasts"].clear()
for _ in range(40): w.step()
got = sizes()
assert got[0] == 1 and state["blasts"][0][1] == 10 and sum(got) == 60, got
print("ok: big edit -> the current frame alone first, then timed batches:", got[:6], "...")
line = [l for l in LOG if l.startswith("edit synced")][-1]
assert "first frame render" in line and "pickup" in line and "apply" in line and "batches 1," in line, line
print("ok: timing line:", line)

# your rig: 1.1 s playblast start-up + 0.28 s/frame -> batches of 5, not single frames
COST["frame"], COST["overhead"] = 0.28, 1.1
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[1, 60]], "focus": 1, "ts": clock["t"]})
state["blasts"].clear()
for _ in range(80): w.step()
got = sizes()
assert got[0] == 1 and max(got) <= 8 and got[-5:-1] == [5, 5, 5, 5], got   # settles on 5 after the speed change
st, per = w.render_model("|shotCam")
assert abs(st - 1.1) < 0.1 and abs(per - 0.28) < 0.05, (st, per)
print("ok: big start-up cost (1.1 s + 0.28 s/frame) -> batches of 5 (~2.5 s), never all singles:", got[:10])

# light rig (0.02 s/frame): batches grow to the largest allowed (12)
COST["frame"], COST["overhead"] = 0.02, 0.05
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[1, 60]], "focus": 1, "ts": clock["t"]})
state["blasts"].clear()
for _ in range(40): w.step()
for _ in range(3):                 # older samples age out of the fit
    common.post_message(session, {"op": "curves", "curves": [], "ranges": [[1, 60]], "focus": 1, "ts": clock["t"]})
    state["blasts"].clear()
    for _ in range(40): w.step()
assert 12 in sizes(), sizes()
print("ok: light rig -> batches up to 12:", sizes())

# small edit: 4 frames -> 1 then the rest
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[20, 23]], "focus": 20, "ts": clock["t"]})
state["blasts"].clear()
for _ in range(6): w.step()
assert sizes() == [1, 3], sizes()
print("ok: small edit -> frame you're on first, then the rest:", sizes())

# other (not viewed) camera never gets the single-frame start
common.write_json_atomic(p["cameras"], {"checked": ["|shotCam", "|sideCam"], "view": "|shotCam"})
for _ in range(40): w.step()
common.post_message(session, {"op": "curves", "curves": [], "ranges": [[1, 60]], "focus": 1, "ts": clock["t"]})
state["blasts"].clear()
for _ in range(60): w.step()
assert sizes("|shotCam")[0] == 1 and 1 not in sizes("|sideCam")[:-1], (sizes("|shotCam"), sizes("|sideCam"))
print("ok: other cameras keep timed batches")

# idle: status.json not rewritten every step
w.step(); m1 = os.stat(p["status"]).st_mtime_ns
_time.sleep(0.02); w.step(); w.step()
assert os.stat(p["status"]).st_mtime_ns == m1
clock["t"] += 2; w.step()
assert os.stat(p["status"]).st_mtime_ns != m1
print("ok: idle status only rewritten as a heartbeat")
assert worker.IDLE_POLL_MS <= 50
