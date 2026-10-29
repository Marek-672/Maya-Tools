"""0.8.0b17: (1) GPU Override off with the deformer evaluator not registered
was read as on (studio, 2026-10-28); (2) the cache's look comes from the
viewport looking through the shot camera, and Reload scene reads it again;
(3) the player's reference image plane waits for Refresh."""
import os, sys, types, tempfile
import _source  # noqa: E402  (tests/_source.py)
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
os.environ["BGCACHE_ROOT"] = tempfile.mkdtemp()
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds"); mel = types.ModuleType("maya.mel")
api = types.ModuleType("maya.api"); om = types.ModuleType("maya.api.OpenMaya"); oma = types.ModuleType("maya.api.OpenMayaAnim")
class _F: kConstant = 0
oma.MFnAnimCurve = _F
for n, m in (("maya", maya), ("maya.cmds", cmds), ("maya.mel", mel), ("maya.api", api),
             ("maya.api.OpenMaya", om), ("maya.api.OpenMayaAnim", oma)):
    sys.modules[n] = m
qt = types.ModuleType("PySide2"); qc = types.ModuleType("PySide2.QtCore")
class T:
    def __init__(s): pass
    def setSingleShot(s, x): pass
    def start(s, *a): pass
    def stop(s): pass
    @property
    def timeout(s): return types.SimpleNamespace(connect=lambda f: None)
qc.QTimer = T; qt.QtCore = qc; sys.modules["PySide2"] = qt; sys.modules["PySide2.QtCore"] = qc
sys.path.insert(0, REPO)
from bgcache import controller

# ---- (2) two viewports: the last-clicked one (persp, textures off), the shot camera's (textures on)
panels = {"modelPanel1": {"camera": "perspShape", "displayTextures": False},
          "modelPanel4": {"camera": "noise_cameraShape", "displayTextures": True}}
cmds.getPanel = lambda visiblePanels=False, withFocus=False, typeOf=None: \
    "modelPanel" if typeOf else ("modelPanel1" if withFocus else list(panels))
cmds.modelPanel = lambda p, query=True, camera=False: panels[p]["camera"]
cmds.nodeType = lambda n: "camera" if n.endswith("Shape") else "transform"
cmds.listRelatives = lambda n, parent=False, fullPath=False, **k: ["|" + n[:-5]] if parent else []
cmds.ls = lambda *a, **k: list(a[0:1]) if a else []
def modelEditor(p, query=True, **flags):
    flag = list(flags)[0]
    return panels[p].get(flag, True) if flag != "queryPluginObjects" else False
cmds.modelEditor = modelEditor
cmds.pluginDisplayFilter = lambda **k: []
controller.scene.list_cameras = lambda: [{"name": "|noise_camera", "label": "noise_camera"}]
d = controller.viewport_display()
assert d["displayTextures"] is True, d
assert controller.scene.DISPLAY_SOURCE.startswith("modelPanel4"), controller.scene.DISPLAY_SOURCE
print("ok: the cache's look comes from the viewport looking through the shot camera "
      "(textures on), not the one you last clicked (textures off)")
controller.scene.list_cameras = lambda: [{"name": "|shotCam", "label": "shotCam"}]     # nobody looks through it
d = controller.viewport_display()
assert d["displayTextures"] is False and controller.scene.DISPLAY_SOURCE.startswith("modelPanel1")
print("ok: no viewport looks through a shot camera: the one you last clicked, as before")

c = _source.source("controller")
rl = c[c.index("    def reload_scene(self"):c.index("\n    def ", c.index("    def reload_scene(self") + 10)]
assert "display = scene.viewport_display()           # b17: read again, never reused" in rl
assert '"viewport_renderer": self.cfg.get("viewport_renderer")' in rl
print("ok: Reload scene reads your viewport again (and the renderer), it no longer reuses Start's")
w = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert '"textures %s" % ("on" if d.get("displayTextures") else "off")' in w and 'log("viewport settings: %s"' in w
print("ok: worker.log says textures on/off, lights, image planes and which viewport they came from")

# ---- (3) the reference plane waits for Refresh
show = c[c.index("    def show_image_plane"):c.index("    def _before_save")]
assert "self._send_image_planes()" not in show and "press Refresh in the player" in show
print("ok: the player's reference image plane goes into your Maya only; the cache gets it at Refresh")
