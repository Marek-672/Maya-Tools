"""Shared helpers: session folders, atomic JSON files, and the message queue.

No Maya imports here, so the standalone player can use this module too.

Session folder layout:
    config.json   written by the controller at start (incl. camera list, sound)
    cameras.json  written by the player: which cameras to cache, which one is viewed
    player_time.json / maya_time.json   current frame, for player <-> Maya time sync
    status.json   written by the worker (per camera: dirty frames, versions; state)
    inbox/        controller -> worker messages, one JSON file each
    frames/<cam>/ finished frames per camera, f.<frame>.jpg
    tmp/          playblast scratch space
    worker.log    worker log
"""
import glob
import hashlib
import json
import os
import re
import tempfile
import time

from bgcache import system

_user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
ROOT = os.environ.get("BGCACHE_ROOT") or os.path.join(
    tempfile.gettempdir(), "maya_bgcache_" + _user
)

FRAME_NAME = "f.%d.jpg"

# Logs live outside the temp folder, so they survive a crash, a logout or a
# temp clean-up: ~/.bgcache/logs/<session>/ (worker.log, player.log, trace.log).
LOG_ROOT = os.environ.get("BGCACHE_LOGS") or os.path.join(os.path.expanduser("~"), ".bgcache", "logs")
KEEP_LOGS = 15


def new_session():
    base = os.path.join(ROOT, "%s_%d" % (time.strftime("%Y%m%d_%H%M%S"), os.getpid()))
    path, n = base, 1
    while os.path.exists(path):          # Stop and Start within the same second
        n += 1
        path = "%s_%d" % (base, n)
    for sub in ("inbox", "frames", "tmp"):
        os.makedirs(os.path.join(path, sub))
    try:
        os.makedirs(log_dir(path), exist_ok=True)
        _prune_logs()
    except OSError:
        pass
    return path


def remove_session(session):
    """Delete a session's working files (scene copies, cached frames). Its
    logs live in ~/.bgcache/logs and are kept. On Windows a file another
    program still has open can't be deleted: try again briefly; anything
    left is swept at the next Start (prune_sessions)."""
    import shutil
    if session and os.path.dirname(os.path.abspath(session)) == os.path.abspath(ROOT):
        for attempt in range(3):
            shutil.rmtree(session, ignore_errors=True)
            if not os.path.exists(session):
                return
            time.sleep(0.2)


def prune_sessions(keep=None):
    """Remove leftover session folders (from crashes or older versions) whose
    Maya is no longer running. Returns how many were removed."""
    removed = 0
    try:
        names = os.listdir(ROOT)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path) or (keep and os.path.abspath(path) == os.path.abspath(keep)):
            continue
        cfg = read_json(os.path.join(path, "config.json")) or {}
        if cfg.get("controller_pid") and pid_alive(cfg["controller_pid"]):
            continue                      # another Maya of yours is using it
        remove_session(path)
        removed += 1
    return removed


def log_dir(session):
    return os.path.join(LOG_ROOT, os.path.basename(session.rstrip("/")))


def _prune_logs():
    """Keep the newest KEEP_LOGS sessions' logs."""
    try:
        dirs = sorted((os.path.join(LOG_ROOT, d) for d in os.listdir(LOG_ROOT)), key=os.path.getmtime)
    except OSError:
        return
    import shutil
    for old in dirs[:-KEEP_LOGS]:
        shutil.rmtree(old, ignore_errors=True)


def paths(session):
    return {
        "session": session,
        "inbox": os.path.join(session, "inbox"),
        "frames": os.path.join(session, "frames"),
        "tmp": os.path.join(session, "tmp"),
        "config": os.path.join(session, "config.json"),
        "cameras": os.path.join(session, "cameras.json"),
        "player_time": os.path.join(session, "player_time.json"),
        "player_cmd": os.path.join(session, "player_cmd.json"),
        "maya_time": os.path.join(session, "maya_time.json"),
        "status": os.path.join(session, "status.json"),
        "logs": log_dir(session),
        "log": os.path.join(log_dir(session), "worker.log"),
        "player_log": os.path.join(log_dir(session), "player.log"),
        "trace": os.path.join(log_dir(session), "trace.log"),
    }


def camera_key(camera):
    """Folder-safe, unique name for a camera's DAG path."""
    short = re.sub(r"[^A-Za-z0-9]+", "_", camera.split("|")[-1]).strip("_") or "cam"
    return "%s_%s" % (short, hashlib.md5(camera.encode("utf-8")).hexdigest()[:6])


def frames_dir(session, camera):
    return os.path.join(session, "frames", camera_key(camera))


def frame_path(session, frame, camera):
    return os.path.join(frames_dir(session, camera), FRAME_NAME % frame)


def write_json_atomic(path, data):
    """Write to a temp file and rename, so readers never see a half-written file."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as handle:
        json.dump(data, handle)
    try:
        system.retrying(lambda: os.replace(tmp, path))
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _read(path):
    with open(path) as handle:
        return json.load(handle)


# What Maya prints when the graphics card runs out of memory for GPU
# deformers (OpenCL) or drawing (seen at the studio: CL_OUT_OF_RESOURCES on a
# shared 16 GB virtual GPU with three Mayas open).
GPU_TROUBLE_RE = re.compile(r"CL_OUT_OF_RESOURCES|CL_MEM_OBJECT_ALLOCATION_FAILURE|CL_OUT_OF_HOST_MEMORY"
                            r"|OpenCL error|out of (?:video|GPU|graphics) memory", re.IGNORECASE)


def read_new(path, pos, limit=1 << 20):
    """(text appended to `path` since byte `pos`, new pos). A file that got
    shorter (replaced) is read from the start; at most `limit` bytes."""
    try:
        size = os.path.getsize(path)
        if size < pos:
            pos = 0
        if size == pos:
            return "", pos
        with open(path, "rb") as handle:
            handle.seek(max(pos, size - limit))
            data = handle.read()
        return data.decode("utf-8", "replace"), size
    except OSError:
        return "", pos


def read_json(path, default=None):
    try:
        return system.retrying(lambda: _read(path))
    except (IOError, OSError, ValueError):
        return default


_seq = [0]


def post_message(session, msg):
    """Drop a message into the worker's inbox."""
    _seq[0] += 1
    name = "%.6f_%06d.json" % (time.time(), _seq[0])
    write_json_atomic(os.path.join(session, "inbox", name), msg)


def take_messages(session):
    """Read and remove all waiting messages, oldest first."""
    out = []
    for path in sorted(glob.glob(os.path.join(session, "inbox", "*.json"))):
        msg = read_json(path)
        try:
            os.remove(path)
        except OSError:
            pass
        if msg is not None:
            out.append(msg)
    return out


def hidden_console():
    """subprocess options so console programs open no window (Windows)."""
    return system.hidden_console()


def merge_ranges(ranges):
    """Merge overlapping or touching inclusive [a, b] frame ranges."""
    out = []
    for a, b in sorted((int(a), int(b)) for a, b in ranges):
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def pid_alive(pid):
    """True if the process exists (per system: bgcache/system/)."""
    return system.pid_alive(pid)


# --------------------------------------------------------------------------
# Personal settings shared by the controller and player (~/.bgcache_player.json)
# --------------------------------------------------------------------------
PREFS_PATH = os.path.join(os.path.expanduser("~"), ".bgcache_player.json")


def load_prefs():
    try:
        with open(PREFS_PATH) as handle:
            return json.load(handle)
    except (IOError, OSError, ValueError):
        return {}


def save_prefs(prefs):
    tmp = "%s.%d.tmp" % (PREFS_PATH, os.getpid())
    try:
        with open(tmp, "w") as handle:
            json.dump(prefs, handle, indent=1)
        os.replace(tmp, PREFS_PATH)
    except (IOError, OSError):
        pass
