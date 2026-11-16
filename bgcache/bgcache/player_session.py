"""Player: Talking to your Maya and the background Maya: time sync, Reload scene, health banners, reading new frames (status.json), closing when your Maya asks.

Part of the Player (bgcache/player.py); see DEVELOPER.md."""
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401


class SessionMixin(object):
    # ================================================================ time sync
    def send_time(self):
        frame = self._live_frame()
        if frame is None:
            return            # on a neighbour shot: Maya stays where it is
        try:
            common.write_json_atomic(self.p["player_time"], {
                "frame": frame, "ts": time.time(), "sync": self.sync})
        except (IOError, OSError):
            pass

    def send_cmd(self, cmd, **extra):
        msg = {"cmd": cmd, "ts": time.time(), "frame": self._live_frame() or self.start}
        self._last_cmd_ts = msg["ts"]
        msg.update(extra)
        try:
            common.write_json_atomic(self.p["player_cmd"], msg)
        except (IOError, OSError):
            pass

    def _follow_maya(self):
        st = common.read_json(self.p["maya_time"])
        if not st or st.get("ts", 0) <= self._maya_ts:
            return
        self._maya_ts = st["ts"]
        if st.get("raise"):                 # the shelf button, while bgcache runs
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return
        if st.get("note"):                  # a message from your Maya, e.g. a reload that failed
            self._reload_asked = None
            self._flash_message(st["note"], 8.0)
            return
        if (not self.sync and not st.get("force")) or self.playing or self.dragging:
            return              # "force": a step-key jump, followed even with Sync off
        frame = int(st["frame"])
        if self.start <= frame <= self.end:
            pos = self._live_offset() + frame - self.start
            if pos != self.pos:
                self.pos = pos
                self.canvas.update()

    # ================================================================ reload
    RELOAD_GIVE_UP_S = 600        # no sign of the reload by then: stop saying it's coming

    def reload_scene(self):
        """Cache > Reload scene: your Maya exports the scene (can take a while
        on a heavy shot), then the background Maya reopens it. A banner over
        the picture says which stage it's at until it's done."""
        self.send_cmd("reload")
        self._reload_asked = (time.time(), self.cfg.get("rev", 1), self._reloads_done or 0)
        self.canvas.update()

    def _reload_banner(self):
        """The reload banner's text, or None when no reload is going on."""
        clock = lambda since: "%d:%02d" % divmod(int(max(0, time.time() - since)), 60)
        if self.state == "reloading scene":
            since = self.cfg.get("reloaded_at") or (self._reload_asked or (time.time(),))[0]
            return "Reloading scene in the background Maya... %s   (the picture is from before)" % clock(since)
        if self._reload_asked:
            asked, rev, _done = self._reload_asked
            if self.cfg.get("rev", 1) != rev:
                return "Reloading scene in the background Maya... %s" % clock(asked)
            if time.time() - asked > self.RELOAD_GIVE_UP_S:
                self._reload_asked = None
                self._flash_message("Reload scene didn't start: see your Maya's Script Editor", 6.0)
                return None
            return "Reload scene: your Maya is exporting the scene... %s" % clock(asked)
        return None

    def _track_reload(self, status):
        """Called on every status read: notices a finished reload (yours, or
        one started from the Maya panel), however quick it was."""
        done = int(status.get("reloads") or 0)
        if self._reloads_done is None:          # first status: just note where it's at
            self._reloads_done = done
            return
        if done > self._reloads_done and self.state != "reloading scene":
            self._reloads_done = done
            self._reload_asked = None
            self._flash_message("Scene reloaded: re-rendering all frames", 4.0)

    # ================================================================ health
    STUCK_S = 120                 # dirty frames and nothing new for this long: say so
    STUCK_GPU_S = 30              # the same, after graphics-memory errors in worker.log

    def _track_health(self):
        """On every status poll: note when caching last moved, and (every 2 s)
        look for graphics-memory errors in the background Maya's log."""
        now = time.time()
        dirty = self._dirty_in_focus()
        key = (len(dirty), sum(self.loaded.get(self.view, {}).values()) if self.view else 0)
        if key != self._progress_key or not dirty or getattr(self, "paused", False) or self._loading():
            self._progress_key, self._progress_t = key, now
        if now - self._log_check_t >= 2.0:
            self._log_check_t = now
            text, self._log_pos = common.read_new(self.p["log"], self._log_pos)
            if text and common.GPU_TROUBLE_RE.search(text):
                self._gpu_trouble_t = now

    def _health_banner(self):
        """A red banner when caching is in trouble, else None."""
        if self.test_mode or self._loading() or getattr(self, "paused", False):
            return None
        dirty = bool(self._dirty_in_focus())
        if self._warning and dirty:
            return self._warning
        stuck = time.time() - self._progress_t
        if dirty and self._gpu_trouble_t and stuck > self.STUCK_GPU_S:
            return ("GPU deformers failed in the background Maya and caching stopped: "
                    "bgcache is restarting it on the CPU. If this stays, press Stop and Start.")
        if dirty and stuck > self.STUCK_S:
            return ("Caching seems stuck: nothing new for %d:%02d. Try Stop and Start "
                    "(worker.log in ~/.bgcache/logs has the details)." % divmod(int(stuck), 60))
        return None

    # ================================================================ data
    def _check_config(self):
        """The controller rewrites config.json on Reload scene."""
        try:
            mtime = os.path.getmtime(self.p["config"])
        except OSError:
            return
        if mtime == self._cfg_mtime:
            return
        self._cfg_mtime = mtime
        cfg = common.read_json(self.p["config"])
        if not cfg or cfg.get("rev", 1) == self.cfg.get("rev", 1):
            return
        self.cfg = cfg
        self.start, self.end = int(cfg["start"]), int(cfg["end"])
        self.fps = float(cfg.get("fps") or self.fps)
        for cam in list(self.data):
            self.data[cam] = {f: b for f, b in self.data[cam].items() if self.start <= f <= self.end}
            self.loaded[cam] = {f: v for f, v in self.loaded[cam].items() if self.start <= f <= self.end}
        self.lru.clear()
        self._init_live_sound()
        self._update_cam_button()
        self._rebuild_reel()
        if self.sync:                     # b8: the shot grew (or, b11, shrank) with your range
            self.match_maya_range()
        elif self.focus_range:            # b11: keep the focus inside the shot as it is now
            a, b = self.focus_range
            if b < self.start or a > self.end:
                self.set_focus(clear=True, origin="maya")
            else:
                self.set_focus(max(a, self.start), min(b, self.end), origin="maya")

    def _loading(self):
        return self.state in ("copying scene", "snapshotting", "starting background Maya...", "starting",
                              "opening scene", "reloading scene")

    def _loading_text(self):
        since = max(self.cfg.get("launched_at") or 0, self.cfg.get("reloaded_at") or 0)
        elapsed = int(time.time() - since) if since else 0
        what = {"copying scene": "Copying your Maya scene",
                "snapshotting": "Reading your animation"}.get(self.state)
        if what:
            return "%s..." % what
        if self._warning and "GPU" in self._warning:
            # b18: the restart on the CPU reopens your scene; say so, so it isn't taken for a freeze
            since = self._rescue_seen or max(self.cfg.get("launched_at") or 0, self.cfg.get("reloaded_at") or 0)
            elapsed = int(time.time() - since) if since else 0
            return ("GPU deformers failed: restarting the background Maya on the CPU, your edits are "
                    "kept... %d:%02d" % (elapsed // 60, elapsed % 60))
        what = "Launching background Maya" if self.state.startswith("starting") else \
            "Reloading scene" if self.state == "reloading scene" else "Loading scene"
        text = "%s... %d:%02d" % (what, elapsed // 60, elapsed % 60)
        usual = self.cfg.get("usual_startup")
        if usual and not self.cfg.get("reloaded_at"):
            text += " (usually about %d:%02d)" % (int(usual) // 60, int(usual) % 60)
        return text

    def _spin(self):
        if not self.playing and (self._loading() or self._reload_asked or
                                 time.time() < self._flash_until + 0.1):
            self.canvas.update()

    def _status_changed(self):
        try:
            mtime = os.stat(self.p["status"]).st_mtime_ns
        except OSError:
            return False
        if mtime == getattr(self, "_status_mtime", None):
            return False
        self._status_mtime = mtime
        return True

    def _poll_if_changed(self):
        if self._status_changed():
            self._poll()

    def _poll(self):
        self._status_changed()          # note the version we're about to read
        self._check_config()
        st = common.read_json(self.p["status"])
        if st:
            self.state = st.get("state", "")
            self._track_reload(st)
            self._show_paused(bool(st.get("paused")))
            for cam, info in (st.get("cameras") or {}).items():
                if cam not in self.checked:
                    continue
                self.dirty[cam] = set(info.get("dirty") or [])
                for key, version in (info.get("versions") or {}).items():
                    frame = int(key)
                    if self.loaded[cam].get(frame) == version:
                        continue
                    try:
                        with open(common.frame_path(self.session, frame, cam), "rb") as handle:
                            blob = handle.read()
                    except (IOError, OSError):
                        continue
                    self.data[cam][frame] = blob
                    self.loaded[cam][frame] = version
                    self.lru.pop(("live", cam, frame), None)
            warning = st.get("warning") or ""
            if warning and not self._warning:
                self._rescue_seen = time.time()
            self._warning = warning
            self._gpu = st.get("gpu")
            self._worker_pid = st.get("pid")
        self._track_health()
        self._follow_maya()
        self._follow_maya_range()
        self.drawer.follow_place()       # b8: the strip shows the layers of the shot on screen
        self._check_close_request()
        self._update_status()
        if self.controller_pid and not common.pid_alive(self.controller_pid):
            self._close_quietly = True        # your Maya is gone: nothing to ask
            self.close()
        if not self.playing:
            self.canvas.update()

    def _update_status(self):
        text = self._loading_text() if self._loading() else self.state
        if self.state.startswith("error"):
            self.status_label.setStyleSheet("color: #ff8a80")
        elif getattr(self, "paused", False) and not self._loading():
            self.status_label.setStyleSheet("color: #e8c070")
            dirty = len(self.dirty.get(self.view, ())) if self.view else 0
            text = "paused, %d frame%s to redo" % (dirty, "" if dirty == 1 else "s")
        else:
            self.status_label.setStyleSheet("")
        if self.playing and len(self.shown) > 2:
            span = self.shown[-1] - self.shown[0]
            if span > 0:
                text += "  ·  %.1f fps" % ((len(self.shown) - 1) / span)
        else:
            text += "  ·  %.0f fps" % self.fps
        if not self.sync:
            text += "  ·  sync off"
        if self.focus_range:
            waiting = len(self.dirty.get(self.view, set()) - self._dirty_in_focus()) if self.view else 0
            text += "  ·  focus %d-%d" % self.focus_range
            if waiting:
                text += " · %d frame%s waiting outside" % (waiting, "" if waiting == 1 else "s")
        if self._warning:
            text += "  ·  GPU failed, caching on CPU"
            self.status_label.setStyleSheet("color: #ff8a80")
        elif self._gpu is False and not self._loading():
            text += "  ·  caching on CPU"          # quiet: GPU Override is off in your Maya
        self.status_label.setText(text)

    def _image(self, pos):
        seg, local = self._locate(pos)
        if seg["kind"] == "live" and seg.get("ref"):
            if local >= len(seg["ref"]):
                return None                 # reference movie shorter than the shot
            seg = {"kind": "ref", "shot": "ref", "frames": seg["ref"]}
        if seg["kind"] == "live":
            cam, frame = self.view, self.start + local
            if cam is None or frame not in self.data.get(cam, {}):
                return None
            key = ("live", cam, frame)
        else:
            key = (seg["shot"], seg["frames"][local])
        img = self.lru.get(key)
        if img is None:
            if seg["kind"] == "live":
                img = QtGui.QImage.fromData(QtCore.QByteArray(self.data[cam][frame]))
            else:
                img = QtGui.QImage(seg["frames"][local])
            self.lru[key] = img
            while len(self.lru) > LRU_SIZE:
                self.lru.popitem(last=False)
        else:
            self.lru.move_to_end(key)
        return img
