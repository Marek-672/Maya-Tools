"""ffmpeg for continuity movies (0.9.0b4): find it, or download it when
the user clicks "Download it for me" in the setup wizard.

find() looks, in order: the profile's "ffmpeg", the departments_file's
"ffmpeg_path", bgcache's own copy (~/.bgcache/ffmpeg/), the PATH, then the
usual install folders. Image sequences don't need ffmpeg; movies and sound
from movies do.

download() fetches one pinned static build for this system (the
ffmpeg-static project's release BUILD_TAG, made from the usual static
builds: johnvansickle.com for Linux, evermeet.cx / osxexperts for macOS,
gyan.dev for Windows), checks its SHA-256 against the one written here,
and unpacks it into ~/.bgcache/ffmpeg/: no admin rights, nothing else on
the computer changes. It goes online only when called, and a studio can
switch it off with the profile's "ffmpeg_download": false. bgcache's zips
never include ffmpeg.
"""
import gzip
import hashlib
import os
import platform
import shutil
import subprocess
import sys

from bgcache import common, profile

BUILD_TAG = "b6.1.1"            # ffmpeg 7.0.2
URL = "https://github.com/eugeneware/ffmpeg-static/releases/download/%s/%s"
BUILDS = {   # (system, machine) -> (file, SHA-256 of the .gz, size in bytes)
    ("darwin", "arm64"): ("ffmpeg-darwin-arm64.gz",
                          "8923876afa8db5585022d7860ec7e589af192f441c56793971276d450ed3bbfa", 19246198),
    ("darwin", "x86_64"): ("ffmpeg-darwin-x64.gz",
                           "929b375c1182d956c51f7ac25e0b2b0411fb01f6f407aa15c9758efeb4242106", 25296431),
    ("linux", "x86_64"): ("ffmpeg-linux-x64.gz",
                          "bfe8a8fc511530457b528c48d77b5737527b504a3797a9bc4866aeca69c2dffa", 29354986),
    ("windows", "x86_64"): ("ffmpeg-win32-x64.gz",
                            "8883a3dffbd0a16cf4ef95206ea05283f78908dbfb118f73c83f4951dcc06d77", 29581307),
}
EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def own_folder():
    return os.path.join(os.path.expanduser("~"), ".bgcache", "ffmpeg")


def usual_places():
    if os.name == "nt":
        roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        return [os.path.join(r, "ffmpeg", "bin", EXE) for r in roots if r] + \
            [r"C:\ffmpeg\bin\ffmpeg.exe", os.path.join(os.path.expanduser("~"), "scoop", "shims", EXE)]
    return ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", "/opt/local/bin/ffmpeg"]


def find(departments_file_path=None):
    """The ffmpeg to use, or None."""
    for stored in (profile.get("ffmpeg"), departments_file_path, os.path.join(own_folder(), EXE)):
        if stored and os.path.isfile(os.path.expanduser(stored)):
            return os.path.expanduser(stored)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for path in usual_places():
        if os.path.isfile(path):
            return path
    return None


def build_for_this_computer():
    """(file, sha256, size) of the pinned build for this system, or None."""
    system = {"win32": "windows", "darwin": "darwin"}.get(sys.platform, "linux" if sys.platform.startswith("linux")
                                                          else sys.platform)
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return BUILDS.get((system, machine))


def can_download():
    return profile.get("ffmpeg_download") is not False and build_for_this_computer() is not None


def download(progress=None, stop=None, timeout=60.0):
    """Download, check and unpack ffmpeg into ~/.bgcache/ffmpeg/. Returns
    its path. progress(done_bytes, total_bytes); stop() -> True cancels.
    Raises RuntimeError with a plain reason (no internet, checksum wrong,
    cancelled...); nothing is left half-written."""
    if profile.get("ffmpeg_download") is False:
        raise RuntimeError("downloading ffmpeg is switched off here (ask your pipeline team)")
    build = build_for_this_computer()
    if not build:
        raise RuntimeError("no ready-made ffmpeg for this computer (%s %s)" % (sys.platform, platform.machine()))
    name, digest, size = build
    folder = own_folder()
    os.makedirs(folder, exist_ok=True)
    part = os.path.join(folder, name + ".part")
    try:
        _fetch(URL % (BUILD_TAG, name), part, size, digest, progress, stop, timeout)
        exe = os.path.join(folder, EXE)
        tmp = exe + ".new"
        with gzip.open(part, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.chmod(tmp, 0o755)
        os.replace(tmp, exe)
    finally:
        for leftover in (part, os.path.join(folder, EXE + ".new")):
            if os.path.exists(leftover):
                os.remove(leftover)
    if not works(exe):
        os.remove(exe)
        raise RuntimeError("the downloaded ffmpeg doesn't run on this computer")
    return exe


def _fetch(url, path, size, digest, progress, stop, timeout):
    import urllib.request
    sha = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer, open(path, "wb") as out:
            while True:
                if stop and stop():
                    raise RuntimeError("cancelled")
                chunk = answer.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, size)
    except RuntimeError:
        raise
    except Exception as error:       # no internet, proxy, timeout...: said plainly
        raise RuntimeError("couldn't download ffmpeg: %s" % error)
    if sha.hexdigest() != digest:
        raise RuntimeError("the download didn't match the expected file (checksum), so it wasn't used")


def works(exe):
    try:
        result = subprocess.run([exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=20, **common.hidden_console())
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and b"ffmpeg version" in result.stdout
