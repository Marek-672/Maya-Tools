"""0.8.0b5: a sound device that only takes its own rate (Windows headsets often
run at a fixed 48000 Hz). The player converts the sound to the device's rate
instead of going silent; positions stay in the sound's own rate."""
import os, sys, types, array, math
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))

# a fake PySide6 with a device that only accepts 48000 Hz
started, data = {}, {}
class Fmt:
    Int16 = "Int16"
    def setSampleRate(s, r): s.r = r
    def setChannelCount(s, c): s.c = c
    def setSampleFormat(s, f): s.f = f
    def sampleRate(s): return s.r
class Device:
    def isNull(s): return False
    def description(s): return "Headphones (fixed 48 kHz)"
    def isFormatSupported(s, f): return f.r == 48000
    def preferredFormat(s): f = Fmt(); f.setSampleRate(48000); return f
class Sink:
    def __init__(s, dev, fmt): started["rate"] = fmt.r
    def stop(s): pass
    def start(s, buf): started["buf"] = buf
class Buffer:
    def __init__(s): s.d, s.at, s.open_ = b"", 0, False
    def setData(s, d): s.d = bytes(d)
    def open(s, mode): s.open_ = True
    def isOpen(s): return s.open_
    def close(s): s.open_ = False
    def seek(s, o): s.at = o
qm = types.SimpleNamespace(QAudioFormat=Fmt, QAudioSink=Sink,
                           QMediaDevices=types.SimpleNamespace(defaultAudioOutput=lambda: Device()))
qc = types.SimpleNamespace(QBuffer=Buffer, QByteArray=bytes, QIODevice=types.SimpleNamespace(ReadOnly=1))
pyside = types.ModuleType("PySide6"); pyside.QtCore = qc; pyside.QtMultimedia = qm
sys.modules.update({"PySide6": pyside, "PySide6.QtCore": qc, "PySide6.QtMultimedia": qm})
from bgcache import audio
assert audio.QT6

rate = 44100
tone = array.array("h", [int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate) for _ in (0, 1)]).tobytes()
snd = audio.Sound()
snd.set_pcm(tone, 2, rate, 24.0)
assert snd.backend is not None and snd.status == "sound on", snd.status
assert started["rate"] == 48000 and "converted 44100 -> 48000" in snd.backend.name
assert len(snd.backend.buffer.d) == 48000 * 4
print("ok: a device that refuses 44100 Hz plays the sound converted to its 48000 Hz (not silence)")
snd.play(12.0)                                   # frame 12 at 24 fps = 0.5 s
assert snd.backend.buffer.at == 24000 * 4, snd.backend.buffer.at
print("ok: playing from a frame lands at the same moment in the converted sound (0.5 s -> 24000 samples)")
snd.scrub(6.0)
assert len(started["buf"].d) == round(rate / 24.0 * 48000 / rate) * 4 or abs(len(started["buf"].d) // 4 - 2000) <= 1
print("ok: scrubbing a frame plays that frame's sound, converted too")

# A headset that only takes STEREO at 48000 Hz (the home A50): a mono sound
# file used to be refused ("doesn't accept 48000 Hz/1 ch") and play nothing.
Device.isFormatSupported = lambda s, f: f.r == 48000 and getattr(f, "c", 2) == 2
mono = array.array("h", [int(8000 * math.sin(2 * math.pi * 440 * i / 48000)) for i in range(48000)]).tobytes()
snd = audio.Sound()
snd.set_pcm(mono, 1, 48000, 24.0)
assert snd.backend is not None and snd.status == "sound on", snd.status
assert "mono -> stereo" in snd.backend.name and snd.backend.out_ch == 2
assert len(snd.backend.buffer.d) == 48000 * 4
print("ok: a stereo-only device plays a mono sound file as stereo (not silence)")
snd.play(12.0)
assert snd.backend.buffer.at == 24000 * 4, snd.backend.buffer.at
print("ok: frame positions land right after the mono -> stereo conversion")
mono44 = array.array("h", [0] * 44100).tobytes()
snd.set_pcm(mono44, 1, 44100, 24.0)
assert "converted 44100 -> 48000" in snd.backend.name and "mono -> stereo" in snd.backend.name
assert len(snd.backend.buffer.d) == 48000 * 4
snd.play(12.0)
assert snd.backend.buffer.at == 24000 * 4
print("ok: both at once: 44100 Hz mono -> 48000 Hz stereo")
