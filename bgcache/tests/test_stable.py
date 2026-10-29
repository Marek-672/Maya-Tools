import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, time, tempfile
from unittest import mock
exec(open(os.path.join(TESTS, "test_display.py")).read().split("from bgcache import worker")[0])
from bgcache import worker
logs = []
worker.log = lambda m: logs.append(m)

# --- the layout from the crash log: Graph Editor (focus), Outliner, two viewports
closed = []
cmds.lsUI.side_effect = lambda **k: (["graphEditor1Window", "outlinerPanel1Window", "ChannelBoxLayerEditor",
                                      "AttributeEditor", "MainPane", "TimeSlider"] if k.get("type") == "workspaceControl"
                                     else ["MayaWindow", "bgcacheRenderWin", "graphEditor1Window", "scriptEditorPanel1Window", "renderViewWindow"])
cmds.workspaceControl.side_effect = lambda name, **k: True if k.get("query") else closed.append(name)
hidden = []
cmds.window.side_effect = lambda name, **k: True if k.get("query") else hidden.append(name)
cmds.deleteUI.side_effect = lambda name, **k: closed.append("DELETED:" + name)
tools = []
cmds.setToolTo.side_effect = lambda t: tools.append(t)
cmds.getPanel.side_effect = lambda **k: ["modelPanel1", "modelPanel4", "bgcachePanel"]
quiet = []
cmds.modelEditor.side_effect = lambda panel, **k: quiet.append(panel) if k.get("allObjects") is False else None
mel.eval = mock.MagicMock()
w = worker.Worker.__new__(worker.Worker)
w.cfg = {"trace": True}; w.panel = "bgcachePanel"
w._clean_ui()
assert {"graphEditor1Window", "outlinerPanel1Window", "ChannelBoxLayerEditor", "AttributeEditor"} <= set(closed)
assert "MainPane" not in closed and "TimeSlider" not in closed
assert hidden == ["graphEditor1Window"] and not [x for x in closed if x.startswith("DELETED")]
assert tools == ["selectSuperContext"]
assert quiet == ["modelPanel1", "modelPanel4"]
mel.eval.assert_called_with('setNamedPanelLayout "Single Perspective View"')
print("ok: Graph Editor / Outliner / Channel Box / Attribute Editor closed; floating Graph Editor hidden (not deleted);")
print("    Script Editor and Render View left alone; select tool set first; single view;")
print("    other viewports draw nothing; bgcache's render view and Maya's own bars untouched")
print("   ", logs[-1])

# quitting never saves preferences
quits = []
cmds.quit.side_effect = lambda **k: quits.append(k)
src = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert "cmds.quit(force=True, abort=True)" in src
print("ok: the background Maya quits with abort=True (no preferences saved)")
