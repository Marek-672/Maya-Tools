"""The setup wizard's learning core (0.9.0b4): paths in, settings out.

bgcache learns a production's footage layout from one movie (or the first
image of a sequence) the user points at, compared with the open scene:

    learn(movie, scene) -> a Layout (a dict):
        shot, sequence       the shot code and its sequence, as found
        shot_folder          template of the shot's folder, or "" (footage
                             lives outside shot folders)
        shot_pattern         regex that finds the shot (and sequence) in any
                             file name: how a scene saved anywhere is placed
        shots_folder         where the sequence's shots are listed when there
                             are no shot folders
        departments          [{name, base_path, version_pattern, source_type,
                               example, ...}] the profile's own format
        shots                the sequence's shots found next to this one
        notes                [(level, text)]: "ok" / "guess" / "problem"
        chips                the example path, part by part, with what each
                             part was read as (for the wizard's picture)
    to_profile(layout) -> the profile keys to save.
    scan(roots, ...) -> {shot: [footage paths]}: Search by shot name (way B).

It never walks a whole show: one level around the example, a few
neighbours, and scans only where the user points. Paths use forward
slashes, as in profiles. No Maya or Qt here; every function is plain Python
so it can be tested on made-up folder trees (tests/test_learn.py).
"""
import os
import re
import time

from bgcache.continuity import names

MAX_SIDEWAYS = 60          # folders looked into beside the example
MAX_DEPTH = 4              # how deep inside one of them
MAX_SCAN = 200000          # entries a Search by shot name looks at, at most
VERSION_WORD = re.compile(r"^(v|ver|version|take|tk|rev|r)\d+$", re.IGNORECASE)
DATE_RE = re.compile(r"^(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})$")
SHAPE_DIGITS = re.compile(r"\d+")
BOUND_L, BOUND_R = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"


# ------------------------------------------------------------------ paths
def norm(path):
    return (path or "").replace("\\", "/").rstrip("/")


def parts_of(path):
    return norm(path).split("/")


def join(parts):
    return "/".join(parts)


def _token_re(code):
    return re.compile(BOUND_L + re.escape(code) + BOUND_R, re.IGNORECASE)


def has_token(text, code):
    return bool(code) and bool(_token_re(code).search(text or ""))


# ------------------------------------------------------------- shot codes
def _runs(text):
    """Shot-code candidates in one name: runs of 1-3 chunks joined by one
    separator, each chunk holding a digit, none of them a version word."""
    chunks = [(m.start(), m.end(), m.group()) for m in re.finditer(r"[A-Za-z0-9]+", text)]
    out = set()
    for i in range(len(chunks)):
        for j in range(i, min(i + 3, len(chunks))):
            run = chunks[i:j + 1]
            if any(not re.search(r"\d", c[2]) or VERSION_WORD.match(c[2]) or DATE_RE.match(c[2])
                   for c in run):
                break
            if any(run[k + 1][0] - run[k][1] != 1 or text[run[k][1]] not in "_-. "
                   for k in range(len(run) - 1)):
                break
            code = text[run[0][0]:run[-1][1]]
            if DATE_RE.match(code) or re.match(r"^\d+x\d+$", code, re.I):
                continue                  # a date or a resolution, never a shot
            out.add(code)
    return out


def shot_code(movie, scene=None, known=None):
    """(shot, shot folder index in the movie's path or None, why). known: a
    shot code the user typed. Prefers the deepest folder named like a shot
    that the file name or scene also mentions; else the longest code in the
    file name (that the scene shares, when there is a scene)."""
    parts = parts_of(movie)
    stem = names.footage_stem(parts[-1])[0] or os.path.splitext(parts[-1])[0]
    if known:
        for i in range(len(parts) - 2, -1, -1):
            if parts[i].lower() == known.lower():
                return parts[i], i, "the shot you named"
        return known, None, "the shot you named"
    scene_text = norm(scene)
    for i in range(len(parts) - 2, 0, -1):
        folder = parts[i]
        if folder not in _runs(folder) or VERSION_WORD.match(folder):
            continue
        longer = [c for c in _runs(stem) if len(c) > len(folder) and c.lower().startswith(folder.lower())]
        if longer and not any(parts[k].lower() == longer[0].lower() for k in range(len(parts))):
            continue                      # the sequence's folder (sq01 for sq01_sh020 files)
        if has_token(stem, folder) or (scene_text and has_token(scene_text.rsplit("/", 1)[-1], folder)):
            return folder, i, "a folder named like the shot"
    found = sorted(_runs(stem), key=len, reverse=True)
    if scene_text:
        shared = [c for c in found if has_token(scene_text, c)]
        if shared:
            return shared[0], None, "in both the movie's and the scene's names"
        return None, None, "the movie and the scene don't share a shot name"
    if found:
        return found[0], None, "the longest shot-like name in the file name"
    return None, None, "no shot-like name in the file name"


def shape(code):
    """A regex for codes shaped like this one: sq010_0040 -> sq\\d+_\\d+."""
    pieces, pos = [], 0
    for m in SHAPE_DIGITS.finditer(code):
        pieces.append(re.escape(code[pos:m.start()]))
        pieces.append(r"\d+")
        pos = m.end()
    pieces.append(re.escape(code[pos:]))
    return "".join(pieces)


def _sequence(parts, shot, shot_index):
    """(sequence, its folder index or None)."""
    top = shot_index if shot_index is not None else len(parts) - 1
    for i in range(top - 1, 0, -1):
        folder = parts[i]
        if folder.lower() == shot.lower():
            continue
        if folder in _runs(folder) and (shot.lower().startswith(folder.lower())
                                        or (shot_index is not None and i == shot_index - 1)):
            return folder, i
    m = re.match(r"^([A-Za-z0-9]+)[_\-.]", shot)
    return (m.group(1), None) if m else (None, None)


# -------------------------------------------------------------- templates
def template(text, shot, sequence):
    """A name with the shot and sequence swapped for {shot} / {sequence}."""
    out = _token_re(shot).sub("{shot}", text) if shot else text
    if sequence and sequence.lower() != (shot or "").lower():
        out = _token_re(sequence).sub("{sequence}", out)
    return out


def version_pattern(name):
    """(pattern, how) for a templated name: its version swapped for *, or
    (name, None) when it has none. how: "v" (v004, take3...), "number"
    (_003, 001) or "date"."""
    for m in reversed(list(re.finditer(r"(?<![A-Za-z0-9])(v|ver|version|take|tk|rev)(\d+)(?![0-9])",
                                        name, re.IGNORECASE))):
        if "{" not in name[max(0, m.start() - 1):m.end()]:
            return name[:m.start(2)] + "*" + name[m.end(2):], "v"
    m = re.search(r"(?<![A-Za-z0-9}])(\d{4}[-_.]?\d{2}[-_.]?\d{2})(?![0-9])", name)
    if m and DATE_RE.match(m.group(1)):
        return name[:m.start(1)] + "*" + name[m.end(1):], "date"
    m = re.search(r"(?:^|[_\-. ])(\d+)$", name)
    if m:
        return name[:m.start(1)] + "*", "number"
    return name, None


def shot_pattern(stem_template, shot, sequence):
    """The regex that finds the shot in a file name, from how the example's
    name holds it ({sequence}_{shot} together, or {shot} alone)."""
    seq_re = "(?P<sequence>%s)" % shape(sequence) if sequence else None
    m = re.search(r"\{sequence\}([_\-. ]?)\{shot\}", stem_template)
    if m and seq_re:
        body = "%s%s(?P<shot>%s)" % (seq_re, re.escape(m.group(1)), shape(shot))
    elif sequence and shot.lower().startswith(sequence.lower()) and len(shot) > len(sequence):
        body = "(?P<shot>%s%s)" % (seq_re, shape(shot[len(sequence):]))
    else:
        body = "(?P<shot>%s)" % shape(shot)
    return "(?i)" + BOUND_L + body + BOUND_R


# --------------------------------------------------------------- footage
def _footage_in(folder, depth=MAX_DEPTH, budget=None):
    """The newest-looking footage file under folder (a movie, or a
    sequence's first frame), or None. Looks at most `budget` entries."""
    budget = budget if budget is not None else [400]
    try:
        entries = sorted(os.listdir(folder), reverse=True)     # v010 before v009
    except OSError:
        return None
    budget[0] -= len(entries)
    frames = sorted(e for e in entries if names.is_frame(e))
    movies = [e for e in entries if names.is_movie(e)]
    if movies:
        return join([norm(folder), movies[0]])
    if frames:
        return join([norm(folder), frames[0]])
    if depth <= 0:
        return None
    for e in entries:
        if budget[0] <= 0:
            return None
        sub = os.path.join(folder, e)
        if os.path.isdir(sub) and not e.startswith("."):
            found = _footage_in(sub, depth - 1, budget)
            if found:
                return found
    return None


def department(example, anchor, shot, sequence):
    """One department learned from an example footage path. anchor: index
    of the last folder that isn't the department's own (the shot folder,
    or for footage outside shot folders, the folder above the versions)."""
    parts = parts_of(example)
    stem, kind = names.footage_stem(parts[-1])
    folders = [template(p, shot, sequence) for p in parts[:-1]]
    below = folders[anchor + 1:]
    stem_t = template(stem, shot, sequence)
    notes = []
    vfolder = None
    for j in range(len(below) - 1, -1, -1):
        pat, how = version_pattern(below[j])
        if how and ("{shot}" in below[j] or how in ("v", "date") or below[j].isdigit()):
            vfolder = j
            break
    if vfolder is not None:
        pattern, how = version_pattern(below[vfolder])
        dept_folders = below[:vfolder]
        unit = "folder"
    else:
        pattern, how = version_pattern(stem_t)
        dept_folders = below
        unit = "file"
        if kind == "image_sequence" and dept_folders and not version_pattern(dept_folders[-1])[1] \
                and re.match(r"^(\d+x\d+|frames|images|jpg|png|exr|tif)$", dept_folders[-1], re.I):
            notes.append(("guess", "frames are in a '%s' folder" % dept_folders[-1]))
    if how is None:
        notes.append(("guess", "no version number: the newest file is used"))
    elif how in ("number", "date"):
        notes.append(("guess", "versions read as %s" % ("dates" if how == "date" else "plain numbers")))
    base = folders[:anchor + 1] + dept_folders
    name = _department_name(dept_folders, stem_t, parts, anchor)
    return {"name": name, "base_path": join(base), "version_pattern": pattern,
            "source_type": kind or "single_movie", "example": norm(example),
            "versions_in": unit, "notes": notes}


def _plain_name(folder):
    return folder if folder and "{" not in folder and not re.search(r"\d", folder) else ""


def _department_name(dept_folders, stem_t, parts, anchor):
    plain = [f for f in dept_folders if "{" not in f]
    if plain:
        return plain[-1]
    words = [w for w in re.split(r"[_\-. ]+", version_pattern(stem_t)[0])
             if w and "{" not in w and "*" not in w and not VERSION_WORD.match(w + "1")
             and not w.isdigit()]
    if words:
        return words[0]
    folder = parts[anchor] if 0 < anchor < len(parts) else ""
    return folder if folder and "{" not in folder and not re.search(r"\d", folder) else "footage"


# ------------------------------------------------------------------ learn
def learn(movie, scene=None, known_shot=None):
    """Work out the layout from one footage path (see the module notes)."""
    movie = norm(movie)
    parts = parts_of(movie)
    lay = {"shot": None, "sequence": None, "shot_folder": "", "sequence_from_shot": "",
           "shot_pattern": "", "shots_folder": "", "departments": [], "shots": [],
           "notes": [], "chips": [], "example": movie, "scene": norm(scene)}
    if not names.footage_stem(parts[-1])[1]:
        lay["notes"].append(("problem", "that isn't a movie (.mov, .mp4) or an image sequence"))
        return lay
    shot, shot_index, why = shot_code(movie, scene, known_shot)
    if not shot:
        lay["notes"].append(("problem", why))
        return lay
    lay["shot"] = shot
    lay["notes"].append(("ok", "shot %s: %s" % (shot, why)))
    sequence, seq_index = _sequence(parts, shot, shot_index)
    lay["sequence"] = sequence
    tparts = [template(p, shot, sequence) for p in parts]
    if sequence and len(shot) > len(sequence) + 1 and shot.lower().startswith(sequence.lower()) \
            and shot[len(sequence)] in "_-. ":
        lay["sequence_from_shot"] = "{sequence}%s*" % shot[len(sequence)]
    if shot_index is not None:
        lay["shot_folder"] = join(tparts[:shot_index + 1])
        anchor = shot_index
    else:
        anchor = len(parts) - 2
        while anchor > 0 and version_pattern(tparts[anchor])[1] in ("v",) and "{" not in tparts[anchor]:
            anchor -= 1                   # versions in folders without the shot's name
    stem_t = template(names.footage_stem(parts[-1])[0], shot, sequence)
    lay["shot_pattern"] = shot_pattern(stem_t, shot, sequence)
    first = department(movie, anchor, shot, sequence)
    if shot_index is None:
        first["name"] = first["name"] if first["name"] != "footage" else _department_name([], stem_t, parts, anchor - 1)
        lay["shots_folder"] = first["base_path"]
        dated = [i for i, p in enumerate(parts[:-1]) if DATE_RE.match(p)]
        if dated:                         # dailies filed by date: search by shot name instead
            first["notes"].append(("guess", "this footage is filed by date: found by searching for the shot's name"))
            first["search_roots"] = [join(parts[:dated[0]])]
            first["base_path"] = ""
            first["name"] = _plain_name(parts[dated[0] - 1]) or first["name"]
            lay["shots_folder"] = ""
    lay["departments"].append(first)
    for d in _sideways(movie, anchor, shot, sequence, first):
        lay["departments"].append(d)
    lay["shots"] = neighbours(lay)
    lay["chips"] = chips(movie, lay, shot_index, seq_index)
    if shot_index is None and not lay["shot_folder"]:
        lay["notes"].append(("ok", "footage lives outside shot folders: shots are read from file names"))
    if scene and shot_index is not None and not has_token(norm(scene), shot):
        lay["notes"].append(("guess", "the open scene doesn't mention shot %s" % shot))
    return lay


def _sideways(movie, anchor, shot, sequence, first):
    """Other departments beside the example's: folders next to its
    department folder, or (versions in file names) other words in the same
    folder (sh010_anim_v003.mov beside sh010_light_v002.mov)."""
    found = []
    real = parts_of(movie)
    base_real = real[:len(parts_of(first["base_path"]))]
    if first["versions_in"] == "file" and len(base_real) == anchor + 1:
        return _sideways_in_names(join(base_real), shot, sequence, first, anchor)
    if len(base_real) <= anchor + 1:
        return found
    parent = join(base_real[:-1])
    try:
        siblings = sorted(os.listdir(parent))[:MAX_SIDEWAYS]
    except OSError:
        return found
    own = base_real[-1].lower()
    level = len(base_real) - 1
    for name in siblings:
        path = os.path.join(parent, name)
        if name.lower() == own or name.startswith(".") or not os.path.isdir(path):
            continue
        example = _footage_in(path)
        if not example:
            continue
        d = department(example, level - 1, shot, sequence)
        if d["base_path"].split("/")[:level] != first["base_path"].split("/")[:level]:
            continue
        found.append(d)
    return found


def _sideways_in_names(folder, shot, sequence, first, anchor):
    out, seen = [], {first["version_pattern"].lower()}
    try:
        entries = sorted(os.listdir(folder), reverse=True)
    except OSError:
        return out
    for name in entries:
        stem, kind = names.footage_stem(name)
        if not stem or not has_token(stem, shot):
            continue
        pattern = version_pattern(template(stem, shot, sequence))[0]
        if pattern.lower() in seen:
            continue
        seen.add(pattern.lower())
        out.append(department(join([folder, name]), anchor, shot, sequence))
    return out


# ------------------------------------------------------------- neighbours
def neighbours(lay, limit=400):
    """The sequence's shots, by name: the shot folder's siblings shaped like
    the shot, or the shots named in the footage folder."""
    shot = lay["shot"]
    rx = re.compile("(?i)^" + shape(shot) + "$")
    out = set([shot])
    if lay["shot_folder"]:
        parent = fill(lay["shot_folder"], {"shot": shot, "sequence": lay["sequence"] or ""}).rsplit("/", 1)[0]
        try:
            for name in os.listdir(parent)[:limit * 4]:
                if rx.match(name) and os.path.isdir(os.path.join(parent, name)):
                    out.add(name)
        except OSError:
            pass
    elif lay["departments"] and lay["departments"][0].get("search_roots"):
        find = re.compile(lay["shot_pattern"])
        for paths in scan(lay["departments"][0]["search_roots"], lay["shot_pattern"], limit=20000).values():
            m = find.search(paths[0].rsplit("/", 1)[-1])
            if m:
                out.add(m.group("shot"))
    else:
        folder = fill(lay["shots_folder"], {"shot": shot, "sequence": lay["sequence"] or ""})
        find = re.compile(lay["shot_pattern"])
        try:
            for name in os.listdir(folder)[:limit * 20]:
                m = find.search(name)
                if m and (not lay["sequence"] or (m.groupdict().get("sequence") or lay["sequence"]).lower()
                          == lay["sequence"].lower()):
                    out.add(m.group("shot"))
        except OSError:
            pass
    return sorted(out, key=lambda s: s.lower())[:limit]


def fill(text, fields):
    return re.sub(r"\{(\w+)\}", lambda m: fields.get(m.group(1), m.group(0)), text)


# ------------------------------------------------------------------ chips
def chips(movie, lay, shot_index, seq_index):
    """[(text, role, sure)] for the example path: role is one of show-like
    'folder', 'sequence', 'shot', 'department', 'version', 'file'."""
    parts = parts_of(movie)
    out = []
    first = lay["departments"][0] if lay["departments"] else {}
    base_len = len(parts_of(first.get("base_path", "")))
    for i, p in enumerate(parts[:-1]):
        role, sure = "folder", True
        if shot_index is not None and i == shot_index:
            role = "shot"
        elif seq_index is not None and i == seq_index:
            role = "sequence"
        elif i >= base_len and first.get("versions_in") == "folder" and i == base_len:
            role, sure = "version", "number" not in str(first.get("notes"))
        elif shot_index is not None and shot_index < i < base_len:
            role = "department"
        elif shot_index is None and p == first.get("name"):
            role = "department"
        if p:
            out.append((p, role, sure))
    out.append((parts[-1], "file", True))
    return out


# --------------------------------------------------------------- profile
def to_profile(lay, learned_from=None):
    """The profile keys a layout gives (the same format a TD writes)."""
    depts = []
    for d in lay["departments"]:
        entry = {k: d[k] for k in ("name", "base_path", "version_pattern", "source_type")}
        if d.get("search_roots"):
            entry["search_roots"] = d["search_roots"]
        depts.append(entry)
    prof = {"shot_folder": lay["shot_folder"], "shot_pattern": lay["shot_pattern"],
            "departments": depts, "auto_order": [d["name"] for d in depts],
            "_learned_from": learned_from or {"example": lay["example"], "scene": lay["scene"],
                                              "date": time.strftime("%Y-%m-%d")}}
    prof["sequence_from_shot"] = lay["sequence_from_shot"]
    if lay["shots_folder"]:
        prof["shots_folder"] = lay["shots_folder"]
    if lay["scene"] and lay["shot"] and not has_token(lay["scene"], lay["shot"]):
        prof["scenes_by_hand"] = {lay["scene"]: lay["shot"]}     # a test scene outside the show
    return prof


# ------------------------------------------------- Search by shot name (B)
def scan(roots, pattern, stop=None, progress=None, limit=MAX_SCAN):
    """{shot (lower case): [footage paths]} for every movie or first frame
    under roots whose name (or folder) holds a shot found by pattern (a
    shot_pattern regex). stop(): True to give up; progress(count)."""
    find = re.compile(pattern)
    out, seen, count = {}, set(), 0
    for root in roots:
        for folder, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            count += len(files) + len(dirs)
            if stop and stop():
                return out
            if progress:
                progress(count)
            if count > limit:
                return out
            folder_shot = find.search(os.path.basename(folder))
            for name in sorted(files):
                stem, kind = names.footage_stem(name)
                if not stem:
                    continue
                if kind == "image_sequence":
                    key = (folder, stem)
                    if key in seen:
                        continue
                    seen.add(key)
                m = find.search(stem) or folder_shot
                if m:
                    out.setdefault(m.group("shot").lower(), []).append(norm(os.path.join(folder, name)))
    return out


def scene_shot(scene):
    """The shot-like code in a scene's file name (the longest), or None."""
    stem = os.path.splitext(parts_of(scene)[-1])[0] if scene else ""
    found = sorted(_runs(stem), key=len, reverse=True)
    return found[0] if found else None


def from_search(roots, shot, sequence=None, stop=None, progress=None):
    """Search by shot name (way B) as a layout: departments told apart by
    the words in the file names (sh010_anim_v003, sh010_lgt_v002...), each
    found by searching roots."""
    lay = {"shot": shot, "sequence": sequence, "shot_folder": "", "shots_folder": "",
           "sequence_from_shot": "", "departments": [], "shots": [], "notes": [], "chips": [],
           "example": "", "scene": "", "found": {}}
    if sequence and shot.lower().startswith(sequence.lower()) and len(shot) > len(sequence) + 1:
        lay["sequence_from_shot"] = "{sequence}%s*" % shot[len(sequence)]
    lay["shot_pattern"] = shot_pattern("{shot}", shot, sequence)
    found = scan(roots, lay["shot_pattern"], stop=stop, progress=progress)
    lay["found"] = found
    groups = {}
    for path in found.get(shot.lower(), []):
        stem, kind = names.footage_stem(path.rsplit("/", 1)[-1])
        pattern = version_pattern(template(stem, shot, sequence))[0]
        if "{shot}" not in pattern:
            pattern = "*{shot}*"
        groups.setdefault((pattern.lower(), kind), (pattern, kind, path))
    for pattern, kind, path in sorted(groups.values()):
        stem_t = template(names.footage_stem(path.rsplit("/", 1)[-1])[0], shot, sequence)
        name = _department_name([], stem_t, parts_of(path), len(parts_of(path)) - 2)
        lay["departments"].append({"name": name, "base_path": "", "version_pattern": pattern,
                                   "source_type": kind, "search_roots": [norm(r) for r in roots],
                                   "example": path, "versions_in": "file", "notes": []})
    _unique_names(lay["departments"])
    find = re.compile(lay["shot_pattern"])
    shots = set([shot])
    for paths in found.values():
        m = find.search(paths[0].rsplit("/", 1)[-1])
        if m and (not sequence or (m.groupdict().get("sequence") or sequence).lower() == sequence.lower()):
            shots.add(m.group("shot"))
    lay["shots"] = sorted(shots, key=lambda s: s.lower())
    if not lay["departments"]:
        lay["notes"].append(("problem", "no movies or image sequences named after %s in those folders" % shot))
    return lay


def _unique_names(depts):
    seen = {}
    for d in depts:
        base = d["name"]
        n = seen.get(base.lower(), 0)
        seen[base.lower()] = n + 1
        if n:
            d["name"] = "%s %d" % (base, n + 1)


def relative_to(prof, project):
    """A profile's paths with the project folder written as {project}, for a
    team's settings file (each computer says where the project is)."""
    root = norm(project)
    if not root:
        return prof

    def swap(value):
        if isinstance(value, str) and norm(value).lower().startswith(root.lower() + "/"):
            return "{project}" + norm(value)[len(root):]
        if isinstance(value, str) and norm(value).lower() == root.lower():
            return "{project}"
        if isinstance(value, list):
            return [swap(v) for v in value]
        if isinstance(value, dict):
            return {swap(k) if isinstance(k, str) and "/" in k else k: swap(v) for k, v in value.items()}
        return value
    return {k: swap(v) for k, v in prof.items()}
