"""Watching your edits: Maya callbacks, the crash trace (trace.log), path
curves (b18) and the flush that sends changed curves to the hidden Maya.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

from bgcache import common, scene

try:
    from PySide6 import QtCore
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore


class EditsMixin(object):
    # ---------------------------------------------------------------- callbacks
    def _scene_changing(self, *args):
        """Opening a file, a new scene, or quitting Maya: stop bgcache BEFORE the
        old scene is torn down, so it never reacts to thousands of curves being
        deleted and created mid-load."""
        if not self.running:
            return
        self.trace("scene-change", "stopping before the scene changes")
        print("bgcache: the scene is changing, so bgcache is stopping. Click Start again in the new scene.")
        self.stop()

    def _install_callbacks(self):
        self.scene_cb_ids = []
        for msg in ("kBeforeOpen", "kBeforeNew", "kMayaExiting"):
            try:
                self.scene_cb_ids.append(om.MSceneMessage.addCallback(
                    getattr(om.MSceneMessage, msg), self._scene_changing))
            except Exception as error:
                om.MGlobal.displayWarning("bgcache: %s callback: %s" % (msg, error))
        self.callback_ids = self._watch_path_curves() + [
            oma.MAnimMessage.addAnimCurveEditedCallback(self._on_curves_edited),
            om.MDGMessage.addNodeAddedCallback(self._on_curve_added, "animCurve"),
            om.MDGMessage.addNodeRemovedCallback(self._on_curve_removed, "animCurve"),
        ]
        self.job_ids = [
            cmds.scriptJob(event=["Undo", self._on_undo_redo]),
            cmds.scriptJob(event=["Redo", self._on_undo_redo]),
            cmds.scriptJob(event=["timeChanged", self._on_time_changed]),
            cmds.scriptJob(conditionFalse=["playingBack", self._on_time_changed]),   # the frame you stop on
            cmds.scriptJob(event=["SelectionChanged", self._on_selection]),
            # New scene or opening another file ends the session.
            cmds.scriptJob(event=["deleteAll", lambda: cmds.evalDeferred(self.stop)]),
        ]

    # ---------------------------------------------------------------- crash trace
    def trace(self, event, detail=""):
        """One timestamped line per thing bgcache does in your Maya, flushed to
        disk at once: after a crash, the last line shows whether bgcache was
        busy and with what. ~/.bgcache/logs/<session>/trace.log"""
        if not self.session or not (self.cfg or {}).get("trace", True):
            return
        now = time.time()
        if event in scene.BUSY_EVENTS or event.startswith("ignored:"):
            # Frequent events: at most one line per second each, with a count,
            # so tracing stays cheap even during scrubbing or big edits.
            last = self._trace_last.setdefault(event, [0.0, 0])
            last[1] += 1
            if now - last[0] < 1.0:
                return
            detail = "%s (x%d)" % (detail, last[1]) if last[1] > 1 else detail
            last[0], last[1] = now, 0
        line = "%s.%03d %s %s\n" % (time.strftime("%H:%M:%S", time.localtime(now)),
                                     int(now * 1000) % 1000, event, detail)
        try:
            with open(common.paths(self.session)["trace"], "a") as handle:
                handle.write(line)
                handle.flush()
        except (IOError, OSError):
            pass

    def _on_selection(self):
        """Remember the values of the selected controls' unkeyed attributes, so
        when one gets its first key we can tell whether anything changed.
        Done once the selection settles (not on every click of a drag-select)."""
        if not self.running:
            return
        self.trace("selection")
        if not getattr(self, "_selection_queued", False):
            self._selection_queued = True
            QtCore.QTimer.singleShot(100, self._record_selection)

    def _record_selection(self):
        self._selection_queued = False
        if not self.running:
            return
        sel = om.MGlobal.getActiveSelectionList()
        for i in range(min(sel.length(), 100)):
            try:
                obj = sel.getDependNode(i)
                if obj.hasFn(om.MFn.kDagNode):
                    node = om.MFnDagNode(sel.getDagPath(i)).partialPathName()
                else:
                    node = om.MFnDependencyNode(obj).name()
                fn = om.MFnDependencyNode(obj)
                for attr in cmds.listAttr(node, keyable=True, scalar=True) or []:
                    try:
                        plug = fn.findPlug(attr, False)
                        if plug.isDestination:
                            continue      # keyed or driven: tracked as a curve
                        self.static_vals["%s.%s" % (node, attr)] = plug.asDouble()
                    except Exception:
                        continue          # non-numeric attribute: nothing to record
            except Exception as error:
                scene._ignored(error)

    def _dirty(self, name, old, new, first, last):
        """(frame ranges to re-render, send the curve?, reason if the whole shot)."""
        full = [[first, last]]
        plug = new["plug"]
        if scene.cycling(new):
            new["frames"] = scene.frame_values(name, first, last)
        if old is None:
            # First key on a previously unkeyed attribute.
            before = self.static_vals.pop(plug, None)
            if before is None:
                return full, True, "%s: new curve, its earlier value wasn't recorded" % plug
            values = new.get("frames") or scene.frame_values(name, first, last)
            ranges = scene.changed_frames([before] * len(values), values, first)
            return ranges, True, ("%s: new curve, value changed" % plug) if ranges == full else None
        if scene.cycling(new) or scene.cycling(old):
            if old.get("frames") and len(old["frames"]) == len(new["frames"]):
                ranges = scene.changed_frames(old["frames"], new["frames"], first)
                changed = ranges or old["keys"] != new["keys"] or scene.cycling(old) != scene.cycling(new)
                return ranges, bool(changed), ("%s: cycle/linear curve changed everywhere" % plug) if ranges == full else None
            return full, True, "%s: cycle/linear curve, earlier frames not recorded" % plug
        ranges = scene.dirty_ranges(old, new, first, last)
        why = ("%s: edit reaches the whole shot (e.g. its only key, or first/last key)" % plug) if ranges == full else None
        return ranges, bool(ranges), why

    def _remove_callbacks(self):
        # The scene-change callbacks may be the ones running right now: take
        # them out a moment later, not from inside themselves.
        scene_ids, self.scene_cb_ids = getattr(self, "scene_cb_ids", []), []

        def _remove_scene_cbs():
            for cb in scene_ids:
                try:
                    om.MMessage.removeCallback(cb)
                except Exception as error:
                    scene._ignored(error)
        if scene_ids:
            cmds.evalDeferred(_remove_scene_cbs)
        for cb in self.callback_ids:
            try:
                om.MMessage.removeCallback(cb)
            except Exception as error:
                scene._ignored(error)
        for job in self.job_ids:
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except Exception as error:
                scene._ignored(error)
        self.callback_ids, self.job_ids = [], []

    def _schedule(self):
        self._last_edit_t = time.time()      # for the "edit synced" timing in worker.log
        self._held_since = None
        self.flush_timer.start(scene.DEBOUNCE_MS)  # restarts: waits for edits to settle

    def _on_curves_edited(self, curves, client_data=None):
        if not self.running:
            return
        self.trace("curve-edited", len(curves))
        try:
            for i in range(len(curves)):
                self.pending.add(om.MFnDependencyNode(curves[i]).name())
            self._schedule()
        except Exception as error:
            scene._ignored(error)

    # ---------------------------------------------------------------- path curves (b18)
    def _watch_path_curves(self):
        """Curves you edit by hand that drive something (a motion path, spline
        IK, a wire...) have no keys, so key edits never showed their changes
        in the cache. Watch just those (usually a handful): a change to their
        CVs is sent like a key edit. Curves built from other nodes, or rig
        controls that drive nothing, aren't watched."""
        self.pending_shapes = set()
        ids = []
        found = scene.path_curves()
        for shape in found:
            try:
                sel = om.MSelectionList()
                sel.add(shape)
                ids.append(om.MNodeMessage.addAttributeChangedCallback(
                    sel.getDependNode(0), self._on_shape_changed, shape))
            except Exception as error:
                scene._ignored(error)
        if found:
            self.trace("path-curves", "%d watched" % len(found))
        return ids

    def _on_shape_changed(self, msg, plug, other, shape=None):
        if not self.running or not (msg & om.MNodeMessage.kAttributeSet):
            return
        try:
            name = plug.partialName(includeNodeName=False)
        except Exception:  # plug already gone: treated as a shape change
            name = ""
        # CV moves (cp/controlPoints...), and b20: rebuilt or knot-inserted
        # curves (cc/cached, cr/create), which change the CV count
        if not name.startswith(("cp", "controlPoints", "cv", "xv", "yv", "zv", "cc", "cached", "cr", "create")):
            return
        self.pending_shapes.add(shape)
        self._schedule()

    def _send_path_curves(self):
        shapes, self.pending_shapes = getattr(self, "pending_shapes", set()), set()
        out = []
        for shape in sorted(shapes):
            try:
                # b20: the whole curve (degree, knots, CVs), so added or removed
                # CVs reach the background Maya too
                out.append(scene.curve_definition(shape))
            except Exception as error:
                scene._ignored(error)
        if not out:
            return
        names = ", ".join(s["shape"].split("|")[-1] for s in out)
        print("bgcache: path curve edited (%s): re-rendering the shot" % names)
        common.post_message(self.session, {
            "op": "curve_shapes", "shapes": out,
            "ranges": [[self.cfg["start"], self.cfg["end"]]],
            "why": ["path curve edited: %s" % names],
            "focus": int(round(cmds.currentTime(query=True)))})

    def _on_curve_added(self, node, client_data=None):
        if not self.running:
            return
        self.trace("curve-added")
        try:
            self.pending_handles.append(om.MObjectHandle(node))
            self._schedule()
        except Exception as error:
            scene._ignored(error)

    def _on_curve_removed(self, node, client_data=None):
        if not self.running:
            return
        self.trace("curve-removed")
        try:
            old = self.snap.pop(om.MFnDependencyNode(node).name(), None)
            if old and old.get("plug"):
                self.removed.append((old["curve"], old["plug"]))
                self._schedule()
        except Exception as error:
            scene._ignored(error)

    def _on_undo_redo(self):
        self.trace("undo/redo")
        # Re-diff recently edited curves; unchanged ones are ignored by the diff.
        self.pending.update(self.recent)
        self._schedule()

    # ---------------------------------------------------------------- flush
    def flush(self):
        """Send what changed since the last flush: path curve shapes, deleted
        curves, then the edited curves with the frames they dirty."""
        if self._still_dragging():
            return
        self.trace("flush", "%d curves pending" % len(self.pending))
        if not self.running:
            return
        if getattr(self, "pending_shapes", None):
            self._send_path_curves()
        first, last = self.cfg["start"], self.cfg["end"]
        names, self.pending = self.pending, set()
        handles, self.pending_handles = self.pending_handles, []
        removed, self.removed = self.removed, []
        for handle in handles:
            if handle.isValid():
                names.add(om.MFnDependencyNode(handle.object()).name())
        reasons = []        # why the whole shot re-renders (deleted and edited curves add to it)
        self._send_deleted_curves(removed, first, last, reasons)
        curves, ranges = self._read_changed_curves(names, first, last, reasons)
        if reasons:
            print("bgcache: whole shot re-rendering because: %s" % "; ".join(reasons))
        if curves:
            common.post_message(self.session, {
                "op": "curves", "curves": curves, "why": reasons,
                "ranges": common.merge_ranges(ranges),
                "focus": int(round(cmds.currentTime(query=True))),  # render here first
                "edited": getattr(self, "_last_edit_t", None), "ts": time.time()})

    def _still_dragging(self):
        """True while a mouse button is down (dragging keys): flush again
        soon and send once you let go (one edit, not one per step)."""
        if self.running and scene._mouse_held():
            now = time.time()
            if getattr(self, "_held_since", None) is None:
                self._held_since = now
            if now - self._held_since < scene.HELD_MAX_S:
                self.flush_timer.start(scene.HELD_POLL_MS)
                return True
        if getattr(self, "_held_since", None) is not None:
            self._last_edit_t = time.time()      # you let go just now
            self._held_since = None
        return False

    def _send_deleted_curves(self, removed, first, last, reasons):
        """Curves deleted since the last flush: one delete_curves message.
        The whole shot re-renders when a value changed with the curve gone."""
        gone_curves, gone_ranges = [], []
        for curve, plug in removed:
            if not cmds.objExists(plug):
                continue
            try:
                value = cmds.getAttr(plug)
                now = scene.plug_value(plug)
            except Exception as error:
                scene._ignored(error)
                continue
            old = self.snap.pop(curve, None)
            held = scene.constant_value(old)
            gone_curves.append({"curve": curve, "plug": plug, "value": value})
            if held is None or abs(held - now) > scene.TOL:
                gone_ranges = [[first, last]]
                if len(reasons) < 5:
                    reasons.append("%s: curve deleted, value changed" % plug)
        if gone_curves:
            # One message for all of them: unloading a reference or deleting a
            # character can remove thousands of curves at once.
            common.post_message(self.session, {
                "op": "delete_curves", "curves": gone_curves, "ranges": gone_ranges,
                "why": reasons + (["...and %d more" % (len(gone_curves) - 5)]
                                  if gone_ranges and len(gone_curves) > 5 else [])})

    def _read_changed_curves(self, names, first, last, reasons):
        """Re-read the edited curves and compare them with the snapshot:
        (curves to send, frame ranges they dirty)."""
        curves, ranges = [], []
        for name in names:
            try:
                if not cmds.objExists(name) or cmds.nodeType(name) not in scene.TIME_CURVE_TYPES:
                    continue
                plug = scene.curve_plug(name)
                if not plug or self._ignored(plug):
                    continue
                new = scene.read_curve(name)
                new["plug"] = plug
                found, send, why = self._dirty(name, self.snap.get(name), new, first, last)
                self.snap[name] = new
                self.recent.append(name)
                if why:
                    reasons.append(why)
                if not send:
                    continue
                payload = dict(new)
                payload.pop("frames", None)
                payload["samples"] = scene.sample_curve(name, new["keys"])
                curves.append(payload)
                ranges.extend(found)
            except Exception as error:
                om.MGlobal.displayWarning("bgcache: %s: %s" % (name, error))
        return curves, ranges
