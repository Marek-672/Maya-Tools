"""Player: The reel (the shots before yours, yours, the shots after) and its sound: loading, timing, the sync test.

Part of the Player (bgcache/player.py); see DEVELOPER.md."""
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401


class ReelMixin(object):
    # ================================================================ sound
    def _init_live_sound(self):
        self.live_pcm, self.live_status = None, "no sound in scene"
        info = self.cfg.get("audio")
        if not info:
            return
        if info.get("mute"):
            self.live_status = "sound muted in Maya"
            return
        try:
            self.live_pcm, self.channels, self.rate = self.audio_mod.load_aligned(
                info, self.start, self.end, self.fps)
            self.live_status = "sound on"
        except Exception as error:
            self.live_status = "sound unreadable: %s" % error
            print("bgcache: %s (%s)" % (self.live_status, info.get("path")))

    def _rebuild_sound(self):
        parts, any_sound = [], False
        n_live = self.end - self.start + 1
        for seg in self.segments:
            if seg["kind"] == "live":
                parts.append(self.audio_mod.fit(self.live_pcm, n_live, self.fps, self.rate, self.channels))
                any_sound = any_sound or self.live_pcm is not None
            else:
                parts.append(seg["pcm"])
                any_sound = any_sound or bool(seg["sound"])
        if self.live_pcm is not None or not any_sound:
            status = self.live_status
        else:                                   # neighbours play, your shot doesn't: say so
            status = "sound on, except your shot (%s)" % self.live_status
        self.sound.set_pcm(b"".join(parts) if any_sound else b"", self.channels, self.rate, self.fps, status)

    def _sound_text(self):
        if self.sound.muted:
            return "sound off (M)"
        return self.sound.status

    # ================================================================ reel
    def _rebuild_reel(self):
        """Before shots + live shot + after shots, in sequence order."""
        if self.test_mode:
            return            # rebuilt when the sync test ends
        anchor = self._locate(self.pos) if self.segments else None
        order = {s: i for i, s in enumerate(self.shots)}
        segs = []

        def neighbours(side):
            out = []
            if not self.continuity_on:
                return out
            for shot in sorted(self.staged[side], key=lambda s: order.get(s, 1e9)):
                ready = self.prepared.get(shot)
                if ready:
                    out.append({"kind": side, "shot": shot, "n": len(ready["frames"]),
                                "frames": ready["frames"], "pcm": ready["pcm"], "sound": ready["sound"],
                                "first": ready["first"], "label": self._footage_label(ready["info"])})
            return out

        segs += neighbours("before")
        live = {"kind": "live", "shot": self.live_shot, "n": self.end - self.start + 1}
        if self.live_ref and self.live_ref_ready:
            live["ref"] = self.live_ref_ready["frames"]
            live["label"] = self._footage_label(self.live_ref_ready["info"])
        segs.append(live)
        segs += neighbours("after")
        self.segments = segs
        self.total = sum(s["n"] for s in segs)
        # stay on the same picture if it's still in the reel
        if anchor:
            seg, local = anchor
            if seg["kind"] == "live":
                self.pos = self._live_offset() + local
            else:
                self.pos = next((o + local for o, s in self._offsets() if s["shot"] == seg["shot"]),
                                self._live_offset())
        self.pos = min(max(self.pos, 0), self.total - 1)
        self._rebuild_sound()
        self._update_strip_header()
        direction = self.playing
        if direction:                      # restart cleanly from the same picture
            self._stop()
            self.toggle_play(direction)
        self.canvas.update()

    def _offsets(self):
        o = 0
        for s in self.segments:
            yield o, s
            o += s["n"]

    def _live_offset(self):
        for o, s in self._offsets():
            if s["kind"] == "live":
                return o
        return 0

    def _locate(self, pos):
        for o, s in self._offsets():
            if pos < o + s["n"]:
                return s, pos - o
        if not self.segments:        # b8: before the reel is built (the drawing strip asks early)
            n = self.end - self.start + 1
            return {"kind": "live", "shot": getattr(self, "live_shot", None), "n": n}, min(max(pos, 0), n - 1)
        last = self.segments[-1]
        return last, last["n"] - 1

    def _live_frame(self, pos=None):
        seg, local = self._locate(self.pos if pos is None else pos)
        return self.start + local if seg["kind"] == "live" else None

    def _move_to_live(self, frame):
        self.pos = self._live_offset() + min(max(frame, self.start), self.end) - self.start

    def _range_text(self):
        return self._range_texts()[0]

    def _range_texts(self):
        """The playback bar's range text, longest first: shot numbers around
        your range, then counts ("3 before · 1001 – 1100 · 2 after"), then
        the range alone. The label shows the first that fits."""
        short = lambda shot: shot.split("_")[-1]
        segs = getattr(self, "segments", None) or []
        before = [short(s["shot"]) for s in segs if s["kind"] == "before"]
        after = [short(s["shot"]) for s in segs if s["kind"] == "after"]
        cut = self._cut()
        rng = "%d – %d" % (cut or (self.start, self.end))
        if cut:                                   # b8: frames animated past the cut
            rng += " (+%d outside the cut)" % ((self.end - self.start + 1) - (cut[1] - cut[0] + 1))
        full = "  ·  ".join(([" ".join(before)] if before else []) + [rng] + ([" ".join(after)] if after else []))
        counts = "  ·  ".join((["%d before" % len(before)] if before else []) + [rng]
                              + (["%d after" % len(after)] if after else []))
        return [full, counts, rng]














    def _flash_message(self, text, seconds=3.0):
        self._flash, self._flash_until = text, time.time() + seconds
        self.canvas.update()




    def _update_strip_header(self):
        """The ticked shots are shown by their cards (and the range text in
        the playback bar); 0.7.3 removed the Before/After list from here."""
        if getattr(self, "range_label", None) is not None:
            self.range_label.set_texts(self._range_texts())
            where = {"studio": "the studio's shot settings", "outer range": "your Maya's outer range (the range slider's ends)",
                     "playback range": "your Maya's playback range"}.get(self.cfg.get("range_from"), "your Maya")
            cut = self._cut()
            self.range_label.setToolTip("The shot: %d-%d, from %s.%s" % (
                tuple(self.cfg.get("cut") or (self.start, self.end)) + (where,
                " Frames %d-%d are laid out so you can animate past the cut: they're marked purple." % (self.start, self.end)
                if cut else "")))

    def _save_prefs(self):
        self._continuity_prefs()
        common.save_prefs(self.prefs)



    # ================================================================ sound timing
    def _sound_pos(self, pos):
        """Where in the soundtrack to start for picture position pos, shifted
        by your offset from the sync test (+ = earlier). Nothing automatic:
        the audio buffer size is not the real delay (it made sound ~6 frames early)."""
        return pos + self.audio_offset

    def _play_sound(self, pos):
        start = self._sound_pos(pos)
        token = self._play_token = object()
        if start >= 0:
            self.sound.play(start)
        else:   # sound should start later than the picture: wait
            QtCore.QTimer.singleShot(int(-start / self.fps * 1000), lambda: (
                self.playing > 0 and self._play_token is token and self.sound.play(0)))

    def _scrub_sound(self, old):
        if self.scrub_on and not self.playing and self.pos != old:
            self.sound.scrub(max(0.0, self._sound_pos(self.pos)))

    def _set_offset(self, frames):
        self.audio_offset = round(frames, 2)
        self.prefs["audio_offset"] = self.audio_offset
        self._save_prefs()
        if self.playing > 0:
            self._play_sound(self.pos)     # hear the change right away
        when = "earlier" if self.audio_offset > 0 else "later" if self.audio_offset < 0 else ""
        self._flash = "sound offset %+.2f frames %s" % (self.audio_offset, when)
        self._flash_until = time.time() + 2.0
        self.canvas.update()

    def _set_scrub(self, on):
        self.scrub_on = on
        self.b_scrub.setChecked(on)
        self.prefs["scrub"] = on
        self._save_prefs()

    # ---------------------------------------------------------------- sync test
    def toggle_sync_test(self):
        """Flash + click once a second; nudge [ ] until they line up."""
        self._stop()
        if self.test_mode:
            self.test_mode = False
            self.pos = self._test_saved_pos
            self._rebuild_reel()
            self.canvas.update()
            return
        self._test_saved_pos = self.pos
        self.test_mode = True
        self.test_every = max(1, int(round(self.fps)))
        self.total = self.test_every * 4
        self.pos = 0
        self.sound.set_pcm(self.audio_mod.click_track(self.total, self.fps, self.rate, self.channels,
                                                      self.test_every),
                           self.channels, self.rate, self.fps, "sync test")
        if self.sound.muted:
            self._set_mute(False)
        self.toggle_play(1)
