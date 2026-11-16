"""Cameras you move without keys (0.9.0b12): a follow camera you tumble
through, a camera with no animation. Key edits never showed these moves in
the cache (you had to select the camera and Push selected), so the cameras
being cached are watched: when one stops moving, its unkeyed values are sent
and the shot re-renders.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om

from bgcache import common, scene

# Lens and film values of the camera's shape that change the picture (the
# cache ignores 2D pan/zoom and overscan, so those aren't sent).
SHAPE_ATTRS = ("focalLength", "horizontalFilmAperture", "verticalFilmAperture", "horizontalFilmOffset",
               "verticalFilmOffset", "lensSqueezeRatio", "filmFit", "cameraScale", "orthographic",
               "orthographicWidth", "nearClipPlane", "farClipPlane")
TRANSFORM_ATTRS = ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ",
                   "scaleX", "scaleY", "scaleZ", "rotateOrder")


# b17: free image planes (cards in the scene, not on a camera) are watched the same way
FREE_PLANE_ATTRS = ("width", "height", "alphaGain", "visibility")


def free_planes():
    """Transforms of the image planes that aren't attached to a camera."""
    out = []
    try:
        shapes = cmds.ls(type="imagePlane", long=True) or []
    except Exception as error:
        scene._ignored(error)
        return out
    for shape in shapes:
        try:
            if [c for c in (cmds.imagePlane(shape, query=True, camera=True) or []) if c]:     # a free plane answers [""]
                continue
            parent = cmds.listRelatives(shape, parent=True, fullPath=True) or []
            if parent and parent[0] not in out:
                out.append(parent[0])
        except Exception as error:
            scene._ignored(error)
    return out


class CameraMixin(object):
    CAMERA_SETTLE_S = 0.4          # how long a camera rests before its move is sent

    def _camera_nodes(self, camera):
        """[(node, attribute names)] for a camera: its transform and its shape."""
        out = []
        if not cmds.objExists(camera):
            return out
        out.append((camera, TRANSFORM_ATTRS))
        for shape in cmds.listRelatives(camera, shapes=True, type="camera", fullPath=True) or []:
            out.append((shape, SHAPE_ATTRS))
        for shape in cmds.listRelatives(camera, shapes=True, type="imagePlane", fullPath=True) or []:
            out.append((shape, FREE_PLANE_ATTRS))          # b17: a free image plane
        return out

    def _camera_values(self, camera):
        """{plug: value} of the camera's values that nothing drives (no keys,
        no constraint): what a key edit would never send."""
        values = {}
        for node, attrs in self._camera_nodes(camera):
            for attr in attrs:
                plug = "%s.%s" % (node, attr)
                try:
                    if cmds.listConnections(plug, source=True, destination=False):
                        continue          # keyed or driven: curves and the rig carry it
                    values[plug] = cmds.getAttr(plug)
                except Exception as error:
                    scene._ignored(error)
        return values

    def _watch_cameras(self, cameras):
        """Watch the cameras the player caches (cameras.json's checked list).
        Called whenever that file changes; does nothing if the list is the same."""
        self._checked_cameras = [c for c in cameras or [] if c]
        cameras = self._checked_cameras + [p for p in free_planes() if p not in self._checked_cameras]
        if cameras == getattr(self, "_watched_cameras", None):
            return
        self._unwatch_cameras()
        self._watched_cameras = list(cameras)
        self._camera_sent, self._camera_moved = {}, {}
        for camera in cameras:
            try:
                for node, _attrs in self._camera_nodes(camera):
                    sel = om.MSelectionList()
                    sel.add(node)
                    self.camera_cb_ids.append(om.MNodeMessage.addAttributeChangedCallback(
                        sel.getDependNode(0), self._on_camera_changed, camera))
                self._camera_sent[camera] = self._camera_values(camera)
            except Exception as error:
                scene._ignored(error)
        if cameras:
            self.trace("cameras-watched", len(cameras))

    def free_plane_values(self):
        """b17, for Refresh: [[plug, value]] of every free image plane's place
        and size that nothing drives; and planes made since Start get watched."""
        values = []
        for plane in free_planes():
            values += [[plug, value] for plug, value in self._camera_values(plane).items()]
        if getattr(self, "_watched_cameras", None) is not None:
            self._watch_cameras(getattr(self, "_checked_cameras", []))
        return values

    def _unwatch_cameras(self):
        for cb in getattr(self, "camera_cb_ids", []):
            try:
                om.MMessage.removeCallback(cb)
            except Exception as error:
                scene._ignored(error)
        self.camera_cb_ids = []
        self._watched_cameras = None

    def _on_camera_changed(self, msg, plug, other, camera=None):
        """A value on a watched camera was set (you tumbled, typed a focal
        length...): note the time; it's sent once the camera rests."""
        if self.running and (msg & om.MNodeMessage.kAttributeSet):
            self._camera_moved[camera] = time.time()

    def _send_moved_cameras(self):
        """From the 150 ms poll: send the cameras that have come to rest."""
        moved = getattr(self, "_camera_moved", None)
        if not moved or not self.running:
            return
        now = time.time()
        if any(now - t < self.CAMERA_SETTLE_S for t in moved.values()) or scene._mouse_held():
            return
        cameras, self._camera_moved = list(moved), {}
        changed = []
        for camera in cameras:
            values = self._camera_values(camera)
            sent = self._camera_sent.get(camera) or {}
            changed += [[plug, value] for plug, value in values.items() if sent.get(plug) != value]
            self._camera_sent[camera] = values
        if not changed:
            return                # set to the same values, or only driven values changed
        self.trace("camera-moved", "%d values" % len(changed))
        common.post_message(self.session, {"op": "statics", "values": changed,
                                           "ranges": [[self.cfg["start"], self.cfg["end"]]]})
        print("bgcache: camera or reference plane moved without keys: sent %d value(s), re-rendering" % len(changed))
