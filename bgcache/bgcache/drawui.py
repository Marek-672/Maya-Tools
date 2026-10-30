"""Drawing in the player: the side strip, pen input, painting, Blue Pencil.

Player hooks (player.py):
    self.drawer = Drawer(self)            after the UI is built
    self.drawer.paint(p, target, frame)   after the live frame is drawn
    self.drawer.ticks()                   frames with drawings, for the cache bar
    self.drawer.press/move/release(...)   pen and mouse input in Draw mode
    KeyMap(cfg["hotkeys"])                your Maya playback keys

Everything about strokes, layers and files is in drawing.py (no Qt there).
"""
import collections
import os
import re
import time
import zipfile

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets

from bgcache import drawing
from bgcache import hotkeys

Qt = QtCore.Qt
ORANGE = QtGui.QColor(224, 138, 69)
DRAW_STYLE = """
QWidget#drawStrip { background: #1e1e1e; border-left: 1px solid #333; }
QLabel#head { color: #9a9a9a; font-size: 11px; }
QLabel#hint { color: #a8a8a8; font-size: 11px; background: #262626; border-radius: 3px; padding: 6px; }
QToolButton#swatch { background: transparent; border: none; padding: 0; }
QScrollArea#layers { background: #1e1e1e; border: 1px solid #2c2c2c; border-radius: 3px; }
QWidget#layersView, QWidget#layerList { background: #1e1e1e; }
QLabel { color: #cfcfcf; }
QToolButton { color: #ebebeb; background: #343434; border: 1px solid #4a4a4a; border-radius: 3px; padding: 3px 8px; font-size: 12px; }
QToolButton:checked { background: #3d5a73; border-color: #4f7393; color: #f0f0f0; }
QToolButton:hover { background: #3d3d3d; }
QToolButton:checked:hover { background: #46667f; }
QToolButton::menu-indicator { image: none; }
QToolButton#flat { background: transparent; border: none; padding: 1px; }
QToolButton#flat:hover { background: #3a3a3a; }
QToolButton#opacity { background: transparent; border: none; color: #bdbdbd; font-size: 10px; padding: 1px 3px; }
QToolButton#opacity:hover { background: #3a3a3a; }
QToolButton#dup { padding: 1px 3px; }
QFrame#row { border: 1px solid transparent; border-radius: 3px; }
QFrame#row[active="true"] { background: #3a4f63; border-color: #5f84a8; }
QFrame#head { border: 1px solid transparent; border-top-color: #333; border-radius: 0; }
QFrame#head[update="true"] { background: #3a2c1e; border: 1px solid #b8662a; border-radius: 3px; }
QToolButton#update { background: #b8662a; border: 1px solid #e08a45; color: #fff4e8; font-weight: bold; font-size: 11px; padding: 1px 9px; }
QToolButton#update:hover { background: #c9733a; }
QToolButton#revert { font-size: 11px; padding: 1px 9px; }
QToolButton#save { background: #b8662a; border: 1px solid #e08a45; color: #fff4e8; font-weight: bold; padding: 6px 8px; }
QToolButton#save:hover { background: #c9733a; }
QToolButton#save:disabled { background: #2c2c2c; border-color: #3a3a3a; color: #777; font-weight: normal; }
QLabel#unsaved { color: #f5c27a; font-size: 11px; }
QSpinBox { background: #262626; color: #e6e6e6; border: 1px solid #4a4a4a; border-radius: 3px; font-size: 12px; }
QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }
QSlider::handle:horizontal { background: #9ec3e6; width: 12px; margin: -5px 0; border-radius: 6px; }
"""


# --------------------------------------------------------------------------
# Keys: your Maya hotkeys in the player
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Icons
# --------------------------------------------------------------------------
def icon(kind, color="#d6d6d6", size=16):
    """A small line icon (16 px drawing, scaled to size) for the drawing
    strip and the player: kind is one of ICONS."""
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    pen = QtGui.QPen(QtGui.QColor(color), 1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = size / 16.0
    p.scale(s, s)
    path = QtGui.QPainterPath()
    draw = ICONS.get(kind)
    if draw is not None:
        draw(p, path, color, kind)
    p.end()
    return QtGui.QIcon(pm)


def _icon_eye(p, path, color, kind):
    """An eye (layer shown); eye_off adds a slash (hidden)."""
    path.moveTo(1.5, 8)
    path.quadTo(8, 1.5, 14.5, 8)
    path.quadTo(8, 14.5, 1.5, 8)
    p.drawPath(path)
    p.drawEllipse(QtCore.QPointF(8, 8), 2.2, 2.2)
    if kind == "eye_off":
        p.drawLine(QtCore.QPointF(2.5, 13.5), QtCore.QPointF(13.5, 2.5))


def _icon_lock(p, path, color, kind):
    """A closed padlock with a tinted body: clearly locked."""
    body = QtCore.QRectF(3, 7.5, 10, 7)
    tint = QtGui.QColor(color)
    tint.setAlpha(70)
    p.fillRect(body.adjusted(0.5, 0.5, -0.5, -0.5), tint)
    p.drawRoundedRect(body, 1, 1)
    path.moveTo(5.5, 7.5)
    path.lineTo(5.5, 5)
    path.arcTo(QtCore.QRectF(5.5, 2.5, 5, 5), 180, -180)
    path.lineTo(10.5, 7.5)
    p.drawPath(path)


def _icon_unlock(p, path, color, kind):
    """An open padlock: body to the right, shackle swung open to the left."""
    p.drawRoundedRect(QtCore.QRectF(6, 8, 8, 6), 1, 1)
    path.moveTo(8.5, 8)
    path.lineTo(8.5, 5.5)
    path.arcTo(QtCore.QRectF(3.5, 3, 5, 5), 0, 180)
    path.lineTo(3.5, 7)
    p.drawPath(path)


def _icon_copy(p, path, color, kind):
    """Two sheets (duplicate)."""
    p.drawRoundedRect(QtCore.QRectF(2.5, 5.5, 8, 8.5), 1, 1)
    path.moveTo(5.5, 5.5)
    path.lineTo(5.5, 2.5)
    path.lineTo(13.5, 2.5)
    path.lineTo(13.5, 11)
    path.lineTo(10.5, 11)
    p.drawPath(path)


def _icon_person(p, path, color, kind):
    """Head and shoulders (someone's drawings)."""
    p.drawEllipse(QtCore.QPointF(8, 5.5), 2.6, 2.6)
    path.moveTo(3, 14)
    path.cubicTo(3.5, 10, 12.5, 10, 13, 14)
    p.drawPath(path)


def _icon_plus(p, path, color, kind):
    """A plus (new layer)."""
    p.drawLine(QtCore.QPointF(8, 3), QtCore.QPointF(8, 13))
    p.drawLine(QtCore.QPointF(3, 8), QtCore.QPointF(13, 8))


def _icon_arrow(p, path, color, kind):
    """A chevron pointing up or down (move a layer)."""
    y0, y1 = (10, 5) if kind == "up" else (6, 11)
    path.moveTo(4, y0)
    path.lineTo(8, y1)
    path.lineTo(12, y0)
    p.drawPath(path)


def _icon_trash(p, path, color, kind):
    """A bin (delete)."""
    p.drawLine(QtCore.QPointF(3, 4.5), QtCore.QPointF(13, 4.5))
    path.moveTo(6.5, 4.5)
    path.lineTo(6.5, 2.5)
    path.lineTo(9.5, 2.5)
    path.lineTo(9.5, 4.5)
    path.moveTo(4.5, 4.5)
    path.lineTo(5.3, 14)
    path.lineTo(10.7, 14)
    path.lineTo(11.5, 4.5)
    p.drawPath(path)


def _icon_reload(p, path, color, kind):
    """A circular arrow (update)."""
    p.drawArc(QtCore.QRectF(3, 3, 10, 10), 30 * 16, 290 * 16)
    path.moveTo(13, 2.5)
    path.lineTo(13, 6)
    path.lineTo(9.5, 6)
    p.drawPath(path)


def _icon_pen(p, path, color, kind):
    """A pen (Draw)."""
    path.moveTo(3, 13)
    path.lineTo(4, 9.5)
    path.lineTo(11, 2.5)
    path.lineTo(13.5, 5)
    path.lineTo(6.5, 12)
    path.closeSubpath()
    p.drawPath(path)


def _icon_x(p, path, color, kind):
    """A cross (remove)."""
    p.drawLine(QtCore.QPointF(4.5, 4.5), QtCore.QPointF(11.5, 11.5))
    p.drawLine(QtCore.QPointF(11.5, 4.5), QtCore.QPointF(4.5, 11.5))


def _icon_opacity(p, path, color, kind):
    """A half-filled circle (opacity)."""
    p.drawEllipse(QtCore.QPointF(8, 8), 5.5, 5.5)
    half = QtGui.QPainterPath()
    half.moveTo(8, 2.5)
    half.arcTo(QtCore.QRectF(2.5, 2.5, 11, 11), 90, -180)
    half.closeSubpath()
    p.fillPath(half, QtGui.QBrush(QtGui.QColor(color)))


ICONS = {
    "eye": _icon_eye,
    "eye_off": _icon_eye,
    "lock": _icon_lock,
    "unlock": _icon_unlock,
    "copy": _icon_copy,
    "person": _icon_person,
    "plus": _icon_plus,
    "up": _icon_arrow,
    "down": _icon_arrow,
    "trash": _icon_trash,
    "reload": _icon_reload,
    "pen": _icon_pen,
    "x": _icon_x,
    "opacity": _icon_opacity,
}


# --------------------------------------------------------------------------
# Painting strokes
# --------------------------------------------------------------------------
def paint_strokes(p, strokes, opacity=1.0, tint=None):
    """Strokes in frame pixels; the painter is already mapped to the frame."""
    if not strokes or opacity <= 0:
        return
    p.save()
    p.setOpacity(p.opacity() * opacity)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    for st in strokes:
        pts = st.get("p") or []
        if not pts:
            continue
        color = QtGui.QColor(tint or st.get("c") or "#e8c547")
        width = float(st.get("w", 4.0))
        pressures = [pt[2] if len(pt) > 2 else 1.0 for pt in pts]
        if len(pts) == 1:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            r = width * pressures[0] / 2.0
            p.drawEllipse(QtCore.QPointF(pts[0][0], pts[0][1]), r, r)
            continue
        if min(pressures) > 0.999:
            path = QtGui.QPainterPath(QtCore.QPointF(pts[0][0], pts[0][1]))
            for pt in pts[1:]:
                path.lineTo(pt[0], pt[1])
            pen = QtGui.QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        else:
            for a, b, pa, pb in zip(pts, pts[1:], pressures, pressures[1:]):
                pen = QtGui.QPen(color, max(0.5, width * (pa + pb) / 2.0), Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(QtCore.QPointF(a[0], a[1]), QtCore.QPointF(b[0], b[1]))
    p.restore()


# --------------------------------------------------------------------------
# What's drawn: your layers, linked people, Blue Pencil zips
# --------------------------------------------------------------------------
class BlueRow(object):
    """A Blue Pencil zip shown over the playback (read-only)."""

    def __init__(self, path, visible=True, opacity=1.0):
        self.path = path
        self.visible = visible
        self.opacity = opacity
        self.info = drawing.read_bp_zip(path)
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.frames = {}                     # frame -> [member per layer]
        for layer in self.info["layers"]:
            for frame, member in layer["frames"].items():
                self.frames.setdefault(frame, []).append(member)
        self.cache = collections.OrderedDict()

    def image(self, member, frame_w, frame_h, k):
        """The member's drawing cut to the cached frame and scaled to it."""
        if member in self.cache:
            self.cache.move_to_end(member)
            return self.cache[member]
        with zipfile.ZipFile(self.path) as z:
            img = QtGui.QImage.fromData(z.read(member))
        x0, y0 = drawing.frame_to_bp(0, 0, frame_w, frame_h, k)
        region = QtCore.QRect(int(round(x0)), int(round(y0)),
                              int(round(frame_w * k)), int(round(frame_h * k)))
        out = img.copy(region).scaled(frame_w, frame_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.cache[member] = out
        while len(self.cache) > 24:
            self.cache.popitem(last=False)
        return out


class Drawer(object):
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

    # ------------------------------------------------------------ rows
    def cam(self):
        return drawing.camera_folder(self.player.view) if self.player.view else None

    def _rows_pref(self, cam=None):
        rows = self.player.prefs.setdefault("drawing_rows", {})
        return rows.setdefault("%s|%s" % (self.player.live_shot or self.root, cam or self.cam()), {})

    def mine_now(self):
        cam = self.cam()
        if cam is None:
            return None
        if cam not in self.mine:
            path = drawing.layers_path(self.root, self.user, cam)
            if not os.path.isfile(path):
                alt = drawing.layers_path(self.fallback_root, self.user, cam)
                if os.path.isfile(alt):
                    path = alt
            self.mine[cam] = drawing.Drawings(path, (self.W, self.H), owner=self.user)
            if self.mine[cam].recovery():
                QtCore.QTimer.singleShot(0, lambda c=cam: self.offer_recovery(c))   # never inside a paint
        self._ensure_linked(cam)
        return self.mine[cam]

    def _ensure_linked(self, cam):
        if cam in self.people:
            return
        pref = self._rows_pref(cam)
        self.people[cam] = [self._open_person(entry["user"], cam, entry) for entry in pref.get("people", [])]
        blue = []
        for entry in pref.get("blue", []):
            try:
                blue.append(BlueRow(entry["path"], entry.get("visible", True), entry.get("opacity", 1.0)))
            except Exception as error:
                self.player._flash_message("Couldn't read %s: %s" % (os.path.basename(entry["path"]), error))
        self.blue[cam] = blue

    # ------------------------------------------------------------ people (snapshots)
    def _seen_path(self, user, cam, prev=False):
        return os.path.join(self.seen_root, cam, "%s%s.json" % (user, ".prev" if prev else ""))

    @staticmethod
    def _copy(src, dst):
        folder = os.path.dirname(dst)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(src, "rb") as a, open(dst + ".tmp", "wb") as b:
            b.write(a.read())
        os.replace(dst + ".tmp", dst)

    @staticmethod
    def _meta(info):
        return {"rev": info[0], "mtime": info[1], "size": info[2]} if info else None

    def _open_person(self, user, cam, entry=None):
        """A person's row: their drawings as you accepted them (a snapshot),
        and your view of their layers (visible, opacity)."""
        entry = entry or {}
        live = drawing.layers_path(self.root, user, cam)
        seen = self._seen_path(user, cam)
        accepted = entry.get("accepted")
        if not os.path.isfile(seen) and os.path.isfile(live):
            try:
                self._copy(live, seen)
                accepted = self._meta(drawing.file_rev(live))
            except (IOError, OSError):
                seen = live
        row = {"user": user, "cam": cam, "live": live, "seen": seen,
               "accepted": accepted, "prev": entry.get("prev"),
               "view": dict(entry.get("view") or {}), "status": "current",
               "drawings": drawing.Drawings(seen, (self.W, self.H), read_only=True, owner=user)}
        self._status(row)
        return row

    def _status(self, row):
        """"update" (they've saved a newer version than the one you see),
        "revert" (you updated; the version before can come back), or
        "current"."""
        live = self._meta(drawing.file_rev(row["live"]))
        acc = row.get("accepted")
        if live and (not acc or (live["rev"], live["mtime"], live["size"]) !=
                     (acc.get("rev"), acc.get("mtime"), acc.get("size"))):
            row["status"] = "update"
        elif row.get("prev") and os.path.isfile(self._seen_path(row["user"], row["cam"], prev=True)):
            row["status"] = "revert"
        else:
            row["status"] = "current"
        return row["status"]

    def person(self, user, cam=None):
        cam = cam or self.cam()
        self._ensure_linked(cam)
        return next((r for r in self.people.get(cam, []) if r["user"] == user), None)

    def update_person(self, user):
        """Show their newest drawings; the ones you had can come back (Revert)."""
        row = self.person(user)
        if row is None:
            return
        cam = row["cam"]
        try:
            if os.path.isfile(row["seen"]) and row["seen"] != row["live"]:
                self._copy(row["seen"], self._seen_path(user, cam, prev=True))
                row["prev"] = row.get("accepted") or {"rev": row["drawings"].rev}
            self._copy(row["live"], self._seen_path(user, cam))
            row["seen"] = self._seen_path(user, cam)
            row["accepted"] = self._meta(drawing.file_rev(row["live"]))
        except (IOError, OSError) as error:
            self.player._flash_message("Couldn't update %s's drawings: %s" % (user, error), 5.0)
            return
        row["drawings"] = drawing.Drawings(row["seen"], (self.W, self.H), read_only=True, owner=user)
        self._status(row)
        self._save_rows(cam)
        self.player._flash_message("Showing %s's newest drawings (Revert brings back the ones you had)" % user)
        self.changed()

    def revert_person(self, user):
        """Back to the version you had before your last Update."""
        row = self.person(user)
        prev = self._seen_path(user, row["cam"], prev=True) if row else None
        if not prev or not os.path.isfile(prev):
            return
        try:
            self._copy(prev, self._seen_path(user, row["cam"]))
            os.remove(prev)
        except (IOError, OSError) as error:
            self.player._flash_message("Couldn't revert %s's drawings: %s" % (user, error), 5.0)
            return
        row["accepted"], row["prev"] = row.get("prev"), None
        row["seen"] = self._seen_path(user, row["cam"])
        row["drawings"] = drawing.Drawings(row["seen"], (self.W, self.H), read_only=True, owner=user)
        self._status(row)
        self._save_rows(row["cam"])
        self.player._flash_message("Back to the %s drawings you had before" % user)
        self.changed()

    def check_updates(self):
        """Every couple of seconds: has anyone you import saved a newer version?"""
        changed = False
        for cam, rows in list(self.people.items()):
            for row in rows:
                before = row["status"]
                if self._status(row) != before:
                    changed = True
        if changed:
            self.changed()
        return changed

    def _save_rows(self, cam=None):
        cam = cam or self.cam()
        pref = self._rows_pref(cam)
        pref["people"] = [{"user": r["user"], "view": r["view"], "accepted": r.get("accepted"),
                           "prev": r.get("prev")} for r in self.people.get(cam, [])]
        pref["blue"] = [{"path": b.path, "visible": b.visible, "opacity": b.opacity}
                        for b in self.blue.get(cam, [])]
        self.player._save_prefs()

    def save_prefs(self):
        self.player.prefs["drawing"] = {"tool": self.tool, "size": self.pen_size, "eraser_size": self.eraser_size,
                                        "color": self.color, "custom_color": self.custom,
                                        "hold": self.hold, "onion": self.onion, "show": self.show}
        self.player._save_prefs()

    @staticmethod
    def layer_view(row, layer):
        """(visible, opacity) of someone else's layer as you show it."""
        v = row["view"].get(layer["id"]) or {}
        return bool(v.get("visible", layer.get("visible", True))), float(v.get("opacity", layer.get("opacity", 1.0)))

    def rows(self):
        """Top first: your layers, then each person (a heading, then their
        layers), then Blue Pencil zips."""
        mine = self.mine_now()
        if mine is None:
            return []
        cam = self.cam()
        out = [{"kind": "me", "key": "me"}]
        out += [{"kind": "mine", "key": "m:" + l["id"], "layer": l} for l in mine.layers]
        for r in self.people.get(cam, []):
            out.append({"kind": "head", "key": "P:" + r["user"], "row": r})
            out += [{"kind": "person", "key": "p:%s:%s" % (r["user"], l["id"]), "row": r, "layer": l}
                    for l in r["drawings"].layers]
        out += [{"kind": "blue", "key": "b:" + b.path, "row": b} for b in self.blue.get(cam, [])]
        return out

    # ------------------------------------------------------------ saving (0.9.0b3)
    # Changes stay on your screen until Save (Ctrl+S); a private recovery copy
    # follows every change, so a crash loses almost nothing.
    RECOVERY_DELAY_MS = 400

    def edited(self):
        """A change to your drawings: unsaved until Save; recovery copy soon."""
        mine = self.mine_now()
        if mine is None:
            return
        mine.dirty = True
        if self.recovery_timer is not None:
            self.recovery_timer.start(self.RECOVERY_DELAY_MS)
        else:
            self.write_recovery()
        if self.panel is not None:
            self.panel.refresh_save()

    def write_recovery(self):
        for mine in self.mine.values():
            mine.write_recovery()

    def unsaved(self):
        """Cameras with unsaved drawings."""
        return [cam for cam, mine in self.mine.items() if mine.dirty]

    def save_now(self):
        """Save: your drawings go to the shared file, a new version. Returns
        True if everything was saved."""
        ok, warned = True, False
        for cam, mine in list(self.mine.items()):
            if not mine.dirty:
                continue
            error = mine.save()
            if error and not mine.path.startswith(self.fallback_root):
                mine.path = drawing.layers_path(self.fallback_root, self.user, cam)
                error2 = mine.save()
                if not self.saved_warned or error2:
                    self.saved_warned = warned = True
                    self.player._flash_message(
                        "Couldn't save in the shot folder (%s); saved in your home folder" % error
                        if not error2 else "Couldn't save drawings: %s" % error2, 6.0)
                ok = ok and not error2
            elif error:
                ok = False
                warned = True
                self.player._flash_message("Couldn't save drawings: %s" % error, 6.0)
        if ok and not warned:
            self.player._flash_message("Drawings saved", 2.0)
        if self.panel is not None:
            self.panel.refresh_save()
        self.player.canvas.update()
        return ok

    def ask_to_save(self, parent, doing="closing"):
        """Before Stop or closing with unsaved drawings: Save / Don't save /
        Cancel. True to carry on (saved or discarded), False to cancel."""
        if not self.unsaved():
            return True
        box = QtWidgets.QMessageBox(parent)
        box.setWindowTitle("bgcache")
        box.setText("Save your drawings before %s?" % doing)
        box.setInformativeText("Nobody else sees them until you save.")
        save = box.addButton("Save", QtWidgets.QMessageBox.AcceptRole)
        drop = box.addButton("Don't save", QtWidgets.QMessageBox.DestructiveRole)
        box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(save)
        (getattr(box, "exec", None) or box.exec_)()
        clicked = box.clickedButton()
        if clicked is save:
            return self.save_now()
        if clicked is drop:
            for mine in self.mine.values():
                if mine.dirty:
                    mine.clear_recovery()
                    mine.dirty = False
            return True
        return False

    def offer_recovery(self, cam):
        """Unsaved drawings left by a session that ended without Save (a
        crash): offer them back, once, when that camera's drawings open."""
        mine = self.mine.get(cam)
        data = mine.recovery() if mine is not None else None
        if not data:
            return
        when = time.strftime("%a %H:%M", time.localtime(data.get("written") or time.time()))
        box = QtWidgets.QMessageBox(self.player)
        box.setWindowTitle("bgcache")
        box.setText("Unsaved drawings from %s were found (%s)." % (when, cam))
        box.setInformativeText("bgcache kept them when the last session ended without Save. "
                               "Recover them? They stay unsaved until you press Save.")
        rec = box.addButton("Recover", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Discard", QtWidgets.QMessageBox.DestructiveRole)
        (getattr(box, "exec", None) or box.exec_)()
        if box.clickedButton() is rec:
            mine.recover(data)
            self.changed()
            if self.panel is not None:
                self.panel.refresh_save()
        else:
            mine.clear_recovery()

    def restore_version(self, path):
        mine = self.mine_now()
        if mine is None:
            return
        error = mine.restore(path)
        self.player._flash_message("Couldn't restore: %s" % error if error else "Earlier drawings restored and saved",
                                   5.0 if error else 3.0)
        self.changed()
        if self.panel is not None:
            self.panel.refresh_save()

    # ------------------------------------------------------------ people / Blue Pencil
    def find_people(self, cam=None, include_me=False):
        cam = cam or self.cam()
        return drawing.find_people(self.root, self.user, cam, include_me) if cam else []

    def is_linked(self, user, cam=None):
        cam = cam or self.cam()
        self._ensure_linked(cam)
        return any(r["user"] == user for r in self.people.get(cam, []))

    def set_linked(self, user, on, cam=None):
        cam = cam or self.cam()
        self._ensure_linked(cam)
        rows = self.people.setdefault(cam, [])
        if on and not self.is_linked(user, cam):
            rows.append(self._open_person(user, cam))
        elif not on:
            rows[:] = [r for r in rows if r["user"] != user]
            for path in (self._seen_path(user, cam), self._seen_path(user, cam, prev=True)):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self._save_rows(cam)
        self.changed()

    def duplicate(self, key):
        """Copy someone else's layer into your own layers, to edit it."""
        row = next((r for r in self.rows() if r["key"] == key and r["kind"] == "person"), None)
        mine = self.mine_now()
        if row is None or mine is None:
            return None
        user, layer = row["row"]["user"], row["layer"]
        lid = mine.duplicate_layer(layer, "%s: %s (copy)" % (user, layer["name"]),
                                   {"user": user, "layer": layer["name"]})
        self.selected = None
        self.edited()
        self.player._flash_message("Copied %s's %s into your layers: edit it there" % (user, layer["name"]))
        self.changed()
        return lid

    def add_blue(self, path):
        cam = self.cam()
        try:
            row = BlueRow(path)
        except Exception as error:
            self.player._flash_message("Couldn't read %s: %s" % (os.path.basename(path), error), 5.0)
            return
        if row.info.get("camera") and row.info["camera"] != cam:
            self.player._flash_message("Note: drawn on camera %s, you're viewing %s" % (row.info["camera"], cam), 5.0)
        self.blue.setdefault(cam, []).append(row)
        self._save_rows()
        self.changed()

    def remove_row(self, key):
        cam = self.cam()
        if self.selected == key:
            self.selected = None
        if key.startswith("P:"):
            self.set_linked(key[2:], False)
        elif key.startswith("p:"):
            self.set_linked(key.split(":")[1], False)
        elif key.startswith("b:"):
            self.blue[cam] = [b for b in self.blue.get(cam, []) if b.path != key[2:]]
            self._save_rows()
            self.changed()

    def row_value(self, key, name):
        for row in self.rows():
            if row["key"] != key:
                continue
            if row["kind"] == "mine":
                return row["layer"].get(name)
            if row["kind"] == "person":
                visible, opacity = self.layer_view(row["row"], row["layer"])
                return {"visible": visible, "opacity": opacity, "locked": True}.get(name)
            if row["kind"] == "blue":
                return getattr(row["row"], name, None)
        return None

    def set_row(self, key, **values):
        for row in self.rows():
            if row["key"] != key:
                continue
            if row["kind"] == "mine":
                row["layer"].update(values)
                self.edited()
            elif row["kind"] == "person":
                view = row["row"]["view"].setdefault(row["layer"]["id"], {})
                for name in ("visible", "opacity"):
                    if name in values:
                        view[name] = values[name]
                self._save_rows()
            elif row["kind"] == "blue":
                for name, value in values.items():
                    setattr(row["row"], name, value)
                self._save_rows()
        self.changed(rebuild=False)

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
            self.player.canvas.setMouseTracking(bool(on))       # for the size circle
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
        frame = self.player.current_live_frame()
        if mine is None or frame is None:
            return
        why = mine.drawable()
        if why:
            self.player._flash_message("Can't clear: %s" % why)
            return
        if mine.clear_frame(frame, self.hold):
            self.edited()
            self.changed()

    # ------------------------------------------------------------ input
    def _to_frame(self, point):
        t = getattr(self.player, "last_target", None)
        if t is None or t.width() <= 0:
            return None
        s = t.width() / float(self.W)
        return (point.x() - t.x()) / s, (point.y() - t.y()) / s

    def hover_at(self, point):
        """Pointer moved over the picture (None: left it): the size circle follows."""
        self.hover = self._to_frame(point) if point is not None else None
        if self.on:
            self.player.canvas.update()

    def _eraser_radius(self, pressure):
        """Half the eraser size; pen pressure makes it smaller (a light touch
        cuts thin). A mouse, or a tablet arriving as a mouse, has pressure 1."""
        p = pressure if 0.0 < pressure < 1.0 else 1.0
        return max(1.0, self.eraser_size / 2.0 * max(0.15, p))

    def press(self, point, pressure=1.0, eraser=False, whole=False):
        """Start a stroke (or erasing) at a canvas point. False: not drawing.
        whole=True (Shift): the eraser removes whole strokes."""
        frame = self.player.current_live_frame()
        mine = self.mine_now()
        if frame is None or mine is None:
            self.player._flash_message("Draw on your own shot's live frames")
            return False
        why = mine.drawable()
        if why:
            self.player._flash_message("Can't draw: %s" % why)
            return False
        if self.selected is not None:      # drawing goes to your layer: highlight it again
            self.selected = None
            if self.panel is not None:
                self.panel.refresh()
        pos = self._to_frame(point)
        if pos is None:
            return False
        self.frame = frame
        self.hover = pos
        if eraser or self.tool == "eraser":
            self.erasing = True
            self.erase_whole = bool(whole)
            mine.begin_group()
            if mine.erase_at(frame, pos[0], pos[1], self._eraser_radius(pressure), self.hold, whole=self.erase_whole):
                self.changed(rebuild=False)
            return True
        self.stroke = {"c": self.color, "w": float(self.pen_size), "p": [[pos[0], pos[1], round(pressure, 3)]]}
        self.player.canvas.update()
        return True

    def move(self, point, pressure=1.0):
        pos = self._to_frame(point)
        if pos is None:
            return
        self.hover = pos
        mine = self.mine_now()
        if self.erasing:
            if mine.erase_at(self.frame, pos[0], pos[1], self._eraser_radius(pressure), self.hold,
                             whole=self.erase_whole):
                self.changed(rebuild=False)
            else:
                self.player.canvas.update()
            return
        if self.stroke is None:
            return
        last = self.stroke["p"][-1]
        if (pos[0] - last[0]) ** 2 + (pos[1] - last[1]) ** 2 < 1.0:
            return
        # light smoothing: halfway towards the new point
        x = last[0] + (pos[0] - last[0]) * 0.6
        y = last[1] + (pos[1] - last[1]) * 0.6
        self.stroke["p"].append([round(x, 2), round(y, 2), round(pressure, 3)])
        self.player.canvas.update()

    def release(self, point=None):
        mine = self.mine_now()
        if self.erasing:
            self.erasing = False
            mine.end_group()
            self.edited()
            self.changed()
            return
        if self.stroke is None:
            return
        stroke, self.stroke = self.stroke, None
        if point is not None:
            pos = self._to_frame(point)
            if pos is not None and len(stroke["p"]) > 1:
                stroke["p"].append([round(pos[0], 2), round(pos[1], 2), stroke["p"][-1][2]])
        if mine.add_stroke(self.frame, stroke):
            self.edited()
        self.changed()

    # ------------------------------------------------------------ painting
    def ticks(self):
        """Frames with drawings in visible rows (for the cache bar)."""
        if not self.show:
            return set()
        mine = self.mine_now()
        if mine is None:
            return set()
        out = set(mine.drawn_frames())
        for row in self.people.get(self.cam(), []):
            for layer in row["drawings"].layers:
                if self.layer_view(row, layer)[0]:
                    out.update(int(k) for k in layer["frames"])
        for b in self.blue.get(self.cam(), []):
            if b.visible:
                out |= set(b.frames)
        return out

    PAPER_COLOR = (255, 255, 255)

    def paper_alpha(self):
        """0-255: how much the picture fades to white under the drawings
        (Paper, in Draw mode only)."""
        return int(round(255 * self.paper)) if self.on and self.paper > 0 else 0

    def paint_paper(self, p, target):
        """Lay the paper over the picture, under the drawings, so they read
        better. The movie itself is untouched."""
        alpha = self.paper_alpha()
        if alpha:
            r, g, b = self.PAPER_COLOR
            p.fillRect(target, QtGui.QColor(r, g, b, alpha))

    def paint(self, p, target, frame):
        """Drawings over the live frame drawn in `target` (canvas pixels)."""
        mine = self.mine_now()
        if mine is None:
            return
        s = target.width() / float(self.W)
        p.save()
        p.setClipRect(target)
        p.translate(target.x(), target.y())
        p.scale(s, s)
        cam = self.cam()
        if self.show:
            k = self._bp_k()
            for b in reversed(self.blue.get(cam, [])):
                if not b.visible:
                    continue
                key = drawing.held_key(b.frames, frame, self.hold) if self.hold else (frame if frame in b.frames else None)
                if key is None:
                    continue
                p.save()
                p.setOpacity(b.opacity)
                for member in b.frames[key]:
                    try:
                        p.drawImage(QtCore.QRectF(0, 0, self.W, self.H), b.image(member, self.W, self.H, k))
                    except Exception:  # one unreadable imported drawing must not stop the rest drawing
                        pass
                p.restore()
            for row in reversed(self.people.get(cam, [])):
                for layer in reversed(row["drawings"].layers):
                    visible, opacity = self.layer_view(row, layer)
                    if visible:
                        _key, strokes = row["drawings"].strokes_at(layer, frame, self.hold)
                        paint_strokes(p, strokes, opacity)
            active = mine.active_layer()
            for layer in reversed(mine.layers):
                if not layer["visible"]:
                    continue
                key, strokes = mine.strokes_at(layer, frame, self.hold)
                if self.on and self.onion and layer is active:
                    prev, nxt = drawing.neighbour_keys(layer["frames"], key if key is not None else frame)
                    for other, tint in ((prev, "#ff8a7a"), (nxt, "#7ad1ff")):
                        if other is not None and other != key:
                            paint_strokes(p, layer["frames"].get(str(other)), 0.25 * layer["opacity"], tint)
                paint_strokes(p, strokes, layer.get("opacity", 1.0))
        if self.stroke is not None:
            paint_strokes(p, [self.stroke])
        if self.on and self.hover is not None and not getattr(self.player, "playing", 0):
            # size circle: the pen's width, or what the eraser will take
            r = (self.eraser_size if self.tool == "eraser" else self.pen_size) / 2.0
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.0 / max(s, 0.01))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QtCore.QPointF(self.hover[0], self.hover[1]), r, r)
            pen.setColor(QtGui.QColor(0, 0, 0, 160))
            p.setPen(pen)
            p.drawEllipse(QtCore.QPointF(self.hover[0], self.hover[1]), r + 1.0 / max(s, 0.01),
                          r + 1.0 / max(s, 0.01))
        p.restore()

    # ------------------------------------------------------------ Blue Pencil
    def _gate(self):
        for cam in self.player.cfg.get("cameras") or []:
            if cam.get("name") == self.player.view:
                return cam.get("gate")
        return None

    def _bp_k(self):
        gate = self._gate()
        if not gate:
            return drawing.BP_SIZE / float(self.W)       # assume the square spans the frame
        return drawing.bp_scale(gate, self.W)

    def export_blue_pencil(self, path):
        """Your visible layers (and visible linked people) as a Blue Pencil zip.
        Returns (frames written, layers written)."""
        mine = self.mine_now()
        cam_name = (self.player.view or "camera").split("|")[-1]
        k = self._bp_k()
        stem = os.path.splitext(os.path.basename(path))[0]
        sources = [(l["name"], l) for l in mine.layers if l["visible"] and l["frames"]]
        for row in self.people.get(self.cam(), []):
            sources += [("%s_%s" % (row["user"], l["name"]), l)
                        for l in row["drawings"].layers if self.layer_view(row, l)[0] and l["frames"]]
        index, count = [], 0
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name, layer in sources:
                safe = re.sub(r"[\\/:*?\"<>|]+", "_", name)
                frames = []
                for key in sorted(layer["frames"], key=int):
                    img = QtGui.QImage(drawing.BP_SIZE, drawing.BP_SIZE, QtGui.QImage.Format_ARGB32_Premultiplied)
                    img.fill(Qt.transparent)
                    p = QtGui.QPainter(img)
                    x0, y0 = drawing.frame_to_bp(0, 0, self.W, self.H, k)
                    p.translate(x0, y0)
                    p.scale(k, k)
                    paint_strokes(p, layer["frames"][key])
                    p.end()
                    data = QtCore.QByteArray()
                    buf = QtCore.QBuffer(data)
                    buf.open(QtCore.QIODevice.WriteOnly)
                    img.save(buf, "PNG")
                    buf.close()
                    filename = "%s_%s_%d.png" % (cam_name, safe, int(key))
                    z.writestr("%s/%s" % (stem, filename), data.data())
                    frames.append((int(key), filename))
                    count += 1
                    if count % 5 == 0:
                        self.player._flash_message("Exporting to Blue Pencil... %d frames" % count)
                        QtWidgets.QApplication.processEvents()
                index.append((name, True, frames))
            z.writestr("%s/%s.xml" % (stem, stem), drawing.bp_xml(cam_name, index))
        os.replace(tmp, path)
        return count, len(index)


# --------------------------------------------------------------------------
# The side strip
# --------------------------------------------------------------------------
def _head(text):
    label = QtWidgets.QLabel(text.upper())
    label.setObjectName("head")
    return label


def _button(text=None, tip=None, kind=None, checkable=False, object_name=None):
    b = QtWidgets.QToolButton()
    if text:
        b.setText(text)
    if kind:
        b.setIcon(icon(kind))
    if tip:
        b.setToolTip(tip)
    b.setCheckable(checkable)
    if object_name:
        b.setObjectName(object_name)
    b.setFocusPolicy(Qt.NoFocus)
    return b


class SizeDot(QtWidgets.QWidget):
    def __init__(self, drawer):
        super(SizeDot, self).__init__()
        self.drawer = drawer
        self.setFixedSize(28, 28)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor(38, 38, 38))
        r = max(1.0, min(12.0, self.drawer.size / 2.0))
        if self.drawer.tool == "eraser":            # the eraser: an outline of its size
            p.setPen(QtGui.QPen(QtGui.QColor("#e6e6e6"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QtCore.QPointF(14, 14), r, r)
            p.end()
            return
        color = QtGui.QColor(self.drawer.color)
        p.setPen(QtGui.QPen(QtGui.QColor("#8a8a8a"), 1) if _is_dark(color) else Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QtCore.QPointF(14, 14), r, r)
        p.end()


def _is_dark(color):
    try:
        return int(color.lightness()) < 70
    except Exception:  # not a QColor: treat as light
        return False


class Swatch(QtWidgets.QToolButton):
    """A colour circle (26 px). The selected one has an orange bar under it.
    custom=True: the custom colour, a rainbow ring (36 px) around it with a
    1 px black ring between; dark with a white + until a colour is picked."""
    DOT = 26
    RING = 36

    def __init__(self, color=None, tip=None, custom=False):
        super(Swatch, self).__init__()
        self.color, self.custom = color, custom
        self.setObjectName("swatch")
        self.setCheckable(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)
        self.setFixedSize((self.RING if custom else self.DOT) + 2, self.RING + 8)

    def set_color(self, color):
        self.color = color
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        c = QtCore.QPointF(self.width() / 2.0, self.RING / 2.0 + 1)
        r = self.DOT / 2.0
        if self.custom:
            grad = QtGui.QConicalGradient(c, 90)
            for i in range(7):
                grad.setColorAt(i / 6.0, QtGui.QColor.fromHsvF((i % 6) / 6.0, 0.85, 0.95))
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QBrush(grad))
            p.drawEllipse(c, self.RING / 2.0, self.RING / 2.0)
            p.setBrush(QtGui.QColor("#000000"))          # 1 px black ring
            p.drawEllipse(c, r + 1, r + 1)
            p.setBrush(QtGui.QColor(self.color) if self.color else QtGui.QColor("#2a2a2a"))
            p.drawEllipse(c, r, r)
            if not self.color:
                p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
                p.drawLine(QtCore.QPointF(c.x() - 5, c.y()), QtCore.QPointF(c.x() + 5, c.y()))
                p.drawLine(QtCore.QPointF(c.x(), c.y() - 5), QtCore.QPointF(c.x(), c.y() + 5))
        else:
            color = QtGui.QColor(self.color)
            # black (or any dark colour) gets a grey outline so it shows on the dark strip
            p.setPen(QtGui.QPen(QtGui.QColor("#8a8a8a"), 1) if _is_dark(color) else Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(c, r - 0.5, r - 0.5)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(ORANGE)
            p.drawRoundedRect(QtCore.QRectF(c.x() - 10, self.height() - 4, 20, 3), 1.5, 1.5)
        p.end()


def pick_color(parent, initial):
    """Qt's own colour picker in the player's dark colours (basic colours,
    colour square and hue strip, hex field, pick from the screen).
    Returns '#rrggbb', or None if cancelled."""
    dlg = QtWidgets.QColorDialog(QtGui.QColor(initial or "#e8c547"), parent)
    dlg.setWindowTitle("Drawing colour")
    dlg.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)
    try:
        for box in dlg.findChildren(QtWidgets.QDialogButtonBox):
            ok = box.button(QtWidgets.QDialogButtonBox.Ok)
            if ok is not None:
                ok.setText("Use colour")
    except Exception:  # cosmetic only (the OK button's label)
        pass
    run = getattr(dlg, "exec", None) or dlg.exec_
    if run() != QtWidgets.QDialog.Accepted:
        return None
    color = dlg.currentColor()
    return color.name() if color.isValid() else None


class ElideLabel(QtWidgets.QLabel):
    """A name that's cut short with "..." instead of widening the row (a long
    Blue Pencil file name pushed the opacity and x buttons out of sight)."""

    def __init__(self, text):
        super(ElideLabel, self).__init__(text)
        self._full = text
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.setMinimumWidth(20)
        self.setToolTip(text)

    def minimumSizeHint(self):
        return QtCore.QSize(20, super(ElideLabel, self).minimumSizeHint().height())

    def resizeEvent(self, event):
        super(ElideLabel, self).resizeEvent(event)
        QtWidgets.QLabel.setText(self, self.fontMetrics().elidedText(self._full, Qt.ElideMiddle,
                                                                     max(0, int(self.width()))))


class HeadRow(QtWidgets.QFrame):
    """A heading in the layer list: "you", or a person you import (orange
    with Update when they've saved newer drawings; Revert after an update)."""

    def __init__(self, panel, row):
        super(HeadRow, self).__init__()
        self.panel, self.row, self.key = panel, row, row["key"]
        d = panel.drawer
        self.setObjectName("head")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(5)
        me = row["kind"] == "me"
        person = None if me else row["row"]
        status = person["status"] if person else "current"
        self.setProperty("update", "true" if status == "update" else "false")
        pic = QtWidgets.QLabel()
        pic.setPixmap(icon("person", "#f0c890" if status == "update" else ("#d6d6d6" if me else "#b9c7d6"),
                           12).pixmap(12, 12))
        lay.addWidget(pic)
        label = ElideLabel("%s (you)" % d.user if me else person["user"])
        label.setStyleSheet("font-size: 12px; font-weight: bold; color: %s;" % (
            "#f5d7a8" if status == "update" else "#f2f2f2"))
        lay.addWidget(label, 1)
        if person:
            if status == "update":
                b = _button("Update", "%s has saved newer drawings: show them" % person["user"], object_name="update")
                b.clicked.connect(lambda: d.update_person(person["user"]))
                lay.addWidget(b)
            elif status == "revert":
                b = _button("Revert", "Go back to the %s drawings you had before updating" % person["user"],
                            object_name="revert")
                b.clicked.connect(lambda: d.revert_person(person["user"]))
                lay.addWidget(b)
            rm = _button(kind="x", tip="Remove %s from your list (their files are untouched)" % person["user"],
                         object_name="flat")
            rm.clicked.connect(lambda: d.remove_row(self.key))
            lay.addWidget(rm)


class LayerRow(QtWidgets.QFrame):
    def __init__(self, panel, row):
        super(LayerRow, self).__init__()
        self.panel, self.row, self.key = panel, row, row["key"]
        d = panel.drawer
        self.setObjectName("row")
        mine = row["kind"] == "mine"
        # Your active layer (the pen draws there) is highlighted, unless an
        # imported row is selected (clicked): then that one is, for the trash
        # button. Imported layers are always locked: duplicate one to edit it.
        selected = d.selected == self.key
        active = mine and d.selected is None and d.mine_now().active == row["layer"]["id"]
        self.setProperty("active", "true" if (active or selected) else "false")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(18 if row["kind"] in ("mine", "person") else 4, 1, 4, 1)
        lay.setSpacing(3)
        visible = d.row_value(self.key, "visible")
        eye = _button(kind="eye" if visible else "eye_off", tip="Show or hide", object_name="flat")
        eye.clicked.connect(lambda: d.set_row(self.key, visible=not d.row_value(self.key, "visible")) or panel.refresh())
        lay.addWidget(eye)
        locked = bool(row["layer"].get("locked")) if mine else True
        if mine:
            lock = _button(kind="lock" if locked else "unlock",
                           tip="Locked: click to unlock" if locked else "Unlocked: click to lock (no drawing, "
                               "erasing, clearing, undo or deleting)", object_name="flat")
            lock.setIcon(icon("lock", ORANGE.name()) if locked else icon("unlock", "#8a8a8a"))
            lock.clicked.connect(lambda: d.set_row(self.key, locked=not d.row_value(self.key, "locked")) or panel.refresh())
        else:
            lock = _button(kind="lock", tip="Someone else's drawing: always locked. Duplicate it to edit."
                           if row["kind"] == "person" else "A Blue Pencil file: read-only", object_name="flat")
            lock.setIcon(icon("lock", ORANGE.name()))
        lay.addWidget(lock)
        if row["kind"] in ("mine", "person"):
            name = row["layer"]["name"]
        else:
            name = "BP: " + row["row"].name
        label = ElideLabel(name)
        dim = not visible or (mine and locked)
        style = "font-size: 12px; color: %s;" % ("#8a8a8a" if dim else "#f0f0f0")
        if active or selected:
            style += " font-weight: bold;"
        if not mine:
            style += " font-style: italic;"
        if row["kind"] == "blue":
            pic = QtWidgets.QLabel()
            pic.setPixmap(icon("pen", "#b9c7d6", 12).pixmap(12, 12))
            lay.addWidget(pic)
        label.setStyleSheet(style)
        source = row["layer"].get("source") if mine else None
        if mine:
            tip = "%s\nDouble-click to rename" % name
            if source:
                tip += "\nCopied from %s's %s" % (source.get("user"), source.get("layer"))
        else:
            tip = "%s\nRead-only. Click to select; the trash removes it from your list (the files are untouched)" % name
        label.setToolTip(tip)
        lay.addWidget(label, 1)
        if active:
            mark = QtWidgets.QLabel()
            mark.setPixmap(icon("pen", ORANGE.name(), 12).pixmap(12, 12))
            mark.setToolTip("You're drawing on this layer")
            lay.addWidget(mark)
        if row["kind"] == "person":
            dup = _button(kind="copy", tip="Duplicate to my layers (to edit it)")
            dup.setObjectName("dup")
            dup.clicked.connect(lambda: d.duplicate(self.key))
            lay.addWidget(dup)
        pct = int(round(100 * float(d.row_value(self.key, "opacity") or 0)))
        op = _button("%d%%" % pct, "Opacity", "opacity", object_name="opacity")
        op.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        op.setIconSize(QtCore.QSize(12, 12))
        op.clicked.connect(lambda: panel.opacity_popup(self.key, op))
        lay.addWidget(op)
        if row["kind"] == "blue":
            rm = _button(kind="x", tip="Remove from the list (the file is untouched)", object_name="flat")
            rm.clicked.connect(lambda: d.remove_row(self.key))
            lay.addWidget(rm)
        self.mine = mine

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        d = self.panel.drawer
        if self.mine:
            d.selected = None
            d.mine_now().active = self.row["layer"]["id"]     # picking a layer isn't a change to save
        else:
            d.selected = self.key           # imported: select it (for the trash button)
        self.panel.refresh()

    def mouseDoubleClickEvent(self, event):
        if not self.mine:
            return
        layer = self.row["layer"]
        name, ok = QtWidgets.QInputDialog.getText(self, "Rename layer", "Name:", text=layer["name"])
        if ok and name.strip():
            self.panel.drawer.mine_now().rename_layer(layer["id"], name.strip())
            self.panel.drawer.edited()
            self.panel.refresh()


def _line(lay):
    """A thin horizontal line between sections of the drawing strip."""
    line = QtWidgets.QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: #333")
    lay.addWidget(line)


class DrawPanel(QtWidgets.QWidget):
    """Side strip shown in Draw mode."""

    def __init__(self, drawer, keymap):
        super(DrawPanel, self).__init__()
        self.drawer, self.keymap = drawer, keymap
        drawer.panel = self
        self.setObjectName("drawStrip")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(DRAW_STYLE)
        self.setFixedWidth(256)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._build_tool_and_size(lay)
        self._build_colours(lay)
        self._build_show(lay)
        _line(lay)
        self._build_layers(lay)
        _line(lay)
        self._build_share(lay)
        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self._build_save(lay)
        self.setVisible(False)
        self.refresh()

    def _build_save(self, lay):
        """Save at the bottom (0.9.0b3): nothing is shared until you save."""
        self.unsaved_label = QtWidgets.QLabel("\u25cf Unsaved: only you see these changes until you save")
        self.unsaved_label.setObjectName("unsaved")
        self.unsaved_label.setWordWrap(True)
        lay.addWidget(self.unsaved_label)
        row = QtWidgets.QHBoxLayout()
        self.b_save = _button("Save drawings  (Ctrl+S)", "Save your drawings: others see them after they press Update",
                              object_name="save")
        self.b_save.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.b_save.clicked.connect(self.drawer.save_now)
        self.b_history = _button("History", "Your earlier saves of this camera's drawings: restore one")
        self.b_history.clicked.connect(self.show_history)
        row.addWidget(self.b_save, 1)
        row.addWidget(self.b_history)
        lay.addLayout(row)

    def refresh_save(self):
        mine = self.drawer.mine_now()
        dirty = bool(mine is not None and mine.dirty)
        self.unsaved_label.setVisible(dirty)
        self.b_save.setEnabled(dirty)
        self.b_history.setEnabled(mine is not None and os.path.isfile(mine.path))

    def show_history(self):
        """Your earlier saves, newest first; Restore brings one back (and is
        itself a save, so it can be undone the same way)."""
        mine = self.drawer.mine_now()
        if mine is None:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Drawing history")
        dlg.setStyleSheet(DRAW_STYLE + "QDialog { background: #2c2c2c; } QListWidget { background: #1e1e1e; color: #e6e6e6; border: 1px solid #444; }")
        lay = QtWidgets.QVBoxLayout(dlg)
        head = QtWidgets.QLabel("Your saves of %s, newest first. The last %d are kept; a restore is a save "
                                "too, so it can be undone." % (self.drawer.cam(), drawing.VERSIONS_KEPT))
        head.setWordWrap(True)
        lay.addWidget(head)
        lst = QtWidgets.QListWidget()
        versions = mine.versions()
        for v in versions:
            when = time.strftime("%a %d %b %H:%M", time.localtime(v["saved"]))
            frames = "frames %d-%d" % v["frames"] if v["frames"] else "no drawings"
            lst.addItem("%s  \u00b7  %s%s" % (when, frames, "   (current)" if v["current"] else ""))
        lay.addWidget(lst, 1)
        row = QtWidgets.QHBoxLayout()
        restore = _button("Restore", "Bring this version back and save it")
        close = _button("Close")
        row.addStretch(1)
        row.addWidget(restore)
        row.addWidget(close)
        lay.addLayout(row)
        close.clicked.connect(dlg.reject)

        def go():
            i = lst.currentRow()
            if 0 < i < len(versions):
                self.drawer.restore_version(versions[i]["path"])
                dlg.accept()
        restore.clicked.connect(go)
        lst.currentRowChanged.connect(lambda i: restore.setEnabled(0 < i < len(versions)))
        restore.setEnabled(False)
        dlg.resize(420, 320)
        (getattr(dlg, "exec", None) or dlg.exec_)()

    def _build_tool_and_size(self, lay):
        """Tool (Pen / Eraser) and Size."""
        lay.addWidget(_head("Tool"))
        row = QtWidgets.QHBoxLayout()
        self.b_pen = _button("Pen", checkable=True)
        self.b_eraser = _button("Eraser", checkable=True)
        for b in (self.b_pen, self.b_eraser):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            row.addWidget(b)
        self.b_pen.clicked.connect(lambda: self.set_tool("pen"))
        self.b_eraser.clicked.connect(lambda: self.set_tool("eraser"))
        lay.addLayout(row)

        lay.addWidget(_head("Size"))
        row = QtWidgets.QHBoxLayout()
        self.dot = SizeDot(self.drawer)
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.setRange(1, 40)
        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(1, 40)
        self.spin.setFixedWidth(46)
        for w in (self.dot, self.slider, self.spin):
            row.addWidget(w)
        row.addWidget(QtWidgets.QLabel("px"))
        self.slider.valueChanged.connect(self.set_size)
        self.spin.valueChanged.connect(self.set_size)
        lay.addLayout(row)

    def _build_colours(self, lay):
        """Colour: the swatches and your custom colour."""
        lay.addWidget(_head("Colour"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        self.swatches = []
        for color, name in zip(drawing.COLORS, drawing.COLOR_NAMES):
            b = Swatch(color, name)
            b.clicked.connect(lambda checked=False, c=color: self.set_color(c))
            row.addWidget(b)
            self.swatches.append((color, b))
        divider = QtWidgets.QFrame()
        divider.setFixedSize(1, 26)
        divider.setStyleSheet("background: #444")
        row.addSpacing(3)
        row.addWidget(divider)
        row.addSpacing(3)
        self.custom_swatch = Swatch(self.drawer.custom, "Custom colour: click to use it, click again to change it",
                                    custom=True)
        self.custom_swatch.clicked.connect(self.custom_clicked)
        row.addWidget(self.custom_swatch)
        row.addStretch(1)
        lay.addLayout(row)

    def _build_show(self, lay):
        """Show (Hold, Onion skin), step through drawings, Paper, Undo/Redo/Clear."""
        lay.addWidget(_head("Show"))
        row = QtWidgets.QHBoxLayout()
        self.b_hold = _button("Hold", "Each drawing stays until the next drawn frame", checkable=True)
        self.b_onion = _button("Onion skin", "Faint drawings from the drawn frames before (red) and after (blue)",
                               checkable=True)
        for b in (self.b_hold, self.b_onion):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            row.addWidget(b)
        self.b_hold.clicked.connect(lambda c: self._set("hold", c))
        self.b_onion.clicked.connect(lambda c: self._set("onion", c))
        lay.addLayout(row)

        # Step through the drawings (the orange marks on the bar), cycling round
        row = QtWidgets.QHBoxLayout()
        self.b_prev_drawing = _button("◀ Drawing", "Previous drawing")
        self.b_next_drawing = _button("Drawing ▶", "Next drawing (after the last, back to the first)")
        for b, step in ((self.b_prev_drawing, -1), (self.b_next_drawing, 1)):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, s=step: self.drawer.player.step_drawing(s))
            row.addWidget(b)
        lay.addLayout(row)

        # Paper: fade the movie towards white so the drawings read better
        row = QtWidgets.QHBoxLayout()
        paper_label = QtWidgets.QLabel("Paper")
        paper_label.setToolTip("Fade the picture towards white, like paper over the movie, so drawings read better")
        self.paper_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.paper_slider.setRange(0, 100)
        self.paper_slider.setToolTip(paper_label.toolTip())
        self.paper_value = QtWidgets.QLabel("0%")
        self.paper_value.setFixedWidth(34)
        for w in (paper_label, self.paper_slider, self.paper_value):
            row.addWidget(w)
        self.paper_slider.valueChanged.connect(self.set_paper)
        lay.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        for text, tip, fn in (("Undo", "Undo (Ctrl+Z)", self.drawer.undo), ("Redo", "Redo (Ctrl+Shift+Z)", self.drawer.redo),
                              ("Clear", "Clear this frame's drawing on the active layer", self.drawer.clear)):
            b = _button(text, tip)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

    def _build_layers(self, lay):
        """Layers: the buttons and the scrolling layer list."""
        row = QtWidgets.QHBoxLayout()
        row.addWidget(_head("Layers"), 1)
        for kind, tip, fn in (("plus", "New layer", self.add_layer),
                              ("up", "Move layer up", lambda: self.move_layer(-1)),
                              ("down", "Move layer down", lambda: self.move_layer(1)),
                              ("trash", "Delete layer", self.delete_layer)):
            b = _button(kind=kind, tip=tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.rows_box = QtWidgets.QVBoxLayout()
        self.rows_box.setSpacing(2)
        rows_widget = QtWidgets.QWidget()
        rows_widget.setObjectName("layerList")
        rows_widget.setAttribute(Qt.WA_StyledBackground, True)
        rows_widget.setLayout(self.rows_box)
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("layers")
        scroll.viewport().setObjectName("layersView")
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)

    def _build_share(self, lay):
        """Share: Export to Blue Pencil and Import."""
        lay.addWidget(_head("Share"))
        row = QtWidgets.QHBoxLayout()
        self.b_export = _button("Export to Blue Pencil...", "Save the visible layers as a Blue Pencil zip for Maya")
        self.b_import = _button("Import", "Other people's drawings or a Blue Pencil zip")
        self.b_import.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.import_menu = QtWidgets.QMenu(self)
        self.import_menu.aboutToShow.connect(self.fill_import_menu)
        self.b_import.setMenu(self.import_menu)
        self.b_export.clicked.connect(self.export)
        row.addWidget(self.b_export, 1)
        row.addWidget(self.b_import)
        lay.addLayout(row)

    # ------------------------------------------------------------ settings
    def _set(self, name, value):
        setattr(self.drawer, name, value)
        self.drawer.save_prefs()
        self.refresh(rows=False)
        self.drawer.player.canvas.update()

    def set_tool(self, tool):
        self._set("tool", tool)

    def set_paper(self, value):
        """Paper slider, 0-100 %."""
        self.drawer.paper = min(max(value, 0), 100) / 100.0
        self.paper_value.setText("%d%%" % int(value))
        self.drawer.player.canvas.update()

    def set_size(self, value):
        if int(value) != int(self.drawer.size):
            self._set("size", float(value))

    def set_color(self, color):
        self._set("color", color)
        if self.drawer.tool != "pen":
            self.set_tool("pen")

    def custom_clicked(self):
        """First click uses the custom colour; clicking it while it's the
        current colour (or before one is picked) opens the picker."""
        d = self.drawer
        if d.custom and (d.color or "").lower() != d.custom.lower():
            self.set_color(d.custom)
            return
        picked = pick_color(self, d.custom or d.color)
        if picked:
            d.custom = picked
            self.set_color(picked)
        else:
            self.refresh(rows=False)

    def add_layer(self):
        mine = self.drawer.mine_now()
        if mine:
            mine.add_layer()
            self.drawer.edited()
            self.drawer.changed()

    def move_layer(self, delta):
        mine = self.drawer.mine_now()
        if mine and mine.active:
            mine.move_layer(mine.active, delta)
            self.drawer.edited()
            self.drawer.changed()

    def delete_layer(self):
        d = self.drawer
        if d.selected and any(r["key"] == d.selected for r in d.rows()):
            key, d.selected = d.selected, None
            d.remove_row(key)               # imported: off your list, their files untouched
            d.player._flash_message("Removed from your list (the files are untouched)")
            return
        d.selected = None
        mine = self.drawer.mine_now()
        layer = mine.active_layer() if mine else None
        if layer is None:
            return
        if layer.get("locked"):
            d.player._flash_message("Layer %s is locked: unlock it to delete it" % layer["name"])
            return
        if layer["frames"]:
            answer = QtWidgets.QMessageBox.question(
                self, "Delete layer", "Delete layer %s and its drawings?\n(Undo brings it back.)" % layer["name"])
            if answer != QtWidgets.QMessageBox.Yes:
                return
        mine.delete_layer(layer["id"])
        self.drawer.edited()
        self.drawer.changed()

    def opacity_popup(self, key, button):
        menu = QtWidgets.QMenu(self)
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(10, 6, 10, 6)
        row.addWidget(QtWidgets.QLabel("Opacity"))
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setFixedWidth(130)
        slider.setValue(int(round(100 * float(self.drawer.row_value(key, "opacity") or 0))))
        value = QtWidgets.QLabel("%d%%" % slider.value())
        row.addWidget(slider)
        row.addWidget(value)

        def changed(v):
            value.setText("%d%%" % v)
            button.setText("%d%%" % v)
            self.drawer.set_row(key, opacity=v / 100.0)
        slider.valueChanged.connect(changed)
        action = QtWidgets.QWidgetAction(menu)
        action.setDefaultWidget(holder)
        menu.addAction(action)
        run = getattr(menu, "exec", None) or menu.exec_
        run(button.mapToGlobal(QtCore.QPoint(0, button.height())))

    # ------------------------------------------------------------ import / export
    def fill_import_menu(self):
        menu = self.import_menu
        menu.clear()
        d = self.drawer
        cam = d.cam()
        head = menu.addAction("On %s · %s" % (d.player.live_shot or "this shot", cam or "-"))
        head.setEnabled(False)
        people = d.find_people()
        if not people:
            none = menu.addAction("   no one else has drawings for this camera")
            none.setEnabled(False)
        for person in people:
            self._person_action(menu, person, cam)
        # the other cameras: people (and you) with drawings there
        for other in sorted(drawing.drawn_cameras(d.root) - {cam}):
            found = d.find_people(other, include_me=True)
            if not found:
                continue
            menu.addSeparator()
            full = self._camera_named(other)
            state = self._camera_state(full)
            title = menu.addAction("On %s%s" % (other, ("    · " + state) if state else ""))
            title.setEnabled(False)
            if full and not state:
                menu.addAction("   Cache %s" % other, lambda _checked=False, f=full: self.cache_camera(f))
            elif not full:
                note = menu.addAction("   (not a camera in your scene)")
                note.setEnabled(False)
            for person in found:
                if person["user"] == d.user:
                    you = menu.addAction("   you      %d layer%s" % (person["layers"], "" if person["layers"] == 1 else "s"))
                    you.setEnabled(False)
                else:
                    self._person_action(menu, person, other)
        menu.addSeparator()
        menu.addAction("Blue Pencil zip...", self.import_blue)

    def _person_action(self, menu, person, cam):
        d = self.drawer
        linked = d.is_linked(person["user"], cam)
        row = d.person(person["user"], cam) if linked else None
        tag = "update" if row is not None and row["status"] == "update" else \
            "%d layer%s" % (person["layers"], "" if person["layers"] == 1 else "s")
        act = menu.addAction("%s      %s" % (person["user"], tag))
        act.setCheckable(True)
        act.setChecked(linked)
        act.toggled.connect(lambda on, u=person["user"], c=cam: d.set_linked(u, on, c))
        return act

    def _camera_named(self, folder):
        for c in self.drawer.player.cfg.get("cameras") or []:
            if drawing.camera_folder(c.get("name")) == folder:
                return c.get("name")
        return None

    def _camera_state(self, full):
        """"" (not cached), "caching 62%" or "loaded" for one of your cameras."""
        pl = self.drawer.player
        if not full or full not in (pl.checked or []):
            return ""
        total = max(1, int(pl.end) - int(pl.start) + 1)
        have = len(pl.loaded.get(full, {})) if hasattr(pl, "loaded") else 0
        dirty = len(pl.dirty.get(full, ())) if hasattr(pl, "dirty") else 0
        done = min(have, total - dirty) if have else 0
        if done >= total and not dirty:
            return "loaded"
        return "caching %d%%" % int(100.0 * done / total)

    def cache_camera(self, full):
        """Start caching another camera in the background (after the one
        you're viewing); you switch to it yourself with the Camera menu."""
        pl = self.drawer.player
        pl._set_checked(full, True)
        pl._flash_message("Caching %s in the background: switch to it in the Camera menu when it's loaded"
                          % pl._label(full), 5.0)

    def import_blue(self):
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Show a Blue Pencil zip over the playback", os.path.expanduser("~"), "Blue Pencil (*.zip)")
        if path:
            self.drawer.add_blue(path)

    def export(self):
        d = self.drawer
        mine = d.mine_now()
        if mine is None or not (mine.drawn_frames() or d.ticks()):
            d.player._flash_message("Nothing visible to export")
            return
        if not d._gate():
            d.player._flash_message("No camera details from Maya: placement assumes the frame fills Blue Pencil's width", 5.0)
        folder = os.path.dirname(mine.path)
        default = os.path.join(folder, "bluepencil_%s_%s_%s.zip" % (
            d.player.live_shot or "shot", d.cam(), time.strftime("%m%d_%H%M")))
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export to Blue Pencil", default, "Blue Pencil (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            if not os.path.isdir(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            frames, layers = d.export_blue_pencil(path)
        except Exception as error:
            d.player._flash_message("Export failed: %s" % error, 6.0)
            return
        d.player.send_cmd("bp_import", path=path)
        d.player._flash_message("Saved %d drawings on %d layers. In Maya: pick the file in Blue Pencil's "
                                "import (its path is on your clipboard)" % (frames, layers), 8.0)

    # ------------------------------------------------------------ refresh
    def refresh(self, rows=True):
        d = self.drawer
        self.b_pen.setChecked(d.tool == "pen")
        self.b_eraser.setChecked(d.tool == "eraser")
        for w, v in ((self.slider, d.size), (self.spin, d.size)):
            w.blockSignals(True)
            w.setValue(int(v))
            w.blockSignals(False)
        current = (d.color or "").lower()
        preset = False
        for color, b in self.swatches:
            b.setChecked(color.lower() == current)
            preset = preset or color.lower() == current
        self.custom_swatch.set_color(d.custom)
        self.custom_swatch.setChecked(not preset and bool(d.custom) and d.custom.lower() == current)
        self.b_hold.setChecked(d.hold)
        self.b_onion.setChecked(d.onion)
        self.paper_slider.blockSignals(True)
        self.paper_slider.setValue(int(round(d.paper * 100)))
        self.paper_slider.blockSignals(False)
        self.paper_value.setText("%d%%" % int(round(d.paper * 100)))
        self.dot.update()
        prev_key, next_key = self.keymap.label("prev_key"), self.keymap.label("next_key")
        self.b_prev_drawing.setToolTip("Previous drawing (%s)" % prev_key)
        self.b_next_drawing.setToolTip("Next drawing (%s); after the last, back to the first" % next_key)
        self.hint.setText("Scrub: %s + drag or middle-drag · Step: %s / %s · Drawings: %s / %s\n(your Maya hotkeys)" % (
            self.keymap.label("scrub"), self.keymap.label("prev_frame"), self.keymap.label("next_frame"),
            prev_key, next_key))
        self.refresh_save()
        if not rows:
            return
        for _ in range(int(self.rows_box.count())):
            item = self.rows_box.takeAt(0)
            if item.widget():
                item.widget().hide()          # gone at once, not when Qt gets round to deleting it
                item.widget().deleteLater()
        for row in d.rows():
            self.rows_box.addWidget(HeadRow(self, row) if row["kind"] in ("me", "head") else LayerRow(self, row))
        self.rows_box.addStretch(1)
