import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types
from unittest import mock
maya = types.ModuleType("maya"); cmds = mock.MagicMock(); api = types.ModuleType("maya.api")
om = types.ModuleType("maya.api.OpenMaya"); oma = types.ModuleType("maya.api.OpenMayaAnim")
oma.MFnAnimCurve = types.SimpleNamespace(kTangentFixed=1, kConstant=0)
mel = mock.MagicMock(); maya.mel = mel; maya.__path__ = []
for n, m in (("maya", maya), ("maya.cmds", cmds), ("maya.mel", mel), ("maya.api", api), ("maya.api.OpenMaya", om), ("maya.api.OpenMayaAnim", oma)):
    sys.modules[n] = m
maya.cmds = cmds
qt = types.ModuleType("PySide2"); qt.QtCore = mock.MagicMock(); qt.QtGui = mock.MagicMock(); qt.QtWidgets = mock.MagicMock()
sys.modules.update({"PySide2": qt, "PySide2.QtCore": qt.QtCore, "PySide2.QtGui": qt.QtGui,
                    "PySide2.QtWidgets": qt.QtWidgets, "shiboken2": mock.MagicMock()})
sys.path.insert(0, REPO)
from bgcache import worker
calls = []
cmds.window.return_value = False
cmds.modelPanel.return_value = "modelPanel9"
cmds.modelEditor.side_effect = lambda panel, **k: calls.append(k)
w = worker.Worker.__new__(worker.Worker)
w.cfg = {"width": 960, "height": 540, "display": {
    "polymeshes": True, "pluginShapes": True,
    "pluginObjects": {"gpuCacheDisplayFilter": True, "studioSetProxy": True, "bifrostGraphShape": False}}}
w._build_panel()
assert calls[0] == {"edit": True, "allObjects": True}
on = [k["pluginObjects"] for k in calls if "pluginObjects" in k]
# envirs (the plug-in shapes your viewport shows) start hidden: characters and animation only
assert ("gpuCacheDisplayFilter", False) in on and ("studioSetProxy", False) in on
assert not any(name == "bifrostGraphShape" for name, _ in on)      # hidden in your viewport: never touched
assert {"edit": True, "nurbsCurves": False} in calls and {"edit": True, "grid": False} in calls
assert not any(k.get("allObjects") is False for k in calls)
print("ok: render view starts with everything shown except envirs (plug-in shapes off by default); overlays hidden")
from bgcache import controller
cmds.pluginDisplayFilter.return_value = ["gpuCacheDisplayFilter", "studioSetProxy"]
cmds.modelEditor.side_effect = lambda panel, **k: k.get("queryPluginObjects") == "gpuCacheDisplayFilter"
assert controller.plugin_display_filters("modelPanel4") == {"gpuCacheDisplayFilter": True, "studioSetProxy": False}
print("ok: your viewport's plug-in filter settings are read one by one")

# ===== 0.6.8/0.6.9: environment filters kept off in the cache =====
cmds.pluginDisplayFilter.side_effect = None
def pdf(name=None, query=False, listFilters=False, classification=False):
    if listFilters: return ["mayaUsdProxyShapeBaseDisplayFilter", "gpuCacheDisplayFilter", "bifrostGraphShape"]
    return {"mayaUsdProxyShapeBaseDisplayFilter": "drawdb/subscene/vp2RenderDelegate/mayaUsdProxyShapeBase",
            "gpuCacheDisplayFilter": "drawdb/geometry/gpuCache", "bifrostGraphShape": "drawdb/geometry/bifrost"}[name]
cmds.pluginDisplayFilter.side_effect = pdf
calls.clear(); cmds.modelEditor.side_effect = lambda panel, **k: calls.append(k)
w3 = worker.Worker.__new__(worker.Worker)
w3.cfg = {"width": 960, "height": 540, "display": {"pluginShapes": False,
          "pluginObjects": {"mayaUsdProxyShapeBaseDisplayFilter": False, "bifrostGraphShape": False}}}
w3._build_panel()
assert set(w3.plugin_filters) == {"mayaUsdProxyShapeBaseDisplayFilter", "gpuCacheDisplayFilter"}, w3.plugin_filters
calls.clear(); w3._apply_envirs()
assert ("mayaUsdProxyShapeBaseDisplayFilter", False) in [k["pluginObjects"] for k in calls if "pluginObjects" in k]
assert ("gpuCacheDisplayFilter", False) in [k["pluginObjects"] for k in calls if "pluginObjects" in k]
assert not any(k.get("pluginObjects", ("",))[0] == "bifrostGraphShape" for k in calls)
assert not hasattr(worker.Worker, "envirs_visibility")
print("ok: (0.6.9, Envirs removed) the set is never drawn in the cache: characters and animation only")

# the viewport read at Start: a focused panel that's not on screen is skipped
cmds.getPanel.side_effect = lambda **k: ("modelPanel4" if k.get("withFocus") else
                                         ["outlinerPanel1", "modelPanel2"] if k.get("visiblePanels") else
                                         ("modelPanel" if str(k.get("typeOf", "")).startswith("modelPanel") else "other"))
assert controller._active_model_panel() == "modelPanel2"
print("ok: Start reads the viewport on screen, not a hidden one Maya still says has focus")
cmds.pluginDisplayFilter.side_effect = pdf
cmds.modelEditor.side_effect = lambda panel, **k: panel == "modelPanel3" and k.get("queryPluginObjects") == "gpuCacheDisplayFilter"
got = controller.plugin_display_filters(["modelPanel2", "modelPanel3"])
assert got["gpuCacheDisplayFilter"] is True and got["mayaUsdProxyShapeBaseDisplayFilter"] is False
print("ok: a filter on in any visible viewport counts as on")

# ===== 0.7.2: Refresh applies new viewport settings in the background Maya =====
cmds.pluginDisplayFilter.side_effect = pdf
calls.clear(); cmds.modelEditor.side_effect = lambda panel, **k: calls.append(k)
w4 = worker.Worker.__new__(worker.Worker)
w4.cfg = {"width": 960, "height": 540, "start": 1001, "end": 1010, "display": {"displayAppearance": "smoothShaded"}}
w4._build_panel()
w4.log = None
marked = []
w4.mark = lambda a, b: marked.append((a, b))
w4.first, w4.last, w4.cams, w4.view, w4.edits = 1001, 1010, {}, None, []
w4.trace = lambda *a: None
calls.clear()
w4.handle({"op": "statics", "values": [], "ranges": [[1001, 1010]],
           "display": {"displayAppearance": "smoothShaded", "wireframeOnShaded": True}})
assert {"edit": True, "wireframeOnShaded": True} in calls and calls[0] == {"edit": True, "allObjects": True}
assert {"edit": True, "grid": False} in calls          # overlays still forced off
assert marked == [(1001, 1010)] and w4.cfg["display"]["wireframeOnShaded"] is True
assert "wireframe on shaded" in w4._display_text()
print("ok: Refresh's viewport settings are applied to the render view, and every frame re-renders")

src = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert 'evaluator(name="invisibility", enable=True)' in src
print("ok: the background Maya skips evaluating what only feeds hidden things (invisibility evaluator)")
