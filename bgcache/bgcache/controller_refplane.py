"""The player's reference movie as an image plane in your Maya
(bgcache_reference), and the offer to remove it before you save.

Part of the Controller (bgcache/controller.py); see DEVELOPER.md."""
import maya.cmds as cmds
import maya.api.OpenMaya as om

from bgcache import common, scene


class RefPlaneMixin(object):
    # ---------------------------------------------------------------- reference image plane
    def _find_plane(self):
        for tr in cmds.ls(scene.REF_PLANE + "*", type="transform", long=True) or []:
            shapes = cmds.listRelatives(tr, shapes=True, type="imagePlane", fullPath=True)
            if shapes:
                return tr, shapes[0]
        return None, None

    def show_image_plane(self, camera, path, offset, mode):
        """One reference image plane on the shot camera, filling its view.
        mode "front": just past the near clip, covers the scene.
        mode "behind": just inside the far clip, the scene draws over it.
        It's the same size on screen either way (camera image planes always
        fill the view); only what it covers changes."""
        self.trace("image-plane", mode)
        if not cmds.objExists(camera):
            raise RuntimeError("camera %s not found" % camera)
        cam = (cmds.listRelatives(camera, shapes=True, type="camera", fullPath=True) or [camera])[0]
        tr, shape = self._find_plane()
        if shape:
            attached = cmds.imagePlane(shape, query=True, camera=True) or []
            names = set(cmds.ls(attached, long=True) or [])
            names |= set(cmds.listRelatives(attached, shapes=True, fullPath=True) or []) if attached else set()
            if cam not in names:      # attached to another camera: start again
                cmds.delete(tr)
                tr = shape = None
        new = shape is None
        if new:
            made = cmds.imagePlane(camera=cam, fileName=path)
            tr = cmds.rename(made[0], scene.REF_PLANE)
            shape = cmds.listRelatives(tr, shapes=True, type="imagePlane", fullPath=True)[0]
            cmds.setAttr(shape + ".fit", 0)                        # Fill
            cmds.setAttr(shape + ".displayOnlyIfCurrent", 1)       # only through this camera
            cmds.setAttr(tr + ".overrideEnabled", 1)
            cmds.setAttr(tr + ".overrideDisplayType", 2)           # reference: can't click it
        cmds.setAttr(shape + ".imageName", path, type="string")
        cmds.setAttr(shape + ".useFrameExtension", 1)
        cmds.setAttr(shape + ".frameOffset", offset)
        if not cmds.listConnections(shape + ".frameExtension", source=True, destination=False):
            cmds.connectAttr("time1.outTime", shape + ".frameExtension", force=True)
        near = cmds.getAttr(cam + ".nearClipPlane")
        far = cmds.getAttr(cam + ".farClipPlane")
        depth = min(near * 1.5, far * 0.5) if mode == "front" else far * 0.95
        cmds.setAttr(shape + ".depth", depth)
        if self.save_cb is None:
            self.save_cb = om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave, self._before_save)
        # b17: in your Maya only; the cache gets it at the next Refresh, like
        # every image plane ("sometimes you just want it in your Maya")
        print("bgcache: reference image plane %s (%s); press Refresh in the player to see it in the cache"
              % ("in front" if mode == "front" else "behind", path))

    def _send_image_planes(self):
        """The background Maya gets your image planes as they are now (the
        reference plane included) and re-renders, so the player shows your
        animation over them."""
        cfg = self.cfg or {}
        if not self.running or "start" not in cfg:
            return
        try:
            common.post_message(self.session, {"op": "image_planes", "planes": scene.image_planes(),
                                               "ranges": [[cfg["start"], cfg["end"]]]})
        except Exception as error:
            scene._ignored(error)            # the plane in your Maya matters more than the cache

    def remove_image_plane(self):
        self.trace("image-plane-remove")
        tr, _shape = self._find_plane()
        if tr:
            cmds.delete(tr)
            print("bgcache: reference image plane removed (the cache drops it at the next Refresh)")

    def _before_save(self, *args):
        """Saving with the reference image plane still in: offer to remove it."""
        self.trace("before-save")
        tr, _shape = self._find_plane()
        if not tr:
            return
        answer = cmds.confirmDialog(
            title="bgcache", button=["Remove it", "Keep it"], defaultButton="Remove it",
            message="The bgcache reference image plane is in this scene.\n"
                    "Remove it before saving so it doesn't end up in your file?")
        if answer == "Remove it":
            self.remove_image_plane()
