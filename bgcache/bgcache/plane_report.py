"""What Maya has loaded for each camera image plane, as text (0.9.0b14).

For finding out why a plane looks different in the cache than in your Maya
(seen at a studio: one image sequence plane of three came out blurred in the
background Maya only). The background Maya writes this to worker.log at Start
and at every Refresh; in your own Maya, for comparing:

    import bgcache.plane_report as r; r.show()

No state; reads only.
"""
import os
import re

PLANE_ATTRS = ("type", "displayMode", "useFrameExtension", "frameExtension", "frameOffset", "frameCache",
               "frameIn", "frameOut", "coverageX", "coverageY", "coverageOriginX", "coverageOriginY",
               "depth", "fit", "sizeX", "sizeY", "offsetX", "offsetY", "squeezeCorrection", "alphaGain",
               "textureFilter", "displayOnlyIfCurrent", "lockedToCamera", "colorSpace", "visibility")
GLOBAL_ATTRS = ("enableTextureMaxRes", "textureMaxResolution", "multiSampleEnable", "multiSampleCount",
                "motionBlurEnable", "ssaoEnable", "renderDepthOfField", "transparencyAlgorithm")


def _get(cmds, plug):
    try:
        value = cmds.getAttr(plug)
    except Exception as error:  # an attribute this Maya doesn't have: say so, carry on
        return "? (%s)" % str(error).strip().split("\n")[-1][:60]
    return round(value, 3) if isinstance(value, float) else value


def frame_file(image_name, frame):
    """The file a sequence plane shows at this frame: the last run of digits
    before the extension replaced, keeping its padding."""
    found = re.search(r"(\d+)(\.[A-Za-z0-9]+)$", image_name or "")
    if not found:
        return image_name or ""
    digits = found.group(1)
    return image_name[:found.start(1)] + str(int(frame)).zfill(len(digits)) + found.group(2)


def _file_text(path):
    if not path:
        return "no file"
    if not os.path.isfile(path):
        return "NOT ON DISK: %s" % os.path.basename(path)
    return "%s, %d KB" % (os.path.basename(path), os.path.getsize(path) // 1024)


def plane_lines(cmds):
    out = []
    for shape in cmds.ls(type="imagePlane", long=True) or []:
        try:
            cams = [c for c in (cmds.imagePlane(shape, query=True, camera=True) or []) if c]     # a free plane answers [""]
        except Exception as error:  # shown in the report in place of the camera
            cams = ["? (%s)" % error]
        attrs = dict((a, _get(cmds, "%s.%s" % (shape, a))) for a in PLANE_ATTRS)
        name = _get(cmds, shape + ".imageName")
        shown = name
        if attrs.get("useFrameExtension") is True and isinstance(attrs.get("frameExtension"), (int, float)):
            offset = attrs.get("frameOffset") if isinstance(attrs.get("frameOffset"), (int, float)) else 0
            shown = frame_file(name, attrs["frameExtension"] + offset)
        try:
            size = cmds.imagePlane(shape, query=True, imageSize=True)
        except Exception as error:  # shown in the report in place of the size
            size = "? (%s)" % error
        try:
            driven = cmds.listConnections(shape + ".frameExtension", source=True, destination=False) or []
        except Exception:  # no such plug in this Maya
            driven = []
        out.append("  plane %s on %s: %s; Maya says its size is %s; frame driven by %s"
                   % (shape.split("|")[-1], ", ".join(c.split("|")[-1] for c in cams) or "no camera",
                      _file_text(shown), size, ", ".join(driven) or "nothing"))
        out.append("    " + ", ".join("%s %s" % (a, attrs[a]) for a in PLANE_ATTRS))
    return out


def global_lines(cmds, panel=None):
    out = ["  render settings: " + ", ".join(
        "%s %s" % (a, _get(cmds, "hardwareRenderingGlobals." + a)) for a in GLOBAL_ATTRS)]
    try:
        out.append("  material loading: %s" % cmds.displayPref(query=True, materialLoadingMode=True))
    except Exception as error:
        out.append("  material loading: ? (%s)" % error)
    if panel:
        try:
            cam = cmds.modelPanel(panel, query=True, camera=True)
            shapes = cmds.listRelatives(cam, shapes=True, type="camera", fullPath=True) or [cam]
            out.append("  camera %s: depthOfField %s, focusDistance %s, fStop %s, overscan %s"
                       % (cam.split("|")[-1], _get(cmds, shapes[0] + ".depthOfField"),
                          _get(cmds, shapes[0] + ".focusDistance"), _get(cmds, shapes[0] + ".fStop"),
                          _get(cmds, shapes[0] + ".overscan")))
        except Exception as error:
            out.append("  camera: ? (%s)" % error)
    return out


def report(cmds, panel=None):
    """The whole report, as lines."""
    planes = plane_lines(cmds)
    return (["image planes (%d):" % (len(planes) // 2)] + planes + global_lines(cmds, panel))


def show():
    """In your own Maya's Script Editor: print the report for comparing with worker.log."""
    import maya.cmds as cmds
    panel = None
    for p in cmds.getPanel(type="modelPanel") or []:
        if p == cmds.getPanel(withFocus=True):
            panel = p
    print("\n".join(report(cmds, panel)))
