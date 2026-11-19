"""Time sync between your Maya and the player (player_time.json /
maya_time.json), the player's buttons that need your Maya (player_cmd.json),
Push selected and Re-render all.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import os
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om

from bgcache import common, scene


class SyncMixin(object):
    # ---------------------------------------------------------------- time sync
    def _on_time_changed(self):
        """Maya's frame changed: tell the player (unless the player caused it)."""
        self.trace("time")
        if not self.running:
            return
        frame = int(round(cmds.currentTime(query=True)))
        if self._from_player is not None:
            caused = frame == self._from_player
            self._from_player = None
            if caused:
                return
        if not self.sync_enabled:
            return
        now = time.time()
        # b18: while your own Maya plays, tell the player at most 4 times a
        # second (it was a file write on every frame); the frame it stops on
        # is always sent (the playingBack job below).
        try:
            playing = bool(cmds.play(query=True, state=True))
        except Exception:  # Maya busy or closing: count as not playing
            playing = False
        if playing and now - getattr(self, "_time_written", 0.0) < 0.25:
            return
        self._time_written = now
        try:
            common.write_json_atomic(common.paths(self.session)["maya_time"],
                                     {"frame": frame, "ts": now})
        except (IOError, OSError):
            pass

    # ---------------------------------------------------------------- range sync (b8)
    def _on_range_changed(self):
        """Your playback range changed: tell the player (it shows it, and
        with Sync its focus follows). Frames past the shot it knows are added
        (animating outside the cut)."""
        if not self.running:
            return
        try:
            now = scene.playback_range()
        except Exception as error:     # Maya busy or closing: the next change sends it
            scene._ignored(error)
            return
        self.trace("range", "%d-%d" % tuple(now))
        # b11: the shot as laid out is the cut plus your range: it grows when
        # your range goes past the cut, and goes back when you close it again
        cut = self.cfg.get("cut") or [self.cfg["start"], self.cfg["end"]]
        want = [min(int(cut[0]), now[0]), max(int(cut[1]), now[1])]
        if want != [self.cfg["start"], self.cfg["end"]]:
            self._grow(want[0], want[1])
        self._write_maya_range(now)

    def _write_maya_range(self, now):
        self.cfg["maya_range"] = list(now)
        try:
            common.write_json_atomic(common.paths(self.session)["maya_range"],
                                     {"range": list(now), "ts": time.time()})
        except (IOError, OSError) as error:
            scene._ignored(error)

    def _grow(self, first, last):
        """The shot as laid out is now first-last (your range went past the
        cut, or came back): the hidden Maya renders new frames when they're
        in focus, the player lays it out again."""
        print("bgcache: the shot is now %d-%d (was %d-%d)"
              % (first, last, self.cfg["start"], self.cfg["end"]))
        self.cfg.update({"start": int(first), "end": int(last), "rev": int(self.cfg.get("rev", 1)) + 1})
        common.write_json_atomic(common.paths(self.session)["config"], self.cfg)
        common.post_message(self.session, {"op": "grow", "start": int(first), "end": int(last)})

    def _follow_player_focus(self):
        """With Sync on, the player's focus range (I / O, its handles) is your
        playback range; clearing it opens your range to the whole shot."""
        path = common.paths(self.session)["cameras"]
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if mtime == getattr(self, "_cameras_mtime", None):
            return
        self._cameras_mtime = mtime
        want = common.read_json(path) or {}
        self._watch_cameras(want.get("checked"))      # b12: cameras you move without keys
        if "focus" not in want or not self.sync_enabled or want.get("focus_from") == "maya":
            return           # b8: "maya": the player followed your range; nothing to send back
        focus = want.get("focus") or [self.cfg["start"], self.cfg["end"]]
        a, b = int(focus[0]), int(focus[1])
        if [a, b] == scene.playback_range():
            return
        self.trace("range-from-player", "%d-%d" % (a, b))
        if a < cmds.playbackOptions(query=True, animationStartTime=True):
            cmds.playbackOptions(animationStartTime=a)
        if b > cmds.playbackOptions(query=True, animationEndTime=True):
            cmds.playbackOptions(animationEndTime=b)
        cmds.playbackOptions(minTime=a, maxTime=b)
        self._write_maya_range([a, b])

    def _poll_player_time(self):
        """The player scrubbed, stepped or paused: move Maya there. Also runs
        one-off player commands (step key, image plane), with or without Sync."""
        if not self.running:
            return
        self._poll_player_cmd()
        self._follow_player_focus()
        self._send_moved_cameras()
        self._send_shown_hidden()           # b20: assets you showed or hid
        st = common.read_json(common.paths(self.session)["player_time"])
        if st and st.get("ts", 0) > self._player_ts:
            self._player_ts = st["ts"]
            self.sync_enabled = bool(st.get("sync", True))
            # Don't move Maya on every frame the player passes (stepping,
            # scrubbing, flipping through drawings): each move makes Maya
            # evaluate the whole rig. Wait until the player rests on a frame.
            self._pending_frame = (int(st["frame"]), time.time()) if self.sync_enabled else None
        self._apply_pending_frame()

    def _apply_pending_frame(self):
        """Move Maya to the player's frame once it has rested there SETTLE_S."""
        pending = getattr(self, "_pending_frame", None)
        if not pending or time.time() - pending[1] < scene.SETTLE_S:
            return
        self._pending_frame = None
        if not self.sync_enabled or cmds.play(query=True, state=True):
            return
        frame = pending[0]
        if int(round(cmds.currentTime(query=True))) != frame:
            self._from_player = frame
            cmds.currentTime(frame)

    def _poll_player_cmd(self):
        st = common.read_json(common.paths(self.session)["player_cmd"])
        if not st or st.get("ts", 0) <= self._cmd_ts:
            return
        self._cmd_ts = st["ts"]
        cmd = st.get("cmd")
        try:          # tells the player your Maya got it (its Stop steps in if not)
            common.write_json_atomic(common.paths(self.session)["player_cmd"] + ".done", {"ts": st["ts"]})
        except (IOError, OSError) as error:
            scene._ignored(error)
        self.trace("player-cmd", cmd)
        try:
            if cmd in ("next_key", "prev_key"):
                # Same as Maya's step-key buttons: keys of the selection on the time slider.
                which = "next" if cmd == "next_key" else "previous"
                frame = int(round(cmds.findKeyframe(timeSlider=True, which=which)))
                self._from_player = frame
                cmds.currentTime(frame)
                # the player follows a key step even with Sync off
                common.write_json_atomic(common.paths(self.session)["maya_time"],
                                         {"frame": frame, "ts": time.time(), "force": True})
            elif cmd == "image_plane":
                self.show_image_plane(st["camera"], st["path"], int(st["offset"]), st["mode"], st.get("alpha"))
            elif cmd == "image_plane_alpha":
                self.set_image_plane_alpha(st.get("alpha", 1.0))
            elif cmd == "image_plane_remove":
                self.remove_image_plane()
            elif cmd == "refresh":
                self.refresh_display()
            elif cmd == "push_selected":
                self.push_selected()
            elif cmd in ("cache_show_selected", "cache_remove_selected"):
                self.cache_selected(cmd == "cache_show_selected")
            elif cmd == "cache_forget":
                self.cache_forget(st.get("nodes"))
            elif cmd == "reload":
                self.reload_scene()
            elif cmd == "rerender":
                self.rerender_all()
            elif cmd == "selftest":
                from bgcache import selftest
                selftest.run()
            elif cmd == "bp_import":
                self.blue_pencil_import(st.get("path"))
            elif cmd == "stop":
                cmds.evalDeferred(self.stop)       # after this poll returns
            elif cmd == "restart":
                cmds.evalDeferred(self.restart)
            elif cmd == "update":
                from bgcache import update
                path = st.get("path")
                cmds.evalDeferred(lambda: update.update_and_restart(path))
        except Exception as error:
            om.MGlobal.displayWarning("bgcache: %s: %s" % (cmd, error))

    def blue_pencil_import(self, path):
        """The player saved a Blue Pencil zip: copy its path for you and open
        Maya's Blue Pencil import dialog (the only way in; you pick the file)."""
        print("bgcache: Blue Pencil drawings saved to %s" % path)
        try:
            from PySide6 import QtWidgets
        except ImportError:  # Maya 2024 and earlier (PySide2)
            from PySide2 import QtWidgets
        try:
            QtWidgets.QApplication.clipboard().setText(path or "")
        except Exception as error:
            scene._ignored(error)
        try:
            cmds.bluePencilFrame(importFrames=True)
            print("bgcache: the file's path is on your clipboard: paste it into the import dialog")
        except Exception as error:
            om.MGlobal.displayWarning(
                "bgcache: could not open Blue Pencil's import (%s). Use Blue Pencil > Import "
                "and pick %s" % (error, path))

    # ---------------------------------------------------------------- manual sync
    def push_selected(self):
        """Send static (unkeyed) values and curves of the selected controls.

        Use after changing attributes that have no keys, e.g. a space switch or
        a rig setting you typed in without keying. Dirties the whole range.
        """
        self.trace("push-selected")
        if not self.running:
            return
        values = []
        for node in cmds.ls(selection=True, long=True) or []:
            attrs = set(cmds.listAttr(node, keyable=True, scalar=True) or [])
            attrs.update(cmds.listAttr(node, channelBox=True) or [])
            for attr in attrs:
                plug = "%s.%s" % (node, attr)
                try:
                    if cmds.listConnections(plug, source=True, destination=False):
                        continue  # animated or driven: handled by curves/rig
                    values.append([plug, cmds.getAttr(plug)])
                except Exception as error:
                    scene._ignored(error)
            for curve in cmds.listConnections(node, source=True, destination=False,
                                              type="animCurve") or []:
                self.pending.add(curve)
        common.post_message(self.session, {
            "op": "statics", "values": values,
            "ranges": [[self.cfg["start"], self.cfg["end"]]]})
        self.flush()
        print("bgcache: pushed %d static values" % len(values))

    def rerender_all(self):
        self.trace("rerender-all")
        if self.running:
            common.post_message(self.session, {
                "op": "dirty", "ranges": [[self.cfg["start"], self.cfg["end"]]]})
