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
import shutil
import subprocess
import tempfile

from bgcache import common, profile
from bgcache.continuity import names

FRAME_FILE_RE = names.FRAME_RE
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
    """ffmpeg for movies and sound conversion (ffmpeg_get.find: the
    profile's "ffmpeg", the departments_file's "ffmpeg_path", bgcache's own
    downloaded copy, the PATH, the usual folders). Raises if there is none.
    Nothing is written anywhere."""
    from bgcache.continuity import ffmpeg_get
    found = ffmpeg_get.find(_departments_file().get("ffmpeg_path"))
    if found:
        return found
    raise RuntimeError("ffmpeg not found: install it, or set \"ffmpeg\" in the profile "
                       "(bgcache > Set up continuity... can download it)")


# ----------------------------------------------------------------------
# Shot / path resolution
# ----------------------------------------------------------------------
def _version_folders(base_dir, pattern, source_type=None):
    """[(version_number, path)] under base_dir matching pattern, oldest
    first. A version is a folder, or (0.9.0b3) a file with the version in
    its name, kept side by side in one folder: shot_v004.mov, or
    shot_v004.1001.jpg... (path: the movie, or the sequence's first frame).
    0.9.0b4: the version however it's written (names.py: v004, _004,
    take3, a date); a name with no version counts as 0, the newest such
    file or folder winning. A folder wins over a file with the same number."""
    if not os.path.isdir(base_dir):
        return []
    found = {}            # version -> (rank, path); rank: folder 2, file 1; then newer
    for name in sorted(os.listdir(base_dir)):
        full = os.path.join(base_dir, name)
        is_dir = os.path.isdir(full)
        stem = name if is_dir else _versioned_file_stem(name, source_type)
        if not stem or not names.matches(stem, pattern):
            continue
        version = names.version_in(stem, pattern) or 0
        try:
            rank = (2 if is_dir else 1, os.path.getmtime(full) if version == 0 else 0)
        except OSError:
            continue
        if version not in found or rank > found[version][0]:
            found[version] = (rank, full)
    return sorted((v, path) for v, (_rank, path) in found.items())


def _versioned_file_stem(name, source_type):
    """The name of a footage file without frame number and extension, or
    None when the file isn't footage for this department."""
    stem, kind = names.footage_stem(name)
    if stem is None or source_type not in (None, kind):
        return None
    return stem


def _sequence_from_file(first):
    """(first_frame_path, frame_count, first_frame_number) of a sequence
    whose frames sit beside other versions' frames in one folder."""
    folder, name = os.path.split(first)
    stem = name[:FRAME_FILE_RE.search(name).start()]
    frames = sorted(f for f in os.listdir(folder)
                    if FRAME_FILE_RE.search(f) and f[:FRAME_FILE_RE.search(f).start()] == stem)
    return os.path.join(folder, frames[0]), len(frames), _first_frame_number(frames[0])


def _best_version_folder(base_dir, pattern, source_type=None):
    """Return (full_path, version_number) for the highest version under
    base_dir matching pattern, or (None, None)."""
    candidates = _version_folders(base_dir, pattern, source_type)
    if not candidates:
        return None, None
    version_num, folder = candidates[-1]
    return folder, version_num


def list_versions(show, shot, department_name):
    """Version numbers a department has for a shot, newest first."""
    for dept in get_departments():
        if dept["name"] == department_name:
            return [v for v, _folder in reversed(_versions_for(dept, show, shot))]
    return []


def _versions_for(dept, show, shot):
    """[(version, path)] of a department's footage for a shot, oldest first:
    a movie the user dropped on that shot by hand (and its later versions),
    or what Search by shot name found (a department with search_roots), or
    the department's folder."""
    kind = dept.get("source_type")
    by_hand = _by_hand(shot).get(dept["name"])
    if by_hand:
        folder, name = os.path.split(profile._norm(by_hand))
        stem, file_kind = names.footage_stem(name)
        if stem:
            from bgcache.continuity import learn
            return _version_folders(folder, learn.version_pattern(stem)[0], file_kind)
    fields = profile.shot_fields(show, shot)
    try:
        pattern = dept["version_pattern"].format_map(fields)
        if dept.get("search_roots"):
            return _searched(dept, shot, pattern)
        base_dir = profile.fill(dept["base_path"], fields)
    except (KeyError, ValueError) as error:
        print("bgcache: department %r in the profile: unknown field %s" % (dept.get("name"), error))
        return []
    return _version_folders(base_dir, pattern, kind)


def _by_hand(shot):
    """{department: path} the user dropped onto this shot's card."""
    table = profile.get("footage_by_hand") or {}
    for key, value in table.items():
        if key.lower() == (shot or "").lower():
            return value or {}
    return {}


SEARCH_EVERY_S = 120
_index = {"key": None, "time": 0.0, "found": {}}


def _searched(dept, shot, pattern):
    """Search by shot name: every footage file under the department's
    search_roots whose name holds the shot (scanned once, then every 2 min)."""
    from bgcache.continuity import learn
    import time
    roots = [profile._norm(r) for r in dept["search_roots"]]
    key = (tuple(roots), profile.get("shot_pattern"))
    if _index["key"] != key or time.time() - _index["time"] > SEARCH_EVERY_S:
        found = learn.scan(roots, profile.get("shot_pattern")) if profile.get("shot_pattern") else {}
        _index.update(key=key, time=time.time(), found=found)
    best = {}
    for path in _index["found"].get((shot or "").lower(), []):
        stem, kind = names.footage_stem(os.path.basename(path))
        if kind != dept.get("source_type", kind) or not names.matches(stem, pattern):
            continue
        v = names.version_in(stem, pattern) or 0
        try:
            rank = os.path.getmtime(path)
        except OSError:
            continue
        if v not in best or rank > best[v][0]:
            best[v] = (rank, path)
    return sorted((v, path) for v, (_r, path) in best.items())


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
    """Recursively search for the one movie (.mov, .mp4, .m4v) under
    version_folder (handles editorial's extra nesting level the same as
    any other). A movie file itself (a version in its name) is the movie."""
    if os.path.isfile(version_folder):
        return version_folder
    for root, dirs, files in os.walk(version_folder):
        dirs.sort()
        for f in sorted(files):
            if names.is_movie(f):
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
    for dept in candidates:
        found = _versions_for(dept, show, shot)
        if version is not None and department_name is not None:
            folder = dict(found).get(int(version))
            found_version = int(version)
        else:
            found_version, folder = found[-1] if found else (None, None)
        if not folder:
            continue
        if dept["source_type"] == "image_sequence":
            first_frame, nb_frames, start_frame = (_sequence_from_file(folder) if os.path.isfile(folder)
                                                   else _find_sequence_first_frame(folder))
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
    """Shot names in a sequence, in cut order when the profile names an edit
    export (edit_order), else by name."""
    shots = _shots_in_sequence(show, sequence_code)
    edit = profile._norm(profile.get("edit_order") or "")
    if edit and shots:
        from bgcache.continuity import edit_order
        import re
        pattern = profile.get("shot_pattern") or "(?i)(?<![A-Za-z0-9])(?P<shot>%s)(?![A-Za-z0-9])" % \
            "|".join(re.escape(s) for s in shots)
        shots = edit_order.sort_shots(shots, edit, pattern)
    return shots


def _shots_in_sequence(show, sequence_code):
    """From the profile's shot_folder layout (or shots_folder); else the
    shots a Search by shot name found."""
    shots = profile.list_shots(show, sequence_code)
    if shots:
        return shots
    for dept in get_departments():
        if dept.get("search_roots"):
            _searched(dept, "", "*")              # fills the index
            break
    import re
    try:
        rx = re.compile(profile.get("shot_pattern") or "$^")
    except re.error:
        return []
    out = set()
    for paths in _index["found"].values():
        for path in paths:
            m = rx.search(os.path.basename(path))
            if not m:
                continue
            seq = m.groupdict().get("sequence") or profile.sequence_of(m.group("shot"), show)
            if not sequence_code or seq in (None, sequence_code) or (seq or "").lower() == sequence_code.lower():
                out.add(m.group("shot"))
    return sorted(out, key=lambda x: x.lower())
