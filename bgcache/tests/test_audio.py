import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, struct, wave, io, math, array, os, tempfile
# stub PySide2 so audio.py imports
qt = types.ModuleType("PySide2"); qc = types.ModuleType("PySide2.QtCore"); qt.QtCore = qc
sys.modules["PySide2"] = qt; sys.modules["PySide2.QtCore"] = qc
sys.path.insert(0, REPO)
import warnings; warnings.simplefilter("ignore")
from bgcache import audio

rate, fps = 48000, 24.0
n = rate * 2  # 2 s ramp: sample k has value k % 30000 so we can identify positions
vals = [k % 30000 for k in range(n)]

def wav16(path, ch=1):
    w = wave.open(path, "wb"); w.setnchannels(ch); w.setsampwidth(2); w.setframerate(rate)
    data = array.array("h", [v for v in vals for _ in range(ch)]); w.writeframes(data.tobytes()); w.close()

def wav_ext24(path):  # WAVE_FORMAT_EXTENSIBLE, 24-bit, stereo
    ch=2; raw = b"".join(struct.pack("<i", v << 8)[:3] * ch for v in vals)
    fmt = struct.pack("<HHIIHH", 0xFFFE, ch, rate, rate*ch*3, ch*3, 24) + struct.pack("<HHI", 22, 24, 3) + struct.pack("<H", 1) + b"\x00"*14
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(raw)) + raw
    open(path, "wb").write(b"RIFF" + struct.pack("<I", len(body)) + body)

def wav_float(path):
    raw = array.array("f", [v / 32768.0 for v in vals]).tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate*4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(raw)) + raw
    open(path, "wb").write(b"RIFF" + struct.pack("<I", len(body)) + body)

def _ext80(x):
    # IEEE 754 80-bit extended, as AIFF's COMM sample rate needs
    import math
    m, e = math.frexp(float(x))
    return struct.pack(">HQ", e + 16382, int(m * (1 << 64)))

def aiff16(path):  # written by hand: the aifc module is gone from newer Pythons
    data = array.array("h", vals); data.byteswap(); raw = data.tobytes()
    comm = struct.pack(">hIh", 1, len(vals), 16) + _ext80(rate)
    ssnd = struct.pack(">II", 0, 0) + raw
    body = b"AIFF" + b"COMM" + struct.pack(">I", len(comm)) + comm + b"SSND" + struct.pack(">I", len(ssnd)) + ssnd
    open(path, "wb").write(b"FORM" + struct.pack(">I", len(body)) + body)

def first_sample(pcm, ch, k):
    return struct.unpack_from("<h", pcm, k * 2 * min(ch, 2))[0]

for maker, ch, tol in ((wav16, 1, 0), (lambda p: wav16(p, 4), 4, 0), (wav_ext24, 2, 0), (wav_float, 1, 1), (aiff16, 1, 0)):
    path = os.path.join(tempfile.gettempdir(), "t_%s.%s" % (id(maker), "aif" if maker is aiff16 else "wav"))
    maker(path)
    # scene 1001-1048 (2 s), sound starts at frame 1005, sourceStart 2 frames in
    info = {"path": path, "offset": 1005, "source_start": 2, "source_end": 0}
    pcm, c, r = audio.load_aligned(info, 1001, 1048, fps)
    assert r == rate and c == min(ch, 2), (c, r)
    total = len(pcm) // (2 * c)
    assert total == int(round(48 / fps * rate)), total
    lead = int(round(4 / fps * rate))           # frames 1001-1004 silent
    assert all(first_sample(pcm, c, k) == 0 for k in (0, lead - 1))
    s0 = int(round(2 / fps * rate))             # first audible = file sample at 2 frames
    got = first_sample(pcm, c, lead)
    assert abs(got - vals[s0]) <= tol, (maker, got, vals[s0])
    got = first_sample(pcm, c, lead + 1000)
    assert abs(got - vals[s0 + 1000]) <= tol
    # tail beyond the file is silent
    end_k = lead + (n - s0)
    if end_k < total:
        assert first_sample(pcm, c, end_k) == 0
    print("ok", os.path.basename(path), c, "ch")

# sourceEnd trims; scene starting after the sound began
info = {"path": os.path.join(tempfile.gettempdir(), "t_trim.wav"), "offset": 990, "source_start": 0, "source_end": 20}
wav16(info["path"])
pcm, c, r = audio.load_aligned(info, 1001, 1048, fps)
k = 0; assert first_sample(pcm, c, 0) == vals[int(round(11 / fps * rate))]
cut = int(round((20 - 11) / fps * rate))
assert first_sample(pcm, c, cut - 1) != 0 and first_sample(pcm, c, cut) == 0
print("ok trim/late start")
