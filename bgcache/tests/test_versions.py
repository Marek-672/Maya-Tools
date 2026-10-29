"""b10: continuity versions. The department menu lists a department's
versions (pin one); a card shows "v012 -> v013" when newer footage comes in
while the player is open; pinned shots never show it."""
import os, sys, json, types, tempfile
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
JOBS = tempfile.mkdtemp()
prof = {"shot_folder": JOBS + "/projects/{show}/{shot}", "sequence_from_shot": "{sequence}_*",
        "departments": [{"name": "P", "base_path": "{shot_folder}/p", "version_pattern": "P_{shot}_v*",
                         "source_type": "image_sequence"}],
        "auto_order": ["P"]}
json.dump(prof, open(os.path.join(JOBS, "profile.json"), "w"))
os.environ["BGCACHE_PROFILE"] = os.path.join(JOBS, "profile.json")
def make(v):
    d = os.path.join(JOBS, "projects", "SHOW", "sq010_0020", "p", "P_sq010_0020_v%03d" % v)
    os.makedirs(d, exist_ok=True)
    for f in range(1001, 1004):
        open(os.path.join(d, "p.%04d.jpg" % f), "w").write("x")
for v in (10, 11, 12):
    make(v)
exec(open(os.path.join(TESTS, "test_reload.py")).read().split("sys.path.insert(0, REPO)")[0])   # Qt stubs
sys.path.insert(0, REPO)
from bgcache.continuity import resolver as cr, reel

assert cr.list_versions("SHOW", "sq010_0020", "P") == [12, 11, 10]
assert reel.resolve_info("SHOW", "sq010_0020")["version"] == 12
pinned = reel.resolve_info("SHOW", "sq010_0020", "P", 10)
assert pinned["version"] == 10 and "P_sq010_0020_v010" in pinned["source_path"]
assert reel.resolve_info("SHOW", "sq010_0020", "P", 99) is None
print("ok: versions listed newest first; a pinned version resolves to its own folder")

# The player side: the newer-footage check and the menu's update
from bgcache.continuity import ui
class FakePlayer(ui.Continuity):
    def __init__(s):
        s.shot_ids = ("SHOW", "sq010_0020", "sq010"); s.live_shot = "sq010_0010"
        s.infos = {"sq010_0020": reel.resolve_info("SHOW", "sq010_0020")}
        s.dept_override, s.version_pin, s.newer = {}, {}, {}
        s.reel_mod = reel
        s.jobs = types.SimpleNamespace(add=lambda prio, fn, cb: cb("done", fn(None)))
        s.browser = types.SimpleNamespace(cards={})
P = FakePlayer()
P._check_newer(); assert P.newer == {}
print("ok: nothing new: no marker")
make(13)
P._check_newer()
assert P.newer["sq010_0020"]["version"] == 13
print("ok: v013 comes in while the player is open: the card is marked (v012 -> v013)")
P.version_pin["sq010_0020"] = 12; P.newer.clear()
P._check_newer(); assert P.newer == {}
print("ok: a pinned shot is never marked")
src = open(os.path.join(REPO, "bgcache", "continuity", "ui.py")).read()
assert '"Update to %s"' in src and "More versions..." in src and '" \\u2192 v%03d"' in src
print("ok: the menu offers Update, the 10 newest versions and More versions...")
