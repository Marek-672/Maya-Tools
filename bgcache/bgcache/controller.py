"""Foreground half of bgcache. Runs in the Maya session you animate in.

    import bgcache.controller as bgc
    bgc.show_ui()

The Controller is split over a few files (0.8.0b21 clean-up):
    controller.py           this file: start, launch, stop, status, the shelf
                            and panel functions (get, shelf_click, unload...)
    controller_edits.py     Maya callbacks, trace.log, path curves, flush
    controller_refresh.py   Refresh, Reload scene
    controller_gpu.py       restart the hidden Maya on the CPU if the GPU fails
    controller_sync.py      time sync, the player's buttons, Push selected,
                            Re-render all
    controller_refplane.py  the player's reference movie as an image plane
    scene.py                plain functions that read your scene and Maya
Older names (bgcache.controller.list_cameras etc.) still work.

How dirty frames are worked out
-------------------------------
At start we snapshot every time-based anim curve (key times, values, tangents).
When Maya reports curves were edited, we re-read just those curves and diff them
against the snapshot. For each key that changed, the affected frames run from
the nearest unchanged key before it to the nearest unchanged key after it.
Auto/spline tangents that Maya recomputes on neighbouring keys show up as
changed keys too, so they widen the range automatically. Curves with
non-constant infinity (cycle, linear, ...) dirty the whole range.
"""
import collections
import getpass
import math
import os
import subprocess
import time

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from bgcache import common, profile
from bgcache import __version__
from bgcache import scene
from bgcache.scene import *            # noqa: F401,F403  old names: bgcache.controller.list_cameras etc.
from bgcache.scene import (_active_model_panel, _audio_muted, _fmt, _ignored,          # noqa: F401
                           _is_startup_camera, _maya_hotkeys, _mobj, _mouse_held,
                           _pkg_parent, _r, _shot_camera_panel, _visible_model_panels)
from bgcache.controller_refresh import RefreshMixin
from bgcache.controller_gpu import GpuRescueMixin
from bgcache.controller_edits import EditsMixin
from bgcache.controller_sync import SyncMixin
from bgcache.controller_refplane import RefPlaneMixin


PANEL_LABEL = "Background playback cache %s" % __version__

try:
    from PySide6 import QtCore
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore


# Started in the background Maya and the player. bgcache's folder comes from
# the BGCACHE_PKG environment variable, so the commands are fixed strings:
# a folder path inside them (spaces, Windows backslashes) would break the
# quoting. The folder also goes on sys.path here because studio launchers
# can reset PYTHONPATH.
WORKER_COMMAND = ('python("import os, sys; sys.path.insert(0, os.environ[\'BGCACHE_PKG\']); '
                  'import bgcache.worker; bgcache.worker.boot()")')
PLAYER_BOOT = ("import os, sys; sys.path.insert(0, os.environ['BGCACHE_PKG']); import runpy; "
               "runpy.run_module('bgcache.player', run_name='__main__')")


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------
class Controller(RefreshMixin, GpuRescueMixin, EditsMixin, SyncMixin, RefPlaneMixin):
    def __init__(self):
        self.session = None
        self.cfg = None
        self.snap = {}
        self.recent = collections.deque(maxlen=300)
        self.pending = set()
        self.pending_handles = []
        self.removed = []
        self.callback_ids = []
        self.job_ids = []
        self.worker_proc = None
        self.player_proc = None
        self.player_widget = None
        self.mayapy_cmd = None
        self.status_label = None
        self.buttons = {}
        self.ignore = set()
        self._trace_last = {}
        self.scene_cb_ids = []
        self.static_vals = {}       # unkeyed attribute values, recorded on selection
        self.vis_base = {}
        self._progress_on = False
        self.loading_since = None    # set while the background Maya is (re)loading
        self.loading_kind = None
        self.exit_reported = False

        self.flush_timer = QtCore.QTimer()
        self.flush_timer.setSingleShot(True)
        self.flush_timer.timeout.connect(self.flush)
        self.status_timer = QtCore.QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.sync_timer = QtCore.QTimer()
        self.sync_timer.timeout.connect(self._poll_player_time)
        self._player_ts = 0.0
        self._cmd_ts = 0.0
        self.save_cb = None
        self._from_player = None
        self.sync_enabled = True

    @property
    def running(self):
        return self.session is not None

    # ---------------------------------------------------------------- start
    def start(self, width=960, height=540, chunk=12, quality=85,
              switch_off_tools=True, hide_background=True,
              skip_in_background=None, skip_user_setup=False,
              light_background=True, trace=True, refresh_background_prefs=False,
              maya_cmd=None, mayapy_cmd=None, stop_rig_callbacks=None):
        """Snapshot curves, launch the background Maya and the player.

        If the scene has unsaved changes (or is read-only), a private copy is
        exported for the background Maya; your own file is never saved.

        switch_off_tools: switch off the pipeline profile's
            switch_off_in_background tools inside the background Maya.
            (stop_rig_callbacks: the old name for it.)
        hide_background: minimize the background Maya's windows.
        skip_in_background: tools left out of the background Maya (matched
            against its module/script/plug-in paths). Default: the pipeline
            profile's skip_in_background (animBot).
        skip_user_setup: also skip userSetup.py in the background Maya.
        trace: write trace.log (what bgcache does in your Maya, for crash hunting).
        refresh_background_prefs: re-copy your preferences into the background
            Maya's own preferences folder (after changing a viewport setting, say).
        light_background: start the background Maya without auto-loaded
            plug-ins; the plug-ins your scene's nodes use are loaded for it.
        maya_cmd / mayapy_cmd: optional argument lists if your studio needs a
        wrapper instead of $MAYA_LOCATION/bin/maya and bin/mayapy.
        """
        if self.running:
            cmds.warning("bgcache is already running.")
            return
        check_undo()
        if stop_rig_callbacks is not None:
            switch_off_tools = stop_rig_callbacks
        if skip_in_background is None:
            skip_in_background = profile.get("skip_in_background") or ()
        self.session = common.new_session()
        self.exit_reported = False
        self._gpu_log_pos = 0       # how far worker.log has been read for GPU errors
        self._gpu_trouble_t = None  # when GPU errors last showed up in it
        self._gpu_log_t = 0.0
        self.gpu_rescued = False    # restarted on the CPU once this session
        self._update_buttons()
        try:
            self._start(width, height, chunk, quality, switch_off_tools,
                        hide_background, maya_cmd, mayapy_cmd,
                        skip_in_background, skip_user_setup, light_background, trace,
                        refresh_background_prefs)
        finally:
            self._progress_end()
            self._update_buttons()

    def _start(self, width, height, chunk, quality, switch_off_tools,
               hide_background, maya_cmd, mayapy_cmd, skip_in_background, skip_user_setup,
               light_background, trace, refresh_background_prefs):
        """Start's steps, in order: write config.json, open the player, copy
        the scene if needed, snapshot curves, start the hidden Maya, then
        watch your edits."""
        self.cfg = {"trace": bool(trace)}      # so the first trace lines are written
        t_click = time.time()
        self.trace("start", cmds.file(query=True, sceneName=True) or "untitled")
        swept = common.prune_sessions(keep=self.session)
        if swept:
            print("bgcache: removed %d leftover session folder(s) from earlier runs" % swept)
        must_copy = not cmds.file(query=True, sceneName=True) or cmds.file(query=True, modified=True)
        self.mayapy_cmd = mayapy_cmd
        self.cfg = self._session_config(width, height, chunk, quality, switch_off_tools, hide_background,
                                        skip_in_background, skip_user_setup, light_background, trace)
        common.write_json_atomic(common.paths(self.session)["config"], self.cfg)
        self._pre_pick_camera()
        # b13: the player opens first and says what's happening, instead of
        # nothing on screen while your scene is copied.
        self._loading_state("copying scene" if must_copy else "snapshotting")
        self.launch_player()
        QtCore.QCoreApplication.processEvents()
        if must_copy and not self._copy_scene_for_background():
            return
        t_export = time.time() - t_click
        self.trace("export-done", "%.1fs" % t_export)
        self._loading_state("snapshotting")
        t_snap = time.time()
        self._take_snapshot()
        try:
            self.cfg["bg_app_dir"], self.cfg["user_maya_dir"] = scene.background_prefs(refresh_background_prefs)
        except Exception as error:
            # Never fall back to sharing your prefs: stop instead.
            cmds.warning("bgcache: could not set up the background Maya's own preferences: %s" % error)
            self._abort("could not set up separate preferences")
            return
        self._progress("Launching background Maya...")
        self._loading_state("starting background Maya...")
        self.cfg["timing"] = {"export": round(t_export, 1), "snapshot": round(time.time() - t_snap, 1)}
        self.cfg["launch_t"] = time.time()
        common.write_json_atomic(common.paths(self.session)["config"], self.cfg)
        try:
            self._launch_worker(maya_cmd)
        except Exception as error:
            cmds.warning("bgcache: could not start the background Maya: %s" % error)
            self._abort("could not start the background Maya")
            return
        self.loading_since, self.loading_kind = time.time(), "start"
        self.trace("launched", "background Maya pid %s" % getattr(self.worker_proc, "pid", "?"))
        self.launch_player()             # already open; reopens it if it failed to start
        self._start_watching()

    def _session_config(self, width, height, chunk, quality, switch_off_tools, hide_background,
                        skip_in_background, skip_user_setup, light_background, trace):
        """config.json for a new session: what the hidden Maya and the player
        need to know (scene, range, cameras, sound, your viewport, GPU...)."""
        scene_file = cmds.file(query=True, sceneName=True)
        original_scene = scene_file
        display = scene.viewport_display()
        renderer = scene.viewport_renderer()
        gpu_on, gpu_reason = scene.gpu_choice()

        first = int(math.floor(cmds.playbackOptions(query=True, minTime=True)))
        last = int(math.ceil(cmds.playbackOptions(query=True, maxTime=True)))

        cfg = {
            "session": self.session, "scene": scene_file,
            "cameras": scene.list_cameras(), "audio": scene.find_audio(),
            "original_scene": original_scene,
            "display": display, "display_from": scene.DISPLAY_SOURCE,
            "start": first, "end": last, "fps": scene.scene_fps(),
            "width": int(width), "height": int(height), "chunk": int(chunk),
            "quality": int(quality),
            "switch_off_in_background": list(profile.get("switch_off_in_background") or ())
                                        if switch_off_tools else [],
            "drawings_root": profile.drawings_root(original_scene, scene.maya_project()),
            "profile": profile.source(),
            # GPU deformers in the background Maya: the profile's choice
            # (follow your Maya, always, or never)
            "background_gpu": gpu_on, "gpu_reason": gpu_reason,
            "releases_folder": profile.get("releases_folder") or "",
            "github_releases": profile.get("github_releases") or "",
            "before_playblast": profile.get("before_playblast") or "",
            "install_dir": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "hide": bool(hide_background),
            "skip_in_background": list(skip_in_background or ()),
            "skip_user_setup": bool(skip_user_setup),
            "light": bool(light_background),
            "trace": bool(trace),
            "plugins": scene.scene_plugins() if light_background else [],
            "viewport_renderer": renderer,
            "controller_pid": os.getpid(),
            "launched_at": time.time(), "rev": 1,
            "usual_startup": self._usual_startup(original_scene),
            "hotkeys": scene._maya_hotkeys(),
            "user": getpass.getuser(),
        }
        # the viewport renderer's plug-ins load in the background Maya too (light start)
        have = {p["name"] for p in cfg["plugins"]}
        cfg["plugins"] += [p for p in renderer.get("plugins") or [] if p["name"] not in have]
        return cfg

    def _copy_scene_for_background(self):
        """Never save over your file (published scenes are often read-only).
        Export a private copy of the current state for the background Maya.
        False (and Start stops) if it couldn't."""
        self._progress("Exporting scene copy...")
        scene_file = self._export_copy()
        if not scene_file:
            self._loading_state("error: could not copy your scene (see the Script Editor)")
            self._abort("could not export a scene copy")
            return False
        self.cfg["scene"] = scene_file
        return True

    def _take_snapshot(self):
        """Record every curve, visibility and unkeyed value as they are now:
        later edits are compared with this."""
        audio = self.cfg["audio"]
        if not self.cfg["cameras"]:
            cmds.warning("bgcache: no shot camera in the scene (persp/top/front/side are not offered)")
        print("bgcache: %d shot camera(s) offered in the player; sound: %s"
              % (len(self.cfg["cameras"]), audio["path"] if audio else "none"))
        self._progress("Snapshotting curves...")
        self.ignore = scene.default_camera_nodes()
        self._snapshot()
        self.vis_base = scene.visibility_states()
        self.static_vals = {}
        self._on_selection()
        self.trace("snapshot-done", "%d curves" % len(self.snap))

    def _start_watching(self):
        """The last step of Start: Maya callbacks, sync and the status timer."""
        self._install_callbacks()
        self._player_ts = time.time()
        self._cmd_ts = time.time()
        self._from_player = None
        self.sync_enabled = True
        self._on_time_changed()          # player opens on the frame you're on
        self.status_timer.start(1000)
        self.sync_timer.start(150)
        print("bgcache: started, session %s" % self.session)
        print("bgcache: logs for this session: %s" % common.paths(self.session)["logs"])

    def _loading_state(self, state):
        """What the player shows while bgcache starts (before the background
        Maya writes its own status)."""
        try:
            common.write_json_atomic(common.paths(self.session)["status"],
                                     {"state": state, "ts": time.time()})
        except (IOError, OSError) as error:
            scene._ignored(error)

    def _pre_pick_camera(self):
        """b13: cache the camera you're looking through (or the scene's only
        shot camera) without having to pick it in the player first."""
        names = [c["name"] for c in self.cfg.get("cameras") or []]
        pick = None
        try:
            panel = scene._active_model_panel()
            if panel:
                cam = cmds.modelPanel(panel, query=True, camera=True)
                if cam and cmds.nodeType(cam) == "camera":
                    cam = (cmds.listRelatives(cam, parent=True, fullPath=True) or [cam])[0]
                full = (cmds.ls(cam, long=True) or [None])[0]
                if full in names:
                    pick = full
        except Exception as error:
            scene._ignored(error)
        if pick is None and len(names) == 1:
            pick = names[0]
        if pick:
            common.write_json_atomic(common.paths(self.session)["cameras"], {"checked": [pick], "view": pick})

    # ---------------------------------------------------------------- feedback
    def _progress(self, text):
        """Show a step in the panel and Maya's progress bar, and let Maya
        repaint before the next (blocking) step."""
        self._set_label(text)
        try:
            bar = mel.eval("$bgcacheBar = $gMainProgressBar")
            if not self._progress_on:
                cmds.progressBar(bar, edit=True, beginProgress=True, isInterruptable=False,
                                 status="bgcache: " + text, maxValue=100)
                self._progress_on = True
            else:
                cmds.progressBar(bar, edit=True, status="bgcache: " + text)
        except Exception as error:
            scene._ignored(error)
        QtCore.QCoreApplication.processEvents()

    def _progress_end(self):
        if self._progress_on:
            try:
                cmds.progressBar(mel.eval("$bgcacheBar = $gMainProgressBar"), edit=True, endProgress=True)
            except Exception as error:
                scene._ignored(error)
            self._progress_on = False

    def _abort(self, why):
        self.session = None
        self._set_label("not started: %s" % why, error=True)

    def _startup_key(self, scene_file=None):
        scene_file = scene_file or (self.cfg or {}).get("original_scene") or ""
        return os.path.basename(scene_file) or "untitled"

    def _usual_startup(self, scene_file):
        return (common.load_prefs().get("startup") or {}).get(self._startup_key(scene_file))

    def _record_startup(self, seconds):
        prefs = common.load_prefs()
        times = prefs.setdefault("startup", {})
        key = self._startup_key()
        old = times.get(key)
        times[key] = round(seconds if old is None else (old + seconds) / 2.0, 1)  # smooth it
        common.save_prefs(prefs)

    # ---------------------------------------------------------------- launch
    def _env(self):
        env = os.environ.copy()
        pkg_parent = scene._pkg_parent()
        env["PYTHONPATH"] = os.pathsep.join(p for p in (pkg_parent, env.get("PYTHONPATH", "")) if p)
        env["BGCACHE_CONFIG"] = common.paths(self.session)["config"]
        env["BGCACHE_PKG"] = pkg_parent
        return env

    def _worker_env(self):
        """The background Maya's environment: yours, minus tools it doesn't
        need that can stop it loading (animBot pops up a dialog on startup)."""
        env = self._env()
        app_dir, version_dir = self.cfg.get("bg_app_dir"), self.cfg.get("user_maya_dir")
        if app_dir and version_dir:
            # Own preferences; your scripts, modules and plug-ins still found.
            env["MAYA_APP_DIR"] = app_dir
            maya_root = os.path.dirname(version_dir)
            extra = {
                "MAYA_SCRIPT_PATH": [os.path.join(version_dir, "scripts"), os.path.join(maya_root, "scripts")],
                "PYTHONPATH": [os.path.join(version_dir, "scripts"), os.path.join(maya_root, "scripts")],
                "MAYA_MODULE_PATH": [os.path.join(version_dir, "modules"), os.path.join(maya_root, "modules")],
                "MAYA_PLUG_IN_PATH": [os.path.join(version_dir, "plug-ins"), os.path.join(maya_root, "plug-ins")],
            }
            for var, dirs in extra.items():
                have = [x for x in env.get(var, "").split(os.pathsep) if x]
                env[var] = os.pathsep.join(have + [d for d in dirs if d not in have and os.path.isdir(d)])
            # No first-run, feedback or home-screen prompts in the hidden Maya.
            for var in ("MAYA_DISABLE_CIP", "MAYA_DISABLE_CER", "MAYA_DISABLE_ADP", "MAYA_NO_HOME"):
                env[var] = "1"
        skip = [w.lower() for w in self.cfg.get("skip_in_background") or ()]
        removed = []
        for var in scene.PATH_VARS:
            if var not in env or not skip:
                continue
            parts = env[var].split(os.pathsep)
            kept = [x for x in parts if not any(w in x.lower() for w in skip)]
            removed += [x for x in parts if x not in kept]
            env[var] = os.pathsep.join(kept)
        if removed:
            print("bgcache: left out of the background Maya: %s" % ", ".join(sorted(set(removed))))
        if "animbot" in skip:
            # do-nothing animBot first in line, whatever else tries to start it
            stubs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs")
            env["PYTHONPATH"] = os.pathsep.join(x for x in (stubs, env.get("PYTHONPATH", "")) if x)
        env["BGCACHE_BACKGROUND"] = "1"     # a userSetup can check this to skip things
        if self.cfg.get("skip_user_setup"):
            env["MAYA_SKIP_USERSETUP_PY"] = "1"
        return env

    def _launch_worker(self, maya_cmd=None):
        self._maya_cmd = maya_cmd           # the same command for a restart on the CPU
        base = list(maya_cmd) if maya_cmd else [scene.find_maya()]
        if not base[0]:
            raise RuntimeError("no Maya executable found; pass maya_cmd=[...] to show_ui()")
        print("bgcache: background Maya command: %s" % " ".join(base))
        if self.cfg.get("light"):
            base = base + ["-noAutoloadPlugins"]
        # bgcache's location goes in the command itself: studio launchers can
        # reset PYTHONPATH, so the environment alone isn't enough.
        cmd = base + ["-command", WORKER_COMMAND]
        log = open(common.paths(self.session)["log"], "a")
        self.worker_proc = subprocess.Popen(cmd, env=self._worker_env(), stdout=log,
                                            stderr=subprocess.STDOUT)

    def launch_player(self):
        """Player as its own mayapy process if possible (never stutters);
        otherwise as a window inside this Maya."""
        if not self.running:
            return
        if self.player_proc and self.player_proc.poll() is None:
            return
        if self.player_widget is not None and self.player_widget.isVisible():
            self.player_widget.raise_()
            return
        base = list(self.mayapy_cmd) if self.mayapy_cmd else [scene.find_mayapy()]
        if base[0]:
            try:
                cmd = base + ["-c", PLAYER_BOOT, self.session, str(os.getpid())]
                log = open(common.paths(self.session)["player_log"], "a")
                self.player_proc = subprocess.Popen(cmd, env=self._env(), stdout=log,
                                                    stderr=subprocess.STDOUT, **common.hidden_console())
                print("bgcache: player running in its own process (%s)" % base[0])
                return
            except Exception as error:
                cmds.warning("bgcache: mayapy player failed (%s), using in-Maya player" % error)
        from bgcache import player
        self.player_widget = player.Player(self.session)
        self.player_widget.show()
        print("bgcache: player running inside this Maya (no mayapy found)")

    def show_player(self):
        """The shelf button while bgcache runs: bring the player to the
        front, or open it again if you closed it (caching carried on)."""
        if not self.running:
            return
        if self.player_proc and self.player_proc.poll() is None:
            common.write_json_atomic(common.paths(self.session)["maya_time"], {
                "frame": int(cmds.currentTime(query=True)), "ts": time.time(), "raise": True})
            return
        if self.player_widget is not None:
            try:
                self.player_widget.show()
                self.player_widget.raise_()
                return
            except Exception as error:
                scene._ignored(error)
                self.player_widget = None
        self.launch_player()

    def restart(self):
        """Stop, then start again fresh (the player's bgcache > Restart)."""
        self.trace("restart")
        self.stop()
        cmds.evalDeferred(lambda: self.start(**_start_kwargs), lowestPriority=True)

    # ---------------------------------------------------------------- stop
    def stop(self):
        self.trace("stop")
        if not self.running:
            return
        common.post_message(self.session, {"op": "quit"})
        self._remove_callbacks()
        self.flush_timer.stop()
        self.status_timer.stop()
        self.sync_timer.stop()
        if self.player_proc and self.player_proc.poll() is None:
            self.player_proc.terminate()
        if self.player_widget is not None:
            try:
                self.player_widget.close()
            except Exception as error:
                scene._ignored(error)
            self.player_widget = None
        worker = self.worker_proc
        session = self.session

        def _ensure_dead_and_clean():
            # Still loading (it can't act on "quit" until the scene is open):
            # end it outright. A plain terminate makes Maya write a crash file.
            if worker and worker.poll() is None:
                worker.kill()
                try:
                    worker.wait(5)
                except Exception as error:
                    scene._ignored(error)
            # Then free the temp space: scene copies and cached frames.
            common.remove_session(session)
        QtCore.QTimer.singleShot(20000, _ensure_dead_and_clean)

        self.session = None
        self.snap = {}
        self.pending = set()
        self.pending_handles = []
        self.removed = []
        self.loading_since = None
        try:
            self.remove_image_plane()
        except Exception as error:
            scene._ignored(error)
        if self.save_cb is not None:
            try:
                om.MMessage.removeCallback(self.save_cb)
            except Exception as error:
                scene._ignored(error)
            self.save_cb = None
        self._set_label("stopped")
        self._update_buttons()
        print("bgcache: stopped")

    # ---------------------------------------------------------------- status
    def _set_label(self, text, error=False):
        if self.status_label and cmds.text(self.status_label, exists=True):
            cmds.text(self.status_label, edit=True, label=text,
                      backgroundColor=(0.55, 0.15, 0.15) if error else (0.27, 0.27, 0.27),
                      enableBackground=error)

    def _update_buttons(self):
        """Start only when stopped; everything else only while running."""
        for name, button in self.buttons.items():
            if cmds.button(button, exists=True):
                cmds.button(button, edit=True,
                            enable=(not self.running) if name == "start" else self.running)

    def toggle_pause(self, on=None):
        """Pause / resume re-rendering in the background Maya. Resuming starts
        at your current frame."""
        if not self.running:
            return
        if on is None:
            st = common.read_json(common.paths(self.session)["status"]) or {}
            on = not st.get("paused")
        common.post_message(self.session, {"op": "pause", "on": bool(on),
                                           "focus": int(round(cmds.currentTime(query=True)))})
        self.trace("pause" if on else "resume")
        self._show_paused(bool(on))
        print("bgcache: re-rendering %s" % ("paused" if on else "resumed"))

    def _show_paused(self, on):
        if getattr(self, "_paused_shown", None) == on:
            return
        self._paused_shown = on
        button = (getattr(self, "buttons", None) or {}).get("pause")
        try:
            if button and cmds.button(button, exists=True):
                cmds.button(button, edit=True, label="Resume re-rendering" if on else "Pause re-rendering")
        except Exception as error:
            scene._ignored(error)

    def _update_status(self):
        if not self.running:
            return
        if self.worker_proc and self.worker_proc.poll() is not None:
            self._set_label("ERROR: background Maya exited, see worker.log", error=True)
            if not self.exit_reported:      # tell the player too
                self.exit_reported = True
                code = self.worker_proc.poll()
                self.trace("worker-exited", "code %s" % code)
                print("bgcache: the background Maya stopped unexpectedly (exit code %s). "
                      "Logs: %s" % (code, common.paths(self.session)["logs"]))
                common.write_json_atomic(common.paths(self.session)["status"], {
                    "state": "error: background Maya exited (see worker.log)", "ts": time.time()})
            return
        st = common.read_json(common.paths(self.session)["status"]) or {}
        state = st.get("state", "starting")
        if self._gpu_rescue_needed(st):
            self.restart_on_cpu()
            return
        if self.loading_since is not None:
            if state in ("starting", "starting background Maya...", "opening scene", "reloading scene") or \
                    (self.loading_kind == "reload" and st.get("ts", 0) < self.loading_since):
                elapsed = time.time() - self.loading_since
                usual = self.cfg.get("usual_startup") if self.loading_kind == "start" else None
                what = "Launching background Maya" if state.startswith("starting") else "Loading scene"
                text = "%s... %s" % (what, scene._fmt(elapsed))
                if usual:
                    text += " (usually about %s)" % scene._fmt(usual)
                self._set_label(text)
                return
            if self.loading_kind == "start" and not state.startswith("error"):
                self._record_startup(time.time() - self.loading_since)
            self.loading_since = None
        self._show_paused(bool(st.get("paused")))
        cams = st.get("cameras") or {}
        dirty = sum(len(c.get("dirty") or []) for c in cams.values())
        text = "%s, %d camera(s), %d dirty frames" % (st.get("state", "starting"), len(cams), dirty)
        if state.startswith("error"):
            self._set_label("ERROR: %s" % state, error=True)
            return
        if st.get("error"):
            text += ", error (see worker.log)"
        if st.get("warning"):
            self._set_label("%s  |  %s" % (st["warning"], text), error=True)
            return
        self._set_label(text)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
_controller = None


def get():
    global _controller
    if _controller is None:
        _controller = Controller()
    return _controller


WORKSPACE = "bgcacheWorkspaceControl"
LAYOUT = "bgcacheLayout"
_start_kwargs = {}


_showing = False        # True only while show_ui (the shelf button) is opening the panel
_quit_job = None


_panel_scene_cbs = []     # scene callbacks that close the panel with the shot


def _panel_docked():
    """True when the panel is docked into Maya's layout (it's then part of
    your layout and stays: through scene changes and the next Maya start).
    A floating panel goes with the session."""
    try:
        return (cmds.workspaceControl(WORKSPACE, exists=True)
                and not cmds.workspaceControl(WORKSPACE, query=True, floating=True))
    except Exception as error:
        scene._ignored(error)
        return False


def _close_panel(force=False):
    """Close a floating panel and drop Maya's saved state for it, so it
    doesn't come back the next time Maya starts (the shelf button opens it).
    A docked panel stays where you put it, unless force."""
    if not force and _panel_docked():
        return
    try:
        if cmds.workspaceControl(WORKSPACE, exists=True):
            cmds.deleteUI(WORKSPACE)
    except Exception as error:
        scene._ignored(error)
    try:
        if cmds.workspaceControlState(WORKSPACE, exists=True):
            cmds.workspaceControlState(WORKSPACE, remove=True)
    except Exception as error:
        scene._ignored(error)


def _close_if_idle():
    """Close the panel unless bgcache is running or the shelf button is
    opening it right now."""
    if _showing:
        return
    try:
        if _controller is not None and _controller.running:
            return
    except Exception as error:
        scene._ignored(error)
    _close_panel()


def _close_panel_with_shot(*args):
    """Opening another file or File > New: the panel goes with the shot.
    Deferred, so nothing is deleted while Maya is switching scenes (bgcache
    itself is stopped by the controller's own callback first)."""
    try:
        cmds.evalDeferred(_close_panel, lowestPriority=True)
    except Exception as error:
        scene._ignored(error)


def _close_panel_after_open(*args):
    """After a scene has opened (or File > New): Maya can bring the panel back
    from a saved layout while it loads, after the close above ran. Close it
    again once the scene is in, and once more a moment later, unless bgcache
    is running."""
    try:
        cmds.evalDeferred(_close_if_idle, lowestPriority=True)
    except Exception as error:
        scene._ignored(error)
    try:
        QtCore.QTimer.singleShot(1500, _close_if_idle)
    except Exception as error:
        scene._ignored(error)


def _close_panel_on_exit(*args):
    _close_panel()            # now: Maya saves its layout as it quits (docked: kept)


def _forget_panel_on_quit():
    """Close the panel when its shot closes (another file opened, File > New)
    and when Maya quits, so it isn't saved in your layout and doesn't come back
    next time Maya starts. The shelf button opens it."""
    global _quit_job
    if _quit_job is None or not cmds.scriptJob(exists=_quit_job):
        _quit_job = cmds.scriptJob(event=["quitApplication", _close_panel])
    if _panel_scene_cbs:
        return
    for msg, fn in (("kBeforeOpen", _close_panel_with_shot), ("kBeforeNew", _close_panel_with_shot),
                    ("kAfterOpen", _close_panel_after_open), ("kAfterNew", _close_panel_after_open),
                    ("kMayaExiting", _close_panel_on_exit)):
        try:
            _panel_scene_cbs.append(om.MSceneMessage.addCallback(getattr(om.MSceneMessage, msg), fn))
        except Exception as error:
            scene._ignored(error)


def unload():
    """Called by the installer before an update or uninstall swaps the code in
    this Maya: stop, remove this copy's callbacks and the panel's contents
    (they point at this copy), so the new copy starts clean. No restart."""
    global _quit_job
    try:
        if _controller is not None and _controller.running:
            _controller.stop()
    except Exception as error:
        scene._ignored(error)
    try:
        if _quit_job is not None and cmds.scriptJob(exists=_quit_job):
            cmds.scriptJob(kill=_quit_job, force=True)
    except Exception as error:
        scene._ignored(error)
    _quit_job = None
    for cb in list(_panel_scene_cbs):
        try:
            om.MMessage.removeCallback(cb)
        except Exception as error:
            scene._ignored(error)
    del _panel_scene_cbs[:]
    try:
        if cmds.layout(LAYOUT, exists=True):
            cmds.deleteUI(LAYOUT)
    except Exception as error:
        scene._ignored(error)


ONE_OFF_OPTIONS = ("refresh_background_prefs",)   # apply to the next Start only


def _start_clicked():
    get().start(**_start_kwargs)
    for key in ONE_OFF_OPTIONS:
        _start_kwargs.pop(key, None)


def _build_ui():
    """Fill the dockable panel. Maya also runs this when it restores the panel
    from a saved layout (an older version's, or after a crash): then, and
    always in the background Maya, the panel is closed instead."""
    if os.environ.get("BGCACHE_BACKGROUND"):
        cmds.evalDeferred(lambda: _close_panel(force=True))   # never in the background Maya
        return
    if not _showing:
        # Maya restored the panel from a saved layout (versions before b12 had
        # one, docked or floating): everything is in the player now, so it goes.
        cmds.evalDeferred(lambda: _close_panel(force=True))
        return
    _forget_panel_on_quit()       # docked (kept in your layout) or opened by the shelf button
    c = get()
    # Look for OUR layout by name: Maya can put its own children in the panel,
    # so "does it have children?" isn't a safe test.
    if cmds.layout(LAYOUT, exists=True):
        parent = cmds.layout(LAYOUT, query=True, parent=True) or ""
        if WORKSPACE in parent.split("|"):
            return   # already built in this panel
        cmds.deleteUI(LAYOUT)   # left over somewhere else
    cmds.setParent(WORKSPACE)
    cmds.columnLayout(LAYOUT, adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
    cmds.separator(style="none", height=4)
    c.buttons = {
        "start": cmds.button(label="Start", command=lambda *_: _start_clicked()),
        "player": cmds.button(label="Reopen player", command=lambda *_: c.launch_player()),
        "pause": cmds.button(label="Pause re-rendering", command=lambda *_: c.toggle_pause(),
                             annotation="Edits keep going to the player, changed frames stay red "
                                        "until you resume (it resumes at your current frame)"),
        "stop": cmds.button(label="Stop", command=lambda *_: c.stop()),
    }
    cmds.text(label="Refresh, Push selected, Reload scene and\nRe-render are in the player (Pause too).",
              align="left", font="smallPlainLabelFont")
    c.status_label = cmds.text(label="running" if c.running else "stopped", align="left")
    c._update_buttons()
    c._update_status()


UNDO_HELP = ("To keep undo on every time Maya starts: Windows > Settings/Preferences > "
             "Preferences > Undo, set Undo to On, then click Save.")


def check_undo():
    """Undo watcher: warn when undo is off in your Maya (before 0.6.2 the
    background Maya could save "undo off" into your shared preferences), and
    offer to turn it back on. Never stops Start."""
    try:
        if cmds.undoInfo(query=True, state=True):
            return True
        answer = cmds.confirmDialog(
            title="bgcache: undo is off",
            message="Undo is turned off in this Maya, so Ctrl+Z won't work.\n\n"
                    "Turn it back on now?\n\n" + UNDO_HELP,
            button=["Turn undo on", "Leave it off"], defaultButton="Turn undo on",
            cancelButton="Leave it off", dismissString="Leave it off")
        if answer == "Turn undo on":
            cmds.undoInfo(state=True)
            print("bgcache: undo turned back on for this session. " + UNDO_HELP)
            return True
        cmds.warning("bgcache: undo is still off. " + UNDO_HELP)
    except Exception as error:
        scene._ignored(error)
    return False


def shelf_click(**start_kwargs):
    """The bgcache shelf button (b12: everything is in the player). Not
    running: Start (the player opens at once and shows the progress).
    Running: bring the player to the front, or reopen it if you closed it.
    start_kwargs are passed to Controller.start()."""
    global _start_kwargs
    if os.environ.get("BGCACHE_BACKGROUND"):
        return                               # never in the background Maya
    if start_kwargs:
        _start_kwargs = start_kwargs
    _close_panel(force=True)                 # an old version's panel, if any
    c = get()
    if c.running:
        c.show_player()
    else:
        _start_clicked()


def shelf_stop():
    """The shelf button's right-click menu: Stop."""
    c = get()
    if c.running:
        c.stop()


def shelf_reopen():
    """Right-click menu: Reopen player (or Start when stopped)."""
    shelf_click()


def shelf_restart():
    """Right-click menu: Restart."""
    c = get()
    if c.running:
        c.restart()
    else:
        _start_clicked()


def shelf_selftest():
    """Right-click menu: Self-test."""
    from bgcache import selftest
    selftest.run()


def show_ui(panel=False, **start_kwargs):
    """Old entry point (shelf buttons from before b12 call it): now the same
    as the shelf button. panel=True opens the old dockable control panel,
    for testing. start_kwargs are passed to Controller.start()."""
    global _start_kwargs, _showing
    if not panel:
        shelf_click(**start_kwargs)
        return
    _start_kwargs = start_kwargs
    if os.environ.get("BGCACHE_BACKGROUND"):
        return                               # never in the background Maya
    if cmds.window("bgcacheUI", exists=True):   # the old floating window
        cmds.deleteUI("bgcacheUI")
    _forget_panel_on_quit()
    _showing = True
    try:
        if cmds.workspaceControl(WORKSPACE, exists=True):
            # Already made this session (docked or floating): just show it.
            cmds.workspaceControl(WORKSPACE, edit=True, visible=True, restore=True, label=PANEL_LABEL)
            _build_ui()
            return
        cmds.workspaceControl(
            WORKSPACE, label=PANEL_LABEL, floating=True,
            initialWidth=320, initialHeight=220, minimumWidth=220, retain=False,
            # plain Python: Maya wraps it in python("...") itself when it saves
            # the layout (wrapping it here made it python(python(...)), which
            # failed on the next start and left an empty panel)
            uiScript="import bgcache.controller as bgc; bgc._build_ui()")
        _build_ui()
    finally:
        _showing = False
