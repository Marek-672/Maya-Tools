"""Background half of bgcache. Runs inside a second Maya launched by the controller.

Loop (driven by a Qt timer so the inbox is checked between chunks):
    1. apply any messages from the controller (curve rebuilds, static values)
    2. pick up the player's camera choice (cameras.json)
    3. playblast the next small chunk of dirty frames, viewed camera first
    4. move the images into frames/<camera>/ and bump their version in status.json

Nothing renders until a camera is checked in the player.
"""
import collections
import glob
import os
import re
import shutil
import time
import traceback

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

from bgcache import common

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6 as shiboken
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets
    import shiboken2 as shiboken

FIXED = int(oma.MFnAnimCurve.kTangentFixed)
FRAME_RE = re.compile(r"\.(-?\d+)\.jpg$")
DEFAULT_DISPLAY = {"polymeshes": True, "displayAppearance": "smoothShaded",
                   "displayTextures": True, "displayLights": "default"}
FORCED_DISPLAY = {"grid": False, "headsUpDisplay": False, "manipulators": False,
                  "selectionHiliteDisplay": False, "nurbsCurves": False,
                  "joints": False, "locators": False, "cameras": False,
                  "lights": False, "ikHandles": False, "deformers": False,
                  "dimensions": False, "handles": False, "pivots": False,
                  "follicles": False}
MAX_RENDER_FAILURES = 3
REF_PLANE = "bgcache_reference"   # the player's reference image plane (controller.REF_PLANE)
GPU_CHECK_S = 2.0          # how often worker.log is checked for graphics-memory errors
GPU_REDO_S = 60.0          # frames rendered this recently are redone after a GPU failure

# Plug-in display filters kept off in the cache, whatever your viewport showed
# at Start (matched against the filter's name and what it draws), so caching
# draws characters and animation only. Filters on in your viewport are off too.
# (The Envirs button that showed them was removed in 0.6.9; see git v0.6.8.)
ENVIR_FILTER_HINTS = ("usd", "gpucache")

# Batches are sized by time, not frame count: the background Maya can only
# notice a new edit between batches, so batches are kept short. Each playblast
# costs a fixed start-up time plus a time per frame (measured per camera), so a
# batch aims for BATCH_TARGET_S, or longer when the start-up cost is big
# (it stays under OVERHEAD_SHARE of the batch), else single frames would be
# slow overall. A light rig gets bigger batches, a heavy one smaller ones.
# Right after an edit, the viewed camera renders 1 frame first (the one you're
# on), so it shows up as soon as possible. cfg "chunk" is the largest batch.
BATCH_TARGET_S = 0.75
OVERHEAD_SHARE = 0.4       # each playblast has a fixed start-up cost: keep it under this share of a batch
FIRST_BATCH = 3            # second batch of a camera, so its render speed can be measured
IDLE_POLL_MS = 50          # how often an idle background Maya checks for edits
CALM_POLL_MS = 100         # b18: after CALM_AFTER_S with nothing to do, check a little less often
CALM_AFTER_S = 2.0
STATUS_HEARTBEAT = 1.0     # rewrite status.json at least this often (seconds)

_log_path = None
_worker = None


# Editors that redraw on every curve change; the background Maya never needs
# them. Others (Render View, Script Editor, Content Browser...) are left alone:
# closing a window whose tool is active can crash Maya.
EDITOR_HINTS = ("graphEditor", "outliner", "dopeSheet", "nodeEditor", "hyperShade", "hyperGraph",
                "AttributeEditor", "ChannelBox", "timeEditor", "trax", "clipEditor")


def log(msg):
    line = "[bgcache %s] %s\n" % (time.strftime("%H:%M:%S"), msg)
    if _log_path:
        try:
            with open(_log_path, "a") as handle:
                handle.write(line)
        except (IOError, OSError):
            pass                      # never let a log line take the worker down
    print(line.rstrip())


_ignored_last = {}


def _ignored(error):
    """An error the background Maya carries on past: noted in worker.log
    (at most once a minute per place) so problems can still be traced."""
    try:
        import inspect
        where = inspect.currentframe().f_back.f_code.co_name
    except Exception:  # frame info unavailable: logged under '?'
        where = "?"
    now = time.time()
    if now - _ignored_last.get(where, 0) > 60:
        _ignored_last[where] = now
        log("ignored error in %s: %s: %s" % (where, type(error).__name__, str(error)[:200]))



def _mobj(name):
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDependNode(0)


class Worker(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = cfg["session"]
        self.p = common.paths(self.session)
        self.first, self.last = int(cfg["start"]), int(cfg["end"])
        self.cams = {}       # camera -> {"dirty", "versions", "focus", "failures"}
        self.order = []      # checked cameras, in the order they were checked
        self.view = None     # camera shown in the player: rendered first
        self.panel_camera = None
        self.missing = set()
        self.version = 0
        self.edits = []          # recent edits, for turnaround timing in the log
        self.render_hidden = False
        self.render_checked = False
        self.envirs = False          # environment never drawn in the cache (Envirs removed in 0.6.9)
        self.plugin_filters = {}
        self.timing = None        # startup stage times, logged once after the first frames
        self.ready_t = None
        self.ref_times = {}
        self.startup_logged = False
        self.panel = None
        self.range_focus = None    # b18: the player's focus range, or None (whole shot)
        self.quitting = False
        self.last_error = ""
        self.convert_units = False  # flipped automatically if verification says so
        self._ac_check = 0.0
        self.after_edit = False   # next viewed-camera batch is a single frame
        self.paused = False       # Pause re-rendering: edits applied, nothing rendered
        self.timings = {}         # camera -> recent (frames, seconds) per playblast, for batch sizes
        self._status_key = None
        self._status_t = 0.0
        # GPU deformers if your Maya uses them, until they fail, then the CPU
        self.gpu_on = bool(cfg.get("background_gpu", True))
        self.warning = ""          # shown in the player and the Maya panel
        if cfg.get("gpu_rescued"):  # b18: restarted on the CPU: keep saying so while it reloads
            self.warning = "GPU deformers failed in the background Maya: caching on the CPU now (slower)."
        self._recent = []          # (time, camera, frames) rendered lately: redone after a GPU failure
        self._log_pos = 0
        self._gpu_check_t = 0.0

        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.step)

    # ---------------------------------------------------------------- setup
    def setup(self):
        if not self._own_prefs_ok():
            return
        log("GPU deformers: %s" % (self.cfg.get("gpu_reason") or ("on" if self.gpu_on else "off")))
        # Minimize straight away, before the slow scene load, so the window
        # doesn't sit on screen while the shot opens.
        self._minimize_main()
        self._clean_ui()
        self.timing = {"launch": self.cfg["_boot_t"] - self.cfg.get("launch_t", self.cfg["_boot_t"])}
        t = time.time()
        self._load_plugins()
        self.timing["plug-ins"] = time.time() - t
        self.write_status("opening scene")
        self._open(self.cfg["scene"])
        t = time.time()
        self._hide_windows()
        self.timing["setup"] = self.timing.get("setup", 0) + time.time() - t
        self.ready_t = time.time()
        log("scene ready, waiting for cameras from the player")
        self.write_status()
        self.timer.start(0)

    def _own_prefs_ok(self):
        """This Maya must use its own preferences folder, never yours (it
        would save over your prefs when it quits). Log which one it uses; if
        it's yours (the system ignored MAYA_APP_DIR), close at once without
        saving anything."""
        try:
            mine = os.path.normcase(os.path.realpath(cmds.internalVar(userPrefDir=True)))
        except Exception as error:
            log("preferences folder unknown: %s" % error)
            return True
        log("preferences folder: %s" % mine)
        yours = self.cfg.get("user_maya_dir")
        if yours and mine.startswith(os.path.normcase(os.path.realpath(yours)) + os.sep):
            log("this background Maya is using YOUR preferences folder (%s): closing it "
                "without saving anything" % yours)
            self.last_error = "the background Maya would have used your preferences folder"
            self.write_status("error: the background Maya couldn't get its own preferences "
                              "folder, so it closed (see worker.log)")
            self._quit()
            return False
        return True

    def _quit(self):
        """Close this Maya: no "Save changes?" (its scene copy has your edits
        in it; on the Mac Maya asks even with force), no saved preferences."""
        try:
            cmds.file(modified=False)
        except Exception as error:
            _ignored(error)
        try:
            cmds.quit(force=True, abort=True)
        except TypeError:
            cmds.quit(force=True)

    def _load_plugins(self):
        """Light mode: Maya started without auto-loaded plug-ins, so load the
        ones the animator's scene nodes use (scene-listed ones load anyway)."""
        if not self.cfg.get("light"):
            return
        loaded = []
        for plug in self.cfg.get("plugins") or []:
            try:
                if not cmds.pluginInfo(plug["name"], query=True, loaded=True):
                    cmds.loadPlugin(plug["path"] or plug["name"], quiet=True)
                    loaded.append(plug["name"])
            except Exception as error:
                log("could not load plug-in %s: %s" % (plug.get("name"), error))
        log("light start: auto-loaded plug-ins skipped; loaded for this scene: %s"
            % (", ".join(loaded) or "none needed"))

    def _log_startup(self, first_frames):
        """One line saying where startup time went (see the to-do on speed)."""
        t = dict(self.timing)
        t.update(self.cfg.get("timing") or {})
        total = (self.ready_t - self.cfg.get("launched_at", self.ready_t)) + first_frames
        order = ("export", "snapshot", "launch", "plug-ins", "scene open", "setup")
        parts = ["%s %.0fs" % (k, t[k]) for k in order if k in t]
        parts.append("first frames %.0fs" % first_frames)
        log("startup: %s  (total %d:%02d)" % (", ".join(parts), int(total) // 60, int(total) % 60))
        refs = sorted(self.ref_times.items(), key=lambda kv: -kv[1])[:5]
        if refs:
            log("slowest references: %s" % ", ".join("%s %.0fs" % (n, d) for n, d in refs))

    def _open(self, path):
        """Open a scene and set this session up to render it."""
        log("opening %s" % path)
        self.ref_times, starts, ids = {}, {}, []

        def before(fobj, *args):
            starts[fobj.resolvedFullName()] = time.time()

        def after(fobj, *args):
            name = fobj.resolvedFullName()
            if name in starts:
                self.ref_times[os.path.basename(name)] = time.time() - starts.pop(name)
        try:
            ids = [om.MSceneMessage.addReferenceCallback(om.MSceneMessage.kBeforeLoadReference, before),
                   om.MSceneMessage.addReferenceCallback(om.MSceneMessage.kAfterLoadReference, after)]
        except Exception as error:
            log("reference timing unavailable: %s" % error)
        t = time.time()
        try:
            cmds.file(path, open=True, force=True, prompt=False)
        finally:
            for cb in ids:
                try:
                    om.MMessage.removeCallback(cb)
                except Exception as error:
                    _ignored(error)
        if getattr(self, "timing", None) is not None:
            self.timing["scene open"] = time.time() - t
        t = time.time()
        cmds.undoInfo(state=False)
        # Image planes, the player's reference plane included, are kept: the
        # cache shows your animation over them (b12; until b11 the reference
        # plane was deleted here).
        for fn in (lambda: cmds.autoSave(enable=False),
                   lambda: cmds.evaluationManager(mode="parallel"),
                   lambda: cmds.evaluator(name="cache", enable=False),  # no need here
                   lambda: cmds.evaluator(name="deformer", enable=self.gpu_on),  # GPU override
                   # skip nodes that only feed hidden things (hidden characters,
                   # hidden display layers): they aren't drawn, so don't evaluate them
                   lambda: cmds.evaluator(name="invisibility", enable=True),
                   # textures loaded before drawing, not in the background: with
                   # "parallel" loading the first frames after opening came out
                   # without textures (seen at the studio on frames 1001-1002)
                   lambda: cmds.displayPref(materialLoadingMode="immediate")):
            try:
                fn()
            except Exception as error:
                log("setup warning: %s" % error)
        cmds.playbackOptions(minTime=self.first, maxTime=self.last)
        self._switch_off_tools(force=True)
        self._build_panel()
        self._clean_ui()
        self.panel_camera = None
        if getattr(self, "timing", None) is not None:
            self.timing["setup"] = time.time() - t

    def reload(self, msg):
        """Reopen a fresh scene copy in this same Maya (no relaunch), keep the
        player's cameras, and re-render everything."""
        self.write_status("reloading scene")
        for key in ("scene", "start", "end", "display", "display_from", "viewport_renderer"):
            if key in msg:
                self.cfg[key] = msg[key]
        self.first, self.last = int(self.cfg["start"]), int(self.cfg["end"])
        self._open(self.cfg["scene"])
        if self.render_hidden:
            try:
                cmds.window("bgcacheRenderWin", edit=True, iconify=True)
            except Exception as error:
                _ignored(error)
        self.missing = set()
        self.edits = []
        for st in self.cams.values():
            st["versions"] = {f: v for f, v in st["versions"].items() if self.first <= f <= self.last}
            st["dirty"] = set(range(self.first, self.last + 1))
            st["focus"] = self.first
            st["failures"].clear()
        self.reloads = getattr(self, "reloads", 0) + 1
        log("scene reloaded (%d-%d), re-rendering" % (self.first, self.last))

    def _build_panel(self):
        w, h = self.cfg["width"], self.cfg["height"]
        if cmds.window("bgcacheRenderWin", exists=True):
            cmds.deleteUI("bgcacheRenderWin")
        win = cmds.window("bgcacheRenderWin", title="bgcache render view",
                          widthHeight=(w, h))
        layout = cmds.paneLayout(configuration="single")
        self.panel = cmds.modelPanel(parent=layout, menuBarVisible=False)
        cmds.showWindow(win)
        self._apply_renderer()
        self._apply_display()
        self._reload_textures()
        log("viewport settings: %s" % self._display_text())

    def _reload_textures(self):
        """b19: make the render view's renderer load its textures, as you would
        by hand when a viewport comes up grey: textures off and on, and ask
        Viewport 2.0 to reload them. At start and at every Refresh."""
        if not getattr(self, "panel", None):
            return
        try:
            if not cmds.modelEditor(self.panel, query=True, displayTextures=True):
                return                      # your view has textures off: nothing to load
            cmds.modelEditor(self.panel, edit=True, displayTextures=False)
            cmds.refresh(force=True)
            cmds.modelEditor(self.panel, edit=True, displayTextures=True)
        except Exception as error:
            log("texture reload (switch) failed: %s" % error)
            return
        try:
            cmds.ogs(reloadTextures=True)
            how = "switched off/on, Viewport 2.0 reloaded them"
        except Exception:  # older Maya without reloadTextures: the switch alone
            how = "switched off/on"
        log("textures in the render view: %s" % how)

    def _apply_renderer(self):
        """b16: draw with the same renderer as your shot camera's viewport
        (a studio's own Viewport 2.0 render override, as its playblast
        does). Studio-specific set-up (its own viewport options) goes in the
        profile's before_playblast hook, never here (b19)."""
        r = self.cfg.get("viewport_renderer") or {}
        if r.get("renderer"):
            try:
                cmds.modelEditor(self.panel, edit=True, rendererName=r["renderer"])
            except Exception as error:
                log("viewport renderer %s not set: %s" % (r["renderer"], error))
        if r.get("override"):
            try:
                cmds.modelEditor(self.panel, edit=True, rendererOverrideName=r["override"])
                log("viewport renderer: %s with %s (as your shot camera's view)" % (r.get("renderer"), r["override"]))
            except Exception as error:
                log("viewport renderer override %s not set (standard Viewport 2.0 instead): %s"
                    % (r["override"], error))
        else:
            log("viewport renderer: %s" % (r.get("renderer") or "Maya's default"))
        # b19: no ogs(disposeReleasableTextures) here any more: done before
        # anything had drawn, the studio renderer then drew the cache grey
        # (studio, 2026-10-28; textured with the standard Viewport 2.0).
        # b18: the renderer's own shading/texture mode (studio renderers can
        # keep one apart from the viewport's textures switch): logged, so a
        # grey cache shows its cause in worker.log
        modes = []
        for attr in ("renderMode", "lightingMode"):
            try:
                modes.append("%s %s" % (attr, cmds.getAttr("hardwareRenderingGlobals." + attr)))
            except Exception:  # attribute not in this Maya: left out of the log line
                pass
        if modes:
            log("renderer settings: %s" % ", ".join(modes))
        self._before_playblast()

    def _before_playblast(self):
        """b18: the profile's before_playblast hook ("module.function"), for a
        studio's own playblast set-up; called once the render view is made."""
        call = self.cfg.get("before_playblast") or ""
        module, _dot, name = call.rpartition(".")
        if not module or not name:
            return
        try:
            import importlib
            fn = getattr(importlib.import_module(module), name)
            try:
                fn(self.panel)
            except TypeError:
                fn()
            log("before_playblast: %s ran" % call)
        except Exception as error:
            log("before_playblast %s failed: %s" % (call, error))

    def _apply_display(self):
        """Set the render view's display from cfg["display"] (your viewport's
        settings, from Start or the latest Refresh)."""
        if not getattr(self, "panel", None):
            return
        # Start with everything shown, like a fresh viewport, then copy the
        # animator's show/hide settings (including each plug-in filter), then
        # hide the overlays a playblast shouldn't have.
        cmds.modelEditor(self.panel, edit=True, allObjects=True)
        display = dict(DEFAULT_DISPLAY)
        display.update(self.cfg.get("display") or {})
        plugin_filters = display.pop("pluginObjects", None) or {}
        self.show_planes = bool(display.get("imagePlane", True))
        display.update(FORCED_DISPLAY)
        for flag, value in display.items():
            try:
                cmds.modelEditor(self.panel, edit=True, **{flag: value})
            except Exception as error:
                log("display flag %s: %s" % (flag, error))
        # The envirs (USD stage, gpuCache, proxies) are never drawn in the
        # cache: the plug-in filters on in your viewport at Start, plus the
        # environment kinds (ENVIR_FILTER_HINTS), are switched off.
        self.plugin_shapes = bool(display.get("pluginShapes", True))
        self.plugin_filters = self._envir_filters(plugin_filters)
        self._apply_envirs()
        self._apply_plane_visibility()

    def _apply_plane_visibility(self):
        """b14: image planes as in your Maya (Show > Image Planes in the shot
        camera's viewport, each plane's own hide), read at Start and Refresh.
        The player's reference plane is the exception: it shows even when
        Show > Image Planes is off, so then the other planes are hidden here
        one by one instead (never in your scene)."""
        if not getattr(self, "panel", None):
            return
        hidden = getattr(self, "_planes_hidden", set())
        for tr in list(hidden):                 # put back what this did last time
            if cmds.objExists(tr):
                self._set(tr + ".visibility", True)
        self._planes_hidden = set()
        show = getattr(self, "show_planes", True)
        refs, others = [], []
        for shape in cmds.ls(type="imagePlane", long=True) or []:
            try:
                if not (cmds.imagePlane(shape, query=True, camera=True) or []):
                    continue
            except Exception:  # plane gone or unreadable: skipped
                continue
            tr = (cmds.listRelatives(shape, parent=True, fullPath=True) or [shape])[0]
            (refs if tr.split("|")[-1].startswith(REF_PLANE) else others).append(tr)
        if show or not refs:
            cmds.modelEditor(self.panel, edit=True, imagePlane=show)
            if not show and others:
                log("image planes off in the cache (Show > Image Planes is off in your shot camera's view)")
            return
        cmds.modelEditor(self.panel, edit=True, imagePlane=True)
        for tr in others:
            if cmds.getAttr(tr + ".visibility"):
                self._set(tr + ".visibility", False)
                self._planes_hidden.add(tr)
        log("image planes: only the player's reference plane shows (Show > Image Planes is off in your view)")

    def _display_text(self):
        d = self.cfg.get("display") or {}
        parts = [str(d.get("displayAppearance", "smoothShaded")),
                 "textures %s" % ("on" if d.get("displayTextures") else "off"),
                 "%s lights" % (d.get("displayLights") or "default"),
                 "image planes %s" % ("shown" if d.get("imagePlane", True) else "hidden")]
        for flag, label in (("wireframeOnShaded", "wireframe on shaded"), ("xray", "x-ray"),
                            ("backfaceCulling", "backface culling"), ("shadows", "shadows")):
            if d.get(flag):
                parts.append(label)
        text = ", ".join(parts)
        if self.cfg.get("display_from"):
            text += "; from %s" % self.cfg["display_from"]
        return text

    def _envir_filters(self, from_viewport):
        names = {n for n, on in (from_viewport or {}).items() if on}
        try:
            registered = cmds.pluginDisplayFilter(query=True, listFilters=True) or []
        except Exception as error:
            log("could not list plug-in display filters: %s" % error)
            registered = []
        for name in registered:
            try:
                what = cmds.pluginDisplayFilter(name, query=True, classification=True) or ""
            except Exception as error:
                _ignored(error)
                what = ""
            text = ("%s %s" % (name, what)).lower()
            if any(hint in text for hint in ENVIR_FILTER_HINTS):
                names.add(name)
        return {n: True for n in sorted(names)}

    def _apply_envirs(self):
        """Show or hide the envirs (the plug-in shapes your viewport shows) in
        bgcache's render view. Characters and animation are always drawn."""
        if not getattr(self, "panel", None):
            return
        shown = getattr(self, "envirs", False)
        for name in self.plugin_filters:
            try:
                cmds.modelEditor(self.panel, edit=True, pluginObjects=(name, shown))
            except Exception as error:
                log("plug-in display filter %s: %s" % (name, error))
        # The general "Plugin Shapes" switch must be on for any of them to draw;
        # with Envirs off it goes back to what your viewport had at Start.
        try:
            cmds.modelEditor(self.panel, edit=True,
                             pluginShapes=True if shown else getattr(self, "plugin_shapes", True))
        except Exception as error:
            log("plugin shapes: %s" % error)
        log("envirs %s in the cache (%s)" % ("shown" if shown else "hidden",
                                             ", ".join(sorted(self.plugin_filters)) or "no plug-in shapes"))

    def _hide_windows(self):
        """Minimize this Maya's windows. The render window is put back by
        _check_render if minimizing it makes playblasts come out blank."""
        if not self.cfg.get("hide", True):
            return
        self._minimize_main()        # again, in case opening the scene raised it
        try:
            cmds.window("bgcacheRenderWin", edit=True, iconify=True)
            self.render_hidden = True
            log("background windows minimized")
        except Exception as error:
            log("could not minimize the render window: %s" % error)
        # On the Mac the main window didn't minimise while Maya was still
        # opening: try again once the event loop runs, and say if it worked.
        for ms in (1500, 5000):
            QtCore.QTimer.singleShot(ms, self._minimize_again)

    def _minimize_again(self):
        try:
            import maya.OpenMayaUI as omui
            main = shiboken.wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)
            if not main.isMinimized():
                main.setWindowState(main.windowState() | QtCore.Qt.WindowMinimized)
                main.showMinimized()
                QtWidgets.QApplication.processEvents()
            done = main.isMinimized()
            if done != getattr(self, "_main_minimized", None):
                self._main_minimized = done
                log("main window minimized: %s" % ("yes" if done else "NO (the system kept it open)"))
        except Exception as error:
            log("could not minimize the main window: %s" % error)

    def trace(self, msg):
        if self.cfg.get("trace", True):
            log("trace: " + msg)

    def _clean_ui(self):
        """The background Maya inherits your saved window layout (Graph Editor,
        Outliner...). Those redraw on every curve the worker rebuilds, a likely
        cause of crashes, and extra viewports redraw the rig for nothing. Close
        the editors, use a single view, and stop other viewports drawing."""
        closed = []
        try:
            cmds.setToolTo("selectSuperContext")    # no editor's tool left active
        except Exception as error:
            _ignored(error)
        for ctl in cmds.lsUI(type="workspaceControl") or []:
            if any(h.lower() in ctl.lower() for h in EDITOR_HINTS):
                try:
                    if cmds.workspaceControl(ctl, query=True, visible=True):
                        cmds.workspaceControl(ctl, edit=True, close=True)
                        closed.append(ctl)
                except Exception as error:
                    _ignored(error)
        for win in cmds.lsUI(windows=True) or []:
            if win in ("MayaWindow", "bgcacheRenderWin"):
                continue
            if any(h.lower() in win.lower() for h in EDITOR_HINTS):
                try:   # hide, don't delete: safer while Maya is busy
                    if cmds.window(win, query=True, visible=True):
                        cmds.window(win, edit=True, visible=False)
                        closed.append(win)
                except Exception as error:
                    _ignored(error)
        try:
            mel.eval('setNamedPanelLayout "Single Perspective View"')
        except Exception as error:
            log("single view layout: %s" % error)
        quiet = 0
        for panel in cmds.getPanel(type="modelPanel") or []:
            if panel == self.panel:
                continue
            try:
                cmds.modelEditor(panel, edit=True, allObjects=False)
                quiet += 1
            except Exception as error:
                _ignored(error)
        try:
            cmds.select(clear=True)
        except Exception as error:
            _ignored(error)
        log("background window cleaned up: closed %s; %d other viewport(s) drawing nothing"
            % (", ".join(closed) or "no editors", quiet))

    def _minimize_main(self):
        if not self.cfg.get("hide", True):
            return
        try:
            import maya.OpenMayaUI as omui
            main = shiboken.wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)
            if not main.isMinimized():
                main.showMinimized()
                QtWidgets.QApplication.processEvents()   # take effect before the blocking load
        except Exception as error:
            log("could not minimize the main window: %s" % error)

    def _blank(self, path):
        """True if an image is one flat colour (what a hidden viewport gives)."""
        img = QtGui.QImage(path)
        if img.isNull():
            return True
        w, h = img.width(), img.height()
        first = img.pixel(0, 0)
        for i in range(1, 12):
            for j in range(1, 12):
                if img.pixel(w * i // 12, h * j // 12) != first:
                    return False
        return True

    def _check_render(self, cam, frames):
        """Once, after the first chunk: if frames are blank while the render
        window is minimized, restore the window and render them again."""
        if self.render_checked or not frames:
            return
        self.render_checked = True
        path = common.frame_path(self.session, min(frames), cam)
        if self.render_hidden and self._blank(path):
            cmds.window("bgcacheRenderWin", edit=True, iconify=False)
            self.render_hidden = False
            self.cams[cam]["dirty"].update(frames)
            log("frames were blank with the render window minimized; restored it "
                "(this graphics setup needs it visible) and re-rendering")

    def _switch_off_tools(self, force=False):
        """Tools the pipeline profile switches off in the background Maya
        (switch_off_in_background), e.g. a studio tool that re-snaps controls
        on every mesh change: controls aren't in the images. Each one is
        called when a script job containing its text is running; checked
        every 5 s, since such tools can start their jobs again. Only in this
        session: your Maya keeps them."""
        rules = self.cfg.get("switch_off_in_background") or []
        if not rules:
            return
        now = time.time()
        if not force and now - self._ac_check < 5.0:
            return
        self._ac_check = now
        jobs = cmds.scriptJob(listJobs=True) or []
        for rule in rules:
            text, call = rule.get("if_scriptjob_contains"), rule.get("call") or ""
            if text and not any(text in job for job in jobs):
                continue
            module, _dot, name = call.rpartition(".")
            if not module or not name:
                continue
            try:
                import importlib
                getattr(importlib.import_module(module), name)()
                log("switched off in the background session: %s" % call)
            except Exception as error:
                log("could not switch off %s: %s" % (call, error))

    # ---------------------------------------------------------------- loop
    def step(self):
        delay = IDLE_POLL_MS
        try:
            messages = common.take_messages(self.session)
            for msg in messages:
                self.handle(msg)
            if self.quitting or not common.pid_alive(self.cfg.get("controller_pid")):
                if self.quitting:
                    log("Stop pressed: closing the background Maya")
                else:
                    log("your Maya (pid %s) is gone, so the background Maya is closing too "
                        "(if your Maya crashed, its crash file is the one to read)"
                        % self.cfg.get("controller_pid"))
                self.write_status("stopped")
                # Never save preferences or ask about saving on the way out.
                self._quit()
                return
            changed = self._sync_cameras()
            if messages or changed:
                self.write_status()  # let the player show new dirty frames right away
            self._switch_off_tools()
            cam = None if getattr(self, "paused", False) else self.next_camera()
            if cam:
                self.render(cam, self.pick_chunk(cam))
                delay = 0
            now = time.time()
            if cam or messages or changed:
                self._busy_t = now
            elif now - getattr(self, "_busy_t", now) > CALM_AFTER_S:
                delay = CALM_POLL_MS           # idle: an edit still shows within ~0.1 s
            self._check_gpu()
            self.write_status()
        except Exception:
            self.last_error = traceback.format_exc()
            log(self.last_error)
            delay = 1000
        self.timer.start(delay)

    def mark(self, a, b):
        a, b = max(self.first, int(a)), min(self.last, int(b))
        if a <= b:
            for st in self.cams.values():
                st["dirty"].update(range(a, b + 1))

    # ---------------------------------------------------------------- cameras
    def _sync_cameras(self):
        """Follow the player's choice in cameras.json. Returns True if anything changed."""
        want = common.read_json(self.p["cameras"]) or {}
        changed = False
        checked = []
        for cam in want.get("checked") or []:
            if cmds.objExists(cam):
                checked.append(cam)
            elif cam not in self.missing:
                self.missing.add(cam)
                log("camera %s not found in the background scene, skipped" % cam)
        for cam in list(self.cams):
            if cam not in checked:
                del self.cams[cam]
                shutil.rmtree(common.frames_dir(self.session, cam), ignore_errors=True)
                log("stopped caching %s" % cam)
                changed = True
        for cam in checked:
            if cam not in self.cams:
                os.makedirs(common.frames_dir(self.session, cam), exist_ok=True)
                self.cams[cam] = {"dirty": set(range(self.first, self.last + 1)),
                                  "versions": {}, "focus": self.first,
                                  "failures": collections.Counter()}
                log("caching %s" % cam)
                changed = True
        self.order = checked
        focus = want.get("focus")
        focus = (int(focus[0]), int(focus[1])) if focus and len(focus) == 2 else None
        if focus != getattr(self, "range_focus", None):
            self.range_focus = focus
            log("focus range: %s" % ("%d-%d (frames outside wait, red)" % focus if focus else "the whole shot"))
            changed = True
        view = want.get("view")
        view = view if view in self.cams else (checked[0] if checked else None)
        if view != self.view:
            self.view = view
            self.edits = []
            changed = True
        return changed

    def _todo(self, cam):
        """Dirty frames to render now: inside the player's focus range (b18);
        the ones outside stay dirty (red) until the range is widened."""
        dirty = self.cams.get(cam, {}).get("dirty") or set()
        focus = getattr(self, "range_focus", None)
        if not focus:
            return dirty
        return {f for f in dirty if focus[0] <= f <= focus[1]}

    def next_camera(self):
        """Viewed camera first, then the other checked cameras in idle time."""
        if self.view and self._todo(self.view):
            return self.view
        for cam in self.order:
            if self._todo(cam):
                return cam
        return None

    def handle(self, msg):
        """One inbox message: control messages (quit, reload, pause, self-test)
        act at once; edits are applied, then the frames they dirty are marked."""
        op = msg.get("op")
        self.trace("message %s%s" % (op, " (%d curves)" % len(msg.get("curves") or []) if op == "curves" else ""))
        if op == "quit":
            self.quitting = True
            return
        if op == "reload":
            self.reload(msg)
            return
        if op == "pause":
            self.set_paused(bool(msg.get("on")), msg.get("focus"))
            return
        if op == "selftest":
            self._run_selftest(msg)
            return
        t_apply = time.time()
        self._apply_edit(op, msg)
        for why in msg.get("why") or []:
            log("whole shot re-rendering: %s" % why)
        ranges = msg.get("ranges") or []
        for a, b in ranges:
            self.mark(a, b)
        if ranges:
            self.after_edit = True          # the frame you're on, on its own, first
            focus = msg.get("focus")
            focus = int(focus) if focus is not None else int(ranges[0][0])
            focus = min(max(focus, self.first), self.last)  # frame you're working on
            for st in self.cams.values():
                st["focus"] = focus
        if op == "curves" and ranges and self.view and not getattr(self, "paused", False):
            self._time_edit(msg, ranges, t_apply)

    def _run_selftest(self, msg):
        """Self-test (player > Help): the report goes to logs/selftest.json."""
        from bgcache import selftest
        self.write_status("self-test running")
        try:
            lines = selftest.background_report(self, msg)
        except Exception:
            lines = ["self-test failed:"] + traceback.format_exc().splitlines()[-6:]
        common.write_json_atomic(os.path.join(self.p["logs"], "selftest.json"),
                                 {"ts": time.time(), "id": msg.get("id"), "lines": lines})
        log("self-test done:\n  " + "\n  ".join(lines))

    def _apply_edit(self, op, msg):
        """Apply one edit message to the scene here (curves, unkeyed values
        and Refresh's settings, image planes, path curves, deleted curves)."""
        if op == "curves":
            for curve in msg.get("curves") or []:
                try:
                    self.apply_curve(curve)
                except Exception:
                    # One bad curve must not stop the others or the re-render.
                    self.last_error = traceback.format_exc()
                    log("ERROR rebuilding %s:\n%s" % (curve.get("curve"), self.last_error))
        elif op == "statics":
            for plug, value in msg.get("values") or []:
                self._set(plug, value)
            if msg.get("display"):           # Refresh: your viewport's settings now
                self.cfg["display"] = msg["display"]
                self.cfg["display_from"] = msg.get("display_from", "")
                self._apply_display()
                self._reload_textures()
                log("viewport settings refreshed (%s)" % self._display_text())
            if msg.get("image_planes") is not None:
                self.sync_image_planes(msg["image_planes"])
            if "gpu" in msg:
                self._set_gpu(bool(msg["gpu"]), msg.get("gpu_reason") or "")
        elif op == "image_planes":
            self.sync_image_planes(msg.get("planes") or [])
        elif op == "curve_shapes":
            for item in msg.get("shapes") or []:
                self.set_curve_shape(item.get("shape"), item.get("cvs") or [],
                                     item.get("degree"), item.get("knots"))
        elif op == "delete_curve":
            self.delete_curve(msg)
        elif op == "delete_curves":          # many at once (reference unloaded, etc.)
            for item in msg.get("curves") or []:
                self.delete_curve(item)

    def _time_edit(self, msg, ranges, t_apply):
        """Start timing a curve edit for worker.log's speed line ("edit
        synced: ..."). An edit that overlaps ones still rendering takes
        them over: one log line for what you see as one change (a drag,
        undo after edit)."""
        frames = set()
        for a, b in ranges:
            frames.update(range(max(self.first, int(a)), min(self.last, int(b)) + 1))
        now = time.time()
        sent = msg.get("ts") or now
        merged = [e for e in self.edits if e["frames"] & frames]
        for e in merged:
            frames |= e["frames"]
        self.edits = [e for e in self.edits if e not in merged][-20:] + [{
            "sent": sent, "edited": msg.get("edited") or sent,
            "picked": t_apply, "applied": now, "frames": frames, "n": len(frames),
            "first": None, "batches": [], "merged": len(merged)}]

    def set_paused(self, on, focus=None):
        """Pause: keep applying edits (frames go red) but render nothing.
        Resume: start again from the frame you're on (focus), on its own first."""
        if on == getattr(self, "paused", False):
            return
        self.paused = on
        self.edits = []                     # no "edit synced" lines spanning a pause
        if on:
            log("re-rendering paused")
            return
        if focus is not None:
            focus = min(max(int(focus), self.first), self.last)
            for st in self.cams.values():
                st["focus"] = focus
        self.after_edit = True
        log("re-rendering resumed at frame %s (%d frames to redo)"
            % (focus, sum(len(st["dirty"]) for st in self.cams.values())))

    # ---------------------------------------------------------------- scene edits
    def set_curve_shape(self, shape, cvs, degree=None, knots=None):
        """A path curve changed in your Maya (b18). b20: the whole curve is
        replaced in one step with `curve -replace` (keeps its connections, e.g.
        the motion path; checked on the studio's path rig), so added or
        removed CVs work too. Same CV count without knots: b19's one API call."""
        if not shape or not cmds.objExists(shape):
            log("path curve %s isn't in the background scene: Reload scene to bring it" % shape)
            return
        have = [tuple(p) for p in (cmds.getAttr(shape + ".cv[*]") or [])]
        name = shape.split("|")[-1]
        if degree and knots:
            try:
                cmds.curve(shape, replace=True, degree=int(degree), point=[tuple(p) for p in cvs], knot=list(knots))
                if len(have) == len(cvs):
                    far = max(sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5 for p, q in zip(have, cvs)) if cvs else 0
                    what = "CVs moved up to %.2f" % far
                else:
                    what = "%d CVs now (was %d)" % (len(cvs), len(have))
                log("path curve %s updated (%s, replaced in one step)" % (name, what))
                return
            except Exception as error:
                log("path curve %s: replace failed (%s)" % (name, error))
        if len(have) != len(cvs):
            log("path curve %s now has %d CVs (was %d): Reload scene to update its shape"
                % (name, len(cvs), len(have)))
            return
        # b19: all CVs in one call through the API, then tell the curve it
        # changed. b18 set them one at a time with setAttr: each one made Maya
        # re-evaluate the motion path mid-change, and the background Maya
        # crashed ("double free or corruption") on the next frame (studio).
        try:
            sel = om.MSelectionList()
            sel.add(shape)
            fn = om.MFnNurbsCurve(sel.getDagPath(0))
            fn.setCVPositions(om.MPointArray([om.MPoint(p[0], p[1], p[2]) for p in cvs]), om.MSpace.kObject)
            fn.updateCurve()
            how = "in one go"
        except Exception as error:
            log("path curve %s: one-call update failed (%s), setting CVs one by one" % (shape, error))
            for i, p in enumerate(cvs):
                try:
                    cmds.setAttr("%s.controlPoints[%d]" % (shape, i), p[0], p[1], p[2])
                except Exception as error2:
                    log("path curve %s CV %d: %s" % (shape, i, error2))
                    return
            how = "one by one"
        log("path curve %s updated (%d CVs, %s)" % (shape.split("|")[-1], len(cvs), how))

    def sync_image_planes(self, planes):
        """Make this scene's camera image planes match yours: update the ones
        it has, make the ones added since Start, delete the ones you deleted
        (never a referenced one). Returns how many changed."""
        wanted = {p["name"]: p for p in planes}
        changed = 0
        for shape in cmds.ls(type="imagePlane", long=True) or []:
            tr = (cmds.listRelatives(shape, parent=True, fullPath=True) or [shape])[0]
            name = tr.split("|")[-1]
            if name in wanted or not (cmds.imagePlane(shape, query=True, camera=True) or []):
                continue
            try:
                if cmds.referenceQuery(tr, isNodeReferenced=True):
                    continue
            except Exception as error:
                _ignored(error)
            try:
                cmds.delete(tr)
                changed += 1
                log("image plane %s removed (gone from your scene)" % name)
            except Exception as error:
                log("could not remove image plane %s: %s" % (name, error))
        for name, p in wanted.items():
            try:
                changed += self._mirror_plane(name, p)
            except Exception as error:
                log("image plane %s not mirrored: %s" % (name, error))
        if changed:
            log("image planes synced: %d change(s), %d plane(s)" % (changed, len(wanted)))
        self._planes_hidden = set()         # visibility is yours again, as just mirrored
        self._apply_plane_visibility()
        return changed

    def _mirror_plane(self, name, p):
        shapes = [s for s in (cmds.ls(name, long=True) or [])
                  for s in (cmds.listRelatives(s, shapes=True, type="imagePlane", fullPath=True) or [])]
        made = 0
        if shapes:
            shape = shapes[0]
        else:
            if not cmds.objExists(p.get("camera") or ""):
                log("image plane %s: camera %s isn't in the background scene" % (name, p.get("camera")))
                return 0
            cam = (cmds.listRelatives(p["camera"], shapes=True, type="camera", fullPath=True)
                   or [p["camera"]])[0]
            new = cmds.imagePlane(camera=cam, fileName=(p.get("attrs") or {}).get("imageName") or "")
            tr = cmds.rename(new[0], name)
            shape = cmds.listRelatives(tr, shapes=True, type="imagePlane", fullPath=True)[0]
            made = 1
            log("image plane %s added on %s" % (name, p["camera"]))
        tr = (cmds.listRelatives(shape, parent=True, fullPath=True) or [shape])[0]
        attrs = dict(p.get("attrs") or {})
        if p.get("time"):
            attrs.pop("frameExtension", None)          # driven by the time slider
            if not cmds.listConnections(shape + ".frameExtension", source=True, destination=False):
                cmds.connectAttr("time1.outTime", shape + ".frameExtension", force=True)
        for attr, value in attrs.items():
            self._set("%s.%s" % (shape, attr), value)
        self._set(tr + ".visibility", bool(p.get("visible", True)))
        return made

    def _set(self, plug, value):
        try:
            if not cmds.objExists(plug):
                return
            if cmds.listConnections(plug, source=True, destination=False):
                return
            if isinstance(value, str):
                cmds.setAttr(plug, value, type="string")
            else:
                cmds.setAttr(plug, value)
        except Exception as error:
            log("setAttr %s failed: %s" % (plug, error))

    def find_curve(self, data, create=True):
        name = data.get("curve")
        if name and cmds.objExists(name) and cmds.nodeType(name).startswith("animCurveT"):
            return name
        plug = data.get("plug")
        if not plug or not cmds.objExists(plug):
            return None
        src = cmds.listConnections(plug, source=True, destination=False,
                                   type="animCurve", skipConversionNodes=True) or []
        if src or not create:
            return src[0] if src else None
        keys = data.get("keys") or []
        cmds.setKeyframe(plug, time=keys[0][0] if keys else self.first)
        src = cmds.listConnections(plug, source=True, destination=False,
                                   type="animCurve", skipConversionNodes=True) or []
        return src[0] if src else None

    def apply_curve(self, data):
        curve = self.find_curve(data)
        if not curve:
            log("no curve for %s (%s), skipped" % (data.get("curve"), data.get("plug")))
            return
        samples = data.get("samples") or []
        err = None
        # Update the keys in place first: the curve is never left without keys,
        # so Maya doesn't treat it as un-animated and rebuild its evaluation
        # for the whole rig (it cost ~0.7 s on the next frame). If that doesn't
        # match your Maya, fall back to removing and re-adding every key.
        for rebuild in (self._update_keys, self._rebuild):
            for convert in (self.convert_units, not self.convert_units):
                rebuild(curve, data, convert)
                err = self._verify(curve, samples)
                if err < 1e-3:
                    self.convert_units = convert
                    if rebuild is self._rebuild:
                        log("%s: in-place update didn't match, rebuilt instead" % curve)
                    return
        log("WARNING %s rebuilt but differs from foreground by %.5f" % (curve, err))

    def _update_keys(self, curve, data, convert):
        """Make the curve's keys match data without ever emptying it: set
        existing keys, add new ones, then remove the ones that are gone."""
        fn = oma.MFnAnimCurve(_mobj(curve))
        unit = om.MTime.uiUnit()
        keys = sorted(data["keys"], key=lambda k: k[0])
        change = oma.MAnimCurveChange()
        for k in keys:
            t = om.MTime(k[0], unit)
            index = fn.find(t)
            if index is None:
                fn.addKey(t, k[1], int(k[2]), int(k[3]))
            else:
                fn.setValue(index, k[1], change)
        wanted = {round(k[0], 4) for k in keys}
        for i in range(fn.numKeys - 1, -1, -1):
            if round(fn.input(i).asUnits(unit), 4) not in wanted:
                fn.remove(i, change)
        self._set_curve_attrs(fn, data, keys, convert, change)

    def _rebuild(self, curve, data, convert):
        fn = oma.MFnAnimCurve(_mobj(curve))
        unit = om.MTime.uiUnit()
        for i in range(fn.numKeys - 1, -1, -1):
            fn.remove(i)
        fn.setIsWeighted(bool(data["weighted"]))
        fn.setPreInfinityType(int(data["pre"]))
        fn.setPostInfinityType(int(data["post"]))
        keys = data["keys"]
        change = oma.MAnimCurveChange()  # API 2.0 rejects None here; undo is off anyway
        for k in keys:
            fn.addKey(om.MTime(k[0], unit), k[1], int(k[2]), int(k[3]))
        self._set_curve_attrs(fn, data, keys, convert, change, infinity=False)

    def _set_curve_attrs(self, fn, data, keys, convert, change, infinity=True):
        if infinity:
            if fn.isWeighted != bool(data["weighted"]):
                fn.setIsWeighted(bool(data["weighted"]))
            fn.setPreInfinityType(int(data["pre"]))
            fn.setPostInfinityType(int(data["post"]))
        # Second pass, once all neighbours exist, so auto tangents compute correctly.
        for i, k in enumerate(keys):
            _t, _v, itt, ott, ix, iy, ox, oy, tlock, wlock, breakdown = k
            fn.setTangentsLocked(i, False)
            fn.setWeightsLocked(i, False)
            fn.setInTangentType(i, int(itt))
            fn.setOutTangentType(i, int(ott))
            if int(itt) == FIXED:
                fn.setTangent(i, ix, iy, True, change, convert)
            if int(ott) == FIXED:
                fn.setTangent(i, ox, oy, False, change, convert)
            fn.setWeightsLocked(i, bool(wlock))
            fn.setTangentsLocked(i, bool(tlock))
            fn.setIsBreakdown(i, bool(breakdown))

    def _verify(self, curve, samples):
        if not samples:
            return 0.0
        fn = oma.MFnAnimCurve(_mobj(curve))
        unit = om.MTime.uiUnit()
        worst = 0.0
        for t, value in samples:
            got = fn.evaluate(om.MTime(t, unit))
            worst = max(worst, abs(got - value) / max(1.0, abs(value)))
        return worst

    def delete_curve(self, msg):
        curve = self.find_curve(msg, create=False)
        if curve:
            try:
                cmds.delete(curve)
            except Exception as error:
                log("delete %s failed: %s" % (curve, error))
        self._set(msg.get("plug"), msg.get("value"))

    # ---------------------------------------------------------------- rendering
    def pick_chunk(self, cam):
        st = self.cams[cam]
        todo = self._todo(cam)
        frames = sorted(todo)
        after = [f for f in frames if f >= st["focus"]]
        start = after[0] if after else frames[0]
        size = self.chunk_size(cam)
        chunk = [start]
        while len(chunk) < size and chunk[-1] + 1 in todo:
            chunk.append(chunk[-1] + 1)
        return chunk

    def render_model(self, cam):
        """(start-up seconds, seconds per frame) for this camera's playblasts,
        fitted to the recent ones, or None until there are two batch sizes."""
        samples = self.timings.get(cam) or []
        if len({n for n, _ in samples}) < 2:
            return None
        k = float(len(samples))
        mn = sum(n for n, _ in samples) / k
        md = sum(d for _, d in samples) / k
        var = sum((n - mn) ** 2 for n, _ in samples)
        per = sum((n - mn) * (d - md) for n, d in samples) / var if var else 0.0
        if per <= 0:
            per = min(d / n for n, d in samples)
        start = max(0.0, md - per * mn)
        return start, max(per, 1e-3)

    def _no_overscan(self, cam):
        """Cached frames are exactly the camera's resolution gate (this is the
        background copy, so your camera keeps its overscan). Drawings exported
        to Blue Pencil rely on it."""
        try:
            for shape in cmds.listRelatives(cam, shapes=True, type="camera", fullPath=True) or []:
                if abs(cmds.getAttr(shape + ".overscan") - 1.0) > 1e-6:
                    cmds.setAttr(shape + ".overscan", 1.0)
                # 2D pan/zoom is a viewing aid: the cache is always the full
                # frame (drawings and Blue Pencil are laid out on it)
                if cmds.attributeQuery("panZoomEnabled", node=shape, exists=True) and \
                        cmds.getAttr(shape + ".panZoomEnabled"):
                    cmds.setAttr(shape + ".panZoomEnabled", False)
                    log("2D pan/zoom on %s ignored in the cache (full frame)" % shape.split("|")[-2])
        except Exception as error:
            _ignored(error)

    def chunk_size(self, cam):
        """Batch size for the next render: 1 frame right after an edit on the
        viewed camera, else as many frames as fit the batch time (see top)."""
        largest = max(1, int(self.cfg.get("chunk") or 12))
        self._forced_single = False
        if cam == self.view and self.after_edit:
            self.after_edit = False
            self._forced_single = True     # includes the edit's own cost: don't learn from it
            return 1
        model = self.render_model(cam)
        if model is None:                  # measure: one frame, then FIRST_BATCH
            sizes = {n for n, _ in self.timings.get(cam) or []}
            return 1 if 1 not in sizes else min(largest, FIRST_BATCH)
        start, per = model
        target = max(BATCH_TARGET_S, start / OVERHEAD_SHARE)
        # Grow at most to double the biggest measured batch: a fit can be off
        # while the render speed changes (another camera, heavier frames).
        grow = 2 * max(n for n, _ in self.timings[cam])
        return max(1, min(largest, grow, int((target - start) / per)))

    def _playblast(self, prefix, a, b):
        """Playblast frames a-b of the render view to prefix.####.jpg; seconds taken."""
        kwargs = dict(
            startTime=a, endTime=b, format="image", compression="jpg",
            quality=self.cfg["quality"], percent=100,
            widthHeight=(self.cfg["width"], self.cfg["height"]),
            filename=prefix, framePadding=4, forceOverwrite=True, viewer=False,
            showOrnaments=False, offScreen=True, clearCache=True)
        t = time.time()
        try:
            cmds.playblast(editorPanelName=self.panel, **kwargs)
        except Exception as error:
            if "editorPanelName" not in str(error):
                raise
            cmds.setFocus(self.panel)
            cmds.playblast(**kwargs)
        return time.time() - t

    def render(self, cam, chunk):
        t_render = time.time()
        self.trace("render %s %d-%d" % (cam.split("|")[-1], chunk[0], chunk[-1]))
        st = self.cams[cam]
        if cam != self.panel_camera:
            cmds.modelEditor(self.panel, edit=True, camera=cam)
            self.panel_camera = cam
            self._no_overscan(cam)
        tmp = self.p["tmp"]
        for old in glob.glob(os.path.join(tmp, "*")):
            try:
                os.remove(old)
            except OSError:
                pass
        prefix = os.path.join(tmp, "pb")
        t_blast = self._playblast(prefix, chunk[0], chunk[-1])

        self.version += 1
        done = set()
        for path in glob.glob(prefix + ".*.jpg"):
            match = FRAME_RE.search(path)
            if not match:
                continue
            frame = int(match.group(1))
            os.replace(path, common.frame_path(self.session, frame, cam))
            st["versions"][frame] = self.version
            st["dirty"].discard(frame)
            done.add(frame)

        if done:
            self._recent = [r for r in self._recent if t_render - r[0] < GPU_REDO_S] + [(t_render, cam, set(done))]
        for frame in set(chunk) - done:
            st["failures"][frame] += 1
            if st["failures"][frame] >= MAX_RENDER_FAILURES:
                log("frame %d (%s) failed to render %d times, giving up on it"
                    % (frame, cam, MAX_RENDER_FAILURES))
                st["dirty"].discard(frame)
        st["focus"] = chunk[-1] + 1
        took = time.time() - t_render
        self.trace("rendered %d frames in %.2fs (playblast %.2fs)%s" % (
            len(done), took, t_blast, " first after edit" if getattr(self, "_forced_single", False) else ""))
        if done and not getattr(self, "_forced_single", False):
            self.timings[cam] = (self.timings.get(cam) or [])[-7:] + [(len(chunk), took)]   # recent 8
        self._check_render(cam, done)
        if done and not self.startup_logged and self.timing is not None and self.ready_t:
            self.startup_logged = True
            try:
                self._log_startup(time.time() - t_render)
            except Exception as error:
                log("startup timing: %s" % error)
        if cam == self.view:
            for edit in self.edits:
                if edit["frames"] & done:
                    edit["batches"].append(len(done))
            self._time_edits(done)

    def _set_gpu(self, on, reason=""):
        """Refresh: GPU deformers on or off like your Maya's GPU Override now."""
        if on == self.gpu_on:
            return
        try:
            cmds.evaluator(name="deformer", enable=on)
        except Exception as error:
            log("couldn't switch GPU deformers %s: %s" % ("on" if on else "off", error))
            return
        self.gpu_on = on
        self.cfg["background_gpu"], self.cfg["gpu_reason"] = on, reason
        if on:
            self.warning = ""              # a fresh try on the GPU
            self._gpu_check_t = 0.0
        log("GPU deformers switched %s by Refresh (%s)" % ("on" if on else "off", reason or "your Maya"))

    def _check_gpu(self, force=False):
        """Every couple of seconds: has Maya printed graphics-memory errors
        (they go to worker.log)? Then switch this Maya's deformers to the CPU,
        redo the frames rendered just before (they may be wrong), and tell
        the player and the Maya panel."""
        now = time.time()
        if not force and now - self._gpu_check_t < GPU_CHECK_S:
            return
        self._gpu_check_t = now
        text, self._log_pos = common.read_new(self.p["log"], self._log_pos)
        if not text or not common.GPU_TROUBLE_RE.search(text):
            return
        if not self.gpu_on:
            return                     # already on the CPU (or never used the GPU)
        try:
            cmds.evaluator(name="deformer", enable=False)
            self.gpu_on = False
        except Exception as error:
            log("couldn't switch GPU deformers off: %s" % error)
            self.warning = ("GPU deformers failed in the background Maya and couldn't be "
                            "switched off: bgcache restarts it on the CPU if caching stops.")
            return
        redo = 0
        for when, cam, frames in self._recent:
            st = self.cams.get(cam)
            if st and now - when < GPU_REDO_S:
                frames = {f for f in frames if self.first <= f <= self.last}
                st["dirty"] |= frames
                for f in frames:
                    st["failures"][f] = 0
                redo += len(frames)
        self._recent = []
        self.warning = ("GPU deformers failed in the background Maya: caching on the CPU "
                        "now (slower).")
        log("GPU deformers failed (errors above): switched off in the background Maya, "
            "caching on the CPU; redoing %d recent frame(s)" % redo)
        self.write_status()

    def _time_edits(self, done):
        """Log how long each edit took to show up in the player (viewed camera)."""
        now = time.time()
        for edit in list(self.edits):
            if edit["first"] is None and edit["frames"] & done:
                edit["first"] = now
            edit["frames"] -= done
            if not edit["frames"]:
                edit["model"] = self.render_model(self.view) if self.view else None
                log(edit_synced_line(edit, now))
                self.edits.remove(edit)

    # ---------------------------------------------------------------- status
    def write_status(self, state=None):
        if state is None:
            if not self.cams:
                state = "ready, pick a camera"
            elif any(self._todo(cam) for cam in self.cams):
                state = "paused" if getattr(self, "paused", False) else "rendering"
            else:
                state = "ready"
        status = {
            "start": self.first, "end": self.last, "fps": self.cfg.get("fps", 24.0),
            "view": self.view, "checked": list(self.order),
            "cameras": {cam: {"dirty": sorted(st["dirty"]),
                              "versions": {str(k): v for k, v in st["versions"].items()}}
                        for cam, st in self.cams.items()},
            "state": state, "error": self.last_error[-1000:],
            "paused": bool(getattr(self, "paused", False)),
            "reloads": getattr(self, "reloads", 0),     # Reload scene's done so far
            "warning": self.warning,
            "gpu": self.gpu_on,
            "pid": os.getpid(),             # the player's Stop can end this Maya if yours is frozen
        }
        # The idle loop runs every 50 ms: only rewrite the file when something
        # changed (the player re-reads it when it changes), plus a heartbeat.
        key = repr(sorted(status.items(), key=lambda kv: kv[0]))
        now = time.time()
        if key == self._status_key and now - self._status_t < STATUS_HEARTBEAT:
            return
        self._status_key, self._status_t = key, now
        status["ts"] = now
        common.write_json_atomic(self.p["status"], status)


def edit_synced_line(edit, now):
    """One log line per edit: how long until the first new frame and the last,
    split into the steps on the way, with the batch sizes used."""
    first = edit["first"] if edit["first"] is not None else now
    edited = edit.get("edited") or edit["sent"]
    parts = ["edit synced: %d frames" % edit["n"],
             "first frame after %.2fs" % (first - edited),
             "all after %.1fs" % (now - edited),
             "(your Maya %.2fs, pickup %.2fs, apply %.2fs, first frame render %.2fs)" % (
                 edit["sent"] - edited, edit["picked"] - edit["sent"],
                 edit.get("applied", edit["picked"]) - edit["picked"],
                 first - edit.get("applied", edit["picked"]))]
    if edit.get("merged"):
        parts[0] += " (+%d earlier edits still rendering)" % edit["merged"]
    batches = edit.get("batches") or []
    if batches:
        shown = batches[:8]
        parts.append("batches %s%s" % (",".join(str(b) for b in shown),
                                       ",..." if len(batches) > 8 else ""))
    if edit.get("model"):
        parts.append("render %.2fs start-up + %.2fs/frame" % edit["model"])
    return ", ".join(parts[:3]) + " " + " ".join(parts[3:])


def boot():
    """Called by the controller via: maya -command 'python("...boot()")'"""
    global _log_path
    cfg = common.read_json(os.environ["BGCACHE_CONFIG"])
    _log_path = common.paths(cfg["session"])["log"]
    cfg["_boot_t"] = time.time()
    try:   # Maya may have restored the animator's control panel from their layout
        if cmds.workspaceControl("bgcacheWorkspaceControl", exists=True):
            cmds.deleteUI("bgcacheWorkspaceControl")
    except Exception as error:
        _ignored(error)

    def _go():
        global _worker
        try:
            _worker = Worker(cfg)
            _worker.setup()
        except Exception:
            log(traceback.format_exc())
            if _worker:
                _worker.last_error = traceback.format_exc()
                _worker.write_status("error")

    cmds.evalDeferred(_go, lowestPriority=True)
