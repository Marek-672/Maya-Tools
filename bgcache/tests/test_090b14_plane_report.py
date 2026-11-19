"""0.9.0b14: the image plane report (what Maya loaded for each plane), written
by the background Maya at Start and Refresh, and printable in your own Maya."""
import os, sys, tempfile
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import plane_report as r

assert r.frame_file("/a/ref_take1.0992.jpg", 1004) == "/a/ref_take1.1004.jpg"
assert r.frame_file("/a/ref.12.exr", 7) == "/a/ref.07.exr" and r.frame_file("/a/still.jpg", 5) == "/a/still.jpg"
print("ok: the file a sequence plane shows at a frame (padding kept)")

root = tempfile.mkdtemp()
open(os.path.join(root, "ref_take1.1004.jpg"), "wb").write(b"x" * 4096)
values = {"imageName": os.path.join(root, "ref_take1.0992.jpg"), "useFrameExtension": True, "frameExtension": 1004,
          "frameOffset": 0, "depth": 100.0, "coverageX": 960, "enableTextureMaxRes": False}
cmds = mock.MagicMock()
cmds.ls.return_value = ["|cam|camShape|ref_take1|ref_takeShape1"]
cmds.imagePlane.side_effect = lambda shape, **k: ["|cam|camShape"] if k.get("camera") else [960, 540]
def getAttr(plug):
    name = plug.split(".")[-1]
    if name not in values:
        raise RuntimeError("No object matches name: " + plug)
    return values[name]
cmds.getAttr.side_effect = getAttr
cmds.listConnections.return_value = ["time1"]
cmds.displayPref.return_value = "immediate"
text = "\n".join(r.report(cmds))
assert "image planes (1):" in text and "plane ref_takeShape1 on camShape: ref_take1.1004.jpg, 4 KB" in text
assert "Maya says its size is [960, 540]" in text and "frame driven by time1" in text
assert "depth 100.0" in text and "coverageX 960" in text and "textureFilter ? (" in text
assert "enableTextureMaxRes False" in text and "material loading: immediate" in text
print("ok: each plane: the file for this frame and its size on disk, Maya's size for it, its settings; "
      "a setting this Maya doesn't have is marked, not fatal; the render settings")
values["frameExtension"] = 2000
assert "NOT ON DISK: ref_take1.2000.jpg" in "\n".join(r.report(cmds))
print("ok: a frame that isn't on disk is said so")
worker = open(os.path.join(os.path.dirname(TESTS), "bgcache", "worker.py")).read()
assert worker.count("self._log_planes()") == 2 and "plane_report.report(cmds" in worker
print("ok: the background Maya writes it to worker.log at Start and at every Refresh")
