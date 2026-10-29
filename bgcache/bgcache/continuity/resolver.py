"""Footage lookup for the continuity strip: which department's footage a
shot has, and where it is. No Maya and no Qt here.

Departments come from the pipeline profile (bgcache/profile.py): its
"departments" list, or the "departments" list of its "departments_file"
(a JSON file shared with another tool; bgcache only reads it).

    resolve_shot(show, shot, department_name=None): newest version of a
        department's footage for a shot (or of the first department that
        has some, in the listed order).
    list_shots_in_sequence(show, sequence): the sequence's shot names.
    get_thumbnail(shot, info): a still image for a resolved shot: the first
        frame of an image sequence, or a cached ffmpeg grab of a movie.

Image sequences keep their production frame numbers (they don't start at 1).
"""

import os
import re
import json
import fnmatch
import shutil
import subprocess
import tempfile

from bgcache import common, profile

VERSION_RE = re.compile(r"_v(\d+)$")
FRAME_FILE_RE = re.compile(r"\.\d+\.(jpg|jpeg|png|tif|tiff|exr)$", re.IGNORECASE)
THUMB_CACHE_DIR = os.path.join(tempfile.gettempdir(), "bgcache_thumbs")


# ----------------------------------------------------------------------
# Departments (from the pipeline profile)
# ----------------------------------------------------------------------
def _departments_file():
    """The profile's departments_file, read only; {} if none or unreadable."""
    path = profile.get("departments_file")
    if not path:
        return {}
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def get_departments():
    """The departments, in their listed order: the departments_file's list
    if it has one, otherwise the profile's own."""
    return _departments_file().get("departments") or profile.get("departments") or []


def get_ffmpeg_path():
    """ffmpeg for movies and sound conversion: the profile's "ffmpeg", the
    departments_file's "ffmpeg_path", or the one on the PATH. Raises if
    there is none. Nothing is written anywhere."""
    for stored in (profile.get("ffmpeg"), _departments_file().get("ffmpeg_path")):
        if stored and os.path.isfile(os.path.expanduser(stored)):
            return os.path.expanduser(stored)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg not found: install it, or set \"ffmpeg\" in the profile")


# ----------------------------------------------------------------------
# Shot / path resolution
# ----------------------------------------------------------------------
def _version_folders(base_dir, pattern):
    """[(version_number, full_path)] of the _vNNN folders under base_dir
    matching pattern, oldest first."""
    if not os.path.isdir(base_dir):
        return []
    candidates = []
    for name in os.listdir(base_dir):
        full = os.path.join(base_dir, name)
        if not os.path.isdir(full):
            continue
        if not fnmatch.fnmatch(name, pattern):
            continue
        m = VERSION_RE.search(name)
        if not m:
            continue
        candidates.append((int(m.group(1)), full))
    candidates.sort(key=lambda c: c[0])
    return candidates


def _best_version_folder(base_dir, pattern):
    """Return (full_path, version_number) for the highest _vNNN folder
    under base_dir matching pattern, or (None, None)."""
    candidates = _version_folders(base_dir, pattern)
    if not candidates:
        return None, None
    version_num, folder = candidates[-1]
    return folder, version_num


def _dept_place(show, shot, dept):
    fields = profile.shot_fields(show, shot)
    return profile.fill(dept["base_path"], fields), dept["version_pattern"].format_map(fields)


def list_versions(show, shot, department_name):
    """Version numbers a department has for a shot, newest first."""
    for dept in get_departments():
        if dept["name"] != department_name:
            continue
        try:
            base_dir, pattern = _dept_place(show, shot, dept)
        except (KeyError, ValueError):
            return []
        return [v for v, _folder in reversed(_version_folders(base_dir, pattern))]
    return []


def _first_frame_number(filename):
    """Pull the zero-padded frame number out of a sequence filename,
    e.g. 'sq010_0040_anim_v009.1001.jpg' -> 1001. These sequences keep
    native production numbering -- never assume they start at 1."""
    m = re.search(r"\.(\d+)\.[A-Za-z]+$", filename)
    return int(m.group(1)) if m else 1


def _find_sequence_first_frame(version_folder):
    """Look for a resolution subfolder (or frames directly in the
    version folder) and return (first_frame_path, frame_count,
    first_frame_number)."""
    try:
        entries = sorted(os.listdir(version_folder))
    except OSError:
        return None, 0, 1
    for entry in entries:
        sub = os.path.join(version_folder, entry)
        if os.path.isdir(sub):
            frames = sorted(f for f in os.listdir(sub) if FRAME_FILE_RE.search(f))
            if frames:
                return os.path.join(sub, frames[0]), len(frames), _first_frame_number(frames[0])
    frames = sorted(f for f in entries if FRAME_FILE_RE.search(f))
    if frames:
        return os.path.join(version_folder, frames[0]), len(frames), _first_frame_number(frames[0])
    return None, 0, 1


def _find_single_movie(version_folder):
    """Recursively search for the one .mov file under version_folder
    (handles editorial's extra nesting level the same as any other)."""
    for root, _dirs, files in os.walk(version_folder):
        for f in files:
            if f.lower().endswith(".mov"):
                return os.path.join(root, f)
    return None


def resolve_shot(show, shot, department_name=None, version=None):
    """Resolve a shot to a department/version. If department_name is
    given, only that department is tried; otherwise departments are
    tried in their configured priority order. Returns a dict or None.

    image_sequence departments: 'source_path'/'thumbnail_path' point
    directly at the first frame on disk (no extra work needed),
    'frame_count' is authoritative (counted from actual files present),
    'start_frame' is the real on-disk starting frame number.

    single_movie departments: 'source_path' is the .mov file,
    'thumbnail_path' is None (see get_thumbnail), 'frame_count' and
    'start_frame' are None -- a player would typically query the movie
    file's own duration/frame count through whatever media APIs it
    already has, rather than this module needing to know that.

    version (with department_name): that exact version instead of the newest.
    """
    departments = get_departments()
    candidates = departments if department_name is None else [
        d for d in departments if d["name"] == department_name
    ]
    fields = profile.shot_fields(show, shot)
    for dept in candidates:
        try:
            base_dir = profile.fill(dept["base_path"], fields)
            pattern = dept["version_pattern"].format_map(fields)
        except (KeyError, ValueError) as error:
            print("bgcache: department %r in the profile: unknown field %s" % (dept.get("name"), error))
            continue
        if version is not None and department_name is not None:
            folder = dict(_version_folders(base_dir, pattern)).get(int(version))
            found_version = int(version)
        else:
            folder, found_version = _best_version_folder(base_dir, pattern)
        if not folder:
            continue
        if dept["source_type"] == "image_sequence":
            first_frame, nb_frames, start_frame = _find_sequence_first_frame(folder)
            if not first_frame:
                continue
            return {
                "department": dept["name"], "version": found_version,
                "source_type": "image_sequence", "source_path": first_frame,
                "thumbnail_path": first_frame, "frame_count": nb_frames,
                "start_frame": start_frame,
            }
        else:
            movie = _find_single_movie(folder)
            if not movie:
                continue
            return {
                "department": dept["name"], "version": found_version,
                "source_type": "single_movie", "source_path": movie,
                "thumbnail_path": None, "frame_count": None, "start_frame": None,
            }
    return None


def get_thumbnail(shot, info, ffmpeg_path=None):
    """Return a displayable still-image path for a resolved shot.
    Image-sequence departments already have one (their own first frame,
    returned as-is). Movie departments get a one-off ffmpeg frame-grab,
    cached to a temp file keyed by shot/department/version so repeat
    calls don't re-run ffmpeg. Mutates info['thumbnail_path'] as a cache.
    """
    if info["thumbnail_path"]:
        return info["thumbnail_path"]
    if info["source_type"] != "single_movie":
        return None
    if ffmpeg_path is None:
        ffmpeg_path = get_ffmpeg_path()
    cache_dir = os.path.join(THUMB_CACHE_DIR, shot, f"{info['department']}_v{info['version']}")
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(cache_dir, "thumb.jpg")
    try:
        subprocess.check_call(
            [ffmpeg_path, "-y", "-i", info["source_path"], "-frames:v", "1", "-q:v", "4", out_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **common.hidden_console()
        )
    except Exception:  # no thumbnail: the card shows its name only
        return None
    info["thumbnail_path"] = out_path
    return out_path


def list_shots_in_sequence(show, sequence_code):
    """Shot names in a sequence, from the profile's shot_folder layout."""
    return profile.list_shots(show, sequence_code)
