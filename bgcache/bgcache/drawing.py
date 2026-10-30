"""Drawings over the player: layers of strokes per shot, camera and person.

Storage (one file per person and camera, plain JSON):
    <drawings folder>/<user>/drawings/<camera>/layers.json
The drawings folder (profile.drawings_root): in a studio shot, the shot's
shared folder from the pipeline profile; otherwise
<Maya project>/bgcache/<scene name>, or <scene folder>/bgcache/<scene name>
for a scene outside the project. The scene name leaves out its version
number, so every version of a scene shares its drawings.

    {"version": 2, "rev": 12, "frame_size": [960, 540], "active": "l1",
     "layers": [{"id": "l1", "name": "Layer 1", "visible": true, "locked": false,
                 "opacity": 1.0,
                 "frames": {"1142": [{"c": "#e8c547", "w": 6.0,
                                      "p": [[x, y, pressure], ...]}]}}]}

Points and widths are in pixels of the cached frame (frame_size), so lines
keep their place and thickness on the character at any player size. Layers
are listed top first. A frame with no drawing shows the last drawn frame
before it when Hold is on (like a held key).

Other people's drawings are read from their own files and are always
read-only: you see the version you accepted (a snapshot in your prefs
folder) until you press Update; to change one, duplicate the layer into
your own file. Nothing here ever writes to another person's folder.

Saving (0.9.0b3): your drawings are written to that shared file only when
you press Save (Ctrl+S): until then strokes, undo and redo stay on your
screen. While you draw, a private recovery copy is kept up to date in
~/.bgcache/recovery (never shared), so a crash loses almost nothing. Each
save bumps "rev" (so others notice a new version even within the same
second), gives new folders and the file the same permissions as the folder
they're in (so everyone can read them), and first keeps the version it
replaces in history/ next to it: the last VERSIONS_KEPT saves, listed by
versions() and brought back by restore().

This module has no Qt: the player draws strokes and builds the side strip.
"""
import copy
import getpass
import hashlib
import json
import os
import re
import time

from bgcache import common, profile

VERSION = 2
VERSIONS_KEPT = 10          # earlier saves kept in history/ (user: small folders)
COLORS = ["#e85d4a", "#e8c547", "#4cc3e0", "#f2f2f2", "#000000"]   # red, yellow, cyan, white, black
COLOR_NAMES = ["red", "yellow", "cyan", "white", "black"]
UNDO_LIMIT = 200


def user_name():
    try:
        return getpass.getuser()
    except Exception:  # no login name (some Windows setups): fall back to $USER
        return os.environ.get("USER") or "me"


def drawings_root(original_scene, project=None):
    """Folder holding everyone's drawings for this scene (see the top)."""
    return profile.drawings_root(original_scene, project)


def camera_folder(label):
    """Folder name for a camera: its short name, so the same camera matches
    across people's scenes."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", (label or "camera").split("|")[-1]).strip("_") or "camera"


def layers_path(root, user, camera):
    return os.path.join(root, user, "drawings", camera_folder(camera), "layers.json")


def new_layer(name, lid):
    return {"id": lid, "name": name, "visible": True, "locked": False, "opacity": 1.0, "frames": {}}


def held_key(frames, frame, hold=True):
    """The drawn frame shown at `frame`: itself, or with hold the last drawn
    frame before it. None when nothing shows. `frames` keys are strings."""
    if str(frame) in frames:
        return int(frame)
    if not hold or not frames:
        return None
    earlier = [int(k) for k in frames if int(k) <= frame]
    return max(earlier) if earlier else None


def neighbour_keys(frames, key):
    """(previous drawn frame, next drawn frame) around `key`, for onion skin."""
    keys = sorted(int(k) for k in frames)
    before = [k for k in keys if k < key]
    after = [k for k in keys if k > key]
    return (before[-1] if before else None), (after[0] if after else None)


def _dist2_point_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2


def match_parent_mode(path, is_dir=False):
    """Give a new folder or file the same openness as the folder it's in
    (a file without the execute bits). You can always write your own
    file (on Windows a read-only folder would otherwise make it read-only,
    and the next save would fail). Never raises."""
    try:
        mode = os.stat(os.path.dirname(os.path.abspath(path))).st_mode & 0o777
        os.chmod(path, (mode if is_dir else mode & 0o666) | 0o200)
    except OSError:
        pass


def make_dirs(folder):
    """os.makedirs, each new folder matching its parent's permissions."""
    missing = []
    f = os.path.abspath(folder)
    while f and not os.path.isdir(f):
        missing.append(f)
        parent = os.path.dirname(f)
        if parent == f:
            break
        f = parent
    for f in reversed(missing):
        try:
            os.mkdir(f)
        except OSError:
            if not os.path.isdir(f):
                raise
        match_parent_mode(f, is_dir=True)


def file_rev(path):
    """(rev, mtime, size) of a drawings file without loading it all, or None."""
    try:
        st = os.stat(path)
        with open(path) as handle:
            data = json.load(handle)
        return int(data.get("rev") or 0), st.st_mtime, st.st_size
    except (IOError, OSError, ValueError, TypeError):
        return None


def _densify(pts, step):
    """Points with extra ones every `step` pixels along each segment, so a
    cut through a long straight line is clean."""
    out = [list(pts[0])]
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = int((dx * dx + dy * dy) ** 0.5 / step)
        pa = a[2] if len(a) > 2 else 1.0
        pb = b[2] if len(b) > 2 else 1.0
        for i in range(1, n + 1):
            t = i / float(n + 1)
            out.append([round(a[0] + dx * t, 2), round(a[1] + dy * t, 2), round(pa + (pb - pa) * t, 3)])
        out.append(list(b))
    return out


def cut_stroke(stroke, x, y, radius):
    """What's left of a stroke after an eraser circle at (x, y): a list of
    strokes (the pieces either side), [] if all of it is under the eraser,
    or None if the eraser doesn't touch it."""
    if not stroke_hit(stroke, x, y, radius):
        return None
    pts = stroke.get("p") or []
    reach = radius + stroke.get("w", 1.0) / 2.0
    r2 = reach * reach
    if len(pts) > 1:
        pts = _densify(pts, max(0.75, min(radius, stroke.get("w", 1.0)) / 3.0))
    pieces, run = [], []
    for pt in pts:
        if (pt[0] - x) ** 2 + (pt[1] - y) ** 2 <= r2:
            if run:
                pieces.append(run)
            run = []
        else:
            run.append(pt)
    if run:
        pieces.append(run)
    out = []
    for piece in pieces:
        if len(piece) == 1 and len(pts) > 1:
            continue                     # a lone leftover point: gone with the cut
        st = dict(stroke)
        st["p"] = piece
        out.append(st)
    return out


def stroke_hit(stroke, x, y, radius):
    """Does an eraser circle at (x, y) touch this stroke?"""
    reach = radius + stroke.get("w", 1.0) / 2.0
    r2 = reach * reach
    pts = stroke.get("p") or []
    if len(pts) == 1:
        return (pts[0][0] - x) ** 2 + (pts[0][1] - y) ** 2 <= r2
    for a, b in zip(pts, pts[1:]):
        if _dist2_point_segment(x, y, a[0], a[1], b[0], b[1]) <= r2:
            return True
    return False


class Drawings(object):
    """One person's layers for one camera of the shot (yours: editable)."""

    def __init__(self, path, frame_size=(960, 540), read_only=False, owner=None):
        self.path = path
        self.read_only = read_only
        self.owner = owner or user_name()
        self.frame_size = list(frame_size)
        self.layers = []
        self.active = None
        self.undo_stack, self.redo_stack = [], []
        self.mtime = 0.0
        self.rev = 0
        self.source = {}           # what this file is: for an import snapshot, whose and which rev
        self.error = ""
        self.blocked = ""          # why the last undo/redo didn't happen (a locked layer)
        self.dirty = False         # changed since the last Save (only you see the changes)
        self.load()
        if not self.layers and not read_only:
            self.layers = [new_layer("Layer 1", "l1")]
            self.active = "l1"

    # ------------------------------------------------------------ files
    def load(self):
        data = None
        try:
            with open(self.path) as handle:
                data = json.load(handle)
            self.mtime = os.path.getmtime(self.path)
        except (IOError, OSError, ValueError):
            data = None
        if not data:
            return False
        self.rev = int(data.get("rev") or 0)
        return self._apply(data)

    def _apply(self, data):
        """Take layers (and the active layer) from a drawings file's data,
        scaled to our frame size."""
        size = data.get("frame_size") or self.frame_size
        layers = [l for l in data.get("layers") or [] if isinstance(l, dict) and "id" in l]
        if size and list(size) != list(self.frame_size) and size[0]:
            # cached at another size: scale points and widths to ours
            k = self.frame_size[0] / float(size[0])
            for layer in layers:
                for strokes in (layer.get("frames") or {}).values():
                    for st in strokes:
                        st["w"] = st.get("w", 1.0) * k
                        st["p"] = [[p[0] * k, p[1] * k] + list(p[2:]) for p in st.get("p") or []]
        for layer in layers:
            layer.setdefault("name", "Layer")
            layer.setdefault("visible", True)
            layer.setdefault("locked", False)
            layer.setdefault("opacity", 1.0)
            layer.setdefault("frames", {})
        self.layers = layers
        ids = [l["id"] for l in layers]
        self.active = data.get("active") if data.get("active") in ids else (ids[0] if ids else None)
        return True

    def changed_on_disk(self):
        try:
            return os.path.getmtime(self.path) != self.mtime
        except OSError:
            return False

    def save(self):
        """Save: write your layers to the shared file (others see them after
        Update). Returns "" or the reason it couldn't."""
        if self.read_only:
            return "read-only"
        try:
            folder = os.path.dirname(self.path)
            if not os.path.isdir(folder):
                make_dirs(folder)
            self._keep_version()
            on_disk = file_rev(self.path)
            self.rev = max(self.rev, on_disk[0] if on_disk else 0) + 1
            data = {"version": VERSION, "rev": self.rev, "frame_size": self.frame_size,
                    "active": self.active, "owner": self.owner, "saved": time.time(),
                    "layers": self.layers}
            common.write_json_atomic(self.path, data)
            match_parent_mode(self.path)
            self.mtime = os.path.getmtime(self.path)
            self.error = ""
            self.dirty = False
            self.clear_recovery()
        except (IOError, OSError) as error:
            self.error = str(error)
        return self.error

    def history_dir(self):
        return os.path.join(os.path.dirname(self.path), "history")

    def _keep_version(self):
        """Before a save replaces the file: keep it in history/ as a version
        (the last VERSIONS_KEPT). Never raises."""
        if not os.path.isfile(self.path):
            return
        try:
            folder = self.history_dir()
            if not os.path.isdir(folder):
                make_dirs(folder)
            now = time.time()
            stem = os.path.join(folder, "layers_%s_%03d" % (time.strftime("%Y%m%d_%H%M%S", time.localtime(now)),
                                                            int(now * 1000) % 1000))
            target, n = stem + ".json", 0
            while os.path.exists(target):     # two saves in the same millisecond: both kept
                n += 1
                target = "%s_%d.json" % (stem, n)
            with open(self.path, "rb") as src, open(target, "wb") as dst:
                dst.write(src.read())
            match_parent_mode(target)
            old = sorted(f for f in os.listdir(folder) if f.startswith("layers_") and f.endswith(".json"))
            for name in old[:-VERSIONS_KEPT]:
                os.remove(os.path.join(folder, name))
        except (IOError, OSError) as error:   # a missing history never stops a save
            self.error = "history not kept: %s" % error

    def versions(self):
        """Your saves, newest first: dicts with path, saved (time), frames
        (first, last drawn) and current (the file others see)."""
        out = []
        paths = [self.path]
        folder = self.history_dir()
        if os.path.isdir(folder):
            paths += sorted((os.path.join(folder, f) for f in os.listdir(folder)
                             if f.startswith("layers_") and f.endswith(".json")), reverse=True)
        for i, path in enumerate(paths):
            try:
                with open(path) as handle:
                    data = json.load(handle)
            except (IOError, OSError, ValueError):
                continue                  # unreadable or not saved yet: not listed
            keys = sorted(int(k) for layer in data.get("layers") or [] for k in (layer.get("frames") or {})
                          if (layer.get("frames") or {}).get(k))
            out.append({"path": path, "saved": data.get("saved") or os.path.getmtime(path),
                        "frames": (keys[0], keys[-1]) if keys else None, "current": i == 0})
        return out

    def restore(self, path):
        """Bring back an earlier save: it becomes your drawings and is saved
        again (the one it replaces is kept, so a restore can be undone).
        Returns "" or the reason it couldn't."""
        try:
            with open(path) as handle:
                data = json.load(handle)
        except (IOError, OSError, ValueError) as error:
            return "couldn't read that version: %s" % error
        self._record(("layers", (copy.deepcopy(self.layers), self.active)))
        self._apply(data)
        return self.save()

    # ------------------------------------------------------------ recovery
    def recovery_path(self):
        """A private copy of your unsaved drawings, in your own ~/.bgcache."""
        key = hashlib.sha1(os.path.abspath(self.path).encode("utf-8")).hexdigest()[:16]
        return os.path.join(os.path.expanduser("~"), ".bgcache", "recovery", "%s.json" % key)

    def write_recovery(self):
        """Keep the recovery copy up to date while you draw. Never raises."""
        if self.read_only or not self.dirty:
            return
        try:
            path = self.recovery_path()
            folder = os.path.dirname(path)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            common.write_json_atomic(path, {"version": VERSION, "for": os.path.abspath(self.path),
                                            "frame_size": self.frame_size, "active": self.active,
                                            "written": time.time(), "base_rev": self.rev,
                                            "layers": self.layers})
        except (IOError, OSError) as error:   # recovery is a safety net: drawing carries on
            self.error = "recovery copy not written: %s" % error

    def recovery(self):
        """The recovery copy's data if one is waiting for this file (unsaved
        drawings from a session that ended without Save), else None."""
        try:
            with open(self.recovery_path()) as handle:
                data = json.load(handle)
        except (IOError, OSError, ValueError):
            return None
        if data.get("for") != os.path.abspath(self.path):
            return None
        return data

    def recover(self, data):
        """Take the recovery copy's drawings (still unsaved: Save to share)."""
        self._record(("layers", (copy.deepcopy(self.layers), self.active)))
        self._apply(data)
        self.dirty = True

    def clear_recovery(self):
        try:
            os.remove(self.recovery_path())
        except OSError:                       # no recovery copy: nothing to clear
            pass

    # ------------------------------------------------------------ layers
    def layer(self, lid):
        for layer in self.layers:
            if layer["id"] == lid:
                return layer
        return None

    def active_layer(self):
        return self.layer(self.active)

    def _new_id(self):
        n = 1
        ids = {l["id"] for l in self.layers}
        while "l%d" % n in ids:
            n += 1
        return "l%d" % n

    def add_layer(self, name=None):
        lid = self._new_id()
        names = {l["name"] for l in self.layers}
        n = len(self.layers) + 1
        while not name:
            candidate = "Layer %d" % n
            name = candidate if candidate not in names else None
            n += 1
        before = (copy.deepcopy(self.layers), self.active)
        index = self.layers.index(self.active_layer()) if self.active_layer() else 0
        self.layers.insert(index, new_layer(name, lid))      # above the active one
        self.active = lid
        self._record(("layers", before))
        return lid

    def delete_layer(self, lid):
        """False if the layer doesn't exist or is locked."""
        layer = self.layer(lid)
        if layer is None or layer.get("locked"):
            return False
        before = (copy.deepcopy(self.layers), self.active)
        self.layers.remove(layer)
        if not self.layers:
            self.layers = [new_layer("Layer 1", self._new_id())]
        if self.active == lid:
            self.active = self.layers[0]["id"]
        self._record(("layers", before))
        return True

    def duplicate_layer(self, layer, name, source=None):
        """A copy of `layer` (from anyone's drawings) as a new layer of yours,
        above the active one, unlocked. Undoable. Returns its id."""
        lid = self._new_id()
        before = (copy.deepcopy(self.layers), self.active)
        new = new_layer(name, lid)
        new["frames"] = copy.deepcopy(layer.get("frames") or {})
        if source:
            new["source"] = dict(source)
        index = self.layers.index(self.active_layer()) if self.active_layer() else 0
        self.layers.insert(index, new)
        self.active = lid
        self._record(("layers", before))
        return lid

    def move_layer(self, lid, delta):
        layer = self.layer(lid)
        if layer is None:
            return
        i = self.layers.index(layer)
        j = min(max(i + delta, 0), len(self.layers) - 1)
        if i != j:
            self.layers.insert(j, self.layers.pop(i))

    def rename_layer(self, lid, name):
        layer = self.layer(lid)
        if layer is not None and name:
            layer["name"] = name

    def set_layer(self, lid, **values):
        layer = self.layer(lid)
        if layer is not None:
            layer.update(values)

    def drawable(self):
        """Why you can't draw on the active layer right now, or ""."""
        layer = self.active_layer()
        if self.read_only or layer is None:
            return "no layer to draw on"
        if layer["locked"]:
            return "layer %s is locked" % layer["name"]
        if not layer["visible"]:
            return "layer %s is hidden" % layer["name"]
        return ""

    # ------------------------------------------------------------ strokes
    def strokes_at(self, layer, frame, hold=True):
        """(drawn frame, strokes) shown on `layer` at `frame`."""
        key = held_key(layer["frames"], frame, hold)
        return key, (layer["frames"].get(str(key)) or []) if key is not None else []

    def add_stroke(self, frame, stroke):
        """A finished stroke on the active layer at `frame`. Drawing on a
        frame with no drawing of its own starts a new drawn frame there."""
        layer = self.active_layer()
        if self.drawable() or not stroke.get("p"):
            return False
        key = str(int(frame))
        before = copy.deepcopy(layer["frames"].get(key))
        layer["frames"].setdefault(key, []).append(stroke)
        self._record(("frame", layer["id"], key, before))
        return True

    def erase_at(self, frame, x, y, radius, hold=True, record=True, whole=False):
        """Erase what's under the eraser circle on the active layer's shown
        drawing: strokes are cut there and the pieces either side kept, or
        with whole=True every touched stroke goes. Returns how many strokes
        changed."""
        layer = self.active_layer()
        if self.drawable():
            return 0
        key = held_key(layer["frames"], frame, hold)
        if key is None:
            return 0
        strokes = layer["frames"].get(str(key)) or []
        keep, removed = [], 0
        for st in strokes:
            if whole:
                hit = stroke_hit(st, x, y, radius)
                pieces = [] if hit else None
            else:
                pieces = cut_stroke(st, x, y, radius)
            if pieces is None:
                keep.append(st)
            else:
                keep.extend(pieces)
                removed += 1
        if removed:
            before = copy.deepcopy(strokes)
            if keep:
                layer["frames"][str(key)] = keep
            else:
                del layer["frames"][str(key)]
            if record:
                self._record(("frame", layer["id"], str(key), before))
        return removed

    def clear_frame(self, frame, hold=True):
        layer = self.active_layer()
        if self.drawable():
            return False
        key = held_key(layer["frames"], frame, hold)
        if key is None:
            return False
        before = layer["frames"].pop(str(key))
        self._record(("frame", layer["id"], str(key), before))
        return True

    def begin_group(self):
        """Several changes (an eraser drag) undo as one."""
        self._group = []

    def end_group(self):
        group, self._group = getattr(self, "_group", None), None
        if group:
            self.undo_stack.append(("group", group))
            self.redo_stack = []
            del self.undo_stack[:-UNDO_LIMIT]

    def _record(self, state):
        """state: ("frame", layer id, frame key, strokes before) or
        ("layers", (all layers before, active layer id))."""
        if getattr(self, "_group", None) is not None:
            self._group.append(state)
            return
        self.undo_stack.append(state)
        del self.undo_stack[:-UNDO_LIMIT]
        self.redo_stack = []

    # Undo restores the state before; it records the state after, for redo.
    def _swap(self, state):
        if state[0] == "group":
            return ("group", [self._swap(s) for s in reversed(state[1])])
        if state[0] == "frame":
            _kind, lid, key, before = state
            layer = self.layer(lid)
            if layer is None:
                return state
            now = copy.deepcopy(layer["frames"].get(key))
            if before:
                layer["frames"][key] = copy.deepcopy(before)
            else:
                layer["frames"].pop(key, None)
            return ("frame", lid, key, now)
        now = (copy.deepcopy(self.layers), self.active)
        layers, active = state[1]
        self.layers = copy.deepcopy(layers)
        self.active = active if self.layer(active) else (self.layers[0]["id"] if self.layers else None)
        return ("layers", now)

    def _locked_by(self, state):
        """Name of a locked layer this undo/redo step would change, or ""."""
        if state[0] == "group":
            for sub_state in state[1]:
                name = self._locked_by(sub_state)
                if name:
                    return name
            return ""
        if state[0] == "frame":
            layer = self.layer(state[1])
            return layer["name"] if layer is not None and layer.get("locked") else ""
        layers, _active = state[1]
        then = {l["id"]: l for l in layers}
        for layer in self.layers:
            if layer.get("locked"):
                old = then.get(layer["id"])
                if old is None or old.get("frames") != layer.get("frames"):
                    return layer["name"]
        return ""

    def undo(self):
        """True if undone; "" when there's nothing to undo; the reason
        (a locked layer) when it's blocked."""
        if not self.undo_stack:
            return False
        name = self._locked_by(self.undo_stack[-1])
        if name:
            self.blocked = "layer %s is locked" % name
            return False
        self.blocked = ""
        self.redo_stack.append(self._swap(self.undo_stack.pop()))
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        name = self._locked_by(self.redo_stack[-1])
        if name:
            self.blocked = "layer %s is locked" % name
            return False
        self.blocked = ""
        self.undo_stack.append(self._swap(self.redo_stack.pop()))
        return True

    # ------------------------------------------------------------ queries
    def drawn_frames(self, visible_only=True):
        out = set()
        for layer in self.layers:
            if visible_only and not layer["visible"]:
                continue
            out.update(int(k) for k in layer["frames"])
        return out


def find_people(root, me, camera, include_me=False):
    """People with drawings for this camera (others; you too with
    include_me): [{"user", "path", "layers", "mtime", "rev"}], newest first."""
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        if name == me and not include_me:
            continue
        path = layers_path(root, name, camera)
        try:
            mtime = os.path.getmtime(path)
            with open(path) as handle:
                data = json.load(handle)
        except (IOError, OSError, ValueError):
            continue
        layers = [l for l in data.get("layers") or [] if l.get("frames")]
        if layers:
            out.append({"user": name, "path": path, "layers": len(layers), "mtime": mtime,
                        "rev": int(data.get("rev") or 0)})
    out.sort(key=lambda p: -p["mtime"])
    return out


def drawn_cameras(root):
    """Camera folders anyone has drawings for, under <shot>/maya/bgcache."""
    cams = set()
    try:
        for user in os.listdir(root):
            folder = os.path.join(root, user, "drawings")
            if os.path.isdir(folder):
                cams.update(c for c in os.listdir(folder)
                            if os.path.isfile(os.path.join(folder, c, "layers.json")))
    except OSError:
        pass
    return cams


def when_text(mtime, now=None):
    now = now or time.time()
    t, n = time.localtime(mtime), time.localtime(now)
    if t[:3] == n[:3]:
        return "today"
    return time.strftime("%b %d", t).replace(" 0", " ")


# --------------------------------------------------------------------------
# Blue Pencil placement
# --------------------------------------------------------------------------
BP_SIZE = 2048


def res_gate_inches(gate):
    """(width, height) in inches of the camera's resolution gate, which is
    what a cached frame shows (rendered at overscan 1)."""
    fw, fh = gate["fw"], gate["fh"]
    aspect = gate.get("aspect") or (fw / fh)
    fit = gate.get("fit", 1)
    film_aspect = fw / fh
    if fit == 0:            # fill: resolution gate inside the film gate
        fit = 1 if film_aspect <= aspect else 2
    elif fit == 3:          # overscan: film gate inside the resolution gate
        fit = 1 if film_aspect >= aspect else 2
    if fit == 2:
        return fh * aspect, fh
    return fw, fw / aspect


def film_gate_rect(gate, frame_w, frame_h):
    """(x, y, w, h) of the camera's film gate inside a cached frame (the
    resolution gate), centred; None when it fills the frame or is unknown."""
    if not gate or not gate.get("fw") or not gate.get("fh"):
        return None
    res_w, res_h = res_gate_inches(gate)
    w = gate["fw"] * frame_w / res_w
    h = gate["fh"] * frame_h / res_h
    w, h = min(w, frame_w), min(h, frame_h)
    if frame_w - w < 1.0 and frame_h - h < 1.0:
        return None
    return ((frame_w - w) / 2.0, (frame_h - h) / 2.0, w, h)


def bp_scale(gate, frame_w):
    """Blue Pencil square pixels per cached-frame pixel. Blue Pencil's
    2048 square is as wide as the camera's film gate and centred on it
    (measured on a production camera); the cached frame is the resolution gate."""
    res_w, _res_h = res_gate_inches(gate)
    return BP_SIZE * res_w / (gate["fw"] * frame_w)


def frame_to_bp(x, y, frame_w, frame_h, k):
    return BP_SIZE / 2.0 + (x - frame_w / 2.0) * k, BP_SIZE / 2.0 + (y - frame_h / 2.0) * k


def bp_to_frame(bx, by, frame_w, frame_h, k):
    return (bx - BP_SIZE / 2.0) / k + frame_w / 2.0, (by - BP_SIZE / 2.0) / k + frame_h / 2.0


def bp_xml(camera, layers):
    """Blue Pencil's index file. layers: [(name, visible, [(frame, file)])]."""
    from xml.sax.saxutils import quoteattr
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<bluePencil>",
             "    <camera name=%s>" % quoteattr(camera)]
    for name, visible, frames in layers:
        lines.append('        <layer name=%s isStatic="false" isActive="false" isLocked="false" '
                     'isVisible="%s">' % (quoteattr(name), "true" if visible else "false"))
        for frame, filename in frames:
            lines.append("            <frame file=%s time=\"%d\"/>" % (quoteattr(filename), frame))
        lines.append("        </layer>")
    lines += ["    </camera>", "</bluePencil>", ""]
    return "\n".join(lines)


def read_bp_zip(path):
    """Layers of a Blue Pencil zip: {"camera", "layers": [{"name", "frames":
    {frame: member name in the zip}}]}."""
    import zipfile
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        xmls = [n for n in names if n.lower().endswith(".xml")]
        if not xmls:
            raise ValueError("no Blue Pencil index (.xml) in %s" % os.path.basename(path))
        root = ET.fromstring(z.read(xmls[0]))
    folder = os.path.dirname(xmls[0])
    out = {"camera": None, "layers": []}
    for cam in root.iter("camera"):
        out["camera"] = out["camera"] or cam.get("name")
        for layer in cam.iter("layer"):
            frames = {}
            for fr in layer.iter("frame"):
                member = fr.get("file") or ""
                if folder and member not in names:
                    member = folder + "/" + member
                if member in names:
                    frames[int(round(float(fr.get("time", 0))))] = member
            if frames:
                out["layers"].append({"name": layer.get("name") or "layer", "frames": frames})
    return out
