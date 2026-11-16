"""Drawing in the player: the side strip, pen input, painting, Blue Pencil.

Player hooks (player.py):
    self.drawer = Drawer(self)            after the UI is built
    self.drawer.paint(p, target, frame)   after the live frame is drawn
    self.drawer.ticks()                   frames with drawings, for the cache bar
    self.drawer.press/move/release(...)   pen and mouse input in Draw mode
    KeyMap(cfg["hotkeys"])                your Maya playback keys

Everything about strokes, layers and files is in drawing.py (no Qt there).
"""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)
from bgcache.drawui_icons import *  # noqa: F401,F403
from bgcache.drawui_icons import icon, paint_strokes, ICONS  # noqa: F401
from bgcache.drawui_people import PeopleMixin, BlueRow  # noqa: F401
from bgcache.drawui_saving import SavingMixin
from bgcache.drawui_strokes import StrokesMixin
from bgcache.drawui_widgets import *  # noqa: F401,F403
from bgcache.drawui_widgets import _head, _button, _is_dark, _line  # noqa: F401
from bgcache.drawui_panel import DrawPanel  # noqa: F401


_PUNCT = {",": ("Key_Comma", "Key_Less"), ".": ("Key_Period", "Key_Greater"),
          "/": ("Key_Slash", "Key_Question"), ";": ("Key_Semicolon", "Key_Colon"),
          "'": ("Key_Apostrophe", "Key_QuoteDbl"), "[": ("Key_BracketLeft", "Key_BraceLeft"),
          "]": ("Key_BracketRight", "Key_BraceRight"), "\\": ("Key_Backslash", "Key_Bar"),
          "-": ("Key_Minus", "Key_Underscore"), "=": ("Key_Equal", "Key_Plus"),
          "`": ("Key_QuoteLeft", "Key_AsciiTilde")}


def qt_keys(name):
    """Qt key codes a Maya key string can arrive as."""
    if len(name) == 1 and name.isalpha():
        return {getattr(Qt, "Key_" + name.upper())}
    if len(name) == 1 and name.isdigit():
        return {getattr(Qt, "Key_" + name)}
    if name in _PUNCT:
        return {getattr(Qt, n) for n in _PUNCT[name] if hasattr(Qt, n)}
    alias = {"Page_Up": "Key_PageUp", "Page_Down": "Key_PageDown"}.get(name, "Key_" + name)
    return {getattr(Qt, alias)} if hasattr(Qt, alias) else set()


def _mods(event):
    m = event.modifiers()
    return (bool(m & Qt.AltModifier), bool(m & Qt.ControlModifier), bool(m & Qt.ShiftModifier))


class KeyMap(object):
    """Which player action a key press is, from your Maya hotkeys."""

    def __init__(self, keys):
        actions = (keys or {}).get("actions") or {}
        self.specs = {a: list(actions.get(a) or hotkeys.DEFAULTS.get(a, []))
                      for a, _ in hotkeys.ACTIONS}
        self.table = []
        for action, specs in self.specs.items():
            for spec in specs:
                for code in qt_keys(spec.get("key", "")):
                    self.table.append((code, bool(spec.get("alt")), bool(spec.get("ctrl")),
                                       bool(spec.get("shift")), action, spec))

    def action(self, event):
        code, (alt, ctrl, shift) = event.key(), _mods(event)
        for k, a, c, s, action, spec in self.table:
            if k != code or a != alt or c != ctrl:
                continue
            letter = len(spec.get("key", "")) == 1 and spec["key"].isalpha()
            if letter and s != shift:
                continue
            return action
        return None

    def is_key(self, action, event):
        """For key releases (scrub key): same key, ignoring modifiers."""
        return any(k == event.key() for k, _a, _c, _s, act, _sp in self.table if act == action)

    def taken(self, code, alt=False, ctrl=False, shift=False):
        return any(k == code and a == alt and c == ctrl for k, a, c, s, _act, _sp in self.table)

    def label(self, action):
        return " / ".join(hotkeys.spec_text(s) for s in self.specs.get(action) or []) or "-"


class Drawer(PeopleMixin, SavingMixin, StrokesMixin):
    """Drawing state for the player: rows, input, painting, saving.

    Other people's drawings: you see a snapshot of their file (the version
    you accepted), kept in ~/.bgcache/drawings_seen/, until you press Update
    on their heading; Revert goes back to the version before. Their layers
    are always locked; Duplicate copies one into your own file to edit."""

    UPDATE_CHECK_MS = 2000

    def __init__(self, player):
        self.player = player
        cfg = player.cfg
        self.W = int(cfg.get("width") or 960)
        self.H = int(cfg.get("height") or 540)
        self.user = cfg.get("user") or drawing.user_name()
        self.root = cfg.get("drawings_root") or drawing.drawings_root(cfg.get("original_scene"))
        # used when the drawings folder can't be written
        self.fallback_root = os.path.join(os.path.expanduser("~"), ".bgcache", "drawings",
                                          "%s_%s" % tuple(player.shot_ids[:2]) if player.shot_ids else
                                          "local_" + re.sub(r"[^A-Za-z0-9_.-]+", "_", self.root).strip("_")[-80:])
        self.seen_root = os.path.join(os.path.expanduser("~"), ".bgcache", "drawings_seen",
                                      re.sub(r"[^A-Za-z0-9_.-]+", "_", player.live_shot or self.root))
        prefs = player.prefs.setdefault("drawing", {})
        self.tool = prefs.get("tool", "pen")
        self.pen_size = float(prefs.get("size", 6))
        self.eraser_size = float(prefs.get("eraser_size", 20))
        self.color = prefs.get("color", drawing.COLORS[1])
        self.custom = prefs.get("custom_color")     # the colour picked for the custom swatch
        self.hold = bool(prefs.get("hold", True))
        self.onion = bool(prefs.get("onion", True))
        # b12: how many drawings onion skin shows before and after (0-5 each)
        self.onion_before = min(drawing.ONION_MAX, max(0, int(prefs.get("onion_before", 1))))
        self.onion_after = min(drawing.ONION_MAX, max(0, int(prefs.get("onion_after", 1))))
        self.show = bool(prefs.get("show", True))
        # Paper: 0 = the movie, 1 = white paper. Kept while Draw goes off and on,
        # but only for this session: every Start begins at 0 (never saved).
        self.paper = 0.0
        self.on = False
        self.mine = {}            # camera folder -> Drawings
        self.people = {}          # camera folder -> [person row, see _open_person]
        self.blue = {}            # camera folder -> [BlueRow]
        self.selected = None      # imported row key selected (for the trash button)
        self.stroke = None        # stroke being drawn
        self.erasing = False
        self.erase_whole = False
        self.hover = None         # pointer position (frame pixels) for the size circle
        self.saved_warned = False
        self.panel = None
        self._roots = {}          # b8: shot -> its drawings folder (None: unknown)
        self.timer = None
        self.recovery_timer = None
        try:
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self.check_updates)
            self.timer.start(self.UPDATE_CHECK_MS)
            self.recovery_timer = QtCore.QTimer()
            self.recovery_timer.setSingleShot(True)
            self.recovery_timer.timeout.connect(self.write_recovery)
        except Exception:  # no Qt event loop yet (tests): no update checks, recovery written at once
            self.timer = self.recovery_timer = None

    # ------------------------------------------------------------ sizes
    @property
    def size(self):
        return self.eraser_size if self.tool == "eraser" else self.pen_size

    @size.setter
    def size(self, value):
        if self.tool == "eraser":
            self.eraser_size = float(value)
        else:
            self.pen_size = float(value)

    # ------------------------------------------------------------ where you draw (b8)
    # Your own shot: its drawings folder, the camera you view. A shot of the
    # sequence around yours (continuity): that shot's drawings folder, under
    # your name, in that shot's camera folder; so its own artist can import
    # your drawings like anyone else's. Keys: the camera folder for your shot,
    # "<camera folder>@<shot>" for another shot.
    def cam(self):
        """The key of where drawing goes now (see above), or None."""
        place = self.place()
        return place["key"] if place else None

    def place(self, pos=None):
        """{"key", "root", "folder", "shot", "frame"} for the picture at pos
        (default: on screen), or None: no camera, or a shot whose drawings
        folder isn't known."""
        pl = self.player
        if not pl.view:
            return None
        live = drawing.camera_folder(pl.view)
        segments = getattr(pl, "segments", None)
        if not segments:          # before the reel is built: your shot
            try:
                frame = pl.current_live_frame() if hasattr(pl, "current_live_frame") else None
            except (IndexError, KeyError, AttributeError):    # the player isn't set up yet
                frame = None
            return {"key": live, "root": self.root, "folder": live, "shot": None, "frame": frame,
                    "first": getattr(pl, "start", None) or True, "last": getattr(pl, "end", None)}
        seg, local = pl._locate(pl.pos if pos is None else pos)
        if seg["kind"] == "live":
            return {"key": live, "root": self.root, "folder": live, "shot": None, "frame": pl.start + local,
                    "first": pl.start, "last": getattr(pl, "end", None)}
        shot = seg.get("shot")
        root = self.root_for(shot)
        if not root:
            return None
        folder = self.folder_for(shot)
        return {"key": "%s@%s" % (folder, shot), "root": root, "folder": folder, "shot": shot,
                "frame": int(seg.get("first") or 0) + local, "first": int(seg.get("first") or 0),
                "last": int(seg.get("first") or 0) + int(seg.get("n") or 1) - 1}

    def root_for(self, shot):
        """Another shot's drawings folder (the profile's drawings_folder with
        that shot filled in), or None when the profile doesn't say."""
        if not shot or shot == self.player.live_shot:
            return self.root
        if shot in self._roots:
            return self._roots[shot]
        root = None
        template = profile.get("drawings_folder")
        fields = profile.match_shot(self.player.cfg.get("original_scene") or "") if template else None
        if fields:
            try:
                root = profile.fill(template, profile.shot_fields(fields.get("show") or "", shot))
            except (KeyError, ValueError) as error:
                print("bgcache player: no drawings folder for %s (%s)" % (shot, error))
        self._roots[shot] = root
        return root

    def folder_for(self, shot):
        """The camera folder on another shot: your camera's name with your
        shot's name in it swapped for that shot's (m0850_0630_cam ->
        m0850_0640_cam); a camera named the same in every shot stays as it is."""
        mine = drawing.camera_folder(self.player.view)
        live = self.player.live_shot or ""
        if live and shot and live.lower() in mine.lower():
            i = mine.lower().index(live.lower())
            return mine[:i] + shot + mine[i + len(live):]
        return mine

    def _root_of(self, key):
        return self.root if "@" not in (key or "") else self.root_for(key.split("@", 1)[1])

    @staticmethod
    def _folder_of(key):
        return (key or "").split("@", 1)[0]

    def _fallback_of(self, key):
        """Where your drawings go when the shot's folder can't be written."""
        if "@" not in (key or ""):
            return self.fallback_root
        return os.path.join(self.fallback_root, "other_shots", key.split("@", 1)[1])

    def hold_from(self, place=None):
        """What to pass as hold: False with Hold off; else the first frame of
        the shot on screen as you have it (b10), so drawings outside your
        frames never show, held or not, until those frames are yours too."""
        if not self.hold:
            return False
        place = place or self.place()
        return place.get("first", True) if place else True

    def frame_now(self):
        """The frame drawing goes to on screen (yours or another shot's), or None."""
        place = self.place()
        return place["frame"] if place else None

    def follow_place(self):
        """The picture moved to another shot: the strip shows that shot's layers."""
        key = self.cam()
        if key != getattr(self, "_last_key", None):
            self._last_key = key
            if self.panel is not None and self.on:
                self.panel.refresh()

    # ------------------------------------------------------------ rows

    def _rows_pref(self, cam=None):
        rows = self.player.prefs.setdefault("drawing_rows", {})
        return rows.setdefault("%s|%s" % (self.player.live_shot or self.root, cam or self.cam()), {})

    def mine_now(self, cam=None):
        cam = cam or self.cam()
        if cam is None:
            return None
        if cam not in self.mine:
            path = drawing.layers_path(self._root_of(cam), self.user, self._folder_of(cam))
            if not os.path.isfile(path):
                alt = drawing.layers_path(self._fallback_of(cam), self.user, self._folder_of(cam))
                if os.path.isfile(alt):
                    path = alt
            self.mine[cam] = drawing.Drawings(path, (self.W, self.H), owner=self.user)
            if self.mine[cam].recovery():
                QtCore.QTimer.singleShot(0, lambda c=cam: self.offer_recovery(c))   # never inside a paint
        self._ensure_linked(cam)
        return self.mine[cam]

    def _why_not_here(self):
        if not self.player.view:
            return "Pick a camera to draw on"
        if profile.get("drawings_folder") and not profile.match_shot(self.player.cfg.get("original_scene") or ""):
            return ("Can't draw on this shot: your scene isn't in a shot folder, so the shots around it "
                    "can't be found (open your shot's scene, not a copy or recovery file)")
        return ("Can't draw on this shot: the profile doesn't say where its drawings go "
                "(drawings_folder)")

    def _ensure_linked(self, cam):
        if cam in self.people:
            return
        pref = self._rows_pref(cam)
        self.people[cam] = [self._open_person(entry["user"], cam, entry) for entry in pref.get("people", [])]
        self._add_new_people(cam)
        blue = []
        for entry in pref.get("blue", []):
            try:
                blue.append(BlueRow(entry["path"], entry.get("visible", True), entry.get("opacity", 1.0)))
            except Exception as error:
                self.player._flash_message("Couldn't read %s: %s" % (os.path.basename(entry["path"]), error))
        self.blue[cam] = blue

    # ------------------------------------------------------------ changes
    def changed(self, rebuild=True):
        if self.panel is not None and rebuild:
            self.panel.refresh()
        self.player.canvas.update()

    def set_on(self, on):
        self.on = on
        if self.panel is not None:
            self.panel.setVisible(on)
            self.panel.refresh()
        self.player.canvas.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)
        try:
            self.player.canvas.setMouseTracking(True)       # the size circle; b4: the focus handles' hover
        except Exception:  # cosmetic only (the size circle)
            pass
        if not on:
            self.hover = None
        self.player.update_draw_buttons()
        self.player.canvas.update()

    def _blocked(self, mine):
        if getattr(mine, "blocked", ""):
            self.player._flash_message("Can't: %s (unlock it first)" % mine.blocked)

    def undo(self):
        mine = self.mine_now()
        if mine and mine.undo():
            self.edited()
            self.changed()
            return True
        if mine:
            self._blocked(mine)
        return False

    def redo(self):
        mine = self.mine_now()
        if mine and mine.redo():
            self.edited()
            self.changed()
            return True
        if mine:
            self._blocked(mine)
        return False

    def clear(self):
        mine = self.mine_now()
        frame = self.frame_now()
        if mine is None or frame is None:
            return
        why = mine.drawable()
        if why:
            self.player._flash_message("Can't clear: %s" % why)
            return
        if mine.clear_frame(frame, self.hold_from()):
            self.edited()
            self.changed()
