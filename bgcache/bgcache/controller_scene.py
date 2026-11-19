"""One Refresh (0.9.0b21), your Maya's side: noticing that the scene itself
has changed (Maya says when references come and go, something is imported or
a constraint is made), and comparing the scene's structure with what the
background Maya was given, when you press Refresh. Words: refreshing.py."""
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om

from bgcache import common, refreshing, scene


def structure():
    """What the background Maya's copy would have to be reloaded for:
    references (file, loaded), and counts of constraints, deformers and
    objects. A few list commands: a fraction of a second on a heavy scene."""
    refs = {}
    for ref in cmds.ls(type="reference") or []:
        if "sharedReferenceNode" in ref or ref.startswith("_UNKNOWN_REF"):
            continue
        try:
            refs[ref] = [cmds.referenceQuery(ref, filename=True, withoutCopyNumber=True),
                         bool(cmds.referenceQuery(ref, isLoaded=True))]
        except Exception:  # a reference node with no file (a leftover): not counted
            continue
    count = lambda **k: len(cmds.ls(**k) or [])
    return {"references": refs, "constraints": count(type="constraint"),
            "deformers": count(type="geometryFilter"), "objects": count(dag=True)}


class SceneWatchMixin(object):
    def _watch_scene(self):
        """Start and Reload scene: what the background Maya has now, and
        listen for what Maya reports from here on."""
        self._unwatch_scene()
        self._scene_events = []
        try:
            self._structure = structure()
        except Exception as error:
            scene._ignored(error)
            self._structure = None
        msg = om.MSceneMessage
        for name, kind in (("kAfterCreateReference", "reference-added"), ("kAfterRemoveReference", "reference-removed"),
                           ("kAfterLoadReference", "reference-loaded"), ("kAfterUnloadReference", "reference-unloaded"),
                           ("kAfterImport", "imported")):
            try:
                self.structure_cb_ids.append(msg.addCallback(getattr(msg, name), self._on_scene_event, kind))
            except Exception as error:
                scene._ignored(error)
        try:
            self.structure_cb_ids.append(om.MDGMessage.addNodeAddedCallback(self._on_constraint, "constraint"))
        except Exception as error:
            scene._ignored(error)
        self._refresh_baseline()
        self._write_refresh_note()

    def _refresh_baseline(self):
        """What the background Maya has just been given (Start, Reload scene):
        the first Refresh then only sends what you changed since."""
        sent = {}
        try:
            for plug, value in scene.display_layer_values() + self.free_plane_values():
                sent[plug] = value
            sent["_image_planes"] = scene.image_planes()
        except Exception as error:
            scene._ignored(error)
        self._refresh_sent = sent

    def _unwatch_scene(self):
        for cb in getattr(self, "structure_cb_ids", []):
            try:
                om.MMessage.removeCallback(cb)
            except Exception as error:
                scene._ignored(error)
        self.structure_cb_ids = []

    def _on_scene_event(self, kind, *args):
        if isinstance(kind, str) is False and args:      # some Maya versions pass (clientData) last
            kind = args[-1]
        self._scene_changed(kind)

    def _on_constraint(self, node, *args):
        self._scene_changed("constraint")

    def _scene_changed(self, kind):
        if not self.running or self.loading_since is not None:
            return
        events = getattr(self, "_scene_events", [])
        if kind not in events[-1:]:
            events.append(kind)
            self._scene_events = events[-20:]
            self.trace("scene-changed", kind)
            self._write_refresh_note()

    def _write_refresh_note(self, ask=None):
        """For the player: the orange words next to Refresh, and the question
        (changes, seconds a reload took) when a Refresh found one is needed."""
        try:
            common.write_json_atomic(common.paths(self.session)["refresh_note"], {
                "note": refreshing.note(getattr(self, "_scene_events", [])), "ask": ask, "ts": time.time()})
        except Exception as error:
            print("bgcache: could not tell the player the scene changed: %s" % error)

    def changed_structure(self):
        """Refresh: what the scene has that the background Maya's copy doesn't ([] if nothing)."""
        try:
            return refreshing.structure_changes(getattr(self, "_structure", None), structure())
        except Exception as error:
            scene._ignored(error)
            return []

    def unkeyed_changes(self):
        """Refresh: [[plug, value]] of the unkeyed values that changed on what
        you've selected since Start (their values were noted as you selected
        them), and how many nodes they're on. This is what Push selected did."""
        changed, nodes = [], set()
        for plug, before in list(self.static_vals.items()):
            try:
                if cmds.listConnections(plug, source=True, destination=False):
                    continue
                now = cmds.getAttr(plug)
            except Exception:  # the node is gone or the value isn't a number any more
                continue
            if isinstance(now, bool):
                now = float(now)
            if isinstance(now, (int, float)) and abs(float(now) - float(before)) > 1e-9:
                changed.append([plug, now])
                nodes.add(plug.rsplit(".", 1)[0])
                self.static_vals[plug] = float(now)
        return changed, len(nodes)
