import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, json, tempfile, struct, wave, array, time
from unittest import mock
root = tempfile.mkdtemp(); os.environ["BGCACHE_ROOT"] = root
os.environ["HOME"] = root  # prefs + resolver config go to a temp home

class Dummy(object):
    def __init__(self, *a, **k): pass
    def __getattr__(self, name): return mock.MagicMock()
def qtmod(name):
    m = mock.MagicMock(); m.__name__ = name; return m
QtCore, QtGui, QtWidgets = qtmod("QtCore"), qtmod("QtGui"), qtmod("QtWidgets")
for n in ("QWidget", "QFrame", "QLayout"): setattr(QtWidgets, n, Dummy)
class DummyLabel(Dummy):
    def setText(self, text): self._text = text
    def text(self): return getattr(self, "_text", "")
QtWidgets.QLabel = DummyLabel
class DummyToolButton(Dummy):
    def setChecked(self, on): self._on = bool(on)
    def isChecked(self): return getattr(self, "_on", False)
    def setCheckable(self, on): pass
    InstantPopup = 2; MenuButtonPopup = 1
QtWidgets.QToolButton = DummyToolButton
pyside = types.ModuleType("PySide2"); pyside.QtCore, pyside.QtGui, pyside.QtWidgets = QtCore, QtGui, QtWidgets
sys.modules.update({"PySide2": pyside, "PySide2.QtCore": QtCore, "PySide2.QtGui": QtGui, "PySide2.QtWidgets": QtWidgets})
sys.path.insert(0, REPO)
import importlib
from bgcache import common, audio
from bgcache.continuity import reel
import bgcache.player as pl

# --- a fake /projects tree: live shot sound + neighbour sound (exactly shot-length)
jobs = os.path.join(root, "jobs")
def aud(shot, ver, frames, rate=48000):
    d = os.path.join(jobs, "BIRDS", shot, "work", "aud", "AUD_%s_ax_v%03d" % (shot, ver)); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "AUD_%s_ax_v%03d.wav" % (shot, ver))
    w = wave.open(p, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(array.array("h", [1000] * int(frames / 24.0 * rate) * 2).tobytes()); w.close()
    return p
live_audio = aud("sq050_0472", 5, 340)
aud("sq050_0470", 2, 30); aud("sq050_0470", 3, 48)   # newest version should win

session = common.new_session(); p = common.paths(session)
cfg = {"session": session, "start": 1001, "end": 1340, "fps": 24.0, "height": 540,
       "cameras": [{"name": "|shotCam", "label": "shotCam"}],
       "original_scene": "/projects/BIRDS/sq050_0472/maya/scene.mb",
       "audio": {"path": live_audio, "offset": 1001, "source_start": 0, "source_end": 0, "mute": False}}
common.write_json_atomic(p["config"], cfg)

with mock.patch.object(reel.Jobs, "add", lambda self, *a: None):
    P = pl.Player(session)
assert P.shot_ids == ("BIRDS", "sq050_0472", "sq050") and P.live_shot == "sq050_0472"
assert P.total == 340 and P.rate == 48000 and P.channels == 2
print("ok: shot parsed from scene path; live-only reel = 340 frames")

# --- audio lookup for a neighbour uses the live sound path as the template
tmpl = reel.audio_template(live_audio, "sq050_0472")
found = reel.find_shot_audio(tmpl, "sq050_0472", "sq050_0470")
assert found.endswith("AUD_sq050_0470_ax_v003.wav"), found
with mock.patch.object(reel, "ffmpeg", lambda: None):
    pcm, src = reel.prepare_audio("sq050_0470", {"source_type": "image_sequence"}, 48, 24.0, (tmpl, "sq050_0472", 48000, 2))
assert len(pcm) == 48 * 2000 * 4 and src == found
pcm2, src2 = reel.prepare_audio("sq050_0480", {"source_type": "image_sequence"}, 24, 24.0, (tmpl, "sq050_0472", 48000, 2))
assert src2 is None and len(pcm2) == 24 * 2000 * 4 and not any(pcm2)
print("ok: neighbour sound found by swapping the shot code (newest version), cut to shot length; missing -> silence")

# --- stage a before and an after shot (pretend conversion finished)
P.shots = ["sq050_0470", "sq050_0472", "sq050_0475"]
P.staged = {"before": ["sq050_0470"], "after": ["sq050_0475"]}
info = lambda d: {"department": d, "version": 9, "source_type": "image_sequence", "start_frame": 1001}
P.prepared["sq050_0470"] = {"info": info("P"), "frames": ["/x/%d" % i for i in range(48)], "pcm": pcm, "sound": found, "first": 1001}
P.prepared["sq050_0475"] = {"info": info("shoco"), "frames": ["/y/%d" % i for i in range(24)], "pcm": pcm2, "sound": None, "first": 1}
P.pos = P._live_offset() + 141          # on frame 1142
P._rebuild_reel()
assert [s["kind"] for s in P.segments] == ["before", "live", "after"] and P.total == 48 + 340 + 24
assert P._live_frame() == 1142, P._live_frame()
print("ok: reel = before 48 + live 340 + after 24; stayed on frame 1142 after staging")

# soundtrack: exactly as long as the reel, neighbour sound at the start
block = 4; per = 2000
assert len(P.sound.pcm) == P.total * per * block, (len(P.sound.pcm), P.total * per * block)
assert P.sound.pcm[:4] == struct.pack("<hh", 1000, 1000)
assert P.sound.pcm[(48 + 340) * per * block:] == bytes(24 * per * block)
print("ok: one soundtrack spans the reel, sample-exact at each cut")

# positions -> segments, sync only on the live shot
seg, local = P._locate(10); assert seg["shot"] == "sq050_0470" and local == 10
assert P._live_frame(10) is None and P._live_frame(48) == 1001 and P._live_frame(48 + 339) == 1340
P.pos = 5; P.send_time(); assert not os.path.exists(p["player_time"])
P.pos = 48 + 41; P.send_time(); assert common.read_json(p["player_time"])["frame"] == 1042
common.write_json_atomic(p["maya_time"], {"frame": 1200, "ts": time.time() + 5}); P._follow_maya()
assert P._live_frame() == 1200
print("ok: Maya sync maps through the reel; neighbour frames never move Maya")

# continuity off -> live only, still on the same frame
P.b_cont = mock.MagicMock(); P.toggle_continuity(False)
assert P.total == 340 and P._live_frame() == 1200
P.toggle_continuity(True); assert P.total == 412 and P._live_frame() == 1200
assert "before" not in json.load(open(common.PREFS_PATH))["shots"]["sq050_0472"]     # ticks aren't saved any more
print("ok: continuity off/on keeps the frame; ticked shots are not saved")

# ordering: two before shots play in sequence order regardless of staging order
P.shots = ["sq050_0465", "sq050_0470", "sq050_0472", "sq050_0475"]
P.staged["before"] = ["sq050_0470", "sq050_0465"]
P.prepared["sq050_0465"] = dict(P.prepared["sq050_0475"])
P._rebuild_reel()
assert [s["shot"] for s in P.segments][:2] == ["sq050_0465", "sq050_0470"]
print("ok: staged shots play in sequence order")

# --- checkbox staging: side comes from the filmstrip position, any number per side
P.jobs.add = lambda *a: None
P.shots = ["sq050_0460", "sq050_0465", "sq050_0470", "sq050_0472", "sq050_0475", "sq050_0480", "sq050_0490"]
P.staged = {"before": [], "after": []}
for s in ("sq050_0490", "sq050_0460", "sq050_0475", "sq050_0465", "sq050_0470", "sq050_0480"):
    P.stage(s, True)
assert P.staged["before"] == ["sq050_0460", "sq050_0465", "sq050_0470"], P.staged
assert P.staged["after"] == ["sq050_0490", "sq050_0475", "sq050_0480"], P.staged
fake = lambda n: {"info": info("P"), "frames": ["/f/%d" % i for i in range(n)], "pcm": audio.fit(b"", n, 24.0, 48000, 2), "sound": None, "first": 1001}
for i, s in enumerate(["sq050_0460", "sq050_0465", "sq050_0470", "sq050_0475", "sq050_0480", "sq050_0490"]):
    P.prepared[s] = fake(10 + i)
P._rebuild_reel()
order = [seg["shot"] for seg in P.segments]
assert order == P.shots, order
assert len(P.sound.pcm) == P.total * 2000 * 4
print("ok: 3 before + 3 after ticked in any order -> reel plays in sequence order:", " ".join(x[-4:] for x in order))
P.stage("sq050_0465", False)
assert "sq050_0465" not in P.staged["before"] and [seg["shot"] for seg in P.segments].count("sq050_0465") == 0
print("ok: unticking removes the shot from the reel")

# remembered shots on the wrong side get corrected when the shot list arrives
P.staged = {"before": ["sq050_0480"], "after": ["sq050_0460", "sq050_9999"]}
calls = []
def fake_add(prio, fn, cb): calls.append(cb)
P.jobs.add = fake_add
P.browser.cards = {}
P.shot_ids = ("BIRDS", "sq050_0472", "sq050")
P._list_shots()
calls[0]("done", list(P.shots))
assert P.staged == {"before": ["sq050_0460"], "after": ["sq050_0480"]}, P.staged
print("ok: remembered shots re-sorted to the correct side; shots no longer in the sequence dropped")

# next build: Untick all; and a new Start begins with nothing ticked
P.browser.untick = mock.MagicMock()
P.staged = {"before": ["sq050_0460"], "after": ["sq050_0480"]}; P._refresh_cards()
P.browser.untick.setEnabled.assert_called_with(True)
P.untick_all()
assert P.staged == {"before": [], "after": []} and all(seg["kind"] == "live" for seg in P.segments)
P.browser.untick.setEnabled.assert_called_with(False)
print("ok: Untick all empties the reel to your shot alone (button enabled only when something is ticked)")
P.staged = {"before": ["sq050_0460"], "after": []}; P._save_prefs()
with mock.patch.object(reel.Jobs, "add", lambda self, *a: None):
    P3 = pl.Player(session)
assert P3.staged == {"before": [], "after": []}
print("ok: a new Start begins with no shots ticked")

# --- Sync remembers the last choice
P.b_sync = mock.MagicMock()
P._set_sync(False)
assert json.load(open(common.PREFS_PATH))["sync"] is False
if os.path.exists(p["player_time"]): os.remove(p["player_time"])
with mock.patch.object(reel.Jobs, "add", lambda self, *a: None):
    P2 = pl.Player(session)
assert P2.sync is False
sent = common.read_json(p["player_time"])
assert sent and sent["sync"] is False
print("ok: sync off is remembered; the new player tells Maya's side sync is off")
P2.b_sync = mock.MagicMock(); P2._set_sync(True)
assert json.load(open(common.PREFS_PATH))["sync"] is True
print("ok: turning it back on is remembered too")

# ===== new features =====
P = P2
P.jobs.add = lambda *a: None
P.b_scrub = mock.MagicMock()

# scrub sound: plays one frame's slice at picture position + offset
calls = []
P.sound.scrub = lambda pos, frames=1.0: calls.append(pos)
P.sound.latency_frames = lambda: 0.5
P.audio_offset = 1.0
P.playing = 0
before = P.pos
P._step(1)
assert calls and abs(calls[-1] - (P.pos + 1.0)) < 1e-9, (calls, P.pos)   # offset only, no device delay
P._set_scrub(False); calls.clear(); P._step(1); assert not calls
assert json.load(open(common.PREFS_PATH))["scrub"] is False
print("ok: scrub sound plays the frame's slice (your offset only); Scrub off is remembered")

# offset keys
P._set_offset(0.0)
class NoMods:
    def __and__(s, other): return 0
class K:
    def __init__(s, k): s.k = k
    def key(s): return s.k
    def modifiers(s): return NoMods()
    def isAutoRepeat(s): return False
P.keyPressEvent(K(pl.Qt.Key_BracketLeft)); P.keyPressEvent(K(pl.Qt.Key_BracketLeft))
assert P.audio_offset == 0.5 and json.load(open(common.PREFS_PATH))["audio_offset"] == 0.5
P.keyPressEvent(K(pl.Qt.Key_BracketRight))
assert P.audio_offset == 0.25 and "earlier" in P._flash
print("ok: [ and ] nudge the offset by 1/4 frame and remember it:", P._flash)

# negative start (sound later than picture) -> delayed start, not a negative position
played = []
P.sound.play = lambda pos: played.append(pos)
P.sound.latency_frames = lambda: 0.0
P.audio_offset = -2.0
P.playing = 1; P._play_sound(0)
assert not played   # waits instead (timer)
P.audio_offset = 0.5; P._play_sound(10); assert played[-1] == 10.5
print("ok: sound start = picture + offset; negative offsets wait instead of seeking before 0")

# sync test in and out
P.playing = 0
total_before, pos_before, pcm_before = P.total, P.pos, P.sound.pcm
P.toggle_sync_test()
assert P.test_mode and P.total == 96 and P.playing == 1
clicks = array.array("h"); clicks.frombytes(P.sound.pcm)
assert clicks[0] != 0 and clicks[2000 * 2 * 24 // 24 * 1] == 0          # click at frame 0, silence after
assert clicks[48000 * 2] != 0                                         # next click at 1 s (frame 24)
P._rebuild_reel()                    # e.g. a shot finishes converting meanwhile: must not break the test
assert P.total == 96
P.toggle_sync_test()
assert not P.test_mode and P.total == total_before and P.pos == pos_before
assert len(P.sound.pcm) == len(pcm_before)
print("ok: sync test = 4 s of flash+click on each second; leaving restores the reel and its sound")

# Reload scene: player picks up a new range from config.json
cfg2 = common.read_json(p["config"]); cfg2.update({"rev": 7, "start": 1001, "end": 1300, "reloaded_at": time.time()})
time.sleep(0.01); common.write_json_atomic(p["config"], cfg2)
P._cfg_mtime = 0
P._check_config()
live = [s for s in P.segments if s["kind"] == "live"][0]
assert P.end == 1300 and live["n"] == 300, (P.end, live["n"])
print("ok: Reload scene: new frame range picked up from config, reel rebuilt")

# loading text
P.state = "opening scene"; P.cfg["launched_at"] = time.time() - 75; P.cfg.pop("reloaded_at", None); P.cfg["usual_startup"] = 105
assert P._loading() and P._loading_text() == "Loading scene... 1:15 (usually about 1:45)", P._loading_text()
P.state = "error: background Maya exited (see worker.log)"; assert not P._loading()
print("ok: loading text:", "Loading scene... 1:15 (usually about 1:45)")

# --- centring the live shot: waits for layout, then centres; never fights the user
class Bar:
    def __init__(s): s.max, s.val = 0, 0
    def maximum(s): return s.max
    def setValue(s, v): s.val = v
bar = Bar()
lay = types.SimpleNamespace(contentsMargins=lambda: types.SimpleNamespace(left=lambda: 8), spacing=lambda: 8)
P.browser = types.SimpleNamespace(isVisible=lambda: True, cards_layout=lay,
    scroll=types.SimpleNamespace(isVisible=lambda: True, viewport=lambda: types.SimpleNamespace(width=lambda: 1000),
                                 horizontalScrollBar=lambda: bar))
P.shots = ["s%02d" % i for i in range(20)]; P.live_shot = "s10"
P._scroll_to_live()
assert P._center_pending and bar.val == 0            # not laid out yet: waits
content = 16 + 20 * 184 + 19 * 8
bar.max = content - 1000; P._center_now()               # Qt reports the range
middle = 8 + 10 * 192 + 92
assert bar.val == middle - 500 and not P._center_pending, bar.val
bar.val = 123; bar.max += 1; P._center_now()            # later range change (resize): leave the user's scroll alone
assert bar.val == 123
P.shots = P.shots[:3]; P._scroll_to_live(); assert not P._center_pending   # all fit: nothing to do
print("ok: live shot centred once the strip is laid out (card %d of 20 at the middle); user scrolling left alone" % 11)

# ===== your shot as a reference movie; image plane request =====
P = P2
jobs = []
P.jobs.add = lambda prio, fn, cb: jobs.append((fn, cb))
P.shot_ids = ("BIRDS", "sq050_0472", "sq050"); P.live_shot = "sq050_0472"; P.shots = ["sq050_0470", "sq050_0472", "sq050_0473"]
live_card = mock.MagicMock(); P.browser = mock.MagicMock(); P.browser.cards = {"sq050_0472": live_card}
P.staged = {"before": [], "after": []}; P._rebuild_reel()
P.set_live_ref("shoco")
assert P.live_ref == "shoco" and json.load(open(common.PREFS_PATH))["shots"]["sq050_0472"]["live_ref"] == "shoco"
fn, cb = jobs[-1]
ref_frames = ["/ref/%d.jpg" % i for i in range(250)]
cb("done", {"info": {"department": "shoco", "version": 4, "source_type": "single_movie"}, "frames": ref_frames})
seg = [x for x in P.segments if x["kind"] == "live"][0]
assert seg["ref"] == ref_frames and seg["label"] == "shoco v004"
P.pos = P._live_offset() + 10
assert P._live_frame() == P.start + 10          # same shot timing: Maya sync still lines up
loaded = []
with mock.patch.object(pl.QtGui, "QImage", lambda path: loaded.append(path) or mock.MagicMock()):
    P.lru.clear(); P._image(P.pos)
assert loaded == ["/ref/10.jpg"]
P.pos = P._live_offset() + 260                 # beyond the 250-frame movie
assert P._image(P.pos) is None
print("ok: your shot plays the shoco movie in its own slot; frames line up; shorter movie handled")
P.toggle_live_ref(); assert P.live_ref is None and "ref" not in [x for x in P.segments if x["kind"] == "live"][0]
P.toggle_live_ref(); assert P.live_ref == "shoco"
print("ok: R flips live <-> shoco; choice remembered per shot")

# image plane: full-res frames prepared in the background, then one command to Maya
P.view = "|shotCam"
P.live_ref_ready = {"info": {"department": "shoco", "version": 4, "source_type": "single_movie"}, "frames": ref_frames}
P.image_plane("behind")
fn, cb = jobs[-1]
cb("done", ("/tmp/bgcache_reel/sq050_0472/shoco_v4_full/ref.0001.jpg", 1))
msg = common.read_json(p["player_cmd"])
assert msg["cmd"] == "image_plane" and msg["mode"] == "behind" and msg["camera"] == "|shotCam"
assert msg["offset"] == 1 - P.start and P.plane_mode == "behind"
P.remove_image_plane(); assert common.read_json(p["player_cmd"])["cmd"] == "image_plane_remove" and P.plane_mode is None
P.send_cmd("next_key"); assert common.read_json(p["player_cmd"])["cmd"] == "next_key"
print("ok: image plane command (movie frame 1 lines up with frame", P.start, "); remove; step-key uses its own channel")

# a forced Maya jump (step key) is followed even with Sync off
P.sync = False; P.playing = 0; P.dragging = False; P.live_ref = None; P._rebuild_reel()
common.write_json_atomic(p["maya_time"], {"frame": P.start + 7, "ts": time.time() + 50, "force": True})
P._follow_maya(); assert P._live_frame() == P.start + 7
common.write_json_atomic(p["maya_time"], {"frame": P.start + 20, "ts": time.time() + 60})
P._follow_maya(); assert P._live_frame() == P.start + 7
print("ok: with Sync off the player follows step-key jumps only")

# ===== 0.6.9: Envirs button removed =====
P._save_cameras()
assert "b_envirs" not in vars(P) and "_set_envirs" not in vars(pl.Player)
assert "envirs" not in (common.read_json(p["cameras"]) or {})
print("ok: no Envirs button; cameras.json carries cameras only")

# ===== 0.6.6: new frames picked up as soon as status.json changes =====
calls = []
with mock.patch.object(P, "_poll", lambda: (calls.append(1), P._status_changed())):
    P._status_mtime = None
    common.write_json_atomic(p["status"], {"state": "rendering", "ts": 1})
    P._poll_if_changed(); P._poll_if_changed()
    assert len(calls) == 1, calls                    # read once, not every tick
    time.sleep(0.01)
    common.write_json_atomic(p["status"], {"state": "ready", "ts": 2})
    P._poll_if_changed()
    assert len(calls) == 2
print("ok: player re-reads status only when the background Maya rewrote it")

# ===== 0.7.3: the window never grows with ticked continuity shots =====
P.start, P.end = 1001, 1340
P.segments = [{"kind": "before", "shot": "sq050_0470", "n": 48}, {"kind": "before", "shot": "sq050_0471", "n": 20},
              {"kind": "live", "shot": "sq050_0472", "n": 340}, {"kind": "after", "shot": "sq050_0473", "n": 30}]
texts = P._range_texts()
assert texts == ["0470 0471  ·  1001 – 1340  ·  0473", "2 before  ·  1001 – 1340  ·  1 after", "1001 – 1340"], texts
lab = pl.FitLabel()
lab.width = lambda: 120
class FM:
    def horizontalAdvance(self, t): return 7 * len(t)
    def elidedText(self, t, mode, w): return t[: w // 7 - 1] + "…"
lab.fontMetrics = lambda: FM()
lab.set_texts(texts)
assert lab.text() == "1001 – 1340" and lab.toolTip  # shortest that fits; full list on hover
lab.width = lambda: 400; lab._fit()
assert lab.text() == texts[0]
lab.width = lambda: 50; lab._fit()
assert lab.text().endswith("…")
assert "self.chips" not in open(pl.__file__).read()
print("ok: range text picks the longest version that fits (full list on hover); no Before/After list above the strip")
