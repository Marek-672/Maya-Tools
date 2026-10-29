"""What bgcache reads from your Maya: cameras, viewport settings and renderer,
image planes, sound, GPU Override, path curves, anim curve data, and where
Maya and mayapy are. Plain functions, no state (except DISPLAY_SOURCE, the
viewport viewport_display() last read). Used by the Controller.

Before 0.8.0b21 these lived in controller.py; they are still importable
from there (bgcache.controller.list_cameras etc.)."""
import bisect
import math
import os
import shutil

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

from bgcache import common, profile, system

SETTLE_S = 0.25       # the player must rest on a frame this long before your Maya follows it


def _current():
    """The running Controller in this Maya, or None (looked up when needed:
    controller.py imports this module)."""
    import sys
    return getattr(sys.modules.get("bgcache.controller"), "_controller", None)


TIME_CURVE_TYPES = ["animCurveTL", "animCurveTA", "animCurveTU", "animCurveTT"]
FPS_UNITS = {"game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0,
             "show": 48.0, "palf": 50.0, "ntscf": 60.0}
# Viewport settings copied from your active panel to the background render view.
DISPLAY_FLAGS = ["displayAppearance", "displayTextures", "displayLights",
                 "wireframeOnShaded", "xray", "backfaceCulling",
                 "useDefaultMaterial", "twoSidedLighting", "shadows",
                 "polymeshes", "nurbsSurfaces", "subdivSurfaces", "planes",
                 "pluginShapes", "imagePlane", "strokes", "fluids", "hairSystems",
                 "nParticles", "particleInstancers", "dynamics", "greasePencils"]


def plugin_display_filters(panels):
    """Your viewports' setting for each plug-in display filter (gpuCache,
    USD proxies, studio set shapes...). These are separate from the general
    "plug-in shapes" switch, so they have to be copied one by one. A filter
    counts as on if it's on in any of the viewports given."""
    if isinstance(panels, str):
        panels = [panels]
    out = {}
    try:
        names = cmds.pluginDisplayFilter(query=True, listFilters=True) or []
    except Exception as error:
        _ignored(error)
        return out
    for name in names:
        out[name] = False
        for panel in panels:
            try:
                if cmds.modelEditor(panel, query=True, queryPluginObjects=name):
                    out[name] = True
                    break
            except Exception as error:
                _ignored(error)
    return out


def viewport_display():
    """The display settings of the viewport you're working in (DISPLAY_FLAGS
    plus the plug-in filters), for the background render view. Read at Start
    and again at every Refresh. {} if there's no viewport."""
    display = {}
    # b17: everything from the viewport looking through the shot camera (the
    # one the player shows, else any shot camera); the viewport you last
    # clicked only if none does. A last-clicked viewport with textures off
    # gave a grey cache that pointing another viewport at the shot camera
    # couldn't fix (studio, 2026-10-28).
    try:
        panel = _shot_camera_panel() or _active_model_panel()
    except Exception as error:
        _ignored(error)
        panel = None
    global DISPLAY_SOURCE
    DISPLAY_SOURCE = ""
    if not panel:
        return display
    try:
        cam = cmds.modelPanel(panel, query=True, camera=True) or ""
        DISPLAY_SOURCE = "%s, looking through %s" % (panel, cam.split("|")[-1])
    except Exception as error:
        _ignored(error)
        DISPLAY_SOURCE = panel
    for flag in DISPLAY_FLAGS:
        try:
            display[flag] = cmds.modelEditor(panel, query=True, **{flag: True})
        except Exception as error:
            _ignored(error)
    display["pluginObjects"] = plugin_display_filters(_visible_model_panels() or [panel])
    # Show > Image Planes is read like the rest, from that viewport (b14: no
    # longer forced on; b12-b13 drew planes you had hidden)
    return display


DISPLAY_SOURCE = ""      # which viewport viewport_display() last read, for the log


def viewport_renderer():
    """b16: the renderer your shot camera's viewport draws with (e.g. Viewport
    2.0 with a studio override such as the studioViewport2) and the plug-ins that
    provide it, so the background Maya draws the cache the same way. At the
    studio the standard Viewport 2.0 was ~20x slower than yours (3.6 s a frame
    against 5.7 fps) and a plain playblast crashes your Maya. {} if unknown."""
    if profile.get("background_viewport_renderer") is False:
        return {}
    try:
        panel = _shot_camera_panel() or _active_model_panel()
    except Exception as error:
        _ignored(error)
        return {}
    if not panel:
        return {}
    out = {}
    try:
        out["renderer"] = cmds.modelEditor(panel, query=True, rendererName=True) or ""
        out["override"] = cmds.modelEditor(panel, query=True, rendererOverrideName=True) or ""
    except Exception as error:
        _ignored(error)
        return {}
    plugins = []
    if out.get("override"):
        wanted = [n.lower() for n in (profile.get("viewport_plugins") or [])]
        for name in cmds.pluginInfo(query=True, listPlugins=True) or []:
            low = name.lower()
            if low in wanted or "viewport" in low:
                try:
                    plugins.append({"name": name, "path": cmds.pluginInfo(name, query=True, path=True)})
                except Exception as error:
                    _ignored(error)
    out["plugins"] = plugins
    return out


def curve_definition(shape):
    """{shape, degree, knots, cvs} of a NURBS curve, CVs in object space."""
    sel = om.MSelectionList()
    sel.add(shape)
    fn = om.MFnNurbsCurve(sel.getDagPath(0))
    return {"shape": shape, "degree": int(fn.degree), "knots": [float(k) for k in fn.knots()],
            "cvs": [[p.x, p.y, p.z] for p in fn.cvPositions(om.MSpace.kObject)]}


PATH_DRIVEN_TYPES = ("motionPath", "ikHandle", "wire", "pointOnCurveInfo", "nearestPointOnCurve",
                     "curveInfo", "loft", "extrude", "rebuildCurve", "attachCurve")


def path_curves(limit=200):
    """Curve shapes that drive something (PATH_DRIVEN_TYPES) and that you
    edit by hand (nothing feeds their shape), as long names."""
    out = []
    try:
        shapes = cmds.ls(type="nurbsCurve", long=True, noIntermediate=True) or []
    except Exception as error:
        _ignored(error)
        return out
    for shape in shapes:
        try:
            if cmds.listConnections(shape + ".create", source=True, destination=False):
                continue                      # built from other nodes: follows them
            drives = cmds.listConnections(shape, source=False, destination=True) or []
            if any(cmds.nodeType(n) in PATH_DRIVEN_TYPES for n in set(drives)):
                out.append(shape)
        except Exception as error:
            _ignored(error)
        if len(out) >= limit:
            break
    return out


def _shot_camera_panel(session=None):
    """The visible viewport looking through the camera shown in the player
    (or any shot camera), else None."""
    shots = {c["name"] for c in list_cameras()}
    view = None
    try:
        c = _current()
        if c is not None and c.session:
            view = (common.read_json(common.paths(c.session)["cameras"]) or {}).get("view")
    except Exception as error:
        _ignored(error)
    found = None
    for panel in _visible_model_panels():
        try:
            cam = cmds.modelPanel(panel, query=True, camera=True)
            if cam and cmds.nodeType(cam) == "camera":
                cam = (cmds.listRelatives(cam, parent=True, fullPath=True) or [cam])[0]
            cam = (cmds.ls(cam, long=True) or [cam])[0]
        except Exception as error:
            _ignored(error)
            continue
        if view and cam == view:
            return panel
        if found is None and cam in shots:
            found = panel
    return found


# Image plane settings mirrored to the background Maya (Refresh, and the
# player's reference image plane): planes made after Start aren't in its scene.
PLANE_ATTRS = ("imageName", "useFrameExtension", "frameOffset", "frameExtension", "depth",
               "fit", "alphaGain", "displayMode", "displayOnlyIfCurrent", "offsetX", "offsetY",
               "sizeX", "sizeY", "rotate", "squeezeCorrection", "frameIn", "frameOut")


def image_planes():
    """Every camera image plane in your scene: [{name, camera, attrs, time,
    visible}] (time: its frame follows the time slider)."""
    out = []
    for shape in cmds.ls(type="imagePlane", long=True) or []:
        try:
            tr = (cmds.listRelatives(shape, parent=True, fullPath=True) or [shape])[0]
            cams = cmds.imagePlane(shape, query=True, camera=True) or []
            if not cams:
                continue                       # free image planes aren't camera backdrops
            attrs = {}
            for attr in PLANE_ATTRS:
                plug = "%s.%s" % (shape, attr)
                if cmds.attributeQuery(attr, node=shape, exists=True):
                    attrs[attr] = cmds.getAttr(plug)
            src = cmds.listConnections(shape + ".frameExtension", source=True, destination=False) or []
            # hidden with H (transform or shape) or display mode None: off in the cache too
            visible = bool(cmds.getAttr(tr + ".visibility")) and bool(cmds.getAttr(shape + ".visibility")) \
                and attrs.get("displayMode", 1) != 0
            out.append({"name": tr.split("|")[-1], "camera": cams[0].split("|")[-1], "attrs": attrs,
                        "time": any(cmds.nodeType(s) == "time" for s in src),
                        "visible": visible})
        except Exception as error:
            _ignored(error)
    return out


CONSTANT =int(oma.MFnAnimCurve.kConstant)
DEBOUNCE_MS = 100
HELD_POLL_MS = 50        # while a mouse button is down (dragging keys), check again this often
HELD_MAX_S = 5.0         # ...but send anyway after this long, in case the button state is wrong


def _mouse_held():
    """True while a mouse button is down in Maya (dragging keys in the Graph
    Editor, a manipulator, a channel-box slider). A drag on a heavy rig updates
    slower than the debounce, so without this every step of it was sent."""
    try:
        try:
            from PySide6 import QtGui
        except ImportError:  # Maya 2024 and earlier (PySide2)
            from PySide2 import QtGui
        buttons = QtGui.QGuiApplication.mouseButtons()
        try:
            return int(buttons) != 0
        except TypeError:        # PySide6 6.8 (Maya 2027): flags aren't numbers any more
            return getattr(buttons, "value", 0) != 0
    except Exception as error:
        _ignored(error)
        return False


# --------------------------------------------------------------------------
# Curve reading and diffing
# --------------------------------------------------------------------------
def _r(x):
    return round(float(x), 7)


def _mobj(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDependNode(0)


def curve_plug(name):
    """The plug a curve drives, ignoring curves parked on reference nodes."""
    dests = cmds.listConnections(name + ".output", source=False, destination=True,
                                 plugs=True, skipConversionNodes=True) or []
    for dest in dests:
        if cmds.nodeType(dest.split(".")[0]) != "reference":
            return dest
    return None


def read_curve(name):
    fn = oma.MFnAnimCurve(_mobj(name))
    unit = om.MTime.uiUnit()
    keys = []
    for i in range(fn.numKeys):
        ix, iy = fn.getTangentXY(i, True)
        ox, oy = fn.getTangentXY(i, False)
        keys.append((
            _r(fn.input(i).asUnits(unit)), _r(fn.value(i)),
            int(fn.inTangentType(i)), int(fn.outTangentType(i)),
            _r(ix), _r(iy), _r(ox), _r(oy),
            bool(fn.tangentsLocked(i)), bool(fn.weightsLocked(i)),
            bool(fn.isBreakdown(i)),
        ))
    return {
        "curve": name,
        "keys": keys,
        "weighted": bool(fn.isWeighted),
        "pre": int(fn.preInfinityType),
        "post": int(fn.postInfinityType),
    }


TOL = 1e-6


def plug_value(plug):
    """A plug's value in Maya's internal units (radians, cm), same as curves."""
    sel = om.MSelectionList()
    sel.add(plug)
    return sel.getPlug(0).asDouble()


def frame_values(name, first, last):
    """A curve's value on every frame of the shot (internal units)."""
    fn = oma.MFnAnimCurve(_mobj(name))
    unit = om.MTime.uiUnit()
    return [fn.evaluate(om.MTime(f, unit)) for f in range(first, last + 1)]


def changed_frames(old_vals, new_vals, first):
    """Ranges of frames whose values differ."""
    out = []
    for i, (a, b) in enumerate(zip(old_vals, new_vals)):
        if abs(a - b) > TOL:
            f = first + i
            if out and out[-1][1] == f - 1:
                out[-1][1] = f
            else:
                out.append([f, f])
    return out


def constant_value(data):
    """The value a curve holds over the whole shot, or None if it varies."""
    keys = (data or {}).get("keys") or []
    if not keys:
        return None
    value = keys[0][1]
    if len(keys) == 1:
        return value
    for k in keys:   # equal values with flat tangents
        if abs(k[1] - value) > TOL or abs(k[5]) > TOL or abs(k[7]) > TOL:
            return None
    return value


def cycling(data):
    return data["pre"] != CONSTANT or data["post"] != CONSTANT


def scene_plugins():
    """Plug-ins whose nodes are in the scene (with their paths), so a lighter
    background Maya can load just those, even ones the scene doesn't list."""
    out = []
    for name in cmds.pluginInfo(query=True, listPlugins=True) or []:
        try:
            types = cmds.pluginInfo(name, query=True, dependNode=True) or []
            if types and cmds.ls(type=types):
                out.append({"name": name, "path": cmds.pluginInfo(name, query=True, path=True)})
        except Exception as error:
            _ignored(error)
    return out


def sample_curve(name, keys, limit=60):
    """Values at keys and between keys, so the worker can verify its rebuild."""
    fn = oma.MFnAnimCurve(_mobj(name))
    unit = om.MTime.uiUnit()
    times = [k[0] for k in keys]
    mids = [(a + b) * 0.5 for a, b in zip(times, times[1:])]
    ts = sorted(set(times + mids))
    if len(ts) > limit:
        step = len(ts) / float(limit)
        ts = [ts[int(i * step)] for i in range(limit)]
    return [[t, fn.evaluate(om.MTime(t, unit))] for t in ts]


def dirty_ranges(old, new, first, last):
    """Inclusive frame ranges whose values may differ between two curve snapshots."""
    full = [[first, last]]
    if old is None:
        return full  # curve we haven't seen before: the attribute was static
    old_keys, new_keys = set(old["keys"]), set(new["keys"])
    changed = old_keys ^ new_keys
    settings_old = (old["pre"], old["post"], old["weighted"])
    settings_new = (new["pre"], new["post"], new["weighted"])
    if not changed and settings_old == settings_new:
        return []
    if settings_old != settings_new:
        return full
    if new["pre"] != CONSTANT or new["post"] != CONSTANT:
        return full
    stable = sorted({k[0] for k in old_keys & new_keys})
    out = []
    for t in sorted({k[0] for k in changed}):
        i = bisect.bisect_left(stable, t)
        lo = stable[i - 1] if i > 0 else first
        j = bisect.bisect_right(stable, t)
        hi = stable[j] if j < len(stable) else last
        a = max(first, int(math.floor(lo)))
        b = min(last, int(math.ceil(hi)))
        if a <= b:
            out.append((a, b))
    return common.merge_ranges(out)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def scene_fps():
    unit = cmds.currentUnit(query=True, time=True)
    if unit in FPS_UNITS:
        return FPS_UNITS[unit]
    if unit.endswith("fps"):
        try:
            return float(unit[:-3])
        except ValueError:
            pass
    return 24.0


def _visible_model_panels():
    """Viewports actually on screen."""
    try:
        return [p for p in cmds.getPanel(visiblePanels=True) or []
                if cmds.getPanel(typeOf=p) == "modelPanel"]
    except Exception as error:
        _ignored(error)
        return []


def _active_model_panel():
    """The viewport you're working in. Maya can report focus on a viewport
    that's no longer on screen (the default perspective view after switching
    layouts), so the focused one only counts if it's visible."""
    visible = _visible_model_panels()
    panel = cmds.getPanel(withFocus=True)
    if panel and panel in visible:
        return panel
    return visible[0] if visible else None


def _is_startup_camera(shape):
    try:
        return bool(cmds.camera(shape, query=True, startupCamera=True))
    except Exception:  # not a camera any more: not a startup camera
        return False


def default_camera_nodes():
    """Long names of persp/top/front/side, shapes and transforms. Their keys are
    ignored: tumbling persp with Auto Key on must not re-render anything."""
    out = set()
    for shape in cmds.ls(type="camera", long=True) or []:
        if _is_startup_camera(shape):
            out.add(shape)
            out.update(cmds.listRelatives(shape, parent=True, fullPath=True) or [])
    return out


def list_cameras():
    """The scene's own cameras for the player (persp/top/front/side left out)."""
    out = []
    for shape in cmds.ls(type="camera", long=True) or []:
        if _is_startup_camera(shape):
            continue
        parent = cmds.listRelatives(shape, parent=True, fullPath=True)
        if parent:
            out.append({"name": parent[0], "label": parent[0].split("|")[-1],
                        "gate": camera_gate(shape)})
    out.sort(key=lambda c: c["label"].lower())
    return out


def maya_project():
    """The current Maya project's folder, or None."""
    try:
        root = cmds.workspace(query=True, rootDirectory=True)
    except Exception:  # no workspace set: no project
        return None
    return os.path.normpath(root) if root else None


def _maya_hotkeys():
    """Your Maya hotkeys for the player (step, key jump, play, scrub...)."""
    try:
        from bgcache import hotkeys
        keys = hotkeys.read_maya_hotkeys(cmds)
        print("bgcache: player keys from your Maya: %s" % ", ".join(
            "%s %s" % (a, "/".join(hotkeys.spec_text(s) for s in specs) or "-")
            for a, specs in sorted(keys["actions"].items())))
        return keys
    except Exception as error:
        _ignored(error)
        return None


def camera_gate(shape):
    """Film back and fit of a camera, so drawings can be placed on its view
    (Blue Pencil export). Film aperture in inches; fit 0 fill, 1 horizontal,
    2 vertical, 3 overscan."""
    try:
        return {"fw": float(cmds.getAttr(shape + ".horizontalFilmAperture")),
                "fh": float(cmds.getAttr(shape + ".verticalFilmAperture")),
                "fit": int(cmds.getAttr(shape + ".filmFit")),
                "aspect": float(cmds.getAttr("defaultResolution.deviceAspectRatio"))}
    except Exception as error:
        _ignored(error)
        return None


def _audio_muted(node):
    try:
        return bool(cmds.getAttr(node + ".mute"))
    except Exception:  # no mute attribute: not muted
        return False


def pick_sound_node(nodes, muted=lambda n: False):
    """Several sound tracks and none chosen on the time slider (e.g. a shot
    loaded with its full mix plus dialogue/music/effects stems): the first
    that matches the profile's "sound_preference" (in that order, matched in
    the node name, case-insensitive), skipping muted ones; else the first
    track that isn't muted; None if all are muted."""
    live = [n for n in nodes if not muted(n)]
    for want in profile.get("sound_preference") or []:
        for n in live:
            if want.lower() in n.split("|")[-1].lower():
                return n
    return live[0] if live else None


def find_audio():
    """The sound on the time slider (what Maya plays), else the only audio node."""
    node = None
    try:
        slider = mel.eval("$bgcacheTmp = $gPlayBackSlider")
        node = cmds.timeControl(slider, query=True, sound=True) or None
    except Exception as error:
        _ignored(error)
    nodes = cmds.ls(type="audio") or []
    if not node and len(nodes) == 1:
        node = nodes[0]
        print("bgcache: no sound on the time slider, using the only audio node %s" % node)
    if not node and nodes:
        node = pick_sound_node(nodes, lambda n: _audio_muted(n))
        if node:
            print("bgcache: no single sound on the time slider (audio nodes: %s); using %s. "
                  "Pick one on the time slider to choose another." % (", ".join(nodes), node))
    if not node:
        if nodes:
            print("bgcache: no sound on the time slider (audio nodes: %s); player is silent. "
                  "Set the time slider sound before Start." % ", ".join(nodes))
        return None

    def attr(name, default=None):
        try:
            return cmds.getAttr("%s.%s" % (node, name))
        except Exception:  # attribute missing on this sound node: the default
            return default

    path = attr("filename") or ""
    if path and not os.path.isabs(path):
        try:
            path = cmds.workspace(expandName=path)
        except Exception as error:
            _ignored(error)
    if not path or not os.path.isfile(path):
        cmds.warning("bgcache: sound file for %s not found: %r" % (node, path))
        return None
    return {"node": node, "path": path, "offset": float(attr("offset", 0.0) or 0.0),
            "source_start": float(attr("sourceStart", 0.0) or 0.0),
            "source_end": float(attr("sourceEnd", 0.0) or 0.0),
            "mute": bool(attr("mute", False))}



def _ignored(error):
    """An error bgcache deliberately doesn't interrupt you with: noted in
    trace.log (condensed per place) so problems can still be traced."""
    try:
        import inspect
        where = inspect.currentframe().f_back.f_code.co_name
    except Exception:  # frame info unavailable: logged under '?'
        where = "?"
    c = _current()
    if c is not None:
        c.trace("ignored:" + where, "%s: %s" % (type(error).__name__, str(error)[:200]))

BG_APP_DIR = os.path.join(os.path.expanduser("~"), ".bgcache", "maya_app")
# Left out when seeding the background Maya's prefs from yours: window layout,
# panel layouts and shelves (the background Maya never needs them).
PREFS_SKIP = ("windowPrefs.mel", "workspaces", "shelves", "*.deleted", "*.bak")


def background_prefs(refresh=False):
    """The background Maya gets its own MAYA_APP_DIR, so it can never read or
    write YOUR preferences, layout or shelves. It's seeded once from your
    prefs (without layouts and shelves) so it starts configured like yours and
    without Maya's first-run prompts. Returns (its MAYA_APP_DIR, your Maya
    version folder, e.g. ~/maya/2024)."""
    import shutil
    user_prefs = cmds.internalVar(userPrefDir=True).rstrip("/")
    version_dir = os.path.dirname(user_prefs)
    dest = os.path.join(BG_APP_DIR, os.path.basename(version_dir), "prefs")
    if refresh and os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    if not os.path.isdir(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(user_prefs, dest, ignore=shutil.ignore_patterns(*PREFS_SKIP))
        print("bgcache: made the background Maya's own preferences in %s" % dest)
    return BG_APP_DIR, version_dir


def gpu_override_on():
    """Is GPU Override (the deformer evaluator) on in YOUR Maya? The
    background Maya does the same: forcing it on there hung a shot whose rig
    freezes on the GPU (studio, 2026-10-20)."""
    # b17: with GPU Override off the deformer evaluator often isn't registered
    # at all, and the query then returns the list of every evaluator (studio,
    # 2026-10-28), which b11-b16 read as "on": the background Maya got the GPU
    # with your Override off, and a rig that fails there forced a restart.
    try:
        registered = cmds.evaluator(query=True) or []
        if isinstance(registered, str):
            registered = [registered]
        if "deformer" not in registered:
            return False
        on = cmds.evaluator(name="deformer", query=True, enable=True)
        if isinstance(on, (list, tuple)):
            # a one-item [True] answer only; a list of names means "not registered"
            return len(on) == 1 and on[0] is True
        return on is True or on == 1
    except Exception as error:
        _ignored(error)
        return False


def gpu_choice():
    """(use GPU deformers in the background Maya?, why) from the profile's
    background_gpu: "follow" (your Maya's GPU Override; the default),
    "always" (the GPU even when yours is off: studio shots that switch it off
    on open), false (always the CPU)."""
    mode = profile.get("background_gpu")
    if mode is False or str(mode).lower() in ("false", "never", "off", "cpu"):
        return False, "off: the pipeline profile says CPU"
    if str(mode).lower() == "always":
        return True, "on: the pipeline profile says always"
    if gpu_override_on():
        return True, "on: GPU Override is on in your Maya"
    return False, "off: GPU Override is off in your Maya"


def _pkg_parent():
    """The folder that contains the bgcache package."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def visibility_states():
    """{transform: visible} for every transform (fast, via the API)."""
    out = {}
    it = om.MItDependencyNodes(om.MFn.kTransform)
    while not it.isDone():
        try:
            fn = om.MFnDagNode(it.thisNode())
            out[fn.fullPathName()] = fn.findPlug("visibility", False).asBool()
        except Exception as error:
            _ignored(error)
        it.next()
    return out


# Paths searched for Maya modules, scripts and plug-ins: entries matching
# skip_in_background are dropped for the background Maya only.
PATH_VARS = ("MAYA_MODULE_PATH", "PYTHONPATH", "MAYA_SCRIPT_PATH", "MAYA_PLUG_IN_PATH", "XBMLANGPATH")

BUSY_EVENTS = ("time", "curve-edited", "curve-added", "curve-removed", "selection")
REF_PLANE = "bgcache_reference"     # the reference image plane's name

DISPLAY_LAYER_ATTRS = ("visibility", "displayType", "hideOnPlayback", "enabled")


def display_layer_values():
    values = []
    for layer in cmds.ls(type="displayLayer") or []:
        if layer == "defaultLayer":
            continue
        for attr in DISPLAY_LAYER_ATTRS:
            plug = "%s.%s" % (layer, attr)
            try:
                if cmds.objExists(plug):
                    values.append([plug, cmds.getAttr(plug)])
            except Exception as error:
                _ignored(error)
    return values


def _fmt(seconds):
    seconds = int(seconds)
    return "%d:%02d" % (seconds // 60, seconds % 60)


def find_maya():
    """The Maya program for the background Maya: the same Maya as this one if
    possible, so it shares the exact setup (per system: bgcache/system/).
    The profile's maya_wrappers are tried on the PATH last."""
    return system.find_maya(tuple(profile.get("maya_wrappers") or ()))


def find_mayapy():
    """mayapy, for the player window (per system: bgcache/system/)."""
    return system.find_mayapy()
