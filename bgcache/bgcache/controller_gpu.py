"""GPU rescue: when the hidden Maya's GPU deformers fail and it stops
answering, restart it on the CPU (once per session) and tell the player.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import glob
import math
import os
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om

from bgcache import common, scene


class GpuRescueMixin(object):
    # ---------------------------------------------------------------- GPU rescue
    GPU_STUCK_S = 10.0      # GPU errors in worker.log and no heartbeat for this long (b18: was 20)

    def _gpu_rescue_needed(self, st):
        """GPU deformer errors in the background Maya's log and it has stopped
        answering (a playblast stuck on the broken GPU never returns, so it
        can't switch to the CPU by itself)."""
        if getattr(self, "gpu_rescued", False) or self.loading_since is not None \
                or not (self.cfg or {}).get("background_gpu"):
            return False
        now = time.time()
        if now - getattr(self, "_gpu_log_t", 0.0) >= 2.0:
            self._gpu_log_t = now
            text, self._gpu_log_pos = common.read_new(common.paths(self.session)["log"],
                                                      getattr(self, "_gpu_log_pos", 0))
            if text and common.GPU_TROUBLE_RE.search(text):
                self._gpu_trouble_t = now
        if getattr(self, "_gpu_trouble_t", None) is None:
            return False
        return now - float(st.get("ts") or 0) > self.GPU_STUCK_S

    def restart_on_cpu(self):
        """Restart the background Maya with GPU deformers off, on a fresh copy
        of your scene (it has your latest edits). The player keeps its
        cameras and re-renders them."""
        self.gpu_rescued = True
        self.trace("gpu-rescue")
        print("bgcache: GPU deformers failed in the background Maya and it stopped "
              "answering: restarting it on the CPU")
        self._tell_player("GPU deformers failed in the background Maya: restarting it on the "
                          "CPU (slower). Your edits are kept.")
        old = self.worker_proc
        try:
            if old and old.poll() is None:
                old.kill()
                old.wait(10)
        except Exception as error:
            scene._ignored(error)
        try:
            self.flush()
            common.take_messages(self.session)    # already in the new scene copy
            rev = self.cfg.get("rev", 1) + 1
            self._progress("Exporting scene copy...")
            scene_file = self._export_copy("scene_copy_%d.mb" % rev)
            if not scene_file:
                raise RuntimeError("could not export a scene copy")
            self._remove_callbacks()
            self.ignore = scene.default_camera_nodes()
            self._snapshot()
            self.vis_base = scene.visibility_states()
            self.pending = set()
            self.cfg.update({"scene": scene_file, "rev": rev, "background_gpu": False,
                             "gpu_reason": "off: the GPU deformers failed, restarted on the CPU",
                             "launch_t": time.time(), "gpu_rescued": True})
            common.write_json_atomic(common.paths(self.session)["status"], {
                "state": "starting", "ts": time.time(),
                "warning": "GPU deformers failed: restarting the background Maya on the CPU"})
            common.write_json_atomic(common.paths(self.session)["config"], self.cfg)
            self._progress("Restarting the background Maya on the CPU...")
            self._launch_worker(getattr(self, "_maya_cmd", None))
            self._install_callbacks()
            self.loading_since, self.loading_kind = time.time(), "restart"
        except Exception as error:
            self._set_label("GPU failed and the restart on the CPU failed: %s. Press Stop, "
                            "then Start." % error, error=True)
            self._tell_player("GPU failed and restarting on the CPU failed: press Stop, then Start.")
        finally:
            self._progress_end()

    def _tell_player(self, note):
        """A message for the player to show over the picture (it doesn't
        move the player's frame)."""
        try:
            common.write_json_atomic(common.paths(self.session)["maya_time"], {
                "frame": int(cmds.currentTime(query=True)), "ts": time.time(), "note": note})
        except Exception as error:
            print("bgcache: could not tell the player: %s" % error)

    def _prune_scene_copies(self, keep=2):
        """Each Reload scene exports a new copy; keep only the newest few (the
        background Maya has already read the older ones)."""
        copies = sorted(glob.glob(os.path.join(self.session, "scene_copy*.mb")), key=os.path.getmtime)
        for old in copies[:-keep]:
            try:
                os.remove(old)
            except OSError as error:
                scene._ignored(error)

    def _export_copy(self, name="scene_copy.mb"):
        """Export the current scene state to the session folder. Your scene file,
        its name and its modified state are left untouched."""
        self.trace("export-start", name)
        path = os.path.join(self.session, name)
        print("bgcache: exporting a copy of the current scene (this can take a moment)...")
        try:
            cmds.file(path, exportAll=True, preserveReferences=True,
                      type="mayaBinary", force=True)
        except Exception as error:
            cmds.warning("bgcache: could not export a scene copy: %s" % error)
            return None
        return path

    def _ignored(self, plug):
        """True for curves animating persp/top/front/side."""
        found = cmds.ls(plug.split(".")[0], long=True) or []
        return bool(found) and found[0] in self.ignore

    def _snapshot(self):
        self.snap = {}
        first = int(math.floor(cmds.playbackOptions(query=True, minTime=True)))
        last = int(math.ceil(cmds.playbackOptions(query=True, maxTime=True)))
        curves = cmds.ls(type=scene.TIME_CURVE_TYPES) or []
        print("bgcache: snapshotting %d anim curves..." % len(curves))
        for name in curves:
            try:
                plug = scene.curve_plug(name)
                if not plug or self._ignored(plug):
                    continue
                data = scene.read_curve(name)
                data["plug"] = plug
                if scene.cycling(data):
                    data["frames"] = scene.frame_values(name, first, last)
                self.snap[name] = data
            except Exception as error:
                om.MGlobal.displayWarning("bgcache: could not read %s: %s" % (name, error))
        print("bgcache: %d live curves tracked" % len(self.snap))
