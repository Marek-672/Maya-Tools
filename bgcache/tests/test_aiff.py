import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, struct, array, math
qt = types.ModuleType("PySide2"); qc = types.ModuleType("PySide2.QtCore"); qt.QtCore = qc
sys.modules["PySide2"] = qt; sys.modules["PySide2.QtCore"] = qc
sys.path.insert(0, REPO)
from bgcache import audio
rate, fps = 48000, 24.0
n = rate
vals = [int(20000 * math.sin(k * 0.01)) for k in range(n)]

def ext80(x):
    e = int(math.floor(math.log2(x))); m = int(x / 2.0 ** (e - 63))
    return struct.pack(">HQ", e + 16383, m)

def make(path, comp, bits, ch=2, float_=False):
    frames = []
    for v in vals:
        for _ in range(ch):
            if float_:
                frames.append(struct.pack(">f" if bits == 32 else ">d", v / 32768.0))
            elif comp == b"sowt":
                frames.append(struct.pack("<i", v << (bits - 16))[:bits // 8])
            else:
                frames.append(struct.pack(">i", v << (bits - 16))[4 - bits // 8:])
    raw = b"".join(frames)
    is_c = comp is not None
    comm = struct.pack(">HIH", ch, n, bits) + ext80(rate) + ((comp + b"\x04none") if is_c else b"")
    ssnd = struct.pack(">II", 0, 0) + raw
    body = (b"AIFC" if is_c else b"AIFF") + b"COMM" + struct.pack(">I", len(comm)) + comm + (b"\x00" if len(comm) & 1 else b"") \
         + b"SSND" + struct.pack(">I", len(ssnd)) + ssnd
    open(path, "wb").write(b"FORM" + struct.pack(">I", len(body)) + body)

cases = [("plain AIFF 16", None, 16, False), ("AIFF 24", None, 24, False), ("AIFC NONE 16", b"NONE", 16, False),
         ("AIFC sowt 16", b"sowt", 16, False), ("AIFC sowt 24", b"sowt", 24, False), ("AIFC in24", b"in24", 24, False),
         ("AIFC twos 16", b"twos", 16, False), ("AIFC fl32", b"fl32", 32, True), ("AIFC FL32", b"FL32", 32, True), ("AIFC fl64", b"fl64", 64, True)]
for name, comp, bits, fl in cases:
    path = "/tmp/t.aiff"; make(path, comp, bits, float_=fl)
    pcm, ch, r = audio._read_aiff(path)
    got = array.array("h"); got.frombytes(pcm)
    worst = max(abs(got[i * 2] - vals[i]) for i in range(0, n, 97))
    assert r == rate and ch == 2 and len(got) == n * 2 and worst <= 1, (name, r, ch, worst)
    # full pipeline with a Maya-like range and offset
    snd = audio.load_aligned({"path": path, "offset": 1001, "source_start": 0, "source_end": 24}, 1001, 1340, fps)
    print("ok  %-14s rate=%d max err=%d" % (name, r, worst))
try:
    make("/tmp/t.aiff", b"ima4", 16); audio._read_aiff("/tmp/t.aiff")
except ValueError as e:
    print("ok  real compression rejected clearly:", e)
