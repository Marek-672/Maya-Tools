"""Refresh and Reload scene: re-send what your Maya shows (viewport, image
planes, unkeyed values, GPU), or reopen the scene in the hidden Maya.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import math
import time

import maya.cmds as cmds

from bgcache import common, refreshing, scene


class RefreshMixin(object):
    # ---------------------------------------------------------------- refresh / reload
    def refresh_display(self):
        """Refresh (b21: the one button). Sends what's different in your
        viewport settings, display layers, shown and hidden objects, unkeyed
        values on what you've selected (what Push selected did), image planes
        and the GPU setting, and re-renders; says what it sent, or that there
        was nothing. Then, if the scene itself has changed (references,
        constraints, objects), the player asks whether to reload it."""
        self.trace("refresh")
        if not self.running:
            return
        display = scene.viewport_display()
        old = self.cfg.get("display") or {}
        display_changed = sorted(f for f in display if f != "pluginObjects"
                                 and display.get(f) != old.get(f))
        if display and display.get("pluginObjects") != old.get("pluginObjects"):
            display_changed.append("pluginObjects")
        if display:
            self.cfg["display"] = display     # Reload scene sends this one too
            self.cfg["display_from"] = scene.DISPLAY_SOURCE
        sent = getattr(self, "_refresh_sent", None) or {}
        layers = [v for v in scene.display_layer_values() if sent.get(v[0]) != v[1]]
        values = list(layers)
        now = scene.visibility_states()
        changed = 0
        for node, visible in now.items():
            if node not in self.vis_base or self.vis_base[node] == visible:
                continue          # the same, or new since Start (that's for Reload scene, not shown / hidden)
            plug = node + ".visibility"
            try:
                if cmds.listConnections(plug, source=True, destination=False):
                    continue      # animated/driven visibility is synced as curves
            except Exception:  # node gone or unreadable: nothing to send for it
                continue
            values.append([plug, visible])
            changed += 1
        self.vis_base = now
        unkeyed, controls = self.unkeyed_changes()                 # b21: what Push selected did
        moved = [v for v in self.free_plane_values() if sent.get(v[0]) != v[1]]         # b17: free image planes
        values += unkeyed + moved
        image_planes = scene.image_planes()
        planes_changed = image_planes != sent.get("_image_planes")
        gpu_on, gpu_reason = scene.gpu_choice()          # GPU Override switched since Start
        gpu_changed = gpu_on != self.cfg.get("background_gpu")
        self.cfg["background_gpu"], self.cfg["gpu_reason"] = gpu_on, gpu_reason
        for plug, value in layers + moved:
            sent[plug] = value
        sent["_image_planes"] = image_planes
        self._refresh_sent = sent
        planes = (len(image_planes) if planes_changed else 0) + len(set(v[0].rsplit("|", 1)[0] for v in moved))
        said = refreshing.summary(display_changed, len(layers), changed, len(unkeyed), controls, planes, gpu_changed)
        if said:
            msg = {"op": "statics", "values": values,
                   "ranges": [[self.cfg["start"], self.cfg["end"]]],
                   "image_planes": image_planes,      # also ones made after Start
                   "gpu": gpu_on, "gpu_reason": gpu_reason}
            if display:
                msg["display"] = display
                msg["display_from"] = scene.DISPLAY_SOURCE
            common.post_message(self.session, msg)
        structure = self.changed_structure()
        if structure:
            self._write_refresh_note(ask={"changes": structure, "seconds": int(getattr(self, "_reload_took", 0) or 0),
                                          "sent": bool(said)})
        self._tell_player(said or (refreshing.NOTHING if not structure else "Refresh: the scene has changed"))
        print("bgcache: %s%s" % (said or "refresh: nothing to update",
                                 "; scene changed (%s): the player asks about reloading" % ", ".join(structure)
                                 if structure else ""))

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
            shot = scene.shot_range(self.cfg.get("original_scene"))      # b8: the whole shot
            first, last = shot["start"], shot["end"]
            self.cfg.update({"cut": shot["cut"], "range_from": shot["from"], "maya_range": shot["maya"]})
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
