"""Player: The focus range (I / O, the handles on the bar) and, 0.9.0b8, your Maya's playback range: with Sync on they're the same; Match Maya; the shot's cut.

Part of the Player (bgcache/player.py); see DEVELOPER.md."""
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401


class RangeMixin(object):
    # ---------------------------------------------------------------- focus range (b18)
    def set_focus(self, first=None, last=None, clear=False, save=True, origin="player"):
        """Cache only first-last of your shot. Frames outside that your edits
        change go red but wait; widening the range (or clearing it) lets the
        background Maya redo them. b4: Play also stays inside the range (and
        loops it); stepping and scrubbing still go anywhere."""
        if clear:
            self.focus_range = None
        else:
            a, b = self.focus_range or (self.start, self.end)
            a = a if first is None else first
            b = b if last is None else last
            a, b = max(self.start, min(a, self.end)), max(self.start, min(b, self.end))
            if a > b:
                a, b = b, a
            self.focus_range = None if (a, b) == (self.start, self.end) else (a, b)
        self._focus_from = origin
        if save:                 # b19: while a handle is dragged, only when you let go
            self._save_cameras()
        self._update_match_button()
        self._update_status()
        self.canvas.update()

    def _in_focus(self, frame):
        return not self.focus_range or self.focus_range[0] <= frame <= self.focus_range[1]

    def _dirty_in_focus(self):
        dirty = self.dirty.get(self.view, set()) if self.view else set()
        return {f for f in dirty if self._in_focus(f)}

    def _focus_key(self, which):
        """I / O: set the focus start / end at the frame you're on (Shift: back to the shot's end)."""
        frame = self.current_live_frame()
        if frame is None:
            self._flash_message("I and O set the focus range on your own shot", 2.5)
            return
        if which == "in":
            self.set_focus(first=frame)
        else:
            self.set_focus(last=frame)
        a, b = self.focus_range or (self.start, self.end)
        self._flash_message("Caching %d-%d only" % (a, b) if self.focus_range else "Caching the whole shot", 2.0)

    def _bar_x(self, canvas, frame, right=False):
        n = float(self.total) or 1.0
        local = self._live_offset() + frame - self.start + (1 if right else 0)
        return int(canvas.width() * local / n)

    def _handle_at(self, canvas, event):
        """'in' / 'out' if the press is on a focus handle in the cache bar."""
        pt = self._point(event)
        if pt.y() < canvas.height() - BAR_H - TAB_H - 2:
            return None
        a, b = self.focus_range or (self.start, self.end)
        xin, xout = self._bar_x(canvas, a), self._bar_x(canvas, b, right=True)
        # b4: a wider grab, reaching inward over the tab
        if -4 <= pt.x() - xin <= TAB_W + 2 and (abs(pt.x() - xin) <= abs(pt.x() - xout)):
            return "in"
        if -4 <= xout - pt.x() <= TAB_W + 2:
            return "out"
        return None

    def _frame_at(self, canvas, event):
        n = self.total or 1
        x = min(max(self._point(event).x(), 0), canvas.width() - 1)
        local = int(x * n / float(max(1, canvas.width()))) - self._live_offset()
        return self.start + local
        self._update_cam_button()
        self.canvas.update()

    def _update_cam_button(self):
        name = self._label(self.view) if self.view else "pick a camera"
        n = len(self.checked)
        short = name if len(name) <= 24 else name[:11] + "\u2026" + name[-11:]   # long names shortened
        self.cam_button.setText("%s    %d cached  \u25be" % (short, n) if n else "%s  \u25be" % short)
        self.setWindowTitle("bgcache %s player - %s" % (__version__, self._label(self.view) or "no camera"))

    @staticmethod
    def _label(cam):
        return cam.split("|")[-1] if cam else ""

    # ================================================================ range sync (b8)
    def _follow_maya_range(self):
        """Your Maya's playback range changed: shown on the bar (blue); with
        Sync on, the focus follows it. With Sync off a note says so once,
        and Match Maya stays on the playback bar while they differ."""
        st = common.read_json(self.p["maya_range"])
        if not st or st.get("ts", 0) <= self._maya_range_ts or not st.get("range"):
            return
        self._maya_range_ts = st["ts"]
        self.maya_range = (int(st["range"][0]), int(st["range"][1]))
        if self.sync:
            self.match_maya_range()
        elif self.maya_range != self._focus_or_shot() and not self._range_noted:
            self._range_noted = True
            self._flash_message("Your Maya's range is now %d-%d. Sync is off, so the focus stays: "
                                "Match Maya (on the playback bar) makes them the same" % self.maya_range, 6.0)
        self._update_match_button()
        self.canvas.update()

    def _focus_or_shot(self):
        return self.focus_range or (self.start, self.end)

    def match_maya_range(self):
        """The focus becomes your Maya's playback range (the whole shot: no focus)."""
        a, b = self.maya_range
        if (a, b) != self._focus_or_shot():
            self.set_focus(a, b, origin="maya")
        self._update_match_button()

    def _update_match_button(self):
        button = getattr(self, "b_match", None)
        if button is not None:
            button.setVisible(not self.sync and self.maya_range != self._focus_or_shot())

    def _check_close_request(self):
        """b8: your Maya is stopping bgcache (Stop, another scene, quitting):
        ask to save unsaved drawings first, then close."""
        st = common.read_json(self.p["player_close"])
        if not st or st.get("ts", 0) <= getattr(self, "_close_ts", 0):
            return
        self._close_ts = st["ts"]
        unsaved = bool(self.drawer.unsaved()) and not self.test_mode
        self._answer_close("asking" if unsaved else "closing", st["ts"])
        if unsaved:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.drawer.ask_to_save(self, "%s" % (st.get("reason") or "closing"), cancel=False)
            self._answer_close("closing", st["ts"])
        self._close_quietly = True
        self.close()

    def _answer_close(self, state, ts):
        try:
            common.write_json_atomic(self.p["player_close"] + ".answer", {"ts": ts, "state": state})
        except (IOError, OSError) as error:
            print("bgcache player: couldn't answer your Maya: %s" % error)

    def _cut(self):
        """The shot's cut (first, last), or None when the whole shot is the cut."""
        cut = self.cfg.get("cut")
        if not cut or (int(cut[0]), int(cut[1])) == (self.start, self.end):
            return None
        return int(cut[0]), int(cut[1])

    def _outside_cut(self, frame):
        cut = self._cut()
        return bool(cut) and frame is not None and not cut[0] <= frame <= cut[1]
