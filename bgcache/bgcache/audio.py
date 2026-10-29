"""Sound for the bgcache player.

Reads the scene's sound file (WAV or AIFF), lines it up with the playback
range using the audio node's offset / sourceStart / sourceEnd, and plays it.

Backends, tried in order:
    Qt multimedia (QAudioOutput on PySide2, QAudioSink on PySide6)
    paplay / aplay as a subprocess (if Qt multimedia isn't available)

No Maya imports. The player restarts the sound on every play, scrub and loop,
so small drifts never accumulate.
"""
import array
import shutil
import struct
import subprocess
import sys
import threading

try:
    from PySide6 import QtCore
    QT6 = True
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore
    QT6 = False


def log(msg):
    print("bgcache audio: %s" % msg)
    sys.stdout.flush()


# --------------------------------------------------------------------------
# Decoding to 16-bit little-endian PCM (first two channels at most)
# --------------------------------------------------------------------------
def _to_s16le(raw, width, big_endian=False, unsigned8=False, is_float=False):
    if is_float:
        if width not in (4, 8):
            raise ValueError("%d-bit float audio not supported" % (width * 8))
        floats = array.array("f" if width == 4 else "d")
        floats.frombytes(raw)
        if big_endian != (sys.byteorder == "big"):
            floats.byteswap()
        out = array.array("h", (int(max(-1.0, min(1.0, v)) * 32767) for v in floats))
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()
    if width == 1:
        out = bytearray(len(raw) * 2)
        out[1::2] = raw.translate(bytes((b ^ 0x80) for b in range(256))) if unsigned8 else raw
        return bytes(out)
    if width not in (2, 3, 4):
        raise ValueError("%d-bit audio not supported" % (width * 8))
    # Keep the two most significant bytes of each sample.
    out = bytearray(len(raw) // width * 2)
    if big_endian:
        out[0::2], out[1::2] = raw[1::width], raw[0::width]
    else:
        out[0::2], out[1::2] = raw[width - 2::width], raw[width - 1::width]
    return bytes(out)


def _first_two_channels(pcm, channels):
    if channels <= 2:
        return pcm, channels
    block = 2 * channels
    out = bytearray(len(pcm) // block * 4)
    for i in range(4):
        out[i::4] = pcm[i::block]
    return bytes(out), 2


def _read_wav(path):
    """Minimal RIFF reader: PCM 8/16/24/32-bit, float32, and WAVE_FORMAT_EXTENSIBLE
    (which Python's wave module rejects before 3.12)."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            tag, channels, rate = struct.unpack("<HHI", body[:8])
            bits = struct.unpack("<H", body[14:16])[0]
            if tag == 0xFFFE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, channels, rate, bits)
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    if not fmt or raw is None:
        raise ValueError("WAV file has no fmt or data chunk")
    tag, channels, rate, bits = fmt
    if tag not in (1, 3):
        raise ValueError("compressed WAV (format %d) not supported" % tag)
    width = bits // 8
    pcm = _to_s16le(raw[:len(raw) // (width * channels) * width * channels], width,
                    unsigned8=(width == 1), is_float=(tag == 3))
    return pcm, channels, rate


def _ext80(b):
    """IEEE 754 80-bit extended float (AIFF sample rate)."""
    exponent = ((b[0] & 0x7F) << 8) | b[1]
    mantissa = int.from_bytes(b[2:10], "big")
    if exponent == 0 and mantissa == 0:
        return 0.0
    value = mantissa * 2.0 ** (exponent - 16383 - 63)
    return -value if b[0] & 0x80 else value


# AIFF-C compression types that are really uncompressed PCM
_AIFC_BIG_INT = (b"none", b"twos", b"in24", b"in32")
_AIFC_LITTLE_INT = (b"sowt",)
_AIFC_FLOAT = (b"fl32", b"fl64")


def _read_aiff(path):
    """Minimal AIFF / AIFF-C reader: big- and little-endian (sowt) integer PCM,
    and 32/64-bit float. Python's aifc module rejects most AIFF-C files."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"FORM" or data[8:12] not in (b"AIFF", b"AIFC"):
        raise ValueError("not an AIFF file")
    is_aifc = data[8:12] == b"AIFC"
    pos, comm, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"COMM":
            channels, nframes, bits = struct.unpack(">HIH", body[:8])
            rate = int(round(_ext80(body[8:18])))
            comp = body[18:22] if is_aifc and len(body) >= 22 else b"NONE"
            comm = (channels, nframes, bits, rate, comp)
        elif cid == b"SSND":
            offset = struct.unpack(">I", body[:4])[0]
            raw = body[8 + offset:]
        pos += 8 + size + (size & 1)
    if not comm or raw is None:
        raise ValueError("AIFF file has no COMM or SSND chunk")
    channels, nframes, bits, rate, comp = comm
    width = (bits + 7) // 8
    raw = raw[:nframes * width * channels]
    kind = comp.lower()
    if kind in _AIFC_BIG_INT:
        pcm = _to_s16le(raw, width, big_endian=True)
    elif kind in _AIFC_LITTLE_INT:
        pcm = _to_s16le(raw, width)
    elif kind in _AIFC_FLOAT:
        pcm = _to_s16le(raw, 4 if kind == b"fl32" else 8, big_endian=True, is_float=True)
    else:
        raise ValueError("compressed AIFF-C (%r) not supported, %d-bit %d Hz"
                         % (comp.decode("latin-1"), bits, rate))
    return pcm, channels, rate


def read_file(path):
    """Any supported WAV/AIFF file -> (16-bit PCM, channels (max 2), rate)."""
    with open(path, "rb") as handle:
        head = handle.read(12)
    reader = _read_aiff if head[:4] == b"FORM" else _read_wav   # by content, not extension
    pcm, channels, rate = reader(path)
    pcm, channels = _first_two_channels(pcm, channels)
    return pcm, channels, rate


def convert_channels(pcm, src, dst):
    """Mono <-> stereo for 16-bit PCM."""
    if src == dst:
        return pcm
    if src == 1 and dst == 2:
        out = bytearray(len(pcm) * 2)
        out[0::4], out[1::4], out[2::4], out[3::4] = pcm[0::2], pcm[1::2], pcm[0::2], pcm[1::2]
        return bytes(out)
    if src == 2 and dst == 1:
        out = bytearray(len(pcm) // 2)
        out[0::2], out[1::2] = pcm[0::4], pcm[1::4]
        return bytes(out)
    raise ValueError("can't convert %d to %d channels" % (src, dst))


def fit(pcm, frames, fps, rate, channels):
    """Pad with silence or trim so the sound lasts exactly `frames` frames."""
    need = int(round(frames / float(fps) * rate)) * 2 * channels
    pcm = pcm or b""
    return pcm[:need] if len(pcm) >= need else pcm + bytes(need - len(pcm))


def fade(pcm, channels, rate, ms=3.0):
    """Short fade in/out so a slice doesn't click."""
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    frames = len(samples) // channels
    n = min(frames // 2, max(1, int(rate * ms / 1000.0)))
    for i in range(n):
        g = i / float(n)
        for c in range(channels):
            samples[i * channels + c] = int(samples[i * channels + c] * g)
            j = (frames - 1 - i) * channels + c
            samples[j] = int(samples[j] * g)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes()


def click_track(frames, fps, rate, channels, every):
    """Silence with a sharp click on frame 0, every, 2*every... (sync test)."""
    total = int(round(frames / float(fps) * rate))
    samples = array.array("h", bytes(total * 2 * channels))
    length = int(rate * 0.012)
    for k in range(0, frames, every):
        at = int(round(k / float(fps) * rate))
        for i in range(min(length, total - at)):
            v = int(26000 * (1.0 - i / float(length)) * (1 if (i * 2400 // rate) % 2 == 0 else -1))
            for c in range(channels):
                samples[(at + i) * channels + c] = v
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes()


def load_aligned(info, start, end, fps):
    """PCM covering scene frames start..end, silence where there is no sound.

    Maya: the sound begins at scene frame `offset`, starting `sourceStart` frames
    into the file, and stops `sourceEnd` frames into the file.
    """
    pcm, channels, rate = read_file(info["path"])
    block = 2 * channels
    src_len = len(pcm) // block
    src_lo = max(0, int(round(info.get("source_start", 0.0) / fps * rate)))
    src_end = src_len
    if info.get("source_end", 0) > info.get("source_start", 0):
        src_end = min(src_len, int(round(info["source_end"] / fps * rate)))

    total = int(round((end - start + 1) / fps * rate))
    out = bytearray(total * block)
    # file sample playing at output sample k = src0 + k
    src0 = int(round((start - info.get("offset", 0.0) + info.get("source_start", 0.0)) / fps * rate))
    k0 = max(0, src_lo - src0)   # nothing before the sound's offset
    k1 = min(total, src_end - src0)
    if k1 > k0:
        out[k0 * block:k1 * block] = pcm[(src0 + k0) * block:(src0 + k1) * block]
    return bytes(out), channels, rate


def resample(pcm, channels, src_rate, dst_rate):
    """16-bit PCM from src_rate to dst_rate (linear). Uses numpy when there
    (Maya ships it), else plain Python (slower, same result)."""
    if src_rate == dst_rate or not pcm:
        return pcm
    n_src = len(pcm) // (2 * channels)
    n_dst = int(round(n_src * dst_rate / float(src_rate)))
    try:
        import numpy as np
        src = np.frombuffer(pcm[:n_src * 2 * channels], dtype="<i2").reshape(n_src, channels).astype(np.float64)
        where = np.arange(n_dst) * (src_rate / float(dst_rate))
        out = np.empty((n_dst, channels), dtype=np.float64)
        for ch in range(channels):
            out[:, ch] = np.interp(where, np.arange(n_src), src[:, ch])
        return np.clip(np.round(out), -32768, 32767).astype("<i2").tobytes()
    except ImportError:
        src = array.array("h", pcm[:n_src * 2 * channels])
        if sys.byteorder == "big":
            src.byteswap()
        out = array.array("h", bytes(n_dst * 2 * channels))
        step = src_rate / float(dst_rate)
        last = n_src - 1
        for i in range(n_dst):
            pos = i * step
            a = int(pos)
            b = a + 1 if a < last else last
            t = pos - a
            for ch in range(channels):
                out[i * channels + ch] = int(round(src[a * channels + ch] * (1 - t) + src[b * channels + ch] * t))
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()


# --------------------------------------------------------------------------
# Playback
# --------------------------------------------------------------------------
class _QtBackend(object):
    """Qt audio. If the output device won't take the sound as it is, the
    sound is converted here: to the device's sample rate (many Windows
    devices run at a fixed 48000 Hz) and/or from mono to stereo (headsets
    that only take stereo); positions stay in the sound's own format."""

    def __init__(self, pcm, channels, rate):
        self.in_rate = self.out_rate = rate
        self.in_ch = self.out_ch = channels
        other = 2 if channels == 1 else 1
        if QT6:
            from PySide6 import QtMultimedia as qm
            device = qm.QMediaDevices.defaultAudioOutput()
            if device.isNull():
                raise RuntimeError("no default output device")

            def fmt_at(r, ch):
                fmt = qm.QAudioFormat()
                fmt.setSampleRate(r)
                fmt.setChannelCount(ch)
                fmt.setSampleFormat(qm.QAudioFormat.Int16)
                return fmt
            alt = device.preferredFormat().sampleRate() or rate
            fmt = None
            for r, ch in ((rate, channels), (rate, other), (alt, channels), (alt, other)):
                if device.isFormatSupported(fmt_at(r, ch)):
                    fmt, self.out_rate, self.out_ch = fmt_at(r, ch), r, ch
                    break
            if fmt is None:
                raise RuntimeError("default output device doesn't accept %d Hz/%d ch" % (rate, channels))
            self.out = qm.QAudioSink(device, fmt)
            self.name = "Qt (%s)" % device.description()
        else:
            from PySide2 import QtMultimedia as qm

            def fmt_at(r, ch):
                fmt = qm.QAudioFormat()
                fmt.setSampleRate(r)
                fmt.setChannelCount(ch)
                fmt.setSampleSize(16)
                fmt.setCodec("audio/pcm")
                fmt.setByteOrder(qm.QAudioFormat.LittleEndian)
                fmt.setSampleType(qm.QAudioFormat.SignedInt)
                return fmt
            device = qm.QAudioDeviceInfo.defaultOutputDevice()
            if device.isNull():
                raise RuntimeError("no default output device")
            alt = device.nearestFormat(fmt_at(rate, channels)).sampleRate() or rate
            fmt = None
            for r, ch in ((rate, channels), (rate, other), (alt, channels), (alt, other)):
                if device.isFormatSupported(fmt_at(r, ch)):
                    fmt, self.out_rate, self.out_ch = fmt_at(r, ch), r, ch
                    break
            if fmt is None:
                raise RuntimeError("default output device doesn't accept %d Hz/%d ch" % (rate, channels))
            self.out = qm.QAudioOutput(device, fmt)
            self.name = "Qt (%s)" % device.deviceName()
        self.buffer = QtCore.QBuffer()
        self.scrub_buffer = QtCore.QBuffer()
        self.block = 2 * channels                 # bytes per sample frame, the sound's own
        self.out_block = 2 * self.out_ch          # the same in what the device gets
        self.rate = rate
        if self.out_rate != rate:
            self.name += ", converted %d -> %d Hz" % (rate, self.out_rate)
        if self.out_ch != channels:
            self.name += ", %s -> %s" % ("mono" if channels == 1 else "stereo",
                                          "stereo" if self.out_ch == 2 else "mono")
        self.set_data(pcm)

    def _convert(self, data):
        data = convert_channels(data, self.in_ch, self.out_ch) if self.out_ch != self.in_ch else data
        return resample(data, self.out_ch, self.in_rate, self.out_rate)

    def play_data(self, data):
        self.out.stop()
        if self.scrub_buffer.isOpen():
            self.scrub_buffer.close()
        self.scrub_buffer.setData(QtCore.QByteArray(self._convert(data)))
        self.scrub_buffer.open(QtCore.QIODevice.ReadOnly)
        self.out.start(self.scrub_buffer)

    def set_data(self, pcm):
        self.out.stop()
        if self.buffer.isOpen():
            self.buffer.close()
        self.buffer.setData(QtCore.QByteArray(self._convert(pcm)))
        self.buffer.open(QtCore.QIODevice.ReadOnly)

    def play(self, offset):
        """offset: bytes into the sound in its own format."""
        self.out.stop()
        frame = offset // self.block
        if self.out_rate != self.in_rate:
            frame = int(round(frame * self.out_rate / float(self.in_rate)))
        self.buffer.seek(frame * self.out_block)
        self.out.start(self.buffer)

    def stop(self):
        self.out.stop()


class _PipeBackend(object):
    def __init__(self, pcm, channels, rate):
        if shutil.which("paplay"):
            self.cmd = ["paplay", "--raw", "--format=s16le", "--rate=%d" % rate,
                        "--channels=%d" % channels, "--latency-msec=40"]
        elif shutil.which("aplay"):
            self.cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate),
                        "-c", str(channels)]
        else:
            raise RuntimeError("no paplay or aplay on PATH")
        self.pcm = pcm
        self.proc = None
        self.stop_flag = None
        self.name = self.cmd[0]

    def set_data(self, pcm):
        self.stop()
        self.pcm = pcm


    def play_data(self, data):
        full, self.pcm = self.pcm, data
        self.play(0)
        self.pcm = full

    def play(self, offset):
        self.stop()
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        flag = self.stop_flag = threading.Event()
        proc, data = self.proc, self.pcm   # captured now: play_data swaps self.pcm back

        def feed():
            try:
                for i in range(offset, len(data), 16384):
                    if flag.is_set():
                        return
                    proc.stdin.write(data[i:i + 16384])
                proc.stdin.close()
            except (IOError, OSError, ValueError):
                pass
        threading.Thread(target=feed, daemon=True).start()

    def stop(self):
        if self.stop_flag:
            self.stop_flag.set()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


class Sound(object):
    """Plays one soundtrack lined up with the player's timeline:
    set_pcm(...) with the whole track, then play(position) / stop().
    Position 0 is the first frame of the timeline."""

    def __init__(self):
        self.backend = None
        self.fmt = None
        self.pcm = b""
        self.channels, self.rate, self.fps = 2, 48000, 24.0
        self.muted = False
        self.status = "no sound"
        self.failed = False

    @property
    def available(self):
        return self.backend is not None and bool(self.pcm)

    def set_pcm(self, pcm, channels, rate, fps, status="sound on"):
        self.stop()
        self.pcm, self.channels, self.rate, self.fps = pcm or b"", channels, rate, float(fps)
        if not self.pcm:
            self.status = status
            return
        fmt = (channels, rate)
        if self.backend is not None and fmt == self.fmt:
            self.backend.set_data(self.pcm)
            self.status = status
            return
        if self.failed == fmt:
            self.status = "no audio output"
            return
        self.backend, errors = None, []
        for backend in (_QtBackend, _PipeBackend):
            try:
                self.backend = backend(self.pcm, channels, rate)
                break
            except Exception as error:
                errors.append("%s: %s" % (backend.__name__, error))
        if self.backend:
            self.fmt = fmt
            self.status = status
            log("output via %s (%d Hz, %d ch)" % (self.backend.name, rate, channels))
        else:
            self.status = "no audio output"
            self.failed = fmt
            log("no audio output: %s" % "; ".join(errors))

    def play(self, position):
        if not self.available or self.muted:
            return
        block = 2 * self.channels
        offset = int(round(position / self.fps * self.rate)) * block
        if 0 <= offset < len(self.pcm):
            self.backend.play(offset)

    def stop(self):
        if self.backend:
            self.backend.stop()


    def scrub(self, position, frames=1.0):
        """Play just this frame's sound (Maya-style audio scrubbing)."""
        if not self.available or self.muted:
            return
        block = 2 * self.channels
        start = max(0, int(round(position / self.fps * self.rate))) * block
        length = int(round(frames / self.fps * self.rate)) * block
        data = self.pcm[start:start + length]
        if data:
            self.backend.play_data(fade(data, self.channels, self.rate))

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.stop()
        return self.muted
