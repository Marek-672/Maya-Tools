"""Pipeline profile: how a studio lays out its shots, in one JSON file.

bgcache works without one: drawings go next to your Maya project or scene,
and the continuity strip stays off. A studio fills in a profile to tell
bgcache where its shots live, which departments' footage to show beside
yours, where drawings are shared, and which of its own tools to switch off
in the background Maya.

Where bgcache looks for the profile, first found wins:
    1. the file named by the BGCACHE_PROFILE environment variable
    2. profile.json inside the installed bgcache folder (a studio ships it there)
    3. ~/.bgcache/profile.json (your own)
Nothing found: the built-in generic profile (DEFAULT below).

Paths in a profile always use forward slashes, on Windows too. Templates
take {show}, {sequence} and {shot}, and departments and drawings_folder
also take {shot_folder}. Keys you leave out keep their DEFAULT value.
Keys starting with "_" are notes and are ignored.

See profiles/example_studio.json for a filled-in example.
"""
import copy
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT = {
    # Where one shot's folder is, e.g. "/projects/{show}/shots/{shot}". A scene
    # saved inside such a folder is "in a shot": that turns on continuity and
    # the shared drawings folder. Empty: bgcache doesn't know about shots.
    "shot_folder": "",
    # The sequence, when shot_folder has no {sequence}: read from the shot's
    # own name. "{sequence}_*" means everything before the first "_"
    # (shot sq010_0040 is in sequence sq010).
    "sequence_from_shot": "{sequence}_*",
    # Where everyone's drawings for a shot go, e.g. "{shot_folder}/maya/bgcache".
    # Empty, or a scene outside any shot: <Maya project>/bgcache/<scene name>,
    # or <scene's folder>/bgcache/<scene name> when the scene isn't in the project.
    "drawings_folder": "",
    # Footage the continuity strip can show for a shot, one entry per department:
    #   name: shown in the menus
    #   base_path: folder holding the department's versions for a shot
    #   version_pattern: version folder names (* = anything), ending _v<number>
    #   source_type: "image_sequence" (a folder of numbered frames) or
    #                "single_movie" (one .mov inside the version folder)
    "departments": [],
    # Optional: a JSON file with its own "departments" list (and "ffmpeg_path")
    # that replaces the one above, e.g. a file shared with another tool.
    # bgcache only reads it.
    "departments_file": "",
    # Auto picks the first department that has footage, in this order;
    # departments not listed come after, in the order above.
    "auto_order": [],
    # Department movies start with this many slate frames. A movie exactly
    # that much longer than the shot has them skipped; the same length as the
    # shot plays from its first frame.
    "movie_slate_frames": 0,
    # When the shot's length is unknown (no image sequence to compare with):
    # skip the slate frames anyway (true) or play the movie as is (false).
    "assume_slate_when_unknown": False,
    # Tools left out of the background Maya, matched (lower case) against its
    # script, module and plug-in folders. animBot's startup dialog would stop
    # a hidden Maya from loading.
    "skip_in_background": ["animbot"],
    # Tools switched off inside the background Maya only (never in yours):
    #   {"if_scriptjob_contains": "...", "call": "package.module.function"}
    # calls the function (no arguments) whenever a script job containing that
    # text is running, checked every few seconds.
    "switch_off_in_background": [],
    # "follow": the background Maya evaluates deformers on the graphics card
    # (GPU override) when YOUR Maya does: much faster. "always": the GPU even
    # when yours has it off (shots that switch it off when they open).
    # false: always the CPU. If the GPU deformers fail
    # there (out of memory, or a rig that breaks on the GPU), bgcache switches
    # that Maya to the CPU by itself, restarting it if it got stuck, and says
    # so. false: always use the CPU there.
    "background_gpu": "follow",
    # Several sound tracks in a scene and none picked on the time slider:
    # which to play, in order of preference, matched in the sound node's name
    # (e.g. ["_ax_"] for the full mix before dialogue/music/effects stems).
    # Nothing matches: the first track that isn't muted.
    "sound_preference": [],
    # Studio wrapper commands for starting Maya, tried on the PATH after the
    # usual places (the running Maya's own program comes first).
    "maya_wrappers": [],
    # ffmpeg, if it isn't on the PATH (only needed for movies and for sound
    # at a different sample rate).
    "ffmpeg": "",
    # The setup wizard may offer to download ffmpeg (a pinned build, into
    # ~/.bgcache/ffmpeg) when there's none. false: never offer it.
    "ffmpeg_download": True,
    # The background Maya draws the cache with the same viewport renderer as
    # your shot camera's view (Viewport 2.0, plus a studio render override
    # if there is one; plug-ins with "viewport" in their name, or listed in
    # viewport_plugins, are loaded for it). false: always Maya's standard
    # Viewport 2.0.
    "background_viewport_renderer": True,
    "viewport_plugins": [],
    # A studio's own playblast set-up, run in the background Maya once its
    # render view is made: "module.function" (given the panel name, or no
    # arguments). Empty: nothing.
    "before_playblast": "",
    # Updates, only when the artist asks (Help > Check for updates):
    # releases_folder: a studio folder of release zips (bgcache_<version>.zip),
    # or a list of folders tried in order; when set, the only place looked at.
    # github_releases: the GitHub repository whose bgcache releases are
    # checked otherwise (the check's only network use). Empty: no check.
    "releases_folder": "",
    "github_releases": "Marek-672/Maya-Tools",
    # Help > Report a problem (0.9.0b3):
    # reports_url: a Google Apps Script web app that files reports in a
    # Drive folder (tools/reports_receiver.gs). The default sends them to
    # bgcache's author; a studio sets "" (Save only) or its own.
    # reports_folder: where Save report... starts (a pipeline folder, say).
    # Empty: your home folder.
    # 0.9.0b4, footage outside shot folders (the setup wizard writes these):
    # shot_pattern: a regex finding the shot in any file name, with a group
    # named shot (and one named sequence if the name holds it), e.g.
    # "(?i)(?P<shot>sh\\d+)". Used when a scene isn't inside a shot_folder.
    # shots_folder: where the sequence's shots are named (e.g. one folder of
    # playblasts); takes {sequence}. Used when there's no shot_folder.
    "shot_pattern": "",
    "shots_folder": "",
    # scenes_by_hand: {scene path: shot} for scenes saved outside the show
    # that the user told the wizard which shot they are.
    "scenes_by_hand": {},
    # edit_order: an edit export (.edl, Final Cut / Premiere .xml, .fcpxml):
    # neighbouring shots follow the cut instead of name order.
    "edit_order": "",
    # footage_by_hand: {shot: {department: movie}} dropped on a shot's card
    # in the wizard; later versions of that file count as newer.
    "footage_by_hand": {},
    # A film team (0.9.0b4): team_settings is the shared settings file
    # (e.g. P:/FILM/bgcache/settings.json), read before this file's keys;
    # project_folder is where the project is on THIS computer, used for
    # {project} in the team's paths (P:/FILM on Windows, /Volumes/FILM on a Mac).
    "team_settings": "",
    "project_folder": "",
    "reports_url": "https://script.google.com/macros/s/AKfycbxvqrA4Uwsksy4NeuO1zhbzazfk0KgRdL62mumHj9aZ39GCbVAaBL2X_GNUxHNkDbA9/exec",
    "reports_folder": "",
}

_cache = {"key": None, "profile": None, "source": None}
_context = {}          # (show, shot) -> sequence, learnt from scene paths
_extra = {}            # other {fields} of the last shot_folder match (e.g. {episode})


def candidates():
    """Profile files to try, in order."""
    out = []
    env = os.environ.get("BGCACHE_PROFILE")
    if env:
        out.append(os.path.expanduser(env))
    out.append(os.path.join(HERE, "profile.json"))
    out.append(os.path.join(os.path.expanduser("~"), ".bgcache", "profile.json"))
    return out


def _read(path):
    with open(path) as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("a profile must be a JSON object { ... }")
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load(force=False):
    """The active profile (a dict with every DEFAULT key). A personal
    profile with "team_settings" reads that team file first, then its own
    keys on top (0.9.0b4: a film team's shared setup)."""
    if _override["profile"] is not None:
        return _override["profile"]
    found = next((p for p in candidates() if os.path.isfile(p)), None)
    key = _key(found)
    if not force and _cache["profile"] is not None and _cache["key"] == key:
        return _cache["profile"]
    prof = copy.deepcopy(DEFAULT)
    source = "built-in generic profile"
    if found:
        try:
            own = _read(found)
            team = os.path.expanduser(own.get("team_settings") or "")
            if team:
                try:
                    prof.update(_read(team))
                except (IOError, OSError, ValueError) as error:
                    print("bgcache: team settings %s can't be read (%s)" % (team, error))
            prof.update(own)
            source = found
        except (IOError, OSError, ValueError) as error:
            print("bgcache: profile %s can't be read (%s); using the generic profile" % (found, error))
    _cache.update(key=key, profile=prof, source=source)
    return prof


def _key(found):
    """What the cached profile depends on: the file and its team file, with
    their dates."""
    if not found:
        return None
    try:
        key = [found, os.path.getmtime(found)]
        team = _cache["profile"].get("team_settings") if _cache["profile"] else None
        if team and os.path.isfile(os.path.expanduser(team)):
            key += [team, os.path.getmtime(os.path.expanduser(team))]
        return tuple(key)
    except OSError:
        return None


_override = {"profile": None}


def use(prof):
    """Try settings without saving them (the setup wizard's preview): a full
    profile dict, or None to go back to the saved one."""
    if prof is None:
        _override["profile"] = None
        return
    full = copy.deepcopy(DEFAULT)
    full.update({k: v for k, v in prof.items() if not k.startswith("_")})
    _override["profile"] = full
    _context.clear()


def personal_path():
    return os.path.join(os.path.expanduser("~"), ".bgcache", "profile.json")


def is_studio():
    """True when a studio's profile is in use (BGCACHE_PROFILE or one
    shipped in the bgcache folder), not the person's own."""
    src = source()
    return src not in ("built-in generic profile",) and os.path.normcase(os.path.abspath(src)) != \
        os.path.normcase(os.path.abspath(personal_path()))


def source():
    load()
    return _cache["source"]


def get(name):
    return load().get(name, DEFAULT.get(name))


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------
FIELD_RE = re.compile(r"\{(\w+)\}")


def _norm(path):
    """Forward slashes, ~ and {project} (this computer's project_folder, for
    a team's settings) filled in: the form templates are matched against."""
    text = path or ""
    if "{project}" in text:
        text = text.replace("{project}", (get("project_folder") or "").rstrip("/\\"))
    return os.path.expanduser(text).replace("\\", "/")


def _template_regex(template, tail):
    """Regex for a template: {name} matches one folder name (or, for
    {sequence} in sequence_from_shot, as little as possible)."""
    parts, pos, seen = [], 0, set()
    for m in FIELD_RE.finditer(template):
        parts.append(re.escape(template[pos:m.start()]).replace(r"\*", ".*"))
        name = m.group(1)
        parts.append("(?P=%s)" % name if name in seen else "(?P<%s>[^/]+?)" % name)
        seen.add(name)
        pos = m.end()
    parts.append(re.escape(template[pos:]).replace(r"\*", ".*"))
    flags = re.IGNORECASE if os.name == "nt" else 0
    return re.compile("^" + "".join(parts) + tail, flags)


def fill(template, fields):
    """A template with its {fields} filled in, as a normal path. KeyError
    names a field the template uses that isn't known."""
    text = _norm(template).format_map(fields)
    return os.path.normpath(text) if text else text


def sequence_of(shot, show=""):
    """The sequence a shot belongs to (None if unknown)."""
    if (show, shot) in _context:
        return _context[(show, shot)]
    pattern = get("sequence_from_shot")
    if pattern and "{sequence}" in pattern:
        m = _template_regex(pattern, "$").match(shot or "")
        if m:
            return m.group("sequence")
    return None


def shot_fields(show, shot):
    """{show, sequence, shot, shot_folder} for filling templates."""
    fields = dict(_extra)
    fields.update(show=show or "", shot=shot or "", sequence=sequence_of(shot, show) or "")
    template = get("shot_folder")
    try:
        fields["shot_folder"] = _norm(template).format_map(fields).rstrip("/") if template else ""
    except KeyError:
        fields["shot_folder"] = ""
    return fields


def match_shot(path):
    """The shot a file is in, as {show, sequence, shot, shot_folder}, or None:
    from the shot folder it's in, or (0.9.0b4, footage and scenes outside
    shot folders) from the profile's shot_pattern found in its name."""
    return _match_shot_folder(path) or _match_shot_name(path) or _match_by_hand(path)


def _match_by_hand(path):
    """A scene the user told the wizard which shot it is (scenes_by_hand:
    {scene path: shot}), for test scenes saved outside the show."""
    by_hand = {_norm(k).lower(): v for k, v in (get("scenes_by_hand") or {}).items()}
    shot = by_hand.get(_norm(path).lower()) if path else None
    return shot_fields("", shot) if shot else None


def _match_shot_name(path):
    """The shot_pattern's last match in the path, file name first."""
    pattern = get("shot_pattern")
    if not pattern or not path:
        return None
    try:
        rx = re.compile(pattern)
    except re.error as error:
        print("bgcache: shot_pattern in the profile isn't a valid pattern: %s" % error)
        return None
    for part in reversed(_norm(path).split("/")):
        m = rx.search(part)
        if m and m.groupdict().get("shot"):
            shot = m.group("shot")
            if m.groupdict().get("sequence"):
                _context[("", shot)] = m.group("sequence")
            _extra.clear()
            return shot_fields("", shot)
    return None


def _looks_like_shot(name):
    """True unless the profile's shot_pattern says this name isn't a shot."""
    pattern = get("shot_pattern")
    if not pattern:
        return True
    try:
        m = re.compile(pattern).search(name)
    except re.error:
        return True
    return bool(m) and m.group("shot").lower() == name.lower()


def _match_shot_folder(path):
    template = (get("shot_folder") or "").rstrip("/")
    if not template or "{shot}" not in template or not path:
        return None
    m = _template_regex(_norm(template), "(/|$)").match(_norm(path))
    if not m:
        return None
    groups = m.groupdict()
    show, shot = groups.get("show") or "", groups["shot"]
    if not _looks_like_shot(shot) or (m.end() == len(_norm(path)) and os.path.splitext(shot)[1]):
        return None                       # the file itself, or a folder that isn't shot-shaped
    if groups.get("sequence"):
        _context[(show, shot)] = groups["sequence"]
    _extra.clear()
    _extra.update({k: v for k, v in groups.items() if k not in ("show", "sequence", "shot")})
    fields = shot_fields(show, shot)
    fields["shot_folder"] = m.group(0).rstrip("/")
    return fields


def parse_shot(path):
    """(show, shot, sequence) of the shot a file is in, or None."""
    fields = match_shot(path)
    if not fields:
        return None
    return fields["show"], fields["shot"], fields["sequence"] or fields["shot"]


def list_shots(show, sequence):
    """Shot names in a sequence: the folders next to the shot folder, or
    (0.9.0b4) the shots named in the profile's shots_folder."""
    template = (get("shot_folder") or "").rstrip("/")
    if not template:
        return _shots_in_names(show, sequence)
    parent, last = _norm(template).rsplit("/", 1) if "/" in template else ("", template)
    if "{shot}" not in last:
        return []
    known = dict(_extra, show=show or "", sequence=sequence or "")
    try:
        folder = parent.format_map(known)
    except KeyError:
        return []
    if not os.path.isdir(folder):
        return []
    name_re = _template_regex(last.replace("{sequence}", sequence or "{sequence}"), "$")
    sequence_in_path = "{sequence}" in parent
    shots = []
    for entry in os.listdir(folder):
        if not os.path.isdir(os.path.join(folder, entry)):
            continue
        m = name_re.match(entry)
        if not m:
            continue
        shot = m.group("shot")
        if sequence_in_path:
            _context[(show or "", shot)] = sequence
        elif sequence_of(shot, show) not in (sequence, None):
            continue                      # no sequences in this layout: all shots are one
        shots.append(shot)
    return sorted(shots)


def _shots_in_names(show, sequence):
    """Shots found by shot_pattern among the names in shots_folder."""
    folder_t, pattern = get("shots_folder"), get("shot_pattern")
    if not folder_t or not pattern:
        return []
    try:
        folder = fill(folder_t, dict(_extra, show=show or "", sequence=sequence or "", shot=""))
        rx = re.compile(pattern)
        entries = os.listdir(folder)
    except (KeyError, OSError, re.error):
        return []
    shots = set()
    for entry in entries:
        m = rx.search(entry)
        if not m:
            continue
        shot, seq = m.group("shot"), m.groupdict().get("sequence")
        if seq:
            _context[(show or "", shot)] = seq
        if sequence and (seq or sequence_of(shot, show) or sequence).lower() != sequence.lower():
            continue
        shots.add(shot)
    return sorted(shots, key=lambda s: s.lower())


# --------------------------------------------------------------------------
# Drawings
# --------------------------------------------------------------------------
VERSION_TAIL_RE = re.compile(r"[._-]?v\d+$", re.IGNORECASE)


def scene_stem(scene):
    """A scene's name without folder, extension or version number, so every
    version of a scene shares its drawings: walk_v012.mb -> walk."""
    stem = os.path.splitext(os.path.basename(scene or ""))[0]
    bare = VERSION_TAIL_RE.sub("", stem)
    name = bare or stem or "untitled"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "untitled"


def _inside(path, folder):
    if not path or not folder:
        return False
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return path.startswith(folder.rstrip(os.sep) + os.sep)


def drawings_root(scene, project=None):
    """Folder holding everyone's drawings for this scene's shot.

    In a studio shot (profile shot_folder + drawings_folder): the shot's
    shared folder. Otherwise <project>/bgcache/<scene name> when the scene is
    inside the Maya project, else <scene folder>/bgcache/<scene name>.
    An unsaved scene: ~/.bgcache/drawings/untitled."""
    template = get("drawings_folder")
    fields = match_shot(scene) if template else None
    if fields:
        try:
            return fill(template, fields)
        except (KeyError, ValueError) as error:
            print("bgcache: drawings_folder in the profile: unknown field %s" % error)
    if not scene:
        return os.path.join(os.path.expanduser("~"), ".bgcache", "drawings", "untitled")
    stem = scene_stem(scene)
    if project and _inside(scene, project):
        return os.path.join(os.path.normpath(project), "bgcache", stem)
    return os.path.join(os.path.dirname(os.path.abspath(scene)), "bgcache", stem)
