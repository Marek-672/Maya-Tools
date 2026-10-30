"""0.9.0b4: ffmpeg is found where people usually have it, or downloaded
(only on the wizard's click) from a pinned build, checksum-checked."""
import gzip
import hashlib
import io
import os
import shutil
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))
home = os.path.realpath(tempfile.mkdtemp())
os.environ["HOME"] = os.environ["USERPROFILE"] = home
from bgcache.continuity import ffmpeg_get                   # noqa: E402

assert ffmpeg_get.own_folder().startswith(home)
assert all(len(b[1]) == 64 and b[2] > 10 ** 7 for b in ffmpeg_get.BUILDS.values())
assert set(ffmpeg_get.BUILDS) >= {("darwin", "arm64"), ("linux", "x86_64"), ("windows", "x86_64")}
print("ok: a pinned ffmpeg build (with its checksum) for macOS (Apple and Intel), Linux and Windows")

# a fake build: a script that answers -version like ffmpeg does
script = b"#!/bin/sh\necho 'ffmpeg version 7.0.2-static'\n" if os.name != "nt" else b"fake"
packed = gzip.compress(script)
name = "ffmpeg-test.gz"
ffmpeg_get.build_for_this_computer = lambda: (name, hashlib.sha256(packed).hexdigest(), len(packed))
asked = []


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


import urllib.request                                       # noqa: E402
urllib.request.urlopen = lambda url, timeout=0: (asked.append(url), _Answer(packed))[1]
if os.name != "nt":
    seen = []
    exe = ffmpeg_get.download(progress=lambda done, total: seen.append((done, total)))
    assert exe == os.path.join(home, ".bgcache", "ffmpeg", "ffmpeg") and os.access(exe, os.X_OK)
    assert asked == [ffmpeg_get.URL % (ffmpeg_get.BUILD_TAG, name)] and seen[-1] == (len(packed), len(packed))
    assert ffmpeg_get.find() == exe and sorted(os.listdir(ffmpeg_get.own_folder())) == ["ffmpeg"]
    print("ok: Download it for me: fetched, checked, unpacked into ~/.bgcache/ffmpeg, found from then on")

# a wrong checksum leaves nothing behind
ffmpeg_get.build_for_this_computer = lambda: (name, "0" * 64, len(packed))
shutil.rmtree(ffmpeg_get.own_folder(), ignore_errors=True)
try:
    ffmpeg_get.download()
    raise AssertionError("a wrong checksum must fail")
except RuntimeError as error:
    assert "checksum" in str(error)
assert not os.listdir(ffmpeg_get.own_folder())


def offline(url, timeout=0):
    raise OSError("no route to host")


urllib.request.urlopen = offline
try:
    ffmpeg_get.download()
    raise AssertionError("offline must fail")
except RuntimeError as error:
    assert "no route to host" in str(error)
print("ok: a wrong checksum or no internet: a plain message, and nothing half-written is left")

from bgcache import profile                                 # noqa: E402
profile._cache["profile"] = dict(profile.DEFAULT, ffmpeg_download=False)
profile._cache["key"] = profile._cache["key"] or ("x",)
profile.load = lambda force=False: profile._cache["profile"]
assert not ffmpeg_get.can_download()
try:
    ffmpeg_get.download()
    raise AssertionError("switched off must fail")
except RuntimeError as error:
    assert "switched off" in str(error)
print("ok: a studio can switch the download off (ffmpeg_download: false)")
shutil.rmtree(home, ignore_errors=True)
