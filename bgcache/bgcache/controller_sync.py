"""Time sync between your Maya and the player (player_time.json /
maya_time.json), the player's buttons that need your Maya (player_cmd.json),
Push selected and Re-render all.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
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

    def _poll_player_time(self):
        """The player scrubbed, stepped or paused: move Maya there. Also runs
        one-off player commands (step key, image plane), with or without Sync."""
        if not self.running:
            return
        self._poll_player_cmd()
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
                self.show_image_plane(st["camera"], st["path"], int(st["offset"]), st["mode"])
            elif cmd == "image_plane_remove":
                self.remove_image_plane()
            elif cmd == "refresh":
                self.refresh_display()
            elif cmd == "push_selected":
                self.push_selected()
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
