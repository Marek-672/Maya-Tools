"""Drawing in the player: pen and eraser input, painting the drawings over the picture, Blue Pencil export.

Part of drawui.py (the Drawer and the drawing strip); see DEVELOPER.md."""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)
from bgcache.drawui_icons import paint_strokes  # noqa: F401

ONION_ALPHA, ONION_FADE = 0.3, 0.6      # the nearest ghost's opacity; each one further is this much fainter


class StrokesMixin(object):
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
        frame = self.frame_now()
        mine = self.mine_now()
        if frame is None or mine is None:
            self.player._flash_message(self._why_not_here())
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
            if mine.erase_at(frame, pos[0], pos[1], self._eraser_radius(pressure), self.hold_from(), whole=self.erase_whole):
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
            if mine.erase_at(self.frame, pos[0], pos[1], self._eraser_radius(pressure), self.hold_from(),
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
    def ticks(self, cam=None):
        """Frames with drawings in visible rows (for the cache bar); cam: a
        key from place() (default: where you are)."""
        if not self.show:
            return set()
        cam = cam or self.cam()
        mine = self.mine_now(cam)
        if mine is None:
            return set()
        out = set(mine.drawn_frames())
        for row in self.people.get(cam, []):
            for layer in row["drawings"].layers:
                if self.layer_view(row, layer)[0]:
                    out.update(int(k) for k in layer["frames"])
        for b in self.blue.get(cam, []):
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
        place = self.place() or {}
        hold = self.hold_from(place or None)      # b10: never held in from outside the frames you have
        first = place.get("first")
        first = None if first is True or first is None else int(first)      # True: no known first frame
        last = place.get("last")
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
                key = drawing.held_key(b.frames, frame, hold) if self.hold else (frame if frame in b.frames else None)
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
                        _key, strokes = row["drawings"].strokes_at(layer, frame, hold)
                        paint_strokes(p, strokes, opacity)
            active = mine.active_layer()
            for layer in reversed(mine.layers):
                if not layer["visible"]:
                    continue
                key, strokes = mine.strokes_at(layer, frame, hold)
                if self.on and self.onion and layer is active:
                    # b12: your count of drawings before (red) and after (blue),
                    # the nearest strongest; none from outside the frames you have
                    earlier, later = drawing.onion_keys(layer["frames"], key if key is not None else frame,
                                                        self.onion_before, self.onion_after, first, last)
                    for others, tint in ((earlier, "#ff8a7a"), (later, "#7ad1ff")):
                        for step, other in reversed(list(enumerate(others))):      # farthest first, nearest on top
                            paint_strokes(p, layer["frames"].get(str(other)),
                                          ONION_ALPHA * ONION_FADE ** step * layer["opacity"], tint)
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
