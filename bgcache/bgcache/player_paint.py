"""Player: Painting the picture: the frame, drawings, overlays and banners, the cache bar.

Part of the Player (bgcache/player.py); see DEVELOPER.md."""
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401


class PaintMixin(object):
    # ================================================================ drawing
    def paint(self, canvas):
        """Draw the canvas: the frame (or why there's none), drawings, film
        gate, overlays and banners, then the cache bar."""
        p = QtGui.QPainter(canvas)
        rect = canvas.rect()
        p.fillRect(rect, QtGui.QColor(18, 18, 18))
        view = QtCore.QRect(0, 0, rect.width(), rect.height() - BAR_H)
        if self.test_mode:
            self._paint_test(p, view, rect)
            p.end()
            return
        seg, local = self._locate(self.pos)
        live = seg["kind"] == "live"
        ref = live and bool(seg.get("ref"))          # your shot, shown as a department's movie
        frame = self.start + local if live else None
        stale = live and not ref and frame in self.dirty.get(self.view, set())

        img = self._image(self.pos)
        target = view
        if img is not None and not img.isNull():
            target = self._paint_frame(p, view, img, live and not ref, frame, stale)
            if ref:
                self._paint_drawings_on_ref(p, target, frame)
            elif not live and self.drawer.place() is not None:      # b8: drawings on the shots around yours
                self._paint_drawings_on_ref(p, target, int(seg.get("first") or 0) + local)
        else:
            p.setPen(QtGui.QColor(150, 150, 150))
            p.drawText(view, Qt.AlignCenter, self._no_frame_text(p, view, seg, live, ref))
        self._paint_overlays(p, target, seg, local, live, ref, frame, stale)
        self._paint_bar(p, QtCore.QRect(0, rect.height() - BAR_H, rect.width(), BAR_H))
        p.end()

    def _paint_frame(self, p, view, img, yours, frame, stale):
        """The cached frame, fitted to the view; on your live shot (yours)
        also the drawings, film gate, paused tint and the red stale frame.
        Returns where the picture went."""
        scale = min(view.width() / float(img.width()), view.height() / float(img.height()))
        w, h = int(img.width() * scale), int(img.height() * scale)
        target = QtCore.QRect((view.width() - w) // 2, (view.height() - h) // 2, w, h)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        p.drawImage(target, img)
        if yours:
            self.last_target = target
            try:
                self.drawer.paint_paper(p, target)        # Paper: the movie fades to white under the drawings
                self.drawer.paint(p, target, frame)
            except Exception as error:
                print("bgcache player: drawing: %s" % error)
            if self.gate_mask:
                self._paint_gate(p, target)
        if yours and getattr(self, "paused", False):
            p.fillRect(target, QtGui.QColor(190, 30, 30, 46))     # paused: a red tint over the picture
        if stale:
            p.setPen(QtGui.QPen(QtGui.QColor(220, 60, 60), 4))
            p.drawRect(target.adjusted(2, 2, -2, -2))
        return target

    def _paint_drawings_on_ref(self, p, target, frame):
        """b4: your drawings stay on when your shot shows a department's
        movie (same shot, same frames), fitted to the shot's frame shape
        inside the movie's picture; you can keep drawing there too."""
        w, h = float(self.drawer.W), float(self.drawer.H)
        scale = min(target.width() / w, target.height() / h)
        fit = QtCore.QRect(target.x() + int((target.width() - w * scale) / 2),
                           target.y() + int((target.height() - h * scale) / 2), int(w * scale), int(h * scale))
        self.last_target = fit
        try:
            self.drawer.paint_paper(p, fit)
            self.drawer.paint(p, fit, frame)
        except Exception as error:
            print("bgcache player: drawing: %s" % error)

    def _no_frame_text(self, p, view, seg, live, ref):
        """What the picture says when there's no frame to show (the spinner
        too while loading)."""
        if live and not self.cfg.get("cameras"):
            return "No shot camera in this scene\n(persp, top, front and side aren't offered)"
        if live and self.state.startswith("error"):
            p.setPen(QtGui.QColor(255, 138, 128))
            return "The background Maya stopped.\nSee worker.log in the session folder, then Stop and Start again."
        if ref:
            return "the %s movie has no frame here (it's shorter than the shot)" % seg["label"]
        if live and self._loading():
            self._paint_spinner(p, view)
            text = "\n\n\n\n%s" % self._loading_text()
            if not self.view and self.cfg.get("cameras"):
                text += "\nYou can pick a camera from the Camera menu now."
            return text
        if live and not self.view:
            return "Pick a camera from the Camera menu to start caching\n%s" % self.state
        return "frame not rendered yet\n%s" % self.state

    def _paint_overlays(self, p, target, seg, local, live, ref, frame, stale):
        """Text over the picture: camera and sound, frame number, the DRAW /
        PAUSED / SYNC OFF tags, and one banner at the top."""
        if ref:
            left = "REFERENCE: %s · %s     %s     (R: live)" % (seg["shot"], seg["label"], self._sound_text())
            right = "%d" % frame
        elif live:
            left = "%s     %s" % (self._label(self.view) or "no camera", self._sound_text())
            right = "%d%s" % (frame, "  stale" if stale else "")
        else:
            left = "%s · %s · %s     %s" % (seg["shot"], seg["label"], seg["kind"],
                                          "sound" if seg["sound"] else "no sound")
            right = str(seg["first"] + local)
        self._overlay(p, target, left, Qt.AlignLeft, 13)
        self._overlay(p, target, right, Qt.AlignRight, 15)
        tag_y = 0
        place = self.drawer.place() if self.drawer.on else None
        if place is not None:
            mine = self.drawer.mine_now()
            layer = mine.active_layer() if mine else None
            dot = " ●" if mine is not None and mine.dirty else ""     # unsaved
            on = "" if live else " ON %s" % place["shot"]             # b8: drawing on another shot
            tag_y = self._overlay_tag(p, target, "DRAW%s · %s%s" % (on, layer["name"] if layer else "-", dot))
        if live and not ref and getattr(self, "paused", False):
            tag_y = self._overlay_tag(p, target, "PAUSED", y=tag_y, pause_icon=True)
        if live and self.focus_range:         # b4: why playback stays in part of the shot
            tag_y = self._overlay_tag(p, target, "FOCUS %d-%d" % self.focus_range, y=tag_y)
        if live and not self.sync:            # easy to miss otherwise (studio, b11)
            tag_y = self._overlay_tag(p, target, "SYNC OFF", y=tag_y)
        if live and self._outside_cut(frame):  # b8: animating past the cut
            self._overlay_tag(p, target, "OUTSIDE THE CUT %d-%d" % self._cut(), y=tag_y, color=OUTSIDE_CUT)
        banner = self._reload_banner()
        trouble = None if banner else self._health_banner()
        if time.time() < self._flash_until:
            self._overlay_top(p, target, self._flash)
        elif banner:
            self._overlay_top(p, target, banner, busy=True)
        elif trouble:
            self._overlay_top(p, target, trouble, warn=True)

    def _overlay_tag(self, p, target, text, y=0, pause_icon=False, color=None):
        """An orange tag at the picture's top left (DRAW, PAUSED); y: below
        another tag. Returns the y for a tag under this one."""
        font = p.font()
        font.setPixelSize(12)
        p.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
        icon_w = 14 if pause_icon else 0
        top = target.top() + 10 + y
        box = QtCore.QRect(target.left() + 12, top, w + 16 + icon_w, metrics.height() + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(color.red(), color.green(), color.blue(), 220) if color is not None
                   else QtGui.QColor(184, 102, 42, 220))
        p.drawRoundedRect(box, 3, 3)
        if pause_icon:                       # the orange tag's "II"
            p.setBrush(QtGui.QColor(255, 244, 232))
            bar_h = box.height() - 10
            p.drawRect(QtCore.QRect(box.left() + 8, box.top() + 5, 3, bar_h))
            p.drawRect(QtCore.QRect(box.left() + 14, box.top() + 5, 3, bar_h))
        p.setPen(QtGui.QColor(255, 244, 232))
        p.drawText(box.adjusted(icon_w, 0, 0, 0), Qt.AlignCenter, text)
        return y + box.height() + 6

    def _paint_spinner(self, p, view):
        r = 18
        c = view.center()
        box = QtCore.QRect(c.x() - r, c.y() - r - 24, 2 * r, 2 * r)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtGui.QPen(QtGui.QColor(60, 60, 60), 4))
        p.drawEllipse(box)
        p.setPen(QtGui.QPen(QtGui.QColor(232, 163, 61), 4, Qt.SolidLine, Qt.RoundCap))
        angle = (time.time() * 300.0) % 360.0
        p.drawArc(box, int(-angle * 16), 100 * 16)
        p.setPen(QtGui.QColor(170, 170, 170))

    def _overlay_top(self, p, target, text, busy=False, warn=False):
        """A message box at the top of the picture. busy: orange, with a
        small spinner (something is in progress). warn: red (needs you)."""
        font = p.font()
        font.setPixelSize(14)
        p.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
        h = metrics.height() + 8
        spin = h if busy else 0
        box = QtCore.QRect(target.center().x() - (w + spin) // 2 - 10, target.top() + 12, w + spin + 20, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(150, 40, 40, 230) if warn else
                   QtGui.QColor(122, 78, 20, 220) if busy else QtGui.QColor(0, 0, 0, 170))
        p.drawRoundedRect(box, 3, 3)
        if busy:
            r = QtCore.QRect(box.left() + 8, box.top() + 5, h - 10, h - 10)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 220, 160), 2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(r, int(-(time.time() * 300.0 % 360.0) * 16), 100 * 16)
        p.setPen(QtGui.QColor(240, 240, 240))
        p.drawText(box.adjusted(spin, 0, 0, 0), Qt.AlignCenter, text)

    def _paint_test(self, p, view, rect):
        """Sync test: white flash on the click frames, instructions on top."""
        w = min(view.width(), int(view.height() * 16 / 9.0))
        h = int(w * 9 / 16.0)
        target = QtCore.QRect((view.width() - w) // 2, (view.height() - h) // 2, w, h)
        flash = self.pos % self.test_every == 0
        p.fillRect(target, QtGui.QColor(255, 255, 255) if flash else QtGui.QColor(0, 0, 0))
        when = "earlier" if self.audio_offset > 0 else "later" if self.audio_offset < 0 else ""
        lines = ["SYNC TEST: the click should land exactly on the white flash",
                 "[  sound earlier      ]  sound later      Esc  done",
                 "your offset: %+.2f frames %s" % (self.audio_offset, when)]
        if not self.sound.available:
            lines.append("no audio output: %s" % self.sound.status)
        font = p.font()
        font.setPixelSize(15)
        p.setFont(font)
        p.setPen(QtGui.QColor(232, 163, 61))
        p.drawText(target.adjusted(20, 20, -20, -20), Qt.AlignHCenter | Qt.AlignBottom, "\n".join(lines))
        bar = QtCore.QRect(0, rect.height() - BAR_H, rect.width(), BAR_H)
        p.fillRect(bar, QtGui.QColor(40, 40, 40))
        x = int(bar.width() * (self.pos + 0.5) / float(self.total))
        p.fillRect(QtCore.QRect(x - 1, bar.y(), 2, bar.height()), QtGui.QColor(255, 255, 255))

    def _overlay(self, p, target, text, align, size):
        font = p.font()
        font.setPixelSize(size)
        p.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
        h = metrics.height()
        x = target.left() + 12 if align == Qt.AlignLeft else target.right() - 12 - w - 16
        box = QtCore.QRect(x, target.bottom() - 10 - h - 6, w + 16, h + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 140))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QtGui.QColor(240, 240, 240))
        p.drawText(box, Qt.AlignCenter, text)

    def _paint_bar(self, p, bar):
        p.fillRect(bar, QtGui.QColor(40, 40, 40))
        n = self.total
        have, dirty = self.data.get(self.view, {}), self.dirty.get(self.view, set())
        top = bar.y() + 3
        for o, seg in self._offsets():
            x0 = bar.x() + bar.width() * o // n
            x1 = bar.x() + bar.width() * (o + seg["n"]) // n
            if seg["kind"] != "live" or seg.get("ref"):
                p.fillRect(QtCore.QRect(x0, top, max(1, x1 - x0), bar.height() - 3), STAGED)
            else:
                self._paint_live_frames(p, bar, o, seg["n"], have, dirty, top)
            if o > 0:
                p.fillRect(QtCore.QRect(x0 - 1, bar.y(), 2, bar.height()), QtGui.QColor(18, 18, 18))
        xs = [bar.x() + int(bar.width() * (pos + 0.5) / n) for pos in self.drawn_positions()]
        if xs:
            # Drawn frames: 3 px orange ticks the full height of the bar with a
            # dark edge, so they read over green and red. Edges first, so ticks
            # on neighbouring frames don't cover each other.
            for x in xs:
                p.fillRect(QtCore.QRect(x - 2, bar.y(), 5, bar.height()), TICK_EDGE)
            for x in xs:
                p.fillRect(QtCore.QRect(x - 1, bar.y(), 3, bar.height()), TICK)
        self._paint_maya_range(p, bar)
        self._paint_focus(p, bar)
        x = bar.x() + int(bar.width() * (self.pos + 0.5) / n)
        p.fillRect(QtCore.QRect(x - 1, bar.y(), 2, bar.height()), QtGui.QColor(255, 255, 255))

    def _paint_live_frames(self, p, bar, o, count, have, dirty, top):
        """Your shot's frames on the bar: green rendered, red out of date
        (rendered before an edit), hatched never rendered yet (b8: outside
        the focus they wait); a purple line under frames outside the cut."""
        n = self.total
        hatch = QtGui.QBrush(NOT_RENDERED, Qt.BDiagPattern)
        cut = self._cut()
        for i in range(count):
            frame = self.start + i
            a = bar.x() + bar.width() * (o + i) // n
            b = bar.x() + bar.width() * (o + i + 1) // n
            cell = QtCore.QRect(a, top, max(1, b - a), bar.height() - 3)
            if frame in have:
                p.fillRect(cell, RED if frame in dirty else GREEN)
            else:
                p.fillRect(cell, hatch)
            if cut and not cut[0] <= frame <= cut[1]:
                p.fillRect(QtCore.QRect(a, bar.bottom() - 2, max(1, b - a), 3), OUTSIDE_CUT)

    def _paint_maya_range(self, p, bar):
        """b8: your Maya's playback range as a blue line along the top of the
        bar, with ends; with Sync off and a different focus, labelled."""
        n = float(self.total) or 1.0
        live = self._live_offset()
        a, b = self.maya_range
        a, b = max(a, self.start), min(b, self.end)
        if a > b:
            return
        xa = bar.x() + int(bar.width() * (live + a - self.start) / n)
        xb = bar.x() + int(bar.width() * (live + b - self.start + 1) / n)
        p.fillRect(QtCore.QRect(xa, bar.y() - 2, max(2, xb - xa), 2), MAYA_RANGE)
        p.fillRect(QtCore.QRect(xa, bar.y() - 6, 2, 6), MAYA_RANGE)
        p.fillRect(QtCore.QRect(xb - 2, bar.y() - 6, 2, 6), MAYA_RANGE)
        if not self.sync and self.maya_range != self._focus_or_shot():
            font = p.font()
            font.setPixelSize(11)
            p.setFont(font)
            text = "Maya %d-%d" % self.maya_range
            metrics = QtGui.QFontMetrics(font)
            w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
            x = min(max(bar.x() + 2, (xa + xb - w) // 2), bar.right() - w - 6)
            box = QtCore.QRect(x - 4, bar.y() - 22, w + 8, metrics.height() + 2)
            p.fillRect(box, QtGui.QColor(18, 18, 18, 200))
            p.setPen(MAYA_RANGE)
            p.drawText(box, Qt.AlignCenter, text)

    def _paint_focus(self, p, bar):
        """b18: the focus range: outside it the bar is dimmed (red frames
        there wait), with a handle at each end."""
        n = float(self.total) or 1.0
        live = self._live_offset()
        a, b = self.focus_range or (self.start, self.end)
        xa = bar.x() + int(bar.width() * (live + a - self.start) / n)
        xb = bar.x() + int(bar.width() * (live + b - self.start + 1) / n)
        if self.focus_range:
            x0 = bar.x() + int(bar.width() * live / n)
            x1 = bar.x() + int(bar.width() * (live + self.end - self.start + 1) / n)
            shade = QtGui.QColor(0, 0, 0, 130)
            if xa > x0:
                p.fillRect(QtCore.QRect(x0, bar.y(), xa - x0, bar.height()), shade)
            if x1 > xb:
                p.fillRect(QtCore.QRect(xb, bar.y(), x1 - xb, bar.height()), shade)
        hover = getattr(self, "_hover_handle", None) or self._handle_drag
        for x, inward, name in ((xa, 1, "in"), (xb, -1, "out")):
            color = FOCUS if self.focus_range else QtGui.QColor(175, 175, 175)
            if hover == name:
                color = color.lighter(125)
            # b4: a tab above the bar, pointing inward, so a handle shows even
            # at the window's edge; and a 3 px line down the bar
            p.fillRect(QtCore.QRect(x if inward > 0 else x - 3, bar.y(), 3, bar.height()), color)
            tab = QtGui.QPolygon([QtCore.QPoint(x, bar.y() - TAB_H), QtCore.QPoint(x + inward * TAB_W, bar.y() - TAB_H),
                                  QtCore.QPoint(x, bar.y())])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPolygon(tab)
