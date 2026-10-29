"""Refresh and Reload scene: re-send what your Maya shows (viewport, image
planes, unkeyed values, GPU), or reopen the scene in the hidden Maya.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import math
import time

import maya.cmds as cmds

from bgcache import common, scene


class RefreshMixin(object):
    # ---------------------------------------------------------------- refresh / reload
    def refresh_display(self):
        """Send your viewport's display settings (shading, wireframe on
        shaded, show/hide filters...), display layer visibility and
        hidden/shown objects to the background Maya, then re-render. Use after
        changing any of them."""
        self.trace("refresh")
        if not self.running:
            return
        display = scene.viewport_display()
        old = self.cfg.get("display") or {}
        display_changed = sorted(f for f in display if f != "pluginObjects"
                                 and display.get(f) != old.get(f))
        if display:
            self.cfg["display"] = display     # Reload scene sends this one too
            self.cfg["display_from"] = scene.DISPLAY_SOURCE
        values = scene.display_layer_values()
        now = scene.visibility_states()
        changed = 0
        for node, visible in now.items():
            if self.vis_base.get(node) == visible:
                continue
            plug = node + ".visibility"
            try:
                if cmds.listConnections(plug, source=True, destination=False):
                    continue      # animated/driven visibility is synced as curves
            except Exception:  # node gone or unreadable: nothing to send for it
                continue
            values.append([plug, visible])
            changed += 1
        self.vis_base = now
        gpu_on, gpu_reason = scene.gpu_choice()          # GPU Override switched since Start
        self.cfg["background_gpu"], self.cfg["gpu_reason"] = gpu_on, gpu_reason
        msg = {"op": "statics", "values": values,
               "ranges": [[self.cfg["start"], self.cfg["end"]]],
               "image_planes": scene.image_planes(),      # also ones made after Start
               "gpu": gpu_on, "gpu_reason": gpu_reason}
        if display:
            msg["display"] = display
            msg["display_from"] = scene.DISPLAY_SOURCE
        common.post_message(self.session, msg)
        print("bgcache: refreshed display (%d layer settings, %d objects shown/hidden, "
              "viewport settings changed: %s)"
              % (len(values) - changed, changed, ", ".join(display_changed) or "none"))

    def reload_scene(self):
        """Re-export your current scene and reopen it in the background Maya
        without relaunching it. For new characters, props, references,
        constraints or a new frame range. Cameras and continuity are kept."""
        self.trace("reload")
        if not self.running:
            return
        self.flush()
        try:
            scene_file = cmds.file(query=True, sceneName=True)
            rev = self.cfg.get("rev", 1) + 1
            if not scene_file or cmds.file(query=True, modified=True):
                self._progress("Exporting scene copy...")
                scene_file = self._export_copy("scene_copy_%d.mb" % rev)
                if not scene_file:
                    self._set_label("reload failed: could not export", error=True)
                    self._tell_player("Reload scene failed: the scene couldn't be exported "
                                      "(see your Maya's Script Editor)")
                    return
            self._progress("Snapshotting curves...")
            self._remove_callbacks()
            self.ignore = scene.default_camera_nodes()
            self._snapshot()
            self.vis_base = scene.visibility_states()
            self.pending = set()
            first = int(math.floor(cmds.playbackOptions(query=True, minTime=True)))
            last = int(math.ceil(cmds.playbackOptions(query=True, maxTime=True)))
            display = scene.viewport_display()           # b17: read again, never reused
            if display:
                self.cfg["display"], self.cfg["display_from"] = display, scene.DISPLAY_SOURCE
            self.cfg["viewport_renderer"] = scene.viewport_renderer() or self.cfg.get("viewport_renderer") or {}
            self.cfg.update({"scene": scene_file, "start": first, "end": last,
                             "cameras": scene.list_cameras(), "audio": scene.find_audio(),
                             "rev": rev, "reloaded_at": time.time()})
            common.write_json_atomic(common.paths(self.session)["config"], self.cfg)
            common.post_message(self.session, {"op": "reload", "scene": scene_file,
                                               "start": first, "end": last,
                                               "display": self.cfg.get("display"),
                                               "display_from": self.cfg.get("display_from", ""),
                                               "viewport_renderer": self.cfg.get("viewport_renderer")})
            self._install_callbacks()
            self._prune_scene_copies(keep=2)
            self.loading_since, self.loading_kind = time.time(), "reload"
            print("bgcache: reloading %s in the background Maya" % scene_file)
        except Exception as error:
            self._set_label("reload failed: %s" % error, error=True)
            self._tell_player("Reload scene failed: %s (see your Maya's Script Editor)" % error)
            raise
        finally:
            self._progress_end()
