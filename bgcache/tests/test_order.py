import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
import sys, types, os, json, tempfile
from unittest import mock
home = tempfile.mkdtemp(); os.environ["HOME"] = home
qt = types.ModuleType("PySide2"); qc = mock.MagicMock(); qg = mock.MagicMock()
qt.QtCore, qt.QtGui = qc, qg
sys.modules.update({"PySide2": qt, "PySide2.QtCore": qc, "PySide2.QtGui": qg})
sys.path.insert(0, REPO)
from bgcache.continuity import resolver as cr, reel
cr.CONFIG_PATH = os.path.join(home, ".studio_ref_config.json")
names = [d["name"] for d in cr.get_departments()]
assert names == ["P", "WP", "shoco", "lighting", "editorial"]
assert not os.path.exists(cr.CONFIG_PATH)              # bgcache never writes the shot reference tool's file
assert reel.department_order() == ["P", "WP", "shoco", "editorial", "lighting"]
have = {"sq050_0470": {"lighting", "editorial"}, "sq050_0473": {"shoco", "lighting"}, "sq050_0481": set()}
def fake(show, shot, dept=None):
    return {"department": dept, "version": 3} if dept in have[shot] else None
with mock.patch.object(cr, "resolve_shot", fake):
    assert reel.resolve_info("BIRDS", "sq050_0470")["department"] == "editorial"   # editorial before lighting
    assert reel.resolve_info("BIRDS", "sq050_0473")["department"] == "shoco"
    assert reel.resolve_info("BIRDS", "sq050_0470", "lighting")["department"] == "lighting"   # hand-picked wins
    assert reel.resolve_info("BIRDS", "sq050_0481") is None
assert not os.path.exists(cr.CONFIG_PATH)
print("ok: Auto order P, WP, shoco, editorial, lighting; hand-picked department wins; shot reference tool's config never written")
