"""Player: Playback, keys, the mouse and the pen (scrubbing, the focus handles, drawing input).

Part of the Player (bgcache/player.py); see DEVELOPER.md."""
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401


class InputMixin(object):
    # ================================================================ playback
    def _play_window(self):
        """(first, end) reel positions playback stays in: the focus range when
        one is set (b4: like a play range; neighbouring shots are skipped),
        else the whole reel."""
        if not self.focus_range:
            return 0, self.total
        live = self._live_offset()
        a, b = self.focus_range
        return live + a - self.start, min(self.total, live + b - self.start + 1)

    def toggle_play(self, direction=1):
        if self.playing:
            stopping = self.playing == direction
            self.playing = 0
            self.sound.stop()
            self._set_play_icons()
            if stopping:
                self.send_time()
                self.canvas.update()
                return
        self.playing = direction
        lo, hi = self._play_window()
        if not lo <= self.pos < hi:            # outside the focus: play it from its start
            self.pos = lo if direction > 0 else hi - 1
        self.origin = self.pos
        self.loops = 0
        self.clock.restart()
        self.shown.clear()
        if direction > 0:
            self._play_sound(self.pos)
        self._set_play_icons()
        self.canvas.update()

    def _set_play_icons(self):
        self.transport["play"].setIcon(_icon("pause" if self.playing > 0 else "play"))
        self.transport["play_back"].setIcon(_icon("pause" if self.playing < 0 else "play_back"))

    def _tick(self):
        if not self.playing:
            return
        lo, hi = self._play_window()
        n = max(1, hi - lo)
        i = self.origin + self.playing * int(self.clock.nsecsElapsed() * 1e-9 * self.fps)
        if self.loop:
            loops = (i - lo) // n
            i = lo + (i - lo) % n
            if loops != self.loops:
                self.loops = loops
                if self.playing > 0:
                    self._play_sound(lo)
        elif not lo <= i < hi:
            i = min(max(i, lo), hi - 1)
            self.playing = 0
            self.sound.stop()
            self._set_play_icons()
            self.send_time()
        if i != self.pos:
            self.pos = i
            self.shown.append(time.time())
            self.canvas.update()

    def _stop(self):
        if self.playing:
            self.playing = 0
            self.sound.stop()
            self._set_play_icons()

    def _set_pos(self, pos):
        self._stop()
        self.pos = pos % self.total
        self.canvas.update()

    def _step(self, delta):
        old = self.pos
        self._set_pos(self.pos + delta)
        self._scrub_sound(old)
        if not self.test_mode:
            self.send_time()

    def _jump(self, pos):
        old = self.pos
        self._set_pos(pos)
        self._scrub_sound(old)
        if not self.test_mode:
            self.send_time()

    def drawn_frames(self):
        """Frames in your range with a mark on the bar, in order."""
        try:
            return sorted(f for f in self.drawer.ticks(self._live_key()) if self.start <= f <= self.end)
        except Exception:  # drawings not ready yet: no marks
            return []

    def _live_key(self):
        from bgcache import drawing
        return drawing.camera_folder(self.view) if self.view else None

    def drawn_positions(self, only_here=False):
        """Reel positions with drawings, in order: your shot's, and (b8) the
        ones on the shots around it. only_here: the shot on screen only."""
        out = []
        here = self._locate(self.pos)[0] if only_here and self.segments else None
        for o, seg in self._offsets():
            if here is not None and seg is not here:
                continue
            try:
                place = self.drawer.place(o)
                drawn = self.drawer.ticks(place["key"]) if place else set()
            except Exception:  # drawings not ready yet: no marks
                continue
            first = self.start if seg["kind"] == "live" else int(seg.get("first") or 0)
            out += [o + f - first for f in drawn if 0 <= f - first < seg["n"]]
        return sorted(out)

    def step_drawing(self, delta):
        """Go to the next (1) or previous (-1) drawing. Past the last one it
        cycles back to the first (and before the first, to the last)."""
        frames = self.drawn_positions(only_here=True)     # b8: on the shot on screen (yours or another)
        if not frames:
            self._flash_message("No drawings to step to", 2.0)
            return
        current = self.pos
        if delta > 0:
            target = next((f for f in frames if f > current), frames[0])
            wrapped = frames[-1] <= current
        else:
            target = next((f for f in reversed(frames) if f < current), frames[-1])
            wrapped = current <= frames[0]
        self._jump(target)
        if wrapped and len(frames) > 1:
            self._flash_message("Back to the first drawing" if delta > 0 else "Round to the last drawing", 1.5)

    def _set_loop(self, on):
        self.loop = on
        self.b_loop.setChecked(on)

    def _set_mute(self, muted):
        if self.sound.muted != muted:
            self.sound.toggle_mute()
        self.b_sound.setChecked(not muted)
        if not muted and self.playing > 0:
            self._play_sound(self.pos)
        self.canvas.update()

    def _set_sync(self, on):
        self.sync = on
        self.b_sync.setChecked(on)
        self.prefs["sync"] = on
        self._save_prefs()
        self.send_time()
        if on:                       # b8: back on, the player matches your Maya
            self._range_noted = False
            self.match_maya_range()
        self._update_match_button()
        self._update_status()

    def _set_on_top(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.b_top.setChecked(on)
        self.show()


    def stop_bgcache(self):
        """bgcache > Stop: your Maya stops the background Maya
        and closes this player."""
        if not self.test_mode and not self.drawer.ask_to_save(self, "stopping bgcache"):
            return
        self._close_quietly = True
        self.send_cmd("stop")
        self._flash_message("Stopping bgcache")
        # b13: your Maya normally stops everything at once. If it's frozen,
        # the player stops the background Maya itself, then closes.
        QtCore.QTimer.singleShot(4000, self._stop_background_directly)

    def _maya_answered(self):
        done = common.read_json(self.p["player_cmd"] + ".done") or {}
        return done.get("ts", 0) >= getattr(self, "_last_cmd_ts", 0)

    def _stop_background_directly(self):
        pid = self._worker_pid
        if self._maya_answered():
            pid = None                       # your Maya is stopping it
        if pid and pid != os.getpid() and common.pid_alive(pid):
            print("bgcache player: your Maya didn't stop the background Maya: asking it to quit")
            common.post_message(self.session, {"op": "quit"})
            until = time.time() + 8.0
            while time.time() < until and common.pid_alive(pid):
                QtCore.QCoreApplication.processEvents()
                time.sleep(0.2)
            if common.pid_alive(pid):
                print("bgcache player: the background Maya didn't answer: ending it (pid %s)" % pid)
                import signal
                try:
                    os.kill(int(pid), getattr(signal, "SIGKILL", signal.SIGTERM))
                except (OSError, ValueError) as error:
                    print("bgcache player: couldn't end it: %s" % error)
        self.close()

    def _close_choice(self):
        """Closing the window (x): "stop", "keep" (caching carries on; the
        shelf button reopens the player) or None (cancel). Asks unless you
        ticked "Don't ask again"."""
        remembered = self.prefs.get("on_close")
        if remembered in ("stop", "keep"):
            return remembered
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("bgcache")
        box.setText("Stop bgcache, or keep caching in the background?")
        box.setInformativeText("Keep caching: the bgcache shelf button brings this player back, "
                               "with everything cached so far.")
        stop = box.addButton("Stop bgcache", QtWidgets.QMessageBox.AcceptRole)
        keep = box.addButton("Keep caching", QtWidgets.QMessageBox.ActionRole)
        box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(keep)
        again = QtWidgets.QCheckBox("Don't ask again")
        box.setCheckBox(again)
        run = getattr(box, "exec", None) or box.exec_
        run()
        clicked = box.clickedButton()
        choice = "stop" if clicked is stop else "keep" if clicked is keep else None
        if choice and again.isChecked():
            self.prefs["on_close"] = choice
            self._save_prefs()
        return choice


    # ================================================================ input


    # ================================================================ drawing input
    @staticmethod
    def _point(event):
        for name in ("position", "posF", "pos"):
            fn = getattr(event, name, None)
            if fn is not None:
                try:
                    pt = fn()
                    return QtCore.QPointF(pt)
                except Exception:  # Qt versions name the position differently: try the next
                    continue
        return QtCore.QPointF(0, 0)

    def current_live_frame(self):
        """Your shot's frame on screen, live or shown as a department's movie
        (b4: drawings and focus work on both); None on a neighbour."""
        seg, local = self._locate(self.pos)
        if seg["kind"] != "live":
            return None
        return self.start + local

    def _wants_scrub(self, canvas, event):
        in_bar = self._point(event).y() >= canvas.height() - BAR_H - 4
        return event.button() == Qt.MiddleButton or self.scrub_held or in_bar

    def canvas_press(self, canvas, event):
        """True when the press is used here (a focus handle, drawing, or
        scrubbing in Draw mode)."""
        if event.button() == Qt.LeftButton and not self.playing:
            handle = self._handle_at(canvas, event)
            if handle:
                self._handle_drag = handle
                return True
        if event.button() == Qt.MiddleButton or (self.drawer.on and event.button() == Qt.LeftButton
                                                 and self._wants_scrub(canvas, event)):
            self.input_mode = "scrub"
            self.dragging = True
            self.scrub(canvas, event)
            return True
        if not self.drawer.on or event.button() != Qt.LeftButton:
            return False
        if self.playing:
            return True                       # no drawing while playing
        self.input_mode = "draw" if self.drawer.press(self._point(event), whole=_shift(event)) else None
        return True

    def canvas_move(self, canvas, event):
        if not event.buttons() and not self._handle_drag:
            self._hover_handle_at(canvas, event)
        if self._handle_drag:
            frame = self._frame_at(canvas, event)
            if self._handle_drag == "in":
                self.set_focus(first=frame, save=False)
            else:
                self.set_focus(last=frame, save=False)
            return True
        if self.input_mode == "scrub":
            self.scrub(canvas, event)
            return True
        if self.input_mode == "draw":
            self.drawer.move(self._point(event))
            return True
        if self.drawer.on and not self.input_mode:
            self.drawer.hover_at(self._point(event))     # the size circle follows the pointer
        return self.drawer.on and bool(event.buttons() & Qt.LeftButton)

    def _hover_handle_at(self, canvas, event):
        """b4: a focus handle under the pointer lights up, with a sideways cursor."""
        handle = None if self.playing else self._handle_at(canvas, event)
        if handle == getattr(self, "_hover_handle", None):
            return
        self._hover_handle = handle
        if handle:
            canvas.setCursor(Qt.SizeHorCursor)
        else:
            canvas.setCursor(Qt.CrossCursor if self.drawer.on else Qt.ArrowCursor)
        canvas.update()

    def canvas_release(self, canvas, event):
        if self._handle_drag:
            self._handle_drag = None
            self._save_cameras()
            a, b = self.focus_range or (self.start, self.end)
            self._flash_message("Caching %d-%d only" % (a, b) if self.focus_range else "Caching the whole shot", 2.0)
            return True
        mode, self.input_mode = self.input_mode, None
        if mode == "scrub":
            self.dragging = False
            if not self.test_mode:
                self.send_time()
            return True
        if mode == "draw":
            self.drawer.release(self._point(event))
            return True
        return self.drawer.on

    def canvas_tablet(self, canvas, event):
        """Pen input with pressure, when the tablet's pressure reaches this
        machine (over PCoIP it may arrive as a plain mouse instead)."""
        kind = event.type()
        if not self.drawer.on or self.playing:
            event.ignore()
            return
        if kind == QtCore.QEvent.TabletPress:
            if self.scrub_held or self._point(event).y() >= canvas.height() - BAR_H - 4:
                event.ignore()                   # let the mouse event scrub
                return
            eraser = "Eraser" in str(event.pointerType())
            self.input_mode = "tablet" if self.drawer.press(self._point(event), event.pressure(), eraser,
                                                            whole=_shift(event)) else None
            event.accept()
        elif kind == QtCore.QEvent.TabletMove:
            if self.input_mode == "tablet":
                self.drawer.move(self._point(event), event.pressure())
                event.accept()
            else:
                event.ignore()
        elif kind == QtCore.QEvent.TabletRelease:
            if self.input_mode == "tablet":
                self.input_mode = None
                self.drawer.release(self._point(event))
                event.accept()
            else:
                event.ignore()

    def update_draw_buttons(self):
        self.b_draw.setChecked(self.drawer.on)
        self.b_drawings.setChecked(self.drawer.show)

    def _set_show_drawings(self, on):
        self.drawer.show = on
        self.drawer.save_prefs()
        self.canvas.update()

    def _set_gate_mask(self, on):
        self.gate_mask = on
        self.b_gate.setChecked(on)
        self.prefs["gate_mask"] = on
        self._save_prefs()
        self.canvas.update()

    def _paint_gate(self, p, target):
        """Film gate mask: 75% black outside what's in shot, thin line on the gate."""
        gate = None
        for cam in self.cfg.get("cameras") or []:
            if cam.get("name") == self.view:
                gate = cam.get("gate")
        W, H = int(self.cfg.get("width") or 960), int(self.cfg.get("height") or 540)
        rect = self.drawui.drawing.film_gate_rect(gate, W, H)
        if rect is None:
            return
        s = target.width() / float(W)
        inner = QtCore.QRectF(target.x() + rect[0] * s, target.y() + rect[1] * s, rect[2] * s, rect[3] * s)
        outer = QtCore.QRectF(target)
        shade = QtGui.QColor(0, 0, 0, 191)
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(shade)
        p.drawRect(QtCore.QRectF(outer.left(), outer.top(), outer.width(), inner.top() - outer.top()))
        p.drawRect(QtCore.QRectF(outer.left(), inner.bottom(), outer.width(), outer.bottom() - inner.bottom()))
        p.drawRect(QtCore.QRectF(outer.left(), inner.top(), inner.left() - outer.left(), inner.height()))
        p.drawRect(QtCore.QRectF(inner.right(), inner.top(), outer.right() - inner.right(), inner.height()))
        p.setPen(QtGui.QPen(QtGui.QColor(150, 150, 150), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(inner)
        p.restore()

    def set_paused(self, on=None):
        """Pause / resume re-rendering. Sent straight to the background Maya
        (works even while your Maya is busy); resume starts at this frame."""
        on = self.b_pause.isChecked() if on is None else bool(on)
        frame = self._live_frame()
        common.post_message(self.session, {"op": "pause", "on": on,
                                           "focus": frame if frame is not None else self.start})
        self._show_paused(on)
        self._flash_message("Re-rendering paused: edits keep coming in, changed frames stay red"
                            if on else "Re-rendering resumed from this frame")

    def _show_paused(self, on):
        self.paused = on
        self.b_pause.blockSignals(True)
        self.b_pause.setChecked(on)
        self.b_pause.setText("Resume" if on else "Pause")
        self.b_pause.blockSignals(False)

    def _maya_cmd(self, cmd, message):
        self.send_cmd(cmd)
        self._flash_message(message)

    def scrub(self, canvas, event):
        if canvas.width() <= 0:
            return
        x = min(max(self._point(event).x(), 0), canvas.width() - 1)
        old = self.pos
        self._set_pos(int(x * self.total / float(canvas.width())))
        self._scrub_sound(old)
