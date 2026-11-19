"""Drawing in the player: other people's drawings (snapshots, Update / Revert, listed by themselves, b8) and Blue Pencil zips; their rows in the strip.

Part of drawui.py (the Drawer and the drawing strip); see DEVELOPER.md."""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)


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


class PeopleMixin(object):
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
        live = drawing.layers_path(self._root_of(cam), user, self._folder_of(cam))
        seen = self._seen_path(user, cam)
        accepted = entry.get("accepted")
        if not os.path.isfile(seen) and os.path.isfile(live):
            try:
                self._copy(live, seen)
                accepted = self._meta(drawing.file_rev(live))
            except (IOError, OSError):
                seen = live
        row = {"user": user, "cam": cam, "live": live, "seen": seen,
               "accepted": accepted, "prev": entry.get("prev"), "hide_new": bool(entry.get("hide_new")),
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

    NEW_PEOPLE_EVERY = 5          # check_updates runs: look for new people every ~10 s

    def check_updates(self):
        """Every couple of seconds: has anyone you see saved a newer version?
        Every ~10 s: has someone new saved drawings on this shot (b8)?"""
        changed = False
        self._checks = getattr(self, "_checks", 0) + 1
        cam = self.cam()
        if cam and cam in self.people and self._checks % self.NEW_PEOPLE_EVERY == 0:
            changed = self._add_new_people(cam)
        for cam, rows in list(self.people.items()):
            for row in rows:
                before = row["status"]
                if self._status(row) != before:
                    changed = True
        if changed:
            self.changed()
        return changed

    # b8: everyone who has saved drawings on this shot and camera is listed by
    # themselves (no Import needed), with their layers off until you click
    # the eye. Removing someone (x) keeps them off the list until you tick
    # them in Import again.
    def _add_new_people(self, cam):
        """List people with drawings here that aren't listed yet. True if any."""
        try:
            found = self.find_people(cam)
        except (IOError, OSError) as error:
            print("bgcache player: couldn't look for other people's drawings: %s" % error)
            return False
        pref = self._rows_pref(cam)
        listed = {r["user"] for r in self.people.get(cam, [])} | set(pref.get("removed", []))
        new = [p["user"] for p in found if p["user"] not in listed and p["user"] != self.user]
        for user in new:
            row = self._open_person(user, cam, {"hide_new": True})
            self.people.setdefault(cam, []).append(row)
        if new:
            self._save_rows(cam)
        return bool(new)

    def set_person_visible(self, user, on):
        """The eye on a person's heading: all their layers on or off."""
        row = self.person(user)
        if row is None:
            return
        for layer in row["drawings"].layers:
            row["view"].setdefault(layer["id"], {})["visible"] = bool(on)
        row["hide_new"] = False
        self._save_rows(row["cam"])
        self.changed()

    def person_visible(self, row):
        return any(self.layer_view(row, layer)[0] for layer in row["drawings"].layers)

    def _save_rows(self, cam=None):
        cam = cam or self.cam()
        pref = self._rows_pref(cam)
        pref["people"] = [{"user": r["user"], "view": r["view"], "accepted": r.get("accepted"),
                           "prev": r.get("prev"), "hide_new": bool(r.get("hide_new"))}
                          for r in self.people.get(cam, [])]
        pref["blue"] = [{"path": b.path, "visible": b.visible, "opacity": b.opacity}
                        for b in self.blue.get(cam, [])]
        self.player._save_prefs()

    def save_prefs(self):
        self.player.prefs["drawing"] = {"tool": self.tool, "size": self.pen_size, "eraser_size": self.eraser_size,
                                        "color": self.color, "custom_color": self.custom,
                                        "hold": self.hold, "onion": self.onion, "show": self.show,
                                        "onion_before": self.onion_before, "onion_after": self.onion_after}
        self.player._save_prefs()

    @staticmethod
    def layer_view(row, layer):
        """(visible, opacity) of someone else's layer as you show it. b8: a
        person listed by themselves has their layers off until you turn them on."""
        v = row["view"].get(layer["id"]) or {}
        default = False if row.get("hide_new") else layer.get("visible", True)
        return bool(v.get("visible", default)), float(v.get("opacity", layer.get("opacity", 1.0)))

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

    # ------------------------------------------------------------ people / Blue Pencil
    def find_people(self, cam=None, include_me=False):
        cam = cam or self.cam()
        return drawing.find_people(self._root_of(cam), self.user, self._folder_of(cam), include_me) if cam else []

    def is_linked(self, user, cam=None):
        cam = cam or self.cam()
        self._ensure_linked(cam)
        return any(r["user"] == user for r in self.people.get(cam, []))

    def set_linked(self, user, on, cam=None):
        cam = cam or self.cam()
        self._ensure_linked(cam)
        rows = self.people.setdefault(cam, [])
        pref = self._rows_pref(cam)
        removed = pref.setdefault("removed", [])
        if on and user in removed:
            removed.remove(user)
        elif not on and user not in removed:
            removed.append(user)
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
