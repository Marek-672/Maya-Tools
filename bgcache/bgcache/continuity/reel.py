"""Continuity reel for the bgcache player: neighbour shots played before and
after the live shot.

Footage is found with continuity.resolver (departments from the pipeline
profile). Every staged shot, image sequence or movie, is turned once
into JPEGs at the player's resolution and cached under
$TMPDIR/bgcache_reel/<shot>/<dept>_v<version>_<height>p/, so all sources play,
scrub and step exactly like the live frames. Movies need ffmpeg.

Sound: each shot's own sound file (found from the live shot's sound path by
swapping the shot code, newest version), else the movie's sound, else
silence; decoded to the live sound's rate and channels and cut to exactly the
shot's length so cuts stay in sync.

All slow work runs on one background thread (Jobs); results are handed back to
the Qt thread by Jobs.drain().
"""
import glob
import itertools
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

try:
    from PySide6 import QtCore, QtGui
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui

from bgcache import common, profile
from bgcache.continuity import resolver as cr

CACHE_ROOT = os.path.join(tempfile.gettempdir(), "bgcache_reel")
FRAME_NUM_RE = re.compile(r"\.(-?\d+)\.[A-Za-z]+$")


def log(msg):
    print("bgcache reel: %s" % msg)
    sys.stdout.flush()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def parse_shot(path):
    """(show, shot, sequence) of the shot a file is in (profile's shot_folder)."""
    return profile.parse_shot(path)


def ffmpeg():
    try:
        return cr.get_ffmpeg_path()
    except Exception:  # no ffmpeg configured: callers fall back to Qt
        return None


def department_order():
    """Auto's order: the profile's auto_order first, then the other
    departments in their listed order."""
    names = [d["name"] for d in cr.get_departments()]
    first = [n for n in (profile.get("auto_order") or ()) if n in names]
    return first + [n for n in names if n not in first]


def resolve_info(show, shot, department=None, version=None):
    """Footage for a shot: one department (newest, or `version`), or Auto
    (first that has footage)."""
    if department:
        if version is not None:
            return cr.resolve_shot(show, shot, department, version)
        return cr.resolve_shot(show, shot, department)
    for name in department_order():
        info = cr.resolve_shot(show, shot, name)
        if info:
            return info
    return None


def label(info):
    return "%s v%03d" % (info["department"], info["version"]) if info else ""


# --------------------------------------------------------------------------
# Background jobs
# --------------------------------------------------------------------------
class Jobs(object):
    """One worker thread. add(priority, fn, callback): fn(report) runs on the
    thread (report(x) sends progress); callback(kind, value) runs on the Qt
    thread from drain(), kind = "progress" | "done" | "error"."""

    def __init__(self):
        self.q = queue.PriorityQueue()
        self.results = queue.Queue()
        self.count = itertools.count()
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, priority, fn, callback):
        self.q.put((priority, next(self.count), fn, callback))

    def _run(self):
        while True:
            _prio, _n, fn, callback = self.q.get()
            report = lambda value, cb=callback: self.results.put((cb, "progress", value))
            try:
                self.results.put((callback, "done", fn(report)))
            except Exception as error:
                log(traceback.format_exc().rstrip())
                self.results.put((callback, "error", str(error) or error.__class__.__name__))

    def drain(self):
        while True:
            try:
                callback, kind, value = self.results.get_nowait()
            except queue.Empty:
                return
            try:
                callback(kind, value)
            except Exception:
                log(traceback.format_exc().rstrip())


# --------------------------------------------------------------------------
# Resolving and thumbnails (run on the job thread)
# --------------------------------------------------------------------------
def resolve(show, shot, department=None, thumb_size=(168, 60), version=None):
    """(info, thumbnail QImage or None) for a shot."""
    info = resolve_info(show, shot, department, version)
    if not info:
        return None, None
    img = None
    try:
        path = cr.get_thumbnail(shot, info)
        if path:
            img = QtGui.QImage(path)
            if not img.isNull():
                img = img.scaled(thumb_size[0], thumb_size[1], QtCore.Qt.KeepAspectRatio,
                                 QtCore.Qt.SmoothTransformation)
    except Exception as error:
        log("thumbnail for %s: %s" % (shot, error))
    return info, img


KEEP_VERSIONS = 2     # b18: converted versions kept per shot and department


def _older_versions(shot_dir, keep=KEEP_VERSIONS):
    """Converted folders of a shot beyond the newest `keep` versions of each
    department (and size), e.g. P v009 when P v011 and v012 are converted."""
    groups = {}
    for name in os.listdir(shot_dir):
        m = re.match(r"^(.+)_v(\w+?)_(\d+)p$", name)
        if not m:
            continue
        dept, ver, height = m.groups()
        key = int(ver) if ver.isdigit() else -1
        groups.setdefault((dept, height), []).append((key, name))
    out = []
    for items in groups.values():
        items.sort(reverse=True)
        out += [os.path.join(shot_dir, name) for _key, name in items[keep:]]
    return out


def _used_since(path, since):
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            if max(st.st_atime, st.st_mtime) >= since:
                return True
    return False


def prune_cache(max_age_days=14, max_gb=10.0):
    """Keep the continuity cache from growing forever: keep the newest
    KEEP_VERSIONS converted versions per shot and department, then remove
    converted shots not used for max_age_days, then the oldest until it's
    under max_gb."""
    old = 0
    for shot in os.listdir(CACHE_ROOT) if os.path.isdir(CACHE_ROOT) else []:
        shot_dir = os.path.join(CACHE_ROOT, shot)
        if os.path.isdir(shot_dir):
            for path in _older_versions(shot_dir):
                if _used_since(path, time.time() - 86400):
                    continue              # used today (a pinned older version, say): keep it
                shutil.rmtree(path, ignore_errors=True)
                old += 1
    if old:
        log("continuity cache: removed %d older converted version(s) (the newest %d per department are kept)"
            % (old, KEEP_VERSIONS))
    entries = []
    for shot in os.listdir(CACHE_ROOT) if os.path.isdir(CACHE_ROOT) else []:
        for name in os.listdir(os.path.join(CACHE_ROOT, shot)):
            path = os.path.join(CACHE_ROOT, shot, name)
            size, newest = 0, os.path.getmtime(path)
            for root, _dirs, files in os.walk(path):
                for f in files:
                    try:
                        st = os.stat(os.path.join(root, f))
                    except OSError:
                        continue
                    size += st.st_size
                    newest = max(newest, st.st_atime, st.st_mtime)
            entries.append([newest, size, path])
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for newest, size, path in sorted(entries):
        total = sum(e[1] for e in entries if e[2] is not None)
        if newest < cutoff or total > max_gb * 1024 ** 3:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
            for e in entries:
                if e[2] == path:
                    e[1], e[2] = 0, None
    if removed:
        log("continuity cache: removed %d old converted shot(s)" % removed)
    return removed


# --------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------
def cache_dir(shot, info, height):
    return os.path.join(CACHE_ROOT, shot, "%s_v%s_%dp" % (info["department"], info["version"], height))


def _cached_frames(folder):
    files = glob.glob(os.path.join(folder, "f.*.jpg"))
    return sorted(files, key=lambda f: int(FRAME_NUM_RE.search(f).group(1)))


def shot_length(show, shot):
    """The shot's frame count from an image-sequence department (P, WP),
    which carries real frame numbers; None if there's none."""
    try:
        for dept in cr.get_departments():
            if dept.get("source_type") != "image_sequence":
                continue
            found = cr.resolve_shot(show, shot, dept["name"])
            if found and found.get("frame_count"):
                return int(found["frame_count"])
    except Exception:  # frame count is optional: the movie's own length is used
        pass
    return None


def movie_skip(info, n_frames):
    """Frames to skip at the start of a department movie: its slate
    (profile: movie_slate_frames). A movie exactly that much longer than the
    shot skips them; the same length skips nothing. With no image sequence to
    compare against, the profile's assume_slate_when_unknown decides."""
    slate = int(profile.get("movie_slate_frames") or 0)
    if not slate or not info or info.get("source_type") != "single_movie":
        return 0
    ids = parse_shot(info.get("source_path") or "")
    length = shot_length(ids[0], ids[1]) if ids else None
    if length:
        return slate if n_frames == length + slate else 0
    return slate if profile.get("assume_slate_when_unknown") and n_frames > slate else 0


def source_stamp(info):
    """What the footage file looks like now (date and size; for an image
    sequence its folder's newest date and frame count): a version
    re-published under the same name changes it."""
    path = info.get("source_path") or ""
    try:
        if info.get("source_type") == "image_sequence":
            folder = os.path.dirname(path)
            names = [n for n in os.listdir(folder) if cr.FRAME_FILE_RE.search(n)]
            newest = max([os.path.getmtime(os.path.join(folder, n)) for n in names] or [0])
            return [round(newest, 1), len(names)]
        return [round(os.path.getmtime(path), 1), os.path.getsize(path)]
    except (OSError, ValueError):
        return None


def footage_changed(shot, info, height):
    """True if the cached frames were made from an older copy of the file."""
    try:
        with open(os.path.join(cache_dir(shot, info, height), "done.json")) as handle:
            made = json.load(handle).get("stamp")
    except (IOError, OSError, ValueError):
        return False
    now = source_stamp(info)
    return bool(made and now and made != now)


def forget(shot, info=None):
    """Drop the converted frames (and movie sound) of one shot's version, or
    of the whole shot, so they're made again from the file."""
    root = os.path.join(CACHE_ROOT, shot)
    prefix = "%s_v%s_" % (info["department"], info["version"]) if info else ""
    for name in (os.listdir(root) if os.path.isdir(root) else []):
        if name.startswith(prefix):
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)


def prepare_frames(shot, info, height, report):
    """JPEGs of the shot at the player's height, cached. Returns frame paths.
    Made again when the file itself has changed (same version re-published)."""
    out = cache_dir(shot, info, height)
    done = os.path.join(out, "done.json")
    if os.path.isfile(done) and not footage_changed(shot, info, height):
        frames = _cached_frames(out)
        if frames:
            return frames
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    if info["source_type"] == "image_sequence":
        src = os.path.dirname(info["source_path"])
        files = [f for f in os.listdir(src) if cr.FRAME_FILE_RE.search(f)]
        files.sort(key=lambda f: int(FRAME_NUM_RE.search(f).group(1)))
        if not files:
            raise RuntimeError("no frames in %s" % src)
        for i, name in enumerate(files):
            img = QtGui.QImage(os.path.join(src, name))
            if img.isNull():
                raise RuntimeError("unreadable frame %s" % name)
            if img.height() > height:
                img = img.scaledToHeight(height, QtCore.Qt.SmoothTransformation)
            if not img.save(os.path.join(out, "f.%d.jpg" % (i + 1)), "JPG", 85):
                raise RuntimeError("could not write %s" % out)
            if i % 8 == 0:
                report((i + 1) / float(len(files)))
    else:
        exe = ffmpeg()
        if not exe:
            raise RuntimeError("ffmpeg not found (needed for movies)")
        cmd = [exe, "-y", "-v", "error", "-i", info["source_path"],
               "-vf", "scale=-2:%d" % height, "-q:v", "3", "-start_number", "1",
               os.path.join(out, "f.%d.jpg")]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                **common.hidden_console())
        while proc.poll() is None:
            time.sleep(0.5)
            report(len(glob.glob(os.path.join(out, "f.*.jpg"))))
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg failed: %s" % err.strip()[-300:])
    frames = _cached_frames(out)
    if not frames:
        raise RuntimeError("no frames came out")
    with open(done, "w") as handle:
        json.dump({"source": info["source_path"], "frames": len(frames),
                   "stamp": source_stamp(info)}, handle)
    return frames


def shot_frames(shot, info, height, report):
    """(frames of the shot itself, slate frames skipped): prepare_frames
    without a movie's slate."""
    frames = prepare_frames(shot, info, height, report)
    skip = movie_skip(info, len(frames))
    return frames[skip:], skip


def prepare_full(shot, info, report):
    """Full-resolution frames for a Maya image plane: (first file, its frame
    number). Image sequences are used straight from disk; movies are
    converted once (ref.0001.jpg...) and cached."""
    if info["source_type"] == "image_sequence":
        first = info["source_path"]
        m = FRAME_NUM_RE.search(first)
        return first, int(m.group(1)) if m else (info.get("start_frame") or 1)
    out = os.path.join(CACHE_ROOT, shot, "%s_v%s_full" % (info["department"], info["version"]))
    first = os.path.join(out, "ref.0001.jpg")
    if os.path.isfile(os.path.join(out, "done.json")) and os.path.isfile(first):
        return _full_start(out, info)
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg not found (needed for movies)")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    proc = subprocess.Popen([exe, "-y", "-v", "error", "-i", info["source_path"], "-q:v", "2",
                             "-start_number", "1", os.path.join(out, "ref.%04d.jpg")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **common.hidden_console())
    while proc.poll() is None:
        time.sleep(0.5)
        report(len(glob.glob(os.path.join(out, "ref.*.jpg"))))
    if proc.returncode != 0 or not os.path.isfile(first):
        raise RuntimeError("ffmpeg failed: %s" % proc.stderr.read().decode("utf-8", "replace").strip()[-300:])
    with open(os.path.join(out, "done.json"), "w") as handle:
        json.dump({"source": info["source_path"]}, handle)
    return _full_start(out, info)


def _full_start(out, info):
    """(first file of the shot, its number): past the movie's slate."""
    n = len(glob.glob(os.path.join(out, "ref.*.jpg")))
    first = 1 + movie_skip(info, n)
    return os.path.join(out, "ref.%04d.jpg" % first), first


# --------------------------------------------------------------------------
# Sound
# --------------------------------------------------------------------------
def audio_template(live_path, live_shot):
    """From the live shot's sound path, the folder and version pattern to look
    for in other shots, e.g. ('/projects/BIRDS/sq010_0040/sound', 'SND_sq010_0040_v*')."""
    if not live_path or not live_shot or live_shot not in live_path:
        return None
    version_dir = os.path.dirname(live_path)
    pattern = re.sub(r"_v\d+$", "_v*", os.path.basename(version_dir))
    if pattern == os.path.basename(version_dir):
        return None
    return os.path.dirname(version_dir), pattern


def find_shot_audio(template, live_shot, shot):
    if not template:
        return None
    base, pattern = template
    folder, _version = cr._best_version_folder(base.replace(live_shot, shot),
                                               pattern.replace(live_shot, shot))
    if not folder:
        return None
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if name.lower().endswith((".aif", ".aiff", ".aifc", ".wav")):
                return os.path.join(root, name)
    return None


def decode_audio(path, rate, channels):
    """16-bit PCM at the given rate/channels, or None."""
    exe = ffmpeg()
    if exe:
        result = subprocess.run([exe, "-v", "error", "-i", path, "-vn", "-f", "s16le",
                                 "-acodec", "pcm_s16le", "-ar", str(rate), "-ac", str(channels), "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **common.hidden_console())
        return result.stdout if result.returncode == 0 and result.stdout else None
    from bgcache import audio   # no ffmpeg: our own reader, if the rate already matches
    try:
        pcm, src_channels, src_rate = audio.read_file(path)
    except Exception:  # unreadable sound: the shot plays silent
        return None
    if src_rate != rate:
        log("%s is %d Hz, needs %d Hz: install ffmpeg to convert" % (path, src_rate, rate))
        return None
    return audio.convert_channels(pcm, src_channels, channels)


def prepare_audio(shot, info, frames, fps, sound_args, skip=0):
    """(pcm exactly `frames` long, where it came from). skip: slate frames
    at the start of the movie (dropped from the movie's own sound)."""
    from bgcache import audio
    template, live_shot, rate, channels = sound_args
    pcm, source = None, None
    path = find_shot_audio(template, live_shot, shot)
    if path:
        pcm, source = decode_audio(path, rate, channels), path
    if pcm is None and info["source_type"] == "single_movie" and ffmpeg():
        pcm, source = decode_audio(info["source_path"], rate, channels), "movie"
        if pcm and skip:
            cut = int(round(skip * rate / float(fps))) * channels * 2
            pcm = pcm[cut:]
    if pcm is None:
        source = None
    return audio.fit(pcm, frames, fps, rate, channels), source


def prepare_shot(show, shot, info, department, height, fps, sound_args, report):
    """Everything the player needs to play a staged shot."""
    if info is None:
        info = resolve_info(show, shot, department)
        if not info:
            raise RuntimeError("no footage found")
    frames, skip = shot_frames(shot, info, height, report)
    pcm, source = prepare_audio(shot, info, len(frames), fps, sound_args, skip)
    log("%s ready: %s, %d frames%s, sound: %s" % (shot, label(info), len(frames),
                                                   " (slate skipped)" if skip else "", source or "none"))
    first = info.get("start_frame") or 1
    return {"info": info, "frames": frames, "pcm": pcm, "sound": source, "first": first}
