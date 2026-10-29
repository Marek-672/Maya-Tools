import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import types, time, tempfile
from unittest import mock
qt = types.ModuleType("PySide2"); qt.QtCore = mock.MagicMock(); qt.QtGui = mock.MagicMock()
sys.modules.update({"PySide2": qt, "PySide2.QtCore": qt.QtCore, "PySide2.QtGui": qt.QtGui})
sys.path.insert(0, REPO)
from bgcache.continuity import reel
reel.CACHE_ROOT = tempfile.mkdtemp()
def make(shot, name, mb, age_days):
    d = os.path.join(reel.CACHE_ROOT, shot, name); os.makedirs(d)
    f = os.path.join(d, "f.1.jpg"); open(f, "wb").write(b"x" * int(mb * 1024 * 1024))
    t = time.time() - age_days * 86400
    os.utime(f, (t, t)); os.utime(d, (t, t))
make("sq050_0470", "P_v9_540p", 5, 30)       # unused for a month
make("sq050_0473", "P_v17_540p", 5, 1)
make("sq050_0481", "P_v22_540p", 5, 2)
assert reel.prune_cache(max_age_days=14, max_gb=1) == 1
assert not os.path.exists(os.path.join(reel.CACHE_ROOT, "sq050_0470", "P_v9_540p"))
print("ok: converted shots unused for 2 weeks are removed")
assert reel.prune_cache(max_age_days=14, max_gb=6.0 / 1024) == 1     # cap ~6 MB: oldest of the two goes
assert os.path.isdir(os.path.join(reel.CACHE_ROOT, "sq050_0473", "P_v17_540p"))
assert not os.path.exists(os.path.join(reel.CACHE_ROOT, "sq050_0481", "P_v22_540p"))
print("ok: over the size cap, the least recently used goes first")

# ===== 0.7.5: department movies start with a slate =====
info_mov = {"source_type": "single_movie", "source_path": "/projects/BIRDS/sq050_0472/movie/cgr/CG_x_v3/a.mov",
            "department": "shoco", "version": 3}
info_seq = {"source_type": "image_sequence", "source_path": "/projects/BIRDS/sq050_0472/work/mov/P/a.1001.jpg"}
with mock.patch.object(reel, "shot_length", lambda show, shot: 340):
    assert reel.movie_skip(info_mov, 341) == 1          # one longer than the shot: the slate
    assert reel.movie_skip(info_mov, 340) == 0          # same length: no slate
    assert reel.movie_skip(info_mov, 360) == 0          # something else: play as is
    assert reel.movie_skip(info_seq, 341) == 0          # image sequences carry frame numbers
with mock.patch.object(reel, "shot_length", lambda show, shot: None):
    assert reel.movie_skip(info_mov, 341) == 1          # nothing to compare: studio movies have a slate
fake = ["f.%d.jpg" % i for i in range(1, 342)]
with mock.patch.object(reel, "prepare_frames", lambda *a: list(fake)), \
     mock.patch.object(reel, "shot_length", lambda show, shot: 340):
    frames, skip = reel.shot_frames("sq050_0472", info_mov, 540, lambda x: None)
assert skip == 1 and len(frames) == 340 and frames[0] == "f.2.jpg"
full = tempfile.mkdtemp()
for i in range(1, 342):
    open(os.path.join(full, "ref.%04d.jpg" % i), "w").close()
with mock.patch.object(reel, "shot_length", lambda show, shot: 340):
    path, first = reel._full_start(full, info_mov)
assert first == 2 and path.endswith("ref.0002.jpg")     # the image plane starts past the slate
print("ok: a movie one frame longer than the shot skips its slate (playback, sound, image plane)")
